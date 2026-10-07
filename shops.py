"""Coleta pública de lojas. Preços sem condição explícita não viram Pix."""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl, quote, urljoin, urlsplit
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from core import AMOUNT, coupons, detect_brand, effective_price, matches, money, normalized, prices, utcnow, valid_url
from mercado_livre_browser import MELI_HOSTS, MercadoLivreBrowser
from shopee_browser import SHOPEE_HOSTS, ShopeeBrowser, validate_shopee_page

STORE_HOSTS = {'www.pichau.com.br', 'pichau.com.br', 'www.mercadolivre.com.br',
               'mercadolivre.com.br', 'produto.mercadolivre.com.br', 'lista.mercadolivre.com.br',
               'www.kabum.com.br', 'kabum.com.br', 'www.amazon.com.br', 'amazon.com.br',
               'www.terabyteshop.com.br', 'terabyteshop.com.br'} | SHOPEE_HOSTS
REDIRECT_HOSTS = STORE_HOSTS | {'meli.la', 'mercadolivre.com', 'www.mercadolivre.com',
                              'adrena.click', 'curt.link', 'bit.ly', 'amzn.to', 's.shopee.com.br', 'shope.ee'}
SHOP_NAMES = ('Pichau', 'Mercado Livre', 'KaBuM', 'Amazon', 'Shopee', 'Terabyte Shop')
COUPON_SHOPS = SHOP_NAMES + ('AliExpress',)
PUBLIC_COUPONS_URL = 'https://www.melhorescartoes.com.br/cupom-desconto.html'


def shop_name(url: str) -> str:
    host = urlsplit(url).hostname or ''
    if host in {'pichau.com.br', 'www.pichau.com.br'}:
        return 'Pichau'
    if host in {'kabum.com.br', 'www.kabum.com.br'}:
        return 'KaBuM'
    if host in {'terabyteshop.com.br', 'www.terabyteshop.com.br'}:
        return 'Terabyte Shop'
    if host in {'amazon.com.br', 'www.amazon.com.br', 'amzn.to'}:
        return 'Amazon'
    if host in SHOPEE_HOSTS | {'s.shopee.com.br', 'shope.ee'}:
        return 'Shopee'
    if host in REDIRECT_HOSTS and ('mercadolivre' in host or host == 'meli.la'):
        return 'Mercado Livre'
    return host or 'Loja não identificada'


def coupon_shop(text: str, urls: list[str]) -> str:
    found = set()
    pending = list(urls)
    for _ in range(3):
        destinations = []
        for url in pending:
            if not valid_url(url):
                continue
            name = shop_name(url)
            host = urlsplit(url).hostname or ''
            if host == 'shopee.com.br' or host.endswith('.shopee.com.br'):
                name = 'Shopee'
            elif host == 'aliexpress.com' or host.endswith('.aliexpress.com'):
                name = 'AliExpress'
            if name in COUPON_SHOPS:
                found.add(name)
            for key, value in parse_qsl(urlsplit(url).query):
                if key.lower() in {'url', 'u', 'ued', 'redirect', 'destination', 'target'} and valid_url(value):
                    destinations.append(value)
        pending = destinations
    if not found:
        text = normalized(text)
        aliases = {'Pichau': r'\bpichau\b', 'Mercado Livre': r'\bmercado\s*livre\b',
                   'KaBuM': r'\bkabum\b', 'Amazon': r'\bamazon\b',
                   'Shopee': r'\bshopee\b', 'Terabyte Shop': r'\bterabyte(?:\s*shop)?\b',
                   'AliExpress': r'\baliexpress\b'}
        found = {name for name, pattern in aliases.items() if re.search(pattern, text)}
    return ' · '.join(name for name in COUPON_SHOPS if name in found) or 'Loja não identificada'


def public_coupons(html: str) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    result = []
    tables = [table for table in soup.find_all('table')
              if table.find_all('tr') and {'cupom', 'link'} <= {normalized(cell.get_text(' ', strip=True))
                                      for cell in table.find_all('tr')[0].find_all(['td', 'th'])}]
    if not tables:
        raise ValueError('Melhores Cartões não apresentou tabelas de cupons legíveis.')
    for table in tables:
        for row in table.find_all('tr')[1:]:
            cells = row.find_all('td', recursive=False)
            if len(cells) not in (4, 5):
                continue
            if len(cells) == 5 and cells[4].get_text(' ', strip=True) != '✅':
                continue
            anchor = cells[3].find('a', href=True)
            url = anchor['href'] if anchor else ''
            shop = coupon_shop(cells[0].get_text(' ', strip=True), [url])
            if shop not in SHOP_NAMES or not valid_url(url):
                continue
            code = cells[2].get_text(' ', strip=True)
            activation = normalized(code) == 'ative no link'
            if not activation and not re.fullmatch(r'[A-Za-z0-9_-]{3,40}', code):
                continue
            item = dict(shop=shop, code='' if activation else code, conditions=cells[1].get_text(' ', strip=True),
                        url=url, source='Melhores Cartões', source_url=PUBLIC_COUPONS_URL,
                        activation=activation, checked_at=utcnow())
            if not any((previous['shop'], previous['code'], previous['conditions']) == (shop, item['code'], item['conditions']) for previous in result):
                result.append(item)
    return result[:200]


def structured_products(soup: BeautifulSoup) -> list[dict]:
    found = []

    def walk(value):
        if isinstance(value, dict):
            kind = value.get('@type')
            if kind == 'Product' or isinstance(kind, list) and 'Product' in kind:
                found.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for script in soup.find_all('script', type='application/ld+json'):
        try:
            walk(json.loads(script.string or script.get_text()))
        except (json.JSONDecodeError, TypeError):
            continue
    return found


def price_text(text: str, shop: str) -> dict:
    values = prices(text)
    flat = re.sub(r'\s+', ' ', normalized(text))
    pix = re.search(AMOUNT + r'\s*(?:no\s+)?pix\b', flat, re.I)
    if not pix:
        pix = re.search(r'(?:a vista|no pix)\s*' + AMOUNT, flat, re.I)
    if pix:
        values['pix'] = money(pix[1])
    # Pichau usa "R$ ... no PIX com 15% desconto" e "R$ ... em até 12x ...".
    if shop in {'Pichau', 'Terabyte Shop'}:
        pix = re.search(AMOUNT + r'\s*no\s+pix', flat, re.I)
        card = re.search(AMOUNT + r'\s*em\s+ate\s+(\d{1,2})\s*x\s*(?:de\s*)?' + AMOUNT, flat, re.I)
        if pix:
            values['pix'] = money(pix[1])
        if card:
            values.update(card=money(card[1]), installments=int(card[2]), installment=money(card[3]))
    return values


def mercado_livre_coupon_price(soup: BeautifulSoup, base: int | None, relevant: str) -> int | None:
    if base is None:
        return None
    for label in soup.select('.ui-vpp-coupons-awareness__checkbox-label'):
        if label.get_text('\n', strip=True) not in relevant:
            continue
        if any(parent.has_attr('hidden')
               or re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', parent.get('style', ''), re.I)
               for parent in [label, *label.parents] if parent.name):
            continue
        text = normalized(label.get_text(' ', strip=True))
        text = re.sub(r'(\d)\s*([.,])\s*(\d)', r'\1\2\3', text)
        match = re.search(AMOUNT + r'\s+com\s+cupom\b', text, re.I)
        if match:
            value = money(match[1])
            if value is not None and 0 < value < base:
                return value
    return None


def mercado_livre_shipping_origin(soup: BeautifulSoup, relevant: str) -> str:
    # Navegação e recomendações podem mencionar Internacional em anúncios locais.
    sections = soup.select('.ui-pdp-buybox, .ui-pdp-header, .xprod-lib-shipping-section')
    text = normalized(' '.join(section.get_text(' ', strip=True) for section in sections)
                      if sections else relevant)
    if re.search(r'\b(?:internacional|produto do exterior|impostos de importacao|'
                 r'envio (?:da|do|dos|de) (?:china|hong kong|estados unidos|eua|japao|coreia|singapura|taiwan))\b', text):
        return 'international'
    delivery = soup.select('.ui-pdp-buybox, .xprod-lib-shipping-section')
    return ('local' if delivery and re.search(r'\b(?:chegara|receba|retire|envio local|frete nacional)\b',
                                             normalized(' '.join(e.get_text(' ', strip=True) for e in delivery))) else 'unknown')


def product_offer(html: str, url: str, expected: dict | None = None) -> dict:
    soup = BeautifulSoup(html, 'html.parser')
    heading = soup.find('h1')
    title = heading.get_text(' ', strip=True) if heading else ''
    products = structured_products(soup)
    name = shop_name(url)
    if name == 'Shopee':
        validate_shopee_page(html, url)
    kabum = None
    if name == 'KaBuM':
        script = soup.find('script', id='__NEXT_DATA__')
        try:
            candidate = json.loads(script.string or script.get_text())['props']['pageProps']['product'] if script else {}
            product_id = re.search(r'/produto/(\d+)', urlsplit(url).path)
            if product_id and str(candidate.get('id')) == product_id[1] and normalized(candidate.get('title', '')) == normalized(title):
                kabum = candidate
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    product = next((item for item in products if not title or normalized(item.get('name', '')) == normalized(title)), None)
    if product is None and products and not title:
        product = products[0]
    if product and not title:
        title = product.get('name', '')
    if not title or expected and not matches(expected, title):
        raise ValueError('A página não confirmou o modelo da peça; anúncio preservado sem conferência.')
    for element in soup(['script', 'style', 'nav', 'footer']):
        element.decompose()
    text = soup.get_text('\n', strip=True)
    # Impede usar os preços de "produtos relacionados" como os deste anúncio.
    start = text.find(title)
    relevant = text[start:] if start >= 0 else text
    relevant = re.split(r'(?i)\b(?:características|sobre o produto|descrição|veja também|produtos relacionados)\b', relevant)[0]
    data = price_text(relevant, name)
    availability = 'unknown'
    seller = None
    structured_price = None
    if product:
        offers = product.get('offers') or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if isinstance(offers, dict):
            price = offers.get('price')
            if price is not None:
                data['announced'] = int(round(float(price) * 100))
                structured_price = data['announced']
            stock = str(offers.get('availability', ''))
            if stock.endswith('OutOfStock') or stock.endswith('Discontinued'):
                availability = 'out'
            elif stock.endswith('InStock'):
                availability = 'in'
            offered_by = offers.get('seller')
            if isinstance(offered_by, dict):
                seller = offered_by.get('name')
    if name == 'Mercado Livre':
        price_box = soup.select_one('.ui-pdp-price')
        if price_box or structured_price is not None:
            text_price = price_box.get_text(' ', strip=True) if price_box else ''
            text_price = re.sub(r'(\d)\s*([.,])\s*(\d)', r'\1\2\3', normalized(text_price))
            # O bloco também contém propaganda de crédito/cartão, não preços da peça.
            text_price = re.split(r'\b(?:credito disponivel|cartao de credito mercado\s*pago|ver meios de pagamento e promocoes)\b', text_price)[0]
            data = price_text(text_price, name)
            if structured_price is not None:
                data['announced'] = structured_price
    if kabum:
        price_data = kabum.get('prices') or {}
        installment = kabum.get('installment') or {}
        pix = price_data.get('priceWithDiscount')
        if pix is not None and re.search(r'\b(?:a vista no pix|no pix)\b', normalized(text)):
            data['pix'] = int(round(float(pix) * 100))
        if price_data.get('price') is not None and installment.get('installment') and installment.get('amount') is not None:
            data.update(card=int(round(float(price_data['price']) * 100)),
                        installments=int(installment['installment']), installment=int(round(float(installment['amount']) * 100)))
        seller = kabum.get('sellerName')
        availability = 'in' if kabum.get('available') is True else 'out' if kabum.get('available') is False else availability
    if name == 'Amazon':
        price_box = soup.select_one('#corePriceDisplay_desktop_feature_div, #corePrice_feature_div')
        amount = price_box.select_one('.a-price:not(.a-text-price) .a-offscreen') if price_box else None
        if amount:
            data = price_text(price_box.get_text(' ', strip=True), name)
            data['announced'] = money(amount.get_text())
        elif product and data['announced'] is not None:
            data = dict(prices(''), announced=data['announced'])
        else:
            raise ValueError('Amazon não apresentou preço legível do produto; anúncio preservado sem conferência.')
        merchant = soup.select_one('#sellerProfileTriggerId')
        if merchant:
            seller = merchant.get_text(' ', strip=True)
    if name == 'Terabyte Shop':
        box = soup.select_one('.AreaInfvlrpdt')
        box_heading = box.find('h1') if box else None
        if not box_heading or normalized(box_heading.get_text(' ', strip=True)) != normalized(title):
            raise ValueError('Terabyte Shop não apresentou a área de preço do produto; anúncio preservado sem conferência.')
        data = prices('')
        cash = box.select_one('#valVista')
        if cash:
            value = money(cash.get_text(' ', strip=True))
            condition = normalized(cash.parent.parent.get_text(' ', strip=True))
            data['pix' if re.search(r'\bpix\b', condition) else 'announced'] = value
        card_box = box.select_one('.val-parc')
        if card_box:
            card = price_text(card_box.get_text(' ', strip=True), name)
            for key in ('card', 'installments', 'installment'):
                data[key] = card[key]
        merchant = box.select_one('.vendPor')
        if merchant:
            seller = re.sub(r'^Vendido por:\s*', '', merchant.get_text(' ', strip=True), flags=re.I)
        stock = box.select_one('.prodCond')
        if stock:
            stock_text = normalized(stock.get_text(' ', strip=True))
            if re.search(r'\b(?:produto indisponivel|produto esgotado|fora de estoque|avise-me)\b', stock_text):
                availability = 'out'
            elif re.search(r'\b(?:pronta entrega|produto disponivel)\b', stock_text):
                availability = 'in'
    if name == 'Shopee':
        offers = product.get('offers') if product else None
        if not isinstance(offers, dict) or offers.get('priceCurrency', 'BRL') != 'BRL':
            raise ValueError('Shopee não apresentou preço legível do produto; anúncio preservado sem conferência.')
        value = offers.get('price')
        if value is None and offers.get('lowPrice') == offers.get('highPrice'):
            value = offers.get('lowPrice')
        if value is None:
            raise ValueError('Shopee apresentou preço por variação ou sem valor único. Confira a opção na loja; anúncio preservado.')
        try:
            value = int(round(float(value) * 100))
        except (ValueError, TypeError, OverflowError):
            raise ValueError('Shopee não apresentou preço válido do produto; anúncio preservado.') from None
        if value <= 0:
            raise ValueError('Shopee não apresentou preço válido do produto; anúncio preservado.')
        data = dict(prices(''), announced=value)
    if re.search(r'\b(produto indisponivel|produto esgotado|fora de estoque)\b', normalized(relevant)):
        availability = 'out'
    if all(data[key] is None for key in ('pix', 'card', 'announced')):
        raise ValueError('A página não apresentou preço legível; anúncio preservado sem conferência.')
    coupon_price = (mercado_livre_coupon_price(soup, data['announced'] if data['announced'] is not None
                   else next((data[key] for key in ('pix', 'card') if data[key] is not None), None), relevant)
                   if name == 'Mercado Livre' else None)
    now = utcnow()
    return dict(url=url, title=title, shop=name, seller=seller, brand=detect_brand(title), **data, coupons=[], coupon_price=coupon_price,
                shipping_origin=mercado_livre_shipping_origin(soup, relevant) if name == 'Mercado Livre' else 'unknown',
                status='Preço lido na loja', published_at=now, received_at=now, checked_at=now,
                availability=availability, message=None)


def search_links(html: str, base_url: str, component: dict | None) -> list[str]:
    soup = BeautifulSoup(html, 'html.parser')
    found = []
    excluded = set()
    if shop_name(base_url) == 'Mercado Livre':
        for card in soup.select('.ui-search-layout__item'):
            if re.search(r'\b(?:internacional|compra internacional)\b', normalized(card.get_text(' ', strip=True))):
                excluded.update(urljoin(base_url, anchor['href']).split('#')[0]
                                for anchor in card.find_all('a', href=True))
    for anchor in soup.find_all('a', href=True):
        href = urljoin(base_url, anchor['href'])
        host = urlsplit(href).hostname
        if host not in STORE_HOSTS:
            continue
        is_product = (host in {'pichau.com.br', 'www.pichau.com.br'} and
                      bool(re.search(r'/(?:placa-de-video|fonte-|ssd-|water-cooler-)', urlsplit(href).path))) or (
                      bool(re.search(r'(?:/MLB-?\d+|/p/MLB\d+)', href, re.I))) or (
                      host in {'kabum.com.br', 'www.kabum.com.br'} and bool(re.search(r'/produto/\d+', urlsplit(href).path))) or (
                      host in {'amazon.com.br', 'www.amazon.com.br'} and bool(re.search(r'/(?:dp|gp/product)/[A-Z0-9]{10}(?:/|$)', urlsplit(href).path)))
        is_product = is_product or (host in SHOPEE_HOSTS and bool(re.search(r'(?:-i\.\d+\.\d+|/product/\d+/\d+)(?:/|$)', urlsplit(href).path)))
        is_product = is_product or (host in {'terabyteshop.com.br', 'www.terabyteshop.com.br'}
                                    and bool(re.search(r'^/produto/\d+(?:/|$)', urlsplit(href).path)))
        if not is_product or href.split('#')[0] in excluded:
            continue
        title = anchor.get_text(' ', strip=True) or anchor.get('title', '')
        if not title:
            image = anchor.find('img')
            title = image.get('alt', '') if image else ''
        if title and (component is None or matches(component, title)) and valid_url(href) and href not in found:
            found.append(href.split('#')[0])
    for item in structured_products(soup):
        offer = item.get('offers') or {}
        href = urljoin(base_url, item.get('url') or (offer.get('url', '') if isinstance(offer, dict) else ''))
        title = item.get('name', '')
        if title and (component is None or matches(component, title)) and urlsplit(href).hostname in STORE_HOSTS and href.split('#')[0] not in excluded and href not in found and href != base_url:
            found.append(href)
    return found[:12]


def mercado_livre_search_candidates(html: str, base_url: str, component: dict) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    found = {}
    excluded = set()

    def amount(node):
        if node is None:
            return None
        fraction = node.select_one('.andes-money-amount__fraction')
        cents = node.select_one('.andes-money-amount__cents')
        if fraction:
            value = money(fraction.get_text(strip=True) + ',' + (cents.get_text(strip=True) if cents else '00'))
        else:
            match = re.search(AMOUNT, node.get_text(' ', strip=True))
            value = money(match[1]) if match else None
        return value if value and value > 0 else None

    def price_label(node):
        if node is None:
            return ''
        copy = BeautifulSoup(str(node), 'html.parser')
        for value_node in copy.select('.andes-money-amount'):
            value = amount(value_node)
            value_node.replace_with(f'R$ {value // 100},{value % 100:02}' if value else '')
        return copy.get_text(' ', strip=True)

    for card in soup.select('.ui-search-layout__item'):
        text = normalized(card.get_text(' ', strip=True))
        if re.search(r'\b(?:internacional|compra internacional|envio da china|produto do exterior)\b', text):
            excluded.update(urljoin(base_url, anchor['href']).split('#')[0] for anchor in card.find_all('a', href=True))
            continue
        for alternative in card.select('.poly-component__buy-box'):
            alternative.decompose()
        title_node = card.select_one('.poly-component__title, .ui-search-item__title')
        links_found = search_links(str(card), base_url, component)
        if not links_found:
            continue
        url = links_found[0]
        title = title_node.get_text(' ', strip=True) if title_node else ''
        if not title or not matches(component, title):
            found.setdefault(url, dict(url=url, reading=None))
            continue
        price_box = card.select_one('.poly-price__current, .ui-search-price__second-line')
        value = amount(price_box)
        if value is None:
            found.setdefault(url, dict(url=url, reading=None))
            continue
        data = prices('')
        data['announced'] = value
        # Somente a área principal: outra opção de compra pode ter outro vendedor.
        installments = card.select_one('.poly-price__installments, .ui-search-installments')
        payment = price_text(price_label(price_box) + '\n' + price_label(installments), 'Mercado Livre')
        for key in ('pix', 'card', 'installments', 'installment'):
            data[key] = payment[key]
        coupon_price = None
        for label in card.select('.poly-coupons__pill'):
            if any(parent.has_attr('hidden') or parent.get('aria-hidden') == 'true'
                   or re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', parent.get('style', ''), re.I)
                   for parent in [label, *label.parents] if parent.name):
                continue
            match = re.search(AMOUNT + r'\s+com\s+cupom\b', normalized(price_label(label)), re.I)
            if match:
                coupon = money(match[1])
                if coupon and coupon < value:
                    coupon_price = coupon
                    break
        seller = card.select_one('.poly-component__seller, .ui-search-official-store-label')
        origin = ('local' if 'SHIPPING*ORIGIN_10215068' in base_url
                  or re.search(r'\b(?:envio local|frete nacional|envio do brasil)\b', text) else 'unknown')
        now = utcnow()
        reading = dict(url=url, title=title, shop='Mercado Livre',
                       seller=seller.get_text(' ', strip=True) if seller else None, brand=detect_brand(title),
                       **data, coupons=[], coupon_price=coupon_price, shipping_origin=origin,
                       status='Preço lido na loja · busca do Mercado Livre', availability='unknown',
                       published_at=now, received_at=now, checked_at=now, message=None)
        found[url] = dict(url=url, reading=reading)
    # Layout sem cartões reconhecidos continua exigindo leitura individual.
    for url in search_links(html, base_url, component):
        if url not in excluded:
            found.setdefault(url, dict(url=url, reading=None))
    return sorted(found.values(), key=lambda item: effective_price(item['reading']) if item['reading'] else float('inf'))[:12]


class Shops:
    def __init__(self, data_dir: Path | None = None):
        self.ml_browser = MercadoLivreBrowser(data_dir / 'mercado-livre') if data_dir else None
        self.shopee_browser = ShopeeBrowser(data_dir / 'shopee') if data_dir else None
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(25, connect=10), follow_redirects=False,
                                        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
                                                 'Accept-Language': 'pt-BR,pt;q=0.9'})

    async def fetch(self, url: str) -> tuple[str, str]:
        # Não consulta hosts arbitrários recebidos de mensagens nem URLs locais.
        for _ in range(7):
            if not valid_url(url) or urlsplit(url).hostname not in REDIRECT_HOSTS or urlsplit(url).port not in {None, 443}:
                raise ValueError('Conferência automática disponível apenas para links das lojas e encurtadores suportados.')
            if self.ml_browser and (self.ml_browser.configured or self.ml_browser.login_open) and urlsplit(url).hostname in MELI_HOSTS:
                return await self.ml_browser.fetch(url)
            if urlsplit(url).hostname in SHOPEE_HOSTS:
                if not self.shopee_browser:
                    raise ValueError('Shopee exige uma sessão própria do Chrome. Abra a sessão na aba Fontes.')
                return await self.shopee_browser.fetch(url)
            response = await self.client.get(url)
            if response.status_code in {301, 302, 303, 307, 308}:
                destination = response.headers.get('location')
                if not destination:
                    raise ValueError('O link redirecionou sem indicar o destino.')
                url = urljoin(url, destination)
                continue
            if response.status_code in {401, 403, 429, 503}:
                raise ValueError(f'A loja recusou a consulta ({response.status_code}). O preço anunciado continua disponível.')
            response.raise_for_status()
            if urlsplit(url).hostname not in STORE_HOSTS:
                raise ValueError('O destino não é uma loja com conferência automática nesta versão.')
            if len(response.content) > 6_000_000:
                raise ValueError('Página acima do limite de leitura.')
            return response.text, url
        raise ValueError('O link excedeu o limite de redirecionamentos.')

    async def check(self, url: str, component: dict) -> dict:
        html, resolved = await self.fetch(url)
        return product_offer(html, resolved, component)

    async def _search_page(self, shop: str, component: dict) -> tuple[str, str]:
        query = component['query']
        if shop == 'KaBuM' and re.search(r'\bwater\s+cooler\b', normalized(query)):
            query = re.sub(r'\b(120|240|280|360|420)\b(?!\s*mm)', r'\1mm', query, flags=re.I)
        urls = {'Pichau': 'https://www.pichau.com.br/search?q=' + quote(query),
                'Mercado Livre': 'https://lista.mercadolivre.com.br/' + quote(query.replace(' ', '-')),
                'KaBuM': 'https://www.kabum.com.br/busca/' + quote(query.replace(' ', '-')),
                'Amazon': 'https://www.amazon.com.br/s?k=' + quote(query),
                'Shopee': 'https://shopee.com.br/search?keyword=' + quote(query),
                'Terabyte Shop': 'https://www.terabyteshop.com.br/busca?str=' + quote(query)}
        url = urls[shop]
        html, resolved = await self.fetch(url)
        text = normalized(BeautifulSoup(html, 'html.parser').get_text(' ', strip=True))
        if shop == 'Amazon' and any(marker in text for marker in ('digite os caracteres', 'enter the characters', 'robot check', 'algo deu errado')):
            raise ValueError('Amazon bloqueou a consulta pública. Ofertas do Telegram continuam disponíveis; busca direta não foi concluída.')
        if shop == 'Mercado Livre' and 'para continuar, acesse sua conta' in text:
            raise ValueError('Mercado Livre exigiu login para esta consulta. Ofertas do Telegram continuam disponíveis; busca direta não foi concluída.')
        if shop == 'Mercado Livre':
            # O endereço genérico com o sufixo é redirecionado sem filtro: seguir
            # o link Local publicado pela página, que inclui categoria e estado.
            soup = BeautifulSoup(html, 'html.parser')
            local = next((urljoin(resolved, anchor['href']) for anchor in soup.find_all('a', href=True)
                          if normalized(anchor.get_text(' ', strip=True)) == 'local'
                          and 'SHIPPING*ORIGIN_10215068' in anchor['href']), None)
            if local and (not valid_url(local) or urlsplit(local).hostname not in MELI_HOSTS):
                raise ValueError('Mercado Livre não apresentou o filtro de envio Local; consulta nacional não concluída.')
            if local:
                html, resolved = await self.fetch(local)
                if 'SHIPPING*ORIGIN_10215068' not in resolved:
                    raise ValueError('Mercado Livre não manteve o filtro de envio Local; consulta nacional não concluída.')
            # Algumas buscas não oferecem Local. Cada produto continua exigindo
            # origem nacional confirmada para catálogo/avisos (offer_matches).
        return html, resolved

    async def discover(self, shop: str, component: dict) -> list[str]:
        html, resolved = await self._search_page(shop, component)
        result = search_links(html, resolved, component)
        if not result:
            raise ValueError('Nenhum anúncio legível encontrado nesta consulta. Pode haver ausência de ofertas ou conteúdo carregado por scripts.')
        return result

    async def discover_mercado_livre(self, component: dict) -> list[dict]:
        html, resolved = await self._search_page('Mercado Livre', component)
        result = mercado_livre_search_candidates(html, resolved, component)
        if not result:
            raise ValueError('Nenhum anúncio legível encontrado nesta consulta. Pode haver ausência de ofertas ou conteúdo carregado por scripts.')
        return result

    async def coupon_list(self) -> list[dict]:
        html, _ = await self.fetch('https://www.pichau.com.br/promocao/cupons')
        soup = BeautifulSoup(html, 'html.parser')
        result = []
        for anchor in soup.find_all('a', href=True):
            if normalized(anchor.get_text(' ', strip=True)) != 'ver produtos':
                continue
            parent = anchor.parent
            text = parent.get_text(' ', strip=True)
            for _ in range(3):
                if re.search(r'\b(?:\d+%|off)\b', normalized(text)):
                    break
                parent = parent.parent
                text = parent.get_text(' ', strip=True)
            tokens = re.findall(r'\b[A-Za-z0-9_-]{4,30}\b', text)
            candidates = [token for token in tokens if any(c.isdigit() for c in token) and any(c.isalpha() for c in token)]
            if candidates:
                result.append(dict(code=candidates[-1], conditions=text, url=urljoin('https://www.pichau.com.br', anchor['href'])))
        return result

    async def public_coupon_list(self) -> list[dict]:
        response = await self.client.get(PUBLIC_COUPONS_URL)
        response.raise_for_status()
        if len(response.content) > 6_000_000:
            raise ValueError('Fonte pública de cupons acima do limite de leitura.')
        return public_coupons(response.text)

    async def close(self):
        if self.shopee_browser:
            await self.shopee_browser.close()
        await self.client.aclose()
        if self.ml_browser:
            await self.ml_browser.close()
