import unittest

import httpx

from shops import Shops, coupon_shop, product_offer, search_links, shop_name


URL = 'https://www.terabyteshop.com.br/produto/42569/msi-rtx-5060'
PART = {'kind': 'gpu', 'query': 'rtx 5060'}
TITLE = 'Placa de Vídeo MSI RTX 5060 Cyclone OC, 8GB'


def product(pix=True, stock='Pronta entrega'):
    label = 'à vista com 15% de desconto no Pix' if pix else 'Preço anunciado'
    return f'''<div class="AreaInfvlrpdt"><h1>{TITLE}</h1>
        <span class="vendPor">Vendido por: <span>TerabyteShop</span></span>
        <ul class="prodCond"><li>{stock}</li></ul>
        <div><p class="precode">De: R$ 4.979,90 por:</p>
          <div class="preco-linha"><p id="valVista">R$ 2.749,99</p></div><p>{label}</p></div>
        <p class="val-parc"><span id="valParc">R$ 3.235,28</span> em até
          <span>12x</span> de <span>R$ 269,61</span> sem juros no cartão</p>
        <div id="verparcelamento">1 x de R$ 2.911,75; 18 x de R$ 197,71</div></div>
        <h2>Produtos relacionados</h2><p>Outra placa R$ 10,00 no Pix</p>'''


class TerabyteParsingTests(unittest.TestCase):
    def test_store_and_coupons_identify_exact_domains_and_store_aliases(self):
        for url in (URL, 'https://terabyteshop.com.br/produto/123'):
            self.assertEqual(shop_name(url), 'Terabyte Shop')
            self.assertEqual(coupon_shop('', [url]), 'Terabyte Shop')
        for text in ('Terabyte', 'TerabyteShop', 'TERABYTE SHOP'):
            self.assertEqual(coupon_shop(text, []), 'Terabyte Shop')
        self.assertNotEqual(shop_name('https://terabyteshop.com.br.evil.test/produto/123'), 'Terabyte Shop')

    def test_search_matches_product_links_without_duplicates_or_other_models(self):
        html = ''.join(f'<a href="/produto/{number}/rtx-5060" title="{TITLE}"><img></a>' for number in range(20))
        html += f'<a href="/produto/0/rtx-5060">{TITLE}</a>'
        html += '<a href="/produto/30/ti">MSI RTX 5060 Ti</a><a href="/busca">MSI RTX 5060</a>'
        links = search_links(html, 'https://www.terabyteshop.com.br/busca', PART)
        self.assertEqual(len(links), 12)
        self.assertEqual(links[0], 'https://www.terabyteshop.com.br/produto/0/rtx-5060')
        self.assertNotIn('https://www.terabyteshop.com.br/produto/30/ti', links)

    def test_main_payment_blocks_preserve_exact_total_and_ignore_old_or_related_prices(self):
        offer = product_offer(product(), URL, PART)
        self.assertEqual((offer['pix'], offer['card'], offer['installments'], offer['installment']),
                         (274999, 323528, 12, 26961))
        self.assertIsNone(offer['announced'])
        self.assertEqual((offer['shop'], offer['seller'], offer['brand'], offer['availability']),
                         ('Terabyte Shop', 'TerabyteShop', 'MSI', 'in'))
        self.assertIsNone(offer['coupon_price'])

    def test_cash_value_without_pix_condition_is_only_announced(self):
        offer = product_offer(product(pix=False), URL, PART)
        self.assertIsNone(offer['pix'])
        self.assertEqual(offer['announced'], 274999)
        self.assertEqual(offer['card'], 323528)

    def test_missing_main_price_or_wrong_model_does_not_confirm_related_prices(self):
        for html in (f'<h1>{TITLE}</h1><p>Outra placa R$ 10,00 no Pix</p>',
                     product().replace('RTX 5060', 'RTX 5060 Ti'),
                     f'<div class="AreaInfvlrpdt"><h1>{TITLE}</h1></div><p>R$ 10,00 no Pix</p>'):
            with self.subTest(html=html), self.assertRaises(ValueError):
                product_offer(html, URL, PART)

    def test_out_of_stock_remains_unavailable(self):
        self.assertEqual(product_offer(product(stock='Produto indisponível'), URL, PART)['availability'], 'out')


class TerabyteFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_and_price_check_use_public_store_with_encoded_query(self):
        shops = Shops()
        requests = []
        def respond(request):
            requests.append(request)
            html = f'<a href="{URL}">{TITLE}</a>' if request.url.path == '/busca' else product()
            return httpx.Response(200, text=html)
        try:
            await shops.client.aclose()
            shops.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
            self.assertEqual(await shops.discover('Terabyte Shop', PART), [URL])
            self.assertEqual(requests[0].url.params['str'], PART['query'])
            self.assertEqual((await shops.check(URL, PART))['pix'], 274999)
        finally:
            await shops.close()

    async def test_block_and_foreign_redirect_do_not_supply_offers(self):
        for response in (httpx.Response(403), httpx.Response(302, headers={'location': 'https://example.com/private'})):
            shops = Shops()
            try:
                await shops.client.aclose()
                shops.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response))
                with self.assertRaises(ValueError):
                    await shops.check(URL, PART)
            finally:
                await shops.close()
