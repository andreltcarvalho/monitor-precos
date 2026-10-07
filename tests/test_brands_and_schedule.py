import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core import Store, detect_brand, group_offers, matches, utcnow
from monitor import Monitor
from shops import product_offer, search_links


class BrandDetectionTests(unittest.TestCase):
    def test_manufacturers_and_aliases_are_canonical_without_matching_substrings(self):
        for title, expected in [('Placa MSI RTX 5060', 'MSI'), ('GIGABYTE AORUS RTX 5060', 'Gigabyte'),
                                ('INNO 3D RTX 5060', 'INNO3D'), ('ASUS RTX 5060 Ti', 'ASUS'),
                                ('Fonte Corsair CX750', 'Corsair'), ('Kingston NV3 1TB', 'Kingston'),
                                ('Placa MAXSUN RTX 5060', 'Maxsun')]:
            with self.subTest(title=title):
                self.assertEqual(detect_brand(title), expected)
        self.assertIsNone(detect_brand('RTX 5060 modelo desconhecido'))
        self.assertIsNone(detect_brand('MSI Gigabyte RTX 5060'))
        self.assertIsNone(detect_brand('Corsairism PNYXYZ'))

    def test_model_filter_respects_ignored_brands_for_telegram_and_custom_gpu(self):
        part = {'kind': 'gpu', 'ignored_brands': '["Maxsun", "INNO3D"]'}
        self.assertFalse(matches(part, 'MAXSUN RTX 5060 8GB'))
        self.assertFalse(matches(part, 'INNO 3D RTX 5060'))
        self.assertTrue(matches(part, 'MSI RTX 5060 8GB'))
        self.assertTrue(matches(part, 'RTX 5060 marca não informada'))
        self.assertFalse(matches({'kind':'custom', 'query':'rtx 5060 ti', 'ignored_brands':['Maxsun']},
                                 'MAXSUN RTX 5060 Ti 16GB'))

    def test_catalog_hides_ignored_brand_without_removing_raw_offers(self):
        part = {'id':1, 'kind':'gpu', 'ignored_brands':['Maxsun']}
        offers = [dict(id=1, component_id=1, title='Maxsun RTX 5060', pix=100000),
                  dict(id=2, component_id=1, title='MSI RTX 5060', pix=200000)]
        self.assertEqual([row['id'] for row in group_offers([part], offers)[1]], [2])
        self.assertEqual(len(offers), 2)
        part['ignored_brands'] = []
        self.assertEqual(len(group_offers([part], offers)[1]), 2)

    def test_search_excludes_brand_and_confirmed_product_identifies_brand(self):
        part = {'kind':'gpu', 'ignored_brands':['Maxsun']}
        html = '<a href="/maxsun/p/MLB123">MAXSUN RTX 5060</a><a href="/msi/p/MLB124">MSI RTX 5060</a>'
        links = search_links(html, 'https://www.mercadolivre.com.br/rtx-5060', part)
        self.assertEqual(links, ['https://www.mercadolivre.com.br/msi/p/MLB124'])
        offer = product_offer('<h1>MSI RTX 5060</h1><p>R$ 2.000,00 no Pix</p>', links[0], part)
        self.assertEqual(offer['brand'], 'MSI')


class BrandStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'monitor.sqlite3'
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def save_offer(self, brand, price, number):
        offer = dict(url=f'https://www.pichau.com.br/rtx-{number}', title=f'{brand} RTX 5060',
                     shop='Pichau', pix=price, card=None, announced=None, coupons=[],
                     status='Preço lido na loja', availability='in', published_at=utcnow(), received_at=utcnow())
        return self.store.upsert_offer(1, offer, {'source':'Pichau', 'published_at':utcnow()})[0]

    def ignore(self, brands):
        self.store.save_component('RTX 5060', 'gpu', 'rtx 5060', None, None, 'pix', 1, brands)

    def test_preference_survives_restart_and_old_save_call_does_not_reset_it(self):
        self.ignore(['Maxsun', 'INNO3D', 'Maxsun'])
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(json.loads(self.store.components()[0]['ignored_brands']), ['Maxsun', 'INNO3D'])
        self.store.save_component('RTX 5060', 'gpu', 'rtx 5060', None, None, 'pix', 1)
        self.assertEqual(json.loads(self.store.components()[0]['ignored_brands']), ['Maxsun', 'INNO3D'])

    def test_excluded_offer_does_not_notify_or_lower_alert_cutoff(self):
        excluded = self.save_offer('Maxsun', 100000, 1)
        wanted = self.save_offer('MSI', 200000, 2)
        self.ignore(['Maxsun'])
        self.assertFalse(self.store.should_alert(self.store.offer(excluded['id']), True))
        self.assertTrue(self.store.should_alert(self.store.offer(wanted['id']), True))
        self.assertEqual(len(self.store.offers()), 2)
        self.assertEqual(len(self.store.rows('SELECT * FROM observations')), 2)

    def test_migration_backfills_brand_and_keeps_data_and_history(self):
        saved = self.save_offer('Gigabyte', 200000, 1)
        self.store.db.execute('ALTER TABLE offers DROP COLUMN brand')
        self.store.db.execute('ALTER TABLE components DROP COLUMN ignored_brands')
        self.store.db.commit()
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.offer(saved['id'])['brand'], 'Gigabyte')
        self.assertEqual(self.store.components()[0]['ignored_brands'], '[]')
        self.assertEqual(len(self.store.rows('SELECT * FROM observations')), 1)


class ShopScheduleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'monitor.sqlite3')
        self.monitor = Monitor(self.store, Path(self.temp.name))
        self.monitor.shops.discover = AsyncMock(return_value=[])
        async def discover_ml(component):
            return [dict(url=url, reading=None) for url in await self.monitor.shops.discover('Mercado Livre', component)]
        self.monitor.shops.discover_mercado_livre = AsyncMock(side_effect=discover_ml)
        self.monitor.shops.coupon_list = AsyncMock(return_value=[])
        self.monitor.shops.public_coupon_list = AsyncMock(return_value=[])

    async def asyncTearDown(self):
        await self.monitor.shops.close()
        self.store.close()
        self.temp.cleanup()

    def called_shops(self):
        return [call.args[0] for call in self.monitor.shops.discover.await_args_list]

    async def test_mercado_livre_runs_after_all_other_shops_and_pichau_coupons(self):
        sequence = []
        async def discover(shop, part):
            sequence.append(shop)
            return []
        async def coupons():
            sequence.append('Cupons Pichau')
            return []
        self.monitor.shops.discover.side_effect = discover
        self.monitor.shops.coupon_list.side_effect = coupons
        await self.monitor.scan_shops()
        self.assertEqual(sequence, ['Pichau'] * 3 + ['KaBuM'] * 3 + ['Amazon'] * 3
                         + ['Shopee'] * 3 + ['Terabyte Shop'] * 3 + ['Cupons Pichau'] + ['Mercado Livre'] * 3)

    async def test_automatic_cycles_skip_meli_until_thirty_minutes_but_keep_other_shops(self):
        with patch('monitor.monotonic', side_effect=[100, 699, 1899, 1900]):
            for expected in (True, False, False, True):
                self.monitor.shops.discover.reset_mock()
                await self.monitor.scan_shops()
                shops = self.called_shops()
                self.assertEqual('Mercado Livre' in shops, expected)
                self.assertEqual(shops[:15], ['Pichau'] * 3 + ['KaBuM'] * 3 + ['Amazon'] * 3 + ['Shopee'] * 3 + ['Terabyte Shop'] * 3)

    async def test_manual_query_bypasses_meli_interval(self):
        with patch('monitor.monotonic', side_effect=[100, 101]):
            await self.monitor.scan_shops()
            self.monitor.shops.discover.reset_mock()
            await self.monitor.scan_shops(force_ml=True)
        self.assertEqual(self.called_shops()[-3:], ['Mercado Livre'] * 3)

    async def test_cycle_duration_does_not_add_another_ten_minutes_of_delay(self):
        self.monitor.running = True
        self.monitor.scan_shops = AsyncMock()
        async def sleep(delay):
            self.monitor.running = False
        with patch('monitor.monotonic', side_effect=[100, 340]), patch('monitor.asyncio.sleep', side_effect=sleep) as sleeper:
            await self.monitor.shop_loop()
        sleeper.assert_awaited_once_with(360)
