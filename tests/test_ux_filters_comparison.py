import unittest

from core import utcnow
from presentation import catalog_summary, comparison_rows, coupon_catalog, coupon_page, coupon_refresh_notice, coupon_shop_options, filter_sources, offer_card_data, offer_filter_chips, piece_scan_activity, scan_outcome


class CatalogUXTests(unittest.TestCase):
    def test_default_selection_does_not_claim_active_filters(self):
        self.assertEqual(offer_filter_chips(' ', '', ''), [])

    def test_active_filters_are_named_and_individually_removable(self):
        chips = offer_filter_chips('  White  ', 'Pichau', 'verified', 'RTX 5060')
        self.assertEqual(chips, [dict(key='query', label='Busca: White'),
                                 dict(key='component', label='Peça: RTX 5060'),
                                 dict(key='shop', label='Loja: Pichau'),
                                 dict(key='state', label='Preço conferido')])

    def test_each_verification_condition_keeps_its_meaning(self):
        for value, label in [('verified', 'Preço conferido'), ('announced', 'Anúncio do Telegram'),
                             ('pending', 'Sem confirmação'), ('unavailable', 'Indisponível')]:
            with self.subTest(value=value):
                self.assertEqual(offer_filter_chips('', '', value), [dict(key='state', label=label)])

    def test_queries_remain_literal_without_html_or_price_interpretation(self):
        self.assertEqual(offer_filter_chips('<White> R$ 2000', '', '')[0]['label'], 'Busca: <White> R$ 2000')

    def offer(self, **changes):
        stamp = utcnow()
        row = dict(title='MSI RTX 5060 White', shop='Pichau', seller='Pichau',
                   pix=100000, card=120000, installments=12, installment=10000,
                   announced=None, coupons='[]', coupon_price=None, availability='in',
                   status='Preço lido na loja', checked_at=stamp, published_at=stamp,
                   valid_until='2099-01-01T00:00:00+00:00')
        row.update(changes)
        return row

    def test_differences_hide_equal_conditions_without_changing_values(self):
        first = self.offer()
        second = dict(first, pix=90000, seller='Outra loja')
        differences = comparison_rows([first, second], True)
        self.assertEqual([row['field'] for row in differences], ['Vendedor', 'Pix'])
        self.assertEqual(differences[-1]['offer0'], 'R$ 1.000,00')
        self.assertEqual(differences[-1]['offer1'], 'R$ 900,00')
        self.assertEqual(len(comparison_rows([first, second])), 12)

    def test_unknown_is_not_equal_to_known_and_coupon_condition_remains_explicit(self):
        first = self.offer()
        second = dict(first, pix=None, coupon_price=85000)
        differences = {row['field']: row for row in comparison_rows([first, second], True)}
        self.assertEqual(differences['Pix']['offer1'], 'Não informado')
        self.assertEqual(differences['Preço com cupom']['offer0'], 'Não confirmado')
        self.assertIn('disponível na sessão', differences['Preço com cupom']['offer1'])
        self.assertNotIn('Frete', differences)

    def test_third_offer_participates_in_difference_detection(self):
        first = self.offer()
        rows = comparison_rows([first, first, dict(first, card=130000)], True)
        self.assertEqual([row['field'] for row in rows], ['Total no cartão'])
        self.assertEqual(rows[0]['offer2'], 'R$ 1.300,00')

    def test_equal_unknown_values_do_not_invent_differences(self):
        first = self.offer(pix=None, card=None, seller=None)
        self.assertEqual(comparison_rows([first, first], True), [])

    def test_source_search_handles_accents_names_and_ids_and_keeps_original_rows(self):
        sources = [dict(id=1, name='Promoções do Guiga', reference='-1001592709849', enabled=1),
                   dict(id=2, name='Ofertas Adrenaline', reference='@ofertasadrenaline', enabled=0)]
        self.assertEqual(filter_sources(sources, '  promocoes  '), [sources[0]])
        self.assertEqual(filter_sources(sources, '1592709849'), [sources[0]])
        self.assertEqual(filter_sources(sources, '@ofertasadrenaline'), [sources[1]])
        self.assertEqual(filter_sources(sources, ''), sources)
        self.assertEqual(filter_sources(sources, 'inexistente'), [])
        self.assertEqual(sources[1]['enabled'], 0)

    def test_discount_used_to_sort_is_visible_without_relabeling_the_base_payment(self):
        card = offer_card_data(self.offer(shop='Mercado Livre', pix=None, announced=100000, coupon_price=90000))
        self.assertTrue(card['coupon_primary'])
        self.assertEqual(card['display_amount'], 'R$ 900,00')
        self.assertEqual(card['display_payment'], 'com cupom na sua sessão')
        self.assertEqual(card['amount'], 'R$ 1.000,00')
        self.assertEqual(card['payment'], 'pagamento não informado')

    def test_cheaper_pix_stays_prominent_and_equal_coupon_does_not_claim_discount(self):
        for coupon in (100000, 110000, 0, -1, None):
            with self.subTest(coupon=coupon):
                card = offer_card_data(self.offer(coupon_price=coupon))
                self.assertFalse(card['coupon_primary'])
                self.assertEqual(card['display_amount'], 'R$ 1.000,00')
                self.assertEqual(card['display_payment'], 'no Pix')

    def test_expired_or_unavailable_coupon_does_not_become_the_main_price(self):
        for changes in [dict(valid_until='2000-01-01T00:00:00+00:00'), dict(availability='out')]:
            with self.subTest(changes=changes):
                card = offer_card_data(self.offer(coupon_price=90000, **changes))
                self.assertFalse(card['coupon_primary'])
                self.assertEqual(card['display_amount'], 'R$ 1.000,00')
                self.assertEqual(card['coupon_amount'], 'R$ 900,00')

    def test_no_base_price_is_invented_when_only_session_coupon_is_known(self):
        card = offer_card_data(self.offer(pix=None, card=None, announced=None, coupon_price=90000))
        self.assertEqual(card['amount'], '—')
        self.assertEqual(card['display_amount'], 'R$ 900,00')
        self.assertEqual(card['display_payment'], 'com cupom na sua sessão')

    def test_piece_scan_distinguishes_own_query_global_query_and_other_piece(self):
        part = dict(id=8, name='Water Cooler', enabled=True)
        other = dict(id=3, name='Kingston NV3 1 TB', enabled=True)
        statuses = {'Pichau': '5 anúncio(s) consultado(s)', 'Mercado Livre': 'Consultando…'}
        self.assertEqual(piece_scan_activity(part, part, statuses, True), 'Atualizando esta peça · Mercado Livre.')
        self.assertEqual(piece_scan_activity(part, None, statuses, True), 'Consulta geral em andamento · Mercado Livre.')
        self.assertEqual(piece_scan_activity(part, other, statuses, True), 'Aguarde a consulta de Kingston NV3 1 TB · Mercado Livre.')
        self.assertEqual(piece_scan_activity(part, None, {}, True), 'Consulta geral em andamento.')

    def test_paused_or_idle_piece_explains_why_refresh_is_unavailable_or_what_it_does(self):
        part = dict(id=8, name='Water Cooler', enabled=True)
        self.assertIn('só desta peça', piece_scan_activity(part, None, {}, False))
        self.assertIn('Ative esta peça na aba Peças', piece_scan_activity(dict(part, enabled=False), part, {}, True))

    def test_scan_outcome_does_not_present_partial_failure_as_success(self):
        statuses = {'Pichau': '2 anúncio(s) consultado(s) · algumas consultas falharam',
                    'Mercado Livre': '3 anúncio(s) consultado(s)', 'Amazon': 'Consulta pausada',
                    'Shopee': 'Verificação humana pendente'}
        result = scan_outcome(statuses)
        self.assertEqual(result['tone'], 'pending')
        self.assertEqual(result['summary'], '1 loja com leitura · 2 lojas com pendências · 1 loja sem consulta')

    def test_empty_paused_and_running_outcomes_do_not_invent_completed_readings(self):
        self.assertEqual(scan_outcome({}), dict(summary='Nenhuma loja consultada', tone='neutral'))
        self.assertEqual(scan_outcome({'Pichau': 'Consultando…'})['summary'], '1 loja em andamento')
        self.assertEqual(scan_outcome({'Pichau': 'Consulta pausada'})['summary'], '1 loja sem consulta')
        self.assertEqual(scan_outcome({'Pichau': '1 anúncio(s) consultado(s)'})['tone'], 'verified')

    def test_selection_is_named_without_claiming_it_is_a_filter(self):
        self.assertEqual(catalog_summary(60, 60, False, ''), '60 ofertas nas peças acompanhadas')
        self.assertEqual(catalog_summary(0, 0, False, 'favorite'), '0 ofertas favoritas')
        self.assertEqual(catalog_summary(2, 2, False, 'hidden'), '2 ofertas ocultas')
        self.assertEqual(catalog_summary(3, 0, True, 'favorite'), '0 de 3 ofertas favoritas · filtros ativos')
        self.assertEqual(catalog_summary(60, 12, True, ''), '12 de 60 ofertas · filtros ativos')

    def test_open_coupon_reading_defers_new_publications_without_mutating_rows(self):
        old = [dict(key='a', conditions='Produtos selecionados')]
        latest = [dict(key='b', conditions='Outra publicação'), *old]
        self.assertEqual(coupon_refresh_notice(old, latest, old, {'a'}),
                         '1 nova publicação disponível · sua leitura foi preservada.')
        self.assertEqual(old, [dict(key='a', conditions='Produtos selecionados')])
        self.assertEqual(len(latest), 2)

    def test_closed_filtered_out_or_off_page_coupon_does_not_hold_refresh(self):
        old = [dict(key='a'), dict(key='b')]
        latest = [dict(key='c'), *old]
        for visible, expanded in [(old, set()), ([old[1]], {'a'}), ([], {'a'})]:
            with self.subTest(visible=visible, expanded=expanded):
                self.assertEqual(coupon_refresh_notice(old, latest, visible, expanded), '')

    def test_unchanged_coupon_reading_has_no_update_notice(self):
        rows = [dict(key='a', conditions='Produtos selecionados')]
        self.assertEqual(coupon_refresh_notice(rows, list(rows), rows, {'a'}), '')

    def test_coupon_changes_or_removals_do_not_claim_new_publications(self):
        old = [dict(key='a', conditions='Texto anterior'), dict(key='b')]
        latest = [dict(key='a', conditions='Texto atualizado')]
        self.assertEqual(coupon_refresh_notice(old, latest, old, {'a'}),
                         'Atualização da lista disponível · sua leitura foi preservada.')

    def test_coupon_update_notice_counts_new_keys_not_codes(self):
        old = [dict(key='a', codes='GPU10')]
        latest = [dict(key='b', codes='GPU10'), dict(key='c', codes='GPU10'), *old]
        self.assertTrue(coupon_refresh_notice(old, latest, old, {'a'}).startswith('2 novas publicações'))

    def test_coupon_counts_publications_instead_of_unique_codes(self):
        rows = [dict(shop='Pichau', codes='GPU10'), dict(shop='Pichau', codes='GPU10')]
        options = coupon_shop_options(rows)
        self.assertEqual(options[''], 'Todas as lojas (2)')
        self.assertEqual(options['Pichau'], 'Pichau (2)')
        self.assertEqual(options['Amazon'], 'Amazon (0)')
        self.assertEqual(len(rows), 2)

    def test_official_coupon_reading_keeps_identity_after_reorder_or_text_change(self):
        a = dict(code='GPU10', conditions='Produtos selecionados', url='https://www.pichau.com.br/promocao/cupons/GPU10')
        b = dict(a, code='GPU20', url='https://www.pichau.com.br/promocao/cupons/GPU20')
        before = coupon_catalog([], [a, b], [])
        after = coupon_catalog([], [b, dict(a, conditions='Novas condições')], [])
        self.assertEqual(before[0]['key'], after[1]['key'])
        self.assertNotEqual(before[0]['key'], after[0]['key'])
        self.assertEqual(after[1]['conditions'], 'Novas condições')

    def test_public_coupon_insertion_does_not_move_open_conditions_to_another_code(self):
        a = dict(code='GPU10', conditions='Produtos selecionados', url='https://www.amazon.com.br/',
                 source_url='https://example.com/amazon', source='Site', shop='Amazon', activation=False, checked_at=utcnow())
        b = dict(a, code='GPU20')
        before = coupon_catalog([], [], [a])
        after = coupon_catalog([], [], [b, dict(a, checked_at=utcnow())])
        self.assertEqual(before[0]['key'], after[1]['key'])
        self.assertNotEqual(before[0]['key'], after[0]['key'])
        self.assertTrue(coupon_refresh_notice(before, after, before, {before[0]['key']}).startswith('1 nova publicação'))

    def test_no_code_activations_keep_distinct_origins_and_unchanged_links(self):
        a = dict(code='', conditions='Ative no link', url='https://www.amazon.com.br/',
                 source_url='https://example.com/primeiro', source='Site', shop='Amazon', activation=True, checked_at=utcnow())
        b = dict(a, source_url='https://example.com/segundo')
        rows = coupon_catalog([], [], [a, b])
        self.assertNotEqual(rows[0]['key'], rows[1]['key'])
        self.assertEqual([row['url'] for row in rows], [a['url'], b['url']])
        self.assertTrue(all(row['activation'] and row['codes'] == '' for row in rows))

    def test_multi_shop_counts_follow_the_same_membership_as_filter(self):
        rows = [dict(shop='Mercado Livre · Amazon'), dict(shop='Loja não identificada'),
                dict(shop='Outra Amazon falsa')]
        options = coupon_shop_options(rows)
        for shop in ('Mercado Livre', 'Amazon', 'Loja não identificada'):
            self.assertEqual(options[shop], f'{shop} ({coupon_page(rows, "", 1, shop)[1]})')
        self.assertEqual(options['Amazon'], 'Amazon (1)')

    def test_empty_coupon_counts_do_not_claim_a_discount_exists(self):
        options = coupon_shop_options([])
        self.assertEqual(options[''], 'Todas as lojas (0)')
        self.assertTrue(all(label.endswith('(0)') for label in options.values()))

    def test_coupon_dates_distinguish_publication_from_reading_without_inventing_expiry(self):
        stamp = utcnow()
        post = dict(source='Grupo', message_id=1, text='Cupom GPU10 Pichau', codes='["GPU10"]',
                    links='[]', published_at=stamp)
        official = dict(code='GPU10', conditions='Produtos selecionados', checked_at=stamp,
                        url='https://www.pichau.com.br/promocao/cupons')
        public = dict(code='AMAZON10', conditions='Produtos selecionados', checked_at=stamp, shop='Amazon',
                      source='Fonte pública', url='https://www.amazon.com.br/', source_url='https://example.com/', activation=False)
        rows = coupon_catalog([post], [official], [public])
        self.assertEqual([row['timestamp_kind'] for row in rows], ['published', 'checked', 'checked'])
        self.assertTrue(all(row['stamp'] == stamp for row in rows))
        self.assertTrue(all('expires_at' not in row for row in rows))
        self.assertEqual([row['codes'] for row in rows], ['GPU10', 'GPU10', 'AMAZON10'])


if __name__ == '__main__':
    unittest.main()
