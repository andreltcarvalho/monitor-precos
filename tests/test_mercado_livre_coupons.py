import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core import Store, group_offers, utcnow
from monitor import Monitor
from presentation import group_caption, offer_card_data
from shops import product_offer


URL = 'https://www.mercadolivre.com.br/ssd-kingston-nv3/p/MLB2058578787'
TITLE = 'SSD Kingston NV3 1TB M.2 2280 PCIe 4.0'
PART = {'id': 3, 'kind': 'ssd', 'capacity_gb': 1000}
LABEL = '<span class="ui-vpp-coupons-awareness__checkbox-label">{text}</span>'


def page(label='R$ 753 , 23 com Cupom', extra=''):
    structured = json.dumps({'@type': 'Product', 'name': TITLE,
                             'offers': {'price': 836.92, 'availability': 'https://schema.org/InStock'}})
    return (f'<h1>{TITLE}</h1><script type="application/ld+json">{structured}</script>'
            f'<p>R$ 836,92</p>{LABEL.format(text=label) if label else ""}{extra}'
            '<form class="ui-pdp-buybox">Chegará grátis amanhã</form>')


class CouponParsingTests(unittest.TestCase):
    def test_real_split_currency_keeps_base_and_coupon_separate(self):
        offer = product_offer(page(), URL, PART)
        self.assertEqual(offer['announced'], 83692)
        self.assertEqual(offer['coupon_price'], 75323)
        self.assertIsNone(offer['pix'])
        self.assertIsNone(offer['card'])
        self.assertEqual(offer['coupons'], [])

    def test_currency_split_across_elements_is_read(self):
        html = page('<span>R$</span><span>753</span><span>,</span><span>23</span><span>com Cupom</span>')
        self.assertEqual(product_offer(html, URL, PART)['coupon_price'], 75323)

    def test_discount_amount_percent_and_invalid_price_are_not_coupon_prices(self):
        for label in ('10% OFF com Cupom', 'R$ 83,69 de desconto', 'R$ 0,00 com Cupom',
                      'R$ 900,00 com Cupom', 'R$ 836,92 com Cupom'):
            with self.subTest(label=label):
                self.assertIsNone(product_offer(page(label), URL, PART)['coupon_price'])

    def test_related_product_and_generic_coupon_text_are_not_used(self):
        related = '<h2>Produtos relacionados</h2>' + LABEL.format(text='R$ 50,00 com Cupom')
        for html in (page(None, related), page(None, '<p>R$ 50,00 com Cupom</p>')):
            self.assertIsNone(product_offer(html, URL, PART)['coupon_price'])

    def test_hidden_coupon_is_not_available_in_session(self):
        for marker in ('hidden', 'style="visibility: hidden"', 'style="display: none"'):
            html = page(None, f'<div {marker}>{LABEL.format(text="R$ 753,23 com Cupom")}</div>')
            with self.subTest(marker=marker):
                self.assertIsNone(product_offer(html, URL, PART)['coupon_price'])

    def test_visible_label_hidden_only_from_screen_readers_is_still_a_coupon(self):
        html = page().replace('class="ui-vpp-coupons-awareness__checkbox-label"',
                              'aria-hidden="true" class="ui-vpp-coupons-awareness__checkbox-label"')
        self.assertEqual(product_offer(html, URL, PART)['coupon_price'], 75323)

    def test_other_stores_do_not_use_mercado_livre_coupon_markup(self):
        offer = product_offer(page(), 'https://www.pichau.com.br/ssd-kingston-nv3', PART)
        self.assertIsNone(offer['coupon_price'])

    def test_mercado_pago_ad_does_not_replace_product_total_or_coupon(self):
        box = ('<div class="ui-pdp-price">R$ 1.230 , 77 R$ 836 , 92 32% OFF '
               '12x R$ 80 , 65 com outros cartões Crédito disponível: parcelado sem cartão '
               'Cartão de Crédito Mercado Pago R$ 100 OFF Até 3% de cashback</div>')
        offer = product_offer(page(extra=box), URL, PART)
        self.assertEqual(offer['announced'], 83692)
        self.assertEqual(offer['card'], 96780)
        self.assertEqual(offer['installment'], 8065)
        self.assertEqual(offer['coupon_price'], 75323)
        self.assertEqual(offer_card_data(offer)['amount'], 'R$ 836,92')

    def test_structured_product_without_payment_block_does_not_use_credit_ads(self):
        offer = product_offer(page(extra='<p>Cartão de Crédito Mercado Pago R$ 100 no cartão</p>'), URL, PART)
        self.assertEqual(offer['announced'], 83692)
        self.assertIsNone(offer['card'])


class CouponCatalogTests(unittest.TestCase):
    def offer(self, number, base, coupon=None, **changes):
        return dict(id=number, component_id=3, shop='Mercado Livre', title=TITLE,
                    announced=base, coupon_price=coupon, shipping_origin='local', **changes)

    def test_coupon_changes_order_before_pagination_without_replacing_base(self):
        offers = [self.offer(1, 80000), self.offer(2, 83692, 75323), self.offer(3, 90000)]
        rows = group_offers([PART], offers)[3]
        self.assertEqual([row['id'] for row in rows], [2, 1, 3])
        self.assertEqual(rows[0]['announced'], 83692)
        self.assertEqual([row['id'] for row in offers], [1, 2, 3])

    def test_duplicate_selection_uses_coupon_and_preserves_original_ids(self):
        offers = [self.offer(1, 80000, seller='Loja'), self.offer(2, 83692, 75323, seller='Loja')]
        rows = group_offers([PART], offers)[3]
        self.assertEqual(rows[0]['id'], 2)
        self.assertEqual(set(rows[0]['duplicate_ids']), {1, 2})

    def test_card_and_group_caption_identify_coupon_condition(self):
        offer = self.offer(2, 83692, 75323)
        card = offer_card_data(offer)
        self.assertEqual(card['amount'], 'R$ 836,92')
        self.assertEqual(card['coupon_amount'], 'R$ 753,23')
        self.assertEqual(card['payment'], 'pagamento não informado')
        self.assertIn('R$ 753,23 · com cupom na sua sessão', group_caption(PART, [offer]))

    def test_cheaper_pix_remains_first_even_when_coupon_exists(self):
        offer = self.offer(2, 83692, 75323, pix=70000)
        other = self.offer(1, 72000)
        self.assertEqual(group_offers([PART], [other, offer])[3][0]['id'], 2)
        self.assertIn('R$ 700,00 · no Pix', group_caption(PART, [other, offer]))

    def test_zero_or_negative_coupon_does_not_promote_offer(self):
        for coupon in (0, -1):
            offers = [self.offer(1, 80000), self.offer(2, 83692, coupon)]
            with self.subTest(coupon=coupon):
                self.assertEqual(group_offers([PART], offers)[3][0]['id'], 1)
                self.assertEqual(offer_card_data(offers[1])['coupon_amount'], '')


class CouponPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'monitor.sqlite3'
        self.store = Store(self.path)
        self.monitor = Monitor(self.store, Path(self.temp.name))

    async def asyncTearDown(self):
        await self.monitor.shops.close()
        self.store.close()
        self.temp.cleanup()

    def save(self, offer):
        return self.store.upsert_offer(3, offer, {'source': 'Mercado Livre', 'published_at': utcnow()})[0]

    async def test_price_survives_restart_and_is_removed_after_coupon_disappears(self):
        row = self.save(product_offer(page(), URL, PART))
        await self.monitor.shops.close()
        self.store.close()
        self.store = Store(self.path)
        self.monitor = Monitor(self.store, Path(self.temp.name))
        self.assertEqual(self.store.offer(row['id'])['coupon_price'], 75323)
        self.save(product_offer(page(None), URL, PART))
        updated = self.store.offer(row['id'])
        self.assertIsNone(updated['coupon_price'])
        self.assertEqual(updated['announced'], 83692)

    async def test_manual_check_updates_and_clears_coupon_price(self):
        row = self.save(product_offer(page(None), URL, PART))
        self.monitor.shops.check = AsyncMock(return_value=product_offer(page(), URL, PART))
        with patch.object(self.monitor, 'alert', new=AsyncMock()):
            await self.monitor.check_offer(row['id'])
            self.assertEqual(self.store.offer(row['id'])['coupon_price'], 75323)
            self.monitor.shops.check.return_value = product_offer(page(None), URL, PART)
            await self.monitor.check_offer(row['id'])
        self.assertIsNone(self.store.offer(row['id'])['coupon_price'])

    async def test_migration_preserves_existing_offer_and_history(self):
        row = self.save(product_offer(page(None), URL, PART))
        before = len(self.store.rows('SELECT * FROM observations'))
        await self.monitor.shops.close()
        self.store.db.execute('ALTER TABLE offers DROP COLUMN coupon_price')
        self.store.db.commit()
        self.store.close()
        self.store = Store(self.path)
        self.monitor = Monitor(self.store, Path(self.temp.name))
        self.assertIsNone(self.store.offer(row['id'])['coupon_price'])
        self.assertEqual(self.store.offer(row['id'])['announced'], 83692)
        self.assertEqual(len(self.store.rows('SELECT * FROM observations')), before)
