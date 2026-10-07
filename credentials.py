"""Credenciais da API protegidas pelo usuário atual do Windows (DPAPI)."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_byte))]


def protect_data_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    if os.name != 'nt':
        path.chmod(0o700)
        return
    account = os.environ.get('USERDOMAIN', '') + '\\' + os.environ['USERNAME']
    result = subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r',
                             account + ':(OI)(CI)F', 'SYSTEM:(OI)(CI)F'],
                            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise OSError('Não foi possível restringir o acesso à pasta de sessão do Telegram.')


def crypt(data: bytes, decrypt: bool = False) -> bytes:
    if os.name != 'nt':
        raise OSError('A configuração de credenciais desta versão requer Windows.')
    buffer = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    outgoing = Blob()
    library = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        ok = library.CryptUnprotectData(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing))
    else:
        ok = library.CryptProtectData(ctypes.byref(incoming), 'Monitor de preços', None, None, None, 1, ctypes.byref(outgoing))
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel.LocalFree(outgoing.data)


def save_credentials(data_dir: Path, api_id: int, api_hash: str):
    protect_data_dir(data_dir)
    raw = json.dumps({'api_id': api_id, 'api_hash': api_hash}).encode()
    (data_dir / 'telegram-credentials.bin').write_bytes(crypt(raw))


def load_credentials(data_dir: Path) -> dict | None:
    path = data_dir / 'telegram-credentials.bin'
    return json.loads(crypt(path.read_bytes(), decrypt=True)) if path.exists() else None
