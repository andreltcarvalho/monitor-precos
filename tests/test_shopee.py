import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from shops import Shops, coupon_shop, product_offer, search_links, shop_name
from shopee_browser import ShopeeBrowser, validate_shopee_page


PART = {'kind': 'custom', 'query': 'water cooler rise mode 360 argb'}
URL = 'https://shopee.com.br/Water-Cooler-i.123.456'
TITLE = 'Water Cooler Rise Mode 360mm ARGB'


def product(offers):
    return f'<h1>{TITLE}</h1><script type="application/ld+json">' + json.dumps(
        {'@type': 'Product', 'name': TITLE, 'offers': offers}) + '</script>'


class ShopeeParsingTests(unittest.TestCase):
    def test_domains_and_short_links_identify_shopee_without_accepting_lookalikes(self):
        for url in (URL, 'https://s.shopee.com.br/example', 'https://shope.ee/example', 'https://www.shopee.com.br/product/123/456'):
            self.assertEqual(shop_name(url), 'Shopee')
            self.assertEqual(coupon_shop('', [url]), 'Shopee')
        self.assertNotEqual(shop_name('https://shopee.com.br.evil.test/product/1/2'), 'Shopee')

    def test_search_links_only_return_matching_products_up_to_twelve(self):
        html = ''.join(f'<a href="/Water-Cooler-i.123.{number}">{TITLE}</a>' for number in range(20))
        html += '<a href="/search?keyword=water">Water Cooler Rise Mode 360mm ARGB</a><a href="/product/3/4">Water Cooler Rise Mode 240mm ARGB</a>'
        found = search_links(html, 'https://shopee.com.br/search', PART)
        self.assertEqual(len(found), 12)
        self.assertEqual(found[0], 'https://shopee.com.br/Water-Cooler-i.123.0')

    def test_session_search_reads_other_models_but_requires_a_product_title(self):
        html = '<a href="/product/1/2"><img alt="SSD Kingston 480GB"></a>'
        html += '<a href="/product/1/3"></a><a href="/search">SSD Kingston</a>'
        self.assertEqual(search_links(html, 'https://shopee.com.br/search', None), ['https://shopee.com.br/product/1/2'])
        self.assertEqual(search_links(html, 'https://shopee.com.br/search', PART), [])

    def test_structured_price_stock_and_seller_do_not_infer_pix_or_related_discount(self):
        html = product({'price': '299.99', 'priceCurrency': 'BRL', 'availability': 'https://schema.org/InStock', 'seller': {'name': 'Loja da peça'}})
        offer = product_offer(html + '<p>Outra placa R$ 10,00 no Pix</p>', URL, PART)
        self.assertEqual((offer['announced'], offer['pix'], offer['seller'], offer['availability']), (29999, None, 'Loja da peça', 'in'))

    def test_price_range_missing_price_and_foreign_currency_do_not_confirm(self):
        for offers in ({'lowPrice': 199, 'highPrice': 399}, {}, {'price': 30, 'priceCurrency': 'USD'}, {'price': 0}):
            with self.subTest(offers=offers), self.assertRaises(ValueError):
                product_offer(product(offers), URL, PART)
        self.assertEqual(product_offer(product({'lowPrice': 300, 'highPrice': 300}), URL, PART)['announced'], 30000)

    def test_wrong_model_and_unstructured_related_price_are_rejected(self):
        with self.assertRaises(ValueError):
            product_offer(product({'price': 300}).replace('360mm', '240mm'), URL, PART)
        with self.assertRaises(ValueError):
            product_offer(f'<h1>{TITLE}</h1><p>Recomendado R$ 10,00 no Pix</p>', URL, PART)

    def test_login_and_human_verification_are_explicit_and_url_is_restricted(self):
        for html, marker in (('<p>Login Necessário</p>', 'login'), ('<p>Verificação de segurança</p>', 'humana')):
            with self.assertRaisesRegex(ValueError, marker):
                validate_shopee_page(html, URL)
        for url in ('http://shopee.com.br/product/1/2', 'https://example.com', 'https://shopee.com.br:444/product/1/2'):
            with self.assertRaisesRegex(ValueError, 'HTTPS'):
                validate_shopee_page('', url)

    def test_retry_later_block_is_not_reported_as_missing_products_or_login(self):
        html = '<h1>Tente Novamente Mais Tarde</h1><script type="application/ld+json">{}</script>'
        with self.assertRaisesRegex(ValueError, 'bloqueou a consulta automática'):
            validate_shopee_page(html, 'https://shopee.com.br/search')
        with self.assertRaisesRegex(ValueError, 'Não é ausência de peças'):
            product_offer(html, URL, PART)

    def test_verification_redirect_is_detected_before_the_page_text_loads(self):
        with self.assertRaisesRegex(ValueError, 'bloqueou a consulta automática'):
            validate_shopee_page('<script type="application/ld+json">{}</script>', 'https://shopee.com.br/verify/captcha?redirect=search')


class ShopeeSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.profile = Path(self.temp.name) / 'shopee'
        self.browser = ShopeeBrowser(self.profile)

    async def asyncTearDown(self):
        await self.browser.close()
        self.temp.cleanup()

    async def test_unconfigured_or_pending_session_does_not_launch_a_browser(self):
        with patch.object(self.browser, '_read') as read:
            with self.assertRaisesRegex(ValueError, 'login necessário'):
                await self.browser.fetch(URL)
            self.browser.configured = True
            self.browser.login_open = True
            with self.assertRaisesRegex(ValueError, 'login necessário'):
                await self.browser.fetch(URL)
            read.assert_not_called()

    async def test_confirmation_before_opening_login_does_not_launch_chrome(self):
        with patch.object(self.browser, '_read') as read, self.assertRaisesRegex(ValueError, 'Abra a sessão'):
            await self.browser.confirm(PART)
        read.assert_not_called()

    async def test_browser_http_block_and_foreign_navigation_do_not_supply_prices(self):
        context = MagicMock()
        page = MagicMock()
        page.is_closed.return_value = False
        page.goto.return_value.status = 403
        context.pages = [page]
        self.browser._context = context
        with self.assertRaisesRegex(ValueError, '403'):
            self.browser._read(URL)
        page.content.assert_not_called()
        route = MagicMock()
        route.request.url = 'https://example.com/private'
        route.request.is_navigation_request.return_value = True
        route.request.frame = page.main_frame
        page.route.call_args.args[1](route)
        route.abort.assert_called_once()
        route.continue_.assert_not_called()

    async def test_login_opens_normal_chrome_with_own_profile_and_persists_pending(self):
        process = MagicMock()
        process.poll.return_value = None
        with patch('shopee_browser.protect_data_dir', side_effect=lambda path: path.mkdir()), patch('shopee_browser.chrome_executable', return_value='chrome.exe'), patch('shopee_browser.subprocess.Popen', return_value=process) as spawn:
            await self.browser.open_login()
        args = spawn.call_args.args[0]
        self.assertIn('--user-data-dir=' + str(self.profile.resolve()), args)
        self.assertEqual(args[-1], 'https://shopee.com.br/buyer/login')
        self.assertTrue(self.browser.login_open)
        self.assertTrue((self.profile / 'login-pending').exists())
        with patch.object(self.browser, '_read') as read, self.assertRaisesRegex(ValueError, 'Feche'):
            await self.browser.confirm(PART)
        read.assert_not_called()

    async def test_confirmation_requires_readable_search_and_retains_pending_on_failure(self):
        self.profile.mkdir()
        (self.profile / 'login-pending').write_text('1')
        self.browser.login_open = True
        with patch.object(self.browser, '_read', return_value=('<h1>Sem resultados</h1>', 'https://shopee.com.br/search')):
            with self.assertRaisesRegex(ValueError, 'produtos legíveis'):
                await self.browser.confirm(PART)
        self.assertFalse(self.browser.configured)
        self.assertTrue((self.profile / 'login-pending').exists())
        with patch.object(self.browser, '_read', return_value=(f'<a href="{URL}">{TITLE}</a>', 'https://shopee.com.br/search')):
            await self.browser.confirm(PART)
        self.assertTrue(self.browser.configured)
        self.assertFalse(self.browser.login_open)
        self.assertTrue((self.profile / 'monitor-enabled').exists())
        self.assertFalse((self.profile / 'login-pending').exists())

    async def test_confirmation_does_not_require_matching_the_first_piece(self):
        self.profile.mkdir()
        self.browser.login_open = True
        html = '<a href="/product/1/2">SSD Kingston 480GB</a>'
        with patch.object(self.browser, '_read', return_value=(html, 'https://shopee.com.br/search')) as read:
            await self.browser.confirm(PART)
        self.assertEqual(read.call_count, 1)
        self.assertTrue(self.browser.configured)
        self.assertFalse(self.browser.login_open)

    async def test_empty_piece_search_uses_broad_search_to_confirm_session(self):
        self.profile.mkdir()
        self.browser.login_open = True
        pages = [('<h1>Nenhum resultado</h1>', 'https://shopee.com.br/search'),
                 ('<a href="/product/1/2">SSD Kingston 480GB</a>', 'https://shopee.com.br/search')]
        with patch.object(self.browser, '_read', side_effect=pages) as read:
            await self.browser.confirm(PART)
        self.assertEqual(read.call_args.args[0], 'https://shopee.com.br/search?keyword=ssd')
        self.assertTrue(self.browser.configured)

    async def test_unloaded_or_foreign_products_do_not_confirm_or_retry_login(self):
        self.profile.mkdir()
        self.browser.login_open = True
        for html in ('<a href="/product/1/2"></a>',
                     '<a href="https://www.pichau.com.br/ssd-kingston">SSD Kingston</a>'):
            with patch.object(self.browser, '_read', return_value=(html, 'https://shopee.com.br/search')) as read:
                with self.assertRaisesRegex(ValueError, 'não carregou uma busca'):
                    await self.browser.confirm(PART)
            self.assertEqual(read.call_count, 1)
            self.assertFalse(self.browser.configured)
            self.assertTrue(self.browser.login_open)

    async def test_blocked_search_never_confirms_or_falls_back_to_another_query(self):
        self.profile.mkdir()
        self.browser.login_open = True
        for html, url, marker in (('<h1>Login Necessário</h1>', 'https://shopee.com.br/search', 'exige login'),
                                  ('<h1>Tente Novamente Mais Tarde</h1>', 'https://shopee.com.br/search', 'bloqueou'),
                                  ('', 'https://shopee.com.br/verify/captcha', 'bloqueou')):
            with patch.object(self.browser, '_read', return_value=(html, url)) as read:
                with self.assertRaisesRegex(ValueError, marker):
                    await self.browser.confirm(PART)
            self.assertEqual(read.call_count, 1)
            self.assertFalse(self.browser.configured)
            self.assertTrue(self.browser.login_open)

    async def test_fetch_failure_keeps_session_and_reports_diagnosis(self):
        self.browser.configured = True
        with patch.object(self.browser, '_read', side_effect=ValueError('Shopee recusou a consulta (403).')):
            with self.assertRaisesRegex(ValueError, '403'):
                await self.browser.fetch(URL)
        self.assertTrue(self.browser.configured)
        self.assertIn('403', self.browser.status)

    async def test_shop_routes_main_domain_to_browser_and_restricts_short_redirect(self):
        shops = Shops(Path(self.temp.name))
        try:
            shops.shopee_browser.fetch = AsyncMock(return_value=(product({'price': 300}), URL))
            await shops.client.aclose()
            shops.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(302, headers={'location': URL})))
            offer = await shops.check('https://s.shopee.com.br/example', PART)
            shops.shopee_browser.fetch.assert_awaited_once_with(URL)
            self.assertEqual(offer['shop'], 'Shopee')
            shops.shopee_browser.fetch.reset_mock()
            await shops.client.aclose()
            shops.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(302, headers={'location': 'https://example.com/private'})))
            with self.assertRaises(ValueError):
                await shops.fetch('https://shope.ee/example')
            shops.shopee_browser.fetch.assert_not_awaited()
        finally:
            await shops.close()
