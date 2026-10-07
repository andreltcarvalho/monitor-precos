from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from credentials import crypt
from monitor import notify_windows

payload = b'roundtrip-test-not-a-secret'
try:
    encrypted = crypt(payload)
    print('DPAPI roundtrip:',crypt(encrypted,True)==payload,flush=True)
except Exception as exc:
    print('DPAPI:',type(exc).__name__,str(exc),flush=True)
try:
    notify_windows(dict(component='Monitor de peças · teste de instalação',pix=None,card=None,announced=None,
                        shop='Aviso local',status='Notificação de teste',url='http://127.0.0.1:8765'))
    print('Windows aceitou a notificação de teste.',flush=True)
except Exception as exc:
    print('Notificação:',type(exc).__name__,str(exc),flush=True)
