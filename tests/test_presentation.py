import unittest
from datetime import datetime, timedelta, timezone

from presentation import coupon_page, filter_offers, group_caption, history_chart_options, history_method, history_window_text, new_dialog_choices, offer_card_data, offer_freshness, shop_state


class PriceHistoryPresentationTests(unittest.TestCase):
    def test_chart_accessible_description_names_piece_payment_dates_and_exact_amounts(self):
        history = {'points': [{'date': '2026-10-02', 'price': 90001}, {'date': '2026-10-01', 'price': 100099}]}
        chart = history_chart_options(history, 'NV3 · Pix sem cupom')
        self.assertEqual(chart['aria']['label']['description'],
                         'NV3 · Pix sem cupom. Menor preço confirmado por dia, sem frete. 01/10/2026: R$ 1.000,99; 02/10/2026: R$ 900,01.')
        self.assertEqual(chart['series'][0]['data'], [1000.99, 900.01])

    def test_chart_description_does_not_invent_a_price_for_a_missing_day(self):
        chart = history_chart_options({'points': [{'date': '2026-10-01', 'price': 10000}, {'date': '2026-10-03', 'price': 9000}]})
        description = chart['aria']['label']['description']
        self.assertNotIn('02/10/2026:', description)
        self.assertIn('sem estimativa', description)
        self.assertIn('Ainda não há leituras', history_chart_options({'points': []})['aria']['label']['description'])

    def test_history_method_distinguishes_coupon_and_original_payments(self):
        self.assertIn('incluindo o cupom', history_method('effective'))
        self.assertIn('pagamentos diferentes', history_method('effective'))
        for payment in ('pix', 'card', 'announced'):
            self.assertIn('sem aplicar cupons', history_method(payment).lower())
        self.assertIn('não o valor de cada parcela', history_method('card'))
        self.assertIn('sem pagamento identificado', history_method('announced'))

    def test_empty_and_short_history_are_explicit(self):
        empty = history_window_text(dict(minimum=None, median=None, days=0))
        self.assertEqual(empty['minimum'], '—')
        self.assertEqual(empty['coverage'], '0 dias observados')
        short = history_window_text(dict(minimum=10000, median=11000, days=2))
        self.assertEqual(short['median'], 'R$ 110,00')
        self.assertIn('histórico curto', short['coverage'])
        self.assertNotIn('curto', history_window_text(dict(minimum=10000, median=11000, days=3))['coverage'])

    def test_chart_does_not_interpolate_unobserved_days(self):
        chart = history_chart_options({'points': [{'date': '2026-10-01', 'price': 10000}, {'date': '2026-10-03', 'price': 9000}]})
        self.assertEqual(chart['xAxis']['data'], ['01/10', '02/10', '03/10'])
        self.assertEqual(chart['series'][0]['data'], [100.0, None, 90.0])
        self.assertFalse(chart['series'][0]['connectNulls'])
        self.assertEqual(history_chart_options({'points': []})['series'][0]['data'], [])


class CardPresentationTests(unittest.TestCase):
    def offer(self, **changes):
        return dict(title='Placa de Video Gigabyte GeForce RTX 5060 Windforce MAX OC, 8GB, GDDR7, 128-bit, GV-N5060WF2MAX-OC-8GD',
                    status='Preço lido na loja', availability='in', **changes)

    def test_short_model_keeps_manufacturer_and_variant(self):
        card = offer_card_data(self.offer())
        self.assertEqual(card['title'], 'Gigabyte RTX 5060 Windforce MAX OC')
        self.assertEqual(card['specs'], '8GB · GDDR7')

    def test_power_supply_short_title_removes_complete_category_prefix(self):
        offer = self.offer()
        offer['title'] = 'Fonte de Alimentação Corsair CX750, 750W, 80 Plus Bronze'
        self.assertEqual(offer_card_data(offer)['title'], 'Corsair CX750')
        offer['title'] = 'Fonte Corsair CX750, 750W'
        self.assertEqual(offer_card_data(offer)['title'], 'Corsair CX750')

    def test_gpu_specs_do_not_include_manufacturer_part_number(self):
        offer = self.offer()
        offer['title'] = 'MSI RTX 5060 Shadow 2X OC, 8GB, GDDR7-912-V537-037'
        self.assertEqual(offer_card_data(offer)['specs'], '8GB · GDDR7')

    def test_non_csv_gpu_title_separates_only_terminal_technical_suffix(self):
        offer = self.offer()
        offer['title'] = 'Gigabyte Placa gráfica RTX 5060 Eagle OC 8G - 8GB GDDR7, 128 bits, PCI-E 5.0'
        card = offer_card_data(offer)
        self.assertEqual(card['title'], 'Gigabyte RTX 5060 Eagle OC')
        self.assertEqual(card['specs'], '8GB · GDDR7')
        offer['title'] = 'MSI RTX 5060 8GB GDDR7 OC White V2'
        self.assertTrue(offer_card_data(offer)['title'].endswith('OC White V2'))

    def test_long_title_keeps_variant_that_would_be_truncated(self):
        offer = self.offer()
        offer['title'] = 'MSI RTX 5060 ' + 'Modelo muito longo ' * 6 + 'OC White V2'
        card = offer_card_data(offer)
        self.assertIn('…', card['title'])
        self.assertTrue(card['title'].endswith('OC / White / V2'))

    def test_nv3_summary_separates_capacity_and_explicit_interface(self):
        offer = self.offer()
        offer['title'] = 'Hd SSD M.2 1TB Nv3 Gen4 6000-4000 Mb/s Snv3s/1000g Kingston'
        card = offer_card_data(offer)
        self.assertEqual(card['title'], 'Kingston NV3')
        self.assertEqual(card['specs'], '1TB · M.2')
        self.assertEqual(offer['title'], 'Hd SSD M.2 1TB Nv3 Gen4 6000-4000 Mb/s Snv3s/1000g Kingston')

    def test_nv3_summary_preserves_mini_and_form_factor_variants(self):
        offer = self.offer()
        offer['title'] = 'SSD M.2 1TB Kingston Nv3 Mini 2230 Nvme PCIe 4.0 Snv3sm3/1t0 6000/4000 Mb/s'
        card = offer_card_data(offer)
        self.assertEqual(card['title'], 'Kingston NV3 Mini 2230')
        self.assertEqual(card['specs'], '1TB · M.2 · NVMe · PCIe 4.0')

    def test_nv3_summary_does_not_infer_capacity_from_sku_or_transfer_rate(self):
        offer = self.offer()
        offer['title'] = 'SSD Kingston NV3 M.2 SNV3S/1000G até 6GB/s'
        self.assertEqual(offer_card_data(offer)['title'], 'Kingston NV3 M.2 SNV3S/1000G até 6GB/s')

    def test_nv3_summary_preserves_bundle_description(self):
        offer = self.offer()
        offer['title'] = 'Kit 2 unidades SSD Kingston NV3 1TB M.2'
        self.assertEqual(offer_card_data(offer)['title'], offer['title'])

    def test_nv3_summary_does_not_turn_accessories_or_multiple_capacities_into_ssd(self):
        offer = self.offer()
        for title in ('RLSOCO Estojo rígido para SSD Kingston NV3 1TB (apenas estojo)',
                      'Kingston NV3 M.2 500GB/1TB/2TB',
                      'Case para SSD Kingston NV3 1TB M.2'):
            with self.subTest(title=title):
                offer['title'] = title
                self.assertEqual(offer_card_data(offer)['title'], title)

    def test_pix_is_primary_and_installment_is_never_total(self):
        card = offer_card_data(self.offer(pix=267999, card=315293, installments=12, installment=26274))
        self.assertEqual(card['amount'], 'R$ 2.679,99')
        self.assertEqual(card['payment'], 'no Pix')
        self.assertEqual(card['secondary'], '12x de R$ 262,74')

    def test_unknown_payment_stays_explicit(self):
        card = offer_card_data(self.offer(announced=267999))
        self.assertEqual(card['payment'], 'pagamento não informado')
        self.assertEqual(card['secondary'], '')

    def test_card_only_uses_total_instead_of_single_installment(self):
        card = offer_card_data(self.offer(card=315293, installments=12, installment=26274))
        self.assertEqual(card['amount'], 'R$ 3.152,93')
        self.assertEqual(card['payment'], 'total no cartão')

    def test_missing_prices_do_not_display_zero(self):
        card = offer_card_data(self.offer())
        self.assertEqual(card['amount'], '—')
        self.assertEqual(card['payment'], 'preço não informado')

    def test_failed_check_is_not_claimed_as_verified(self):
        offer = self.offer(pix=200000)
        offer.update(status='A loja recusou a consulta (403)', checked_at='2026-10-01T20:00:00+00:00')
        self.assertEqual(offer_card_data(offer)['verification'], 'Sem confirmação')

    def test_out_of_stock_remains_visible(self):
        offer = self.offer(pix=200000)
        offer['availability'] = 'out'
        self.assertEqual(offer_card_data(offer)['verification'], 'Indisponível')

    def test_coupon_is_not_claimed_as_validated(self):
        offer = self.offer(pix=200000)
        offer['status'] = 'Preço da loja lido · cupom não validado'
        self.assertEqual(offer_card_data(offer)['verification'], 'Preço conferido')

    def test_marketplace_seller_is_shown_without_inventing_unknown_seller(self):
        card = offer_card_data(self.offer(shop='Amazon', seller='Loja ABC'))
        self.assertEqual(card['seller'], 'Vendido por Loja ABC')
        self.assertEqual(offer_card_data(self.offer(shop='Pichau', seller='PICHAU'))['seller'], '')
        self.assertEqual(offer_card_data(self.offer(shop='KaBuM', seller='KaBuM!'))['seller'], '')
        self.assertEqual(offer_card_data(self.offer(shop='Amazon', seller=None))['seller'], '')

    def test_group_count_only_shows_multiple_saved_announcements(self):
        self.assertEqual(offer_card_data(self.offer(duplicate_ids=[2, 3]))['grouped'], '2 anúncios agrupados')
        self.assertEqual(offer_card_data(self.offer(duplicate_ids=[2]))['grouped'], '')
        self.assertEqual(offer_card_data(self.offer())['grouped'], '')

    def test_failed_check_does_not_make_announced_price_look_freshly_verified(self):
        offer = self.offer(pix=200000)
        offer.update(status='Consulta recusada', checked_at='2026-10-01T20:00:00+00:00',
                     published_at='2026-09-30T18:00:00+00:00')
        self.assertTrue(offer_card_data(offer)['freshness'].startswith('Anúncio de 30/09'))

    def test_verified_price_uses_check_time_and_unknown_time_is_explicit(self):
        offer = self.offer(checked_at='2026-10-01T20:00:00+00:00')
        self.assertTrue(offer_card_data(offer)['freshness'].startswith('Preço lido 01/10'))
        self.assertEqual(offer_card_data(self.offer(checked_at='invalid'))['freshness'], 'Horário não informado')


class OfferBrowsingTests(unittest.TestCase):
    def offers(self):
        return [dict(id=1, title='MSI RTX 5060 White', component='Placa de vídeo', shop='Pichau',
                     pix=200000, status='Preço lido na loja', availability='in'),
                dict(id=2, title='MSI RTX 5060 V2', component='Placa de vídeo', shop='Amazon',
                     announced=210000, status='Anunciado no Telegram', availability='unknown'),
                dict(id=3, title='Gigabyte RTX 5060', component='Placa de vídeo', shop='KaBuM',
                     pix=100000, status='Preço lido na loja', availability='out')]

    def test_default_filters_preserve_all_offers_and_order(self):
        self.assertEqual(filter_offers(self.offers()), self.offers())

    def test_whitespace_only_search_preserves_all_offers(self):
        self.assertEqual(filter_offers(self.offers(), '   '), self.offers())

    def test_shop_and_verification_filters_combine_with_search(self):
        self.assertEqual([offer['id'] for offer in filter_offers(self.offers(), 'white', 'Pichau', 'verified')], [1])
        self.assertEqual(filter_offers(self.offers(), 'white', 'Amazon', 'verified'), [])

    def test_component_selection_combines_with_shop_state_and_query(self):
        rows = [dict(self.offers()[0], component_id=1), dict(self.offers()[1], component_id=1),
                dict(self.offers()[2], component_id=2)]
        self.assertEqual(filter_offers(rows, component_id=1), rows[:2])
        self.assertEqual(filter_offers(rows, 'white', 'Pichau', 'verified', 1), rows[:1])
        self.assertEqual(filter_offers(rows, 'white', 'Pichau', 'verified', 2), [])
        self.assertEqual(filter_offers(rows, component_id=0), rows)

    def test_search_normalizes_accents_and_coupon_text(self):
        self.assertEqual(len(filter_offers(self.offers(), 'video')), 3)
        offer = dict(self.offers()[0], coupons='["PLACA10"]')
        self.assertEqual(filter_offers([offer], 'placa10'), [offer])

    def test_out_of_stock_does_not_pass_verified_filter(self):
        self.assertEqual([offer['id'] for offer in filter_offers(self.offers(), state='verified')], [1])
        self.assertEqual([offer['id'] for offer in filter_offers(self.offers(), state='unavailable')], [3])

    def test_group_minimum_excludes_out_of_stock_and_preserves_payment(self):
        caption = group_caption({'enabled': True}, self.offers())
        self.assertEqual(caption, 'Menor valor listado: R$ 2.000,00 · no Pix')
        caption = group_caption({}, [self.offers()[1]])
        self.assertIn('R$ 2.100,00 · pagamento não informado', caption)

    def test_group_target_and_paused_state_are_independent_of_offer_payment(self):
        caption = group_caption({'target': 190000, 'target_payment': 'card', 'enabled': False}, [])
        self.assertIn('Nenhuma oferta nesta seleção', caption)
        self.assertIn('Limite R$ 1.900,00 no cartão', caption)
        self.assertIn('Monitoramento pausado', caption)

    def test_unknown_and_zero_prices_are_distinct_in_summary(self):
        self.assertEqual(group_caption({}, [dict(self.offers()[1], announced=None)]), 'Sem preço disponível para comparar')
        self.assertIn('R$ 0,00', group_caption({}, [dict(self.offers()[0], pix=0)]))

    def test_source_states_do_not_hide_partial_failure_or_block(self):
        self.assertEqual(shop_state('12 anúncio(s) consultado(s) · algumas consultas falharam'), ('ativa · falhas parciais', 'pending'))
        self.assertEqual(shop_state('A loja recusou a consulta (403)'), ('consulta bloqueada', 'pending'))
        self.assertEqual(shop_state('Mercado Livre: login necessário'), ('login necessário', 'pending'))
        self.assertEqual(shop_state('Login em andamento'), ('login em andamento', 'pending'))
        self.assertEqual(shop_state('Consultando…'), ('consultando', 'announced'))

    def test_session_states_explain_the_required_action(self):
        for status in ('Login pendente · entre na conta, feche o Chrome do monitor e confirme a sessão',
                       'Chrome aberto · entre na conta, feche essa janela e clique Confirmar sessão',
                       'O Chrome do monitor ainda está aberto. Feche suas janelas e clique Confirmar sessão novamente.'):
            with self.subTest(status=status):
                self.assertEqual(shop_state(status), ('fechar Chrome e confirmar', 'pending'))
        self.assertEqual(shop_state('Mercado Livre pediu verificação humana. Abra a sessão na aba Fontes para conferir.'),
                         ('verificação humana', 'pending'))
        self.assertEqual(shop_state('A sessão ainda não retornou anúncios legíveis. Confira o login no Chrome e tente Confirmar sessão novamente.'),
                         ('confirmar sessão', 'pending'))


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc)

    def test_age_crosses_minutes_hours_and_days_without_changing_absolute_time(self):
        for elapsed, suffix in [(0, 'agora'), (60, 'há 1 min'), (3599, 'há 59 min'), (3600, 'há 1 h'),
                                (86400, 'há 1 dia'), (172800, 'há 2 dias')]:
            offer = dict(status='Preço lido na loja', checked_at=(self.now - timedelta(seconds=elapsed)).isoformat())
            self.assertTrue(offer_freshness(offer, self.now).endswith(suffix))
            self.assertTrue(offer_freshness(offer, self.now).startswith('Preço lido '))

    def test_failed_check_uses_announcement_age_instead_of_new_attempt(self):
        offer = dict(status='Consulta recusada', checked_at=self.now.isoformat(),
                     published_at=(self.now - timedelta(hours=3)).isoformat())
        self.assertTrue(offer_freshness(offer, self.now).startswith('Anúncio de '))
        self.assertTrue(offer_freshness(offer, self.now).endswith('há 3 h'))

    def test_missing_invalid_and_future_timestamps_are_explicit(self):
        for value in (None, 'invalid'):
            self.assertEqual(offer_freshness(dict(published_at=value), self.now), 'Horário não informado')
        future = dict(published_at=(self.now + timedelta(hours=1)).isoformat())
        self.assertTrue(offer_freshness(future, self.now).endswith('horário futuro informado'))


class CouponBrowsingTests(unittest.TestCase):
    def test_search_matches_code_source_and_conditions_with_accents(self):
        rows = [dict(codes='GPU10', source='Pichau', conditions='Placas de vídeo'),
                dict(codes='GPU10', source='Outro grupo', conditions='Só para compras no app')]
        for query in ('pichau', 'video'):
            self.assertEqual(coupon_page(rows, query, 1), ([rows[0]], 1, 1))
        self.assertEqual(coupon_page(rows, 'gpu10', 1), (rows, 2, 1))
        self.assertEqual(coupon_page(rows, 'compras', 1), ([rows[1]], 1, 1))

    def test_pagination_preserves_publications_and_clamps_after_search(self):
        rows = [dict(codes=f'CODE{i}', source='Grupo', conditions='') for i in range(23)]
        self.assertEqual(coupon_page(rows, '', 2), (rows[10:20], 23, 2))
        self.assertEqual(coupon_page(rows, '', 9), (rows[20:], 23, 3))
        self.assertEqual(coupon_page(rows, 'CODE22', 3), ([rows[22]], 1, 1))

    def test_empty_results_have_valid_page_without_synthetic_coupon(self):
        self.assertEqual(coupon_page([], '', -1), ([], 0, 1))
        self.assertEqual(coupon_page([dict(codes='GPU10')], 'inexistente', 2), ([], 0, 1))


class GroupSelectionTests(unittest.TestCase):
    def test_registered_group_is_excluded_by_resolved_id_or_private_reference(self):
        sources = [dict(chat_id=-1001, reference='@primeiro'), dict(chat_id=None, reference='-1002')]
        dialogs = [dict(id='-1001', name='Primeiro'), dict(id=-1002, name='Segundo'), dict(id=-1003, name='Novo')]
        self.assertEqual(new_dialog_choices(sources, dialogs), {'-1003': 'Novo'})

    def test_duplicate_names_and_unresolved_public_sources_do_not_hide_other_groups(self):
        sources = [dict(chat_id=None, reference='@publico', enabled=False)]
        dialogs = [dict(id=-1001, name='Mesmo nome'), dict(id=-1002, name='Mesmo nome')]
        self.assertEqual(new_dialog_choices(sources, dialogs), {'-1001': 'Mesmo nome', '-1002': 'Mesmo nome'})

    def test_paused_registered_group_is_still_registered(self):
        self.assertEqual(new_dialog_choices([dict(chat_id=-1001, enabled=False)], [dict(id=-1001, name='Pausado')]), {})


if __name__ == '__main__':
    unittest.main()
