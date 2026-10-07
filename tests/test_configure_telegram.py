import contextlib
import io
import unittest
import urllib.error
from unittest.mock import AsyncMock, patch

from telethon import errors
import configure_telegram as login


class LoginTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.patches = contextlib.ExitStack()
        self.addCleanup(self.patches.close)
        self.output = io.StringIO()
        self.patches.enter_context(contextlib.redirect_stdout(self.output))
        self.patches.enter_context(patch.object(login.urllib.request, 'urlopen', side_effect=urllib.error.URLError('offline')))
        self.protect = self.patches.enter_context(patch.object(login, 'protect_data_dir'))
        self.patches.enter_context(patch.object(login, 'load_credentials', return_value=None))
        self.save = self.patches.enter_context(patch.object(login, 'save_credentials'))
        self.patches.enter_context(patch('builtins.input', return_value='12345'))
        self.patches.enter_context(patch.object(login.getpass, 'getpass', side_effect=['a' * 32, '+5511999999999', '12345', 'private-password']))
        self.client = AsyncMock()
        self.client.is_user_authorized.return_value = False
        self.factory = self.patches.enter_context(patch.object(login, 'TelegramClient', return_value=self.client))

    def assert_no_secrets(self):
        for value in ['a' * 32, '+5511999999999', 'private-password']:
            self.assertNotIn(value, self.output.getvalue())

    async def test_invalid_hash_explains_format_before_network(self):
        with patch.object(login.getpass, 'getpass', return_value='invalid'):
            await login.main()
        self.assertIn('32 caracteres', self.output.getvalue())
        self.factory.assert_not_called()

    async def test_invalid_id_explains_numeric_input(self):
        with patch('builtins.input', return_value='not-an-id'):
            await login.main()
        self.assertIn('apenas o número', self.output.getvalue())
        self.factory.assert_not_called()

    async def test_permission_failure_identifies_local_setup(self):
        self.protect.side_effect = PermissionError('private-password')
        await login.main()
        self.assertIn('Sem permissão ao preparar a configuração local', self.output.getvalue())
        self.factory.assert_not_called()
        self.assert_no_secrets()

    async def test_network_failure_identifies_connection_and_hides_details(self):
        self.client.connect.side_effect = OSError('private-password')
        await login.main()
        self.assertIn('conectar ao Telegram (OSError)', self.output.getvalue())
        self.save.assert_not_called()
        self.client.disconnect.assert_awaited_once()
        self.assert_no_secrets()

    async def test_api_rejection_distinct_from_network_failure(self):
        self.client.send_code_request.side_effect = errors.ApiIdInvalidError(None)
        await login.main()
        self.assertIn('par API ID/API hash', self.output.getvalue())
        self.save.assert_not_called()
        self.assert_no_secrets()

    async def test_code_timeout_identifies_operation(self):
        self.client.send_code_request.side_effect = TimeoutError('private-password')
        await login.main()
        self.assertIn('Tempo esgotado ao pedir o código', self.output.getvalue())
        self.assert_no_secrets()

    async def test_two_factor_success_saves_after_login(self):
        self.client.sign_in.side_effect = [errors.SessionPasswordNeededError(None), None]
        await login.main()
        self.assertEqual(self.client.sign_in.await_count, 2)
        self.save.assert_called_once()
        self.assertIn('Conta conectada', self.output.getvalue())
        self.assert_no_secrets()

    async def test_running_monitor_prevents_session_conflict(self):
        with patch.object(login.urllib.request, 'urlopen', return_value=io.StringIO('{"running":true}')):
            await login.main()
        self.assertIn('Encerre o monitor', self.output.getvalue())
        self.factory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
