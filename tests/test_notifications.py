import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import unittest

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

from cloud.app import app, repository
from cloud.notifications import bot_call, candidates, recipient
from test_cloud import FakeRepository, part, offer
from core import utcnow

TOKEN = '123456789:' + 'synthetic_fixture_' * 2


class NotificationRulesTests(unittest.TestCase):
    def test_below_limit_does_not_require_cheapest_ten_percent(self):
        rows = [offer(i, 100000 + i * 1000) for i in range(12)]
        result = candidates([part(notification_target=120000)], rows)
        self.assertEqual(len(result), 12)
        self.assertEqual(result[-1]['price'], 111000)
        self.assertEqual(candidates([part(notification_target=100000)], rows), [])

    def test_limit_optional_and_independent_of_catalog_maximum(self):
        self.assertEqual(candidates([part()], [offer(1, 100000)]), [])
        component = dict(part(notification_target=150000), target=90000)
        self.assertEqual(len(candidates([component], [offer(1, 100000)])), 1)

    def test_confirmed_coupon_used_but_announced_coupon_ignored(self):
        ml = offer('coupon', None, shop='Mercado Livre', announced=130000, coupon_price=110000)
        result = candidates([part(notification_target=120000)], [ml])
        self.assertEqual(result[0]['price'], 110000)
        self.assertIn('Com cupom', result[0]['text'])
        ml.update(status='Anunciado no Telegram', published_at=utcnow())
        self.assertEqual(candidates([part(notification_target=120000)], [ml]), [])

    def test_invalid_hidden_paused_brand_and_disabled_shop_excluded(self):
        component = part(notification_target=120000)
        for fields in ({'hidden': True}, {'availability': 'out'}, {'valid_until': utcnow()},
                       {'title': 'Outra peça'}, {'shop': 'Mercado Livre', 'shipping_origin': 'international'},
                       {'url': 'javascript:alert(1)'}):
            self.assertEqual(candidates([component], [offer(1, 100000, **fields)]), [])
        self.assertEqual(candidates([dict(component, enabled=0)], [offer(1, 100000)]), [])
        self.assertEqual(candidates([dict(component, ignored_brands=['MSI'])], [offer(1, 100000, title='MSI RTX 5060')]), [])
        self.assertEqual(candidates([component], [offer(1, 100000)], settings={'shop:Pichau': '0'}), [])

    def test_same_offer_same_or_higher_price_not_repeated_lower_allowed(self):
        component = part(notification_target=150000)
        first = candidates([component], [offer(1, 110000)])[0]
        receipt = {'identity': first['identity'], 'price': first['price']}
        for price in (110000, 120000):
            self.assertEqual(candidates([component], [offer(1, price)], [receipt]), [])
        self.assertEqual(candidates([component], [offer(1, 100000)], [receipt])[0]['price'], 100000)

    def test_duplicate_model_same_store_not_double_notified(self):
        component = part(notification_target=150000)
        rows = [offer(1, 110000, title='MSI RTX 5060'), offer(2, 100000, title='MSI RTX 5060')]
        result = candidates([component], rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['offer_id'], '2')
        white = offer(3, 120000, title='MSI RTX 5060 White')
        self.assertEqual(len(candidates([component], rows+[white])), 2)

    def test_pairing_requires_nonce_private_chat_and_recent_message(self):
        start = datetime.now(timezone.utc)-timedelta(minutes=1)
        message = {'message': {'text': '/start nonce', 'date': int(datetime.now(timezone.utc).timestamp()),
                              'chat': {'id': 123, 'type': 'private'}, 'from': {'id': 123}}}
        self.assertEqual(recipient([message], 'nonce', start.isoformat()), '123')
        self.assertIsNone(recipient([message], 'other', start.isoformat()))
        self.assertIsNone(recipient([message], 'nonce', (start+timedelta(days=1)).isoformat()))
        message['message']['chat']['type'] = 'group'
        self.assertIsNone(recipient([message], 'nonce', start.isoformat()))

    def test_telegram_network_error_never_exposes_token(self):
        client = AsyncMock()
        client.post.side_effect = httpx.ReadTimeout('Sensitive URL ' + TOKEN)
        with self.assertRaises(HTTPException) as error:
            asyncio.run(bot_call(client, TOKEN, 'getMe'))
        self.assertNotIn(TOKEN, str(error.exception.detail))
        self.assertEqual(error.exception.status_code, 502)

    def test_blocked_bot_and_conflict_have_actionable_errors(self):
        for code in (401, 403, 409, 429):
            client = AsyncMock()
            client.post.return_value = httpx.Response(code, json={'ok': False, 'error_code': code})
            with self.assertRaises(HTTPException) as error:
                asyncio.run(bot_call(client, TOKEN, 'getMe'))
            self.assertNotIn(TOKEN, error.exception.detail)
            self.assertNotIn('Sensitive', error.exception.detail)


class NotificationApiTests(unittest.TestCase):
    def setUp(self):
        self.repo = FakeRepository()
        self.repo.data['components', '1'] = part(notification_target=250000)
        self.config = dict(token=TOKEN, username='fixture_bot', nonce='nonce', chat_id=None,
                           paired_at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
                           pair_until=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat(), enabled=False)
        self.repo.request = AsyncMock(return_value=self.config)
        app.dependency_overrides[repository] = lambda: self.repo
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()

    def save(self, **fields):
        data = dict(part(), target_text='', notification_target_text='2.000,00')
        data.update(fields)
        return self.client.post('/api/components', json=data)

    def test_threshold_saved_as_cents_empty_disables_and_invalid_rejected(self):
        self.assertEqual(self.save().json()['notification_target'], 200000)
        self.assertEqual(self.save(notification_target_text='').json()['notification_target'], None)
        for value in ('0', '-1', 'abc', '2.000,123', 100, True):
            response = self.save(notification_target_text=value)
            self.assertEqual(response.status_code, 422)
            self.assertIn('notification_target_text', response.json()['detail'])

    def test_old_client_preserves_cloud_override_notification_target(self):
        self.repo.data['overrides', 'component:1'] = {'notification_target': 190000}
        data = dict(part(), target_text='')
        self.assertEqual(self.client.post('/api/components', json=data).json()['notification_target'], 190000)

    def test_status_never_returns_token_or_recipient_id(self):
        response = self.client.get('/api/notifications')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(TOKEN, response.text)
        self.assertNotIn('chat_id', response.json())
        self.assertIn('?start=nonce', response.json()['pair_url'])

    def test_connect_validates_bot_before_saving_and_does_not_return_token(self):
        with patch('cloud.app.bot_call', AsyncMock(return_value={'username': 'fixture_bot'})):
            response = self.client.post('/api/notifications/connect', json={'token': TOKEN})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(TOKEN, response.text)
        self.assertEqual(self.repo.request.call_args_list[0].args[1], 'rpc/monitor_telegram_save')

    def test_pair_uses_unique_start_and_no_group_or_old_message(self):
        updates = [{'message': {'text': '/start nonce', 'date': int(datetime.now(timezone.utc).timestamp()),
                   'chat': {'type': 'private', 'id': 123}, 'from': {'id': 123}}}]
        with patch('cloud.app.bot_call', AsyncMock(return_value=updates)):
            response = self.client.post('/api/notifications/pair', json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.repo.request.call_args_list[1].kwargs['data']['recipient_id'], '123')
        with patch('cloud.app.bot_call', AsyncMock(return_value=[])):
            self.assertEqual(self.client.post('/api/notifications/pair', json={}).status_code, 422)

    def test_test_requires_recipient_and_propagates_failure_without_secret(self):
        self.assertEqual(self.client.post('/api/notifications/test', json={}).status_code, 422)
        self.config['chat_id'] = '123'
        with patch('cloud.app.bot_call', AsyncMock(side_effect=HTTPException(502, 'Bot bloqueado.'))):
            response = self.client.post('/api/notifications/test', json={})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn(TOKEN, response.text)

    def test_scheduler_requires_secret_and_returns_candidates_only(self):
        payload = {'components': [part(notification_target=120000)], 'offers': [offer(1, 100000)], 'receipts': []}
        with patch.dict('os.environ', {'MONITOR_CRON_SECRET': 'fixture-secret'}):
            self.assertEqual(self.client.post('/api/scheduled/notifications', json=payload).status_code, 401)
            response = self.client.post('/api/scheduled/notifications', json=payload, headers={'Authorization': 'Bearer fixture-secret'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['notifications'][0]['price'], 100000)
            self.assertEqual(self.client.post('/api/scheduled/notifications', json={'components': {}, 'offers': []}, headers={'Authorization': 'Bearer fixture-secret'}).status_code, 422)


if __name__ == '__main__':
    unittest.main()
