import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core import Store, utcnow
from monitor import Monitor


class PieceRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'monitor.sqlite3')
        self.monitor = Monitor(self.store, Path(self.temp.name))
        self.monitor.shops.discover = AsyncMock(return_value=[])
        async def discover_ml(component):
            return [dict(url=url, reading=None) for url in await self.monitor.shops.discover('Mercado Livre', component)]
        self.monitor.shops.discover_mercado_livre = AsyncMock(side_effect=discover_ml)
        self.monitor.shops.check = AsyncMock()
        self.monitor.shops.coupon_list = AsyncMock(return_value=[])
        self.monitor.shops.public_coupon_list = AsyncMock(return_value=[])
        self.monitor.alert = AsyncMock()

    async def asyncTearDown(self):
        await self.monitor.shops.close()
        self.store.close()
        self.temp.cleanup()

    def save(self, part_id, number, price=40000, stale=False):
        stamp = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat() if stale else utcnow()
        title = {1: 'MSI RTX 5060', 2: 'Fonte Corsair CX750', 3: 'SSD Kingston NV3 1TB'}[part_id]
        offer = dict(url=f'https://www.pichau.com.br/item-{part_id}-{number}', title=f'{title} modelo {number}',
                     seller='Pichau', shop='Pichau', pix=price, card=None, announced=None,
                     installments=None, installment=None, coupons=[], availability='in',
                     status='Preço lido na loja', checked_at=stamp, published_at=stamp, received_at=stamp)
        return self.store.upsert_offer(part_id, offer, dict(source='Teste', published_at=stamp))[0]

    async def test_scoped_discovery_only_visits_selected_piece_and_mercado_livre_last(self):
        await self.monitor.scan_shops(force_ml=True, component_id=2)
        calls = self.monitor.shops.discover.await_args_list
        self.assertEqual([call.args[0] for call in calls], ['Pichau', 'KaBuM', 'Amazon', 'Shopee', 'Terabyte Shop', 'Mercado Livre'])
        self.assertEqual([call.args[1]['id'] for call in calls], [2, 2, 2, 2, 2, 2])
        self.assertEqual(self.monitor.shop_scan_component_id, 2)
        self.assertIsNotNone(self.monitor.last_shop_scan_started)
        self.assertIsNotNone(self.monitor.last_shop_scan_finished)
        self.assertEqual(self.monitor.shop_status['Pichau'], 'Nenhum anúncio encontrado para esta peça')

    async def test_scoped_query_preserves_global_intervals_and_does_not_fetch_coupon_feeds(self):
        self.monitor.next_ml_scan = 500
        self.monitor.next_coupon_scan = 600
        with patch('monitor.monotonic', return_value=100):
            await self.monitor.scan_shops(force_ml=True, component_id=2)
        self.assertEqual((self.monitor.next_ml_scan, self.monitor.next_coupon_scan), (500, 600))
        self.monitor.shops.coupon_list.assert_not_awaited()
        self.monitor.shops.public_coupon_list.assert_not_awaited()
        self.assertIn('Mercado Livre', [call.args[0] for call in self.monitor.shops.discover.await_args_list])

    async def test_disabled_shops_are_skipped_for_selected_piece(self):
        self.store.set_setting('shop:Amazon', '0')
        self.store.set_setting('shop:Shopee', '0')
        self.store.set_setting('shop:Terabyte Shop', '0')
        self.store.set_setting('shop:Mercado Livre', '0')
        await self.monitor.scan_shops(component_id=2)
        self.assertEqual([call.args[0] for call in self.monitor.shops.discover.await_args_list], ['Pichau', 'KaBuM'])

    async def test_missing_or_paused_piece_never_falls_back_to_all_pieces(self):
        await self.monitor.scan_shops(component_id=999)
        self.store.toggle('components', 2, False)
        await self.monitor.scan_shops(component_id=2)
        self.monitor.shops.discover.assert_not_awaited()
        self.monitor.shops.coupon_list.assert_not_awaited()
        self.assertIsNone(self.monitor.last_shop_scan_started)

    async def test_concurrent_query_is_rejected_without_changing_current_scope(self):
        self.monitor.shop_scan_component_id = 1
        async with self.monitor.shop_lock:
            await self.monitor.scan_shops(component_id=2)
        self.monitor.shops.discover.assert_not_awaited()
        self.assertEqual(self.monitor.shop_scan_component_id, 1)

    async def test_scoped_revalidation_never_touches_other_piece(self):
        other = self.save(1, 1, stale=True)
        selected = self.save(2, 1, stale=True)
        self.monitor.check_offer = AsyncMock()
        for shop in ('KaBuM', 'Amazon', 'Mercado Livre'):
            self.store.set_setting('shop:' + shop, '0')
        with patch('monitor.asyncio.sleep', new_callable=AsyncMock):
            await self.monitor.scan_shops(component_id=2)
        self.monitor.check_offer.assert_awaited_once_with(selected['id'])
        self.assertEqual(self.store.offer(other['id'])['checked_at'], other['checked_at'])

    async def test_scoped_discovery_updates_selected_piece_and_keeps_top_twelve_cutoff(self):
        rows = [self.save(2, number, 40000 + number * 1000) for number in range(13)]
        other = self.save(1, 1, 250000)
        self.monitor.shops.discover.side_effect = lambda shop, part: [rows[0]['url'], rows[-1]['url']] if shop == 'Pichau' else []
        found = dict(rows[0], pix=39000, checked_at=utcnow())
        self.monitor.shops.check.return_value = found
        with patch('monitor.asyncio.sleep', new_callable=AsyncMock):
            await self.monitor.scan_shops(component_id=2)
        self.monitor.shops.check.assert_awaited_once_with(rows[0]['url'], self.store.components()[1])
        self.assertEqual(self.store.offer(rows[0]['id'])['pix'], 39000)
        self.assertEqual(self.store.offer(other['id'])['pix'], 250000)

    async def test_next_global_scan_still_visits_all_pieces_and_clears_partial_scope(self):
        await self.monitor.scan_shops(component_id=2)
        self.monitor.shops.discover.reset_mock()
        await self.monitor.scan_shops(force_ml=True)
        self.assertEqual({call.args[1]['id'] for call in self.monitor.shops.discover.await_args_list}, {1, 2, 3})
        self.assertIsNone(self.monitor.shop_scan_component_id)
        self.monitor.shops.coupon_list.assert_awaited_once()
        self.monitor.shops.public_coupon_list.assert_awaited_once()
