"""Uma consulta HTTP de peça/loja, compartilhada por botão e agendamento."""
import asyncio

import httpx

from core import canonical_url, coupon_is_today, detect_brand, effective_price, reading_valid_until, top_offers, tracking_price, utcnow
from cloud_protocol import offer_key


def failure_reason(error):
    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return 'A loja excedeu o tempo da consulta.'
    if isinstance(error, httpx.HTTPStatusError):
        return 'A loja retornou HTTP ' + str(error.response.status_code) + '.'
    if isinstance(error, httpx.HTTPError):
        return 'Não foi possível estabelecer a conexão com a loja.'
    # ValueErrors são mensagens do coletor; não devolver URLs, HTML ou rastros de transporte.
    text = str(error)
    return text[:250] if 'http' not in text.lower() else 'A página não permitiu uma leitura confirmada.'


async def check_offer(collectors, repo, part, old, timeout=60):
    """Confere uma oferta HTTP sem enfileirar trabalho no PC."""
    try:
        async with asyncio.timeout(timeout):
            reading = await collectors.check(old['url'], part)
        row = {**old, **reading, 'id': old['id'], 'component_id': part['id'],
               'brand': reading.get('brand') or detect_brand(reading['title']),
               'coupon_price': reading.get('coupon_price'), 'valid_until': reading_valid_until(reading)}
        stamp = row.get('checked_at') or utcnow()
        observation = {field: row.get(field) for field in
                       ('pix', 'card', 'announced', 'coupon_price', 'status', 'availability')}
        observation.update(offer_id=old['id'], observed_at=stamp)
        await repo.put_many([{'kind': 'offers', 'record_key': old['id'], 'data': row},
                            {'kind': 'observations', 'record_key': old['id'] + ':' + stamp, 'data': observation}])
        return {'detail': 'Oferta conferida online.', 'checked': True, 'execution': 'cloud'}
    except (httpx.HTTPError, ValueError, TimeoutError):
        await repo.put('offers', old['id'], dict(old, valid_until=None,
                       status='Falha na revalidação · anúncio preservado'))
        return {'detail': 'A loja bloqueou ou não concluiu a leitura. Último preço preservado, sem confirmação.',
                'checked': False, 'execution': 'cloud'}


async def collect_shop(collectors, repo, part, known, name, timeout=120):
    count, failures, reasons = 0, 0, []
    try:
        async with asyncio.timeout(timeout):
            candidates = await collectors.discover(name, part)
            for url in candidates[:12]:
                old = next((o for o in known if canonical_url(o['url']) == canonical_url(url)), None)
                cut = top_offers([part], known, tracking_price).get(part['id'], [])
                if old and (old.get('hidden') or len(cut) == 12 and tracking_price(old) > tracking_price(cut[-1])):
                    continue
                try:
                    reading = await collectors.check(url, part)
                    key = offer_key(part['id'], reading['url'])
                    row = dict(reading, id=key, component_id=part['id'],
                               brand=reading.get('brand') or detect_brand(reading['title']),
                               valid_until=reading_valid_until(reading))
                    prior = await repo.get('offers', key)
                    row['published_at'] = (prior or row).get('published_at', row.get('published_at'))
                    row['origins'] = (prior or {}).get('origins') or name
                    new_cut = top_offers([part], known, tracking_price).get(part['id'], [])
                    if not old and len(new_cut) == 12 and effective_price(row) > tracking_price(new_cut[-1]):
                        continue
                    stamp = row.get('checked_at') or utcnow()
                    observation = {field: row.get(field) for field in ('pix', 'card', 'announced', 'coupon_price', 'status', 'availability')}
                    observation.update(offer_id=key, observed_at=stamp)
                    await repo.put_many([{'kind': 'offers', 'record_key': key, 'data': row},
                        {'kind': 'observations', 'record_key': key + ':' + stamp, 'data': observation}])
                    known[:] = [o for o in known if o['id'] != key] + [row]
                    count += 1
                except (httpx.HTTPError, ValueError) as exc:
                    failures += 1
                    reasons.append(failure_reason(exc))
                    if old:
                        await repo.put('offers', old['id'], dict(old, valid_until=None, status='Falha na revalidação · anúncio preservado'))
    except (ValueError, httpx.HTTPError, TimeoutError) as exc:
        failures += 1
        reasons.append(failure_reason(exc))
    detail = f'{count} ofertas consultadas' + (' · algumas leituras falharam' if failures else '')
    if not count and failures:
        detail = 'Consulta bloqueada, indisponível ou sem anúncios legíveis; histórico preservado.'
    status = {'name': name, 'component_id': part['id'], 'count': count, 'failures': failures, 'detail': detail, 'reason': next(iter(reasons), ''), 'checked_at': utcnow()}
    await repo.put('status', 'cloud:' + name + ':' + str(part['id']), status)
    return status


PUBLIC_COUPON_SOURCES = ('Pichau', 'Melhores Cartões', 'Pelando')


async def collect_public_coupons(collectors, previous, timeout=30):
    """Cada fonte falha isoladamente; preservar só os códigos encontrados hoje."""
    async def collect(name):
        cached = [item for item in previous if item.get('source') == name]
        try:
            async with asyncio.timeout(timeout):
                items = await collectors.coupon_list() if name == 'Pichau' else await collectors.public_coupon_source(name)
            for item in items:
                prior = next((row for row in cached if row.get('code') == item.get('code') and row.get('url') == item.get('url')), {})
                item.update(source=name, shop=item.get('shop') or name,
                            found_at=item.get('found_at') or prior.get('found_at') or utcnow(), checked_at=utcnow())
            status = {'source': name, 'count': len(items), 'failures': 0, 'detail': f'{len(items)} cupons consultados.'}
        except (httpx.HTTPError, ValueError, TimeoutError) as error:
            items = cached
            status = {'source': name, 'count': 0, 'failures': 1,
                      'detail': failure_reason(error) + ' Última leitura preservada.'}
        status.update(coupon_source=True, checked_at=utcnow())
        return items, status
    results = await asyncio.gather(*(collect(name) for name in PUBLIC_COUPON_SOURCES))
    return {'coupons': [item for rows, _ in results for item in rows if coupon_is_today(item.get('found_at'))],
            'status': [status for _, status in results]}


class ScheduledReadings:
    """Coleta devolve os registros ao Supabase; a Vercel não assume o dono da conta."""
    def __init__(self, known):
        self.known = {row['id']: row for row in known}
        self.written = {}

    async def get(self, kind, key):
        return self.known.get(key) if kind == 'offers' else None

    async def put(self, kind, key, data):
        await self.put_many([{'kind': kind, 'record_key': key, 'data': data}])

    async def put_many(self, rows):
        for row in rows:
            self.written[row['kind'], row['record_key']] = row
            if row['kind'] == 'offers':
                self.known[row['record_key']] = row['data']
