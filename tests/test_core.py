from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from core import Store, brl, canonical_url, coupons, group_offers, links, matches, money, prices, recent, utcnow
from shops import product_offer, search_links


class GroupingTests(unittest.TestCase):
    def test_each_group_orders_by_pix_before_pagination(self):
        offers = [dict(id=1, component_id=1, pix=280000, card=320000),
                  dict(id=2, component_id=2, pix=50000),
                  dict(id=3, component_id=1, pix=250000, card=350000),
                  dict(id=4, component_id=2, pix=40000)]
        groups = group_offers([{'id': 1}, {'id': 2}], offers)
        self.assertEqual([row['id'] for row in groups[1]], [3, 1])
        self.assertEqual([row['id'] for row in groups[2]], [4, 2])

    def test_missing_pix_uses_displayed_card_total_or_announced_price(self):
        offers = [dict(id=1, component_id=1, card=300000, installment=25000),
                  dict(id=2, component_id=1, announced=260000),
                  dict(id=3, component_id=1, pix=280000, announced=200000)]
        groups = group_offers([{'id': 1}], offers)
        self.assertEqual([row['id'] for row in groups[1]], [2, 3, 1])

    def test_unknown_prices_last_and_equal_prices_keep_order(self):
        offers = [dict(id=1, component_id=1), dict(id=2, component_id=1, pix=100),
                  dict(id=3, component_id=1, pix=0), dict(id=4, component_id=1, pix=100)]
        groups = group_offers([{'id': 1}], offers)
        self.assertEqual([row['id'] for row in groups[1]], [3, 2, 4, 1])
        self.assertEqual([row['id'] for row in offers], [1, 2, 3, 4])

    def test_manufacturers_share_component_but_other_parts_stay_separate(self):
        parts = [{'id': 1, 'name': 'RTX 5060'}, {'id': 2, 'name': 'CX750'}, {'id': 3, 'name': 'NV3'}]
        offers = [{'id': 10, 'component_id': 1, 'title': 'MSI RTX 5060'},
                  {'id': 11, 'component_id': 2, 'title': 'Corsair CX750'},
                  {'id': 12, 'component_id': 1, 'title': 'Zotac RTX 5060'}]
        groups = group_offers(parts, offers)
        self.assertEqual([row['id'] for row in groups[1]], [10, 12])
        self.assertEqual([row['id'] for row in groups[2]], [11])
        self.assertEqual(groups[3], [])

    def test_filter_results_keep_groups_and_do_not_merge_equal_names(self):
        parts = [{'id': 1, 'name': 'Minha peça'}, {'id': 2, 'name': 'Minha peça'}]
        filtered = [{'id': 12, 'component_id': 2}]
        groups = group_offers(parts, filtered)
        self.assertEqual(groups[1], [])
        self.assertEqual([row['id'] for row in groups[2]], [12])
        self.assertEqual(group_offers([], filtered), {})

    def test_pichau_nac_duplicate_collapses_without_deleting_source_rows(self):
        offers = [dict(id=1, component_id=1, shop='Pichau', seller='Pichau', title='MSI RTX 5060 White, G5060-8V2CW-NAC', pix=280000),
                  dict(id=2, component_id=1, shop='Pichau', seller='Pichau', title='MSI RTX 5060 White, G5060-8V2CW', pix=270000)]
        rows = group_offers([{'id': 1}], offers)[1]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], 2)
        self.assertEqual(set(rows[0]['duplicate_ids']), {1, 2})
        self.assertEqual(len(offers), 2)
        self.assertNotIn('duplicate_ids', offers[0])

    def test_variants_stores_and_sellers_remain_separate(self):
        base = dict(component_id=1, shop='Pichau', seller='Pichau', pix=260000)
        offers = [dict(base, id=1, title='INNO3D RTX 5060 Twin X2 OC White, 195070W'),
                  dict(base, id=2, title='INNO3D RTX 5060 Twin X2 OC V2, 195071N'),
                  dict(base, id=3, title='INNO3D RTX 5060 Twin X2 OC White, 195070W', shop='Amazon'),
                  dict(base, id=4, title='INNO3D RTX 5060 Twin X2 OC White, 195070W', seller='Outro')]
        self.assertEqual(len(group_offers([{'id': 1}], offers)[1]), 4)

    def test_duplicate_out_of_stock_does_not_hide_available_offer(self):
        base = dict(component_id=1, shop='Pichau', title='RTX 5060 MSI', seller='Pichau')
        offers = [dict(base, id=1, pix=200000, availability='out'), dict(base, id=2, pix=250000, availability='in')]
        rows = group_offers([{'id': 1}], offers)[1]
        self.assertEqual([row['id'] for row in rows], [2])

    def test_unconfirmed_generic_telegram_titles_are_not_merged(self):
        offers = [dict(id=1, component_id=1, shop='Amazon', title='RTX 5060', announced=260000),
                  dict(id=2, component_id=1, shop='Amazon', title='RTX 5060', announced=270000)]
        self.assertEqual(len(group_offers([{'id': 1}], offers)[1]), 2)


class ParsingTests(unittest.TestCase):
    def test_amazon_tracking_urls_share_asin_but_keep_seller_and_variant(self):
        first = canonical_url('https://www.amazon.com.br/MSI/dp/B0ABCDEFG1/ref=sr_1_1?qid=123&tag=canal&smid=LOJA')
        second = canonical_url('https://amazon.com.br/gp/product/B0ABCDEFG1?qid=456&smid=LOJA')
        self.assertEqual(first, second)
        self.assertNotEqual(first, canonical_url('https://www.amazon.com.br/dp/B0ABCDEFG1?smid=OUTRA'))
        self.assertNotEqual(first, canonical_url('https://www.amazon.com.br/dp/B0ABCDEFG2?smid=LOJA'))

    def test_currency_brazilian_and_store_html(self):
        for value, expected in [('2.629,99', 262999), ('2,629.99', 262999), ('1,159.99', 115999),
                                ('R$ 399,99', 39999), ('R$ 470.58', 47058), ('3.529', 352900), ('100',10000)]:
            with self.subTest(value=value):
                self.assertEqual(money(value), expected)
        self.assertEqual(brl(262999), 'R$ 2.629,99')

    def test_gpu_accepts_different_manufacturers(self):
        component = {'kind': 'gpu'}
        self.assertTrue(matches(component, 'Gigabyte RTX 5060 OC 8 GB'))
        self.assertTrue(matches(component, 'MSI RTX5060 8GB'))
        for title in ['RTX 5060 Ti', 'RTX5060TI 16GB', 'RTX 50600', 'PC Gamer RTX 5060', 'Notebook RTX 5060']:
            self.assertFalse(matches(component, title), title)

    def test_source_component_is_exact_model(self):
        self.assertTrue(matches({'kind':'psu'}, 'Fonte Corsair CX 750 750W'))
        self.assertFalse(matches({'kind':'psu'}, 'Fonte Corsair CX750M'))
        self.assertFalse(matches({'kind':'psu'}, 'Fonte Corsair CX750 F'))
        self.assertFalse(matches({'kind':'psu'}, 'Fonte Corsair RM750'))

    def test_ssd_capacity(self):
        component = {'kind': 'ssd', 'capacity_gb': 1000}
        for title in ['Kingston NV3 1TB', 'SSD NV3 Kingston 1000 GB']:
            self.assertTrue(matches(component, title))
        for title in ['Kingston NV3 2TB', 'Kingston NV2 1TB', 'Kingston NV3 500GB']:
            self.assertFalse(matches(component, title))

    def test_custom_component_requires_every_search_term(self):
        part = {'kind':'custom','query':'ryzen 7 5700x'}
        self.assertTrue(matches(part, 'Processador Ryzen 7 5700X AMD'))
        self.assertFalse(matches(part, 'Ryzen 7 5700X3D'))

    def test_fan_category_aliases_preserve_model_color_and_accessory_filters(self):
        part = {'kind': 'custom', 'query': 'ventoinha nordwind black'}
        for title in ['Cooler Para Gabinete Round5 Nordwind Black, ARGB, 120mm, PWM, Preto',
                      'Fan Round5 Nordwind Black 120mm', 'Ventoinhas Round5 Nordwind Black',
                      'Cooler para Gabinete Round5 Nordwind Reverse Black']:
            self.assertTrue(matches(part, title), title)
        for title in ['Cooler para Gabinete Round5 Nordwind White', 'Fan Round5 Outro Black',
                      'Cooler para CPU Nordwind Black', 'Suporte para Fan Nordwind Black',
                      'Kit Fan com 3 Unidades Round5 Nordwind Black']:
            self.assertFalse(matches(part, title), title)
        self.assertTrue(matches(dict(part, query='fan nordwind black'), 'Ventoinha Nordwind Black'))

    def test_water_cooler_size_with_mm_matches_without_relaxing_other_terms(self):
        part = {'kind': 'custom', 'query': 'water cooler rise mode 360 argb'}
        for title in ('Water Cooler Rise Mode Black ARGB 360mm Intel AMD',
                      'Water Cooler Rise Mode ARGB 360 mm Preto'):
            self.assertTrue(matches(part, title), title)
        for title in ('Water Cooler Rise Mode ARGB 240mm', 'Water Cooler Rise Mode RGB 360mm',
                      'Water Cooler Gamdias ARGB 360mm', 'Water Cooler Rise Mode ARGB 1360mm'):
            self.assertFalse(matches(part, title), title)
        self.assertTrue(matches(dict(part, query='water cooler rise mode 360mm argb'),
                                'Water Cooler Rise Mode ARGB 360 mm'))

    def test_installment_not_pix_or_announced_price(self):
        parsed = prices('RTX 5060\n10x de R$ 299,90 sem juros')
        self.assertEqual(parsed['card'], 299900)
        self.assertIsNone(parsed['pix'])
        self.assertIsNone(parsed['announced'])

    def test_telegram_payment_unknown_remains_unknown(self):
        parsed = prices('Fonte Corsair CX750 por R$399,99\nCompre aqui: https://www.pichau.com.br/fonte-cx750')
        self.assertEqual(parsed['announced'], 39999)
        self.assertIsNone(parsed['pix'])

    def test_pix_and_card_are_separate(self):
        parsed = prices('RTX 5060 por R$ 2.629,99 no PIX\nR$ 3.105,87 no cartão\n12x de R$ 258,83')
        self.assertEqual(parsed['pix'], 262999)
        self.assertEqual(parsed['installments'], 12)
        self.assertIsNotNone(parsed['card'])

    def test_two_payment_prices_on_same_line(self):
        parsed=prices('RTX 5060: R$2.500,00 no Pix ou R$2.800,00 no cartão')
        self.assertEqual(parsed['pix'],250000)
        self.assertEqual(parsed['card'],280000)

    def test_explicit_card_total_preserved_over_rounded_installments(self):
        parsed=prices('R$3.105,87 no cartão\n12x de R$258,83')
        self.assertEqual(parsed['card'],310587)

    def test_coupon_codes_and_links(self):
        self.assertEqual(coupons('Com cupom `SITE0110` + `DESCONTOSMELI`'), ['SITE0110','DESCONTOSMELI'])
        self.assertEqual(links('[Compre](https://meli.la/abc)\nTelegram https://t.me/ofertasadrenaline'), ['https://meli.la/abc'])
        self.assertEqual(links('https://user:secret@www.pichau.com.br/foo'), [])

    def test_freshness_window(self):
        now = datetime.now(timezone.utc)
        self.assertTrue(recent((now-timedelta(seconds=299)).isoformat(), now))
        self.assertFalse(recent((now-timedelta(seconds=301)).isoformat(), now))
        self.assertFalse(recent((now+timedelta(minutes=2)).isoformat(), now))

    def test_real_store_decimal_format_regression(self):
        html = '''<h1>Placa de Video RTX 5060 8GB</h1><span>de R$ 3,411.75 por:</span>
        <span>à vista</span><strong>R$ 2,639.99</strong><span>no PIX com 15% desconto</span>
        <strong>R$ 3,105.87</strong><span>em até 12x de R$ 258.83 sem juros no cartão</span>
        <h2>Características</h2><p>Outro produto R$ 99,00</p>'''
        result = product_offer(html, 'https://www.pichau.com.br/placa-de-video-rtx-5060', {'kind':'gpu'})
        self.assertEqual(result['pix'], 263999)
        self.assertEqual(result['card'], 310587)

    def test_structured_price_is_not_automatically_pix(self):
        html = '''<h1>Fonte Corsair CX750</h1><script type="application/ld+json">
        {"@type":"Product","name":"Fonte Corsair CX750","offers":{"price":399.99,"availability":"https://schema.org/InStock"}}</script>'''
        result = product_offer(html,'https://www.pichau.com.br/fonte-cx750', {'kind':'psu'})
        self.assertEqual(result['announced'],39999)
        self.assertIsNone(result['pix'])
        self.assertEqual(result['availability'],'in')

    def test_product_confirmation_rejects_wrong_component(self):
        with self.assertRaises(ValueError):
            product_offer('<h1>RTX 5060 Ti</h1><p>R$ 3.999,00 no Pix</p>',
                          'https://www.pichau.com.br/placa-de-video-5060-ti', {'kind':'gpu'})

    def test_search_filters_complete_pc_and_ti(self):
        html = '''<a href="/placa-de-video-rtx-5060">MSI RTX 5060</a>
        <a href="/placa-de-video-rtx-5060-ti">RTX 5060 Ti</a>
        <a href="/pc-gamer-rtx-5060">PC Gamer RTX 5060</a>'''
        self.assertEqual(search_links(html,'https://www.pichau.com.br/search',{'kind':'gpu'}),
                         ['https://www.pichau.com.br/placa-de-video-rtx-5060'])


class StoreTests(unittest.TestCase):
    def test_amazon_search_tracking_does_not_create_new_record(self):
        first, _ = self.save(self.offer(shop='Amazon', url='https://www.amazon.com.br/MSI/dp/B0ABCDEFG1/ref=sr_1?qid=123'))
        second, changed = self.save(self.offer(shop='Amazon', url='https://www.amazon.com.br/dp/B0ABCDEFG1?qid=456'), message_id=2)
        self.assertEqual(first['id'], second['id'])
        self.assertFalse(changed)
        self.assertEqual(len(self.store.offers()), 1)

    def test_existing_amazon_urls_normalize_on_reopen_without_losing_history(self):
        first, _ = self.save(self.offer(shop='Amazon', url='https://www.amazon.com.br/dp/B0ABCDEFG1'))
        second, _ = self.save(self.offer(shop='Amazon', url='https://www.amazon.com.br/dp/B0ABCDEFG2'), message_id=2)
        self.store.db.execute('UPDATE offers SET url=? WHERE id=?', ('https://www.amazon.com.br/MSI/dp/B0ABCDEFG1/ref=sr_1?qid=123', first['id']))
        self.store.db.execute('UPDATE offers SET url=? WHERE id=?', ('https://www.amazon.com.br/MSI/dp/B0ABCDEFG1/ref=sr_2?qid=456', second['id']))
        self.store.db.commit()
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(len(self.store.offers()), 1)
        self.assertEqual(self.store.offers()[0]['url'], 'https://www.amazon.com.br/dp/B0ABCDEFG1')
        self.assertEqual(len(self.store.rows('SELECT * FROM observations')), 2)
        self.assertEqual(len(self.store.rows('SELECT * FROM origins')), 2)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'test.sqlite3'
        self.store = Store(self.path)
        self.part = self.store.components()[0]

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def offer(self, **changes):
        value = dict(url='https://www.pichau.com.br/placa-de-video-rtx-5060?utm_source=test',
                     title='RTX 5060',shop='Pichau',pix=250000,card=280000,announced=None,
                     coupons=[],status='Anunciado no Telegram',published_at=utcnow(),received_at=utcnow())
        value.update(changes)
        return value

    def save(self, offer=None, source='Grupo A', message_id=1):
        return self.store.upsert_offer(self.part['id'],offer or self.offer(),
                                       dict(source=source,chat_id=-1001,message_id=message_id,published_at=utcnow()))

    def ranked_offer(self, amount, number, **changes):
        value = self.offer()
        value.update(url=f'https://www.pichau.com.br/oferta-{number}', title=f'RTX 5060 modelo {number}',
                     pix=amount, seller='Pichau')
        value.update(changes)
        return self.save(value, message_id=number)[0]

    def test_top_ten_percent_rounds_up_and_includes_the_candidate(self):
        rows = [self.ranked_offer(100000 + index * 1000, index) for index in range(10)]
        self.assertTrue(self.store.should_alert(rows[0], True))
        self.assertFalse(self.store.should_alert(rows[1], True))
        self.ranked_offer(200000, 10)
        self.assertTrue(self.store.should_alert(rows[1], True))
        self.assertFalse(self.store.should_alert(rows[2], True))
        for index in range(11, 21):
            self.ranked_offer(200000 + index, index)
        self.assertTrue(self.store.should_alert(rows[2], True))

    def test_small_sample_allows_only_the_cheapest_and_equal_prices(self):
        first = self.ranked_offer(100000, 1)
        expensive = self.ranked_offer(120000, 2)
        tied = self.ranked_offer(100000, 3)
        self.assertTrue(self.store.should_alert(first, True))
        self.assertTrue(self.store.should_alert(tied, True))
        self.assertFalse(self.store.should_alert(expensive, True))

    def test_unavailable_and_unpriced_offers_do_not_inflate_the_sample(self):
        self.ranked_offer(100000, 1)
        candidate = self.ranked_offer(110000, 2)
        for index in range(3, 30):
            self.ranked_offer(None if index % 2 else 90000, index,
                              card=None, announced=None, availability='unknown' if index % 2 else 'out')
        self.assertFalse(self.store.should_alert(candidate, True))

    def test_grouped_duplicates_do_not_inflate_the_cheapest_band(self):
        for index in range(8):
            self.ranked_offer(100000 + index * 1000, index)
        for index in range(8, 30):
            self.ranked_offer(300000, index, title='RTX 5060 mesmo modelo caro')
        candidate = self.ranked_offer(100500, 30)
        self.assertFalse(self.store.should_alert(candidate, True))

    def test_ranking_uses_selected_payment_without_mixing_pix_and_card(self):
        self.ranked_offer(100000, 1, card=300000)
        candidate = self.ranked_offer(200000, 2, card=250000)
        self.assertFalse(self.store.should_alert(candidate, True))
        self.store.save_component('RTX 5060', 'gpu', 'rtx 5060', None, 400000, 'card', self.part['id'])
        self.assertTrue(self.store.should_alert(self.store.offer(candidate['id']), True))

    def test_another_component_does_not_change_the_price_band(self):
        candidate = self.ranked_offer(200000, 1)
        self.store.upsert_offer(self.store.components()[1]['id'], self.offer(pix=10000),
                               dict(source='Pichau', published_at=utcnow()))
        self.assertTrue(self.store.should_alert(candidate, True))

    def test_missing_or_zero_price_never_alerts_without_a_limit(self):
        for number, amount in enumerate((None, 0)):
            candidate = self.ranked_offer(amount, number, card=None, announced=None)
            self.assertFalse(self.store.should_alert(candidate, True))

    def test_unknown_payment_is_compared_only_with_announced_prices(self):
        self.ranked_offer(100000, 1, card=None, announced=None)
        candidate = self.ranked_offer(None, 2, card=None, announced=200000)
        self.assertTrue(self.store.should_alert(candidate, True))
        self.ranked_offer(None, 3, card=None, announced=150000)
        self.assertFalse(self.store.should_alert(candidate, True))

    def test_same_offer_in_two_groups_is_one_record(self):
        first, changed = self.save()
        self.assertTrue(changed)
        second, changed = self.save(source='Grupo B',message_id=2)
        self.assertFalse(changed)
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(len(self.store.offers()),1)
        self.assertEqual(len(self.store.rows('SELECT * FROM origins')),2)

    def test_alert_dedup_persists_across_restart(self):
        row, _ = self.save()
        self.assertTrue(self.store.should_alert(row,True))
        self.store.mark_alert(row)
        self.store.close()
        self.store = Store(self.path)
        self.assertFalse(self.store.should_alert(self.store.offer(row['id']),True))

    def test_optional_limit_uses_selected_payment(self):
        self.store.save_component('RTX 5060','gpu','rtx 5060',None,260000,'pix',self.part['id'])
        row, _ = self.save()
        self.assertTrue(self.store.should_alert(row,True))
        self.store.save_component('RTX 5060','gpu','rtx 5060',None,260000,'card',self.part['id'])
        self.assertFalse(self.store.should_alert(self.store.offer(row['id']),True))

    def test_unknown_payment_does_not_trigger_capped_alert(self):
        self.store.save_component('RTX 5060','gpu','rtx 5060',None,260000,'pix',self.part['id'])
        row, _ = self.save(self.offer(pix=None,card=None,announced=200000))
        self.assertFalse(self.store.should_alert(row,True))

    def test_stale_disabled_or_out_of_stock_does_not_alert(self):
        row, _ = self.save()
        self.assertFalse(self.store.should_alert(row,False))
        self.store.toggle('components',self.part['id'],False)
        self.assertFalse(self.store.should_alert(self.store.offer(row['id']),True))
        row['availability']='out'
        self.assertFalse(self.store.should_alert(row,True))

    def test_changed_coupon_without_price_drop_does_not_alert(self):
        row, _ = self.save()
        self.store.mark_alert(row)
        next_row, changed = self.save(self.offer(coupons=['GPU10']),message_id=2)
        self.assertTrue(changed)
        self.assertFalse(self.store.should_alert(next_row,True))

    def test_component_delete_removes_only_its_history(self):
        self.save()
        self.store.delete('components',self.part['id'])
        self.assertEqual(len(self.store.components()),2)
        self.assertEqual(self.store.offers(),[])
        self.assertEqual(self.store.rows('SELECT * FROM observations'),[])

    def test_source_markdown_reference(self):
        self.store.save_source('Outro','[Canal](https://t.me/outrafonte)')
        self.assertEqual(self.store.sources()[-1]['reference'],'@outrafonte')

    def test_known_short_link_is_reused_after_resolution(self):
        row,_=self.save(self.offer(url='https://meli.la/abc'))
        resolved='https://www.mercadolivre.com.br/anuncio/p/MLB123'
        self.store.resolve_offer_url(row['id'],resolved)
        next_row,_=self.save(self.offer(url='https://meli.la/abc'),message_id=2)
        self.assertEqual(row['id'],next_row['id'])
        self.assertEqual(len(self.store.offers()),1)

    def test_direct_store_rechecks_do_not_duplicate_origins(self):
        for _ in range(3):
            self.store.upsert_offer(self.part['id'],self.offer(),dict(source='Pichau',published_at=utcnow()))
        self.assertEqual(len(self.store.rows('SELECT * FROM origins')),1)

    def test_messages_out_of_order_are_tracked_individually(self):
        self.store.checkpoint(1,20)
        self.assertFalse(self.store.message_processed(1,19))
        self.store.checkpoint(1,19)
        self.assertTrue(self.store.message_processed(1,19))
        self.assertEqual(self.store.sources()[0]['last_message'],20)

    def test_message_deletion_preserves_other_origin(self):
        row,_ = self.save()
        self.save(source='Grupo B',message_id=2)
        self.store.remove_message(-1001,[1])
        self.assertNotEqual(self.store.offer(row['id'])['status'],'Publicação removida')
        self.store.remove_message(-1001,[2])
        self.assertEqual(self.store.offer(row['id'])['status'],'Publicação removida')


if __name__=='__main__':
    unittest.main()
