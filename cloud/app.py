"""API e painel da nuvem. Sem banco local, Chrome ou tarefas contínuas."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import secrets
from statistics import median
import uuid
from urllib.parse import urlsplit

import httpx
from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from cloud.repository import Repository, configuration, user_session
from cloud.collection import collect_shop, check_offer, collect_public_coupons, ScheduledReadings
from cloud_protocol import CLOUD_SHOPS, LOCAL_SHOPS, PUBLIC_SETTINGS, SYNC_KINDS, catalog, offer_key
from core import BRAND_ALIASES, canonical_url, confirmed_price, coupon_is_today, detect_brand, effective_price, matches, offer_matches, price_is_current, reading_valid_until, source_input, top_offers, tracking_price, utcnow, valid_url
from forms import component_input_errors
from ml_coupon_applicator import application_state
from presentation import coupon_catalog, offer_card_data
from shops import Shops, shop_name

ASSETS = Path(__file__).parent / 'static'
app = FastAPI(title='Monitor de peças', docs_url=None, redoc_url=None)


@app.middleware('http')
async def request_guards(request, call_next):
    # Cookies não autorizam alterações feitas por outra origem. Workers usam Bearer.
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        origin = request.headers.get('origin')
        expected = os.environ.get('MONITOR_PUBLIC_URL', '').rstrip('/')
        host_origin = f"{request.url.scheme}://{request.headers.get('host', '')}"
        if origin and origin not in {expected, host_origin}:
            return JSONResponse({'detail': 'Origem da requisição não autorizada.'}, status_code=403)
        if not origin and request.cookies.get('monitor_access') and not request.headers.get('authorization'):
            return JSONResponse({'detail': 'Origem ausente; recarregue o painel.'}, status_code=403)
    try:
        size = int(request.headers.get('content-length', '0'))
    except ValueError:
        return JSONResponse({'detail': 'Tamanho da requisição inválido.'}, status_code=400)
    if size < 0 or size > 1_000_000:
        return JSONResponse({'detail': 'Envie os dados em lotes menores.'}, status_code=413)
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        chunks, total = [], 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > 1_000_000:
                return JSONResponse({'detail': 'Envie os dados em lotes menores.'}, status_code=413)
            chunks.append(chunk)
        request._body = b''.join(chunks)
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


@asynccontextmanager
async def repo_context(request):
    header = request.headers.get('authorization', '')
    token = header[7:] if header.startswith('Bearer ') else request.cookies.get('monitor_access')
    async with httpx.AsyncClient(timeout=20) as client:
        user = await user_session(client, token)
        yield Repository(client, token, user['id'])


async def repository(request: Request):
    async with repo_context(request) as repo:
        yield repo


def session_response(request, session, detail='Conectado.'):
    response = JSONResponse({'detail': detail})
    secure = request.url.scheme == 'https' or os.environ.get('VERCEL') == '1'
    for name, field, age in [('monitor_access', 'access_token', session.get('expires_in', 3600)),
                             ('monitor_refresh', 'refresh_token', 30 * 86400)]:
        if session.get(field):
            response.set_cookie(name, session[field], max_age=age, httponly=True, secure=secure, samesite='lax', path='/')
    return response


async def auth_call(client, path, data):
    url, key = configuration()
    response = await client.post(url + '/auth/v1/' + path, json=data, headers={'apikey': key})
    if response.is_error:
        message = 'Não foi possível entrar. Confira e-mail, senha e confirmação do e-mail.'
        if response.status_code == 429:
            message = 'Muitas tentativas. Aguarde alguns minutos antes de tentar novamente.'
        raise HTTPException(400, message)
    return response.json()


@app.post('/api/auth/{action}')
async def authentication(action: str, request: Request, data: dict = Body(default={})):
    async with httpx.AsyncClient(timeout=20) as client:
        if action == 'logout':
            url, key = configuration()
            token = request.cookies.get('monitor_access')
            if token:
                await client.post(url + '/auth/v1/logout?scope=local', headers={'apikey': key, 'Authorization': 'Bearer ' + token})
            response = JSONResponse({'detail': 'Sessão encerrada.'})
            response.delete_cookie('monitor_access')
            response.delete_cookie('monitor_refresh')
            return response
        if action == 'refresh':
            token = request.cookies.get('monitor_refresh')
            if not token:
                raise HTTPException(401, 'Entre novamente.')
            session = await auth_call(client, 'token?grant_type=refresh_token', {'refresh_token': token})
            return session_response(request, session)
        if action not in {'login', 'signup'}:
            raise HTTPException(404, 'Ação desconhecida.')
        email, password = str(data.get('email', '')).strip(), str(data.get('password', ''))
        if '@' not in email or len(email) > 254 or not 8 <= len(password) <= 128:
            raise HTTPException(422, 'Informe um e-mail e uma senha com pelo menos 8 caracteres.')
        path = 'token?grant_type=password' if action == 'login' else 'signup'
        session = await auth_call(client, path, {'email': email, 'password': password})
        return session_response(request, session, 'Conta criada. Confirme seu e-mail e depois entre.' if not session.get('access_token') else 'Conectado.')


@app.get('/health')
def health():
    return {'app': 'monitor-precos', 'mode': 'cloud', 'region': os.environ.get('VERCEL_REGION', 'local'), 'configured': bool(os.environ.get('SUPABASE_URL') and os.environ.get('SUPABASE_PUBLISHABLE_KEY'))}


@app.get('/')
def home():
    return FileResponse(ASSETS / 'index.html')


@app.get('/api/session')
async def session(repo=Depends(repository)):
    from olx import STATES
    return {'olx_states': STATES, 'connected': True, 'cloud_shops': CLOUD_SHOPS, 'local_shops': LOCAL_SHOPS, 'brands': list(BRAND_ALIASES)}


async def values(repo, kind):
    return [row['data'] for row in await repo.records(kind)]


async def components(repo):
    rows, override_rows = await asyncio.gather(values(repo, 'components'), repo.records('overrides'))
    overrides = {row['record_key']: row['data'] for row in override_rows}
    return [dict(row, **overrides.get('component:' + str(row['id']), {})) for row in rows
            if not overrides.get('component:' + str(row['id']), {}).get('deleted')]


@app.get('/api/catalog')
async def get_catalog(repo=Depends(repository)):
    parts, offers, preference_rows, statuses, commands, scans = await asyncio.gather(
        components(repo), values(repo, 'offers'), repo.records('preferences'),
        values(repo, 'status'), repo.commands(), repo.records('scans'))
    prefs = {row['record_key']: row['data'] for row in preference_rows}
    saved = [dict(row, **prefs.get(str(row['id']), {})) for row in offers]
    for row in saved:
        row['display'] = offer_card_data(row)
    groups = catalog(parts, offers, prefs)
    for group in groups:
        for row in group['offers']:
            row['display'] = offer_card_data(row)
    return {'groups': groups, 'components': parts, 'offers': saved,
            'status': statuses, 'commands': commands,
            'scan_next_at': {row['record_key']: (datetime.fromisoformat(row['updated_at']) + timedelta(minutes=5)).isoformat()
                             for row in scans if row.get('updated_at')},
            'offer_limit': 12, 'record_limit_reached': len(offers) >= 10000}


@app.post('/api/components')
async def save_component(data: dict = Body(...), repo=Depends(repository)):
    errors = component_input_errors(data.get('name'), data.get('kind'), data.get('query'), data.get('capacity_gb'),
                                    data.get('target_text', ''), data.get('target_payment', 'pix'))
    brands = data.get('ignored_brands') or []
    if not isinstance(brands, list) or any(brand not in BRAND_ALIASES for brand in brands):
        errors['ignored_brands'] = 'Escolha as marcas na lista.'
    if errors:
        raise HTTPException(422, errors)
    from core import money
    identifier = data.get('id')
    if identifier is not None and not await repo.get('components', str(identifier)):
        raise HTTPException(404, 'Peça não encontrada.')
    identifier = int(identifier) if identifier is not None else -secrets.randbelow(2**48-1)-1
    part = {key: data.get(key) for key in ('name', 'kind', 'query', 'capacity_gb')}
    part.update(id=identifier, target=money(data['target_text']) if data.get('target_text', '').strip() else None,
                target_payment=data.get('target_payment', 'pix'), ignored_brands=brands, enabled=int(bool(data.get('enabled', True))))
    part['name'], part['query'] = part['name'].strip(), part['query'].strip()
    part['capacity_gb'] = int(part['capacity_gb']) if part['kind'] == 'ssd' else None
    await repo.put('components', str(identifier), part)
    await repo.put('overrides', 'component:' + str(identifier), part)
    return part


@app.delete('/api/components/{identifier}')
async def delete_component(identifier: int, repo=Depends(repository)):
    part = await repo.get('components', identifier)
    if not part:
        raise HTTPException(404, 'Peça não encontrada.')
    await repo.put('overrides', 'component:' + str(identifier), {'deleted': True, 'id': identifier})
    await repo.command('component_delete', {'component_id': identifier, 'label': part['name'][:120]})
    return {'detail': 'Peça removida do painel. O PC receberá a alteração ao conectar.'}


@app.post('/api/preferences/{key}')
async def preference(key: str, data: dict = Body(...), repo=Depends(repository)):
    if data.get('field') not in {'favorite', 'hidden'} or type(data.get('enabled')) is not bool:
        raise HTTPException(422, 'Preferência inválida.')
    value = await repo.preference(key, data['field'], data['enabled'])
    if value is None:
        raise HTTPException(404, 'Oferta não encontrada.')
    return value


@app.get('/api/history/{identifier}')
async def history(identifier: int, payment: str = 'effective', repo=Depends(repository)):
    if payment not in {'pix', 'card', 'announced', 'effective'}:
        raise HTTPException(422, 'Pagamento inválido.')
    part = next((p for p in await components(repo) if p['id'] == identifier), None)
    if not part:
        raise HTTPException(404, 'Peça não encontrada.')
    offers = {o['id']: o for o in await values(repo, 'offers') if o['component_id'] == identifier}
    today = datetime.now(timezone(timedelta(hours=-3))).date()
    result = await repo.history(identifier, (today-timedelta(days=30)).isoformat())
    rows = result['rows']
    daily = {}
    for row in rows:
        offer = offers.get(row.get('offer_id'))
        if not offer or not offer_matches(part, offer) or not confirmed_price(row.get('status') or '') or row.get('availability') == 'out':
            continue
        try:
            stamp = datetime.fromisoformat(row['observed_at'])
            stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
            day = stamp.astimezone(timezone(timedelta(hours=-3))).date()
        except (ValueError, KeyError):
            continue
        if not today-timedelta(days=29) <= day <= today or stamp > datetime.now(timezone.utc):
            continue
        if payment == 'announced' and (row.get('pix') is not None or row.get('card') is not None and offer.get('shop') != 'Mercado Livre'):
            continue
        price = effective_price(dict(offer, **row)) if payment == 'effective' else row.get(payment)
        if price is not None and 0 < price < float('inf'):
            daily[day.isoformat()] = min(price, daily.get(day.isoformat(), price))
    prices = list(daily.values())
    return {'points': [{'date': day, 'price': daily[day]} for day in sorted(daily)],
            'minimum': min(prices) if prices else None, 'median': int(median(prices)) if prices else None,
            'payment': payment, 'truncated': result['truncated']}


@app.get('/api/sources')
async def sources(repo=Depends(repository)):
    setting_rows, status_rows, telegram = await asyncio.gather(repo.records('settings'), values(repo, 'status'), values(repo, 'sources'))
    settings = {row['record_key']: row['data'].get('value') for row in setting_rows}
    worker = next((row for row in status_rows if row.get('name') == 'PC conectado'), None)
    return {'shops': [{'name': name, 'local': name in LOCAL_SHOPS, 'enabled': settings.get('shop:' + name, '1') == '1'}
                      for name in CLOUD_SHOPS + LOCAL_SHOPS], 'telegram': telegram, 'status': status_rows, 'worker': worker}


@app.post('/api/shops')
async def toggle_shop(data: dict = Body(...), repo=Depends(repository)):
    if data.get('name') not in CLOUD_SHOPS + LOCAL_SHOPS or type(data.get('enabled')) is not bool:
        raise HTTPException(422, 'Loja inválida.')
    key = 'shop:' + data['name']
    value = {'value': '1' if data['enabled'] else '0'}
    await repo.put('settings', key, value)
    await repo.put('overrides', key, value)
    return {'detail': 'Fonte atualizada.'}


@app.get('/api/coupons')
async def get_coupons(repo=Depends(repository)):
    post_rows, setting_rows, application_rows, override_rows = await asyncio.gather(
        values(repo, 'coupons'), repo.records('settings'), values(repo, 'coupon_applications'), repo.records('overrides'))
    posts = [p for p in post_rows if coupon_is_today(p.get('found_at') or p.get('published_at'))]
    settings = {row['record_key']: row['data'].get('value', '[]') for row in setting_rows}
    disabled = {row['data']['code']: row['data']['disabled'] for row in override_rows
                if row['record_key'].startswith('coupon-disabled:') and coupon_is_today(row['data'].get('found_at'))}
    feed = json.loads(settings.get('cloud_coupon_feed', '[]'))
    public = [item for item in json.loads(settings.get('public_coupons', '[]')) + [item for item in feed if item.get('source') != 'Pichau'] if coupon_is_today(item.get('found_at') or item.get('checked_at'))]
    pichau = [item for item in json.loads(settings.get('pichau_coupons', '[]')) + [item for item in feed if item.get('source') == 'Pichau'] if coupon_is_today(item.get('found_at') or item.get('checked_at'))]
    public.sort(key=lambda item: item.get('checked_at') or '', reverse=True)
    pichau.sort(key=lambda item: item.get('checked_at') or '', reverse=True)
    coupons = [dict(item, code=code.strip()) for item in coupon_catalog(posts, pichau, public)
               for code in (item['codes'].split(',') if item['codes'] else [''])]
    applications = {row['code']: dict(row, disabled=disabled.get(row['code'], row.get('disabled', False)))
                    for row in application_rows if coupon_is_today(row.get('found_at'))}
    ml, seen_codes = [], set()
    for item in coupons:
        if item.get('shop') != 'Mercado Livre' or item.get('activation') or not re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{2,39}', item.get('code', '').upper()):
            continue
        code = item['code'].upper()
        if code in seen_codes:
            continue
        seen_codes.add(code)
        row = applications.pop(code, {'code': code, 'status': 'new', 'detail': '', 'found_at': item.get('found_at'), 'source': item.get('source'), 'attempts': 0, 'disabled': disabled.get(code, False)})
        if row.get('source') == 'Melhores Cartões':
            row = dict(row, source=item.get('source'))
        ml.append(dict(row, **application_state(row)))
    ml.extend(dict(row, **application_state(row)) for row in applications.values()
              if row.get('source') != 'Melhores Cartões')
    for row in applications.values():
        if row.get('source') == 'Melhores Cartões':
            continue
        coupons.append({'code': row['code'], 'shop': 'Mercado Livre', 'source': row.get('source'),
                        'stamp': row.get('found_at'), 'conditions': '', 'url': ''})
    status = await values(repo, 'status')
    return {'coupons': coupons, 'applications': ml,
            'collection_status': [row for row in status if row.get('coupon_source')],
            'schedule': next((row for row in status if row.get('coupon_schedule')), None)}


@app.post('/api/coupons/refresh')
async def refresh_coupons(repo=Depends(repository)):
    if not await repo.request('POST', 'rpc/monitor_claim_scan', data={'component_key': 'coupons'}):
        raise HTTPException(429, 'Os cupons públicos foram consultados há menos de cinco minutos. Aguarde para atualizar.')
    old = await repo.get('settings', 'cloud_coupon_feed') or {'value': '[]'}
    previous = json.loads(old['value'])
    collectors = Shops()
    try:
        result = await collect_public_coupons(collectors, previous)
        await repo.put_many([{'kind': 'status', 'record_key': 'cloud:coupons:' + row['source'], 'data': row}
                             for row in result['status']] + [{'kind': 'settings', 'record_key': 'cloud_coupon_feed',
                             'data': {'value': json.dumps(result['coupons'], ensure_ascii=False)}}])
        return {'status': result['status']}
    finally:
        await collectors.close()


@app.post('/api/scan/{identifier}')
async def scan(identifier: int, repo=Depends(repository)):
    part = next((p for p in await components(repo) if p['id'] == identifier), None)
    if not part or not part.get('enabled'):
        raise HTTPException(404, 'Peça não encontrada ou pausada.')
    if not await repo.request('POST', 'rpc/monitor_claim_scan', data={'component_key': str(identifier)}):
        raise HTTPException(429, 'Esta peça foi consultada há menos de cinco minutos. Aguarde para atualizar.')
    prefs = {r['record_key']: r['data'] for r in await repo.records('preferences')}
    known = [dict(o, **prefs.get(o['id'], {})) for o in await values(repo, 'offers') if o['component_id'] == identifier]
    settings = {r['record_key']: r['data'].get('value') for r in await repo.records('settings')}
    collectors = Shops()
    statuses = []
    try:
        statuses = await asyncio.gather(*(collect_shop(collectors, repo, part, known, name, 120)
            for name in CLOUD_SHOPS if settings.get('shop:' + name, '1') == '1'))
    finally:
        await collectors.close()
    if any(settings.get('shop:' + name, '1') == '1' for name in LOCAL_SHOPS):
        await repo.command('scan', {'component_id': identifier, 'label': part['name'][:120]})
    count = sum(row['count'] for row in statuses)
    failed = [row['name'] for row in statuses if row['failures']]
    detail = f'{count} leituras online concluídas.'
    if failed:
        detail += ' Falhas em ' + ', '.join(failed) + '; veja Fontes.'
    if any(settings.get('shop:' + name, '1') == '1' for name in LOCAL_SHOPS):
        detail += ' Consultas com Chrome ficaram na fila do PC.'
    return {'status': statuses, 'detail': detail}


def authorize_schedule(request):
    secret = os.environ.get('MONITOR_CRON_SECRET', '')
    if not secret:
        raise HTTPException(503, 'Agendamento ainda não configurado.')
    if not secrets.compare_digest(request.headers.get('authorization', ''), 'Bearer ' + secret):
        raise HTTPException(401, 'Agendamento não autorizado.')


@app.post('/api/scheduled/coupons')
async def scheduled_coupons(request: Request, data: dict = Body(...)):
    authorize_schedule(request)
    previous = data.get('coupons')
    if (not isinstance(previous, list) or len(previous) > 500
            or any(not isinstance(row, dict) or row.get('source') not in {'Pichau', 'Melhores Cartões', 'Pelando'}
                   or not isinstance(row.get('code', ''), str) or len(row.get('code', '')) > 100 for row in previous)):
        raise HTTPException(422, 'Lote de cupons inválido.')
    collectors = Shops()
    try:
        return await collect_public_coupons(collectors, previous)
    finally:
        await collectors.close()


@app.post('/api/scheduled/collect')
async def scheduled_collect(request: Request, data: dict = Body(...)):
    authorize_schedule(request)
    part, known, name = data.get('component'), data.get('offers'), data.get('shop')
    if (not isinstance(part, dict) or type(part.get('id')) is not int or not part.get('enabled')
            or part.get('kind') not in {'custom', 'gpu', 'psu', 'ssd'} or not isinstance(part.get('query'), str)
            or name not in CLOUD_SHOPS or not isinstance(known, list) or len(known) > 500
            or any(not isinstance(row, dict) or not isinstance(row.get('id'), str)
                   or row.get('component_id') != part['id'] or not isinstance(row.get('url'), str)
                   or not valid_url(row['url']) for row in known)):
        raise HTTPException(422, 'Lote de agendamento inválido.')
    repo = ScheduledReadings(known)
    collectors = Shops()
    try:
        status = await collect_shop(collectors, repo, part, known, name, 120)
    finally:
        await collectors.close()
    return {'records': list(repo.written.values()), 'status': status}


@app.get('/api/used')
async def used(repo=Depends(repository)):
    from olx import eligible
    searches, listings = await asyncio.gather(values(repo, 'olx_searches'), values(repo, 'olx_listings'))
    by_id = {row['id']: {'target': None, 'city': '', 'excluded': '', **row} for row in searches}
    return {'searches': searches, 'listings': [dict(row, eligible=eligible(by_id[row['search_id']],
            {'price': None, 'location': '', 'title': '', **row})) for row in listings if row['search_id'] in by_id]}


@app.post('/api/commands')
async def command(data: dict = Body(...), repo=Depends(repository)):
    action, payload = data.get('action'), data.get('payload', {})
    allowed = {'check', 'coupon_batch', 'coupon_retry', 'coupon_disabled', 'source_save', 'source_toggle', 'source_delete',
               'olx_save', 'olx_toggle', 'olx_delete', 'olx_scan', 'session_open', 'session_confirm'}
    if action not in allowed or not isinstance(payload, dict) or len(json.dumps(payload)) > 5000:
        raise HTTPException(422, 'Pedido inválido.')
    if action in {'session_open', 'session_confirm'}:
        if payload.get('shop') not in LOCAL_SHOPS:
            raise HTTPException(422, 'Escolha Mercado Livre ou Shopee para gerenciar a sessão.')
    if action == 'coupon_disabled':
        code = str(payload.get('code', '')).upper()
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{2,39}', code) or type(payload.get('disabled')) is not bool:
            raise HTTPException(422, 'Código ou estado inválido.')
        body = await get_coupons(repo)
        row = next((row for row in body['applications'] if row['code'] == code), None)
        if not row:
            raise HTTPException(404, 'Cupom de hoje não encontrado.')
        saved = {field: row.get(field) for field in
                 ('code', 'status', 'detail', 'found_at', 'source', 'attempts', 'attempted_at')}
        saved['disabled'] = payload['disabled']
        await repo.put('coupon_applications', code, saved)
        await repo.put('overrides', 'coupon-disabled:' + code,
                       {'code': code, 'disabled': saved['disabled'], 'found_at': saved['found_at']})
        return {'detail': 'Cupom desativado.' if saved['disabled'] else 'Cupom reativado.', 'execution': 'cloud'}
    if action == 'check':
        old = await repo.get('offers', payload.get('key', ''))
        if not old:
            raise HTTPException(404, 'Oferta não encontrada.')
        # Confia no domínio validado, não no nome vindo do cadastro/snapshot.
        name = shop_name(old.get('url', ''))
        if name in CLOUD_SHOPS:
            part = next((p for p in await components(repo) if p['id'] == old['component_id']), None)
            if not part:
                raise HTTPException(404, 'Peça não encontrada.')
            collectors = Shops()
            try:
                return await check_offer(collectors, repo, part, old)
            finally:
                await collectors.close()
    payload = {key: value for key, value in payload.items() if key != 'label'}
    if action == 'source_save':
        if set(payload) != {'name', 'reference'}:
            raise HTTPException(422, 'Informe nome e referência do grupo.')
        try:
            payload = source_input(payload['name'], payload['reference'])
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        existing, queued = await asyncio.gather(values(repo, 'sources'), repo.commands())
        references = [row.get('reference', '') for row in existing] + [row.get('payload', {}).get('reference', '')
            for row in queued if row.get('action') == 'source_save' and row.get('status', 'pending') in {'pending','running'}]
        if payload['reference'].casefold() in {value.casefold() for value in references if isinstance(value, str)}:
            raise HTTPException(409, 'Este grupo já está cadastrado ou foi enviado ao PC.')
    if action == 'olx_save':
        from olx import search_input
        allowed_fields = {'name', 'mode', 'url', 'query', 'state', 'city', 'target', 'excluded'}
        if (set(payload)-allowed_fields or not {'name','mode'} <= set(payload)
                or any(not isinstance(value, str) for value in payload.values())):
            raise HTTPException(422, 'Revise os campos da busca OLX.')
        if payload['mode'] == 'fields':
            payload['state'] = payload.get('state', 'SP').upper()
        payload['excluded'] = ','.join(term.strip() for term in re.split(r'[,\n]+', payload.get('excluded', '')) if term.strip())
        try:
            search_input(**payload)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
    if action == 'check':
        payload['label'] = old.get('title', '')[:120]
    if action in {'source_toggle', 'source_delete', 'olx_toggle', 'olx_delete', 'olx_scan'}:
        kind = 'sources' if action.startswith('source_') else 'olx_searches'
        saved = await repo.get(kind, payload.get('id', ''))
        if not saved:
            raise HTTPException(404, 'Fonte não encontrada.' if kind == 'sources' else 'Busca não encontrada.')
        payload['label'] = str(saved.get('name', ''))[:120]
    return await repo.command(action, payload)


@app.post('/api/commands/{identifier}/cancel')
async def cancel_command(identifier: uuid.UUID, repo=Depends(repository)):
    rows = await repo.request('PATCH', 'monitor_commands', params={
        'owner_id': 'eq.' + repo.owner, 'id': 'eq.' + str(identifier), 'status': 'eq.pending',
        'action': 'neq.component_delete'}, data={'status': 'failed', 'detail': 'Cancelado pelo usuário.', 'updated_at': utcnow()},
        prefer='return=representation')
    if not rows:
        raise HTTPException(409, 'O pedido já foi recebido pelo PC ou não está mais na fila.')
    return {'detail': 'Pedido cancelado. Ele não será executado pelo PC.'}


@app.post('/api/worker/pull')
async def pull(repo=Depends(repository)):
    overrides, preferences, offers, coupons = await asyncio.gather(
        repo.records('overrides'), repo.records('preferences'), repo.records('offers'), repo.get('settings', 'cloud_coupon_feed'))
    return {'overrides': overrides, 'preferences': preferences, 'offers': offers,
            'coupon_feed': json.loads(coupons['value']) if coupons else []}


@app.post('/api/worker/claim')
async def claim(repo=Depends(repository)):
    # O coletor pede o próximo lote depois de terminar o anterior. Não reenviar ações antigas.
    cutoff = (datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    await repo.request('PATCH', 'monitor_commands', params={
        'owner_id': 'eq.' + repo.owner, 'status': 'eq.running', 'updated_at': 'lt.' + cutoff},
        data={'status': 'failed', 'detail': 'Sem confirmação há mais de uma hora. Confira o resultado antes de enviar novamente.', 'updated_at': utcnow()})
    return {'commands': await repo.request('POST', 'rpc/monitor_claim_commands', data={})}


@app.post('/api/worker/reconcile')
async def reconcile(data: dict = Body(...), repo=Depends(repository)):
    for kind in ('sources', 'olx_searches'):
        keys = data.get(kind)
        if not isinstance(keys, list) or len(keys) > 10000 or any(not isinstance(key, str) or not key.isdigit() for key in keys):
            raise HTTPException(422, 'Lista de registros inválida.')
    for kind in ('sources', 'olx_searches'):
        keep = set(data[kind])
        for row in await repo.records(kind):
            if row['record_key'] not in keep:
                await repo.delete(kind, row['record_key'])
    for kind in ('coupons', 'coupon_applications'):
        for row in await repo.records(kind):
            item = row['data']
            if not coupon_is_today(item.get('found_at') or item.get('published_at')):
                await repo.delete(kind, row['record_key'])
    return {'ok': True}


@app.post('/api/worker/ack/{identifier}')
async def ack(identifier: uuid.UUID, data: dict = Body(...), repo=Depends(repository)):
    if data.get('status') not in {'done', 'failed'}:
        raise HTTPException(422, 'Estado inválido.')
    await repo.request('PATCH', 'monitor_commands', params={'id': 'eq.' + str(identifier), 'owner_id': 'eq.' + repo.owner},
                       data={'status': data['status'], 'detail': str(data.get('detail', ''))[:500], 'updated_at': utcnow()})
    return {'ok': True}


@app.post('/api/worker/push')
async def push(data: dict = Body(...), repo=Depends(repository)):
    rows = data.get('rows')
    if not isinstance(rows, list) or len(rows) > 100 or len(json.dumps(data)) > 900000:
        raise HTTPException(422, 'Lote inválido. Envie até 100 registros.')
    safe = []
    for row in rows:
        if not isinstance(row, dict):
            raise HTTPException(422, 'Registro inválido.')
        kind, key, value = row.get('kind'), str(row.get('record_key', '')), row.get('data')
        if kind not in SYNC_KINDS or not 1 <= len(key) <= 200 or not isinstance(value, dict):
            raise HTTPException(422, 'Registro inválido.')
        if kind == 'settings' and key not in PUBLIC_SETTINGS:
            raise HTTPException(422, 'Configuração privada não pode ser enviada.')
        if kind == 'offers':
            if not valid_url(value.get('url', '')):
                raise HTTPException(422, 'Link inválido.')
            previous = await repo.get('offers', key)
            if previous and (previous.get('checked_at') or '') > (value.get('checked_at') or ''):
                continue
        safe.append({'kind': kind, 'record_key': key, 'data': value})
    await repo.put_many(safe)
    return {'accepted': len(safe)}


app.mount('/assets', StaticFiles(directory=ASSETS), name='assets')
