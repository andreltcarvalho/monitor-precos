"""Fila persistente de códigos do Mercado Livre, na sessão local do monitor."""
import asyncio
import json
import re
from datetime import datetime, timedelta, timezone

from core import coupon_is_today, normalized, utcnow
from presentation import coupon_catalog


LABELS = {'inserted': 'Inserido', 'existing': 'Já estava na conta',
          'rejected': 'Recusado', 'pending': 'Pendente'}
GROUPS = {'new': 'Novos', 'active': 'Ativados', 'failed': 'Falhas', 'disabled': 'Desativados'}


def application_state(row, applying=False):
    """Classifica o resultado salvo sem converter uma pendência em ativação."""
    status, text = row['status'], normalized(row.get('detail') or '')
    failure, retryable, guidance = '', False, ''
    if status in ('inserted', 'existing'):
        group, label = 'active', LABELS[status]
        guidance = 'Adicionado à conta; validade e condições continuam dependendo da loja.'
    elif status == 'new':
        group, label = 'new', 'Ainda não enviado'
        guidance = 'Será enviado no próximo ciclo automático.'
    elif applying:
        group, label = 'new', 'Aplicando agora'
        guidance = 'Aguardando confirmação do Mercado Livre.'
    else:
        group, label = 'failed', 'Falha'
        if re.search(r'nao se aplica (?:a|para) voce|nao elegivel', text):
            failure = 'Não elegível para sua conta'
        elif re.search(r'expirad|vencid|encerrad', text):
            failure = 'Expirado'
        elif re.search(r'esgotad|esgotou|nao esta mais disponivel', text):
            failure = 'Indisponível / esgotado'
        elif re.search(r'invalid|nao existe|nao e valido', text):
            failure = 'Código inválido'
        elif status == 'rejected':
            failure = 'Recusado pela loja'
        else:
            retryable = True
            if re.search(r'login|sessao|captcha|bloque|403|401', text):
                failure = 'Sessão / bloqueio'
                guidance = 'Confira a sessão em Fontes antes de retentar.'
            elif 'tentativa iniciada' in text:
                failure = 'Tentativa interrompida'
            elif re.search(r'problema|temporar|tente novamente|429|503|rede', text):
                failure = 'Erro temporário'
            elif 'navegador' in text:
                failure = 'Falha no navegador'
            else:
                failure = 'Sem confirmação'
        guidance = guidance or ('Pode retentar pelo botão ou no próximo ciclo de uma hora.' if retryable else
                                'Não será reenviado: o site recusou este código.')
        label = 'Pode retentar' if retryable else 'Sem retentativa'
    if row.get('disabled'):
        group, label, retryable = 'disabled', 'Desativado', False
        guidance = 'Sem novos envios. Reativar conserva o último resultado e as tentativas.'
    return dict(group=group, label=label, failure=failure, retryable=retryable, guidance=guidance)


class CouponApplicator:
    def __init__(self, store, browser, shop_lock):
        self.store, self.browser, self.shop_lock = store, browser, shop_lock
        self.lock = asyncio.Lock()
        self.current_code = None
        self.status = 'Aplicação automática a cada hora · aguardando execução'

    def due(self):
        stamp = self.store.get_setting('ml_coupon_last_run')
        try:
            return datetime.now(timezone.utc) >= datetime.fromisoformat(stamp) + timedelta(hours=1)
        except (ValueError, TypeError):
            return True

    def catalog(self):
        self.store.prune_coupons()
        rows = coupon_catalog(self.store.rows('SELECT * FROM coupon_posts ORDER BY published_at DESC'), [],
                              json.loads(self.store.get_setting('public_coupons', '[]')))
        codes = {}
        for row in rows:
            if row['shop'] != 'Mercado Livre' or row['activation']:
                continue
            for code in row['codes'].split(','):
                code = code.strip().upper()
                if re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{2,39}', code):
                    codes.setdefault(code, dict(code=code, source=row['source'], status='new', detail='',
                                                attempted_at='', attempts=0, disabled=0, found_at=row['found_at'], conditions=row['conditions']))
        for row in self.history():
            codes[row['code']] = dict(codes.get(row['code'], {}), **row)
        return [dict(row, **application_state(row, row['code'] == self.current_code)) for row in codes.values()]

    def candidates(self, retry_only=False, code=None):
        rows = [row for row in self.catalog() if coupon_is_today(row['found_at'])]
        new = [(row['code'], row['source']) for row in rows
               if row['group'] == 'new' and row['status'] == 'new' and not retry_only]
        pending = [(row['code'], row['source']) for row in sorted(rows, key=lambda row: row['attempted_at'])
                   if row['retryable']]
        if code is not None:
            return [item for item in pending if item[0] == code]
        return new + pending

    def set_disabled(self, code, disabled):
        row = next((row for row in self.catalog() if row['code'] == code), None)
        if row is None:
            return
        self.store.db.execute('''INSERT INTO ml_coupon_applications
            (code,status,detail,attempted_at,attempts,source,disabled,found_at) VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(code) DO UPDATE SET disabled=excluded.disabled''',
            (code, row['status'], row['detail'], row['attempted_at'], row['attempts'], row['source'], int(disabled), row['found_at']))
        self.store.db.commit()

    def history(self):
        return self.store.rows('SELECT * FROM ml_coupon_applications ORDER BY attempted_at DESC,code')

    def record(self, code, source, status, detail):
        found_at = next((row['found_at'] for row in self.catalog() if row['code'] == code), utcnow())
        self.store.db.execute('''INSERT INTO ml_coupon_applications(code,status,detail,attempted_at,source,found_at)
            VALUES(?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET status=excluded.status,
            detail=excluded.detail,attempted_at=excluded.attempted_at,
            attempts=ml_coupon_applications.attempts+1,source=excluded.source''',
            (code, status, detail[:500], utcnow(), source, found_at))
        self.store.db.commit()

    async def run(self, retry_only=False, code=None):
        if self.lock.locked():
            return
        async with self.lock:
            if self.store.get_setting('shop:Mercado Livre', '1') != '1':
                self.status = 'Aplicação pausada · fonte Mercado Livre desativada'
                return
            if not self.browser.configured or self.browser.login_open:
                self.status = 'Aplicação pendente · confirme a sessão do Mercado Livre em Fontes'
                return
            self.status = 'Aguardando consultas em andamento…'
            async with self.shop_lock:
                self.store.set_setting('ml_coupon_last_run', utcnow())
                candidates = self.candidates(retry_only, code)
                totals = dict.fromkeys(LABELS, 0)
                consecutive_problems = 0
                selected_code = code
                for index, (code, source) in enumerate(candidates):
                    # A preferência pode mudar enquanto um código anterior está sendo enviado.
                    if code not in {item[0] for item in self.candidates(retry_only, selected_code)}:
                        continue
                    self.status = f'Inserindo {index + 1} de {len(candidates)} códigos · {code}'
                    # Commit antes de enviar: interrupções nunca viram sucesso.
                    self.record(code, source, 'pending', 'Tentativa iniciada; aguardando confirmação do site')
                    self.current_code = code
                    try:
                        status, detail = await self.browser.apply_coupon(code)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        detail = str(exc) if isinstance(exc, ValueError) else 'Falha no navegador; confira a sessão do Mercado Livre'
                        self.store.db.execute('UPDATE ml_coupon_applications SET detail=? WHERE code=?', (detail[:500], code))
                        self.store.db.commit()
                        self.status = 'Aplicação interrompida · ' + detail
                        return
                    finally:
                        self.current_code = None
                    if status not in LABELS:
                        status, detail = 'pending', 'Resposta não reconhecida; inserção não confirmada'
                    self.store.db.execute('UPDATE ml_coupon_applications SET status=?,detail=? WHERE code=?',
                                          (status, detail[:500], code))
                    self.store.db.commit()
                    totals[status] += 1
                    temporary_problem = status == 'pending' and 'tivemos um problema' in normalized(detail)
                    consecutive_problems = consecutive_problems + 1 if temporary_problem else 0
                    if consecutive_problems >= 5:
                        self.status = 'Aplicação pausada · 5 erros consecutivos: Tivemos um problema · próxima execução em 1 hora'
                        return
                    if status == 'pending' and not temporary_problem and application_state(dict(status=status, detail=detail))['retryable']:
                        self.status = 'Aplicação pendente · ' + detail
                        return
                    if index + 1 < len(candidates):
                        await asyncio.sleep(2)
                self.status = (('Nenhuma falha recuperável para retentar' if retry_only else 'Nenhum código novo do Mercado Livre') + ' · próxima execução em 1 hora' if not candidates else
                               ' · '.join(f'{LABELS[key]}: {value}' for key, value in totals.items() if value) + ' · próxima execução em 1 hora')

    async def loop(self):
        while True:
            try:
                self.store.prune_coupons()
                if self.due():
                    await self.run()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.status = 'Aplicação indisponível · nova tentativa no próximo ciclo'
            await asyncio.sleep(60)
