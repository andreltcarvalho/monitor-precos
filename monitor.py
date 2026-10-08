"""Monitor contínuo, independente de conexões ao painel."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
from time import monotonic

import httpx
from telethon import TelegramClient, events, errors, utils, types

from core import Store, alert_payment, alert_price, brl, canonical_url, coupons, detect_brand, links, matches, offer_fingerprint, price_is_current, reading_valid_until, recent, utcnow
from credentials import load_credentials
from shops import SHOP_NAMES, Shops, shop_name
from ml_coupon_applicator import CouponApplicator
from olx import OlxMonitor
from cloud_sync import CloudSync

LOG = logging.getLogger('monitor')


def notify_windows(offer: dict):
    from windows_toasts import Toast, WindowsToaster
    toast = Toast()
    key = alert_payment(offer)
    value = alert_price(offer, key)
    payment = ({'pix': 'Pix ', 'card': 'Parcelado ', 'announced': 'Preço anunciado '}.get(key, 'Preço ') + brl(value))
    if value is not None and value == offer.get('coupon_price') and value != offer.get(key):
        payment = brl(value) + ' com cupom na sua sessão'
    toast.text_fields = [offer['component'], payment, offer['shop'] + ' · ' + offer.get('alert_reason', offer['status'])]
    toast.launch_action = offer['url']
    WindowsToaster('Monitor de peças').show_toast(toast)


class Monitor:
    def __init__(self, store: Store, data_dir: Path):
        self.store, self.data_dir = store, data_dir
        self.shops = Shops(data_dir)
        self.client = None
        self.telegram_status = 'Telegram não configurado'
        self.notification_status = 'Ainda não enviada'
        self.shop_status = {name: 'Aguardando primeira consulta' for name in SHOP_NAMES}
        self.source_status: dict[int, str] = {}
        self.tasks: list[asyncio.Task] = []
        self.resolve_lock = asyncio.Lock()
        self.shop_lock = asyncio.Lock()
        self.ml_coupons = CouponApplicator(store, self.shops.ml_browser, self.shop_lock)
        self.olx = OlxMonitor(store, data_dir, notify_windows)
        self.alert_lock = asyncio.Lock()
        self.check_queue: asyncio.Queue[int] = asyncio.Queue(maxsize=300)
        self.queued: set[int] = set()
        self.manual_checks: set[int] = set()
        self.selected: dict[int, dict] = {}
        self.running = False
        self.last_received = None
        self.last_alert = None
        self.last_delay = None
        self.last_shop_scan_started = None
        self.last_shop_scan_finished = None
        self.shop_scan_component_id = None
        self.next_ml_scan = 0
        self.next_coupon_scan = 0
        self.coupon_status = 'Cupons públicos · aguardando primeira consulta'
        self.cloud = CloudSync(self, data_dir)

    async def start(self):
        self.store.prune_coupons()
        self.running = True
        self.tasks = [asyncio.create_task(self.check_worker()), asyncio.create_task(self.shop_loop()),
                      asyncio.create_task(self.telegram_loop()), asyncio.create_task(self.ml_coupons.loop()),
                      asyncio.create_task(self.olx.loop()), asyncio.create_task(self.cloud.loop())]

    async def stop(self):
        self.running = False
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.client:
            await self.client.disconnect()
        await self.shops.close()
        await self.olx.collector.close()
        self.store.close()

    async def telegram_loop(self):
        while self.running:
            try:
                if not self.client or not self.client.is_connected():
                    await self.connect_telegram()
                if self.client and self.client.is_connected():
                    await self.sync_sources()
                    await self.recover_recent()
                    self.telegram_status = 'Conectado · recebendo novas mensagens'
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                raise
            except errors.FloodWaitError as exc:
                self.telegram_status = f'Telegram pediu pausa de {exc.seconds}s'
                await asyncio.sleep(max(exc.seconds, 1))
            except Exception as exc:
                self.telegram_status = 'Conexão interrompida · tentando novamente em 30s'
                LOG.warning('Telegram indisponível: %s', type(exc).__name__)
                if self.client:
                    await self.client.disconnect()
                await asyncio.sleep(30)

    async def connect_telegram(self):
        credentials = load_credentials(self.data_dir)
        if not credentials:
            self.telegram_status = 'Telegram não configurado · execute Conectar-Telegram.cmd'
            return
        if self.client:
            await self.client.disconnect()
        self.client = TelegramClient(str(self.data_dir / 'telegram'), **credentials,
                                     auto_reconnect=True, catch_up=True, flood_sleep_threshold=0, sequential_updates=True)
        self.client.add_event_handler(self.on_message, events.NewMessage())
        self.client.add_event_handler(self.on_edit, events.MessageEdited())
        self.client.add_event_handler(self.on_delete, events.MessageDeleted())
        self.telegram_status = 'Conectando ao Telegram…'
        await self.client.connect()
        if not await self.client.is_user_authorized():
            await self.client.disconnect()
            self.client = None
            self.telegram_status = 'Autenticação necessária · execute Conectar-Telegram.cmd'
            return
        await self.client.get_me()
        await self.sync_sources()
        await self.client.catch_up()

    async def sync_sources(self):
        if not self.client or not self.client.is_connected():
            return
        async with self.resolve_lock:
            enabled = self.store.rows('SELECT * FROM sources WHERE enabled=1')
            enabled_ids = {row['id'] for row in enabled}
            self.selected = {chat: source for chat, source in self.selected.items() if source['id'] in enabled_ids}
            for source in enabled:
                if source['chat_id'] in self.selected:
                    continue
                try:
                    reference = int(source['reference']) if source['reference'].startswith('-') else source['reference']
                    entity = await self.client.get_entity(reference)
                    if not isinstance(entity, (types.Chat, types.Channel)):
                        self.source_status[source['id']] = 'Escolha um grupo ou canal'
                        continue
                    # API não entra em grupos; conta precisa já ser participante.
                    if getattr(entity, 'left', False):
                        self.source_status[source['id']] = 'Entre nesta fonte pelo seu Telegram e tente novamente'
                        continue
                    chat_id = utils.get_peer_id(entity)
                    registered = self.store.rows('SELECT id,name FROM sources WHERE chat_id=? AND id<>?', (chat_id, source['id']))
                    if registered:
                        self.source_status[source['id']] = 'Fonte já cadastrada como ' + registered[0]['name']
                        continue
                    baseline = source['baseline'] or utcnow()
                    self.store.db.execute('UPDATE sources SET chat_id=?,baseline=? WHERE id=?', (chat_id, baseline, source['id']))
                    self.store.db.commit()
                    source.update(chat_id=chat_id, baseline=baseline)
                    self.selected[chat_id] = source
                    self.source_status[source['id']] = 'Acompanhando novas mensagens'
                except errors.FloodWaitError:
                    raise
                except Exception as exc:
                    self.source_status[source['id']] = 'Sem acesso · confira se sua conta participa da fonte'
                    LOG.warning('Fonte não resolvida: %s', type(exc).__name__)

    async def recover_recent(self):
        """No máximo 100 mensagens recentes por fonte; nunca percorre histórico inteiro."""
        for source in list(self.selected.values()):
            cutoff = max(datetime.fromisoformat(source['baseline']), datetime.now(timezone.utc) - timedelta(minutes=5))
            pending = []
            async for message in self.client.iter_messages(source['chat_id'], limit=100):
                if message.date < cutoff:
                    break
                if not self.store.message_processed(source['id'],message.id):
                    pending.append(message)
            for message in reversed(pending):
                await self.ingest(source['chat_id'], message.id, message.raw_text or '', message.date,
                                  [e.url for e in (message.entities or []) if getattr(e, 'url', None)])

    async def on_message(self, event):
        try:
            await self.ingest(event.chat_id, event.id, event.raw_text or '', event.date,
                              [e.url for e in (event.message.entities or []) if getattr(e, 'url', None)])
        except Exception as exc:
            LOG.warning('Falha ao processar mensagem: %s', type(exc).__name__)

    async def on_edit(self, event):
        try:
            await self.ingest(event.chat_id, event.id, event.raw_text or '', event.date,
                              [e.url for e in (event.message.entities or []) if getattr(e, 'url', None)], edited=True)
        except Exception as exc:
            LOG.warning('Falha ao processar edição: %s', type(exc).__name__)

    async def on_delete(self, event):
        if event.chat_id in self.selected:
            self.store.remove_message(event.chat_id, event.deleted_ids)

    async def ingest(self, chat_id: int, message_id: int, text: str, published: datetime,
                     extra_links: list[str] | None = None, edited: bool = False):
        source = self.selected.get(chat_id)
        current_source = self.store.rows('SELECT * FROM sources WHERE chat_id=? AND enabled=1', (chat_id,))
        if not source or not current_source:
            return
        source = current_source[0]
        stamp = published.astimezone(timezone.utc).isoformat()
        if stamp < source['baseline'] or not recent(stamp):
            self.store.checkpoint(source['id'], message_id)
            return
        if not edited and self.store.message_processed(source['id'], message_id):
            return
        self.last_received = utcnow()
        self.last_delay = max(0, (datetime.now(timezone.utc) - published).total_seconds())
        url_list = links(text, extra_links)
        codes = coupons(text)
        username = source['reference'].removeprefix('@')
        message_url = (f'https://t.me/{username}/{message_id}' if source['reference'].startswith('@')
                       else f'https://t.me/c/{str(chat_id).removeprefix("-100")}/{message_id}' if str(chat_id).startswith('-100') else None)
        origin = dict(source=source['name'], chat_id=chat_id, message_id=message_id,
                      message_url=message_url, published_at=stamp)
        if edited:
            self.store.remove_message(chat_id,[message_id])
        if codes:
            self.store.db.execute('INSERT INTO coupon_posts(source,message_id,text,codes,published_at,links,message_url,found_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(source,message_id) DO UPDATE SET text=excluded.text,codes=excluded.codes,links=excluded.links,message_url=excluded.message_url',
                                  (source['name'], message_id, text, json.dumps(codes), stamp, json.dumps(url_list), message_url, utcnow()))
            self.store.db.commit()
        title = next((line.strip() for line in text.splitlines() if line.strip()), 'Oferta do Telegram')
        if url_list:
            from core import prices
            for component in self.store.components():
                if not component['enabled'] or not matches(component, text):
                    continue
                offer = dict(url=url_list[0], title=title[:350], shop=shop_name(url_list[0]),
                             **prices(text), coupons=codes, status='Anunciado no Telegram',
                             message=text, published_at=stamp, received_at=utcnow(), checked_at=None,
                             availability='unknown')
                row, changed = self.store.upsert_offer(component['id'], offer, origin)
                await self.alert(row, fresh=True)
                if changed or row['checked_at'] is None:
                    self.enqueue(row['id'])
        self.store.checkpoint(source['id'], message_id)

    async def alert(self, offer: dict, fresh: bool):
        async with self.alert_lock:
            decision = self.store.alert_evaluation(offer, fresh)
            if not decision:
                return
            try:
                await asyncio.to_thread(notify_windows, dict(offer, alert_reason=decision['reason']))
                self.store.mark_alert(offer)
                self.notification_status = 'Último aviso enviado ao Windows'
                self.last_alert = utcnow()
            except Exception as exc:
                self.notification_status = 'Não foi possível enviar aviso ao Windows · oferta salva no painel'
                LOG.warning('Notificação indisponível: %s', type(exc).__name__)

    def enqueue(self, offer_id: int, manual: bool = False):
        if not manual and not self.store.should_track_offer(self.store.offer(offer_id)):
            return
        if manual:
            self.manual_checks.add(offer_id)
        if offer_id in self.queued:
            return
        try:
            self.check_queue.put_nowait(offer_id)
            self.queued.add(offer_id)
        except asyncio.QueueFull:
            self.manual_checks.discard(offer_id)
            self.store.db.execute("UPDATE offers SET status='Conferência pendente · fila cheia' WHERE id=?", (offer_id,))
            self.store.db.commit()

    async def check_worker(self):
        while True:
            offer_id = await self.check_queue.get()
            try:
                if offer_id in self.manual_checks or self.store.should_track_offer(self.store.offer(offer_id)):
                    await self.check_offer(offer_id)
            finally:
                self.queued.discard(offer_id)
                self.manual_checks.discard(offer_id)
                self.check_queue.task_done()

    async def check_offer(self, offer_id: int):
        row = self.store.offer(offer_id)
        if not row:
            return
        component = next((item for item in self.store.components() if item['id'] == row['component_id']), None)
        if not component or not component['enabled']:
            return
        try:
            found = await self.shops.check(row['url'], component)
            offer_id = self.store.resolve_offer_url(offer_id, found['url'])
            row = self.store.offer(offer_id)
            # Dados anunciados e cupom permanecem identificados; o preço da loja não valida o cupom.
            self.store.db.execute('UPDATE offers SET pix=?,card=?,announced=?,installments=?,installment=?,checked_at=?,availability=?,status=?,title=?,seller=?,shop=?,coupon_price=?,brand=?,shipping_origin=?,valid_until=? WHERE id=?',
                                  (found['pix'], found['card'], found['announced'], found['installments'], found['installment'],
                                   found['checked_at'], found['availability'], 'Preço da loja lido · cupom não validado' if json.loads(row['coupons'])
                                   else 'Preço lido na loja', found.get('title') or row['title'],
                                   found.get('seller') or row['seller'], found.get('shop') or row['shop'], found.get('coupon_price'),
                                   found.get('brand') or detect_brand(found.get('title') or row['title']), found.get('shipping_origin', 'unknown'), reading_valid_until(found), offer_id))
            self.store.db.execute('INSERT INTO observations(offer_id,observed_at,pix,card,announced,status,availability,coupon_price) VALUES(?,?,?,?,?,?,?,?)',
                                  (offer_id, utcnow(), found['pix'], found['card'], found['announced'], found['status'], found['availability'], found.get('coupon_price')))
            self.store.db.commit()
            updated = self.store.offer(offer_id)
            previous_delivered = self.store.db.execute('SELECT 1 FROM alerts WHERE offer_id=? AND fingerprint=?',
                                                        (offer_id,row['fingerprint'])).fetchone() is not None
            updated['fingerprint'] = offer_fingerprint(updated)
            self.store.db.execute('UPDATE offers SET fingerprint=? WHERE id=?', (updated['fingerprint'],offer_id))
            self.store.db.execute('UPDATE alerts SET identity=? WHERE offer_id=?', (self.store.alert_identity(updated), offer_id))
            self.store.db.commit()
            if previous_delivered and alert_payment(row) != alert_payment(updated):
                # A primeira confirmação estabelece referência na nova condição;
                # não compara preço anunciado sem pagamento com Pix/cartão.
                self.store.mark_alert(updated, notified=False)
            await self.alert(updated, fresh=price_is_current(updated))
        except (ValueError, httpx.HTTPError) as exc:
            self.store.db.execute('UPDATE offers SET status=?,checked_at=?,valid_until=NULL WHERE id=?',
                                  (str(exc) if isinstance(exc, ValueError) else 'Falha de rede ao conferir a loja', utcnow(), offer_id))
            self.store.db.commit()
        except Exception as exc:
            LOG.warning('Conferência falhou: %s', type(exc).__name__)
            self.store.db.execute("UPDATE offers SET status='Falha na conferência · anúncio preservado',checked_at=?,valid_until=NULL WHERE id=?", (utcnow(), offer_id))
            self.store.db.commit()

    async def shop_loop(self):
        while self.running:
            started = monotonic()
            await self.scan_shops()
            await asyncio.sleep(max(0, 600 - (monotonic() - started)))

    async def scan_shops(self, force_ml: bool = False, component_id: int | None = None, shops: tuple | None = None):
        if self.shop_lock.locked():
            return
        if component_id is not None and not any(part['id'] == component_id and part['enabled'] for part in self.store.components()):
            return
        async with self.shop_lock:
            self.shop_scan_component_id = component_id
            self.last_shop_scan_started = utcnow()
            order = [name for name in SHOP_NAMES if name != 'Mercado Livre'] + ['Mercado Livre']
            if shops is not None:
                order = [name for name in order if name in shops]
            for shop in order:
                if shop == 'Mercado Livre':
                    now = monotonic()
                    if component_id is None:
                        try:
                            found = await self.shops.coupon_list()
                            self.store.set_setting('pichau_coupons', json.dumps(found, ensure_ascii=False))
                        except (ValueError, httpx.HTTPError):
                            pass
                        if force_ml or now >= self.next_coupon_scan:
                            self.next_coupon_scan = now + 1800
                            self.coupon_status = 'Cupons públicos · consultando cupons…'
                            try:
                                public = await self.shops.public_coupon_list()
                                self.store.set_setting('public_coupons', json.dumps(public, ensure_ascii=False))
                                self.coupon_status = f'Cupons públicos · {len(public)} cupons/ativações consultados'
                            except (ValueError, httpx.HTTPError):
                                self.coupon_status = 'Cupons públicos · consulta indisponível; última leitura preservada'
                if self.store.get_setting('shop:' + shop, '1') != '1':
                    self.shop_status[shop] = 'Consulta pausada'
                    continue
                if shop == 'Mercado Livre':
                    if component_id is None:
                        if not force_ml and now < self.next_ml_scan:
                            continue
                        self.next_ml_scan = now + 1800
                count, failures = 0, []
                self.shop_status[shop] = 'Consultando…'
                for component in self.store.components():
                    if not component['enabled'] or component_id is not None and component['id'] != component_id:
                        continue
                    attempted = set()
                    try:
                        candidates = (await self.shops.discover_mercado_livre(component) if shop == 'Mercado Livre'
                                      else [dict(url=url, reading=None) for url in await self.shops.discover(shop, component)])
                        for candidate in candidates:
                            url = candidate['url']
                            reading = candidate['reading']
                            if reading:
                                reading['valid_until'] = reading_valid_until(reading)
                            attempted.add(canonical_url(url))
                            known = self.store.rows('SELECT * FROM offers WHERE component_id=? AND url=?',
                                                    (component['id'], canonical_url(url)))
                            tracked = (dict((known[0] if known else dict(id=None, component_id=component['id'])), **reading)
                                       if reading else known[0] if known else None)
                            if tracked and not self.store.should_track_offer(tracked):
                                continue
                            try:
                                needs_product = (reading is None or reading.get('shipping_origin') != 'local'
                                                 or component.get('target') is not None
                                                 and reading.get(component.get('target_payment', 'pix')) is None)
                                offer = await self.shops.check(url, component) if needs_product else reading
                                attempted.add(canonical_url(offer['url']))
                                row, changed = self.store.upsert_offer(component['id'], offer,
                                                                       dict(source=shop, published_at=offer['published_at']))
                                count += 1
                                await self.alert(row, fresh=True)
                            except (ValueError, httpx.HTTPError) as exc:
                                failures.append(str(exc) if isinstance(exc, ValueError) else 'Falha de rede')
                                self.store.db.execute('UPDATE offers SET valid_until=NULL,status=? WHERE component_id=? AND url=?',
                                                      ('Falha na revalidação · anúncio preservado', component['id'], canonical_url(url)))
                                self.store.db.commit()
                            if needs_product:
                                await asyncio.sleep(1)
                    except (ValueError, httpx.HTTPError) as exc:
                        failures.append(str(exc) if isinstance(exc, ValueError) else 'Falha de rede ao consultar a loja')
                    except Exception as exc:
                        LOG.warning('Consulta de loja falhou: %s', type(exc).__name__)
                        failures.append('Falha ao extrair os dados da loja')
                    stale = [row for row in self.store.rows('SELECT * FROM offers WHERE component_id=? AND shop=? ORDER BY COALESCE(checked_at,received_at)', (component['id'], shop))
                             if not price_is_current(row) and canonical_url(row['url']) not in attempted
                             and row.get('shipping_origin') != 'international' and matches(component, row['title'])
                             and self.store.should_track_offer(row)]
                    for row in stale[:4]:
                        await self.check_offer(row['id'])
                        await asyncio.sleep(1)
                self.shop_status[shop] = (f'{count} anúncio(s) consultado(s) · {datetime.now().strftime("%H:%M:%S")}'
                                          if count else (failures[0] if failures else 'Nenhum anúncio encontrado para esta peça' if component_id is not None else 'Nenhuma peça ativa'))
                if count and failures:
                    self.shop_status[shop] += ' · algumas consultas falharam'
            self.last_shop_scan_finished = utcnow()

    async def test_notification(self):
        try:
            await asyncio.to_thread(notify_windows, dict(component='Monitor de peças · teste',
                                                        pix=None, card=None, announced=None,
                                                        shop='Aviso de teste', status='Notificações locais',
                                                        url='http://127.0.0.1:8765'))
            self.notification_status = 'Aviso de teste enviado ao Windows'
            return True
        except Exception as exc:
            self.notification_status = 'Windows não aceitou a notificação de teste'
            LOG.warning('Teste de notificação falhou: %s', type(exc).__name__)
            return False
