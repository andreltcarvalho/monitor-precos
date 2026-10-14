import json
import unittest
from unittest.mock import AsyncMock

from core import matches
from shops import Shops, product_offer, search_links


PART = {'kind': 'custom', 'query': 'Clamper Pocket Fit LCF, 3P, 10 A'}
TITLE = 'Protetor Contra Surto DPS Iclamper Pocket Fit, 3 Pinos, 10A, Preto LCF - 26800'
URL = 'https://www.kabum.com.br/produto/602069/protetor-contra-surto-dps-iclamper-pocket-fit-3-pinos-10a-preto-lcf-26800'


class ClamperIdentificationTests(unittest.TestCase):
    def test_brand_pin_and_current_spellings_identify_same_model(self):
        for title in (TITLE, 'Clamper Pocket Fit LCF 3P 10 Amperes',
                      'iCLAMPER Pocket Fit LCF 3 pinos 10 A Transparente'):
            with self.subTest(title=title):
                self.assertTrue(matches(PART, title))

    def test_other_electrical_variants_and_bundles_are_not_same_model(self):
        for title in ('Clamper Pocket Fit LCF 2P 10A', 'Clamper Pocket Fit LCF 3P 20A',
                      'Clamper Pocket LCF 3P 10A', 'Clamper Pocket Fit 3P 10A',
                      'Clamper Energia Fit LCF 3P 10A', 'Kit 2 Clamper Pocket Fit LCF 3P 10A',
                      'Adaptador para Clamper Pocket Fit LCF 3P 10A'):
            with self.subTest(title=title):
                self.assertFalse(matches(PART, title))

    def test_search_catalogue_filters_variants_and_product_revalidates_model(self):
        rows = [{'code': 602069, 'name': TITLE, 'available': True, 'priceWithDiscount': 39.99},
                {'code': 661783, 'name': 'Clamper Pocket Fit LCF 3 Pinos 20A', 'available': True}]
        html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps({
            'props': {'pageProps': {'data': {'catalogServer': {'data': rows}}}}}) + '</script>'
        self.assertEqual(search_links(html, 'https://www.kabum.com.br/busca/clamper', PART),
                         ['https://www.kabum.com.br/produto/602069/'])
        offer = product_offer(f'<h1>{TITLE}</h1><p>R$ 39,99 no PIX</p>', URL, PART)
        self.assertEqual(offer['pix'], 3999)
        with self.assertRaisesRegex(ValueError, 'não confirmou o modelo'):
            product_offer('<h1>Clamper Pocket Fit LCF 2 Pinos 10A</h1><p>R$ 19,99 no PIX</p>', URL, PART)


class ClamperSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_amazon_browser_verification_is_reported_as_blocked(self):
        shops = Shops()
        try:
            shops.fetch = AsyncMock(return_value=(
                '<meta http-equiv="refresh" content="5; URL=/s?k=clamper&amp;bm-verify=challenge">',
                'https://www.amazon.com.br/s?k=clamper'))
            with self.assertRaisesRegex(ValueError, 'Amazon bloqueou a consulta pública'):
                await shops.discover('Amazon', PART)
        finally:
            await shops.close()

    async def test_discovery_uses_shop_terms_without_editing_saved_query(self):
        shops = Shops()
        try:
            shops.fetch = AsyncMock(return_value=(f'<a href="{URL}">{TITLE}</a>',
                'https://www.kabum.com.br/busca/clamper-pocket-fit-3p-10a'))
            self.assertEqual(await shops.discover('KaBuM', PART), [URL])
            shops.fetch.assert_awaited_once_with('https://www.kabum.com.br/busca/clamper-pocket-fit-3p-10a')
            self.assertEqual(PART['query'], 'Clamper Pocket Fit LCF, 3P, 10 A')
        finally:
            await shops.close()

