import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from core import Store, group_offers, top_offers, utcnow
from presentation import comparison_rows, offer_selection, toggle_comparison


class OfferPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'monitor.sqlite3'
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def save(self, number, price=100000, component_id=1, **changes):
        stamp = utcnow()
        row = dict(url=f'https://www.pichau.com.br/offer-{number}', title=f'MSI RTX 5060 modelo {number}',
                   shop='Pichau', seller='Pichau', pix=price, card=None, announced=None, coupons=[],
                   availability='in', status='Preço lido na loja', published_at=stamp, received_at=stamp, checked_at=stamp)
        row.update(changes)
        return self.store.upsert_offer(component_id, row, dict(source='Teste', published_at=stamp))[0]

    def selected(self, view=''):
        return offer_selection(self.store.components(), self.store.offers(), view)[1]

    def set_limit(self, target, payment='pix'):
        part = self.store.components()[0]
        self.store.save_component(part['name'], part['kind'], part['query'], part['capacity_gb'], target, payment, part['id'])

    def test_catalog_limit_updates_saved_offers_without_fetching_or_deleting_history(self):
        cheap = self.save(1, 90000)
        equal = self.save(2, 100000)
        expensive = self.save(3, 100001)
        unknown_pix = self.save(4, None, announced=90000)
        snapshot = self.store.offers()
        self.set_limit(100000)
        self.assertEqual([row['id'] for row in offer_selection(self.store.components(), snapshot, '')[1]], [cheap['id'], equal['id']])
        self.set_limit(95000)
        self.assertEqual([row['id'] for row in offer_selection(self.store.components(), snapshot, '')[1]], [cheap['id']])
        self.set_limit(None)
        self.assertEqual({row['id'] for row in offer_selection(self.store.components(), snapshot, '')[1]},
                         {cheap['id'], equal['id'], expensive['id'], unknown_pix['id']})
        self.assertEqual(len(self.store.rows('SELECT * FROM observations')), 4)

    def test_card_limit_uses_total_instead_of_pix_or_individual_installment(self):
        eligible = self.save(1, 95000, card=100000)
        self.save(2, 90000, card=100001, installments=12, installment=8334)
        self.save(3, 90000)
        self.set_limit(100000, 'card')
        self.assertEqual([row['id'] for row in self.selected()], [eligible['id']])

    def test_limit_is_applied_before_top_twelve(self):
        for index in range(12):
            self.save(index, 80000 + index, card=150000)
        eligible = self.save(13, 95000, card=100000)
        self.set_limit(100000, 'card')
        self.assertEqual([row['id'] for row in self.selected()], [eligible['id']])

    def test_limit_is_applied_before_choosing_duplicate_representative(self):
        invalid = self.save(1, 80000, card=150000)
        eligible = self.save(2, 90000, card=100000, title=invalid['title'])
        self.set_limit(100000, 'card')
        self.assertEqual([row['id'] for row in self.selected()], [eligible['id']])

    def test_maximum_does_not_assume_coupon_or_announced_price_is_pix(self):
        self.save(1, 110000, coupon_price=90000)
        self.save(2, None, shop='Mercado Livre', announced=110000, coupon_price=90000)
        self.set_limit(100000)
        self.assertEqual(self.selected(), [])

    def test_over_limit_saved_and_hidden_offers_remain_accessible_in_their_selections(self):
        favorite = self.save(1, 110000)
        hidden = self.save(2, 110000)
        self.store.set_offer_preference([favorite['id']], 'favorite', True)
        self.store.set_offer_preference([hidden['id']], 'hidden', True)
        self.set_limit(100000)
        self.assertEqual(self.selected(), [])
        self.assertEqual([row['id'] for row in self.selected('favorite')], [favorite['id']])
        self.assertEqual([row['id'] for row in self.selected('hidden')], [hidden['id']])

    def test_preferences_survive_update_and_reopen_without_erasing_history(self):
        row = self.save(1)
        for name in ('favorite', 'hidden'):
            self.store.set_offer_preference([row['id']], name, True)
        self.save(1, 90000)
        self.store.close()
        self.store = Store(self.path)
        current = self.store.offer(row['id'])
        self.assertEqual((current['favorite'], current['hidden'], current['pix']), (1, 1, 90000))
        self.assertEqual(len(self.store.rows('SELECT * FROM observations')), 2)

    def test_migration_defaults_preserve_existing_offers_and_history(self):
        row = self.save(1)
        self.store.close()
        with closing(sqlite3.connect(self.path)) as database:
            database.execute('ALTER TABLE offers DROP COLUMN favorite')
            database.execute('ALTER TABLE offers DROP COLUMN hidden')
            database.commit()
        self.store = Store(self.path)
        current = self.store.offer(row['id'])
        self.assertEqual((current['favorite'], current['hidden'], current['pix']), (0, 0, 100000))
        self.assertEqual(len(self.store.rows('SELECT * FROM observations')), 1)

    def test_hidden_offer_excluded_from_catalog_tracking_alerts_and_can_be_restored(self):
        row = self.save(1)
        self.assertTrue(self.store.should_alert(row, True))
        self.store.set_offer_preference([row['id']], 'hidden', True)
        self.assertEqual(self.selected(), [])
        self.assertFalse(self.store.should_alert(row, True))  # Even a stale in-memory candidate.
        self.assertFalse(self.store.should_track_offer(self.store.offer(row['id'])))
        self.assertEqual(self.selected('hidden')[0]['id'], row['id'])
        self.store.set_offer_preference([row['id']], 'hidden', False)
        self.assertEqual(self.selected()[0]['id'], row['id'])
        self.assertTrue(self.store.should_alert(self.store.offer(row['id']), True))

    def test_hiding_a_group_keeps_other_stores_and_variants_and_fills_top_twelve(self):
        rows = [self.save(index, 100000 + index * 1000) for index in range(13)]
        duplicate = self.save(20, 100000, title=rows[0]['title'])
        amazon = self.save(21, 100500, title=rows[0]['title'], shop='Amazon', seller='Amazon')
        grouped = self.selected()[0]
        self.assertEqual(set(grouped['duplicate_ids']), {rows[0]['id'], duplicate['id']})
        self.store.set_offer_preference(grouped['duplicate_ids'], 'hidden', True)
        selected = self.selected()
        self.assertEqual(len(selected), 12)
        self.assertIn(amazon['id'], {row['id'] for row in selected})
        self.assertFalse(set(grouped['duplicate_ids']).intersection(item for row in selected for item in row['duplicate_ids']))

    def test_favorite_survives_representative_change_and_is_available_outside_top_twelve(self):
        rows = [self.save(index, 100000 + index * 1000) for index in range(13)]
        self.store.set_offer_preference([rows[-1]['id']], 'favorite', True)
        cheaper_duplicate = self.save(20, 111500, title=rows[-1]['title'])
        self.assertNotIn(cheaper_duplicate['id'], {row['id'] for row in self.selected()})
        favorites = self.selected('favorite')
        self.assertEqual(len(favorites), 1)
        self.assertEqual(favorites[0]['id'], cheaper_duplicate['id'])
        self.assertTrue(favorites[0]['favorite'])
        self.assertFalse(self.store.should_track_offer(self.store.offer(cheaper_duplicate['id'])))

    def test_saved_views_keep_price_order_and_twelve_limit_and_hide_favorites(self):
        rows = [self.save(index, 100000 + index * 1000) for index in range(14)]
        self.store.set_offer_preference([row['id'] for row in rows], 'favorite', True)
        self.store.set_offer_preference([rows[0]['id']], 'hidden', True)
        favorites = self.selected('favorite')
        self.assertEqual(len(favorites), 12)
        self.assertEqual([row['pix'] for row in favorites], sorted(row['pix'] for row in favorites))
        self.assertNotIn(rows[0]['id'], {row['id'] for row in favorites})

    def test_url_merge_keeps_favorite_and_hidden_on_surviving_offer(self):
        first, second = self.save(1), self.save(2)
        self.store.set_offer_preference([first['id']], 'favorite', True)
        self.store.set_offer_preference([second['id']], 'hidden', True)
        merged_id = self.store.resolve_offer_url(first['id'], second['url'])
        self.assertEqual(merged_id, second['id'])
        merged = self.store.offer(merged_id)
        self.assertEqual((merged['favorite'], merged['hidden']), (1, 1))
        self.assertEqual(len(self.store.rows('SELECT * FROM observations WHERE offer_id=?', (merged_id,))), 2)

    def test_preference_rejects_arbitrary_database_fields(self):
        row = self.save(1)
        with self.assertRaises(ValueError):
            self.store.set_offer_preference([row['id']], 'pix', True)
        self.assertEqual(self.store.offer(row['id'])['pix'], 100000)

    def test_comparison_accepts_three_same_piece_and_rejects_fourth_and_other_piece(self):
        rows = [self.save(index) for index in range(4)]
        selected = []
        for row in rows[:3]:
            selected = toggle_comparison(selected, row)
        self.assertEqual(len(selected), 3)
        with self.assertRaisesRegex(ValueError, 'até três'):
            toggle_comparison(selected, rows[3])
        different = self.save(30, component_id=2, title='Fonte Corsair CX750')
        with self.assertRaisesRegex(ValueError, 'mesma peça'):
            toggle_comparison(selected[:1], different)
        with self.assertRaisesRegex(ValueError, 'Restaure'):
            toggle_comparison([], dict(rows[3], hidden=1))

    def test_comparison_removes_duplicate_group_instead_of_adding_twice(self):
        first = self.save(1)
        second = self.save(2, title=first['title'])
        grouped = group_offers(self.store.components(), self.store.offers())[1][0]
        self.assertEqual(toggle_comparison([grouped], second), [])

    def test_comparison_preserves_payment_and_coupon_conditions_without_inventing_freight(self):
        row = self.save(1, card=120000, installments=12, installment=10000, coupon_price=90000, coupons=['PROMO'])
        fields = {item['field']: item['offer0'] for item in comparison_rows([row])}
        self.assertEqual(fields['Pix'], 'R$ 1.000,00')
        self.assertEqual(fields['Total no cartão'], 'R$ 1.200,00')
        self.assertEqual(fields['Parcelamento'], '12x de R$ 100,00')
        self.assertIn('R$ 900,00', fields['Preço com cupom'])
        self.assertIn('não validados', fields['Códigos publicados'])
        self.assertEqual(fields['Frete'], 'Não consultado')
        self.assertIn('desatualizado', comparison_rows([dict(row, valid_until='2000-01-01T00:00:00+00:00')])[7]['offer0'])

    def test_unknown_prices_and_seller_stay_unknown_in_comparison(self):
        row = self.save(1, price=None, seller=None)
        fields = {item['field']: item['offer0'] for item in comparison_rows([row])}
        self.assertEqual(fields['Pix'], 'Não informado')
        self.assertEqual(fields['Vendedor'], 'Não informado')
        self.assertEqual(fields['Preço com cupom'], 'Não confirmado')


if __name__ == '__main__':
    unittest.main()
