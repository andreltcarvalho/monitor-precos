import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch
from telethon import types

import httpx
from core import Store, utcnow
from monitor import Monitor, notify_windows
from shops import Shops


class MonitorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.temp.name)/'monitor.sqlite3')
        self.monitor=Monitor(self.store,Path(self.temp.name))
        self.monitor.shops.public_coupon_list = AsyncMock(return_value=[])
        self.monitor.shops.discover_mercado_livre = AsyncMock(return_value=[])
        self.now=datetime.now(timezone.utc)
        self.store.db.execute('UPDATE sources SET chat_id=?,baseline=? WHERE id=1',(-100123,(self.now-timedelta(seconds=5)).isoformat()))
        self.store.db.commit()
        self.monitor.selected={-100123:self.store.sources()[0]}
        self.toast=patch('monitor.notify_windows')
        self.notify=self.toast.start()

    async def asyncTearDown(self):
        self.toast.stop()
        await self.monitor.shops.close()
        self.store.close()
        self.temp.cleanup()

    async def send(self, message_id=1, stamp=None, chat=-100123, text=None, edited=False):
        await self.monitor.ingest(chat,message_id,text or 'RTX 5060 por R$2.500,00 no Pix\nhttps://www.pichau.com.br/placa-de-video-rtx-5060',stamp or self.now,edited=edited)

    async def test_alert_precedes_store_check_and_deduplicates(self):
        self.monitor.shops.check=AsyncMock()
        await self.send()
        self.notify.assert_called_once()
        self.monitor.shops.check.assert_not_called()
        self.assertEqual(self.monitor.check_queue.qsize(),1)
        await self.send()
        await self.send(message_id=2)
        self.notify.assert_called_once()
        self.assertEqual(len(self.store.offers()),1)

    async def test_only_selected_sources_are_processed(self):
        await self.send(chat=-100999)
        self.assertEqual(self.store.offers(),[])
        self.notify.assert_not_called()

    async def test_expensive_message_is_saved_silently_and_cheaper_message_alerts(self):
        await self.send()
        self.notify.reset_mock()
        await self.send(message_id=2, text='RTX 5060 por R$2600 no Pix\nhttps://www.pichau.com.br/placa-mais-cara')
        self.notify.assert_not_called()
        self.assertEqual(len(self.store.offers()), 2)
        await self.send(message_id=3, text='RTX 5060 por R$2400 no Pix\nhttps://www.pichau.com.br/placa-mais-barata')
        self.notify.assert_called_once()
        self.assertEqual(self.notify.call_args.args[0]['pix'], 240000)

    async def test_confirmation_can_alert_when_price_becomes_known_without_a_limit(self):
        await self.send(text='RTX 5060 oferta nova\nhttps://www.pichau.com.br/placa-sem-preco')
        self.notify.assert_not_called()
        row = self.store.offers()[0]
        self.monitor.shops.check = AsyncMock(return_value=dict(
            url=row['url'], pix=230000, card=250000, announced=None, installments=10,
            installment=25000, checked_at=self.now.isoformat(), availability='in', status='Preço lido na loja'))
        await self.monitor.check_offer(row['id'])
        self.notify.assert_called_once()
        await self.monitor.check_offer(row['id'])
        self.notify.assert_called_once()

    async def test_store_scan_keeps_expensive_offers_without_notifying(self):
        await self.send()
        self.notify.reset_mock()
        async def discover(shop, component):
            return ['https://www.pichau.com.br/cara', 'https://www.pichau.com.br/barata'] if shop == 'Pichau' and component['id'] == 1 else []
        async def check(url, component):
            return dict(url=url, title='RTX 5060 ' + url.rsplit('/', 1)[-1], shop='Pichau',
                        pix=240000 if url.endswith('/barata') else 260000, card=None, announced=None,
                        coupons=[], status='Preço lido na loja', availability='in',
                        published_at=self.now.isoformat(), received_at=self.now.isoformat())
        self.monitor.shops.discover = AsyncMock(side_effect=discover)
        self.monitor.shops.check = AsyncMock(side_effect=check)
        self.monitor.shops.coupon_list = AsyncMock(return_value=[])
        with patch('monitor.asyncio.sleep', new=AsyncMock()):
            await self.monitor.scan_shops()
        self.assertEqual(len(self.store.offers()), 3)
        self.notify.assert_called_once()
        self.assertEqual(self.notify.call_args.args[0]['pix'], 240000)

    def test_card_limit_notification_displays_the_compared_card_total(self):
        with patch('windows_toasts.Toast') as toast, patch('windows_toasts.WindowsToaster'):
            notify_windows(dict(component='RTX 5060', pix=250000, card=280000, target=300000,
                                target_payment='card', shop='Pichau', status='Preço lido na loja',
                                url='https://www.pichau.com.br/placa'))
            self.assertEqual(toast.return_value.text_fields[1], 'Parcelado R$ 2.800,00')

    def test_notification_contains_the_reason_without_claiming_a_coupon_discount(self):
        with patch('windows_toasts.Toast') as toast, patch('windows_toasts.WindowsToaster'):
            notify_windows(dict(component='RTX 5060', pix=250000, card=None, shop='Pichau',
                                status='Preço da loja lido · cupom não validado',
                                alert_reason='Novo menor preço da peça · queda de 2.0% desde o último aviso',
                                url='https://www.pichau.com.br/placa'))
            self.assertIn('Novo menor preço', toast.return_value.text_fields[2])
            self.assertIn('queda de 2.0%', toast.return_value.text_fields[2])

    async def test_confirmation_keeps_last_notified_price_until_two_percent_drop(self):
        await self.send()
        row = self.store.offers()[0]
        def found(price):
            return dict(url=row['url'], title='MSI RTX 5060', shop='Pichau', seller='Pichau',
                        pix=price, card=None, announced=None, installments=None, installment=None,
                        checked_at=utcnow(), availability='in', status='Preço lido na loja')
        self.monitor.shops.check = AsyncMock(return_value=found(247500))
        await self.monitor.check_offer(row['id'])
        self.notify.assert_called_once()
        self.assertEqual(self.store.offer(row['id'])['title'], 'MSI RTX 5060')
        self.monitor.shops.check.return_value = found(245000)
        await self.monitor.check_offer(row['id'])
        self.assertEqual(self.notify.call_count, 2)
        self.assertIn('queda de 2.0%', self.notify.call_args.args[0]['alert_reason'])

    async def test_payment_clarification_does_not_repeat_and_later_drop_can_notify(self):
        await self.send(text='RTX 5060 por R$2500\nhttps://www.pichau.com.br/placa')
        row = self.store.offers()[0]
        found = dict(url=row['url'], pix=240000, card=None, announced=None, installments=None,
                     installment=None, checked_at=utcnow(), availability='in', status='Preço lido na loja')
        self.monitor.shops.check = AsyncMock(return_value=found)
        await self.monitor.check_offer(row['id'])
        self.notify.assert_called_once()
        found['pix'] = 237600
        await self.monitor.check_offer(row['id'])
        self.notify.assert_called_once()
        found['pix'] = 235200
        await self.monitor.check_offer(row['id'])
        self.assertEqual(self.notify.call_count, 2)
        self.assertIn('primeira confirmação', self.notify.call_args.args[0]['alert_reason'])

    async def test_concurrent_alerts_do_not_deliver_twice(self):
        await self.send(text='RTX 5060 oferta nova\nhttps://www.pichau.com.br/placa')
        row = self.store.offer(self.store.offers()[0]['id'])
        row.update(pix=250000, fingerprint='new-price')
        self.store.db.execute('UPDATE offers SET pix=?,fingerprint=? WHERE id=?', (250000, 'new-price', row['id']))
        self.store.db.commit()
        await asyncio.gather(self.monitor.alert(row, True), self.monitor.alert(row, True))
        self.notify.assert_called_once()

    async def test_failed_repeat_does_not_advance_price_reference(self):
        await self.send()
        self.notify.side_effect = PermissionError()
        await self.send(message_id=2, text='RTX 5060 por R$2400 no Pix\nhttps://www.pichau.com.br/placa-de-video-rtx-5060')
        self.assertEqual(self.store.rows('SELECT price FROM alerts')[0]['price'], 250000)
        self.notify.side_effect = None
        await self.monitor.alert(self.store.offer(self.store.offers()[0]['id']), True)
        self.assertEqual(len(self.store.rows('SELECT * FROM alerts WHERE notified=1')), 2)

    async def test_old_messages_and_first_connection_history_are_ignored(self):
        await self.send(stamp=self.now-timedelta(hours=1))
        self.assertEqual(self.store.offers(),[])
        self.notify.assert_not_called()

    async def test_paused_source_does_not_generate_offers(self):
        self.store.toggle('sources',1,False)
        await self.send()
        self.assertEqual(self.store.offers(),[])

    async def test_same_channel_by_username_and_id_keeps_active_source(self):
        self.store.save_source('Adrenaline repetido', '-100123')
        self.monitor.client = Mock()
        self.monitor.client.is_connected.return_value = True
        self.monitor.client.get_entity = AsyncMock(return_value=types.Channel(
            id=123, title='Adrenaline', photo=types.ChatPhotoEmpty(), date=self.now))
        with patch('monitor.utils.get_peer_id', return_value=-100123):
            await self.monitor.sync_sources()
        self.assertEqual(len(self.monitor.selected), 1)
        self.assertIn('Fonte já cadastrada', self.monitor.source_status[2])
        self.assertEqual(self.store.sources()[0]['chat_id'], -100123)
        await self.send()
        self.notify.assert_called_once()

    async def test_source_messages_out_of_order_do_not_disappear(self):
        await self.send(message_id=2)
        await self.send(message_id=1,text='RTX 5060 por R$2400 no Pix\nhttps://www.pichau.com.br/placa-de-video-outra-rtx-5060')
        self.assertEqual(len(self.store.offers()),2)

    async def test_edited_message_no_longer_matching_withdraws_origin(self):
        await self.send()
        await self.send(text='Oferta encerrada',edited=True)
        self.assertEqual(self.store.offers()[0]['status'],'Publicação removida')

    async def test_generic_coupon_is_stored_without_fake_product_offer(self):
        text = 'Novo cupom no Mercado Livre\n`SITE0110`\n10% OFF em R$79, limite R$30\nhttps://mercadolivre.com/sec/test'
        received = (self.now + timedelta(seconds=30)).isoformat()
        with patch('monitor.utcnow', return_value=received):
            await self.send(text=text)
        self.assertEqual(self.store.offers(),[])
        self.assertEqual(len(self.store.rows('SELECT * FROM coupon_posts')),1)
        row = self.store.rows('SELECT * FROM coupon_posts')[0]
        self.assertEqual((row['published_at'], row['found_at']), (self.now.isoformat(), received))
        with patch('monitor.utcnow', return_value=(self.now + timedelta(minutes=1)).isoformat()):
            await self.send(text=text + '\nCondições atualizadas', edited=True)
        self.assertEqual(self.store.rows('SELECT found_at FROM coupon_posts')[0]['found_at'], received)

    async def test_missing_payment_with_limit_keeps_offer_without_alert(self):
        self.store.db.execute("UPDATE components SET target=260000 WHERE id=1")
        self.store.db.commit()
        await self.send(text='RTX 5060 por R$2.500,00\nhttps://www.pichau.com.br/placa-de-video-rtx-5060')
        self.assertEqual(len(self.store.offers()),1)
        self.notify.assert_not_called()

    async def test_failed_confirmation_keeps_announced_offer(self):
        await self.send()
        self.monitor.shops.check=AsyncMock(side_effect=ValueError('A loja recusou a consulta (403)'))
        await self.monitor.check_offer(self.store.offers()[0]['id'])
        offer=self.store.offers()[0]
        self.assertEqual(offer['pix'],250000)
        self.assertIn('403',offer['status'])

    async def test_failed_notification_is_not_marked_delivered(self):
        self.notify.side_effect=PermissionError()
        await self.send()
        self.assertEqual(self.store.rows('SELECT * FROM alerts'),[])
        self.assertEqual(len(self.store.offers()),1)

    async def test_scan_cycle_finishes_even_when_shop_queries_are_refused(self):
        self.monitor.shops.discover = AsyncMock(side_effect=ValueError('Consulta recusada'))
        self.monitor.shops.coupon_list = AsyncMock(side_effect=ValueError('Cupons indisponíveis'))
        with patch('monitor.utcnow', side_effect=['2026-10-01T20:00:00+00:00', '2026-10-01T20:00:10+00:00']):
            await self.monitor.scan_shops()
        self.assertEqual(self.monitor.last_shop_scan_started, '2026-10-01T20:00:00+00:00')
        self.assertEqual(self.monitor.last_shop_scan_finished, '2026-10-01T20:00:10+00:00')
        self.assertFalse(self.monitor.shop_lock.locked())

    async def test_cancelled_scan_does_not_claim_completion(self):
        entered = asyncio.Event()
        async def discover(*args):
            entered.set()
            await asyncio.Event().wait()
        self.monitor.shops.discover = AsyncMock(side_effect=discover)
        self.monitor.last_shop_scan_finished = '2026-10-01T19:00:00+00:00'
        task = asyncio.create_task(self.monitor.scan_shops())
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIsNotNone(self.monitor.last_shop_scan_started)
        self.assertEqual(self.monitor.last_shop_scan_finished, '2026-10-01T19:00:00+00:00')
        self.assertFalse(self.monitor.shop_lock.locked())

    async def test_second_scan_does_not_reset_the_running_cycle(self):
        await self.monitor.shop_lock.acquire()
        try:
            self.monitor.last_shop_scan_started = '2026-10-01T20:00:00+00:00'
            self.monitor.shops.discover = AsyncMock()
            await self.monitor.scan_shops()
            self.assertEqual(self.monitor.last_shop_scan_started, '2026-10-01T20:00:00+00:00')
            self.monitor.shops.discover.assert_not_called()
        finally:
            self.monitor.shop_lock.release()


class FetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_untrusted_redirect_never_queries_local_network(self):
        client=Shops()
        seen=[]
        def handle(request):
            seen.append(str(request.url))
            return httpx.Response(302,headers={'location':'https://127.0.0.1/private'})
        await client.client.aclose()
        client.client=httpx.AsyncClient(transport=httpx.MockTransport(handle))
        try:
            with self.assertRaises(ValueError):
                await client.fetch('https://meli.la/test')
            self.assertEqual(len(seen),1)
        finally:
            await client.close()


if __name__=='__main__':
    unittest.main()
