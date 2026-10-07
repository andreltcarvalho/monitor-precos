import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import httpx

from core import Store
from olx import OlxCollector, OlxMonitor, city_confirmed, eligible, olx_url, parse_search, search_input, search_url

URL = 'https://www.olx.com.br/estado-sp?q=cadeira&sf=1'
FIXTURE = Path(__file__).parent / 'fixtures' / 'olx-search.html'


def listing(ad_id='1234567890', price=50000, title='Cadeira de escritório'):
    return dict(ad_id=ad_id, price=price, title=title,
                url='https://sp.olx.com.br/grande-campinas/escritorio/cadeira-' + ad_id,
                location='Piracicaba, Centro', published_text='Hoje, 10:00')


class OlxParsingTests(unittest.TestCase):
    def test_real_cards_read_current_price_not_old_price_or_installment(self):
        result = parse_search(FIXTURE.read_text(encoding='utf-8'), URL)
        self.assertEqual(len(result), 4)
        discounted = next(row for row in result if row['ad_id'] == '1459825416')
        self.assertEqual(discounted['price'], 8000)
        self.assertEqual(discounted['location'], 'Osasco, Bandeiras')
        self.assertEqual(result[0]['price'], 9000)
        self.assertEqual(result[0]['published_text'], 'Hoje, 08:10')
        self.assertNotIn('pix', discounted)

    def test_ad_id_deduplicates_tracking_parameters(self):
        html = FIXTURE.read_text(encoding='utf-8')
        self.assertEqual(len(parse_search(html + html, URL)), 4)

    def test_unknown_price_does_not_take_installment_or_other_card(self):
        html = '<section class="olx-adcard"><a data-testid="adcard-link" href="' + listing()['url'] + '">Cadeira</a><p>R$ 10 em 10x</p></section>'
        self.assertIsNone(parse_search(html, URL)[0]['price'])

    def test_cloudflare_is_error_not_empty_search(self):
        with self.assertRaisesRegex(ValueError, 'verificação humana'):
            parse_search('<title>Attention Required! | Cloudflare</title>', URL)

    def test_missing_layout_is_error_but_explicit_empty_results_are_valid(self):
        with self.assertRaises(ValueError):
            parse_search('<title>OLX</title><h1>Busque agora</h1>', URL)
        self.assertEqual(parse_search('<div id="total-of-ads">0 resultados</div>', URL), [])

    def test_external_links_and_invalid_ids_are_never_ingested(self):
        html = '<section class="olx-adcard"><a data-testid="adcard-link" href="https://evil.test/cadeira-1234567890">Cadeira</a></section>'
        with self.assertRaises(ValueError):
            parse_search(html, URL)

    def test_search_url_preserves_filters_and_resets_page_and_order(self):
        url = olx_url(URL + '&pe=700&furnitures_office_chairs_condition=2&o=4&sf=2')
        params = parse_qs(urlsplit(url).query)
        self.assertEqual(params['pe'], ['700'])
        self.assertEqual(params['furnitures_office_chairs_condition'], ['2'])
        self.assertEqual(params['sf'], ['1'])
        self.assertNotIn('o', params)

    def test_urls_cannot_escape_to_accounts_or_external_hosts(self):
        for url in ['http://www.olx.com.br/brasil', 'https://olx.com.br.evil.test/brasil',
                    'https://www.olx.com.br@evil.test/brasil', 'https://conta.olx.com.br/notificacoes',
                    'https://www.olx.com.br:444/brasil', 'https://user:password@www.olx.com.br/brasil',
                    'https://www.olx.com.br/copyright.htm', listing()['url']]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                olx_url(url)

    def test_both_input_modes_and_precise_price_filter(self):
        fields = search_input('Cadeira', 'fields', query='cadeira escritório', city='Piracicaba', target='700,50')
        self.assertEqual((fields['city'], fields['target']), ('Piracicaba', 70050))
        self.assertEqual(parse_qs(urlsplit(fields['url']).query)['pe'], ['701'])
        self.assertEqual(urlsplit(fields['url']).path, '/estado-sp/grande-campinas/piracicaba')
        link = search_input('Cadeira', 'link', url=URL, city='ignorar')
        self.assertEqual((link['city'], link['query']), ('', ''))
        for value in ['-1', 'NaN', '0', 'abc']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                search_input('Cadeira', 'link', url=URL, target=value)

    def test_title_exclusion_and_ceiling_keep_unknown_price_out(self):
        search = dict(target=70000, excluded='quebrado, peças')
        self.assertTrue(eligible(search, listing()))
        self.assertFalse(eligible(search, listing(price=80000)))
        self.assertFalse(eligible(search, listing(price=None)))
        self.assertFalse(eligible(search, listing(title='Cadeira para PEÇAS')))

    def test_city_form_excludes_nearby_towns_and_unknown_location(self):
        search = dict(target=None, excluded='', city='Piracicaba')
        self.assertTrue(eligible(search, listing()))
        self.assertFalse(eligible(search, dict(listing(), location='Campinas, Centro')))
        self.assertFalse(eligible(search, dict(listing(), location='')))

    def test_existing_piracicaba_search_uses_city_route_and_preserves_query_filters(self):
        search = dict(url=URL + '&pe=701', resolved_url=URL + '&pe=701', city='piracicaba', state='SP')
        result = search_url(search)
        self.assertEqual(urlsplit(result).path, '/estado-sp/grande-campinas/piracicaba')
        self.assertEqual(parse_qs(urlsplit(result).query), {'q': ['cadeira'], 'pe': ['701'], 'sf': ['1']})
        category = 'https://www.olx.com.br/informatica/placas-de-video/estado-sp?q=rtx&sf=1'
        self.assertEqual(urlsplit(search_url(dict(search, resolved_url=category))).path,
                         '/informatica/placas-de-video/estado-sp/grande-campinas/piracicaba')
        for changes in (dict(city='Campinas'), dict(city='Piracicaba', state='MG'), dict(city='', state='')):
            self.assertEqual(search_url(dict(search, **changes)), olx_url(URL + '&pe=701'))

    def test_city_confirmation_requires_destination_not_city_in_query_or_similar_name(self):
        for heading in ('"rtx" em Piracicaba', 'Placas de Vídeo - Piracicaba, São Paulo'):
            self.assertTrue(city_confirmed('<div id="total-of-ads"><h1>' + heading + '</h1></div>', 'Piracicaba'))
        for heading in ('"Piracicaba" em São Paulo', '"rtx" em Piracicaba Mirim', '"rtx" em Campinas'):
            self.assertFalse(city_confirmed('<div id="total-of-ads"><h1>' + heading + '</h1></div>', 'Piracicaba'))

    def test_local_parser_excludes_recommendations_and_unknown_locations(self):
        html = FIXTURE.read_text(encoding='utf-8').replace('Osasco, Bandeiras', 'Piracicaba, Centro')
        result = parse_search(html, URL, 'Piracicaba')
        self.assertTrue(result)
        self.assertTrue(all(row['location'] == 'Piracicaba, Centro' for row in result))
        self.assertEqual(parse_search(FIXTURE.read_text(encoding='utf-8'), URL, 'Piracicaba'), [])


class OlxCityCollectorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.collector = OlxCollector(Path(self.temp.name) / 'profile')
        self.search = dict(url=URL, resolved_url=None, city='Piracicaba', state='SP')
        self.city_url = search_url(self.search)
        html = FIXTURE.read_text(encoding='utf-8')
        self.local_html = html.replace('em São Paulo', 'em Piracicaba').replace('Osasco, Bandeiras', 'Piracicaba, Centro')

    async def asyncTearDown(self):
        await self.collector.close()
        self.temp.cleanup()

    async def test_city_page_needs_no_location_selector_even_when_unavailable(self):
        page = MagicMock()
        page.url = self.city_url
        page.goto.return_value.status = 200
        page.content.return_value = self.local_html + '<p>Seleção de localização indisponível no momento</p>'
        with patch.object(self.collector, '_page', return_value=page):
            results, resolved = await self.collector.search(self.search)
        self.assertEqual(resolved, self.city_url)
        page.goto.assert_called_once_with(self.city_url, wait_until='domcontentloaded', timeout=30000)
        page.get_by_role.assert_not_called()
        self.assertTrue(results)
        self.assertTrue(all(row['location'] == 'Piracicaba, Centro' for row in results))

    async def test_direct_read_rejects_state_results_even_with_cached_url(self):
        self.search['resolved_url'] = URL
        await self.collector.client.aclose()
        self.collector.client = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=FIXTURE.read_text(encoding='utf-8'))))
        browser = Mock(return_value=([], self.city_url))
        with patch.object(self.collector, '_search_browser', browser):
            results, resolved = await self.collector.search(self.search)
        browser.assert_called_once_with(self.search, self.city_url)
        self.assertEqual((results, resolved), ([], self.city_url))

    async def test_direct_read_filters_out_of_city_recommendations(self):
        self.search['resolved_url'] = self.city_url
        await self.collector.client.aclose()
        self.collector.client = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=self.local_html)))
        with patch.object(self.collector, '_search_browser') as browser:
            results, _ = await self.collector.search(self.search)
        browser.assert_not_called()
        self.assertTrue(results)
        self.assertTrue(all(row['location'] == 'Piracicaba, Centro' for row in results))


class OlxMonitorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'test.sqlite3')
        self.notify = Mock()
        self.monitor = OlxMonitor(self.store, self.root, self.notify)
        self.search_id = self.monitor.save_search(name='Cadeira', mode='link', url=URL, target='700')
        self.monitor.collector.search = AsyncMock(return_value=([listing()], URL))

    async def asyncTearDown(self):
        await self.monitor.collector.close()
        self.store.close()
        self.temp.cleanup()

    async def test_baseline_and_repeated_read_do_not_alert(self):
        await self.monitor.scan()
        self.notify.assert_not_called()
        self.assertIsNotNone(self.monitor.searches()[0]['baseline'])
        await self.monitor.scan()
        self.notify.assert_not_called()
        self.assertEqual(len(self.monitor.listings(self.search_id)), 1)
        self.assertEqual(len(self.store.rows('SELECT * FROM olx_observations')), 1)

    async def test_first_batch_preserves_olx_recent_order(self):
        self.monitor.collector.search.return_value = ([listing('1234567891'), listing('1234567890')], URL)
        await self.monitor.scan()
        self.assertEqual([row['ad_id'] for row in self.monitor.listings(self.search_id)], ['1234567891', '1234567890'])

    async def test_new_ad_once_and_real_reduction_alert_again(self):
        await self.monitor.scan()
        newer = listing('1234567891', price=60000)
        self.monitor.collector.search.return_value = ([listing(), newer], URL)
        await self.monitor.scan()
        self.assertEqual(self.notify.call_count, 1)
        self.assertEqual(self.notify.call_args.args[0]['announced'], 60000)
        await self.monitor.scan()
        self.assertEqual(self.notify.call_count, 1)
        self.monitor.collector.search.return_value = ([listing(), dict(newer, price=55000)], URL)
        await self.monitor.scan()
        self.assertEqual(self.notify.call_count, 2)
        self.assertIn('Preço caiu', self.notify.call_args.args[0]['alert_reason'])

    async def test_above_ceiling_later_drop_below_ceiling_is_not_missed(self):
        self.monitor.collector.search.return_value = ([listing(price=80000)], URL)
        await self.monitor.scan()
        self.monitor.collector.search.return_value = ([listing(price=65000)], URL)
        await self.monitor.scan()
        self.notify.assert_called_once()

    async def test_failure_does_not_renew_reading_or_establish_baseline(self):
        self.monitor.collector.search.side_effect = ValueError('Cloudflare bloqueou')
        await self.monitor.scan()
        self.assertIsNone(self.monitor.searches()[0]['baseline'])
        self.monitor.collector.search.side_effect = None
        await self.monitor.scan()
        before = self.monitor.listings(self.search_id)
        checked = self.monitor.searches()[0]['checked_at']
        self.monitor.collector.search.side_effect = ValueError('Falha de rede')
        await self.monitor.scan()
        self.assertEqual(self.monitor.listings(self.search_id), before)
        self.assertEqual(self.monitor.searches()[0]['checked_at'], checked)

    async def test_notification_failure_retries_only_when_currently_observed(self):
        await self.monitor.scan()
        self.monitor.collector.search.return_value = ([listing(price=45000)], URL)
        self.notify.side_effect = RuntimeError('Windows indisponível')
        await self.monitor.scan()
        self.assertEqual(self.monitor.listings(self.search_id)[0]['reference_price'], 50000)
        self.monitor.collector.search.return_value = ([], URL)
        await self.monitor.scan()
        self.assertEqual(self.notify.call_count, 1)
        self.monitor.collector.search.return_value = ([listing(price=45000)], URL)
        self.notify.side_effect = None
        await self.monitor.scan()
        self.assertEqual(self.notify.call_count, 2)
        self.assertIsNone(self.monitor.listings(self.search_id)[0]['pending'])

    async def test_price_increase_does_not_reset_alert_reference(self):
        await self.monitor.scan()
        for price in [55000, 50000, 51000]:
            self.monitor.collector.search.return_value = ([listing(price=price)], URL)
            await self.monitor.scan()
        self.notify.assert_not_called()

    async def test_paused_search_is_not_collected_and_deleted_search_is_not_recreated(self):
        self.store.db.execute('UPDATE olx_searches SET enabled=0')
        self.store.db.commit()
        await self.monitor.scan()
        self.monitor.collector.search.assert_not_called()
        self.store.db.execute('UPDATE olx_searches SET enabled=1')
        async def delete_during_read(search):
            self.store.db.execute('DELETE FROM olx_searches WHERE id=?', (self.search_id,))
            self.store.db.commit()
            return [listing()], URL
        self.monitor.collector.search.side_effect = delete_during_read
        await self.monitor.scan()
        self.assertEqual(self.store.rows('SELECT * FROM olx_listings'), [])

    async def test_overlapping_scan_returns_without_duplicate_request(self):
        async with self.monitor.lock:
            self.assertFalse(await self.monitor.scan())
        self.monitor.collector.search.assert_not_called()

    async def test_disappeared_listing_is_preserved_without_claiming_sold(self):
        await self.monitor.scan()
        self.monitor.collector.search.return_value = ([], URL)
        await self.monitor.scan()
        self.assertEqual(len(self.monitor.listings(self.search_id)), 1)
        self.assertNotEqual(self.monitor.listings(self.search_id)[0]['checked_at'], self.monitor.searches()[0]['checked_at'])

    async def test_http_block_switches_to_browser_and_does_not_retry_http_each_cycle(self):
        collector = self.monitor.collector
        collector.client.get = AsyncMock(return_value=httpx.Response(403, request=httpx.Request('GET', URL)))
        collector._run = AsyncMock(return_value=([listing()], URL))
        search = self.monitor.searches()[0]
        await OlxCollector.search(collector, search)
        await OlxCollector.search(collector, search)
        collector.client.get.assert_awaited_once()
        self.assertTrue(collector.browser_required)
        # Restabelece _run para fechar de fato o executor no teardown.
        del collector._run


if __name__ == '__main__':
    unittest.main()
