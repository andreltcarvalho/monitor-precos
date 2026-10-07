import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx

from core import Store, group_offers, price_is_current, utcnow
from monitor import Monitor, notify_windows
from presentation import coupon_catalog, coupon_page, group_caption, offer_card_data
from shops import PUBLIC_COUPONS_URL, Shops, coupon_shop, public_coupons


class FreshnessAndCouponTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'monitor.sqlite3'
        self.store = Store(self.path)
        self.monitor = Monitor(self.store, Path(self.temp.name))
        self.monitor.shops.discover = AsyncMock(return_value=[])
        self.monitor.shops.discover_mercado_livre = AsyncMock(return_value=[])
        self.monitor.shops.coupon_list = AsyncMock(return_value=[])
        self.monitor.shops.public_coupon_list = AsyncMock(return_value=[])
        self.now = datetime.now(timezone.utc)

    async def asyncTearDown(self):
        await self.monitor.shops.close()
        self.store.close()
        self.temp.cleanup()

    def save(self, number=1, price=100000, age=0, coupon=None, shop='Pichau', **changes):
        stamp = (self.now - timedelta(minutes=age)).isoformat()
        offer = dict(url=f'https://www.pichau.com.br/item-{number}', title=f'MSI RTX 5060 modelo {number}',
                     shop=shop, pix=price if shop != 'Mercado Livre' else None,
                     card=None, announced=price if shop == 'Mercado Livre' else None,
                     installments=None, installment=None, coupon_price=coupon, coupons=[],
                     status='Preço lido na loja', availability='in', shipping_origin='local',
                     checked_at=stamp, published_at=stamp, received_at=stamp)
        offer.update(changes)
        return self.store.upsert_offer(1, offer, dict(source=shop, published_at=stamp))[0]

    async def test_expired_price_stops_affecting_cutoff_and_minimum_without_disappearing(self):
        old = self.save(1, 10000, age=31)
        current = self.save(2, 200000)
        rows = group_offers(self.store.components(), self.store.offers())[1]
        self.assertEqual([row['id'] for row in rows], [current['id'], old['id']])
        self.assertIn('R$ 2.000,00', group_caption(self.store.components()[0], rows))
        self.assertFalse(self.store.should_alert(old, True))
        self.assertTrue(self.store.should_alert(current, True))
        self.assertEqual(offer_card_data(old)['verification'], 'Preço desatualizado')
        self.assertEqual(len(self.store.offers()), 2)

    async def test_shop_specific_expiry_and_restart_do_not_renew_old_price(self):
        domestic = self.save(age=31)
        ml = self.save(2, age=89, shop='Mercado Livre')
        self.assertFalse(price_is_current(domestic, self.now))
        self.assertTrue(price_is_current(ml, self.now))
        self.assertFalse(price_is_current(ml, self.now + timedelta(minutes=2)))
        await self.monitor.shops.close()
        self.store.close()
        self.store = Store(self.path)
        self.monitor = Monitor(self.store, Path(self.temp.name))
        self.assertEqual(self.store.offer(domestic['id'])['valid_until'], domestic['valid_until'])

    async def test_failed_check_invalidates_price_without_losing_past_history(self):
        row = self.save()
        self.monitor.shops.check = AsyncMock(side_effect=ValueError('Consulta recusada'))
        await self.monitor.check_offer(row['id'])
        updated = self.store.offer(row['id'])
        self.assertFalse(price_is_current(updated))
        self.assertFalse(self.store.should_alert(updated, True))
        self.assertEqual(updated['pix'], 100000)
        self.assertEqual(self.store.price_history(1, 'pix')['30']['minimum'], 100000)
        self.assertEqual(len(self.store.rows('SELECT * FROM observations')), 1)

    async def test_scan_rechecks_only_four_missing_stale_offers_after_discovery(self):
        for number in range(7):
            self.save(number, age=31)
        self.save(9)
        self.monitor.check_offer = AsyncMock()
        for shop in ('Mercado Livre', 'KaBuM', 'Amazon'):
            self.store.set_setting('shop:' + shop, '0')
        with patch('monitor.asyncio.sleep', new=AsyncMock()):
            await self.monitor.scan_shops()
        self.assertEqual(self.monitor.check_offer.await_count, 4)

    async def test_confirmed_coupon_changes_cutoff_and_two_percent_repeat_reference(self):
        row = self.save(1, 100000, coupon=90000, shop='Mercado Livre')
        self.save(2, 95000, shop='Mercado Livre')
        decision = self.store.alert_evaluation(row, True)
        self.assertEqual(decision['price'], 90000)
        self.assertIn('com cupom na sua sessão', decision['reason'])
        self.store.mark_alert(row)
        self.assertFalse(self.store.should_alert(self.save(1, 100000, coupon=89000, shop='Mercado Livre'), True))
        lower = self.save(1, 100000, coupon=88000, shop='Mercado Livre')
        self.assertTrue(self.store.should_alert(lower, True))
        self.assertFalse(self.store.should_alert(self.save(1, 100000, shop='Mercado Livre'), True))

    async def test_session_coupon_does_not_satisfy_unrelated_pix_or_card_limit(self):
        self.store.save_component('RTX 5060', 'gpu', 'rtx 5060', None, 90000, 'pix', 1)
        self.assertFalse(self.store.should_alert(self.save(1, 100000, coupon=80000, shop='Mercado Livre'), True))
        self.store.save_component('RTX 5060', 'gpu', 'rtx 5060', None, 90000, 'card', 1)
        self.assertFalse(self.store.should_alert(self.save(1, 100000, coupon=80000, card=110000, shop='Mercado Livre'), True))

    async def test_history_stores_coupon_changes_same_day_and_keeps_original_price_separate(self):
        row = self.save(1, 100000, coupon=90000, shop='Mercado Livre')
        self.save(1, 100000, coupon=80000, shop='Mercado Livre')
        self.save(1, 100000, shop='Mercado Livre')
        self.assertEqual(self.store.price_history(1, 'effective')['30']['minimum'], 80000)
        self.assertEqual(self.store.price_history(1, 'announced')['30']['minimum'], 100000)
        readings = self.store.rows('SELECT coupon_price FROM observations WHERE offer_id=? ORDER BY id', (row['id'],))
        self.assertEqual([r['coupon_price'] for r in readings], [90000, 80000, None])

    async def test_manual_reading_records_and_clears_coupon_in_observations(self):
        row = self.save(1, 100000, shop='Mercado Livre')
        found = dict(row, coupon_price=80000, checked_at=utcnow())
        self.monitor.shops.check = AsyncMock(return_value=found)
        with patch('monitor.notify_windows'):
            await self.monitor.check_offer(row['id'])
            found['coupon_price'] = None
            await self.monitor.check_offer(row['id'])
        self.assertEqual([r['coupon_price'] for r in self.store.rows('SELECT coupon_price FROM observations ORDER BY id')], [None, 80000, None])

    async def test_old_offer_revalidated_now_can_notify_on_new_confirmed_coupon(self):
        row = self.save(1, 100000, age=120, shop='Mercado Livre')
        self.store.mark_alert(row)
        found = dict(row, coupon_price=80000, checked_at=utcnow(), status='Preço lido na loja')
        self.monitor.shops.check = AsyncMock(return_value=found)
        with patch('monitor.notify_windows') as notify:
            await self.monitor.check_offer(row['id'])
            notify.assert_called_once()
            self.assertEqual(self.store.rows('SELECT price FROM alerts ORDER BY rowid DESC LIMIT 1')[0]['price'], 80000)

    async def test_notification_shows_actual_discounted_price_and_session_condition(self):
        row = self.save(1, 100000, coupon=80000, shop='Mercado Livre')
        fake_toast = Mock()
        with patch('windows_toasts.Toast', return_value=fake_toast), patch('windows_toasts.WindowsToaster'):
            notify_windows(row)
        self.assertEqual(fake_toast.text_fields[1], 'R$ 800,00 com cupom na sua sessão')

    async def test_coupon_migration_does_not_invent_old_discounts(self):
        row = self.save(1, 100000, coupon=80000, shop='Mercado Livre')
        self.store.db.execute('ALTER TABLE observations DROP COLUMN coupon_price')
        self.store.db.execute('ALTER TABLE offers DROP COLUMN valid_until')
        self.store.db.commit()
        await self.monitor.shops.close()
        self.store.close()
        self.store = Store(self.path)
        self.monitor = Monitor(self.store, Path(self.temp.name))
        self.assertIsNone(self.store.rows('SELECT coupon_price FROM observations')[0]['coupon_price'])
        self.assertEqual(self.store.price_history(1, 'effective')['30']['minimum'], 100000)
        self.assertEqual(self.store.offer(row['id'])['coupon_price'], 80000)

    async def test_coupon_entities_and_message_link_are_persisted(self):
        baseline = (self.now - timedelta(seconds=10)).isoformat()
        self.store.db.execute('UPDATE sources SET chat_id=-100123,baseline=? WHERE id=1', (baseline,))
        self.store.db.commit()
        self.monitor.selected = {-100123: self.store.sources()[0]}
        await self.monitor.ingest(-100123, 5, 'Cupom `GPU10` para componentes', self.now,
                                  ['https://www.kabum.com.br/promocao'])
        post = self.store.rows('SELECT * FROM coupon_posts')[0]
        self.assertEqual(json.loads(post['links']), ['https://www.kabum.com.br/promocao'])
        self.assertIn('/5', post['message_url'])
        self.assertEqual(coupon_catalog([post], [], [])[0]['shop'], 'KaBuM')

    async def test_public_source_interval_failure_and_replacement(self):
        for shop in ('Mercado Livre', 'Pichau', 'KaBuM', 'Amazon'):
            self.store.set_setting('shop:' + shop, '0')
        self.monitor.shops.public_coupon_list.return_value = [dict(code='GPU10')]
        with patch('monitor.monotonic', return_value=1000):
            await self.monitor.scan_shops()
            await self.monitor.scan_shops()
        self.assertEqual(self.monitor.shops.public_coupon_list.await_count, 1)
        self.monitor.shops.public_coupon_list.side_effect = ValueError('Página bloqueada')
        await self.monitor.scan_shops(force_ml=True)
        self.assertEqual(json.loads(self.store.get_setting('public_coupons'))[0]['code'], 'GPU10')
        self.assertIn('indisponível', self.monitor.coupon_status)
        self.monitor.shops.public_coupon_list.side_effect = None
        self.monitor.shops.public_coupon_list.return_value = []
        await self.monitor.scan_shops(force_ml=True)
        self.assertEqual(json.loads(self.store.get_setting('public_coupons')), [])


class PublishedCouponTests(unittest.TestCase):
    def test_shop_uses_direct_shortened_and_explicit_affiliate_destination_links(self):
        cases = [('https://meli.la/test', 'Mercado Livre'), ('https://amzn.to/test', 'Amazon'),
                 ('https://www.awin1.com/cread.php?ued=https%3A%2F%2Fwww.kabum.com.br%2Foferta', 'KaBuM')]
        for url, expected in cases:
            self.assertEqual(coupon_shop('Pichau também oferece descontos', [url]), expected)
        self.assertEqual(coupon_shop('Cupom sem loja', ['https://example.com']), 'Loja não identificada')
        self.assertEqual(coupon_shop('Cupons Amazon e Pichau', []), 'Pichau · Amazon')
        self.assertEqual(coupon_shop('Cupom', ['https://evil.test/?domain=amazon.com.br']), 'Loja não identificada')

    def test_other_telegram_shops_use_exact_domains_and_can_be_filtered(self):
        self.assertEqual(coupon_shop('', ['https://s.shopee.com.br/6L4u0KrhTT']), 'Shopee')
        self.assertEqual(coupon_shop('', ['https://a.aliexpress.com/_c3IxVuAN']), 'AliExpress')
        self.assertEqual(coupon_shop('', ['https://shopee.com.br.evil.test/test']), 'Loja não identificada')
        post = dict(id=1, message_id=1, codes='["TESTE10"]', text='Cupom TESTE10 https://s.shopee.com.br/test',
                    source='Grupo', published_at=utcnow(), links='[]')
        catalog = coupon_catalog([post], [], [])
        self.assertEqual(coupon_page(catalog, '', 1, 'Shopee')[1], 1)
        self.assertEqual(coupon_page(catalog, '', 1, 'Amazon')[1], 0)

    def html(self):
        return '''<table><tr><td>LOJA</td><td>REGRA</td><td>CUPOM</td><td>LINK</td></tr>
        <tr><td><img></td><td>10% OFF em eletrônicos acima de R$ 149</td><td><b>GPU10</b></td><td><a href="https://www.mercadolivre.com.br/ofertas">aqui</a></td></tr>
        <tr><td></td><td>Produtos selecionados</td><td>Ative no link</td><td><a href="https://www.amazon.com.br/promotion/test">aqui</a></td></tr>
        <tr><td></td><td>Outra loja</td><td>MODA10</td><td><a href="https://example.com">aqui</a></td></tr></table>'''

    def test_public_table_keeps_codes_conditions_activations_and_source(self):
        rows = public_coupons(self.html())
        self.assertEqual(len(rows), 2)
        self.assertEqual((rows[0]['code'], rows[0]['shop']), ('GPU10', 'Mercado Livre'))
        self.assertIn('eletrônicos', rows[0]['conditions'])
        self.assertEqual(rows[0]['source_url'], PUBLIC_COUPONS_URL)
        self.assertTrue(rows[1]['activation'])
        self.assertEqual(rows[1]['code'], '')

    def test_public_parser_rejects_missing_or_unrelated_tables(self):
        for html in ('<h1>Access denied</h1>', '<table></table>', '<table><tr><td>Preço</td></tr></table>'):
            with self.assertRaisesRegex(ValueError, 'tabelas de cupons'):
                public_coupons(html)

    def test_five_column_table_without_shop_heading_keeps_only_active_codes(self):
        html = '''<table><tr><th></th><th>REGRA</th><th>CUPOM</th><th>LINK</th><th>ESTÁ ATIVO?</th></tr>
        <tr><td></td><td>15% em produtos selecionados</td><td>MESA15</td><td><a href="https://www.amazon.com.br/promotion/test">aqui</a></td><td>✅</td></tr>
        <tr><td></td><td>Eletrônicos</td><td>ANTIGO10</td><td><a href="https://www.mercadolivre.com.br/ofertas">aqui</a></td><td>❌</td></tr>
        <tr><td></td><td>Sem confirmação</td><td>TALVEZ10</td><td><a href="https://www.amazon.com.br/promotion/test">aqui</a></td><td>?</td></tr></table>'''
        rows = public_coupons(html)
        self.assertEqual([(row['shop'], row['code']) for row in rows], [('Amazon', 'MESA15')])

    def test_coupon_catalog_hides_expired_web_cache_and_filters_shop(self):
        rows = public_coupons(self.html())
        rows[0]['checked_at'] = (datetime.now(timezone.utc) - timedelta(hours=13)).isoformat()
        catalog = coupon_catalog([], [], rows)
        self.assertEqual(len(catalog), 1)
        self.assertEqual(coupon_page(catalog, 'Amazon', 1, 'Amazon')[1], 1)
        self.assertEqual(coupon_page(catalog, '', 1, 'Mercado Livre')[1], 0)


class PublicCouponFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_uses_fixed_public_page_and_does_not_follow_purchase_links(self):
        shops = Shops()
        await shops.client.aclose()
        urls = []
        def respond(request):
            urls.append(str(request.url))
            return httpx.Response(200, text=PublishedCouponTests().html())
        shops.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            self.assertEqual(len(await shops.public_coupon_list()), 2)
            self.assertEqual(urls, [PUBLIC_COUPONS_URL])
        finally:
            await shops.close()
