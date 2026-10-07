import asyncio
from asyncio import sleep as real_sleep
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from core import Store, coupon_is_today, utcnow
from mercado_livre_browser import COUPONS_URL, MercadoLivreBrowser, coupon_result, coupon_response
from ml_coupon_applicator import CouponApplicator, application_state


class ResultTests(unittest.TestCase):
    def test_failure_types_and_retry_guidance(self):
        for detail, failure, retryable in [
            ('Este cupom não se aplica a você.', 'Não elegível para sua conta', False),
            ('Código expirado', 'Expirado', False),
            ('O cupom esgotou.', 'Indisponível / esgotado', False),
            ('Cupom inválido', 'Código inválido', False),
            ('Tivemos um problema', 'Erro temporário', True),
            ('Login necessário', 'Sessão / bloqueio', True),
            ('Falha no navegador', 'Falha no navegador', True),
            ('Resposta não reconhecida', 'Sem confirmação', True),
            ('Tentativa iniciada; aguardando confirmação do site', 'Tentativa interrompida', True),
        ]:
            with self.subTest(detail=detail):
                state = application_state(dict(status='pending', detail=detail))
                self.assertEqual((state['group'], state['failure'], state['retryable']), ('failed', failure, retryable))
                self.assertTrue(state['guidance'])
        self.assertEqual(coupon_result('O cupom esgotou. Há outros disponíveis.'), 'rejected')

    def test_activation_and_disabled_states_do_not_claim_eligibility(self):
        for status in ('inserted', 'existing'):
            state = application_state(dict(status=status, detail=''))
            self.assertEqual(state['group'], 'active')
            self.assertFalse(state['retryable'])
            self.assertIn('condições', state['guidance'])
        state = application_state(dict(status='pending', detail='Erro temporário', disabled=1))
        self.assertEqual(state['group'], 'disabled')
        self.assertFalse(state['retryable'])
        self.assertEqual(application_state(dict(status='pending', detail=''), applying=True)['label'], 'Aplicando agora')

    def test_official_response_confirms_success_and_preserves_known_errors(self):
        self.assertEqual(coupon_response({'responseMessage': {'type': 'success', 'text': 'Cupom adicionado!'}}),
                         ('inserted', 'Cupom adicionado!'))
        self.assertEqual(coupon_response({'responseMessage': {'type': 'error', 'text': 'Este cupom já foi adicionado.'}}),
                         ('existing', 'Este cupom já foi adicionado.'))
        self.assertEqual(coupon_response({'responseMessage': {'type': 'error', 'text': 'Este cupom não se aplica a você.'}}),
                         ('rejected', 'Este cupom não se aplica a você.'))

    def test_empty_or_unknown_response_is_not_confirmation(self):
        for body in [None, {}, {'coupon': {'code': 'TESTE10'}}, {'responseMessage': {'type': 'error'}},
                     {'responseMessage': {'type': 'loading', 'text': 'spinner'}}]:
            self.assertIsNone(coupon_response(body))
        self.assertEqual(coupon_response({'responseMessage': {'type': 'error', 'text': 'Tivemos um problema'}}),
                         ('pending', 'Tivemos um problema'))
    def test_only_explicit_success_and_existing_are_confirmed(self):
        for message in ['Cupom adicionado!', 'Você adicionou um cupom', 'Código inserido com sucesso']:
            self.assertEqual(coupon_result(message), 'inserted')
        for message in ['Você já adicionou esse cupom', 'Cupom já está na sua conta', 'Cupom já foi aplicado']:
            self.assertEqual(coupon_result(message), 'existing')

    def test_expired_and_negative_messages_are_not_success(self):
        for message in ['Cupom inválido', 'Código expirado', 'Cupom já expirado']:
            self.assertEqual(coupon_result(message), 'rejected')
        for message in ['Cupom não foi aplicado', 'Tente novamente', 'Inserir código', 'Cupons disponíveis']:
            self.assertEqual(coupon_result(message), 'pending')

    def test_personal_ineligibility_is_an_explicit_rejection(self):
        for message in ['Este cupom não se aplica a você.', 'Este cupom não se aplica para você.']:
            self.assertEqual(coupon_result(message), 'rejected')

    def test_browser_submits_only_the_coupon_form_and_reads_new_feedback(self):
        with tempfile.TemporaryDirectory() as temp:
            browser = MercadoLivreBrowser(Path(temp))
            browser.configured, browser._headless = True, False
            page = MagicMock()
            page.is_closed.return_value = False
            page.url = COUPONS_URL
            page.content.return_value = '<h1>Cupons</h1>'
            feedback = MagicMock()
            feedback.is_visible.return_value = True
            feedback.inner_text.side_effect = ['Cupons', 'Cupom adicionado!']
            page.locator.return_value.all.return_value = [feedback]
            browser._context = MagicMock(pages=[page])
            browser._read_page = MagicMock()
            page.evaluate.side_effect = [None, False, RuntimeError('Contexto encerrado após confirmação')]
            try:
                self.assertEqual(browser._apply_coupon('TESTE10')[0], 'inserted')
                self.assertEqual([call.args[0] for call in page.get_by_placeholder.return_value.fill.call_args_list], ['', 'TESTE10'])
                self.assertEqual(page.get_by_role.call_args.kwargs, dict(name='Inserir', exact=True))
                browser._read_page.assert_called_once_with(COUPONS_URL)
            finally:
                browser._executor.shutdown(wait=False)

    def test_invalid_code_and_unconfigured_session_do_not_submit(self):
        with tempfile.TemporaryDirectory() as temp:
            browser = MercadoLivreBrowser(Path(temp))
            browser._launch = MagicMock()
            try:
                for code in ['BAD CODE', 'VALID10']:
                    with self.assertRaises(ValueError):
                        browser._apply_coupon(code)
                browser._launch.assert_not_called()
            finally:
                browser._executor.shutdown(wait=False)

    def test_browser_preserves_ineligibility_and_unknown_site_errors(self):
        for message, status in [('Este cupom não se aplica a você.', 'rejected'),
                                ('Não foi possível validar este cupom agora.', 'pending')]:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as temp:
                browser = MercadoLivreBrowser(Path(temp))
                browser.configured, browser._headless = True, False
                page = MagicMock()
                page.is_closed.return_value = False
                page.url = COUPONS_URL
                page.content.return_value = '<h1>Cupons</h1>'
                feedback = MagicMock()
                feedback.is_visible.return_value = True
                feedback.inner_text.side_effect = ['Cupons\nInserir', f'Cupons\n{message}\nInserir\nErro\n{message}']
                page.locator.return_value.all.return_value = [feedback]
                browser._context = MagicMock(pages=[page])
                browser._read_page = MagicMock()
                try:
                    with patch('time.monotonic', side_effect=[0, 1, 21]):
                        self.assertEqual(browser._apply_coupon('TESTE10'), (status, message))
                finally:
                    browser._executor.shutdown(wait=False)

    def test_rejection_reuses_page_and_success_reopens_it(self):
        with tempfile.TemporaryDirectory() as temp:
            browser = MercadoLivreBrowser(Path(temp))
            browser.configured, browser._headless = True, False
            page = MagicMock()
            page.is_closed.return_value = False
            page.url = 'https://www.mercadolivre.com.br/'
            page.content.return_value = '<h1>Cupons</h1>'
            feedback = MagicMock()
            feedback.is_visible.return_value = True
            feedback.inner_text.side_effect = ['Cupons', 'Cupom inválido', 'Cupons', 'Cupom adicionado!']
            page.locator.return_value.all.return_value = [feedback]
            browser._context = MagicMock(pages=[page])
            browser._read_page = MagicMock(side_effect=lambda url: setattr(page, 'url', url))
            try:
                self.assertEqual(browser._apply_coupon('INVALIDO10')[0], 'rejected')
                browser._read_page.assert_called_once_with(COUPONS_URL)
                self.assertEqual(browser._apply_coupon('VALIDO10')[0], 'inserted')
                self.assertEqual(browser._read_page.call_count, 2)
                self.assertEqual([call.args[0] for call in page.get_by_placeholder.return_value.fill.call_args_list],
                                 ['', 'INVALIDO10', '', 'VALIDO10'])
            finally:
                browser._executor.shutdown(wait=False)

    def test_success_redirect_reopens_initial_page_immediately_and_continues(self):
        for destination in [COUPONS_URL + '&filter=my_coupons', 'https://www.mercadolivre.com.br/cupons/active?source_page=int_input_code']:
            with self.subTest(destination=destination), tempfile.TemporaryDirectory() as temp:
                browser = MercadoLivreBrowser(Path(temp))
                browser.configured, browser._headless = True, False
                page = MagicMock()
                page.is_closed.return_value = False
                page.url = COUPONS_URL
                page.content.return_value = '<h1>Cupons</h1>'
                page.locator.return_value.all.return_value = []
                browser._context = MagicMock(pages=[page])
                state = {'form': True, 'code': ''}
                field, opener, submit = MagicMock(), MagicMock(), MagicMock()
                field.is_visible.side_effect = lambda: state['form']
                opener.is_visible.side_effect = lambda: state['form']
                field.fill.side_effect = lambda value, **kwargs: state.update(code=value)
                page.get_by_placeholder.return_value = field
                page.get_by_role.side_effect = lambda role, **kwargs: submit if kwargs.get('exact') else opener
                callbacks = {}
                page.on.side_effect = lambda event, callback: callbacks.update({event: callback})
                def send(**kwargs):
                    callbacks['response'](SimpleNamespace(
                        url='https://www.mercadolivre.com.br/cupons/api/input-code', status=200,
                        request=SimpleNamespace(method='POST', post_data=json.dumps({'coupon_input_code': state['code']})),
                        json=lambda: {'responseMessage': {'type': 'success', 'text': 'Cupom adicionado!'}}))
                    state['form'] = False
                    page.url = destination
                submit.click.side_effect = send
                def reopen(url):
                    state['form'] = True
                    page.url = url
                browser._read_page = MagicMock(side_effect=reopen)
                try:
                    self.assertEqual(browser._apply_coupon('PRIMEIRO10')[0], 'inserted')
                    browser._read_page.assert_called_once_with(COUPONS_URL)
                    self.assertEqual(page.url, COUPONS_URL)
                    self.assertEqual(browser._apply_coupon('SEGUNDO10')[0], 'inserted')
                    self.assertEqual(browser._read_page.call_count, 2)
                    self.assertEqual([call.args[0] for call in field.fill.call_args_list],
                                     ['', 'PRIMEIRO10', '', 'SEGUNDO10'])
                    self.assertEqual(submit.click.call_count, 2)
                finally:
                    browser._executor.shutdown(wait=False)

    def test_closed_modal_with_visible_opener_does_not_refresh(self):
        with tempfile.TemporaryDirectory() as temp:
            browser = MercadoLivreBrowser(Path(temp))
            browser.configured, browser._headless = True, False
            page = MagicMock()
            page.is_closed.return_value = False
            page.url = COUPONS_URL
            page.content.return_value = '<h1>Cupons</h1>'
            feedback = MagicMock()
            feedback.is_visible.return_value = True
            feedback.inner_text.side_effect = ['Cupons', 'Cupom inválido']
            page.locator.return_value.all.return_value = [feedback]
            page.get_by_placeholder.return_value.is_visible.return_value = False
            page.get_by_role.return_value.is_visible.return_value = True
            browser._context = MagicMock(pages=[page])
            browser._read_page = MagicMock()
            try:
                self.assertEqual(browser._apply_coupon('INVALIDO10')[0], 'rejected')
                browser._read_page.assert_not_called()
            finally:
                browser._executor.shutdown(wait=False)

    def test_active_redirect_without_response_confirms_and_reopens_despite_lost_context(self):
        for lost_context in [False, True]:
            with self.subTest(lost_context=lost_context), tempfile.TemporaryDirectory() as temp:
                browser = MercadoLivreBrowser(Path(temp))
                browser.configured, browser._headless = True, False
                page = MagicMock()
                page.is_closed.return_value = False
                page.url = COUPONS_URL
                page.content.return_value = '<h1>Cupons</h1>'
                feedback = MagicMock()
                feedback.is_visible.return_value = True
                feedback.inner_text.return_value = 'spinner'
                page.locator.return_value.all.return_value = [feedback]
                browser._context = MagicMock(pages=[page])
                def submit(**kwargs):
                    page.url = 'https://www.mercadolivre.com.br/cupons/active?source_page=int_input_code'
                    if lost_context:
                        raise RuntimeError('Execution context was destroyed')
                page.get_by_role.return_value.click.side_effect = submit
                browser._read_page = MagicMock(side_effect=lambda url: setattr(page, 'url', url))
                try:
                    result = browser._apply_coupon('TESTE10')
                    self.assertEqual(result[0], 'inserted')
                    self.assertIn('Meus cupons', result[1])
                    self.assertNotIn('spinner', result[1])
                    self.assertEqual(page.url, COUPONS_URL)
                    browser._read_page.assert_called_once_with(COUPONS_URL)
                    page.get_by_role.return_value.click.assert_called_once()
                finally:
                    browser._executor.shutdown(wait=False)

    def test_unrelated_redirect_and_spinner_are_not_confirmation(self):
        for destination in ['https://www.mercadolivre.com.br/cupons/active?source_page=mperfil',
                            'https://www.mercadolivre.com.br/cupons',
                            'https://www.mercadolivre.com.br/cupons/active-fake?source_page=int_input_code']:
            with self.subTest(destination=destination), tempfile.TemporaryDirectory() as temp:
                browser = MercadoLivreBrowser(Path(temp))
                browser.configured, browser._headless = True, False
                page = MagicMock()
                page.is_closed.return_value = False
                page.url = COUPONS_URL
                page.content.return_value = '<h1>Cupons</h1>'
                feedback = MagicMock()
                feedback.is_visible.return_value = True
                feedback.inner_text.side_effect = ['Cupons', 'spinner']
                page.locator.return_value.all.return_value = [feedback]
                browser._context = MagicMock(pages=[page])
                browser._read_page = MagicMock()
                page.get_by_role.return_value.click.side_effect = lambda **kwargs: setattr(page, 'url', destination)
                try:
                    with patch('time.monotonic', side_effect=[0, 1, 21]):
                        result = browser._apply_coupon('TESTE10')
                    self.assertEqual(result[0], 'pending')
                    self.assertNotIn('spinner', result[1])
                    browser._read_page.assert_not_called()
                finally:
                    browser._executor.shutdown(wait=False)

    def test_reopening_failure_does_not_overwrite_official_success(self):
        with tempfile.TemporaryDirectory() as temp:
            browser = MercadoLivreBrowser(Path(temp))
            browser.configured, browser._headless = True, False
            page = MagicMock()
            page.is_closed.return_value = False
            page.url = COUPONS_URL
            page.content.return_value = '<h1>Cupons</h1>'
            page.locator.return_value.all.return_value = []
            browser._context = MagicMock(pages=[page])
            callbacks = {}
            page.on.side_effect = lambda event, callback: callbacks.update({event: callback})
            response = SimpleNamespace(url='https://www.mercadolivre.com.br/cupons/api/input-code', status=200,
                request=SimpleNamespace(method='POST', post_data=json.dumps({'coupon_input_code': 'TESTE10'})),
                json=lambda: {'responseMessage': {'type': 'success', 'text': 'Cupom adicionado!'}})
            page.get_by_role.return_value.click.side_effect = lambda **kwargs: callbacks['response'](response)
            browser._read_page = MagicMock(side_effect=ValueError('Falha ao reabrir'))
            try:
                self.assertEqual(browser._apply_coupon('TESTE10'), ('inserted', 'Cupom adicionado!'))
                browser._read_page.assert_called_once_with(COUPONS_URL)
                page.remove_listener.assert_called_once_with('response', callbacks['response'])
            finally:
                browser._executor.shutdown(wait=False)

    def test_active_redirect_resolves_unknown_response_but_preserves_explicit_rejection(self):
        for message, expected in [('Resposta não reconhecida', 'inserted'), ('Cupom inválido', 'rejected')]:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as temp:
                browser = MercadoLivreBrowser(Path(temp))
                browser.configured, browser._headless = True, False
                page = MagicMock()
                page.is_closed.return_value = False
                page.url = COUPONS_URL
                page.content.return_value = '<h1>Cupons</h1>'
                page.locator.return_value.all.return_value = []
                browser._context = MagicMock(pages=[page])
                callbacks = {}
                page.on.side_effect = lambda event, callback: callbacks.update({event: callback})
                response = SimpleNamespace(url='https://www.mercadolivre.com.br/cupons/api/input-code', status=200,
                    request=SimpleNamespace(method='POST', post_data=json.dumps({'coupon_input_code': 'TESTE10'})),
                    json=lambda: {'responseMessage': {'type': 'error', 'text': message}})
                def submit(**kwargs):
                    callbacks['response'](response)
                    page.url = 'https://www.mercadolivre.com.br/cupons/active?source_page=int_input_code'
                page.get_by_role.return_value.click.side_effect = submit
                browser._read_page = MagicMock(side_effect=lambda url: setattr(page, 'url', url))
                try:
                    self.assertEqual(browser._apply_coupon('TESTE10')[0], expected)
                    browser._read_page.assert_called_once_with(COUPONS_URL)
                    self.assertEqual(page.url, COUPONS_URL)
                finally:
                    browser._executor.shutdown(wait=False)

    def test_identical_feedback_requires_a_new_dom_response(self):
        for renewed in [False, True]:
            with self.subTest(renewed=renewed), tempfile.TemporaryDirectory() as temp:
                browser = MercadoLivreBrowser(Path(temp))
                browser.configured, browser._headless = True, False
                page = MagicMock()
                page.is_closed.return_value = False
                page.url = COUPONS_URL
                page.content.return_value = '<h1>Cupons</h1>'
                feedback = MagicMock()
                feedback.is_visible.return_value = True
                feedback.inner_text.return_value = 'Este cupom não se aplica a você.'
                page.locator.return_value.all.return_value = [feedback]
                page.evaluate.side_effect = [None, renewed, None]
                browser._context = MagicMock(pages=[page])
                try:
                    with patch('time.monotonic', side_effect=[0, 1, 21]):
                        result = browser._apply_coupon('OUTRO10')
                    self.assertEqual(result[0], 'rejected' if renewed else 'pending')
                    if renewed:
                        self.assertEqual(result[1], 'Este cupom não se aplica a você.')
                finally:
                    browser._executor.shutdown(wait=False)

    def test_response_for_sent_code_survives_navigation_during_click(self):
        with tempfile.TemporaryDirectory() as temp:
            browser = MercadoLivreBrowser(Path(temp))
            browser.configured, browser._headless = True, False
            page = MagicMock()
            page.is_closed.return_value = False
            page.url = COUPONS_URL
            page.content.return_value = '<h1>Cupons</h1>'
            page.locator.return_value.all.return_value = []
            browser._context = MagicMock(pages=[page])
            callbacks = {}
            page.on.side_effect = lambda event, callback: callbacks.update({event: callback})
            response = SimpleNamespace(url='https://www.mercadolivre.com.br/cupons/api/input-code', status=200,
                request=SimpleNamespace(method='POST', post_data=json.dumps({'coupon_input_code': 'TESTE10'})),
                json=lambda: {'responseMessage': {'type': 'success', 'text': 'Cupom adicionado!'}})
            def submit(**kwargs):
                callbacks['response'](response)
                raise RuntimeError('Execution context was destroyed')
            page.get_by_role.return_value.click.side_effect = submit
            try:
                self.assertEqual(browser._apply_coupon('TESTE10'), ('inserted', 'Cupom adicionado!'))
                page.remove_listener.assert_called_once_with('response', callbacks['response'])
            finally:
                browser._executor.shutdown(wait=False)

    def test_response_for_other_code_or_http_failure_does_not_confirm_success(self):
        for received_code, http_status in [('OUTRO10', 200), ('TESTE10', 500)]:
            with self.subTest(code=received_code, status=http_status), tempfile.TemporaryDirectory() as temp:
                browser = MercadoLivreBrowser(Path(temp))
                browser.configured, browser._headless = True, False
                page = MagicMock()
                page.is_closed.return_value = False
                page.url = COUPONS_URL
                page.content.return_value = '<h1>Cupons</h1>'
                page.locator.return_value.all.return_value = []
                browser._context = MagicMock(pages=[page])
                callbacks = {}
                page.on.side_effect = lambda event, callback: callbacks.update({event: callback})
                response = SimpleNamespace(url='https://www.mercadolivre.com.br/cupons/api/input-code', status=http_status,
                    request=SimpleNamespace(method='POST', post_data=json.dumps({'coupon_input_code': received_code})),
                    json=lambda: {'responseMessage': {'type': 'success', 'text': 'Cupom adicionado!'}})
                page.get_by_role.return_value.click.side_effect = lambda **kwargs: callbacks['response'](response)
                try:
                    with patch('time.monotonic', side_effect=[0, 1, 21]):
                        self.assertEqual(browser._apply_coupon('TESTE10')[0], 'pending')
                finally:
                    browser._executor.shutdown(wait=False)

    def test_temporary_navigation_recovers_visible_success_without_resubmitting(self):
        with tempfile.TemporaryDirectory() as temp:
            browser = MercadoLivreBrowser(Path(temp))
            browser.configured, browser._headless = True, False
            page = MagicMock()
            page.is_closed.return_value = False
            page.url = COUPONS_URL
            page.content.return_value = '<h1>Cupons</h1>'
            feedback = MagicMock()
            feedback.is_visible.return_value = True
            feedback.inner_text.side_effect = ['Cupons', 'Cupom adicionado!']
            page.locator.return_value.all.return_value = [feedback]
            page.evaluate.side_effect = [None, RuntimeError('Execution context was destroyed'), False, None]
            browser._context = MagicMock(pages=[page])
            try:
                with patch('time.monotonic', side_effect=[0, 1, 2, 21]):
                    self.assertEqual(browser._apply_coupon('TESTE10'), ('inserted', 'Cupom adicionado!'))
                page.get_by_role.return_value.click.assert_called_once()
            finally:
                browser._executor.shutdown(wait=False)


class ApplicatorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'test.sqlite3'
        self.store = Store(self.path)
        self.browser = MagicMock(configured=True, login_open=False)
        self.browser.apply_coupon = AsyncMock(return_value=('inserted', 'Cupom adicionado!'))
        self.applicator = CouponApplicator(self.store, self.browser, asyncio.Lock())
        self.sleep = patch('ml_coupon_applicator.asyncio.sleep', new_callable=AsyncMock)
        self.sleep.start()

    async def asyncTearDown(self):
        self.sleep.stop()
        self.store.close()
        self.temp.cleanup()

    def post(self, code='TESTE10', shop='Mercado Livre', number=1):
        self.store.db.execute('INSERT INTO coupon_posts(source,message_id,text,codes,published_at) VALUES(?,?,?,?,?)',
                              ('Telegram', number, f'Cupom {shop}', json.dumps([code]), utcnow()))
        self.store.db.commit()

    def test_today_uses_sao_paulo_midnight_not_utc_or_last_24_hours(self):
        now = datetime(2026, 10, 6, 3, 5, tzinfo=timezone.utc)
        self.assertTrue(coupon_is_today('2026-10-06T03:00:00+00:00', now))
        self.assertTrue(coupon_is_today('2026-10-06T00:01:00-03:00', now))
        self.assertFalse(coupon_is_today('2026-10-06T02:59:59+00:00', now))
        self.assertFalse(coupon_is_today('2026-10-07T03:00:00+00:00', now))
        for stamp in ('', None, 'sem data'):
            self.assertFalse(coupon_is_today(stamp, now))

    async def test_old_discoveries_are_deleted_even_when_attempted_today(self):
        self.post('ONTEM10')
        self.applicator.record('ONTEM10', 'Telegram', 'pending', 'Tivemos um problema')
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.store.db.execute('UPDATE coupon_posts SET found_at=?', (yesterday,))
        self.store.db.execute('UPDATE ml_coupon_applications SET found_at=?', (yesterday,))
        self.store.db.commit()
        self.post('HOJE10', number=2)
        self.applicator.record('HOJE10', 'Telegram', 'pending', 'Tivemos um problema')
        for retry_only, code in ((True, 'ONTEM10'), (True, None), (False, None)):
            await self.applicator.run(retry_only, code)
        self.browser.apply_coupon.assert_awaited_once_with('HOJE10')
        self.assertEqual([row['code'] for row in self.applicator.history()], ['HOJE10'])
        self.assertEqual([json.loads(row['codes']) for row in self.store.rows('SELECT codes FROM coupon_posts')], [['HOJE10']])

    def test_pruning_also_deletes_public_and_official_caches_of_other_shops(self):
        now = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)
        for key in ('public_coupons', 'pichau_coupons'):
            self.store.set_setting(key, json.dumps([
                dict(code='ONTEM10', url='https://example.com/old', found_at='2026-10-05T12:00:00+00:00', checked_at=now.isoformat()),
                dict(code='HOJE10', url='https://example.com/new', found_at=now.isoformat(), checked_at=now.isoformat())]))
        self.store.prune_coupons(now)
        for key in ('public_coupons', 'pichau_coupons'):
            self.assertEqual([row['code'] for row in json.loads(self.store.get_setting(key))], ['HOJE10'])
        self.assertEqual(len(self.store.components()), 3)

    def test_refreshing_cache_does_not_move_discovery_date_to_today(self):
        for key in ('public_coupons', 'pichau_coupons'):
            self.store.set_setting(key, json.dumps([dict(code='VELHO10', url='https://example.com/coupon', checked_at='2026-10-05T12:00:00+00:00')]))
            self.store.set_setting(key, json.dumps([dict(code='VELHO10', url='https://example.com/coupon', checked_at='2026-10-06T12:00:00+00:00')]))
            row = json.loads(self.store.get_setting(key))[0]
            self.assertEqual(row['found_at'], '2026-10-05T12:00:00+00:00')
            self.assertEqual(row['checked_at'], '2026-10-06T12:00:00+00:00')

    async def test_new_and_retry_batches_recheck_date_between_submissions(self):
        for retry_only in (False, True):
            with self.subTest(retry_only=retry_only):
                self.store.db.execute('DELETE FROM coupon_posts')
                self.store.db.execute('DELETE FROM ml_coupon_applications')
                clock = [datetime(2026, 10, 6, 2, 59, tzinfo=timezone.utc)]
                class Clock(datetime):
                    @classmethod
                    def now(cls, tz=None):
                        return clock[0].astimezone(tz) if tz else clock[0]
                for number, code in enumerate(('PRIMEIRO10', 'SEGUNDO10'), 1):
                    self.post(code, number=number)
                    self.store.db.execute('UPDATE coupon_posts SET published_at=?,found_at=? WHERE message_id=?',
                                          (clock[0].isoformat(), clock[0].isoformat(), number))
                    if retry_only:
                        self.store.db.execute('INSERT INTO ml_coupon_applications(code,status,detail,attempted_at,source,found_at) VALUES(?,?,?,?,?,?)',
                                              (code, 'pending', 'Tivemos um problema', clock[0].isoformat(), 'Telegram', clock[0].isoformat()))
                self.store.db.commit()
                async def submit(code):
                    clock[0] = datetime(2026, 10, 6, 3, 1, tzinfo=timezone.utc)
                    return 'inserted', 'Cupom adicionado!'
                self.browser.apply_coupon.reset_mock()
                self.browser.apply_coupon.side_effect = submit
                with patch('core.datetime', Clock):
                    await self.applicator.run(retry_only)
                self.assertEqual(self.browser.apply_coupon.await_count, 1)
                self.assertEqual(self.applicator.history(), [])

    def test_legacy_migration_uses_publication_instead_of_latest_attempt(self):
        self.post('ONTEM10')
        self.applicator.record('ONTEM10', 'Telegram', 'pending', 'Tivemos um problema')
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.store.db.execute('UPDATE coupon_posts SET published_at=?', (yesterday,))
        self.store.db.execute('ALTER TABLE coupon_posts DROP COLUMN found_at')
        self.store.db.execute('ALTER TABLE ml_coupon_applications DROP COLUMN found_at')
        self.store.db.commit()
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.rows('SELECT found_at FROM ml_coupon_applications')[0]['found_at'], yesterday)
        self.store.prune_coupons()
        self.assertEqual(self.store.rows('SELECT * FROM ml_coupon_applications'), [])

    def test_unknown_discovery_is_deleted_instead_of_assuming_today(self):
        self.store.db.execute('INSERT INTO ml_coupon_applications(code,status,detail,attempted_at,source) VALUES(?,?,?,?,?)',
                              ('SEMDATA10', 'pending', 'Tivemos um problema', utcnow(), 'Telegram'))
        self.store.db.commit()
        self.store.prune_coupons()
        self.assertEqual(self.applicator.history(), [])

    async def test_retry_only_excludes_new_success_terminal_and_disabled_codes(self):
        for number, code in enumerate(['NOVO10', 'FALHA10', 'ATIVO10', 'INVALIDO10', 'ESGOTOU10', 'PAUSADO10'], 1):
            self.post(code, number=number)
        for code, status, detail in [('FALHA10', 'pending', 'Tivemos um problema'),
                                     ('ATIVO10', 'inserted', 'Cupom adicionado!'),
                                     ('INVALIDO10', 'rejected', 'Cupom inválido'),
                                     ('ESGOTOU10', 'pending', 'O cupom esgotou.'),
                                     ('PAUSADO10', 'pending', 'Resposta desconhecida')]:
            self.applicator.record(code, 'Telegram', status, detail)
        self.applicator.set_disabled('PAUSADO10', True)
        await self.applicator.run(retry_only=True)
        self.browser.apply_coupon.assert_awaited_once_with('FALHA10')
        self.assertEqual(next(row for row in self.applicator.history() if row['code'] == 'FALHA10')['attempts'], 2)
        self.assertIn(('NOVO10', 'Telegram'), self.applicator.candidates())

    async def test_individual_retry_does_not_send_another_failure(self):
        for number, code in enumerate(['FALHA10', 'OUTRO10'], 1):
            self.post(code, number=number)
            self.applicator.record(code, 'Telegram', 'pending', 'Tivemos um problema')
        await self.applicator.run(retry_only=True, code='FALHA10')
        self.browser.apply_coupon.assert_awaited_once_with('FALHA10')
        await self.applicator.run(retry_only=True, code='FALHA10')
        self.browser.apply_coupon.assert_awaited_once_with('FALHA10')

    async def test_disabled_new_coupon_survives_restart_and_reactivation(self):
        self.post()
        self.applicator.set_disabled('TESTE10', True)
        self.store.close()
        self.store = Store(self.path)
        self.applicator = CouponApplicator(self.store, self.browser, asyncio.Lock())
        await self.applicator.run()
        self.browser.apply_coupon.assert_not_awaited()
        row = self.applicator.history()[0]
        self.assertEqual((row['disabled'], row['attempts'], row['attempted_at']), (1, 0, ''))
        self.applicator.set_disabled('TESTE10', False)
        await self.applicator.run()
        self.browser.apply_coupon.assert_awaited_once_with('TESTE10')

    async def test_disable_and_reactivate_preserves_last_response_and_attempt_count(self):
        self.post()
        await self.applicator.run()
        before = self.applicator.history()[0]
        self.applicator.set_disabled('TESTE10', True)
        self.applicator.set_disabled('TESTE10', False)
        self.assertEqual(self.applicator.history()[0], before)
        await self.applicator.run()
        self.browser.apply_coupon.assert_awaited_once()

    async def test_disable_queued_coupon_is_respected_before_submission(self):
        self.post('SEGUNDO10')
        self.post('PRIMEIRO10', number=2)
        async def submit(code):
            self.applicator.set_disabled('SEGUNDO10', True)
            return 'inserted', 'Cupom adicionado!'
        self.browser.apply_coupon.side_effect = submit
        await self.applicator.run()
        self.browser.apply_coupon.assert_awaited_once_with('PRIMEIRO10')

    async def test_recorded_failures_remain_retryable_without_original_publication(self):
        self.applicator.record('ANTIGO10', 'Site público', 'pending', 'Tivemos um problema')
        await self.applicator.run(retry_only=True)
        self.browser.apply_coupon.assert_awaited_once_with('ANTIGO10')

    async def test_catalog_merges_duplicate_publications_and_shows_saved_result(self):
        self.post()
        self.post('teste10', number=2)
        await self.applicator.run()
        rows = self.applicator.catalog()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['code'], rows[0]['group'], rows[0]['attempts']), ('TESTE10', 'active', 1))

    async def test_old_database_gets_disabled_column_without_resetting_history(self):
        self.applicator.record('ANTIGO10', 'Telegram', 'rejected', 'Cupom inválido')
        self.store.db.execute('ALTER TABLE ml_coupon_applications DROP COLUMN disabled')
        self.store.db.commit()
        self.store.close()
        self.store = Store(self.path)
        row = self.store.rows('SELECT * FROM ml_coupon_applications')[0]
        self.assertEqual((row['status'], row['attempts'], row['disabled']), ('rejected', 1, 0))

    async def test_duplicate_codes_are_sent_once_and_persist_across_restart(self):
        self.post('teste10')
        self.post(number=2)
        await self.applicator.run()
        self.store.close()
        self.store = Store(self.path)
        self.applicator = CouponApplicator(self.store, self.browser, asyncio.Lock())
        await self.applicator.run()
        self.browser.apply_coupon.assert_awaited_once_with('TESTE10')
        self.assertEqual(self.applicator.history()[0]['status'], 'inserted')
        self.assertFalse(self.applicator.due())

    async def test_other_shops_unknown_shop_and_malformed_codes_are_excluded(self):
        for number, (code, shop) in enumerate([('PI10', 'Pichau'), ('BAD CODE', 'Mercado Livre'),
                                               ('UN10', 'desconhecido'), ('MIX10', 'Mercado Livre e Pichau')], 1):
            self.post(code, shop, number)
        await self.applicator.run()
        self.browser.apply_coupon.assert_not_awaited()

    async def test_existing_and_rejected_are_not_retried(self):
        self.post()
        self.post('INVALIDO10', number=2)
        self.browser.apply_coupon.side_effect = [('existing', 'Já adicionado'), ('rejected', 'Cupom inválido')]
        await self.applicator.run()
        await self.applicator.run()
        self.assertEqual(self.browser.apply_coupon.await_count, 2)

    async def test_personal_rejection_is_saved_verbatim_and_not_retried(self):
        self.post()
        self.browser.apply_coupon.return_value = ('rejected', 'Este cupom não se aplica a você.')
        await self.applicator.run()
        await self.applicator.run()
        row = self.applicator.history()[0]
        self.assertEqual((row['status'], row['detail']), ('rejected', 'Este cupom não se aplica a você.'))
        self.browser.apply_coupon.assert_awaited_once()

    async def test_pending_stops_batch_and_can_retry_without_claiming_success(self):
        self.post()
        self.post('OUTRO10', number=2)
        self.browser.apply_coupon.return_value = ('pending', 'Resposta desconhecida')
        await self.applicator.run()
        self.assertEqual(self.browser.apply_coupon.await_count, 1)
        self.assertEqual(self.applicator.history()[0]['status'], 'pending')
        self.assertEqual(len(self.applicator.candidates()), 2)

    async def test_tivemos_um_problema_keeps_pending_and_continues_to_other_coupons(self):
        for number in range(1, 4):
            self.post(f'CUPOM{number}0', number=number)
        queued = [code for code, _ in self.applicator.candidates()]
        self.browser.apply_coupon.side_effect = [('pending', 'Tivemos um problema.'),
                                                  ('inserted', 'Cupom adicionado!'),
                                                  ('existing', 'Já adicionado')]
        await self.applicator.run()
        self.assertEqual([call.args[0] for call in self.browser.apply_coupon.await_args_list], queued)
        failed = next(row for row in self.applicator.history() if row['code'] == queued[0])
        self.assertEqual((failed['status'], failed['detail'], failed['attempts']), ('pending', 'Tivemos um problema.', 1))
        self.assertEqual(self.applicator.candidates(retry_only=True), [(queued[0], 'Telegram')])

    async def test_five_consecutive_problems_stop_batch_and_retry_in_next_run(self):
        for retry_only in (False, True):
            with self.subTest(retry_only=retry_only):
                self.store.db.execute('DELETE FROM coupon_posts')
                self.store.db.execute('DELETE FROM ml_coupon_applications')
                for number in range(1, 8):
                    code = f'CUPOM{number}0'
                    self.post(code, number=number)
                    if retry_only:
                        self.applicator.record(code, 'Telegram', 'pending', 'Tivemos um problema')
                queued = [code for code, _ in self.applicator.candidates(retry_only)]
                self.browser.apply_coupon.reset_mock()
                self.browser.apply_coupon.side_effect = None
                self.browser.apply_coupon.return_value = ('pending', 'Tivemos um problema')
                await self.applicator.run(retry_only)
                self.assertEqual([call.args[0] for call in self.browser.apply_coupon.await_args_list], queued[:5])
                self.assertIn('5 erros consecutivos', self.applicator.status)
                self.assertIn('próxima execução em 1 hora', self.applicator.status)
                self.assertFalse(self.applicator.due())
                self.assertFalse(self.applicator.lock.locked())
                self.assertFalse(self.applicator.shop_lock.locked())
                self.assertIsNone(self.applicator.current_code)
                self.assertEqual(len(self.applicator.candidates(retry_only)), 7)
                self.browser.apply_coupon.reset_mock()
                self.browser.apply_coupon.return_value = ('inserted', 'Cupom adicionado!')
                await self.applicator.run(retry_only)
                self.assertEqual(self.browser.apply_coupon.await_count, 7)
                self.assertEqual(self.applicator.candidates(), [])

    async def test_other_response_resets_consecutive_problem_counter(self):
        for middle in [('inserted', 'Cupom adicionado!'), ('existing', 'Já adicionado'), ('rejected', 'Cupom inválido')]:
            with self.subTest(middle=middle):
                self.store.db.execute('DELETE FROM coupon_posts')
                self.store.db.execute('DELETE FROM ml_coupon_applications')
                for number in range(1, 10):
                    self.post(f'CUPOM{number}0', number=number)
                self.browser.apply_coupon.reset_mock()
                self.browser.apply_coupon.side_effect = [('pending', 'Tivemos um problema')] * 4 + [middle] + [('pending', 'Tivemos um problema')] * 4
                await self.applicator.run()
                self.assertEqual(self.browser.apply_coupon.await_count, 9)
                self.assertNotIn('5 erros consecutivos', self.applicator.status)
                self.assertEqual(len(self.applicator.candidates(retry_only=True)), 8)

    async def test_network_failure_preserves_pending_attempt(self):
        self.post()
        self.browser.apply_coupon.side_effect = ValueError('Login necessário')
        await self.applicator.run()
        self.assertEqual(self.applicator.history()[0]['status'], 'pending')
        self.assertIn('interrompida', self.applicator.status)

    async def test_disabled_source_or_login_pending_do_not_send(self):
        self.post()
        self.store.set_setting('shop:Mercado Livre', '0')
        await self.applicator.run()
        self.store.set_setting('shop:Mercado Livre', '1')
        self.browser.login_open = True
        await self.applicator.run()
        self.browser.apply_coupon.assert_not_awaited()

    async def test_hourly_deadline_is_persistent_and_manual_button_can_run_early(self):
        self.post()
        self.assertTrue(self.applicator.due())
        self.store.set_setting('ml_coupon_last_run', (datetime.now(timezone.utc) - timedelta(minutes=59)).isoformat())
        self.assertFalse(self.applicator.due())
        await self.applicator.run()
        self.browser.apply_coupon.assert_awaited_once()
        self.store.set_setting('ml_coupon_last_run', (datetime.now(timezone.utc) - timedelta(hours=1, seconds=1)).isoformat())
        self.assertTrue(self.applicator.due())

    async def test_scheduler_skips_recent_run_and_checks_again_every_minute(self):
        self.store.set_setting('ml_coupon_last_run', utcnow())
        self.applicator.run = AsyncMock()
        with patch('ml_coupon_applicator.asyncio.sleep', side_effect=asyncio.CancelledError) as sleep:
            with self.assertRaises(asyncio.CancelledError):
                await self.applicator.loop()
        self.applicator.run.assert_not_awaited()
        sleep.assert_awaited_once_with(60)

    async def test_interrupted_submission_stays_pending_for_next_execution(self):
        self.post()
        self.browser.apply_coupon.side_effect = asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await self.applicator.run()
        self.assertEqual(self.applicator.history()[0]['status'], 'pending')
        self.assertFalse(self.applicator.lock.locked())
        self.assertFalse(self.applicator.shop_lock.locked())

    async def test_shop_scan_and_duplicate_execution_cannot_overlap(self):
        self.post()
        await self.applicator.shop_lock.acquire()
        task = asyncio.create_task(self.applicator.run())
        await real_sleep(0)
        await self.applicator.run()
        self.browser.apply_coupon.assert_not_awaited()
        self.applicator.shop_lock.release()
        await task
        self.browser.apply_coupon.assert_awaited_once()
