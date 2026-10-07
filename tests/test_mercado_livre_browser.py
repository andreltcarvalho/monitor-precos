import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from mercado_livre_browser import MercadoLivreBrowser, validate_page
from shops import Shops


SEARCH = 'https://lista.mercadolivre.com.br/rtx-5060'
PRODUCT = 'https://produto.mercadolivre.com.br/MLB-123456789-placa-rtx-5060-_JM'
RESULTS = f'<h1>RTX 5060</h1><a href="{PRODUCT}">MSI RTX 5060 8GB</a>'
COMPONENT = {'query': 'rtx 5060', 'kind': 'gpu'}


class PageValidationTests(unittest.TestCase):
    def test_login_redirect_and_form_are_actionable(self):
        for html, url in [('', 'https://auth.mercadolivre.com.br/login'),
                          ('', 'https://www.mercadolivre.com.br/jms/mlb/lgz/login'),
                          ('<h1>Para continuar, acesse sua conta</h1>', SEARCH)]:
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, 'login necessário'):
                validate_page(html, url)

    def test_human_verification_is_not_an_offer(self):
        with self.assertRaisesRegex(ValueError, 'verificação humana'):
            validate_page('<h1>Verifique que você é humano</h1>', SEARCH)

    def test_foreign_destination_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'destino não suportado'):
            validate_page(RESULTS, 'https://example.com/')


class BrowserSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.profile = Path(self.temp.name) / 'mercado-livre'
        self.browser = MercadoLivreBrowser(self.profile)
        self.context = MagicMock()
        self.context.pages = []
        self.page = MagicMock()
        self.page.url = SEARCH
        self.page.content.return_value = RESULTS
        self.page.goto.return_value = SimpleNamespace(status=200)
        self.context.new_page.return_value = self.page
        self.driver = MagicMock()
        self.driver.chromium.launch_persistent_context.return_value = self.context
        self.launcher = patch('playwright.sync_api.sync_playwright')
        self.launcher.start().return_value.start.return_value = self.driver
        self.protection = patch('mercado_livre_browser.protect_data_dir',
                                side_effect=lambda path: path.mkdir(parents=True, exist_ok=True))
        self.protection.start()
        self.chrome = patch('mercado_livre_browser.chrome_executable', return_value='C:/Chrome/chrome.exe')
        self.chrome.start()
        self.process = MagicMock()
        self.process.poll.return_value = None
        self.spawn = patch('mercado_livre_browser.subprocess.Popen', return_value=self.process)
        self.popen = self.spawn.start()

    async def asyncTearDown(self):
        await self.browser.close()
        self.launcher.stop()
        self.protection.stop()
        self.chrome.stop()
        self.spawn.stop()
        self.temp.cleanup()

    async def confirm(self):
        self.process.poll.return_value = 0
        await self.browser.confirm(COMPONENT)

    async def test_unconfigured_browser_does_not_start_chrome(self):
        with self.assertRaisesRegex(ValueError, 'login necessário'):
            await self.browser.fetch(SEARCH)
        self.driver.chromium.launch_persistent_context.assert_not_called()

    async def test_human_login_then_background_read_uses_same_saved_profile(self):
        await self.browser.open_login()
        args = self.popen.call_args.args[0]
        self.assertIn('--user-data-dir=' + str(self.profile.resolve()), args)
        self.assertFalse(any('debugging' in arg or 'automation' in arg for arg in args))
        self.driver.chromium.launch_persistent_context.assert_not_called()
        await self.confirm()
        self.assertTrue(self.browser.configured)
        self.assertTrue((self.profile / 'monitor-enabled').exists())
        self.assertFalse(self.browser.login_open)
        self.context.close.assert_not_called()
        html, url = await self.browser.fetch(SEARCH)
        options = self.driver.chromium.launch_persistent_context.call_args
        self.assertEqual(options.args, (str(self.profile),))
        self.assertTrue(options.kwargs['headless'])
        self.assertEqual(options.kwargs['channel'], 'chrome')
        self.assertEqual((html, url), (RESULTS, SEARCH))
        reopened = MercadoLivreBrowser(self.profile)
        try:
            self.assertTrue(reopened.configured)
        finally:
            await reopened.close()

    async def test_confirmation_retries_403_with_window_and_remembers_success(self):
        await self.browser.open_login()
        self.page.goto.side_effect = [SimpleNamespace(status=403), SimpleNamespace(status=200)]
        await self.confirm()
        launches = self.driver.chromium.launch_persistent_context.call_args_list
        self.assertEqual([call.kwargs['headless'] for call in launches], [True, False])
        self.assertTrue(all(call.args == (str(self.profile),) for call in launches))
        self.assertTrue((self.profile / 'visible-required').exists())
        self.assertTrue((self.profile / 'monitor-enabled').exists())
        self.assertFalse((self.profile / 'login-pending').exists())
        self.assertIn('Chrome com janela habilitada', self.browser.status)

    async def test_fetch_retries_403_once_and_keeps_window_for_next_read(self):
        await self.browser.open_login()
        await self.confirm()
        self.page.goto.side_effect = [SimpleNamespace(status=403), SimpleNamespace(status=200),
                                     SimpleNamespace(status=200)]
        self.assertEqual(await self.browser.fetch(SEARCH), (RESULTS, SEARCH))
        self.assertEqual(await self.browser.fetch(PRODUCT), (RESULTS, SEARCH))
        self.assertEqual(self.driver.chromium.launch_persistent_context.call_count, 2)
        self.assertIn('Chrome com janela disponível', self.browser.status)

    async def test_visible_reads_keep_and_reuse_tab_so_chrome_remains_alive(self):
        await self.browser.open_login()
        self.page.goto.side_effect = [SimpleNamespace(status=403), SimpleNamespace(status=200)]
        await self.confirm()
        self.page.goto.side_effect = None
        self.context.pages = [self.page]
        self.page.is_closed.return_value = False
        self.context.new_page.reset_mock()
        self.page.close.reset_mock()
        for _ in range(2):
            self.assertEqual(await self.browser.fetch(SEARCH), (RESULTS, SEARCH))
        self.context.new_page.assert_not_called()
        self.page.close.assert_not_called()
        self.page.unroute.assert_called_with('**/*')

    async def test_late_close_of_old_context_does_not_clear_new_context(self):
        await self.browser.open_login()
        await self.confirm()
        old_close_handler = self.context.on.call_args.args[1]
        replacement = MagicMock()
        self.driver.chromium.launch_persistent_context.return_value = replacement
        await self.browser._run(self.browser._launch, False)
        old_close_handler(self.context)
        self.assertIs(self.browser._context, replacement)
        replacement.on.call_args.args[1](replacement)
        self.assertIsNone(self.browser._context)

    async def test_closed_context_during_tab_creation_has_safe_actionable_error(self):
        await self.browser.open_login()
        await self.confirm()
        self.context.new_page.side_effect = RuntimeError('private session detail')
        with self.assertRaisesRegex(ValueError, '^Falha ao consultar') as failure:
            await self.browser.fetch(SEARCH)
        self.assertNotIn('private', str(failure.exception))

    async def test_restart_uses_saved_window_mode_without_repeating_hidden_request(self):
        await self.browser.open_login()
        self.page.goto.side_effect = [SimpleNamespace(status=403), SimpleNamespace(status=200)]
        await self.confirm()
        await self.browser.close()
        self.driver.chromium.launch_persistent_context.reset_mock()
        self.page.goto.side_effect = None
        reopened = MercadoLivreBrowser(self.profile)
        try:
            self.assertEqual(await reopened.fetch(SEARCH), (RESULTS, SEARCH))
            self.driver.chromium.launch_persistent_context.assert_called_once()
            self.assertFalse(self.driver.chromium.launch_persistent_context.call_args.kwargs['headless'])
        finally:
            await reopened.close()

    async def test_403_in_both_modes_preserves_session_without_enabling_failed_confirmation(self):
        await self.browser.open_login()
        (self.profile / 'session-preserved').write_text('existing profile')
        self.page.goto.return_value = SimpleNamespace(status=403)
        with self.assertRaisesRegex(ValueError, 'bloqueou a consulta.*403'):
            await self.confirm()
        self.assertEqual(self.page.goto.call_count, 2)
        self.assertFalse((self.profile / 'monitor-enabled').exists())
        self.assertFalse((self.profile / 'visible-required').exists())
        self.assertTrue((self.profile / 'login-pending').exists())
        self.assertEqual((self.profile / 'session-preserved').read_text(), 'existing profile')
        self.assertNotIn('login necessário', self.browser.status)

    async def test_failed_visible_retry_preserves_previously_enabled_session(self):
        await self.browser.open_login()
        await self.confirm()
        self.page.goto.side_effect = [SimpleNamespace(status=403), RuntimeError('private session detail')]
        with self.assertRaisesRegex(ValueError, 'Falha ao consultar'):
            await self.browser.fetch(SEARCH)
        self.assertTrue((self.profile / 'monitor-enabled').exists())
        self.assertFalse((self.profile / 'visible-required').exists())
        self.assertNotIn('private', self.browser.status)

    async def test_other_http_errors_do_not_launch_window_or_repeat_request(self):
        await self.browser.open_login()
        await self.confirm()
        for status, message in [(401, 'login necessário'), (429, 'limitou as consultas'),
                                (503, 'temporariamente indisponível')]:
            self.page.goto.reset_mock()
            self.page.goto.return_value = SimpleNamespace(status=status)
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, message):
                await self.browser.fetch(SEARCH)
            self.page.goto.assert_called_once()
            self.assertEqual(self.driver.chromium.launch_persistent_context.call_count, 1)
            self.assertTrue((self.profile / 'monitor-enabled').exists())

    async def test_visible_403_is_not_retried_again(self):
        await self.browser.open_login()
        (self.profile / 'visible-required').write_text('1')
        self.browser._headless = False
        self.page.goto.return_value = SimpleNamespace(status=403)
        with self.assertRaisesRegex(ValueError, 'bloqueou a consulta'):
            await self.confirm()
        self.page.goto.assert_called_once()
        self.assertEqual(self.driver.chromium.launch_persistent_context.call_count, 1)
        self.assertTrue((self.profile / 'visible-required').exists())

    async def test_403_verification_and_login_pages_keep_specific_diagnosis(self):
        await self.browser.open_login()
        self.page.goto.return_value = SimpleNamespace(status=403)
        for html, message in [('<h1>Verifique que você é humano</h1>', 'verificação humana'),
                              ('<h1>Para continuar, acesse sua conta</h1>', 'login necessário')]:
            self.page.goto.reset_mock()
            self.page.content.return_value = html
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                await self.confirm()
            self.page.goto.assert_called_once()
            self.assertTrue((self.profile / 'login-pending').exists())
            self.assertFalse((self.profile / 'monitor-enabled').exists())
        self.assertTrue(all(call.kwargs['headless'] for call in
                            self.driver.chromium.launch_persistent_context.call_args_list))

    async def test_login_pauses_fetch_without_changing_the_page(self):
        await self.browser.open_login()
        self.page.goto.reset_mock()
        with self.assertRaisesRegex(ValueError, 'Login.*em andamento'):
            await self.browser.fetch(SEARCH)
        self.page.goto.assert_not_called()

    async def test_reopening_login_does_not_reset_login_form(self):
        await self.browser.open_login()
        await self.browser.open_login()
        self.popen.assert_called_once()
        self.driver.chromium.launch_persistent_context.assert_not_called()

    async def test_confirmation_without_open_window_does_not_enable_profile(self):
        with self.assertRaisesRegex(ValueError, 'Abra a sessão'):
            await self.confirm()
        self.assertFalse((self.profile / 'monitor-enabled').exists())

    async def test_blocked_confirmation_keeps_human_window_and_profile_disabled(self):
        await self.browser.open_login()
        self.page.content.return_value = '<h1>Para continuar, acesse sua conta</h1>'
        with self.assertRaisesRegex(ValueError, 'login necessário'):
            await self.confirm()
        self.assertFalse(self.browser.configured)
        self.assertTrue(self.browser.login_open)
        self.context.close.assert_called_once()
        self.assertFalse((self.profile / 'monitor-enabled').exists())

    async def test_empty_search_cannot_confirm_session(self):
        await self.browser.open_login()
        self.page.content.return_value = '<h1>RTX 5060</h1>'
        with self.assertRaisesRegex(ValueError, 'anúncios legíveis'):
            await self.confirm()
        self.assertFalse(self.browser.configured)

    async def test_expired_session_reports_login_without_removing_saved_profile(self):
        await self.browser.open_login()
        await self.confirm()
        self.page.content.return_value = '<h1>Para continuar, acesse sua conta</h1>'
        with self.assertRaisesRegex(ValueError, 'login necessário'):
            await self.browser.fetch(SEARCH)
        self.assertIn('login necessário', self.browser.status)
        self.assertTrue((self.profile / 'monitor-enabled').exists())

    async def test_network_failure_closes_query_page_and_hides_sensitive_exception(self):
        await self.browser.open_login()
        await self.confirm()
        self.page.goto.side_effect = RuntimeError('private session token')
        self.page.close.side_effect = RuntimeError('closed')
        with self.assertRaisesRegex(ValueError, '^Falha ao consultar') as failure:
            await self.browser.fetch(SEARCH)
        self.assertNotIn('private', str(failure.exception))
        self.page.close.assert_called()

    async def test_chrome_failure_is_actionable_without_exposing_driver_error(self):
        self.driver.chromium.launch_persistent_context.side_effect = RuntimeError('private profile path')
        with self.assertRaisesRegex(ValueError, 'Google Chrome está instalado') as failure:
            await self.browser.open_login()
            await self.confirm()
        self.assertNotIn('private', str(failure.exception))

    async def test_profile_in_use_after_restart_has_specific_recovery_without_secrets(self):
        self.profile.mkdir()
        (self.profile / 'login-pending').write_text('1')
        self.browser.login_open = True
        for marker in ('Failed to create a ProcessSingleton', 'profile is already in use', 'process did exit: exitCode=21'):
            self.driver.chromium.launch_persistent_context.side_effect = RuntimeError(marker + ' private session detail')
            with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, 'Chrome do monitor ainda está aberto') as failure:
                await self.browser.confirm(COMPONENT)
            self.assertNotIn('private', str(failure.exception))
            self.assertEqual(self.browser.status, str(failure.exception))
            self.assertTrue((self.profile / 'login-pending').exists())
            self.assertFalse(self.browser.configured)

    async def test_browser_does_not_navigate_to_external_or_local_entry(self):
        await self.browser.open_login()
        await self.confirm()
        self.page.goto.reset_mock()
        for url in ['https://127.0.0.1/', 'https://example.com/', 'https://user@lista.mercadolivre.com.br/',
                    'http://lista.mercadolivre.com.br/', 'https://lista.mercadolivre.com.br:8443/']:
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, 'somente páginas HTTPS'):
                await self.browser.fetch(url)
        self.page.goto.assert_not_called()

    async def test_redirect_navigation_to_local_host_is_aborted(self):
        await self.browser.open_login()
        await self.confirm()
        await self.browser.fetch(SEARCH)
        handler = self.page.route.call_args.args[1]
        route = MagicMock()
        route.request.url = 'https://127.0.0.1/private'
        route.request.is_navigation_request.return_value = True
        route.request.frame = self.page.main_frame
        handler(route)
        route.abort.assert_called_once()
        route.continue_.assert_not_called()

    async def test_monitor_shutdown_closes_chrome_and_driver(self):
        await self.browser.open_login()
        await self.confirm()
        await self.browser._run(self.browser._close)
        self.context.close.assert_called_once()
        self.driver.stop.assert_called_once()

    async def test_confirmation_requires_closing_human_chrome_without_killing_it(self):
        await self.browser.open_login()
        with self.assertRaisesRegex(ValueError, 'feche todas as janelas'):
            await self.browser.confirm(COMPONENT)
        self.driver.chromium.launch_persistent_context.assert_not_called()
        self.process.terminate.assert_not_called()
        self.assertFalse(self.browser.configured)
        self.assertIn('feche todas as janelas', self.browser.status)

    async def test_native_chrome_spawn_failure_does_not_enable_login(self):
        self.popen.side_effect = OSError('private process detail')
        with self.assertRaisesRegex(ValueError, 'Não foi possível abrir o Chrome') as failure:
            await self.browser.open_login()
        self.assertNotIn('private', str(failure.exception))
        self.assertFalse(self.browser.login_open)

    async def test_restart_keeps_login_pending_and_success_clears_it(self):
        await self.browser.open_login()
        reopened = MercadoLivreBrowser(self.profile)
        try:
            self.assertTrue(reopened.login_open)
            with self.assertRaisesRegex(ValueError, 'Login.*em andamento'):
                await reopened.fetch(SEARCH)
        finally:
            await reopened.close()
        await self.confirm()
        self.assertFalse((self.profile / 'login-pending').exists())


class CollectorRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_mercado_livre_uses_configured_browser(self):
        with tempfile.TemporaryDirectory() as folder:
            shops = Shops(Path(folder))
            shops.ml_browser.configured = True
            shops.ml_browser.fetch = AsyncMock(return_value=(RESULTS, SEARCH))
            await shops.client.aclose()
            shops.client = httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, text='Pichau page')))
            try:
                self.assertEqual(await shops.fetch(SEARCH), (RESULTS, SEARCH))
                self.assertEqual(await shops.fetch('https://www.pichau.com.br/search?q=rtx'),
                                 ('Pichau page', 'https://www.pichau.com.br/search?q=rtx'))
                shops.ml_browser.fetch.assert_awaited_once_with(SEARCH)
            finally:
                await shops.close()

    async def test_login_in_progress_does_not_fall_back_to_anonymous_request(self):
        with tempfile.TemporaryDirectory() as folder:
            shops = Shops(Path(folder))
            shops.ml_browser.login_open = True
            shops.client.get = AsyncMock()
            try:
                with self.assertRaisesRegex(ValueError, 'Login.*em andamento'):
                    await shops.fetch(SEARCH)
                shops.client.get.assert_not_awaited()
            finally:
                await shops.close()
