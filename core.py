"""Regras de identificação, extração e persistência do monitor local."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from statistics import median
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def coupon_is_today(stamp: str, now: datetime | None = None) -> bool:
    """Dia civil de São Paulo, independente do fuso configurado no Windows."""
    zone = timezone(timedelta(hours=-3), 'America/Sao_Paulo')
    try:
        found = datetime.fromisoformat(stamp)
        found = found.replace(tzinfo=timezone.utc) if found.tzinfo is None else found
        return found.astimezone(zone).date() == (now or datetime.now(timezone.utc)).astimezone(zone).date()
    except (TypeError, ValueError):
        return False


def normalized(value: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', value.lower())
                   if not unicodedata.combining(c))


def money(value: str) -> int:
    value = re.sub(r'[^\d,.]', '', value)
    # Lojas brasileiras também publicam "2,629.99" no HTML.
    separators = [index for index, char in enumerate(value) if char in ',.']
    if separators and len(value) - separators[-1] - 1 in {1, 2}:
        index = separators[-1]
        whole = re.sub(r'[,.]', '', value[:index])
        return int(whole or '0') * 100 + int((value[index + 1:] + '00')[:2])
    return int(re.sub(r'[,.]', '', value) or '0') * 100


def brl(value: int | None) -> str:
    if value is None:
        return 'Não informado'
    return ('R$ ' + f'{value / 100:,.2f}').replace(',', '_').replace('.', ',').replace('_', '.')


BRAND_ALIASES = {
    'ASUS': ('asus',), 'MSI': ('msi',), 'Gigabyte': ('gigabyte', 'aorus'),
    'Zotac': ('zotac',), 'INNO3D': ('inno3d', 'inno 3d'), 'PNY': ('pny',),
    'Galax': ('galax',), 'Palit': ('palit',), 'Gainward': ('gainward',),
    'Colorful': ('colorful',), 'Maxsun': ('maxsun',), 'Manli': ('manli',),
    'ASRock': ('asrock',), 'Sapphire': ('sapphire',), 'PowerColor': ('powercolor',),
    'XFX': ('xfx',), 'Biostar': ('biostar',), 'Yeston': ('yeston',),
    'Corsair': ('corsair',), 'Kingston': ('kingston',), 'Samsung': ('samsung',),
    'Crucial': ('crucial',), 'ADATA': ('adata', 'xpg'), 'Western Digital': ('western digital', 'wd'),
    'Seagate': ('seagate',), 'TeamGroup': ('teamgroup', 'team group'),
    'Seasonic': ('seasonic',), 'Cooler Master': ('cooler master', 'coolermaster'),
    'Thermaltake': ('thermaltake',), 'DeepCool': ('deepcool',), 'EVGA': ('evga',),
}


def detect_brand(text: str) -> str | None:
    text = normalized(text or '')
    found = [brand for brand, aliases in BRAND_ALIASES.items()
             if any(re.search(r'\b' + re.escape(alias).replace(r'\ ', r'[\s-]+') + r'\b', text)
                    for alias in aliases)]
    return found[0] if len(found) == 1 else None


def brand_ignored(component: dict, brand: str | None) -> bool:
    ignored = component.get('ignored_brands') or []
    if isinstance(ignored, str):
        ignored = json.loads(ignored)
    return brand is not None and brand in ignored


def matches(component: dict, text: str) -> bool:
    if brand_ignored(component, detect_brand(text)):
        return False
    text = normalized(text)
    kind = component['kind']
    query = normalized(component.get('query') or '')
    if kind == 'custom':
        fan_category = r'\b(?:ventoinhas?|fans?|coolers?\s+(?:para\s+|de\s+)?gabinete)\b'
        text = re.sub(fan_category, 'ventoinha', text)
        query = re.sub(fan_category, 'ventoinha', query)
    model = re.search(r'\brtx\s*5060\b|\bcx[\s-]*750\b|\bnv3\b', text)
    if kind == 'custom':
        first_token = re.findall(r'[a-z0-9]+', query)
        model = re.search(rf'\b{re.escape(first_token[0])}\b', text) if first_token else None
    # Acessório antes do modelo identifica o produto vendido; "com backplate" não.
    excluded = r'\b(kit|combo|pc gamer|computador|notebook|desktop|estojo|case|capa|enclosure|adaptador|riser|suporte|cabo|waterblock|backplate)\b'
    if (kind != 'custom' or not re.search(excluded, query)) and (
            re.search(r'\b(kit|combo|pc gamer|computador|notebook|desktop)\b', text)
            or model and re.search(excluded, text[:model.start()])):
        return False
    if kind == 'gpu':
        if not re.search(r'\brtx\s*5060\b', text) or re.search(r'\brtx\s*5060\s*ti\b', text):
            return False
        return not bool(re.search(r'\b(pc gamer|computador|notebook|desktop|kit upgrade)\b', text))
    if kind == 'psu':
        return bool(re.search(r'\bcx[\s-]*750\b', text)) and not bool(
            re.search(r'\bcx[\s-]*750\s*[mf]\b', text))
    if kind == 'ssd':
        capacity = int(component.get('capacity_gb') or 1000)
        capacities = [int(Decimal(amount.replace(',', '.')) * (1000 if unit == 'tb' else 1))
                      for amount, unit in re.findall(r'\b(\d+(?:[.,]\d+)?)\s*(gb|tb)\b(?!\s*/\s*s)', text)]
        allowed = {1000, 1024} if capacity == 1000 else {capacity}
        return bool(model and re.search(r'\bnv3\b', text) and capacities and all(value in allowed for value in capacities))
    # Dimensões anunciadas como 360mm/360 mm equivalem à busca por 360.
    # Não separar números de códigos de modelo como 5700X ou RTX5060TI.
    text = re.sub(r'\b(\d+)\s*mm\b', r'\1 mm', text)
    tokens = re.findall(r'[a-z0-9]+', re.sub(r'\b(\d+)\s*mm\b', r'\1 mm', query))
    return bool(tokens) and all(re.search(rf'\b{re.escape(token)}\b', text) for token in tokens)


def offer_matches(component: dict, offer: dict) -> bool:
    if offer.get('shop') == 'Mercado Livre' and offer.get('shipping_origin', 'unknown') != 'local':
        return False
    if brand_ignored(component, offer.get('brand') or detect_brand(offer.get('title') or '')):
        return False
    if not component.get('kind'):
        return True
    if 'não confirmou o modelo' in (offer.get('status') or ''):
        return False
    text = offer.get('title') or ''
    if not confirmed_price(offer.get('status') or '') and offer.get('message'):
        text = offer['message']
    return matches(component, text)


def offer_group_key(offer: dict) -> tuple:
    title = normalized(offer.get('title', '')).strip()
    if offer.get('shop') == 'Pichau':
        title = re.sub(r'-nac$', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    key = (normalized(offer.get('shop', '')), normalized(offer.get('seller') or ''), title)
    return key if title and offer.get('seller') else key + (offer['id'],)


def alert_payment(offer: dict) -> str | None:
    if offer.get('target') is None and offer.get('shop') == 'Mercado Livre' and offer.get('pix') is None and offer.get('announced') is not None:
        return 'announced'
    return (offer['target_payment'] if offer.get('target') is not None else
            next((key for key in ('pix', 'card', 'announced') if offer.get(key) is not None), None))


def alert_price(offer: dict, payment: str | None) -> int | None:
    value = offer.get(payment) if payment else None
    coupon = offer.get('coupon_price')
    # O preço "com cupom" da sessão não informa Pix nem total parcelado.
    if payment == 'announced' and confirmed_price(offer.get('status') or '') and value is not None and coupon and 0 < coupon < value:
        return coupon
    return value


def reading_valid_until(offer: dict) -> str | None:
    confirmed = confirmed_price(offer.get('status') or '')
    if not confirmed and offer.get('status') != 'Anunciado no Telegram':
        return None
    value = (offer.get('checked_at') or offer.get('received_at')) if confirmed else offer.get('published_at')
    try:
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        minutes = (90 if offer.get('shop') == 'Mercado Livre' else 30) if confirmed else 5
        return (stamp + timedelta(minutes=minutes)).isoformat()
    except (ValueError, TypeError):
        return None


def price_is_current(offer: dict, now: datetime | None = None) -> bool:
    if 'valid_until' not in offer and not any(key in offer for key in ('checked_at', 'received_at', 'published_at')):
        return True  # Resumos sem datas; registros persistidos sempre possuem valid_until.
    value = offer.get('valid_until') if 'valid_until' in offer else reading_valid_until(offer)
    try:
        deadline = datetime.fromisoformat(value)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return deadline > (now or datetime.now(timezone.utc))
    except (ValueError, TypeError):
        return False


def confirmed_price(status: str) -> bool:
    return status.startswith(('Preço lido na loja', 'Preço da loja lido'))


AMOUNT = r'R\$\s*(\d+(?:[.,]\d+)*)'


def prices(text: str) -> dict:
    """Nunca confunde o valor de uma parcela com preço total ou Pix."""
    result = dict(pix=None, card=None, announced=None, installments=None, installment=None)
    lines = normalized(text).splitlines()
    explicit_card = None
    for line in lines:
        parcel = re.search(r'(\d{1,2})\s*x\s*(?:de\s*)?' + AMOUNT, line, re.I)
        if parcel and 1 <= int(parcel[1]) <= 24:
            result['installments'] = int(parcel[1])
            result['installment'] = money(parcel[2])
            result['card'] = result['installments'] * result['installment']
        clean = re.sub(r'\d{1,2}\s*x\s*(?:de\s*)?' + AMOUNT, '', line, flags=re.I)
        values = list(re.finditer(AMOUNT, clean, re.I))
        if not values:
            continue
        pix = re.search(AMOUNT + r'\s*(?:no\s*)?(?:pix|a vista)\b', clean, re.I)
        if not pix:
            pix = re.search(r'(?:pix|a vista)\s*:?\s*' + AMOUNT, clean, re.I)
        card = re.search(AMOUNT + r'\s*(?:no\s*)?(?:cartao|parcelado)\b', clean, re.I)
        if not card:
            card = re.search(r'(?:cartao|parcelado)\s*:?\s*' + AMOUNT, clean, re.I)
        if pix:
            result['pix'] = money(pix[1])
        if card:
            explicit_card = money(card[1])
        # "de ... por ..." usa o preço anunciado após "por".
        selected = re.search(r'\bpor\s*' + AMOUNT, clean, re.I)
        amount = money(selected[1] if selected else values[-1][1])
        if pix or card:
            continue
        if ('pix' in clean or 'a vista' in clean) and len(values) == 1:
            result['pix'] = amount
        elif ('cartao' in clean or 'parcelado' in clean) and len(values) == 1:
            explicit_card = amount
        elif result['announced'] is None and (selected or len(values) == 1) and not re.search(r'\b(cupom|frete|cashback|minimo|limite)\b', clean):
            result['announced'] = amount
    if explicit_card is not None:
        result['card'] = explicit_card
    return result


def coupons(text: str) -> list[str]:
    found = []
    for line in text.splitlines():
        if 'cupom' not in normalized(line):
            continue
        quoted = re.findall(r'[`“\"\']([A-Za-z0-9_-]{3,40})[`”\"\']', line)
        codes = quoted or re.findall(r'\b(?=[A-Z0-9_-]*[A-Z])[A-Z0-9_-]{4,40}\b', line)
        found.extend(code for code in codes if code not in {'CUPOM', 'NOVO', 'OFF', 'PIX'})
    # Publicações de cupons podem trazer um código por linha entre crases.
    if 'cupom' in normalized(text):
        found.extend(re.findall(r'`([A-Za-z0-9_-]{3,40})`', text))
    return list(dict.fromkeys(found))


def valid_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username and not parsed.password
    except ValueError:
        return False


def links(text: str, extra: list[str] | None = None) -> list[str]:
    candidates = re.findall(r'https://[^\s<>]+', text) + (extra or [])
    found = []
    for candidate in candidates:
        candidate = candidate.rstrip(').,;]')
        if not valid_url(candidate):
            continue
        host = urlsplit(candidate).hostname
        if host in {'t.me', 'telegram.me', 'wa.me', 'whatsapp.com', 'www.whatsapp.com'}:
            continue
        if candidate not in found:
            found.append(candidate)
    return found


def canonical_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.hostname in {'amazon.com.br', 'www.amazon.com.br'}:
        asin = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})(?:/|$)', parsed.path)
        if asin:
            query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                     if key.lower() in {'m', 'smid', 'condition', 'offerlistingid'}]
            return urlunsplit(('https', 'www.amazon.com.br', '/dp/' + asin[1], urlencode(sorted(query)), ''))
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
             if not key.lower().startswith('utm_') and key.lower() not in
             {'matt_tool', 'matt_word', 'matt_source', 'matt_campaign_id', 'gclid', 'fbclid'}]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip('/'), urlencode(query), ''))


def offer_fingerprint(offer: dict) -> str:
    values = [offer.get(key) for key in ('pix', 'card', 'announced', 'installments', 'installment', 'coupon_price')]
    codes = offer.get('coupons', [])
    values.append(json.loads(codes) if isinstance(codes, str) else codes)
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def recent(published_at: str, now: datetime | None = None) -> bool:
    published = datetime.fromisoformat(published_at)
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    age = ((now or datetime.now(timezone.utc)) - published).total_seconds()
    return -30 <= age <= 300


def effective_price(offer: dict) -> int | float:
    base = next((offer[key] for key in ('pix', 'card', 'announced')
                 if offer.get(key) is not None), float('inf'))
    if offer.get('shop') == 'Mercado Livre' and offer.get('pix') is None and offer.get('announced') is not None:
        base = offer['announced']
    coupon = offer.get('coupon_price')
    return min(base, coupon) if coupon is not None and coupon > 0 else base


def catalog_price(offer: dict) -> int | float:
    return effective_price(offer) if price_is_current(offer) else float('inf')


def tracking_price(offer: dict) -> int | float:
    # Último preço base orienta quais anúncios vencidos serão revalidados;
    # um cupom vencido não mantém artificialmente o anúncio entre os baratos.
    return effective_price(offer if price_is_current(offer) else dict(offer, coupon_price=None))


def group_offers(components: list[dict], offers: list[dict], price_key=catalog_price, include_hidden=False) -> dict[int, list[dict]]:
    grouped = {part['id']: [] for part in components}
    parts = {part['id']: part for part in components}
    for offer in offers:
        if (include_hidden or not offer.get('hidden')) and offer['component_id'] in grouped and offer_matches(parts[offer['component_id']], offer):
            grouped[offer['component_id']].append(offer)
    for rows in grouped.values():
        rows.sort(key=price_key)
        unique = {}
        for offer in sorted(rows, key=lambda item: item.get('availability') == 'out'):
            key = offer_group_key(offer)
            if key not in unique:
                unique[key] = dict(offer, duplicate_ids=[offer['id']])
            else:
                unique[key]['duplicate_ids'].append(offer['id'])
                unique[key]['favorite'] = bool(unique[key].get('favorite') or offer.get('favorite'))
        rows[:] = sorted(unique.values(), key=price_key)
    return grouped


def top_offers(components: list[dict], offers: list[dict], price_key=catalog_price) -> dict[int, list[dict]]:
    grouped = group_offers(components, [row for row in offers if row.get('availability') != 'out'
                                      and effective_price(row) > 0], price_key)
    return {part_id: sorted(rows, key=lambda row: (price_key(row), tracking_price(row), min(row['duplicate_ids'])))[:12]
            for part_id, rows in grouped.items()}


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS components (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
                query TEXT NOT NULL, capacity_gb INTEGER, target INTEGER,
                target_payment TEXT NOT NULL DEFAULT 'pix', enabled INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, reference TEXT NOT NULL UNIQUE,
                chat_id INTEGER UNIQUE, enabled INTEGER NOT NULL DEFAULT 1,
                baseline TEXT, last_message INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS offers (
                id INTEGER PRIMARY KEY, component_id INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
                url TEXT NOT NULL, title TEXT NOT NULL, shop TEXT NOT NULL, seller TEXT,
                pix INTEGER, card INTEGER, announced INTEGER, installments INTEGER, installment INTEGER,
                coupons TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL, message TEXT,
                published_at TEXT NOT NULL, received_at TEXT NOT NULL, checked_at TEXT,
                availability TEXT NOT NULL DEFAULT 'unknown', fingerprint TEXT NOT NULL,
                UNIQUE(component_id,url));
            CREATE TABLE IF NOT EXISTS origins (
                id INTEGER PRIMARY KEY, offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
                source TEXT NOT NULL, chat_id INTEGER, message_id INTEGER, message_url TEXT,
                published_at TEXT NOT NULL, UNIQUE(offer_id,source,message_id));
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY, offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
                observed_at TEXT NOT NULL, pix INTEGER, card INTEGER, announced INTEGER, status TEXT,
                availability TEXT NOT NULL DEFAULT 'unknown');
            CREATE TABLE IF NOT EXISTS alerts (
                offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
                fingerprint TEXT NOT NULL, delivered_at TEXT NOT NULL, PRIMARY KEY(offer_id,fingerprint));
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS ml_coupon_applications (
                code TEXT PRIMARY KEY, status TEXT NOT NULL, detail TEXT NOT NULL,
                attempted_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 1,
                source TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS url_aliases (alias TEXT PRIMARY KEY, destination TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS processed_messages (
                source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                message_id INTEGER NOT NULL, processed_at TEXT NOT NULL, PRIMARY KEY(source_id,message_id));
            CREATE TABLE IF NOT EXISTS coupon_posts (
                source TEXT NOT NULL, message_id INTEGER NOT NULL, text TEXT NOT NULL,
                codes TEXT NOT NULL, published_at TEXT NOT NULL, PRIMARY KEY(source,message_id));
        ''')
        if 'disabled' not in {row['name'] for row in self.db.execute('PRAGMA table_info(ml_coupon_applications)')}:
            self.db.execute('ALTER TABLE ml_coupon_applications ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0')
        if 'found_at' not in {row['name'] for row in self.db.execute('PRAGMA table_info(ml_coupon_applications)')}:
            self.db.execute("ALTER TABLE ml_coupon_applications ADD COLUMN found_at TEXT NOT NULL DEFAULT ''")
        if 'availability' not in {row['name'] for row in self.db.execute('PRAGMA table_info(observations)')}:
            self.db.execute("ALTER TABLE observations ADD COLUMN availability TEXT NOT NULL DEFAULT 'unknown'")
        if 'coupon_price' not in {row['name'] for row in self.db.execute('PRAGMA table_info(offers)')}:
            self.db.execute('ALTER TABLE offers ADD COLUMN coupon_price INTEGER')
        if 'brand' not in {row['name'] for row in self.db.execute('PRAGMA table_info(offers)')}:
            self.db.execute('ALTER TABLE offers ADD COLUMN brand TEXT')
        if 'shipping_origin' not in {row['name'] for row in self.db.execute('PRAGMA table_info(offers)')}:
            self.db.execute("ALTER TABLE offers ADD COLUMN shipping_origin TEXT NOT NULL DEFAULT 'unknown'")
        if 'valid_until' not in {row['name'] for row in self.db.execute('PRAGMA table_info(offers)')}:
            self.db.execute('ALTER TABLE offers ADD COLUMN valid_until TEXT')
            for row in self.rows('SELECT * FROM offers'):
                self.db.execute('UPDATE offers SET valid_until=? WHERE id=?', (reading_valid_until(row), row['id']))
        for name in ('favorite', 'hidden'):
            if name not in {row['name'] for row in self.db.execute('PRAGMA table_info(offers)')}:
                self.db.execute(f'ALTER TABLE offers ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0')
        if 'coupon_price' not in {row['name'] for row in self.db.execute('PRAGMA table_info(observations)')}:
            self.db.execute('ALTER TABLE observations ADD COLUMN coupon_price INTEGER')
        for name, datatype in [('links', "TEXT NOT NULL DEFAULT '[]'"), ('message_url', 'TEXT'),
                               ('found_at', "TEXT NOT NULL DEFAULT ''")]:
            if name not in {row['name'] for row in self.db.execute('PRAGMA table_info(coupon_posts)')}:
                self.db.execute(f'ALTER TABLE coupon_posts ADD COLUMN {name} {datatype}')
        # Registros antigos só conheciam a publicação/consulta; tentativa não é descoberta.
        self.db.execute("UPDATE coupon_posts SET found_at=published_at WHERE found_at=''")
        known_coupons = {}
        for post in self.rows('SELECT codes,found_at FROM coupon_posts ORDER BY found_at'):
            for code in json.loads(post['codes']):
                known_coupons[code.strip().upper()] = post['found_at']
        for item in json.loads(self.get_setting('public_coupons', '[]')):
            known_coupons.setdefault(item.get('code', '').strip().upper(), item.get('found_at') or item.get('checked_at') or '')
        for code, stamp in known_coupons.items():
            self.db.execute("UPDATE ml_coupon_applications SET found_at=? WHERE code=? AND found_at=''", (stamp, code))
        if 'ignored_brands' not in {row['name'] for row in self.db.execute('PRAGMA table_info(components)')}:
            self.db.execute("ALTER TABLE components ADD COLUMN ignored_brands TEXT NOT NULL DEFAULT '[]'")
        for row in self.rows('SELECT id,title,message FROM offers WHERE brand IS NULL'):
            brand = detect_brand(row['title']) or detect_brand(row['message'] or '')
            if brand:
                self.db.execute('UPDATE offers SET brand=? WHERE id=?', (brand, row['id']))
        columns = {row['name'] for row in self.db.execute('PRAGMA table_info(alerts)')}
        for name, datatype in [('payment', 'TEXT'), ('price', 'INTEGER'), ('identity', 'TEXT'), ('notified', 'INTEGER NOT NULL DEFAULT 1')]:
            if name not in columns:
                self.db.execute(f'ALTER TABLE alerts ADD COLUMN {name} {datatype}')
        # Avisos antigos não guardavam preço: recuperar a última leitura anterior ao aviso.
        for alert in self.rows('SELECT * FROM alerts WHERE identity IS NULL'):
            offer = self.offer(alert['offer_id'])
            payment = alert_payment(offer)
            observations = self.rows('SELECT * FROM observations WHERE offer_id=? AND observed_at<=? ORDER BY id DESC LIMIT 1',
                                     (offer['id'], alert['delivered_at']))
            price = None
            if observations:
                reading = dict(observations[0], target=offer.get('target'), target_payment=offer.get('target_payment'))
                payment = alert_payment(reading)
                price = reading.get(payment)
            self.db.execute('UPDATE alerts SET payment=?,price=?,identity=? WHERE offer_id=? AND fingerprint=?',
                            (payment, price, self.alert_identity(offer), offer['id'], alert['fingerprint']))
        if self.get_setting('seeded') is None:
            for item in [('RTX 5060', 'gpu', 'rtx 5060', None), ('Corsair CX750', 'psu', 'corsair cx750', None),
                         ('Kingston NV3 1 TB', 'ssd', 'kingston nv3 1tb', 1000)]:
                self.db.execute('INSERT INTO components(name,kind,query,capacity_gb) VALUES(?,?,?,?)', item)
            self.db.execute('INSERT INTO sources(name,reference) VALUES(?,?)', ('Ofertas Adrenaline', '@ofertasadrenaline'))
            self.set_setting('seeded', '1')
        self.db.commit()

        for row in self.rows("SELECT id,url FROM offers WHERE shop='Amazon'"):
            if self.offer(row['id']):
                self.resolve_offer_url(row['id'], row['url'])

    def rows(self, sql: str, args=()) -> list[dict]:
        return [dict(row) for row in self.db.execute(sql, args)]

    def components(self) -> list[dict]:
        return self.rows('SELECT * FROM components ORDER BY id')

    def sources(self) -> list[dict]:
        return self.rows('SELECT * FROM sources ORDER BY id')

    def get_setting(self, key: str, default=None):
        row = self.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str):
        if key in ('public_coupons', 'pichau_coupons'):
            def identity(item):
                return (item.get('source'), item.get('url'), item.get('code'), item.get('activation'))
            previous = {identity(item): item.get('found_at') or item.get('checked_at')
                        for item in json.loads(self.get_setting(key, '[]'))}
            items = json.loads(value)
            for item in items:
                item['found_at'] = item.get('found_at') or previous.get(identity(item)) or item.get('checked_at') or utcnow()
            value = json.dumps(items, ensure_ascii=False)
        self.db.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))
        self.db.commit()

    def prune_coupons(self, now: datetime | None = None):
        """Apaga publicações, resultados e caches fora do dia atual; não altera ofertas."""
        for row in self.rows('SELECT source,message_id,found_at,published_at FROM coupon_posts'):
            if not coupon_is_today(row['found_at'] or row['published_at'], now):
                self.db.execute('DELETE FROM coupon_posts WHERE source=? AND message_id=?', (row['source'], row['message_id']))
        for row in self.rows('SELECT code,found_at FROM ml_coupon_applications'):
            if not coupon_is_today(row['found_at'], now):
                self.db.execute('DELETE FROM ml_coupon_applications WHERE code=?', (row['code'],))
        for key in ('public_coupons', 'pichau_coupons'):
            cached = self.get_setting(key)
            if cached is not None:
                items = json.loads(cached)
                today = [item for item in items if coupon_is_today(item.get('found_at') or item.get('checked_at'), now)]
                if today != items:
                    self.set_setting(key, json.dumps(today, ensure_ascii=False))
        self.db.commit()

    def save_component(self, name: str, kind: str, query: str, capacity_gb: int | None,
                       target: int | None, payment: str, component_id: int | None = None,
                       ignored_brands: list[str] | None = None):
        if not name.strip() or not query.strip() or kind not in {'gpu', 'psu', 'ssd', 'custom'}:
            raise ValueError('Informe o nome e a busca da peça.')
        if target is not None and target <= 0:
            raise ValueError('O preço máximo deve ser maior que zero.')
        if payment not in {'pix', 'card'}:
            raise ValueError('Escolha Pix ou total parcelado para o limite.')
        if ignored_brands is None:
            previous = self.db.execute('SELECT ignored_brands FROM components WHERE id=?', (component_id,)).fetchone()
            ignored_brands = json.loads(previous[0]) if previous else []
        if any(brand not in BRAND_ALIASES for brand in ignored_brands):
            raise ValueError('Escolha as marcas na lista de marcas ignoradas.')
        values = (name.strip(), kind, query.strip(), capacity_gb, target, payment,
                  json.dumps(list(dict.fromkeys(ignored_brands)), ensure_ascii=False))
        if component_id:
            self.db.execute('UPDATE components SET name=?,kind=?,query=?,capacity_gb=?,target=?,target_payment=?,ignored_brands=? WHERE id=?', values + (component_id,))
        else:
            self.db.execute('INSERT INTO components(name,kind,query,capacity_gb,target,target_payment,ignored_brands) VALUES(?,?,?,?,?,?,?)', values)
        self.db.commit()

    def save_source(self, name: str, reference: str):
        reference = reference.strip()
        markdown = re.fullmatch(r'\[[^\]]*\]\(([^)]+)\)', reference)
        if markdown:
            reference = markdown[1]
        if reference.startswith('https://t.me/'):
            reference = '@' + urlsplit(reference).path.strip('/').removeprefix('s/').split('/')[0]
        if reference.startswith('@') and re.fullmatch(r'@[A-Za-z0-9_]{5,}', reference):
            pass
        elif re.fullmatch(r'-[1-9]\d+', reference):
            pass
        else:
            raise ValueError('Use @nome, link público t.me/nome ou ID negativo de um grupo em que você já participa.')
        if not name.strip():
            raise ValueError('Informe o nome da fonte.')
        try:
            self.db.execute('INSERT INTO sources(name,reference) VALUES(?,?)', (name.strip(), reference))
            self.db.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError('Esta fonte já está cadastrada.') from exc

    def toggle(self, table: str, row_id: int, enabled: bool):
        if table not in {'components', 'sources'}:
            raise ValueError('Tabela inválida.')
        self.db.execute(f'UPDATE {table} SET enabled=? WHERE id=?', (int(enabled), row_id))
        self.db.commit()

    def delete(self, table: str, row_id: int):
        if table not in {'components', 'sources'}:
            raise ValueError('Tabela inválida.')
        self.db.execute(f'DELETE FROM {table} WHERE id=?', (row_id,))
        self.db.commit()

    def upsert_offer(self, component_id: int, offer: dict, origin: dict) -> tuple[dict, bool]:
        url = canonical_url(offer['url'])
        alias = self.db.execute('SELECT destination FROM url_aliases WHERE alias=?', (url,)).fetchone()
        if alias:
            url = alias['destination']
        old = self.db.execute('SELECT * FROM offers WHERE component_id=? AND url=?', (component_id, url)).fetchone()
        offer = dict(offer)
        offer['brand'] = offer.get('brand') or detect_brand(offer.get('title') or '') or detect_brand(offer.get('message') or '')
        if old and origin.get('chat_id') is None:
            offer['published_at'] = old['published_at']
            offer['message'] = old['message']
            offer['coupons'] = json.loads(old['coupons'])
            if offer['coupons']:
                offer['status'] = 'Preço da loja lido · cupom não validado'
        fingerprint = offer_fingerprint(offer)
        changed = old is None or old['fingerprint'] != fingerprint
        offer['valid_until'] = reading_valid_until(offer)
        fields = ('title', 'shop', 'seller', 'pix', 'card', 'announced', 'installments', 'installment',
                  'coupons', 'status', 'message', 'published_at', 'received_at', 'checked_at', 'availability', 'coupon_price', 'brand', 'shipping_origin', 'valid_until')
        values = [json.dumps(offer.get(key, []), ensure_ascii=False) if key == 'coupons'
                  else offer.get(key, 'unknown' if key in {'availability', 'shipping_origin'} else None) for key in fields]
        if old:
            self.db.execute('UPDATE offers SET ' + ','.join(f'{field}=?' for field in fields)
                            + ',fingerprint=? WHERE id=?', values + [fingerprint, old['id']])
            offer_id = old['id']
        else:
            cursor = self.db.execute('INSERT INTO offers(component_id,url,' + ','.join(fields)
                                     + ',fingerprint) VALUES(' + ','.join('?' for _ in range(len(fields) + 3)) + ')',
                                     [component_id, url] + values + [fingerprint])
            offer_id = cursor.lastrowid
        exists = self.db.execute('SELECT 1 FROM origins WHERE offer_id=? AND source=? AND message_id IS ?',
                                 (offer_id,origin['source'],origin.get('message_id'))).fetchone()
        if not exists:
            self.db.execute('INSERT INTO origins(offer_id,source,chat_id,message_id,message_url,published_at) VALUES(?,?,?,?,?,?)',
                            (offer_id, origin['source'], origin.get('chat_id'), origin.get('message_id'), origin.get('message_url'), origin['published_at']))
        latest = self.db.execute('SELECT observed_at FROM observations WHERE offer_id=? ORDER BY id DESC LIMIT 1', (offer_id,)).fetchone()
        new_day = not latest or datetime.fromisoformat(latest[0]).astimezone().date() != datetime.now().astimezone().date()
        if changed or confirmed_price(offer['status']) and new_day:
            self.db.execute('INSERT INTO observations(offer_id,observed_at,pix,card,announced,status,availability,coupon_price) VALUES(?,?,?,?,?,?,?,?)',
                            (offer_id, utcnow(), offer.get('pix'), offer.get('card'), offer.get('announced'), offer['status'], offer.get('availability', 'unknown'), offer.get('coupon_price')))
        self.db.commit()
        return self.offer(offer_id), changed

    def offer(self, offer_id: int) -> dict:
        row = self.rows('SELECT o.*,c.name component,c.target,c.target_payment,c.enabled FROM offers o JOIN components c ON c.id=o.component_id WHERE o.id=?', (offer_id,))
        return row[0] if row else {}

    def offers(self) -> list[dict]:
        return self.rows('''SELECT o.*,c.name component,
            EXISTS(SELECT 1 FROM origins WHERE offer_id=o.id AND chat_id IS NOT NULL) telegram_origin,
            (SELECT group_concat(DISTINCT source) FROM origins WHERE offer_id=o.id) origins
                            FROM offers o JOIN components c ON c.id=o.component_id ORDER BY o.received_at DESC''')

    def should_alert(self, offer: dict, fresh: bool) -> bool:
        return self.alert_evaluation(offer, fresh) is not None

    def set_offer_preference(self, offer_ids: list[int], preference: str, enabled: bool):
        if preference not in {'favorite', 'hidden'}:
            raise ValueError('Preferência inválida.')
        self.db.executemany(f'UPDATE offers SET {preference}=? WHERE id=?',
                            [(int(enabled), offer_id) for offer_id in set(offer_ids)])
        self.db.commit()

    def should_track_offer(self, offer: dict) -> bool:
        if not offer:
            return False
        part = next((row for row in self.components() if row['id'] == offer['component_id']), None)
        if not part or not part['enabled'] or offer.get('hidden') or offer.get('availability') == 'out' or offer.get('shipping_origin') == 'international':
            return False
        candidate = dict(offer)
        if candidate.get('shop') == 'Mercado Livre' and candidate.get('shipping_origin', 'unknown') == 'unknown':
            candidate['shipping_origin'] = 'local'  # Só permite primeira conferência; não entra no catálogo.
        if not offer_matches(part, candidate):
            return False
        rows = self.rows('SELECT * FROM offers WHERE component_id=?', (offer['component_id'],))
        selected = top_offers([part], rows, tracking_price)[part['id']]
        if len(selected) < 12:
            return True
        value = tracking_price(offer)
        # Sem preço conhecido, uma primeira leitura é necessária para decidir.
        cutoff = tracking_price(selected[-1])
        selected_id = any(offer.get('id') in row['duplicate_ids'] for row in selected)
        return value == float('inf') or 0 < value < cutoff or selected_id and 0 < value <= cutoff

    @staticmethod
    def alert_identity(offer: dict) -> str:
        return hashlib.sha256(json.dumps([offer['component_id'], *offer_group_key(offer)], ensure_ascii=False).encode()).hexdigest()

    def alert_evaluation(self, offer: dict, fresh: bool) -> dict | None:
        if not fresh or self.offer(offer['id']).get('hidden') or not price_is_current(offer) or not offer.get('enabled', True) or offer.get('availability') == 'out':
            return None
        part = next((part for part in self.components() if part['id'] == offer['component_id']), None)
        if not part or not offer_matches(part, offer):
            return None
        selected = top_offers([part], self.rows('SELECT * FROM offers WHERE component_id=?', (part['id'],)))[part['id']]
        if len(selected) == 12 and not any(offer['id'] in row['duplicate_ids'] for row in selected) and catalog_price(offer) >= catalog_price(selected[-1]):
            return None
        if offer.get('target') is not None:
            value = alert_price(offer, offer['target_payment'])
            if value is None or value > offer['target']:
                return None
        payment = alert_payment(offer)
        value = alert_price(offer, payment)
        if value is None or value <= 0:
            return None
        peers = [row for row in self.rows('SELECT * FROM offers WHERE component_id=? AND availability<>?',
                                         (offer['component_id'], 'out'))
                 if alert_price(row, payment) is not None and alert_price(row, payment) > 0 and price_is_current(row) and offer_matches(part, row)
                 and (payment != 'announced' or row.get('pix') is None and (row.get('card') is None or row['shop'] == 'Mercado Livre'))]
        grouped = group_offers([part], peers)[offer['component_id']]
        by_id = {row['id']: alert_price(row, payment) for row in peers}
        amounts = sorted(min(by_id[offer_id] for offer_id in row['duplicate_ids']) for row in grouped)
        # A oferta já está salva: participa da faixa, sem inflar a amostra com anúncios agrupados.
        if not amounts or value > amounts[(len(amounts) + 9) // 10 - 1]:
            return None
        if self.db.execute('SELECT 1 FROM alerts WHERE offer_id=? AND fingerprint=?',
                           (offer['id'], offer['fingerprint'])).fetchone():
            return None
        previous = self.db.execute('''SELECT * FROM alerts WHERE (offer_id=? OR identity=?)
            AND price>0 AND payment=? ORDER BY delivered_at DESC,rowid DESC LIMIT 1''',
            (offer['id'], self.alert_identity(offer), payment)).fetchone()
        if previous and value * 100 > previous['price'] * 98:
            return None
        # Sem referência recuperável, evitar repetir um aviso legado do mesmo anúncio.
        if not previous and self.db.execute('SELECT 1 FROM alerts WHERE offer_id=? AND price IS NULL AND notified=1', (offer['id'],)).fetchone():
            return None
        rank = 1 + sum(amount < value for amount in amounts)
        others = [by_id[item] for row in grouped for item in row['duplicate_ids']
                  if offer_group_key(row) != offer_group_key(offer)]
        reason = ('Única oferta comparável' if len(amounts) == 1 else
                  'Novo menor preço da peça' if others and value < min(others) else
                  f'Entre os 10% mais baratos · posição {rank} de {len(amounts)}')
        if offer.get('coupon_price') == value and value != offer.get(payment):
            reason += ' · com cupom na sua sessão'
        if previous:
            drop = (previous['price'] - value) * 100 / previous['price']
            reference = 'o último aviso' if previous['notified'] else 'a primeira confirmação'
            reason += f' · queda de {drop:.1f}% desde {reference}'
        history = self.price_history(offer['component_id'], payment)['30']
        if history['days'] >= 3 and value < history['median']:
            reason += f" · {(history['median'] - value) * 100 / history['median']:.1f}% abaixo da mediana de 30 dias"
        return dict(payment=payment, price=value, reason=reason, rank=rank, count=len(amounts))

    def price_history(self, component_id: int, payment: str, now: datetime | None = None) -> dict:
        if payment not in {'pix', 'card', 'announced', 'effective'}:
            raise ValueError('Pagamento inválido para o histórico.')
        part = next((part for part in self.components() if part['id'] == component_id), None)
        today = (now or datetime.now(timezone.utc)).astimezone().date()
        cutoff = today - timedelta(days=29)
        readings = self.rows('''SELECT o.*,h.observed_at,h.status observation_status,h.availability observation_availability,
            h.pix observed_pix,h.card observed_card,h.announced observed_announced,h.coupon_price observed_coupon,
            h.'''+('announced' if payment == 'effective' else payment)+''' history_price
            FROM observations h JOIN offers o ON o.id=h.offer_id WHERE o.component_id=? AND h.observed_at>=?''',
            (component_id, (cutoff - timedelta(days=1)).isoformat()))
        daily, counts = {}, {}
        for row in readings:
            value = row['history_price']
            if payment == 'effective':
                reading = dict(row, pix=row['observed_pix'], card=row['observed_card'], announced=row['observed_announced'], coupon_price=row['observed_coupon'])
                value = effective_price(reading)
                if value == float('inf'):
                    value = None
            if not part or not offer_matches(part, row) or not confirmed_price(row['observation_status'] or '') or row['observation_availability'] == 'out' or value is None or value <= 0:
                continue
            if payment == 'announced' and (row['observed_pix'] is not None or row['observed_card'] is not None and row['shop'] != 'Mercado Livre'):
                continue
            try:
                stamp = datetime.fromisoformat(row['observed_at'])
                day = stamp.astimezone().date()
            except (ValueError, TypeError):
                continue
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
                day = stamp.astimezone().date()
            if day < cutoff or day > today or stamp > (now or datetime.now(timezone.utc)):
                continue
            daily[day] = min(value, daily.get(day, value))
            counts[day] = counts.get(day, 0) + 1
        result = {'points': [{'date': day.isoformat(), 'price': daily[day]} for day in sorted(daily)]}
        for window in (7, 30):
            days = [day for day in daily if day >= today - timedelta(days=window - 1)]
            values = [daily[day] for day in days]
            result[str(window)] = dict(minimum=min(values) if values else None,
                median=int(median(values)) if values else None, days=len(days), readings=sum(counts[day] for day in days))
        return result

    def resolve_offer_url(self, offer_id: int, resolved_url: str) -> int:
        """Agrupa encurtadores diferentes quando a loja confirma o mesmo anúncio."""
        old = self.offer(offer_id)
        if not old:
            return offer_id
        url = canonical_url(resolved_url)
        if old['url'] != url:
            self.db.execute('INSERT INTO url_aliases VALUES(?,?) ON CONFLICT(alias) DO UPDATE SET destination=excluded.destination', (old['url'],url))
        existing = self.db.execute('SELECT id FROM offers WHERE component_id=? AND url=? AND id<>?',
                                   (old['component_id'], url, offer_id)).fetchone()
        if existing:
            destination = existing['id']
            target = self.offer(destination)
            codes = list(dict.fromkeys(json.loads(target['coupons']) + json.loads(old['coupons'])))
            self.db.execute('UPDATE offers SET coupons=?,message=COALESCE(message,?),published_at=? WHERE id=?',
                            (json.dumps(codes),old['message'],old['published_at'] if old['message'] and not target['message'] else target['published_at'],destination))
            self.db.execute('INSERT OR IGNORE INTO origins(offer_id,source,chat_id,message_id,message_url,published_at) SELECT ?,source,chat_id,message_id,message_url,published_at FROM origins WHERE offer_id=?', (destination,offer_id))
            self.db.execute('INSERT OR IGNORE INTO alerts(offer_id,fingerprint,delivered_at,payment,price,identity,notified) SELECT ?,fingerprint,delivered_at,payment,price,identity,notified FROM alerts WHERE offer_id=?', (destination,offer_id))
            self.db.execute('UPDATE observations SET offer_id=? WHERE offer_id=?', (destination,offer_id))
            self.db.execute('UPDATE offers SET favorite=?,hidden=? WHERE id=?',
                            (int(bool(target['favorite'] or old['favorite'])), int(bool(target['hidden'] or old['hidden'])), destination))
            self.db.execute('DELETE FROM offers WHERE id=?', (offer_id,))
            offer_id = destination
        else:
            self.db.execute('UPDATE offers SET url=? WHERE id=?', (url,offer_id))
        self.db.commit()
        return offer_id

    def mark_alert(self, offer: dict, notified: bool = True):
        payment = alert_payment(offer)
        self.db.execute('INSERT OR IGNORE INTO alerts(offer_id,fingerprint,delivered_at,payment,price,identity,notified) VALUES(?,?,?,?,?,?,?)',
                        (offer['id'], offer['fingerprint'], utcnow(), payment,
                         alert_price(offer, payment), self.alert_identity(offer), int(notified)))
        self.db.commit()

    def checkpoint(self, source_id: int, message_id: int):
        self.db.execute('UPDATE sources SET last_message=MAX(last_message,?) WHERE id=?', (message_id, source_id))
        self.db.execute('INSERT OR IGNORE INTO processed_messages VALUES(?,?,?)',(source_id,message_id,utcnow()))
        self.db.commit()

    def message_processed(self, source_id: int, message_id: int) -> bool:
        return self.db.execute('SELECT 1 FROM processed_messages WHERE source_id=? AND message_id=?', (source_id,message_id)).fetchone() is not None

    def remove_message(self, chat_id: int, message_ids: list[int]):
        for message_id in message_ids:
            rows = self.rows('SELECT offer_id FROM origins WHERE chat_id=? AND message_id=?', (chat_id, message_id))
            self.db.execute('DELETE FROM origins WHERE chat_id=? AND message_id=?', (chat_id, message_id))
            for row in rows:
                exists = self.db.execute('SELECT 1 FROM origins WHERE offer_id=?', (row['offer_id'],)).fetchone()
                if not exists:
                    self.db.execute("UPDATE offers SET status='Publicação removida' WHERE id=?", (row['offer_id'],))
        self.db.commit()

    def close(self):
        self.db.close()
