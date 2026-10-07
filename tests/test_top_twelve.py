import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core import Store, top_offers, utcnow
from monitor import Monitor
from presentation import filter_offers


class TopTwelveTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'monitor.sqlite3')
        self.monitor = Monitor(self.store, Path(self.temp.name))
        self.monitor.shops.discover = AsyncMock(return_value=[])
        self.monitor.shops.discover_mercado_livre = AsyncMock(return_value=[])
        self.monitor.shops.coupon_list = AsyncMock(return_value=[])
        self.monitor.shops.public_coupon_list = AsyncMock(return_value=[])
        self.monitor.alert = AsyncMock()

    async def asyncTearDown(self):
        await self.monitor.shops.close()
        self.store.close()
        self.temp.cleanup()

    def save(self, number, price, component_id=1, **changes):
        stamp = utcnow()
        offer = dict(url=f'https://www.pichau.com.br/item-{component_id}-{number}',
                     title=f'MSI RTX 5060 modelo {number}', seller='Pichau', shop='Pichau',
                     pix=price, card=None, announced=None, coupon_price=None, installments=None,
                     installment=None, coupons=[], availability='in', shipping_origin='local',
                     status='Preço lido na loja', published_at=stamp, checked_at=stamp, received_at=stamp)
        offer.update(changes)
        return self.store.upsert_offer(component_id, offer, dict(source='Teste', published_at=stamp))[0]

    def fill(self, count=13):
        return [self.save(number, 100000 + number * 1000) for number in range(count)]

    def selected(self):
        return top_offers(self.store.components(), self.store.offers())[1]

    def test_exactly_twelve_after_ordering_across_shops_and_before_filters(self):
        self.fill()
        amazon = self.save(20, 99000, shop='Amazon', seller='Amazon')
        rows = self.selected()
        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[0]['id'], amazon['id'])
        self.assertEqual([row['pix'] for row in rows], sorted(row['pix'] for row in rows))
        self.assertEqual(len(filter_offers(rows, shop='Pichau')), 11)
        self.assertEqual(len(self.store.offers()), 14)

    def test_each_component_gets_its_own_twelve(self):
        self.fill()
        for number in range(14):
            self.save(number, 30000 + number * 1000, component_id=2,
                      title=f'Fonte Corsair CX750 modelo {number}')
        grouped = top_offers(self.store.components(), self.store.offers())
        self.assertEqual((len(grouped[1]), len(grouped[2])), (12, 12))

    def test_older_cheapest_offer_stays_selected_beyond_three_hundred_records(self):
        first = self.save(0, 90000)
        for number in range(1, 302):
            self.save(number, 100000 + number * 1000)
        self.assertEqual(self.selected()[0]['id'], first['id'])
        self.assertEqual(len(self.selected()), 12)

    def test_duplicates_do_not_consume_slots_and_ties_never_exceed_twelve(self):
        rows = [self.save(number, 100000) for number in range(13)]
        duplicate = self.save(30, 100000, title=rows[0]['title'])
        selected = self.selected()
        self.assertEqual(len(selected), 12)
        self.assertEqual(selected[0]['duplicate_ids'], [duplicate['id'], rows[0]['id']])
        self.assertEqual({row['id'] for row in selected}, {row['id'] for row in self.selected()})
        self.assertFalse(self.store.should_track_offer(rows[-1]))

    def test_confirmed_coupon_can_enter_and_disappearance_removes_it(self):
        self.fill()
        discounted = self.save(20, None, shop='Mercado Livre', seller='Loja',
                               announced=200000, coupon_price=99000)
        self.assertEqual(self.selected()[0]['id'], discounted['id'])
        self.assertTrue(self.store.should_track_offer(discounted))
        cleared = self.save(20, None, shop='Mercado Livre', seller='Loja', announced=200000)
        self.assertNotIn(cleared['id'], [row['id'] for row in self.selected()])
        self.assertFalse(self.store.should_track_offer(cleared))

    def test_expensive_duplicate_is_not_read_just_because_its_group_has_a_cheap_offer(self):
        rows = self.fill()
        duplicate = self.save(30, 300000, title=rows[0]['title'])
        self.assertTrue(self.store.should_track_offer(rows[0]))
        self.assertFalse(self.store.should_track_offer(duplicate))

    def test_expired_readings_keep_top_checks_bounded_without_using_old_coupon(self):
        stamp = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        rows = [self.save(number, 100000 + number * 1000, checked_at=stamp) for number in range(13)]
        discounted = self.save(20, None, shop='Mercado Livre', seller='Loja',
                               announced=200000, coupon_price=1000, checked_at=stamp)
        self.assertTrue(self.store.should_track_offer(rows[0]))
        self.assertFalse(self.store.should_track_offer(rows[-1]))
        self.assertFalse(self.store.should_track_offer(discounted))
        self.assertEqual(len(self.selected()), 12)

    def test_out_of_stock_or_ignored_brand_frees_a_slot(self):
        rows = self.fill()
        self.store.db.execute("UPDATE offers SET availability='out' WHERE id=?", (rows[0]['id'],))
        self.store.db.commit()
        self.assertTrue(self.store.should_track_offer(rows[-1]))
        self.assertEqual(len(self.selected()), 12)
        self.assertNotIn(rows[0]['id'], [row['id'] for row in self.selected()])
        self.store.db.execute("UPDATE components SET ignored_brands='[\"MSI\"]' WHERE id=1")
        self.store.db.commit()
        self.assertEqual(self.selected(), [])
        self.assertFalse(self.store.should_track_offer(rows[-1]))

    def test_new_unknown_price_needs_first_read_and_new_cheaper_price_reenters(self):
        rows = self.fill()
        unknown = self.save(30, None)
        self.assertTrue(self.store.should_track_offer(unknown))
        self.assertFalse(self.store.should_track_offer(rows[-1]))
        cheaper = self.save(12, 98000)
        self.assertTrue(self.store.should_track_offer(cheaper))
        self.assertEqual(self.selected()[0]['id'], cheaper['id'])

    async def test_discovery_does_not_read_known_pages_above_cutoff(self):
        rows = self.fill()
        self.monitor.shops.discover.side_effect = lambda shop, part: [rows[0]['url'], rows[-1]['url']] if part['id'] == 1 else []
        self.monitor.shops.check = AsyncMock(return_value=rows[0])
        for name in ('Mercado Livre', 'KaBuM', 'Amazon', 'Shopee', 'Terabyte Shop'):
            self.store.set_setting('shop:' + name, '0')
        with patch('monitor.asyncio.sleep', new_callable=AsyncMock):
            await self.monitor.scan_shops()
        self.assertEqual([call.args[0] for call in self.monitor.shops.check.await_args_list], [rows[0]['url']])
        self.assertEqual(len(self.store.offers()), 13)

    async def test_stale_revalidation_only_reads_selected_known_groups(self):
        stamp = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        rows = [self.save(number, 100000 + number * 1000, checked_at=stamp) for number in range(13)]
        self.monitor.check_offer = AsyncMock()
        for name in ('Mercado Livre', 'KaBuM', 'Amazon', 'Shopee'):
            self.store.set_setting('shop:' + name, '0')
        with patch('monitor.asyncio.sleep', new_callable=AsyncMock):
            await self.monitor.scan_shops()
        checked = [call.args[0] for call in self.monitor.check_offer.await_args_list]
        self.assertEqual(len(checked), 4)
        self.assertNotIn(rows[-1]['id'], checked)

    async def test_queue_skips_costly_known_offer_but_manual_check_remains_available(self):
        rows = self.fill()
        self.monitor.enqueue(rows[-1]['id'])
        self.assertTrue(self.monitor.check_queue.empty())
        self.monitor.enqueue(rows[-1]['id'], manual=True)
        self.monitor.check_offer = AsyncMock()
        worker = asyncio.create_task(self.monitor.check_worker())
        await self.monitor.check_queue.join()
        worker.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await worker
        self.monitor.check_offer.assert_awaited_once_with(rows[-1]['id'])

    async def test_queue_rechecks_cutoff_when_another_offer_becomes_cheaper(self):
        rows = self.fill(12)
        self.monitor.enqueue(rows[-1]['id'])
        self.save(30, 90000)
        self.monitor.check_offer = AsyncMock()
        worker = asyncio.create_task(self.monitor.check_worker())
        await self.monitor.check_queue.join()
        worker.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await worker
        self.monitor.check_offer.assert_not_awaited()

    def test_alerts_above_twelve_stay_silent_even_if_top_ten_percent_would_allow(self):
        rows = self.fill(130)
        self.assertIsNone(self.store.alert_evaluation(rows[12], True))
        self.assertIsNotNone(self.store.alert_evaluation(rows[11], True))
