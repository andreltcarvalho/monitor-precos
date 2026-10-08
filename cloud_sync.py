"""Ponte opcional com a nuvem; Chrome e credenciais de lojas não saem do PC."""
import asyncio
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from cloud_protocol import CLOUD_SHOPS, LOCAL_SHOPS, PUBLIC_SETTINGS, offer_key
from core import canonical_url, coupon_is_today, price_is_current, utcnow
from credentials import crypt, protect_data_dir

FIELDS = {
    'components': 'id name kind query capacity_gb target target_payment enabled ignored_brands',
    'offers': 'id component_id url title shop seller pix card announced installments installment coupons status message published_at received_at checked_at availability coupon_price brand shipping_origin valid_until favorite hidden origins telegram_origin',
    'observations': 'id offer_id observed_at pix card announced status availability coupon_price',
    'sources': 'id name reference enabled baseline last_message',
    'coupon_posts': 'source message_id text codes published_at links message_url found_at',
    'ml_coupon_applications': 'code status detail attempted_at attempts source disabled found_at',
    'olx_searches': 'id name url query state city target excluded enabled baseline resolved_url checked_at status',
    'olx_listings': 'id search_id ad_id url title price location published_text first_seen checked_at reference_price pending',
    'olx_observations': 'id listing_id price observed_at',
}


def credentials_path(data_dir):
    return Path(data_dir) / 'cloud-credentials.bin'


def save_cloud_credentials(data_dir, value):
    protect_data_dir(Path(data_dir))
    credentials_path(data_dir).write_bytes(crypt(json.dumps(value).encode()))


def load_cloud_credentials(data_dir):
    path = credentials_path(data_dir)
    return json.loads(crypt(path.read_bytes(), decrypt=True)) if path.exists() else None


def public_snapshot(store):
    """Campos explícitos: configurações privadas nunca entram na exportação."""
    rows = []
    offers = store.offers()
    keys = {offer['id']: offer_key(offer['component_id'], offer['url']) for offer in offers}
    existing = {row['name'] for row in store.rows("SELECT name FROM sqlite_master WHERE type='table'")}
    for table, fields in FIELDS.items():
        if table not in existing:
            continue
        raw_rows = offers if table == 'offers' else store.rows('SELECT ' + ','.join(fields.split()) + ' FROM ' + table)
        for raw in raw_rows:
            value = {field: raw.get(field) for field in fields.split()}
            kind = {'coupon_posts': 'coupons', 'ml_coupon_applications': 'coupon_applications'}.get(table, table)
            key = str(value.get('id', value.get('code', '')))
            if table == 'offers':
                value['local_id'], value['id'] = value['id'], keys[value['id']]
                key = value['id']
            elif table == 'observations':
                if value['offer_id'] not in keys:
                    continue
                value['offer_id'] = keys[value['offer_id']]
                key = 'local:' + key
            elif table == 'coupon_posts':
                key = hashlib.sha256((value['source'] + ':' + str(value['message_id'])).encode()).hexdigest()
            rows.append({'kind': kind, 'record_key': key, 'data': value})
    for key in PUBLIC_SETTINGS:
        value = store.get_setting(key)
        if value is not None:
            rows.append({'kind': 'settings', 'record_key': key, 'data': {'value': value}})
    return rows


class CloudSync:
    def __init__(self, monitor, data_dir):
        self.monitor, self.data_dir = monitor, Path(data_dir)
        self.status = 'Nuvem não conectada · execute Conectar-Nuvem.cmd'
        self.hashes = {}
        self.lock = asyncio.Lock()

    async def request(self, client, credentials, method, path, data=None):
        url = credentials['url'].rstrip('/')
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in {None, 443}:
            raise ValueError('O endereço do painel precisa usar HTTPS.')
        response = await client.request(method, url + path, json=data,
            headers={'Authorization': 'Bearer ' + credentials['access_token']})
        if response.status_code == 401:
            refresh = await client.post(url + '/api/auth/refresh',
                headers={'Authorization': 'Bearer ' + credentials['access_token']},
                cookies={'monitor_refresh': credentials['refresh_token']})
            refresh.raise_for_status()
            credentials['access_token'] = refresh.cookies.get('monitor_access')
            credentials['refresh_token'] = refresh.cookies.get('monitor_refresh')
            if not all(credentials.values()):
                raise ValueError('Sessão da nuvem expirada; execute Conectar-Nuvem.cmd.')
            save_cloud_credentials(self.data_dir, credentials)
            response = await client.request(method, url + path, json=data,
                headers={'Authorization': 'Bearer ' + credentials['access_token']})
        response.raise_for_status()
        return response.json()

    def apply_overrides(self, rows, preferences):
        store = self.monitor.store
        for row in rows:
            key, value = row['record_key'], row['data']
            if key.startswith('component:'):
                identifier = int(value['id'])
                old = next((p for p in store.components() if p['id'] == identifier), None)
                if value.get('deleted'):
                    if old:
                        store.delete('components', identifier)
                    continue
                if not old:
                    store.db.execute('INSERT INTO components(id,name,kind,query) VALUES(?,?,?,?)',
                                     (identifier, value['name'], value['kind'], value['query']))
                    store.db.commit()
                store.save_component(value['name'], value['kind'], value['query'], value.get('capacity_gb'),
                    value.get('target'), value.get('target_payment', 'pix'), identifier, value.get('ignored_brands', []))
                store.toggle('components', identifier, bool(value.get('enabled', 1)))
            elif key.startswith('coupon-disabled:') and coupon_is_today(value.get('found_at')):
                self.monitor.ml_coupons.set_disabled(value['code'], bool(value['disabled']))
            elif key in PUBLIC_SETTINGS and key.startswith('shop:'):
                store.set_setting(key, value['value'])
        mapped = {offer_key(o['component_id'], o['url']): o['id'] for o in store.offers()}
        for row in preferences:
            identifier = mapped.get(row['record_key'])
            if identifier:
                for field in ('favorite', 'hidden'):
                    if field in row['data']:
                        store.set_offer_preference([identifier], field, bool(row['data'][field]))

    async def import_offers(self, rows):
        store = self.monitor.store
        parts = {part['id'] for part in store.components()}
        for record in rows:
            value = record['data']
            if value.get('shop') not in CLOUD_SHOPS or value['component_id'] not in parts:
                continue
            old = store.rows('SELECT * FROM offers WHERE component_id=? AND url=?',
                             (value['component_id'], canonical_url(value['url'])))
            if old and (old[0].get('checked_at') or '') >= (value.get('checked_at') or ''):
                continue
            incoming = dict(value)
            if isinstance(incoming.get('coupons'), str):
                incoming['coupons'] = json.loads(incoming['coupons'])
            reading, changed = store.upsert_offer(value['component_id'], incoming,
                {'source': value['shop'] + ' · nuvem', 'published_at': value.get('published_at') or utcnow()})
            if changed and price_is_current(reading):
                await self.monitor.alert(reading, fresh=True)

    async def execute(self, command):
        monitor, store = self.monitor, self.monitor.store
        action, value = command['action'], command['payload']
        if action == 'scan':
            if monitor.shop_lock.locked():
                raise ValueError('Outra consulta está em andamento no PC. Tente novamente após ela terminar.')
            await monitor.scan_shops(force_ml=True, component_id=int(value['component_id']), shops=LOCAL_SHOPS)
        elif action == 'check':
            row = next((o for o in store.offers() if offer_key(o['component_id'], o['url']) == value['key']), None)
            if not row:
                raise ValueError('Oferta não encontrada no PC; aguarde a sincronização.')
            await monitor.check_offer(row['id'])
        elif action in {'session_open', 'session_confirm'}:
            shop = value.get('shop')
            if shop not in LOCAL_SHOPS:
                raise ValueError('Loja sem sessão local gerenciável.')
            if monitor.shop_lock.locked():
                raise ValueError('Outra consulta está em andamento. Aguarde antes de alterar a sessão.')
            browser = monitor.shops.ml_browser if shop == 'Mercado Livre' else monitor.shops.shopee_browser
            if action == 'session_open':
                await browser.open_login()
                return 'Chrome aberto no PC. Entre na conta, feche essa janela e confirme a sessão em Fontes.'
            component = next((part for part in store.components() if part['enabled']), None)
            if not component:
                raise ValueError('Ative uma peça para testar a sessão.')
            await browser.confirm(component)
            monitor.shop_status[shop] = 'Sessão salva · aguardando consulta'
            return 'Sessão confirmada para ' + shop + '. Atualize uma peça para consultar as ofertas.'
        elif action in {'coupon_batch', 'coupon_retry'}:
            await monitor.ml_coupons.run(retry_only=action == 'coupon_retry', code=value.get('code'))
        elif action == 'coupon_disabled':
            monitor.ml_coupons.set_disabled(value['code'], bool(value['disabled']))
        elif action == 'component_delete':
            store.delete('components', int(value['component_id']))
        elif action == 'source_save':
            store.save_source(value['name'], value['reference'])
        elif action in {'source_toggle', 'source_delete'}:
            if action == 'source_toggle':
                store.toggle('sources', int(value['id']), bool(value['enabled']))
            else:
                store.delete('sources', int(value['id']))
        elif action == 'olx_save':
            monitor.olx.save_search(**value)
        elif action in {'olx_toggle', 'olx_delete'}:
            identifier = int(value['id'])
            if action == 'olx_toggle':
                store.db.execute('UPDATE olx_searches SET enabled=? WHERE id=?', (int(bool(value['enabled'])), identifier))
            else:
                store.db.execute('DELETE FROM olx_searches WHERE id=?', (identifier,))
            store.db.commit()
        elif action == 'olx_scan':
            await monitor.olx.scan(int(value['id']))
        else:
            raise ValueError('Comando não reconhecido pelo PC.')

    async def cycle(self):
        async with self.lock:
            credentials = load_cloud_credentials(self.data_dir)
            if not credentials:
                return
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                # Primeiro publicar os dados existentes; a primeira conexão não importa histórico para alertas.
                await self.push(client, credentials)
                result = await self.request(client, credentials, 'POST', '/api/worker/pull', {})
                self.apply_overrides(result['overrides'], result['preferences'])
                await self.import_offers(result['offers'])
                result = await self.request(client, credentials, 'POST', '/api/worker/claim', {})
                for command in result['commands']:
                    try:
                        detail = await self.execute(command)
                        answer = {'status': 'done', 'detail': detail or 'Pedido processado no PC. Confira os resultados na aba correspondente.'}
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        answer = {'status': 'failed', 'detail': str(exc)[:500] if isinstance(exc, ValueError) else 'Falha no coletor local; confira o painel no PC.'}
                    await self.request(client, credentials, 'POST', '/api/worker/ack/' + command['id'], answer)
                await self.push(client, credentials)
                self.status = 'Nuvem conectada · última sincronização ' + utcnow()

    async def push(self, client, credentials):
        rows = public_snapshot(self.monitor.store)
        rows.append({'kind': 'status', 'record_key': 'worker', 'data': {
            'name': 'PC conectado', 'checked_at': utcnow(), 'telegram': self.monitor.telegram_status,
            'coupons': self.monitor.ml_coupons.status, 'shops': self.monitor.shop_status,
            'olx': self.monitor.olx.status, 'sessions': {name: {'configured': browser.configured,
                'login_open': browser.login_open, 'detail': browser.status}
                for name, browser in [('Mercado Livre', self.monitor.shops.ml_browser), ('Shopee', self.monitor.shops.shopee_browser)]}}})
        changed = []
        for row in rows:
            identity = (row['kind'], row['record_key'])
            digest = hashlib.sha256(json.dumps(row['data'], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if self.hashes.get(identity) != digest:
                changed.append((row, identity, digest))
        for offset in range(0, len(changed), 100):
            batch = changed[offset:offset+100]
            await self.request(client, credentials, 'POST', '/api/worker/push', {'rows': [item[0] for item in batch]})
            for _, identity, digest in batch:
                self.hashes[identity] = digest
        await self.request(client, credentials, 'POST', '/api/worker/reconcile', {
            kind: [row['record_key'] for row in rows if row['kind'] == kind]
            for kind in ('sources', 'olx_searches')})

    async def loop(self):
        while self.monitor.running:
            try:
                await self.cycle()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.status = 'Sincronização indisponível · dados locais preservados; confira a conexão ou execute Conectar-Nuvem.cmd.'
            await asyncio.sleep(60)
