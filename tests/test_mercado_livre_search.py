import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core import Store, effective_price, utcnow
from monitor import Monitor
from shops import Shops, mercado_livre_search_candidates


SEARCH = 'https://lista.mercadolivre.com.br/rtx-5060'
LOCAL = SEARCH + '_SHIPPING*ORIGIN_10215068'
URL = 'https://www.mercadolivre.com.br/msi-rtx-5060/p/MLB123'
PART = dict(id=1, kind='gpu', query='rtx 5060')


def amount(value):
    return (f'<span class="andes-money-amount"><span class="andes-money-amount__currency-symbol">R$</span>'
            f'<span class="andes-money-amount__fraction">{value // 100:,}'.replace(',', '.') + '</span>'
            f'<span class="andes-money-amount__cents">{value % 100:02}</span></span>')


def card(value=250000, coupon=230000, url=URL, title='MSI RTX 5060', extra='', payment=''):
    return (f'<li class="ui-search-layout__item"><a class="poly-component__title" href="{url}">{title}</a>'
            '<span class="poly-component__seller">Loja A</span><s>R$ 8.000</s>'
            f'<div class="poly-price__current">{amount(value)}{payment}</div>'
            f'<span class="poly-price__installments">10x {amount(28000)} sem juros</span>'
            '<div class="poly-component__rebates">20% OFF com Saldo no Mercado Pago</div>'
            f'<span class="poly-coupons__pill">{amount(coupon)} com Cupom</span>{extra}</li>')


class SearchParsingTests(unittest.TestCase):
    def read(self, html, url=LOCAL, part=PART):
        return mercado_livre_search_candidates(html, url, part)

    def test_current_price_coupon_installments_and_alternative_are_separate(self):
        extra = ('<div class="poly-component__buy-box">Outra opção de compra R$ 100'
                 '<span class="poly-price__installments">12x R$ 1</span></div>')
        reading = self.read(card(value=463900, coupon=443900, extra=extra))[0]['reading']
        self.assertEqual(reading['announced'], 463900)
        self.assertEqual(reading['coupon_price'], 443900)
        self.assertEqual(effective_price(reading), 443900)
        self.assertEqual((reading['card'], reading['installments'], reading['installment']), (280000, 10, 28000))
        self.assertIsNone(reading['pix'])
        self.assertEqual(reading['seller'], 'Loja A')
        self.assertEqual(reading['brand'], 'MSI')

    def test_alternative_installments_do_not_fill_missing_main_installments(self):
        html = card(extra='<div class="poly-component__buy-box"><span class="poly-price__installments">12x R$ 1</span></div>')
        html = html.replace(f'<span class="poly-price__installments">10x {amount(28000)} sem juros</span>', '')
        self.assertIsNone(self.read(html)[0]['reading']['card'])

    def test_split_cents_and_explicit_pix(self):
        reading = self.read(card(275999, 255999, payment=' no Pix'))[0]['reading']
        self.assertEqual(reading['announced'], 275999)
        self.assertEqual(reading['pix'], 275999)
        self.assertEqual(reading['coupon_price'], 255999)

    def test_hidden_invalid_or_conditional_discounts_are_not_coupon_prices(self):
        for coupon in (250000, 260000, 0):
            self.assertIsNone(self.read(card(coupon=coupon))[0]['reading']['coupon_price'])
        for attribute in ('hidden', 'aria-hidden="true"', 'style="display:none"'):
            html = card().replace('<span class="poly-coupons__pill">', f'<span class="poly-coupons__pill" {attribute}>')
            self.assertIsNone(self.read(html)[0]['reading']['coupon_price'])
        html = card().replace('com Cupom', 'com Saldo no Mercado Pago')
        self.assertIsNone(self.read(html)[0]['reading']['coupon_price'])
        html = card().replace('com Cupom', 'OFF na compra com Cupom')
        self.assertIsNone(self.read(html)[0]['reading']['coupon_price'])

    def test_local_filter_is_required_and_international_cards_are_skipped(self):
        self.assertEqual(self.read(card(), SEARCH)[0]['reading']['shipping_origin'], 'unknown')
        self.assertEqual(self.read(card())[0]['reading']['shipping_origin'], 'local')
        for marker in ('Internacional', 'Compra internacional', 'Envio da China', 'Produto do exterior'):
            self.assertEqual(self.read(card(extra=marker)), [])

    def test_component_and_ignored_brand_filters_are_preserved(self):
        self.assertEqual(self.read(card(title='MSI RTX 5060 Ti')), [])
        self.assertEqual(self.read(card(), part=dict(PART, ignored_brands=['MSI'])), [])

    def test_selects_twelve_cheapest_after_reading_all_cards_with_coupon(self):
        html = ''.join(card(value=300000 + index * 1000, coupon=290000 + index * 1000,
                            url=URL.replace('123', str(1000 + index))) for index in range(15))
        cheap = URL.replace('123', '9999')
        result = self.read(html + card(400000, 100000, url=cheap))
        self.assertEqual(len(result), 12)
        self.assertEqual(result[0]['url'], cheap)
        self.assertEqual(result[-1]['reading']['announced'], 310000)

    def test_missing_price_and_unrecognized_layout_remain_product_candidates(self):
        html = f'<li class="ui-search-layout__item"><a class="poly-component__title" href="{URL}">MSI RTX 5060</a></li>'
        for layout in (html, f'<a href="{URL}">MSI RTX 5060</a>'):
            self.assertEqual(self.read(layout), [dict(url=URL, reading=None)])


class SearchDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_real_local_filter_and_does_not_fetch_each_product(self):
        shops = Shops()
        shops.fetch = AsyncMock(side_effect=[(f'<a href="{LOCAL}">Local</a>', SEARCH), (card(), LOCAL)])
        try:
            result = await shops.discover_mercado_livre(PART)
            self.assertEqual(result[0]['reading']['coupon_price'], 230000)
            self.assertEqual([call.args[0] for call in shops.fetch.await_args_list], [SEARCH, LOCAL])
        finally:
            await shops.close()

    async def test_login_failure_is_not_an_empty_catalog(self):
        shops = Shops()
        shops.fetch = AsyncMock(side_effect=ValueError('Mercado Livre exigiu login'))
        try:
            with self.assertRaisesRegex(ValueError, 'login'):
                await shops.discover_mercado_livre(PART)
        finally:
            await shops.close()


class SearchMonitorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'monitor.sqlite3')
        self.monitor = Monitor(self.store, Path(self.temp.name))
        self.store.db.execute('UPDATE components SET enabled=(id=1),target=NULL')
        self.store.db.commit()
        for shop in ('Pichau', 'KaBuM', 'Amazon', 'Shopee', 'Terabyte Shop'):
            self.store.set_setting('shop:' + shop, '0')
        self.monitor.shops.check = AsyncMock()
        self.monitor.shops.discover_mercado_livre = AsyncMock()
        self.monitor.alert = AsyncMock()

    async def asyncTearDown(self):
        await self.monitor.shops.close()
        self.store.close()
        self.temp.cleanup()

    async def scan(self, html=card(), base=LOCAL):
        self.monitor.shops.discover_mercado_livre.return_value = mercado_livre_search_candidates(html, base, PART)
        with patch('monitor.asyncio.sleep', new=AsyncMock()):
            await self.monitor.scan_shops(component_id=1)

    async def test_complete_search_reading_is_saved_and_manual_check_still_reads_product(self):
        await self.scan()
        self.monitor.shops.check.assert_not_awaited()
        row = self.store.offers()[0]
        self.assertEqual(row['coupon_price'], 230000)
        self.assertIsNotNone(row['valid_until'])
        self.monitor.alert.assert_awaited_once()
        self.monitor.shops.check.return_value = dict(row, announced=240000, coupon_price=220000)
        await self.monitor.check_offer(row['id'])
        self.monitor.shops.check.assert_awaited_once_with(row['url'], self.store.components()[0])
        self.assertEqual(self.store.offer(row['id'])['coupon_price'], 220000)

    async def test_missing_origin_or_price_uses_product_and_preserves_data_on_failure(self):
        await self.scan()
        for html, base in ((card(), SEARCH), (f'<a href="{URL}">MSI RTX 5060</a>', LOCAL)):
            self.monitor.shops.check.reset_mock()
            self.monitor.shops.check.side_effect = ValueError('Produto indisponível para leitura')
            await self.scan(html, base)
            self.monitor.shops.check.assert_awaited_once()
            self.assertEqual(len(self.store.offers()), 1)
            self.assertEqual(self.store.offers()[0]['announced'], 250000)
            self.assertIsNone(self.store.offers()[0]['valid_until'])

    async def test_target_payment_requires_explicit_price_and_card_uses_total(self):
        self.store.db.execute("UPDATE components SET target=300000,target_payment='pix' WHERE id=1")
        self.store.db.commit()
        self.monitor.shops.check.side_effect = ValueError('Sem Pix informado')
        await self.scan()
        self.monitor.shops.check.assert_awaited_once()
        self.monitor.shops.check.reset_mock()
        await self.scan(card(payment=' no Pix'))
        self.monitor.shops.check.assert_not_awaited()
        self.store.db.execute("UPDATE components SET target_payment='card' WHERE id=1")
        self.store.db.commit()
        await self.scan()
        self.monitor.shops.check.assert_not_awaited()
        self.assertEqual(self.store.offers()[0]['card'], 280000)

    async def test_fresh_search_price_can_restore_known_offer_outside_twelve_cutoff(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        for index in range(12):
            reading = mercado_livre_search_candidates(card(value=150000 + index * 1000, coupon=140000 + index * 1000,
                                                        url=URL.replace('123', str(1000 + index)),
                                                        title=f'MSI RTX 5060 modelo {index}'), LOCAL, PART)[0]['reading']
            self.store.upsert_offer(1, reading, dict(source='Mercado Livre', published_at=utcnow()))
        expensive = mercado_livre_search_candidates(card(), LOCAL, PART)[0]['reading']
        expensive.update(checked_at=old, received_at=old)
        row = self.store.upsert_offer(1, expensive, dict(source='Mercado Livre', published_at=old))[0]
        self.assertFalse(self.store.should_track_offer(row))
        await self.scan(card(value=130000, coupon=120000))
        self.monitor.shops.check.assert_not_awaited()
        self.assertEqual(self.store.offer(row['id'])['coupon_price'], 120000)
        self.assertTrue(self.store.should_track_offer(self.store.offer(row['id'])))
        self.assertEqual(len(self.store.rows('SELECT * FROM observations WHERE offer_id=?', (row['id'],))), 2)

    async def test_new_expensive_candidate_does_not_open_product_above_twelve_cutoff(self):
        for index in range(12):
            reading = mercado_livre_search_candidates(card(value=150000 + index * 1000, coupon=140000 + index * 1000,
                                                        url=URL.replace('123', str(1000 + index)),
                                                        title=f'MSI RTX 5060 modelo {index}'), LOCAL, PART)[0]['reading']
            self.store.upsert_offer(1, reading, dict(source='Mercado Livre', published_at=utcnow()))
        await self.scan(card(), SEARCH)
        self.monitor.shops.check.assert_not_awaited()
        self.assertEqual(len(self.store.offers()), 12)
