import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core import Store, group_offers, utcnow
from monitor import Monitor
from shops import Shops, product_offer, search_links


URL = 'https://www.mercadolivre.com.br/msi-rtx-5060/p/MLB123'
SEARCH = 'https://lista.mercadolivre.com.br/rtx-5060'
LOCAL = SEARCH + '_NoIndex_True_SHIPPING*ORIGIN_10215068'
PART = {'id': 1, 'kind': 'gpu', 'query': 'rtx 5060'}


def page(delivery='Chegará grátis amanhã', extra=''):
    return ('<h1>MSI RTX 5060</h1><p>R$ 2.500,00 no Pix</p>'
            f'<form class="ui-pdp-buybox">{delivery}</form>{extra}')


class OriginParsingTests(unittest.TestCase):
    def test_international_buybox_is_identified_without_losing_prices(self):
        for marker in ('Internacional', 'Envio da China', 'Produto do exterior', 'Impostos de importação'):
            with self.subTest(marker=marker):
                offer = product_offer(page(marker), URL, PART)
                self.assertEqual(offer['shipping_origin'], 'international')
                self.assertEqual(offer['pix'], 250000)

    def test_international_menu_and_recommendations_do_not_hide_domestic_product(self):
        html = '<nav>Internacional</nav>' + page(extra='<h2>Produtos relacionados</h2><p>Internacional</p>')
        self.assertEqual(product_offer(html, URL, PART)['shipping_origin'], 'local')

    def test_shipping_section_outside_buybox_on_real_catalog_layout(self):
        for text, expected in [('Chegará grátis amanhã Retire grátis', 'local'),
                               ('Chegará grátis em 15 dias Envio da China', 'international')]:
            html = page().replace('ui-pdp-buybox', 'xprod-lib-shipping-section').replace('Chegará grátis amanhã', text)
            with self.subTest(text=text):
                self.assertEqual(product_offer(html, URL, PART)['shipping_origin'], expected)

    def test_missing_delivery_stays_unknown_and_other_shops_are_not_filtered(self):
        self.assertEqual(product_offer('<h1>MSI RTX 5060</h1><p>R$ 2.500 no Pix</p>', URL, PART)['shipping_origin'], 'unknown')
        self.assertEqual(product_offer(page('Comprar agora'), URL, PART)['shipping_origin'], 'unknown')
        offer = product_offer(page('Internacional'), 'https://www.pichau.com.br/placa-de-video-msi', PART)
        self.assertEqual(offer['shipping_origin'], 'unknown')
        self.assertEqual(len(group_offers([PART], [dict(offer, id=1, component_id=1)])[1]), 1)

    def test_search_card_exclusion_also_covers_structured_duplicate(self):
        overseas = URL.replace('MLB123', 'MLB124')
        structured = json.dumps({'@type': 'Product', 'name': 'MSI RTX 5060', 'url': overseas})
        html = (f'<li class="ui-search-layout__item"><a href="{overseas}">MSI RTX 5060</a>Internacional</li>'
                f'<li class="ui-search-layout__item"><a href="{URL}">MSI RTX 5060</a>Chegará amanhã</li>'
                f'<script type="application/ld+json">{structured}</script>')
        self.assertEqual(search_links(html, LOCAL, PART), [URL])


class OriginPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'monitor.sqlite3'
        self.store = Store(self.path)
        self.monitor = Monitor(self.store, Path(self.temp.name))

    async def asyncTearDown(self):
        await self.monitor.shops.close()
        self.store.close()
        self.temp.cleanup()

    def save(self, origin, price=250000, url=URL):
        offer = dict(url=url, title='MSI RTX 5060', shop='Mercado Livre', pix=price,
                     coupons=[], status='Preço lido na loja', shipping_origin=origin,
                     published_at=utcnow(), received_at=utcnow())
        return self.store.upsert_offer(1, offer, {'source': 'Mercado Livre', 'published_at': utcnow()})[0]

    async def test_catalog_and_alerts_exclude_imported_and_unknown_without_deleting_records(self):
        imported = self.save('international', 100000)
        unknown = self.save('unknown', 150000, URL.replace('MLB123', 'MLB125'))
        local = self.save('local', 250000, URL.replace('MLB123', 'MLB126'))
        self.assertEqual([row['id'] for row in group_offers(self.store.components(), self.store.offers())[1]], [local['id']])
        self.assertFalse(self.store.should_alert(imported, True))
        self.assertFalse(self.store.should_alert(unknown, True))
        self.assertTrue(self.store.should_alert(local, True))
        self.assertEqual(len(self.store.offers()), 3)
        self.assertEqual(len(self.store.rows('SELECT * FROM observations')), 3)

    async def test_manual_confirmation_can_remove_international_offer_and_restore_local(self):
        row = self.save('local')
        self.monitor.shops.check = AsyncMock(return_value=product_offer(page('Envio da China'), URL, PART))
        with patch('monitor.notify_windows') as notify:
            await self.monitor.check_offer(row['id'])
            self.assertEqual(self.store.offer(row['id'])['shipping_origin'], 'international')
            self.assertEqual(group_offers(self.store.components(), self.store.offers())[1], [])
            notify.assert_not_called()
            self.monitor.shops.check.return_value = product_offer(page(), URL, PART)
            await self.monitor.check_offer(row['id'])
        self.assertEqual(self.store.offer(row['id'])['shipping_origin'], 'local')
        self.assertEqual(len(group_offers(self.store.components(), self.store.offers())[1]), 1)

    async def test_migration_and_restart_keep_history_and_hide_unverified_legacy_offer(self):
        row = self.save('local')
        await self.monitor.shops.close()
        self.store.db.execute('ALTER TABLE offers DROP COLUMN shipping_origin')
        self.store.db.commit()
        self.store.close()
        self.store = Store(self.path)
        self.monitor = Monitor(self.store, Path(self.temp.name))
        self.assertEqual(self.store.offer(row['id'])['shipping_origin'], 'unknown')
        self.assertEqual(len(self.store.rows('SELECT * FROM observations')), 1)
        self.assertEqual(group_offers(self.store.components(), self.store.offers())[1], [])


class DomesticDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.shops = Shops()

    async def asyncTearDown(self):
        await self.shops.close()

    async def test_follows_actual_local_filter_instead_of_unfiltered_search(self):
        self.shops.fetch = AsyncMock(side_effect=[(f'<a href="{LOCAL}">Local</a>', SEARCH),
                                                 (f'<a href="{URL}">MSI RTX 5060</a>', LOCAL)])
        self.assertEqual(await self.shops.discover('Mercado Livre', PART), [URL])
        self.assertEqual(self.shops.fetch.await_args_list[1].args, (LOCAL,))

    async def test_missing_local_filter_discovers_candidates_without_assuming_origin(self):
        overseas = URL.replace('MLB123', 'MLB124')
        html = (f'<li class="ui-search-layout__item"><a href="{URL}">MSI RTX 5060</a></li>'
                f'<li class="ui-search-layout__item"><a href="{overseas}">MSI RTX 5060</a>Internacional</li>')
        self.shops.fetch = AsyncMock(return_value=(html, SEARCH))
        self.assertEqual(await self.shops.discover('Mercado Livre', PART), [URL])
        self.assertEqual(self.shops.fetch.await_count, 1)
        offer = product_offer('<h1>MSI RTX 5060</h1><p>R$ 2.500 no Pix</p>', URL, PART)
        self.assertEqual(group_offers([PART], [dict(offer, id=1, component_id=1)])[1], [])

    async def test_redirect_that_drops_explicit_local_filter_still_fails_closed(self):
        self.shops.fetch = AsyncMock(side_effect=[(f'<a href="{LOCAL}">Local</a>', SEARCH),
                                                 (f'<a href="{URL}">MSI RTX 5060</a>', SEARCH)])
        with self.assertRaisesRegex(ValueError, 'filtro de envio Local'):
            await self.shops.discover('Mercado Livre', PART)

    async def test_local_filter_cannot_redirect_to_arbitrary_host(self):
        self.shops.fetch = AsyncMock(return_value=('<a href="https://example.com/_SHIPPING*ORIGIN_10215068">Local</a>', SEARCH))
        with self.assertRaisesRegex(ValueError, 'filtro de envio Local'):
            await self.shops.discover('Mercado Livre', PART)
        self.assertEqual(self.shops.fetch.await_count, 1)
