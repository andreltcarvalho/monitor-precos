"""Conecta o coletor local à conta do painel sem salvar sua senha."""
import asyncio
from getpass import getpass
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from cloud_sync import save_cloud_credentials


async def connect():
    url = input('Endereço HTTPS do painel publicado: ').strip().rstrip('/')
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise ValueError('Informe o endereço HTTPS do seu painel.')
    email = input('E-mail da sua conta no painel: ').strip()
    password = getpass('Senha da conta (não será salva): ')
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        response = await client.post(url + '/api/auth/login', json={'email': email, 'password': password})
        if response.is_error:
            raise ValueError('Login recusado. Confira e-mail, senha e confirmação do e-mail no painel.')
        access, refresh = response.cookies.get('monitor_access'), response.cookies.get('monitor_refresh')
        if not access or not refresh:
            raise ValueError('O painel não confirmou a sessão; confira se o endereço está correto.')
        save_cloud_credentials(Path(__file__).parent / 'data', {'url': url, 'access_token': access, 'refresh_token': refresh})
    print('Nuvem conectada. Reinicie o monitor para ativar a sincronização. Sua senha não foi salva.')


if __name__ == '__main__':
    try:
        asyncio.run(connect())
    except (ValueError, httpx.HTTPError, OSError) as exc:
        print(str(exc) if isinstance(exc, ValueError) else 'Não foi possível conectar. Confira a rede e o endereço do painel.')
        raise SystemExit(1)
