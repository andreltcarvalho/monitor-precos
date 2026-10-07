"""Perfil próprio do Chrome; login humano e consultas sem exportar cookies."""
import asyncio
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from bs4 import BeautifulSoup

from core import normalized, valid_url
from credentials import protect_data_dir


MELI_HOSTS = {'www.mercadolivre.com.br', 'mercadolivre.com.br',
              'lista.mercadolivre.com.br', 'produto.mercadolivre.com.br'}

COUPONS_URL = 'https://www.mercadolivre.com.br/cupons?source_page=mperfil'


def coupon_result(message):
    text = normalized(message)
    if re.search(r'(?:ja (?:foi |esta )?(?:adicionado|aplicado|inserido|ativado)|ja (?:tem|possui|adicionou|aplicou) (?:esse |este |o )?cupom|cupom ja esta na (?:sua )?conta)', text):
        return 'existing'
    if re.search(r'(?:cupom (?:foi )?(?:adicionado|aplicado|inserido|ativado)|(?:adicionamos|aplicamos|inserimos|ativamos|voce adicionou) (?:o |seu |um |esse )?cupom|(?:cupom|codigo).*com sucesso)', text):
        # "Não foi aplicado" e "não pode ser aplicado" não são sucesso.
        if not re.search(r'\bnao\b', text):
            return 'inserted'
    if re.search(r'(?:cupom|codigo).*(?:invalido|expirado|esgotado|esgotou|encerrado|nao existe|nao e valido|nao esta mais disponivel|nao se aplica (?:a|para) voce)|(?:invalido|expirado|esgotado).*(?:cupom|codigo)', text):
        return 'rejected'
    return 'pending'


def coupon_response(body):
    if not isinstance(body, dict) or not isinstance(body.get('responseMessage'), dict):
        return None
    message = body['responseMessage']
    text = next((message[key] for key in ('text', 'message', 'label', 'description')
                 if isinstance(message.get(key), str) and message[key].strip()), '')
    text = BeautifulSoup(text, 'html.parser').get_text(' ', strip=True)
    if message.get('type') == 'success':
        return 'inserted', (text or 'Mercado Livre confirmou a inserção deste código')[:500]
    if text and normalized(text) != 'spinner':
        return coupon_result(text), text[:500]
    return None


class BrowserAccessError(ValueError):
    def __init__(self, status: int):
        self.status = status
        messages = {
            401: 'Mercado Livre: login necessário (401). Abra a sessão na aba Fontes e entre novamente.',
            403: 'Mercado Livre bloqueou a consulta (403), mesmo com o perfil salvo. A sessão foi preservada; confira a página na janela do Chrome do monitor.',
            429: 'Mercado Livre limitou as consultas (429). Aguarde o próximo ciclo; a sessão foi preservada.',
            503: 'Mercado Livre está temporariamente indisponível (503). Aguarde o próximo ciclo; a sessão foi preservada.',
        }
        super().__init__(messages[status])


def chrome_executable():
    for base in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
        candidate = Path(os.environ.get(base, '')) / 'Google/Chrome/Application/chrome.exe'
        if candidate.is_file():
            return str(candidate)
    raise ValueError('Google Chrome não encontrado. Instale o Chrome para abrir a sessão do monitor.')


def validate_page(html: str, url: str):
    parsed = urlsplit(url)
    host = parsed.hostname or ''
    text = normalized(BeautifulSoup(html, 'html.parser').get_text(' ', strip=True))
    if host.startswith('auth.') or '/login' in parsed.path or any(marker in text for marker in (
            'para continuar, acesse sua conta', 'digite sua senha', 'informe seu e-mail')):
        raise ValueError('Mercado Livre: login necessário. Abra a sessão na aba Fontes e entre novamente.')
    if host not in MELI_HOSTS:
        raise ValueError('Mercado Livre abriu uma página de autenticação ou um destino não suportado. Confira a sessão na aba Fontes.')
    if any(marker in text for marker in ('confirme que voce nao e um robo', 'verifique que voce e humano', 'robot check')):
        raise ValueError('Mercado Livre pediu verificação humana. Abra a sessão na aba Fontes para conferir.')


class MercadoLivreBrowser:
    def __init__(self, profile: Path):
        self.profile = profile
        self.configured = (profile / 'monitor-enabled').exists()
        self.login_open = (profile / 'login-pending').exists()
        self._headless = not (profile / 'visible-required').exists()
        self.status = ('Login pendente · entre na conta, feche o Chrome do monitor e confirme a sessão' if self.login_open
                       else 'Perfil salvo · aguardando consulta' if self.configured else 'Sessão não configurada')
        self._driver = self._context = None
        self._login_process = None
        # O subprocesso do Playwright não depende do event loop do servidor Windows.
        # Todos os objetos da API síncrona ficam no mesmo thread.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='mercado-livre')

    async def _run(self, function, *args):
        return await asyncio.get_running_loop().run_in_executor(self._executor, function, *args)

    def _launch(self, headless: bool):
        try:
            from playwright.sync_api import sync_playwright
            if self._context:
                self._context.close()
                self._context = None
            protect_data_dir(self.profile)
            if not self._driver:
                self._driver = sync_playwright().start()
            self._context = self._driver.chromium.launch_persistent_context(
                str(self.profile), channel='chrome', headless=headless, chromium_sandbox=True,
                accept_downloads=False, locale='pt-BR', timeout=20000,
                viewport={'width': 1280, 'height': 900})
            self._headless = headless
            context = self._context
            def closed(_):
                if self._context is context:
                    self._context = None
            context.on('close', closed)
        except Exception as exc:
            if any(marker in str(exc) for marker in ('ProcessSingleton', 'profile is already in use', 'exitCode=21')):
                self.status = 'O Chrome do monitor ainda está aberto. Feche suas janelas e clique Confirmar sessão novamente. Seu login permanece salvo; o Chrome pessoal pode continuar aberto.'
            else:
                self.status = 'Não foi possível abrir o Chrome do monitor. Confira se o Google Chrome está instalado, feche todas as janelas do Chrome do monitor e tente novamente.'
            raise ValueError(self.status) from None

    async def open_login(self):
        await self._run(self._open_login)

    def _open_login(self):
        if self._login_process and self._login_process.poll() is None:
            self.status = 'Janela já aberta · entre na conta, feche o Chrome do monitor e confirme a sessão'
            return
        try:
            if self._context:
                self._context.close()
                self._context = None
            protect_data_dir(self.profile)
            # Login humano no Chrome normal, sem Playwright nem porta de depuração.
            self._login_process = subprocess.Popen([
                chrome_executable(), '--user-data-dir=' + str(self.profile.resolve()),
                '--no-first-run', '--no-default-browser-check', '--new-window',
                'https://www.mercadolivre.com.br/'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            (self.profile / 'login-pending').write_text('1', encoding='ascii')
        except ValueError:
            raise
        except Exception:
            raise ValueError('Não foi possível abrir o Chrome para login. Feche a janela do monitor e tente novamente.') from None
        self.login_open = True
        self.status = 'Chrome aberto · entre na conta, feche essa janela e clique Confirmar sessão'

    def _read_page(self, url: str):
        if not valid_url(url) or urlsplit(url).hostname not in MELI_HOSTS or urlsplit(url).port not in {None, 443}:
            raise ValueError('O navegador do monitor consulta somente páginas HTTPS do Mercado Livre.')
        page = None
        try:
            # Fechar a última aba do Chrome com janela encerra o contexto inteiro.
            pages = self._context.pages if not self._headless else []
            page = next((tab for tab in pages if not tab.is_closed()), None) or self._context.new_page()
            def navigation(route):
                request = route.request
                if request.is_navigation_request() and request.frame == page.main_frame:
                    destination = request.url
                    if (not valid_url(destination) or urlsplit(destination).hostname not in
                            MELI_HOSTS | {'auth.mercadolivre.com.br'} or urlsplit(destination).port not in {None, 443}):
                        route.abort()
                        return
                route.continue_()
            page.unroute('**/*')
            page.route('**/*', navigation)
            response = page.goto(url, wait_until='domcontentloaded', timeout=30000)
            blocked = response and response.status in {401, 403, 429, 503}
            # Espera o conteúdo útil da busca/produto, sem esperar anúncios e analytics.
            if not blocked:
                try:
                    page.locator('h1, a[href*="/MLB"], a[href*="/p/MLB"]').first.wait_for(timeout=5000)
                except Exception:
                    pass
            html, resolved = page.content(), page.url
            if len(html.encode()) > 6_000_000:
                raise ValueError('Página do Mercado Livre acima do limite de leitura.')
            validate_page(html, resolved)
            if blocked:
                raise BrowserAccessError(response.status)
            return html, resolved
        except ValueError:
            raise
        except Exception:
            raise ValueError('Falha ao consultar o Mercado Livre pelo navegador. Confira a sessão na aba Fontes.') from None
        finally:
            try:
                if page and self._headless:
                    page.close()
            except Exception:
                pass

    def _read_with_fallback(self, url: str):
        try:
            result = self._read_page(url)
        except BrowserAccessError as exc:
            if exc.status != 403 or not self._headless:
                raise
            # Mesmo perfil, Chrome com janela: não altera login nem resolve captcha.
            self.status = 'Consulta sem janela bloqueada · testando Chrome com janela'
            self._launch(headless=False)
            result = self._read_page(url)
        if not self._headless:
            (self.profile / 'visible-required').write_text('1', encoding='ascii')
        return result

    async def confirm(self, component: dict):
        return await self._run(self._confirm, component)

    def _confirm(self, component):
        from shops import search_links
        if not self.login_open:
            raise ValueError('Abra a sessão do Mercado Livre e entre na conta primeiro.')
        if self._login_process and self._login_process.poll() is None:
            self.status = 'Após entrar na conta, feche todas as janelas do Chrome do monitor e clique Confirmar sessão novamente. Seu Chrome pessoal pode continuar aberto.'
            raise ValueError(self.status)
        url = 'https://lista.mercadolivre.com.br/' + quote(component['query'].replace(' ', '-'))
        try:
            self._launch(headless=self._headless)
            html, resolved = self._read_with_fallback(url)
            if not search_links(html, resolved, component):
                raise ValueError('A sessão ainda não retornou anúncios legíveis. Confira o login no Chrome e tente Confirmar sessão novamente.')
        except ValueError as exc:
            if self._context:
                self._context.close()
                self._context = None
            self.status = str(exc)
            raise
        (self.profile / 'monitor-enabled').write_text('1', encoding='ascii')
        (self.profile / 'login-pending').unlink(missing_ok=True)
        self.configured = True
        self.login_open = False
        self.status = ('Consulta pelo navegador habilitada · sessão salva neste PC' if self._headless
                       else 'Consulta pelo Chrome com janela habilitada · sessão salva neste PC')

    async def fetch(self, url: str):
        return await self._run(self._fetch, url)

    async def apply_coupon(self, code: str):
        return await self._run(self._apply_coupon, code)

    def _apply_coupon(self, code):
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{2,39}', code):
            raise ValueError('Código de cupom inválido.')
        if self.login_open or not self.configured:
            raise ValueError('Confirme a sessão do Mercado Livre na aba Fontes.')
        if not self._context or self._headless:
            self._launch(headless=False)
        # Mesmo perfil e mesmas restrições de navegação das buscas existentes.
        page = next((tab for tab in self._context.pages if not tab.is_closed()), None)
        if not page or urlsplit(page.url).hostname not in MELI_HOSTS or urlsplit(page.url).path != '/cupons':
            self._read_page(COUPONS_URL)
            page = next(tab for tab in self._context.pages if not tab.is_closed())
        validate_page(page.content(), page.url)
        opener = page.get_by_role('button', name=re.compile(r'^Inserir c[oó]digo$', re.I))
        field = page.get_by_placeholder(re.compile(r'Ins(?:erir|ira).*c[oó]digo.*cupom', re.I))
        if not field.is_visible() and not opener.is_visible():
            # Após sucesso, Meus cupons pode manter /cupons sem o formulário.
            # Reabrir antes do próximo código não repete a inserção confirmada.
            self._read_page(COUPONS_URL)
            page = next(tab for tab in self._context.pages if not tab.is_closed())
            validate_page(page.content(), page.url)
            opener = page.get_by_role('button', name=re.compile(r'^Inserir c[oó]digo$', re.I))
            field = page.get_by_placeholder(re.compile(r'Ins(?:erir|ira).*c[oó]digo.*cupom', re.I))
        if not field.is_visible():
            opener.click(timeout=10000)
            try:
                field.wait_for(state='visible', timeout=3000)
            except Exception:
                # Repete apenas a abertura após hidratação, nunca o envio.
                validate_page(page.content(), page.url)
                opener.click(timeout=10000)
        try:
            field.fill('', timeout=10000)
            field.fill(code, timeout=10000)
        except Exception:
            raise ValueError('Mercado Livre não abriu o campo de cupom; tentativa pendente, sem envio do código') from None
        feedback = page.locator('[role="alert"], [role="status"], [role="dialog"], .andes-form-control__message, .andes-snackbar')

        def messages():
            result = []
            for item in feedback.all():
                if item.is_visible():
                    lines = [line.strip() for line in item.inner_text().splitlines()
                             if normalized(line.strip()) not in {'', 'cupons', 'inserir', 'erro', 'spinner'}]
                    message = '\n'.join(dict.fromkeys(lines))
                    if message:
                        result.append(message)
            return sorted(result, key=len)

        before = set(messages())
        # A mesma recusa pode voltar para dois códigos: observar renovação do
        # feedback evita confundir uma resposta repetida com a resposta antiga.
        page.evaluate('''() => {
            const selector = '[role="alert"], .andes-form-control__message, .andes-snackbar';
            const matches = node => node.nodeType === 1 && (node.matches(selector) || node.querySelector(selector));
            window.__monitorCouponFeedback?.observer.disconnect();
            const state = {changed: false};
            state.observer = new MutationObserver(records => {
                if (records.some(record => {
                    const target = record.target.nodeType === 1 ? record.target : record.target.parentElement;
                    return target?.closest(selector) || [...record.addedNodes, ...record.removedNodes].some(matches);
                })) state.changed = true;
            });
            state.observer.observe(document.body, {subtree: true, childList: true, characterData: true});
            window.__monitorCouponFeedback = state;
        }''')
        # Só feedback visível novo pode confirmar a alteração; catálogo não serve de prova.
        from time import monotonic
        deadline = monotonic() + 20
        last_feedback = None
        confirmed_response = []
        submission_url = page.url

        def activated_redirect():
            destination = urlsplit(page.url)
            return (page.url != submission_url and destination.scheme == 'https' and
                    destination.hostname in {'www.mercadolivre.com.br', 'mercadolivre.com.br'} and
                    destination.port in {None, 443} and destination.path == '/cupons/active' and
                    parse_qs(destination.query).get('source_page') == ['int_input_code'])

        def finish(result):
            redirected = activated_redirect()
            if redirected and result[0] == 'pending':
                result = redirect_result
            if result[0] == 'inserted' or redirected:
                try:
                    self._read_page(COUPONS_URL)
                except Exception:
                    pass  # Falha ao reabrir não desfaz uma inserção já confirmada.
            return result

        redirect_result = ('inserted', 'Mercado Livre redirecionou para Meus cupons após inserir este código')

        def submitted_response(response):
            request = response.request
            if (urlsplit(response.url).hostname not in MELI_HOSTS or
                    urlsplit(response.url).path != '/cupons/api/input-code' or request.method != 'POST'):
                return
            try:
                if json.loads(request.post_data or '{}').get('coupon_input_code') != code:
                    return
                if response.status == 200:
                    result = coupon_response(response.json())
                    if result:
                        confirmed_response.append(result)
            except Exception:
                pass  # Resposta sem confirmação utilizável continua pela tela.

        page.on('response', submitted_response)
        try:
            try:
                page.get_by_role('button', name='Inserir', exact=True).click(timeout=10000)
            except Exception:
                if confirmed_response:
                    return finish(confirmed_response[-1])
                if activated_redirect():
                    return finish(redirect_result)
                raise
            while monotonic() < deadline:
                if confirmed_response:
                    return finish(confirmed_response[-1])
                if activated_redirect():
                    return finish(redirect_result)
                try:
                    validate_page(page.content(), page.url)
                    renewed = page.evaluate('() => window.__monitorCouponFeedback?.changed === true') is True
                    current_messages = messages()
                except ValueError:
                    raise  # Login/verificação não são sucesso.
                except Exception:
                    if confirmed_response:
                        return finish(confirmed_response[-1])
                    if activated_redirect():
                        return finish(redirect_result)
                    if page.is_closed():
                        break
                    page.wait_for_timeout(250)
                    continue  # Navegação do site pode destruir temporariamente o contexto.
                for message in current_messages:
                    if message in before and not renewed:
                        continue
                    if last_feedback is None or len(message) < len(last_feedback):
                        last_feedback = message
                    status = coupon_result(message)
                    if status != 'pending':
                        return finish((status, message[:500]))
                    if re.search(r'tivemos um problema|tente novamente|temporariamente indisponivel', normalized(message)):
                        return finish(('pending', message[:500]))
                page.wait_for_timeout(250)
            if confirmed_response:
                return finish(confirmed_response[-1])
            if activated_redirect():
                return finish(redirect_result)
            return finish(('pending', (last_feedback or 'Mercado Livre não confirmou a inserção; confira a janela do Chrome do monitor')[:500]))
        finally:
            try:
                page.remove_listener('response', submitted_response)
                page.evaluate('''() => {
                    window.__monitorCouponFeedback?.observer.disconnect();
                    delete window.__monitorCouponFeedback;
                }''')
            except Exception:
                pass  # A página pode mudar após a resposta; limpeza não invalida o resultado.

    def _fetch(self, url):
        if self.login_open:
            raise ValueError('Login do Mercado Livre em andamento. Depois de entrar, feche o Chrome do monitor e clique Confirmar sessão na aba Fontes.')
        if not self.configured:
            raise ValueError('Mercado Livre: login necessário. Abra a sessão na aba Fontes.')
        try:
            if not self._context:
                self._launch(headless=self._headless)
            result = self._read_with_fallback(url)
            self.status = ('Consulta pelo navegador disponível' if self._headless
                           else 'Consulta pelo Chrome com janela disponível')
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
