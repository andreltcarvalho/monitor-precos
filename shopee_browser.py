"""Sessão própria da Shopee, com login humano e leitura pelo Chrome instalado."""
import asyncio
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote, urlsplit

from bs4 import BeautifulSoup

from core import normalized, valid_url
from credentials import protect_data_dir
from mercado_livre_browser import chrome_executable


SHOPEE_HOSTS = {'shopee.com.br', 'www.shopee.com.br'}


def validate_shopee_page(html, url):
    if not valid_url(url) or urlsplit(url).hostname not in SHOPEE_HOSTS or urlsplit(url).port not in {None, 443}:
        raise ValueError('O Chrome da Shopee consulta somente páginas HTTPS da Shopee Brasil.')
    if urlsplit(url).path.startswith('/verify/captcha'):
        raise ValueError('Shopee bloqueou a consulta automática e abriu verificação de segurança. O perfil foi preservado; confira a página no Chrome da Shopee antes de tentar confirmar novamente. Não é ausência de peças.')
    text = normalized(BeautifulSoup(html, 'html.parser').get_text(' ', strip=True))
    if 'tente novamente mais tarde' in text:
        raise ValueError('Shopee bloqueou a consulta automática: Tente Novamente Mais Tarde. O perfil foi preservado; aguarde e tente Confirmar sessão novamente. Não é ausência de peças.')
    if '/buyer/login' in urlsplit(url).path or 'login necessario' in text or 'faca login para continuar' in text:
        raise ValueError('Shopee exige login. Abra e confirme a sessão na aba Fontes.')
    if any(marker in text for marker in ('verifique que voce e humano', 'verificacao de seguranca', 'confirme que voce nao e um robo', 'captcha')):
        raise ValueError('Shopee pediu verificação humana. Abra a sessão na aba Fontes e confira a página.')


class ShopeeBrowser:
    def __init__(self, profile: Path):
        self.profile = profile
        self.configured = (profile / 'monitor-enabled').exists()
        self.login_open = (profile / 'login-pending').exists()
        self.status = ('Shopee: login pendente · feche o Chrome e confirme a sessão' if self.login_open
                       else 'Perfil salvo · aguardando consulta' if self.configured else 'Shopee: login necessário na aba Fontes')
        self._driver = self._context = self._login_process = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='shopee')

    async def _run(self, action, *args):
        return await asyncio.get_running_loop().run_in_executor(self._executor, action, *args)

    async def open_login(self):
        await self._run(self._open_login)

    def _open_login(self):
        if self._login_process and self._login_process.poll() is None:
            return
        if self._context:
            self._context.close()
            self._context = None
        protect_data_dir(self.profile)
        self._login_process = subprocess.Popen([
            chrome_executable(), '--user-data-dir=' + str(self.profile.resolve()),
            '--no-first-run', '--no-default-browser-check', '--new-window', 'https://shopee.com.br/buyer/login'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (self.profile / 'login-pending').write_text('1', encoding='ascii')
        self.login_open = True
        self.status = 'Shopee: login em andamento · entre na conta, feche essa janela e confirme a sessão'

    def _read(self, url):
        validate_shopee_page('', url)
        page = None
        try:
            if not self._context:
                from playwright.sync_api import sync_playwright
                protect_data_dir(self.profile)
                if not self._driver:
                    self._driver = sync_playwright().start()
                self._context = self._driver.chromium.launch_persistent_context(
                    str(self.profile), channel='chrome', headless=False, chromium_sandbox=True,
                    accept_downloads=False, locale='pt-BR', viewport={'width': 1280, 'height': 900}, timeout=20000)
                context = self._context
                def closed(_):
                    if self._context is context:
                        self._context = None
                context.on('close', closed)
            page = next((tab for tab in self._context.pages if not tab.is_closed()), None) or self._context.new_page()
            def navigation(route):
                request = route.request
                destination = urlsplit(request.url)
                if request.is_navigation_request() and request.frame == page.main_frame and (
                        not valid_url(request.url) or destination.hostname not in SHOPEE_HOSTS or destination.port not in {None, 443}):
                    route.abort()
                    return
                route.continue_()
            page.unroute('**/*')
            page.route('**/*', navigation)
            response = page.goto(url, wait_until='domcontentloaded', timeout=30000)
            if response and response.status in {401, 403, 429, 503}:
                raise ValueError(f'Shopee recusou a consulta ({response.status}). Sessão e anúncios preservados; confira Fontes.')
            try:
                ready = 'a[href*="-i."], a[href*="/product/"]' if urlsplit(url).path == '/search' else 'script[type="application/ld+json"]'
                page.wait_for_function('''selector => /login necessário|faça login para continuar|verificação de segurança|tente novamente mais tarde|nenhum resultado|nenhum produto|não encontramos|sem resultados/i.test(document.body?.innerText || '') || [...document.querySelectorAll(selector)].some(element => selector.startsWith('script') || (element.innerText || element.title || element.querySelector('img')?.alt || '').trim())''', arg=ready, timeout=12000)
            except Exception:
                pass
            html, resolved = page.content(), page.url
            if len(html.encode()) > 6_000_000:
                raise ValueError('Página da Shopee acima do limite de leitura.')
            validate_shopee_page(html, resolved)
            return html, resolved
        except ValueError:
            raise
        except Exception:
            if self._context:
                try:
                    self._context.close()
                except Exception:
                    pass
                self._context = None
            raise ValueError('Falha no Chrome da Shopee. Feche as janelas desse perfil e confira a sessão na aba Fontes.') from None

    async def confirm(self, component):
        try:
            await self._run(self._confirm, component)
        except ValueError as exc:
            self.status = str(exc)
            raise

    def _confirm(self, component):
        from shops import search_links
        if not self.login_open and not self.configured:
            raise ValueError('Abra a sessão da Shopee na aba Fontes e entre na conta antes de confirmar.')
        if self._login_process and self._login_process.poll() is None:
            raise ValueError('Feche a janela de login da Shopee antes de confirmar a sessão.')
        html, resolved = self._read('https://shopee.com.br/search?keyword=' + quote(component['query']))
        validate_shopee_page(html, resolved)
        # A sessão não depende do modelo ou da disponibilidade da primeira peça.
        if not any(urlsplit(link).hostname in SHOPEE_HOSTS for link in search_links(html, resolved, None)):
            text = normalized(BeautifulSoup(html, 'html.parser').get_text(' ', strip=True))
            if any(marker in text for marker in ('nenhum resultado', 'nenhum produto', 'nao encontramos', 'sem resultados')):
                html, resolved = self._read('https://shopee.com.br/search?keyword=ssd')
                validate_shopee_page(html, resolved)
            if not any(urlsplit(link).hostname in SHOPEE_HOSTS for link in search_links(html, resolved, None)):
                raise ValueError('Shopee não carregou uma busca com produtos legíveis. A sessão foi preservada; confira a página no Chrome da Shopee e tente confirmar novamente. Isso não confirma erro de login nem ausência das suas peças.')
        (self.profile / 'monitor-enabled').write_text('1', encoding='ascii')
        (self.profile / 'login-pending').unlink(missing_ok=True)
        self.configured = True
        self.login_open = False
        self.status = 'Sessão Shopee salva · consultas pelo Chrome com janela'

    async def fetch(self, url):
        if self.login_open or not self.configured:
            raise ValueError('Shopee: login necessário. Abra a sessão, entre na conta, feche o Chrome e confirme na aba Fontes.')
        try:
            result = await self._run(self._read, url)
            self.status = 'Consulta Shopee pelo Chrome disponível'
            return result
        except ValueError as exc:
            self.status = str(exc)
            raise

    async def close(self):
        try:
            if self._driver:
                await self._run(self._close)
        finally:
            self._executor.shutdown(wait=False, cancel_futures=True)

    def _close(self):
        try:
            if self._context:
                self._context.close()
        finally:
            self._context = None
            if self._driver:
                self._driver.stop()
                self._driver = None
