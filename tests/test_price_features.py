from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from core import Store, group_offers, matches, offer_matches, utcnow


class IdentificationTests(unittest.TestCase):
    def test_accessories_and_kits_are_excluded(self):
        cases = [('ssd', 'RLSOCO Estojo rígido para SSD Kingston NV3 500GB/1TB/2TB (apenas estojo)'),
                 ('ssd', 'SSD Kingston NV3 1TB + kit upgrade'),
                 ('gpu', 'Suporte para RTX 5060'), ('gpu', 'Waterblock para RTX 5060'),
                 ('gpu', 'Kit RTX 5060 e Ryzen'), ('psu', 'Cabo para Corsair CX750'),
                 ('psu', 'Combo fonte CX750 e gabinete')]
        for kind, title in cases:
            with self.subTest(title=title):
                self.assertFalse(matches(dict(kind=kind, capacity_gb=1000), title))
        self.assertTrue(matches({'kind': 'gpu'}, 'RTX 5060 com backplate'))
        self.assertTrue(matches({'kind': 'psu'}, 'Fonte Corsair CX750 com cabo de força'))
        self.assertFalse(matches(dict(kind='custom', query='rx 9060'), 'Suporte para RX 9060'))
        self.assertFalse(matches(dict(kind='custom', query='rx 9060'), 'Kit Ryzen e RX 9060'))
        self.assertTrue(matches(dict(kind='custom', query='suporte rx 9060'), 'Suporte para RX 9060'))

    def test_ssd_requires_only_the_requested_capacity_not_transfer_speed(self):
        part = dict(kind='ssd', capacity_gb=1000)
        for title in ['SSD NV3 1TB', 'NV3 1000GB / 1TB', 'NV3 1024GB até 6GB/s']:
            self.assertTrue(matches(part, title), title)
        for title in ['NV3 500GB/1TB/2TB', 'NV3 2TB', 'NV3 SNV3S/1000G 1GB/s', 'NV3 1TB e 500GB']:
            self.assertFalse(matches(part, title), title)
        self.assertTrue(matches(dict(kind='ssd', capacity_gb=2000), 'NV3 2 TB'))

    def test_telegram_generic_title_uses_message_until_store_identification(self):
        part = dict(kind='ssd', capacity_gb=1000)
        offer = dict(title='Oferta imperdível', message='SSD NV3 1TB', status='Anunciado no Telegram')
        self.assertTrue(offer_matches(part, offer))
        offer.update(title='Estojo para NV3 1TB', status='Preço lido na loja')
        self.assertFalse(offer_matches(part, offer))
        offer.update(title='SSD Kingston NV3 1TB')
        self.assertTrue(offer_matches(part, offer))

    def test_failed_model_confirmation_excludes_the_advertised_message(self):
        self.assertFalse(offer_matches(dict(kind='ssd', capacity_gb=1000), dict(title='SSD NV3 1TB',
            message='SSD NV3 1TB', status='A página não confirmou o modelo da peça; anúncio preservado sem conferência.')))


class PriceFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'monitor.sqlite3'
        self.store = Store(self.path)
        self.part = self.store.components()[0]
        self.now = datetime.now(timezone.utc)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def save(self, price=100000, number=1, **changes):
        offer = dict(url=f'https://www.pichau.com.br/item-{number}', title='RTX 5060 modelo A',
                     seller='Pichau', shop='Pichau', pix=price, card=None, announced=None,
                     coupons=[], status='Preço lido na loja', availability='in',
                     checked_at=utcnow(), published_at=utcnow(), received_at=utcnow())
        offer.update(changes)
        return self.store.upsert_offer(self.part['id'], offer, dict(source='Pichau', published_at=utcnow()))[0]

    def observe(self, offer, days_ago, pix, card=None, announced=None, status='Preço lido na loja'):
        self.store.db.execute('INSERT INTO observations(offer_id,observed_at,pix,card,announced,status) VALUES(?,?,?,?,?,?)',
            (offer['id'], (self.now - timedelta(days=days_ago)).isoformat(), pix, card, announced, status))
        self.store.db.commit()

    def test_existing_accessory_does_not_distort_catalog_ranking_or_history(self):
        self.part = self.store.components()[2]
        accessory = self.save(9803, title='Estojo para SSD Kingston NV3 1TB', shop='Amazon')
        ssd = self.save(39999, number=2, title='SSD Kingston NV3 1TB')
        self.assertEqual([row['id'] for row in group_offers([self.part], self.store.offers())[self.part['id']]], [ssd['id']])
        self.assertFalse(self.store.should_alert(accessory, True))
        self.assertTrue(self.store.should_alert(ssd, True))
        history = self.store.price_history(self.part['id'], 'pix')
        self.assertEqual(history['30']['minimum'], 39999)
        self.assertEqual(len(self.store.offers()), 2)

    def test_daily_minimum_prevents_repeated_queries_biasing_median(self):
        row = self.save()
        self.store.db.execute('DELETE FROM observations')
        for _ in range(12):
            self.observe(row, 2, 80000)
        self.observe(row, 2, 70000)
        self.observe(row, 1, 100000)
        self.observe(row, 0, 120000)
        history = self.store.price_history(self.part['id'], 'pix', self.now)
        self.assertEqual(history['7']['minimum'], 70000)
        self.assertEqual(history['7']['median'], 100000)
        self.assertEqual(history['7']['days'], 3)
        self.assertEqual(len(history['points']), 3)

    def test_seven_and_thirty_day_boundaries_and_missing_days(self):
        row = self.save()
        self.store.db.execute('DELETE FROM observations')
        for days, value in [(30, 100), (29, 50000), (7, 60000), (6, 70000), (0, 80000), (-1, 1)]:
            self.observe(row, days, value)
        history = self.store.price_history(self.part['id'], 'pix', self.now)
        self.assertEqual(history['7']['minimum'], 70000)
        self.assertEqual(history['7']['days'], 2)
        self.assertEqual(history['30']['minimum'], 50000)
        self.assertEqual(history['30']['days'], 4)

    def test_history_separates_payments_and_ignores_failed_or_announced_readings(self):
        row = self.save()
        self.store.db.execute('DELETE FROM observations')
        self.observe(row, 1, 80000, card=110000, announced=90000)
        self.observe(row, 1, None, announced=95000)
        self.observe(row, 0, 100, card=200, status='Falha de rede')
        self.observe(row, 0, 50, status='Anunciado no Telegram')
        self.observe(row, 0, 0)
        for payment, expected in [('pix', 80000), ('card', 110000), ('announced', 95000)]:
            with self.subTest(payment=payment):
                self.assertEqual(self.store.price_history(self.part['id'], payment, self.now)['30']['minimum'], expected)
        with self.assertRaises(ValueError):
            self.store.price_history(self.part['id'], 'installment')

    def test_empty_history_has_no_invented_prices(self):
        self.assertEqual(self.store.price_history(self.part['id'], 'pix')['points'], [])
        self.assertEqual(self.store.price_history(self.part['id'], 'pix')['7']['median'], None)

    def test_history_uses_stock_at_observation_not_current_listing_stock(self):
        self.save(100000)
        self.save(50000, availability='out')
        history = self.store.price_history(self.part['id'], 'pix')
        self.assertEqual(history['30']['minimum'], 100000)
        self.assertEqual(self.store.offers()[0]['availability'], 'out')

    def test_legacy_observations_keep_prices_with_unknown_stock(self):
        row = self.save()
        self.store.db.execute('DROP TABLE observations')
        self.store.db.execute('CREATE TABLE observations(id INTEGER PRIMARY KEY,offer_id INTEGER,observed_at TEXT,pix INTEGER,card INTEGER,announced INTEGER,status TEXT)')
        self.store.db.execute('INSERT INTO observations(offer_id,observed_at,pix,status) VALUES(?,?,?,?)',
                              (row['id'], utcnow(), 100000, 'Preço lido na loja'))
        self.store.db.commit()
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.rows('SELECT availability FROM observations')[0]['availability'], 'unknown')
        self.assertEqual(self.store.price_history(self.part['id'], 'pix')['30']['minimum'], 100000)

    def test_unknown_payment_ranking_excludes_prices_with_known_pix_or_card(self):
        self.save(80000, announced=80000)
        candidate = self.save(None, number=2, title='RTX 5060 modelo B', announced=100000)
        self.assertTrue(self.store.should_alert(candidate, True))
        self.assertEqual(self.store.alert_evaluation(candidate, True)['count'], 1)

    def test_unchanged_store_price_records_a_new_day_once(self):
        row = self.save()
        self.store.db.execute('UPDATE observations SET observed_at=?', ((self.now-timedelta(days=1)).isoformat(),))
        self.store.db.commit()
        self.save()
        self.save()
        self.assertEqual(len(self.store.rows('SELECT * FROM observations')), 2)

    def test_repeat_requires_inclusive_two_percent_drop_and_keeps_reference(self):
        row = self.save()
        self.store.mark_alert(row)
        self.assertFalse(self.store.should_alert(self.save(99000), True))
        self.assertFalse(self.store.should_alert(self.save(98001), True))
        row = self.save(98000)
        decision = self.store.alert_evaluation(row, True)
        self.assertIsNotNone(decision)
        self.assertIn('queda de 2.0%', decision['reason'])
        self.store.mark_alert(row)
        self.assertFalse(self.store.should_alert(self.save(97000), True))
        self.assertTrue(self.store.should_alert(self.save(96040), True))

    def test_small_changes_coupons_installments_and_price_increase_do_not_repeat(self):
        self.store.mark_alert(self.save())
        for changes in [dict(coupons=['GPU10']), dict(installments=12, installment=9000), dict(pix=110000)]:
            with self.subTest(changes=changes):
                self.assertFalse(self.store.should_alert(self.save(**changes), True))

    def test_repeat_baseline_survives_restart_and_known_duplicate_url(self):
        self.store.mark_alert(self.save())
        self.store.close()
        self.store = Store(self.path)
        self.assertFalse(self.store.should_alert(self.save(99000, number=2), True))
        self.assertTrue(self.store.should_alert(self.save(98000, number=2), True))

    def test_different_variants_sellers_and_stores_can_notify_separately(self):
        self.store.mark_alert(self.save())
        for number, changes in enumerate([dict(title='RTX 5060 White'), dict(seller='Outro'), dict(shop='Amazon')], 2):
            with self.subTest(changes=changes):
                self.assertTrue(self.store.should_alert(self.save(number=number, **changes), True))

    def test_alias_merge_preserves_notification_price_reference(self):
        first = self.save()
        self.store.mark_alert(first)
        second = self.save(99000, number=2)
        merged = self.store.resolve_offer_url(first['id'], second['url'])
        self.assertEqual(merged, second['id'])
        self.assertFalse(self.store.should_alert(self.store.offer(merged), True))

    def test_reason_uses_comparable_competitors_and_enough_history(self):
        row = self.save()
        self.assertEqual(self.store.alert_evaluation(row, True)['reason'], 'Única oferta comparável')
        self.save(120000, number=2, title='RTX 5060 modelo B')
        self.store.db.execute('DELETE FROM observations')
        for day in [1, 2, 3]:
            self.observe(row, day, 120000)
        reason = self.store.alert_evaluation(row, True)['reason']
        self.assertIn('Novo menor preço', reason)
        self.assertIn('16.7% abaixo da mediana', reason)

    def test_two_percent_drop_still_must_qualify_for_top_ten_percent(self):
        self.store.mark_alert(self.save())
        self.save(90000, number=2, title='RTX 5060 modelo B')
        self.assertFalse(self.store.should_alert(self.save(98000), True))

    def test_legacy_alert_migration_is_additive_and_recoverable(self):
        row = self.save()
        self.store.db.execute('DROP TABLE alerts')
        self.store.db.execute('CREATE TABLE alerts(offer_id INTEGER,fingerprint TEXT,delivered_at TEXT,PRIMARY KEY(offer_id,fingerprint))')
        self.store.db.execute('INSERT INTO alerts VALUES(?,?,?)', (row['id'], row['fingerprint'], utcnow()))
        self.store.db.commit()
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.rows('SELECT price FROM alerts')[0]['price'], 100000)
        self.assertFalse(self.store.should_alert(self.save(99000), True))
        self.assertTrue(self.store.should_alert(self.save(98000), True))

    def test_legacy_reference_uses_observation_before_delivery_not_current_price(self):
        row = self.save()
        self.store.db.execute('DROP TABLE alerts')
        self.store.db.execute('CREATE TABLE alerts(offer_id INTEGER,fingerprint TEXT,delivered_at TEXT,PRIMARY KEY(offer_id,fingerprint))')
        self.store.db.execute('UPDATE observations SET observed_at=?', ((self.now-timedelta(days=2)).isoformat(),))
        self.store.db.execute('INSERT INTO alerts VALUES(?,?,?)', (row['id'], row['fingerprint'], (self.now-timedelta(days=1)).isoformat()))
        self.store.db.commit()
        self.save(99000)
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.rows('SELECT price FROM alerts')[0]['price'], 100000)
        self.assertTrue(self.store.should_alert(self.save(98000), True))
