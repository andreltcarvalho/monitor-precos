"""Login local interativo. Nunca envia mensagens ou entra em grupos."""
import asyncio
import getpass
import json
from pathlib import Path
import urllib.request
import urllib.error

from telethon import TelegramClient, errors

from credentials import load_credentials, protect_data_dir, save_credentials

DATA = Path(__file__).resolve().parent / 'data'


def local_failure(stage, exc):
    if isinstance(exc, PermissionError):
        print(f'Sem permissão ao {stage}. Execute Conectar-Telegram.cmd pelo seu usuário do Windows.')
    elif isinstance(exc, TimeoutError):
        print(f'Tempo esgotado ao {stage}. Confira se o Telegram está acessível pela sua rede.')
    else:
        # Não imprime a exceção: ela pode conter telefone ou outros dados do login.
        print(f'Falha ao {stage} ({type(exc).__name__}).')


async def main():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8765/health',timeout=2) as response:
            if json.load(response).get('running'):
                print('Encerre o monitor pelo botão Encerrar no painel antes de conectar o Telegram.')
                return
    except (urllib.error.URLError, TimeoutError, ValueError):
        pass
    print('Conectar Telegram ao monitor de preços')
    print('Obtenha API ID e API hash em https://my.telegram.org > API development tools.')
    print('Informe os dados apenas neste terminal. Feche o monitor antes de conectar.')
    try:
        protect_data_dir(DATA)
        credentials = load_credentials(DATA)
    except (OSError, ValueError) as exc:
        local_failure('preparar a configuração local', exc)
        return
    if not credentials:
        try:
            api_id = int(input('API ID: ').strip())
        except ValueError:
            print('API ID inválido: informe apenas o número fornecido pelo Telegram.')
            return
        api_hash = getpass.getpass('API hash (oculto): ').strip()
        if api_id <= 0:
            print('API ID inválido: o número deve ser maior que zero.')
            return
        if len(api_hash) != 32 or any(c not in '0123456789abcdefABCDEF' for c in api_hash):
            print('API hash inválido: cole os 32 caracteres, sem aspas ou espaços no meio.')
            return
        credentials = {'api_id': api_id, 'api_hash': api_hash}
    client = TelegramClient(str(DATA / 'telegram'), **credentials, catch_up=False)
    stage = 'conectar ao Telegram'
    try:
        await client.connect()
        if not await client.is_user_authorized():
            phone = getpass.getpass('Telefone com código do país (oculto): ').strip()
            stage = 'pedir o código de login ao Telegram'
            sent = await client.send_code_request(phone)
            code = getpass.getpass('Código recebido no Telegram (oculto): ').strip()
            stage = 'confirmar o código de login'
            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
            except errors.SessionPasswordNeededError:
                stage = 'confirmar a senha de duas etapas'
                await client.sign_in(password=getpass.getpass('Senha de verificação em duas etapas (oculta): '))
        stage = 'salvar a configuração local'
        save_credentials(DATA, **credentials)
        print('Conta conectada. Pode abrir o monitor; escolha apenas os grupos que quer acompanhar.')
    except errors.FloodWaitError as exc:
        print(f'O Telegram pediu uma pausa de {exc.seconds} segundos. Tente novamente depois desse prazo.')
    except (errors.PhoneCodeInvalidError, errors.PhoneCodeExpiredError):
        print('Código inválido ou expirado. Execute a conexão novamente.')
    except errors.ApiIdInvalidError:
        print('O Telegram recusou o par API ID/API hash. Confira se os dois pertencem ao mesmo aplicativo em my.telegram.org.')
    except errors.PhoneNumberInvalidError:
        print('O Telegram recusou o telefone. Use +, código do país, DDD e número.')
    except errors.PasswordHashInvalidError:
        print('O Telegram recusou a senha de verificação em duas etapas.')
    except errors.RPCError as exc:
        print(f'O Telegram recusou a operação ao {stage} ({type(exc).__name__}).')
    except (OSError, ValueError) as exc:
        local_failure(stage, exc)
    finally:
        await client.disconnect()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (ValueError, OSError) as exc:
        local_failure('iniciar a conexão local', exc)
    except (KeyboardInterrupt, EOFError):
        print('Conexão cancelada. Nenhum código de login será reutilizado.')
