"""Buscas locais na OLX, independentes do catálogo e ranking de peças."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import subprocess
from time import monotonic
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup
import httpx

from core import brl, money, normalized, utcnow
from credentials import protect_data_dir
from mercado_livre_browser import chrome_executable

STATES = 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split()
HOSTS = {'olx.com.br', 'www.olx.com.br'} | {uf.lower() + '.olx.com.br' for uf in STATES}


def search_url(search) -> str:
    url = olx_url(search.get('resolved_url') or search['url'])
    if search.get('state') == 'SP' and normalized(search.get('city') or '').strip() == 'piracicaba':
        # Rota municipal verificada na OLX; não depende do seletor indisponível.
        parsed = urlsplit(url)
        prefix = parsed.path.split('/estado-sp', 1)[0] if '/estado-sp' in parsed.path else ''
        url = olx_url(urlunsplit((parsed.scheme, parsed.netloc,
            prefix + '/estado-sp/grande-campinas/piracicaba', parsed.query, '')))
    return url


def city_confirmed(html: str, city: str) -> bool:
    summary = BeautifulSoup(html, 'html.parser').select_one('#total-of-ads h1')
    return bool(summary and re.search(r'(?:\bem\s+|-\s*)' + re.escape(normalized(city).strip()) + r'(?:\s*,|\s*$)',
                                     normalized(summary.get_text(' ', strip=True))))


def olx_url(value: str, listing=False) -> str:
    try:
        parsed = urlsplit(value.strip())
        valid = (parsed.scheme == 'https' and parsed.hostname in HOSTS and
                 parsed.port in {None, 443} and not parsed.username and not parsed.password)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Use um link HTTPS de busca da OLX Brasil.')
    if listing and not re.search(r'-\d{8,}$', parsed.path.rstrip('/')):
        raise ValueError('O link não identifica um anúncio da OLX.')
    if not listing and (re.search(r'-\d{8,}$', parsed.path.rstrip('/')) or
                        parsed.path.endswith('.htm') or not parsed.path.strip('/')):
        raise ValueError('Cole o link dos resultados de uma busca, não um anúncio individual.')
    query = [(k, v) for k, v in parse_qsl(parsed.query) if k not in {'sf', 'o', 'utm_source', 'utm_medium', 'utm_campaign'}]
    if listing:
        query = []
    else:
        query.append(('sf', '1'))
    return urlunsplit(('https', parsed.hostname, parsed.path.rstrip('/'), urlencode(query), ''))


def search_input(name, mode, url='', query='', state='SP', city='', target='', excluded='') -> dict:
    if not (name or '').strip():
        raise ValueError('Dê um nome para identificar esta busca.')
    limit = None
    if (target or '').strip():
        if not re.fullmatch(r'(?:R\$\s*)?(?:\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:[,.]\d{1,2})?)', target.strip()):
            raise ValueError('Use um preço máximo como 700,00, ou deixe vazio.')
        limit = money(target)
        if limit is None or limit <= 0:
            raise ValueError('O preço máximo deve ser maior que zero.')
    if mode == 'fields':
        if not (query or '').strip() or state not in STATES or not (city or '').strip():
            raise ValueError('Informe o produto, a UF e a cidade.')
        params = {'q': query.strip(), 'sf': '1'}
        if limit is not None:
            params['pe'] = str((limit + 99) // 100)
        url = 'https://www.olx.com.br/estado-' + state.lower() + '?' + urlencode(params)
    elif mode == 'link':
        city, state, query = '', '', ''
    else:
        raise ValueError('Escolha cadastro por link ou por produto e cidade.')
    fields = dict(name=name.strip(), url=olx_url(url), city=city.strip(), state=state,
                  query=query.strip(), target=limit, excluded=(excluded or '').strip())
    fields['url'] = search_url(fields)
    return fields


def validate_page(html: str, url: str):
    olx_url(url)
    soup = BeautifulSoup(html, 'html.parser')
    title = normalized(soup.title.get_text(' ', strip=True) if soup.title else '')
    if any(marker in title for marker in ('attention required', 'just a moment', 'access denied')) or soup.select_one('#challenge-form, #cf-challenge-running'):
        raise ValueError('OLX pediu verificação humana ou bloqueou a leitura. Abra o Chrome da OLX e confira a busca; os anúncios salvos foram preservados.')
    return soup


def parse_search(html: str, url: str, city: str = '') -> list[dict]:
    soup = validate_page(html, url)
    cards = soup.select('section.olx-adcard')
    summary = soup.select_one('#total-of-ads')
    if not cards:
        text = normalized(summary.get_text(' ', strip=True) if summary else soup.get_text(' ', strip=True))
        if any(marker in text for marker in ('0 resultados', 'nenhum resultado', 'nao encontramos resultados', 'nao encontramos anuncios')):
            return []
        raise ValueError('A OLX não apresentou cartões de anúncios legíveis. A consulta não foi tratada como busca vazia.')
    results, seen = [], set()
    for card in cards[:50]:
        anchor = card.select_one('a[data-testid="adcard-link"]')
        if not anchor:
            continue
        try:
            href = olx_url(anchor.get('href', ''), listing=True)
        except ValueError:
            continue
        ad_id = re.search(r'-(\d{8,})$', urlsplit(href).path)[1]
        if ad_id in seen:
            continue
        seen.add(ad_id)
        def text(selector):
            element = card.select_one(selector)
            return element.get_text(' ', strip=True) if element else ''
        title = anchor.get('title', '').strip() or anchor.get_text(' ', strip=True)
        price_text = text('.olx-adcard__price')
        # Somente o preço principal do cartão, nunca parcela ou preço riscado.
        price = money(price_text) if re.fullmatch(r'R\$\s*[\d.,\s]+', price_text) else None
        if not title:
            continue
        results.append(dict(ad_id=ad_id, url=href, title=title, price=price if price and price > 0 else None,
                            location=text('.olx-adcard__location'), published_text=text('.olx-adcard__date')))
    if not results:
        raise ValueError('Os cartões da OLX não contêm anúncios identificáveis. Última leitura preservada.')
    return [row for row in results if not city or normalized(row['location'].split(',')[0].strip()) == normalized(city).strip()]


def eligible(search, listing):
    price = listing['price']
    if price is None or price <= 0 or search['target'] is not None and price > search['target']:
        return False
    if search.get('city') and normalized(listing['location'].split(',')[0].strip()) != normalized(search['city']):
        return False
    title = normalized(listing['title'])
    return not any(normalized(term.strip()) in title for term in search['excluded'].split(',') if term.strip())


class OlxCollector:
    def __init__(self, profile: Path):
        self.profile = profile
        self.client = httpx.AsyncClient(timeout=25, follow_redirects=False)
        self.browser_required = False
        self.status = 'Aguardando consulta'
        self._driver = self._context = self._human = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='olx')

    async def _run(self, action, *args):
        return await asyncio.get_running_loop().run_in_executor(self._executor, action, *args)

    async def search(self, search):
        url = search_url(search)
        if not self.browser_required and (not search['city'] or search['resolved_url']):
            try:
                for _ in range(4):
                    response = await self.client.get(url)
                    if response.is_redirect:
                        url = olx_url(str(response.url.join(response.headers.get('location', ''))))
                        continue
                    response.raise_for_status()
                    if len(response.content) > 6_000_000:
                        raise ValueError('Página da OLX acima do limite de leitura.')
                    if search['city'] and not city_confirmed(response.text, search['city']):
                        raise ValueError('A OLX não confirmou a cidade na busca; última leitura preservada.')
                    results = parse_search(response.text, url, search['city'])
                    self.status = 'Leitura direta'
                    return results, url
                raise ValueError('A OLX redirecionou a busca muitas vezes.')
            except (ValueError, httpx.HTTPError):
                self.browser_required = True
        results, resolved = await self._run(self._search_browser, search, url)
        self.status = 'Leitura pelo Chrome da OLX'
        return results, resolved

    def _page(self):
        if self._human and self._human.poll() is None:
            raise ValueError('Feche a janela humana do Chrome da OLX antes de consultar novamente.')
        if not self._context:
            from playwright.sync_api import sync_playwright
            protect_data_dir(self.profile)
            if not self._driver:
                self._driver = sync_playwright().start()
            self._context = self._driver.chromium.launch_persistent_context(
                str(self.profile.resolve()), channel='chrome', headless=False, timeout=20000,
                chromium_sandbox=True, accept_downloads=False, locale='pt-BR',
                viewport={'width': 1280, 'height': 900})
            context = self._context
            def closed(_):
                if self._context is context:
                    self._context = None
            context.on('close', closed)
        page = next((tab for tab in self._context.pages if not tab.is_closed()), None) or self._context.new_page()
        def navigation(route):
            request = route.request
            if request.is_navigation_request() and request.frame == page.main_frame:
                try:
                    olx_url(request.url)
                except ValueError:
                    route.abort()
                    return
            route.continue_()
        page.unroute('**/*')
        page.route('**/*', navigation)
        return page

    def _search_browser(self, search, url):
        try:
            page = self._page()
            response = page.goto(olx_url(url), wait_until='domcontentloaded', timeout=30000)
            if response and response.status >= 400:
                raise ValueError(f'OLX recusou a consulta ({response.status}). Abra o Chrome da OLX para conferir; última leitura preservada.')
            validate_page(page.content(), page.url)
            if search['city'] and not city_confirmed(page.content(), search['city']):
                page.get_by_role('button', name=re.compile('Alterar localização atual:')).click(timeout=12000)
                page.get_by_role('textbox', name='Busque por estado, região, cidade ou bairro', exact=True).fill(search['city'])
                # O seletor oficial resolve região/cidade; não adivinhamos slugs.
                pattern = re.compile(r'^' + re.escape(search['city']) + r'\s+em\s+', re.I)
                choice = page.get_by_role('button', name=pattern)
                choice.first.wait_for(state='visible', timeout=12000)
                if choice.count() != 1:
                    raise ValueError('A OLX retornou cidades ambíguas. Cadastre pelo link da busca com a localização selecionada.')
                before = page.url
                choice.click()
                page.wait_for_url(lambda value: str(value) != before, wait_until='domcontentloaded', timeout=15000)
            try:
                page.wait_for_selector('section.olx-adcard, #total-of-ads', timeout=12000)
            except Exception:
                pass
            html = page.content()
            if len(html.encode()) > 6_000_000:
                raise ValueError('Página da OLX acima do limite de leitura.')
            resolved = olx_url(page.url)
            if search['city']:
                if not city_confirmed(html, search['city']):
                    raise ValueError('A OLX não confirmou a cidade na busca. Use o link com a região já selecionada.')
            return parse_search(html, resolved, search['city']), resolved
        except ValueError:
            raise
        except Exception:
            self._close_browser()
            raise ValueError('Falha no Chrome da OLX. Abra o Chrome da OLX, confira a busca e feche a janela antes de consultar novamente.') from None

    async def open_browser(self, url):
        await self._run(self._open_browser, olx_url(url))

    def _open_browser(self, url):
        if self._human and self._human.poll() is None:
            return
        self._close_browser()
        protect_data_dir(self.profile)
        self._human = subprocess.Popen([
            chrome_executable(), '--user-data-dir=' + str(self.profile.resolve()),
            '--no-first-run', '--no-default-browser-check', '--new-window', url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _close_browser(self):
        if self._context:
            try:
                self._context.close()
            finally:
                self._context = None

    async def close(self):
        await self.client.aclose()
        def close():
            self._close_browser()
            if self._driver:
                self._driver.stop()
                self._driver = None
        await self._run(close)
        self._executor.shutdown(wait=False)


class OlxMonitor:
    def __init__(self, store, data_dir: Path, notify):
        self.store, self.notify = store, notify
        self.collector = OlxCollector(data_dir / 'olx-profile')
        self.lock = asyncio.Lock()
        self.status = 'Cadastre uma busca para acompanhar a OLX'
        self.store.db.executescript('''
            CREATE TABLE IF NOT EXISTS olx_searches (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
                query TEXT NOT NULL, state TEXT NOT NULL, city TEXT NOT NULL,
                target INTEGER, excluded TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
                baseline TEXT, resolved_url TEXT, checked_at TEXT, status TEXT NOT NULL DEFAULT 'Aguardando primeira consulta');
            CREATE TABLE IF NOT EXISTS olx_listings (
                id INTEGER PRIMARY KEY, search_id INTEGER NOT NULL REFERENCES olx_searches(id) ON DELETE CASCADE,
                ad_id TEXT NOT NULL, url TEXT NOT NULL, title TEXT NOT NULL, price INTEGER,
                location TEXT NOT NULL, published_text TEXT NOT NULL, first_seen TEXT NOT NULL,
                checked_at TEXT NOT NULL, reference_price INTEGER, pending TEXT,
                UNIQUE(search_id,ad_id));
            CREATE TABLE IF NOT EXISTS olx_observations (
                id INTEGER PRIMARY KEY, listing_id INTEGER NOT NULL REFERENCES olx_listings(id) ON DELETE CASCADE,
                price INTEGER, observed_at TEXT NOT NULL);
        ''')

    def searches(self):
        return self.store.rows('SELECT * FROM olx_searches ORDER BY id')

    def save_search(self, **draft):
        fields = search_input(**draft)
        cursor = self.store.db.execute('INSERT INTO olx_searches(name,url,query,state,city,target,excluded) VALUES(?,?,?,?,?,?,?)',
                                       tuple(fields[key] for key in ('name', 'url', 'query', 'state', 'city', 'target', 'excluded')))
        self.store.db.commit()
        return cursor.lastrowid

    def listings(self, search_id):
        return self.store.rows('SELECT * FROM olx_listings WHERE search_id=? ORDER BY checked_at DESC,first_seen DESC,id ASC', (search_id,))

    def ingest(self, search, listings, resolved):
        stamp = utcnow()
        for item in listings:
            old = self.store.rows('SELECT * FROM olx_listings WHERE search_id=? AND ad_id=?', (search['id'], item['ad_id']))
            row = old[0] if old else None
            reference = row['reference_price'] if row else item['price']
            pending = row['pending'] if row else ('new' if search['baseline'] else None)
            if row and reference is not None and item['price'] is not None:
                if item['price'] < reference:
                    pending = 'drop' if pending != 'new' else pending
                elif pending == 'drop':
                    pending = None
            values = tuple(item[key] for key in ('url', 'title', 'price', 'location', 'published_text'))
            if row:
                self.store.db.execute('UPDATE olx_listings SET url=?,title=?,price=?,location=?,published_text=?,checked_at=?,pending=? WHERE id=?',
                                      values + (stamp, pending, row['id']))
                listing_id = row['id']
            else:
                cursor = self.store.db.execute('INSERT INTO olx_listings(search_id,ad_id,url,title,price,location,published_text,first_seen,checked_at,reference_price,pending) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                                               (search['id'], item['ad_id']) + values + (stamp, stamp, reference, pending))
                listing_id = cursor.lastrowid
            if not row or row['price'] != item['price']:
                self.store.db.execute('INSERT INTO olx_observations(listing_id,price,observed_at) VALUES(?,?,?)', (listing_id, item['price'], stamp))
            if row and reference is None and item['price'] is not None:
                self.store.db.execute('UPDATE olx_listings SET reference_price=? WHERE id=?', (item['price'], listing_id))
        self.store.db.execute('UPDATE olx_searches SET baseline=COALESCE(baseline,?),resolved_url=?,checked_at=?,status=? WHERE id=?',
                              (stamp, resolved, stamp, f'{len(listings)} anúncios lidos · {self.collector.status}', search['id']))
        self.store.db.commit()
        return stamp

    async def scan(self, search_id=None):
        if self.lock.locked():
            return False
        async with self.lock:
            targets = [search for search in self.searches() if search['enabled'] and
                       (search_id is None or search['id'] == search_id)]
            if not targets:
                self.status = 'Nenhuma busca OLX ativa' if self.searches() else 'Cadastre uma busca para acompanhar a OLX'
                return True
            for search in targets:
                self.status = 'Consultando OLX · ' + search['name']
                try:
                    listings, resolved = await self.collector.search(search)
                    # A busca pode ter sido pausada/removida durante a leitura.
                    active = self.store.rows('SELECT * FROM olx_searches WHERE id=? AND enabled=1', (search['id'],))
                    if not active:
                        continue
                    stamp = self.ingest(active[0], listings, resolved)
                    for item in self.listings(search['id']):
                        if not self.store.rows('SELECT id FROM olx_searches WHERE id=? AND enabled=1', (search['id'],)):
                            break
                        if item['checked_at'] != stamp or not item['pending'] or not eligible(search, item):
                            continue
                        reason = 'Novo anúncio encontrado' if item['pending'] == 'new' else 'Preço caiu de ' + brl(item['reference_price'])
                        try:
                            await asyncio.to_thread(self.notify, dict(component=search['name'] + ' · ' + item['title'],
                                pix=None, card=None, announced=item['price'], shop='OLX · ' + (item['location'] or 'Localização não informada'),
                                alert_reason=reason, status='Preço anunciado', url=item['url']))
                            self.store.db.execute('UPDATE olx_listings SET pending=NULL,reference_price=? WHERE id=?', (item['price'], item['id']))
                            self.store.db.commit()
                        except Exception:
                            self.store.db.execute('UPDATE olx_searches SET status=? WHERE id=?', ('Windows não aceitou o aviso; anúncio salvo e tentativa pendente', search['id']))
                            self.store.db.commit()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    detail = str(exc) if isinstance(exc, (ValueError, httpx.HTTPError)) else 'Falha ao consultar a OLX; anúncios salvos preservados'
                    self.store.db.execute('UPDATE olx_searches SET status=? WHERE id=?', (detail, search['id']))
                    self.store.db.commit()
            self.status = 'Consultas OLX concluídas · consulte o resultado de cada busca'
            return True

    async def loop(self):
        while True:
            started = monotonic()
            await self.scan()
            await asyncio.sleep(max(0, 600 - (monotonic() - started)))
