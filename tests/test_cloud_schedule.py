import asyncio
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from cloud.app import app
from cloud.collection import collect_shop, ScheduledReadings
from cloud_protocol import offer_key
from test_cloud import offer, part


class ScheduledApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.environment = patch.dict(os.environ, MONITOR_CRON_SECRET='test-scheduler')
        self.environment.start()
        self.payload = {'component': part(), 'shop': 'Pichau', 'offers': []}
        self.headers = {'Authorization': 'Bearer test-scheduler'}

    def tearDown(self):
        self.client.close()
        self.environment.stop()

    def test_separate_secret_required_before_creating_collector(self):
        with patch('cloud.app.Shops') as collectors:
            for headers in ({}, {'Authorization': 'Bearer user-login-token'}):
                self.assertEqual(self.client.post('/api/scheduled/collect', json=self.payload, headers=headers).status_code, 401)
            with patch.dict(os.environ, MONITOR_CRON_SECRET=''):
                self.assertEqual(self.client.post('/api/scheduled/collect', json=self.payload, headers=self.headers).status_code, 503)
        collectors.assert_not_called()

    def test_browser_stores_paused_parts_and_foreign_offers_rejected(self):
        invalid = [dict(self.payload, shop=name) for name in ('Mercado Livre', 'Shopee', 'OLX')]
        invalid += [dict(self.payload, component=dict(part(), enabled=0)),
                    dict(self.payload, offers=[offer('foreign', 100, component_id=2)]),
                    dict(self.payload, offers=[dict(offer('broken', 100), url=None)]),
                    dict(self.payload, offers=[dict(offer('broken', 100), id=None)])]
        with patch('cloud.app.Shops') as collectors:
            for data in invalid:
                self.assertEqual(self.client.post('/api/scheduled/collect', json=data, headers=self.headers).status_code, 422)
        collectors.assert_not_called()

    def test_returns_offer_history_and_status_without_database_login(self):
        reading = offer('one', 200000)
        collectors = SimpleNamespace(discover=AsyncMock(return_value=[reading['url']]),
            check=AsyncMock(return_value=reading), close=AsyncMock())
        with patch('cloud.app.Shops', return_value=collectors):
            response = self.client.post('/api/scheduled/collect', json=self.payload, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual({row['kind'] for row in result['records']}, {'offers', 'observations', 'status'})
        row = next(row['data'] for row in result['records'] if row['kind'] == 'offers')
        self.assertEqual(row['id'], offer_key(1, reading['url']))
        self.assertEqual(row['pix'], 200000)
        self.assertEqual(result['status']['count'], 1)
        self.assertFalse(any('owner_id' in row for row in result['records']))
        collectors.close.assert_awaited_once()


class ScheduledCollectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_hidden_and_known_above_twelfth_not_consulted(self):
        known = [offer(i, 200000+i*1000) for i in range(14)]
        known[13]['hidden'] = True
        collector = SimpleNamespace(discover=AsyncMock(return_value=[known[12]['url'], known[13]['url']]), check=AsyncMock())
        repo = ScheduledReadings(known)
        status = await collect_shop(collector, repo, part(), known, 'Pichau')
        collector.check.assert_not_awaited()
        self.assertEqual(status['count'], 0)

    async def test_new_expensive_offer_does_not_replace_cheapest_twelve(self):
        known = [offer(i, 200000+i*1000) for i in range(12)]
        reading = offer('expensive', 250000)
        collector = SimpleNamespace(discover=AsyncMock(return_value=[reading['url']]), check=AsyncMock(return_value=reading))
        repo = ScheduledReadings(known)
        await collect_shop(collector, repo, part(), known, 'Pichau')
        self.assertFalse(any(kind == 'offers' for kind, key in repo.written))

    async def test_failure_preserves_last_price_and_reports_failed_revalidation(self):
        old = offer('old', 200000)
        collector = SimpleNamespace(discover=AsyncMock(return_value=[old['url']]), check=AsyncMock(side_effect=ValueError('403')))
        repo = ScheduledReadings([old])
        status = await collect_shop(collector, repo, part(), [old], 'Pichau')
        saved = repo.written['offers', old['id']]['data']
        self.assertEqual(saved['pix'], old['pix'])
        self.assertIsNone(saved['valid_until'])
        self.assertEqual(status['failures'], 1)
        self.assertIn('histórico preservado', status['detail'])

    async def test_timeout_finishes_batch_and_keeps_completed_readings(self):
        first = offer('first', 200000)
        async def check(url, component):
            if url == first['url']:
                return first
            await asyncio.sleep(1)
        collector = SimpleNamespace(discover=AsyncMock(return_value=[first['url'], 'https://www.pichau.com.br/second']), check=check)
        repo = ScheduledReadings([])
        status = await collect_shop(collector, repo, part(), [], 'Pichau', timeout=0.02)
        self.assertEqual((status['count'], status['failures']), (1, 1))
        self.assertEqual(sum(kind == 'observations' for kind, key in repo.written), 1)


if __name__ == '__main__':
    unittest.main()
