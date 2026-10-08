import asyncio
import json
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

from cloud.app import app, repository
from cloud.repository import Repository, user_session
from cloud_protocol import catalog, offer_key, LOCAL_SHOPS
from cloud_sync import CloudSync, public_snapshot
from core import Store, utcnow


class FakeRepository:
    owner = 'owner-a'

    def __init__(self):
        self.data = {}
        self.written = []
        self.queued = []

    async def records(self, kind):
        return [{'record_key': key, 'data': value} for (group, key), value in self.data.items() if group == kind]

    async def get(self, kind, key):
        return self.data.get((kind, str(key)))

    async def put(self, kind, key, data):
        self.data[kind, str(key)] = data

    async def put_many(self, rows):
        self.written.extend(rows)
        for row in rows:
            await self.put(row['kind'], row['record_key'], row['data'])

    async def delete(self, kind, key):
        self.data.pop((kind, str(key)), None)

    async def preference(self, key, field, enabled):
        if not await self.get('offers', key):
            return None
        value = dict(self.data.get(('preferences', key), {}), **{field: enabled})
        await self.put('preferences', key, value)
        return value

    async def history(self, component, since_day):
        keys = {key for (kind, key), value in self.data.items() if kind == 'offers' and value['component_id'] == component}
        rows = [value for (kind, _), value in self.data.items() if kind == 'observations'
                and value.get('offer_id') in keys and (value.get('observed_at') or '')[:10] >= since_day]
        return {'rows': rows, 'truncated': False}

    async def commands(self):
        return self.queued

    async def command(self, action, payload):
        row = {'action': action, 'payload': payload}
        self.queued.append(row)
        return row


def part(**fields):
    return dict(id=1, name='Placa', kind='custom', query='rtx 5060', enabled=1,
                target=None, target_payment='pix', ignored_brands=[], **fields)


def offer(identifier, price, **fields):
    value = dict(id=str(identifier), component_id=1, title=f'RTX 5060 modelo {identifier}', shop='Pichau',
                 seller='Pichau', url=f'https://www.pichau.com.br/placa-{identifier}', pix=price,
                 card=None, announced=None, status='Preço lido na loja', availability='in', shipping_origin='local',
                 checked_at=utcnow(), valid_until=(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat())
    return dict(value, **fields)


class CatalogTests(unittest.TestCase):
    def test_twelve_cheapest_and_session_coupon_sorting(self):
        rows = [offer(i, 200000+i*1000) for i in range(15)]
        rows.append(offer('coupon', None, shop='Mercado Livre', announced=250000, coupon_price=190000))
        selected = catalog([part()], rows)[0]['offers']
        self.assertEqual(len(selected), 12)
        self.assertEqual(selected[0]['id'], 'coupon')
        self.assertEqual([o['effective'] for o in selected], sorted(o['effective'] for o in selected))

    def test_limit_does_not_treat_unknown_pix_as_coupon_pix(self):
        component = dict(part(), target=210000)
        rows = [offer('below', 200000), offer('above', 220000),
                offer('unknown', None, announced=200000, coupon_price=180000)]
        self.assertEqual([o['id'] for o in catalog([component], rows)[0]['offers']], ['below'])

    def test_stale_hidden_and_unavailable_are_excluded(self):
        rows = [offer('valid', 200000), offer('expired', 100000, valid_until=utcnow()),
                offer('out', 100000, availability='out'), offer('hidden', 100000)]
        self.assertEqual([o['id'] for o in catalog([part()], rows, {'hidden': {'hidden': True}})[0]['offers']], ['valid'])

    def test_canonical_identity_is_stable(self):
        self.assertEqual(offer_key(1, 'https://www.pichau.com.br/placa?utm_source=x'),
                         offer_key(1, 'https://www.pichau.com.br/placa'))
        self.assertNotEqual(offer_key(1, 'https://www.pichau.com.br/placa'), offer_key(2, 'https://www.pichau.com.br/placa'))


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.repo = FakeRepository()
        app.dependency_overrides[repository] = lambda: self.repo
        self.client = TestClient(app)
        self.repo.data['components', '1'] = part()

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()

    def test_queued_context_uses_owned_saved_name_instead_of_client_label(self):
        self.repo.data['sources','7']={'id':7,'name':'Grupo real'}
        result=self.client.post('/api/commands',json={'action':'source_toggle','payload':{'id':7,'enabled':False,'label':'Rótulo falso'}})
        self.assertEqual(result.status_code,200)
        self.assertEqual(self.repo.queued[-1]['payload']['label'],'Grupo real')
        self.assertEqual(self.repo.queued[-1]['payload']['id'],7)
        self.repo.data['olx_searches','3']={'id':3,'name':'Placa em Piracicaba'}
        self.client.post('/api/commands',json={'action':'olx_scan','payload':{'id':3}})
        self.assertEqual(self.repo.queued[-1]['payload']['label'],'Placa em Piracicaba')

    def test_olx_save_payload_remains_accepted_by_local_parser(self):
        from olx import search_input
        draft={'name':'Placa local','mode':'fields','url':'','query':'rtx 5060','state':'SP','city':'Piracicaba','target':'2800','excluded':'quebrada','label':'campo extra'}
        result=self.client.post('/api/commands',json={'action':'olx_save','payload':draft})
        self.assertEqual(result.status_code,200)
        payload=self.repo.queued[-1]['payload']
        self.assertNotIn('label',payload)
        self.assertEqual(search_input(**payload)['name'],'Placa local')

    def test_component_delete_preserves_name_for_activity_after_removal(self):
        self.assertEqual(self.client.delete('/api/components/1').status_code,200)
        self.assertEqual(self.repo.queued[-1]['payload']['label'],part()['name'])

    def test_preference_keeps_other_fields_and_refuses_unknown_offer(self):
        self.repo.data['offers','one']=offer('one',200000)
        self.repo.data['preferences','one']={'favorite':True}
        result=self.client.post('/api/preferences/one',json={'field':'hidden','enabled':True})
        self.assertEqual(result.json(),{'favorite':True,'hidden':True})
        self.assertEqual(self.client.post('/api/preferences/missing',json={'field':'hidden','enabled':True}).status_code,404)
        for value in ({'field':'arbitrary','enabled':True},{'field':'hidden','enabled':'false'}):
            self.assertEqual(self.client.post('/api/preferences/one',json=value).status_code,422)

    def test_private_configuration_rejected_in_export(self):
        response = self.client.post('/api/worker/push', json={'rows': [
            {'kind': 'settings', 'record_key': 'telegram_api_hash', 'data': {'value': 'private'}}]})
        self.assertEqual(response.status_code, 422)
        self.assertFalse(self.repo.written)

    def test_bad_origin_and_cookie_without_origin_rejected(self):
        self.assertEqual(self.client.post('/api/commands', json={}, headers={'Origin': 'https://foreign.example'}).status_code, 403)
        self.client.cookies.set('monitor_access', 'test-session')
        self.assertEqual(self.client.post('/api/commands', json={}).status_code, 403)

    def test_bearer_worker_and_same_origin_browser_allowed(self):
        self.client.cookies.set('monitor_access', 'test-session')
        for headers in ({'Authorization': 'Bearer test-session'}, {'Origin': 'http://testserver'}):
            result = self.client.post('/api/worker/push', json={'rows': []}, headers=headers)
            self.assertEqual(result.status_code, 200)

    def test_large_body_without_content_length_rejected(self):
        request = self.client.build_request('POST', '/api/worker/push', content=b'x'*1_000_001)
        del request.headers['content-length']
        self.assertEqual(self.client.send(request).status_code, 413)

    def test_malformed_record_has_validation_error(self):
        self.assertEqual(self.client.post('/api/worker/push', json={'rows': [None]}).status_code, 422)

    def test_older_local_reading_cannot_overwrite_newer_cloud_price(self):
        self.repo.data['offers', 'key'] = offer('key', 180000, checked_at='2026-10-07T20:00:00+00:00')
        response = self.client.post('/api/worker/push', json={'rows': [
            {'kind': 'offers', 'record_key': 'key', 'data': offer('key', 200000, checked_at='2026-10-07T19:00:00+00:00')}]})
        self.assertEqual(response.json()['accepted'], 0)
        self.assertEqual(self.repo.data['offers', 'key']['pix'], 180000)

    def test_component_save_and_delete_are_authoritative(self):
        response = self.client.post('/api/components', json=dict(part(), id=None, target_text='2.100,00'))
        self.assertEqual(response.status_code, 200, response.text)
        identifier = response.json()['id']
        self.assertLess(identifier, 0)
        self.assertEqual(self.repo.data['overrides', 'component:'+str(identifier)]['target'], 210000)
        self.assertEqual(self.client.delete('/api/components/'+str(identifier)).status_code, 200)
        self.assertTrue(self.repo.data['overrides', 'component:'+str(identifier)]['deleted'])

    def test_missing_offer_cannot_queue_check(self):
        self.assertEqual(self.client.post('/api/commands', json={'action': 'check', 'payload': {'key': 'missing'}}).status_code, 404)
        self.assertFalse(self.repo.queued)

    def test_coupon_codes_are_split_and_missing_feed_application_retained(self):
        self.repo.data['coupons', 'post'] = dict(source='grupo', message_id=1, text='Mercado Livre cupons',
            codes='["PRIMEIRO", "SEGUNDO"]', links='[]', published_at=utcnow(), found_at=utcnow())
        self.repo.data['coupon_applications', 'TERCEIRO'] = dict(code='TERCEIRO', status='inserted', found_at=utcnow())
        result = self.client.get('/api/coupons').json()
        self.assertEqual({r['code'] for r in result['coupons']}, {'PRIMEIRO', 'SEGUNDO', 'TERCEIRO'})
        self.assertEqual({r['code'] for r in result['applications']}, {'PRIMEIRO', 'SEGUNDO', 'TERCEIRO'})
        self.assertEqual(next(r['group'] for r in result['applications'] if r['code'] == 'TERCEIRO'), 'active')

    def test_reconciliation_removes_deleted_sources_and_previous_day_coupons(self):
        self.repo.data['sources', '1'] = {'id': 1}
        self.repo.data['sources', '2'] = {'id': 2}
        self.repo.data['coupons', 'old'] = {'found_at': (datetime.now(timezone.utc)-timedelta(days=2)).isoformat()}
        self.repo.data['coupons', 'today'] = {'found_at': utcnow()}
        result = self.client.post('/api/worker/reconcile', json={'sources': ['2'], 'olx_searches': []})
        self.assertEqual(result.status_code, 200)
        self.assertNotIn(('sources', '1'), self.repo.data)
        self.assertNotIn(('coupons', 'old'), self.repo.data)
        self.assertIn(('coupons', 'today'), self.repo.data)

    def test_history_excludes_unconfirmed_out_and_wrong_payment(self):
        self.repo.data['offers', 'one'] = offer('one', 200000)
        for key, change in [('good', {}), ('out', {'availability': 'out'}), ('unverified', {'status': 'Anunciado no Telegram'})]:
            self.repo.data['observations', key] = dict(offer_id='one', observed_at=utcnow(), pix=200000,
                card=220000, announced=180000, status='Preço lido na loja', availability='in', **{}) | change
        self.assertEqual(self.client.get('/api/history/1?payment=pix').json()['minimum'], 200000)
        self.assertEqual(self.client.get('/api/history/1?payment=announced').json()['points'], [])

    def test_static_panel_and_health(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/assets/app.js').status_code, 200)
        self.assertEqual(self.client.get('/health').json()['mode'], 'cloud')

    def test_catalog_has_compact_model_without_losing_original_or_payment(self):
        title = 'Placa de Video Gigabyte GeForce RTX 5060 Windforce OC White, 8GB, GDDR7, SKU-123'
        self.repo.data['offers', 'gpu'] = offer('gpu', None, title=title, shop='Mercado Livre',
            announced=250000, coupon_price=230000, seller='Outra loja')
        result = self.client.get('/api/catalog').json()
        for row in (result['offers'][0], result['groups'][0]['offers'][0]):
            self.assertEqual(row['title'], title)
            self.assertEqual(row['display']['title'], 'Gigabyte RTX 5060 Windforce OC White')
            self.assertEqual(row['display']['specs'], '8GB · GDDR7')
            self.assertEqual(row['display']['seller'], 'Vendido por Outra loja')
            self.assertEqual(row['display']['payment'], 'pagamento não informado')
            self.assertTrue(row['display']['coupon_primary'])
            self.assertIsNone(row['pix'])

    def test_scan_uses_active_http_sources_preserves_failures_and_queues_local(self):
        self.repo.request = AsyncMock(return_value=True)
        for shop in ('KaBuM', 'Amazon', 'Terabyte Shop'):
            self.repo.data['settings', 'shop:'+shop] = {'value': '0'}
        old = offer('old', 200000)
        old['id'] = offer_key(1, old['url'])
        self.repo.data['offers', old['id']] = old
        collectors = SimpleNamespace(discover=AsyncMock(return_value=[old['url']]),
            check=AsyncMock(side_effect=ValueError('blocked')), close=AsyncMock())
        with patch('cloud.app.Shops', return_value=collectors):
            response = self.client.post('/api/scan/1', json={})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['status'][0]['failures'], 1)
        collectors.discover.assert_awaited_once_with('Pichau', part())
        self.assertIsNone(self.repo.data['offers', old['id']]['valid_until'])
        self.assertEqual(self.repo.data['offers', old['id']]['pix'], 200000)
        self.assertEqual(self.repo.queued[-1]['action'], 'scan')

    def test_cancel_is_atomic_owned_and_only_for_pending_commands(self):
        identifier='00000000-0000-0000-0000-000000000001'
        self.repo.request=AsyncMock(return_value=[{'id':identifier}])
        response=self.client.post('/api/commands/'+identifier+'/cancel',json={})
        self.assertEqual(response.status_code,200)
        params=self.repo.request.call_args.kwargs['params']
        self.assertEqual(params['owner_id'],'eq.owner-a')
        self.assertEqual(params['status'],'eq.pending')
        self.assertEqual(params['action'],'neq.component_delete')
        self.repo.request=AsyncMock(return_value=[])
        self.assertEqual(self.client.post('/api/commands/'+identifier+'/cancel',json={}).status_code,409)

    def test_coupon_disabled_is_saved_online_without_pc_command(self):
        self.repo.data['coupon_applications', 'VALIDO'] = {'code': 'VALIDO', 'status': 'inserted',
            'detail': 'Adicionado', 'found_at': utcnow(), 'source': 'Telegram', 'attempts': 1}
        for disabled, group in ((True, 'disabled'), (False, 'active')):
            response = self.client.post('/api/commands', json={'action': 'coupon_disabled',
                'payload': {'code': 'VALIDO', 'disabled': disabled}})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['execution'], 'cloud')
            self.assertEqual(self.client.get('/api/coupons').json()['applications'][0]['group'], group)
        self.assertFalse(self.repo.queued)
        self.assertEqual(self.repo.data['coupon_applications', 'VALIDO']['status'], 'inserted')

    def test_coupon_disabled_override_survives_older_local_snapshot(self):
        self.repo.data['coupon_applications', 'VALIDO'] = {'code': 'VALIDO', 'status': 'new',
            'detail': '', 'found_at': utcnow(), 'source': 'Telegram', 'attempts': 0, 'disabled': False}
        self.repo.data['overrides', 'coupon-disabled:VALIDO'] = {'code': 'VALIDO', 'disabled': True, 'found_at': utcnow()}
        self.assertEqual(self.client.get('/api/coupons').json()['applications'][0]['group'], 'disabled')
        self.repo.data['overrides', 'coupon-disabled:VALIDO']['found_at'] = (datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
        self.assertEqual(self.client.get('/api/coupons').json()['applications'][0]['group'], 'new')

    def test_coupon_disable_refuses_foreign_old_or_invalid_code(self):
        for payload,status in (({'code':'DESCONHECIDO','disabled':True},404),
                               ({'code':'ABC','disabled':'yes'},422),({'code':'../ABC','disabled':True},422)):
            response = self.client.post('/api/commands',json={'action':'coupon_disabled','payload':payload})
            self.assertEqual(response.status_code,status)
        self.assertFalse(self.repo.written)
        self.assertFalse(self.repo.queued)

    def test_session_commands_allow_only_browser_stores(self):
        for name in ('Mercado Livre', 'Shopee'):
            for action in ('session_open','session_confirm'):
                response = self.client.post('/api/commands',json={'action':action,'payload':{'shop':name}})
                self.assertEqual(response.status_code,200)
                self.assertEqual(self.repo.queued[-1]['payload']['shop'],name)
        self.assertEqual(self.client.post('/api/commands',json={'action':'session_open','payload':{'shop':'Pichau'}}).status_code,422)

    def test_manual_cloud_stores_do_not_wait_for_one_another(self):
        from cloud_protocol import CLOUD_SHOPS
        self.repo.request = AsyncMock(return_value=True)
        started=set();ready=asyncio.Event()
        async def collect(collectors,repo,component,known,name,timeout):
            started.add(name)
            if len(started)==len(CLOUD_SHOPS):ready.set()
            await asyncio.wait_for(ready.wait(),0.5)
            return {'name':name,'count':1,'failures':0}
        collectors=SimpleNamespace(close=AsyncMock())
        with patch('cloud.app.collect_shop',side_effect=collect),patch('cloud.app.Shops',return_value=collectors):
            response=self.client.post('/api/scan/1',json={})
        self.assertEqual(response.status_code,200)
        self.assertEqual(started,set(CLOUD_SHOPS))
        self.assertIn('4 leituras',response.json()['detail'])

    def test_catalog_shows_five_minute_manual_cooldown(self):
        original=self.repo.records;stamp=utcnow()
        async def records(kind):
            return [{'record_key':'1','data':{'started_at':stamp},'updated_at':stamp}] if kind=='scans' else await original(kind)
        self.repo.records=records
        next_at=self.client.get('/api/catalog').json()['scan_next_at']['1']
        self.assertEqual(datetime.fromisoformat(next_at)-datetime.fromisoformat(stamp),timedelta(minutes=5))

    def test_public_coupon_failure_does_not_stop_other_sources_or_erase_cache(self):
        import json
        old={'code':'ANTERIORMC','shop':'KaBuM','source':'Melhores Cartões','conditions':'Informática',
             'url':'https://www.kabum.com.br','source_url':'https://www.melhorescartoes.com.br',
             'activation':False,'found_at':utcnow(),'checked_at':utcnow()}
        self.repo.data['settings','cloud_coupon_feed']={'value':json.dumps([old])}
        self.repo.request=AsyncMock(return_value=True)
        new=dict(old,code='NOVOPEL',shop='Mercado Livre',source='Pelando',url='https://www.mercadolivre.com.br/cupons')
        async def read(name):
            if name=='Melhores Cartões':raise ValueError('Fonte indisponível')
            return [new]
        collectors=SimpleNamespace(coupon_list=AsyncMock(return_value=[]),
            public_coupon_source=AsyncMock(side_effect=read),close=AsyncMock())
        with patch('cloud.app.Shops',return_value=collectors):
            response=self.client.post('/api/coupons/refresh',json={})
        self.assertEqual(response.status_code,200)
        statuses={row['source']:row for row in response.json()['status']}
        self.assertEqual(statuses['Melhores Cartões']['failures'],1)
        self.assertEqual(statuses['Pelando']['count'],1)
        saved=json.loads(self.repo.data['settings','cloud_coupon_feed']['value'])
        self.assertEqual({row['code'] for row in saved},{'ANTERIORMC','NOVOPEL'})
        pulled=self.client.post('/api/worker/pull',json={}).json()['coupon_feed']
        self.assertEqual(pulled,saved)
        shown=self.client.get('/api/coupons').json()
        self.assertIn('NOVOPEL',[row['code'] for row in shown['coupons']])
        self.assertEqual(len(shown['collection_status']),3)
        self.assertFalse(self.repo.queued)
        collectors.close.assert_awaited_once()

    def test_idle_worker_expires_only_old_running_commands_without_resubmitting(self):
        self.repo.request=AsyncMock(side_effect=[None,[]])
        response=self.client.post('/api/worker/claim',json={})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['commands'],[])
        cleanup,claim=self.repo.request.call_args_list
        self.assertEqual(cleanup.args,('PATCH','monitor_commands'))
        params=cleanup.kwargs['params']
        self.assertEqual(params['owner_id'],'eq.owner-a')
        self.assertEqual(params['status'],'eq.running')
        cutoff=datetime.fromisoformat(params['updated_at'][3:])
        self.assertAlmostEqual((datetime.now(timezone.utc)-cutoff).total_seconds(),3600,delta=5)
        self.assertEqual(cleanup.kwargs['data']['status'],'failed')
        self.assertEqual(claim.args,('POST','rpc/monitor_claim_commands'))
        self.assertFalse(self.repo.queued)

    def test_public_coupon_refresh_respects_cooldown_without_http_calls(self):
        self.repo.request=AsyncMock(return_value=False)
        with patch('cloud.app.Shops') as collectors:
            self.assertEqual(self.client.post('/api/coupons/refresh',json={}).status_code,429)
        collectors.assert_not_called()

    def test_duplicate_coupon_sources_keep_one_saved_application_state(self):
        import json
        coupon = {'code': 'SITETODO', 'shop': 'Mercado Livre', 'source': 'Pelando',
                  'source_url': 'https://www.pelando.com.br/cupons', 'url': 'https://www.mercadolivre.com.br/cupons',
                  'activation': False, 'conditions': 'Todo site', 'found_at': utcnow(), 'checked_at': utcnow()}
        self.repo.data['settings', 'public_coupons'] = {'value': json.dumps([coupon, dict(coupon, source='Outra fonte')])}
        self.repo.data['coupon_applications', 'SITETODO'] = {'code': 'SITETODO', 'status': 'inserted',
                    'detail': 'Adicionado', 'found_at': utcnow(), 'attempts': 1, 'source': 'Pelando'}
        body = self.client.get('/api/coupons').json()
        self.assertEqual(len(body['applications']), 1)
        self.assertEqual(body['applications'][0]['group'], 'active')
        self.assertEqual(body['applications'][0]['status'], 'inserted')

    def test_check_http_offer_runs_in_cloud_and_saves_observation(self):
        old = offer('http', 200000, origins='Telegram')
        self.repo.data['offers', old['id']] = old
        collectors = SimpleNamespace(check=AsyncMock(return_value=dict(old, pix=190000)), close=AsyncMock())
        with patch('cloud.app.Shops', return_value=collectors):
            response = self.client.post('/api/commands', json={'action': 'check', 'payload': {'key': old['id']}})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['checked'])
        self.assertEqual(response.json()['execution'], 'cloud')
        self.assertEqual(self.repo.data['offers', old['id']]['pix'], 190000)
        self.assertEqual(self.repo.data['offers', old['id']]['origins'], 'Telegram')
        self.assertEqual(len([row for row in self.repo.written if row['kind'] == 'observations']), 1)
        self.assertFalse(self.repo.queued)
        collectors.close.assert_awaited_once()

    def test_check_http_failure_preserves_price_but_removes_confirmation(self):
        old = offer('blocked', 200000)
        self.repo.data['offers', old['id']] = old
        collectors = SimpleNamespace(check=AsyncMock(side_effect=ValueError('blocked')), close=AsyncMock())
        with patch('cloud.app.Shops', return_value=collectors):
            response = self.client.post('/api/commands', json={'action': 'check', 'payload': {'key': old['id']}})
        self.assertFalse(response.json()['checked'])
        saved = self.repo.data['offers', old['id']]
        self.assertEqual(saved['pix'], 200000)
        self.assertIsNone(saved['valid_until'])
        self.assertFalse(self.repo.written)
        self.assertFalse(self.repo.queued)

    def test_check_browser_offer_stays_local(self):
        old = offer('browser', 200000, shop='Mercado Livre', url='https://www.mercadolivre.com.br/produto/p/MLB123')
        self.repo.data['offers', old['id']] = old
        with patch('cloud.app.Shops') as collectors:
            response = self.client.post('/api/commands', json={'action': 'check', 'payload': {'key': old['id']}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.repo.queued[-1]['action'], 'check')
        collectors.assert_not_called()

    def test_check_does_not_trust_cloud_shop_label_for_another_domain(self):
        self.repo.data['offers', 'unknown'] = offer('unknown', 200000, url='https://example.org/item')
        with patch('cloud.app.Shops') as collectors:
            self.client.post('/api/commands', json={'action': 'check', 'payload': {'key': 'unknown'}})
        collectors.assert_not_called()

    def test_check_unknown_offer_does_not_start_collector(self):
        with patch('cloud.app.Shops') as collectors:
            response = self.client.post('/api/commands', json={'action': 'check', 'payload': {'key': 'missing'}})
        self.assertEqual(response.status_code, 404)
        collectors.assert_not_called()

    def test_scan_cooldown_refuses_repeat_without_calling_collectors(self):
        self.repo.request = AsyncMock(return_value=False)
        with patch('cloud.app.Shops') as collectors:
            self.assertEqual(self.client.post('/api/scan/1', json={}).status_code, 429)
        collectors.assert_not_called()


class RepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_verified_identity_and_server_owned_writes(self):
        requests = []
        def handle(request):
            requests.append(request)
            if request.url.path.endswith('/user'):
                return httpx.Response(200, json={'id': 'owner-a', 'is_anonymous': False})
            return httpx.Response(201, json=[])
        with patch.dict(os.environ, SUPABASE_URL='https://test.supabase.co', SUPABASE_PUBLISHABLE_KEY='public-test'):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                self.assertEqual((await user_session(client, 'session'))['id'], 'owner-a')
                repo = Repository(client, 'session', 'owner-a')
                await repo.put_many([{'kind': 'status', 'record_key': 'pc', 'data': {}, 'owner_id': 'foreign'}])
        self.assertIn(b'"owner_id":"owner-a"', requests[-1].content)
        self.assertNotIn(b'foreign', requests[-1].content)

    async def test_history_requests_only_selected_component_and_period(self):
        with patch.dict(os.environ, SUPABASE_URL='https://test.supabase.co', SUPABASE_PUBLISHABLE_KEY='public-test'):
            repo = Repository(None, 'session', 'owner-a')
            repo.request = AsyncMock(return_value={'rows': [], 'truncated': False})
            self.assertEqual(await repo.history(5, '2026-10-01'), {'rows': [], 'truncated': False})
            self.assertEqual(repo.request.call_args.args, ('POST', 'rpc/monitor_recent_observations'))
            self.assertEqual(repo.request.call_args.kwargs['data'], {'component_key': '5', 'since_day': '2026-10-01'})

    async def test_preference_uses_one_atomic_rpc(self):
        with patch.dict(os.environ,SUPABASE_URL='https://test.supabase.co',SUPABASE_PUBLISHABLE_KEY='public-test'):
            repo=Repository(None,'session','owner-a');repo.request=AsyncMock(return_value={'favorite':True,'hidden':False})
            self.assertEqual(await repo.preference('one','favorite',True),{'favorite':True,'hidden':False})
            repo.request.assert_awaited_once_with('POST','rpc/monitor_set_preference',data={'offer_key':'one','preference_field':'favorite','enabled':True})

    async def test_old_pending_commands_remain_visible_beside_recent_history(self):
        with patch.dict(os.environ, SUPABASE_URL='https://test.supabase.co', SUPABASE_PUBLISHABLE_KEY='public-test'):
            repo = Repository(None, 'session', 'owner-a')
            async def read(method, path, params):
                self.assertEqual(params['owner_id'], 'eq.owner-a')
                if params['status'] == 'in.(pending,running)':
                    self.assertEqual(params['order'], 'created_at.asc')
                    return [{'id': 'old-pending', 'status': 'pending'}]
                self.assertEqual(params['limit'], 50)
                return [{'id': str(i), 'status': 'done'} for i in range(50)]
            repo.request = AsyncMock(side_effect=read)
            rows = await repo.commands()
            self.assertEqual(rows[0]['id'], 'old-pending')
            self.assertEqual(len(rows), 51)

    async def test_no_token_or_anonymous_session_denied(self):
        with self.assertRaises(HTTPException) as error:
            await user_session(None, None)
        self.assertEqual(error.exception.status_code, 401)
        with patch.dict(os.environ, SUPABASE_URL='https://test.supabase.co', SUPABASE_PUBLISHABLE_KEY='public-test'):
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'id': 'guest', 'is_anonymous': True}))) as client:
                with self.assertRaises(HTTPException):
                    await user_session(client, 'guest-session')

    async def test_pagination_does_not_omit_second_page(self):
        with patch.dict(os.environ, SUPABASE_URL='https://test.supabase.co', SUPABASE_PUBLISHABLE_KEY='public-test'):
            repo = Repository(None, 'session', 'owner')
            repo.request = AsyncMock(side_effect=[[{'data': {}}]*500, [{'data': {}}]])
            self.assertEqual(len(await repo.records('offers')), 501)
            self.assertEqual(repo.request.call_args.kwargs['params']['offset'], 500)


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/'test.sqlite3')
        self.monitor = SimpleNamespace(store=self.store, shop_lock=asyncio.Lock(), scan_shops=AsyncMock(), alert=AsyncMock())
        self.bridge = CloudSync(self.monitor, self.temp.name)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    async def test_session_open_and_confirm_reuse_owned_browser(self):
        browser=SimpleNamespace(open_login=AsyncMock(),confirm=AsyncMock())
        self.monitor.shops=SimpleNamespace(ml_browser=browser,shopee_browser=SimpleNamespace(open_login=AsyncMock()))
        self.monitor.shop_status={}
        self.store.save_component('Placa','custom','rtx 5060',None,None,'pix')
        detail=await self.bridge.execute({'action':'session_open','payload':{'shop':'Mercado Livre'}})
        browser.open_login.assert_awaited_once()
        self.assertIn('feche essa janela',detail)
        detail=await self.bridge.execute({'action':'session_confirm','payload':{'shop':'Mercado Livre'}})
        browser.confirm.assert_awaited_once()
        self.assertIn('Sessão confirmada',detail)
        self.monitor.shops.shopee_browser.open_login.assert_not_awaited()
        async with self.monitor.shop_lock:
            with self.assertRaises(ValueError):
                await self.bridge.execute({'action':'session_open','payload':{'shop':'Mercado Livre'}})

    async def test_cloud_coupon_feed_reaches_local_applicator_without_reapplying_success(self):
        from ml_coupon_applicator import CouponApplicator
        from unittest.mock import MagicMock
        self.monitor.ml_coupons=CouponApplicator(self.store,MagicMock(),self.monitor.shop_lock)
        self.monitor.ml_coupons.record('ATIVADO','Pelando','inserted','Cupom adicionado')
        rows=[dict(code=code,shop='Mercado Livre',source='Pelando',conditions='Todo site',activation=False,
                   source_url='https://www.pelando.com.br/d/cupom',url='https://www.mercadolivre.com.br/cupons',
                   found_at=utcnow(),checked_at=utcnow()) for code in ['ATIVADO','NOVO']]
        self.bridge.import_coupons(rows)
        self.bridge.import_coupons(rows)
        self.assertEqual(len(json.loads(self.store.get_setting('public_coupons'))),2)
        self.assertEqual([row[0] for row in self.monitor.ml_coupons.candidates()],['NOVO'])
        self.assertEqual(next(row for row in self.monitor.ml_coupons.catalog() if row['code']=='ATIVADO')['status'],'inserted')
        old=dict(rows[1],code='ONTEM',found_at=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat())
        self.bridge.import_coupons([old])
        self.assertNotIn('ONTEM',[row['code'] for row in self.monitor.ml_coupons.catalog()])

    async def test_coupon_cloud_preference_applies_only_today(self):
        calls=[]
        self.monitor.ml_coupons=SimpleNamespace(set_disabled=lambda code,disabled:calls.append((code,disabled)))
        self.bridge.apply_overrides([{'record_key':'coupon-disabled:VALIDO','data':{'code':'VALIDO','disabled':True,'found_at':utcnow()}},
            {'record_key':'coupon-disabled:ANTIGO','data':{'code':'ANTIGO','disabled':True,
               'found_at':(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()}}],[])
        self.assertEqual(calls,[('VALIDO',True)])

    async def test_session_snapshot_contains_no_cookie_or_profile_path(self):
        browser=SimpleNamespace(configured=True,login_open=False,status='Perfil salvo',cookies='PRIVATE_COOKIE',profile='PRIVATE_PATH')
        self.monitor.shops=SimpleNamespace(ml_browser=browser,shopee_browser=browser)
        self.monitor.telegram_status='Conectado';self.monitor.shop_status={}
        self.monitor.ml_coupons=SimpleNamespace(status='Aguardando');self.monitor.olx=SimpleNamespace(status='Aguardando')
        self.bridge.request=AsyncMock(return_value={})
        await self.bridge.push(None,{'url':'https://panel.example'})
        calls=str(self.bridge.request.call_args_list)
        self.assertNotIn('PRIVATE_COOKIE',calls);self.assertNotIn('PRIVATE_PATH',calls)
        self.assertIn('configured',calls)

    async def test_worker_scans_only_browser_sources_and_refuses_busy_execution(self):
        await self.bridge.execute({'action': 'scan', 'payload': {'component_id': 1}})
        self.monitor.scan_shops.assert_awaited_once_with(force_ml=True, component_id=1, shops=LOCAL_SHOPS)
        async with self.monitor.shop_lock:
            with self.assertRaises(ValueError):
                await self.bridge.execute({'action': 'scan', 'payload': {'component_id': 1}})

    async def test_monitor_really_skips_http_sources_in_worker_scan(self):
        from monitor import Monitor
        monitor = Monitor(self.store, Path(self.temp.name))
        monitor.shops.discover = AsyncMock(return_value=[])
        monitor.shops.discover_mercado_livre = AsyncMock(return_value=[])
        try:
            await monitor.scan_shops(force_ml=True, component_id=1, shops=LOCAL_SHOPS)
            monitor.shops.discover.assert_awaited_once()
            self.assertEqual(monitor.shops.discover.call_args.args[0], 'Shopee')
            monitor.shops.discover_mercado_livre.assert_awaited_once()
        finally:
            await monitor.shops.close()
            await monitor.olx.collector.close()

    async def test_export_excludes_credentials_and_chat_ids(self):
        self.store.set_setting('telegram_api_hash', 'SENSITIVE')
        self.store.set_setting('shop:Pichau', '1')
        self.store.db.execute('UPDATE sources SET chat_id=?', (123456789,))
        self.store.db.commit()
        result = public_snapshot(self.store)
        self.assertNotIn('SENSITIVE', str(result))
        self.assertNotIn('chat_id', str(result))
        self.assertTrue(any(row['record_key'] == 'shop:Pichau' for row in result))

    async def test_cloud_component_preserves_id_locally(self):
        value = dict(part(), id=-123, target=210000)
        self.bridge.apply_overrides([{'record_key': 'component:-123', 'data': value}], [])
        row = next(p for p in self.store.components() if p['id'] == -123)
        self.assertEqual(row['target'], 210000)
        self.bridge.apply_overrides([{'record_key': 'component:-123', 'data': dict(id=-123, deleted=True)}], [])
        self.assertFalse(any(p['id'] == -123 for p in self.store.components()))

    async def test_import_failure_does_not_claim_commands(self):
        self.bridge.push = AsyncMock()
        self.bridge.request = AsyncMock(return_value={'overrides': [], 'preferences': [], 'offers': []})
        self.bridge.import_offers = AsyncMock(side_effect=ValueError('invalid'))
        with patch('cloud_sync.load_cloud_credentials', return_value={'url': 'https://panel.example', 'access_token': 'session', 'refresh_token': 'refresh'}):
            with self.assertRaises(ValueError):
                await self.bridge.cycle()
        self.assertEqual(self.bridge.request.await_count, 1)
        self.assertEqual(self.bridge.request.call_args.args[3], '/api/worker/pull')


if __name__ == '__main__':
    unittest.main()
