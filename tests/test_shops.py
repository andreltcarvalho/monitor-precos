import json
import unittest
from unittest.mock import AsyncMock

import httpx

from shops import Shops, product_offer, search_links, shop_name


class NewShopParsingTests(unittest.TestCase):
    def test_nordwind_fan_discovery_and_product_reading_use_category_alias(self):
        part = {'kind': 'custom', 'query': 'ventoinha nordwind black'}
        title = 'Cooler Para Gabinete Round5 Nordwind Black, ARGB, 120mm, PWM, Preto'
        url = 'https://www.terabyteshop.com.br/produto/41283/cooler-para-gabinete-round5-nordwind-black'
        search = f'<a href="{url}">{title}</a><a href="/produto/41269/kit-fan">Kit Fan Round5 Nordwind Black</a>'
        self.assertEqual(search_links(search, 'https://www.terabyteshop.com.br/busca', part), [url])
        html = f'<div class="AreaInfvlrpdt"><h1>{title}</h1><div><div><span id="valVista">R$ 59,99</span> no Pix</div></div></div>'
        offer = product_offer(html, url, part)
        self.assertEqual(offer['pix'], 5999)
        self.assertEqual(offer['title'], title)

    def test_water_cooler_discovery_reads_pichau_links_and_checks_product_model(self):
        part = {'kind': 'custom', 'query': 'water cooler rise mode 360 argb'}
        title = 'Water Cooler Rise Mode Black 360mm ARGB'
        url = 'https://www.pichau.com.br/water-cooler-rise-mode-360mm-argb'
        html = f'<a href="{url}">{title}</a><a href="/water-cooler-rise-mode-240mm-argb">Water Cooler Rise Mode 240mm ARGB</a>'
        self.assertEqual(search_links(html, 'https://www.pichau.com.br/search', part), [url])
        offer = product_offer(f'<h1>{title}</h1><p>R$ 399,99 no PIX</p>', url, part)
        self.assertEqual(offer['pix'], 39999)

    def test_kabum_search_uses_product_offer_url_and_filters_ti(self):
        items = [dict(**{'@type': 'Product'}, name=name, offers={'url': url}) for name, url in (
            ('MSI RTX 5060', 'https://www.kabum.com.br/produto/123/msi'),
            ('MSI RTX 5060 Ti', 'https://www.kabum.com.br/produto/124/msi-ti'))]
        html = '<script type="application/ld+json">' + json.dumps(items) + '</script>'
        self.assertEqual(search_links(html, 'https://www.kabum.com.br/busca/rtx-5060', {'kind': 'gpu'}),
                         ['https://www.kabum.com.br/produto/123/msi'])

    def kabum_page(self, product_id=123, pix_label=True):
        title = 'Placa de Vídeo MSI RTX 5060'
        product = dict(id=product_id, title=title, sellerName='Parceiro', available=True,
                       prices=dict(price=3294.11, priceWithDiscount=2799.99),
                       installment=dict(installment=10, amount=329.41),
                       crossSellingIds=[456])
        payload = json.dumps({'props': {'pageProps': {'product': product}}})
        label = 'à vista no PIX' if pix_label else 'Preço anunciado'
        return f'<h1>{title}</h1><div>Sobre o produto</div><p>R$ 2.799,99 {label}</p><script id="__NEXT_DATA__">{payload}</script>'

    def test_kabum_product_reads_pix_exact_total_and_seller(self):
        result = product_offer(self.kabum_page(), 'https://www.kabum.com.br/produto/123/msi', {'kind': 'gpu'})
        self.assertEqual((result['pix'], result['card'], result['installments'], result['installment']),
                         (279999, 329411, 10, 32941))
        self.assertEqual((result['shop'], result['seller'], result['availability']), ('KaBuM', 'Parceiro', 'in'))

    def test_kabum_wrong_product_id_cannot_supply_prices(self):
        with self.assertRaises(ValueError):
            product_offer(self.kabum_page(product_id=456), 'https://www.kabum.com.br/produto/123/msi', {'kind': 'gpu'})

    def test_kabum_discount_without_pix_label_is_not_pix(self):
        result = product_offer(self.kabum_page(pix_label=False), 'https://www.kabum.com.br/produto/123/msi', {'kind': 'gpu'})
        self.assertIsNone(result['pix'])
        self.assertEqual(result['card'], 329411)

    def test_amazon_search_discovers_matching_product_links(self):
        html = '<a href="/MSI/dp/B0ABCDEFG1"><h2>MSI RTX 5060</h2></a><a href="/dp/B0ABCDEFG2">MSI RTX 5060 Ti</a>'
        self.assertEqual(search_links(html, 'https://www.amazon.com.br/s?k=rtx', {'kind': 'gpu'}),
                         ['https://www.amazon.com.br/MSI/dp/B0ABCDEFG1'])

    def test_amazon_current_price_scope_excludes_list_and_related_prices(self):
        html = '''<h1><span id="productTitle">MSI RTX 5060</span></h1>
        <div id="corePriceDisplay_desktop_feature_div"><span class="a-price a-text-price"><span class="a-offscreen">R$ 4.000,00</span></span>
        <span class="a-price"><span class="a-offscreen">R$ 2.700,00</span></span></div>
        <a id="sellerProfileTriggerId">Loja parceira</a><div>Produtos relacionados R$ 100,00 no Pix</div>'''
        result = product_offer(html, 'https://www.amazon.com.br/dp/B0ABCDEFG1', {'kind': 'gpu'})
        self.assertEqual(result['announced'], 270000)
        self.assertIsNone(result['pix'])
        self.assertEqual(result['seller'], 'Loja parceira')

    def test_amazon_without_product_price_does_not_confirm_related_price(self):
        with self.assertRaises(ValueError):
            product_offer('<h1>MSI RTX 5060</h1><p>Outra placa R$ 99,00 no Pix</p>',
                          'https://www.amazon.com.br/dp/B0ABCDEFG1', {'kind': 'gpu'})

    def test_amazon_structured_price_does_not_take_pix_from_related_text(self):
        html = '''<h1>MSI RTX 5060</h1><script type="application/ld+json">
        {"@type":"Product","name":"MSI RTX 5060","offers":{"price":2700}}</script>
        <p>Outros produtos R$ 99,00 no Pix</p>'''
        result = product_offer(html, 'https://www.amazon.com.br/dp/B0ABCDEFG1', {'kind': 'gpu'})
        self.assertEqual(result['announced'], 270000)
        self.assertIsNone(result['pix'])

    def test_new_shop_short_links_are_identified(self):
        self.assertEqual(shop_name('https://amzn.to/example'), 'Amazon')
        self.assertEqual(shop_name('https://www.kabum.com.br/produto/123'), 'KaBuM')


class NewShopFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_kabum_water_cooler_search_adds_size_unit_without_changing_component(self):
        shops = Shops()
        try:
            for query in ('water cooler rise mode 360 argb', 'water cooler rise mode 360mm argb'):
                part = {'kind': 'custom', 'query': query}
                product = 'https://www.kabum.com.br/produto/123/water-cooler'
                search = 'https://www.kabum.com.br/busca/water-cooler-rise-mode-360mm-argb'
                shops.fetch = AsyncMock(return_value=(f'<a href="{product}">Water Cooler Rise Mode 360mm ARGB</a>', search))
                self.assertEqual(await shops.discover('KaBuM', part), [product])
                shops.fetch.assert_awaited_once_with(search)
                self.assertEqual(part['query'], query)
            shops.fetch = AsyncMock(return_value=('<a href="https://www.kabum.com.br/produto/456/gpu">MSI RTX 5060</a>', 'https://www.kabum.com.br/busca/rtx-5060'))
            await shops.discover('KaBuM', {'kind': 'gpu', 'query': 'rtx 5060'})
            shops.fetch.assert_awaited_once_with('https://www.kabum.com.br/busca/rtx-5060')
        finally:
            await shops.close()

    async def test_amazon_503_is_explicit_and_does_not_produce_offer(self):
        shops = Shops()
        await shops.client.aclose()
        shops.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
        try:
            with self.assertRaisesRegex(ValueError, '503'):
                await shops.discover('Amazon', {'query': 'rtx 5060', 'kind': 'gpu'})
        finally:
            await shops.close()

    async def test_amazon_captcha_is_not_a_product_result(self):
        shops = Shops()
        shops.fetch = AsyncMock(return_value=('<h1>Digite os caracteres</h1>', 'https://www.amazon.com.br/s?k=rtx'))
        try:
            with self.assertRaisesRegex(ValueError, 'bloqueou'):
                await shops.discover('Amazon', {'query': 'rtx 5060', 'kind': 'gpu'})
        finally:
            await shops.close()

    async def test_amazon_short_link_resolves_only_to_supported_store(self):
        seen = []
        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(302, headers={'location': 'https://www.amazon.com.br/dp/B0ABCDEFG1'}) if request.url.host == 'amzn.to' else httpx.Response(200, text='produto')
        shops = Shops()
        await shops.client.aclose()
        shops.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            _, url = await shops.fetch('https://amzn.to/example')
            self.assertEqual(url, 'https://www.amazon.com.br/dp/B0ABCDEFG1')
            self.assertEqual(len(seen), 2)
        finally:
            await shops.close()
