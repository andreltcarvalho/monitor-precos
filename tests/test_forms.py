import unittest

from forms import component_draft, component_input_errors


class ComponentFormTests(unittest.TestCase):
    def errors(self, **changes):
        values = dict(name='Minha placa', kind='gpu', query='rtx 5060', capacity=1000, target='', payment='pix')
        values.update(changes)
        return component_input_errors(**values)

    def test_valid_piece_without_limit_has_no_errors(self):
        self.assertEqual(self.errors(), {})

    def test_empty_name_and_query_identify_the_correct_fields(self):
        self.assertEqual(set(self.errors(name='  ', query=None)), {'name', 'query'})

    def test_brazilian_and_decimal_price_inputs_are_accepted(self):
        for price in ['2.000,00', '2000', '2000,50', '2000.50', 'R$ 2.000,00']:
            with self.subTest(price=price):
                self.assertEqual(self.errors(target=price), {})

    def test_negative_or_mixed_text_price_cannot_be_saved_as_positive(self):
        for price in ['-2000', 'R$ -2.000,00', 'abc2000', '100 reais', '2,000,00']:
            with self.subTest(price=price):
                self.assertEqual(set(self.errors(target=price)), {'target'})

    def test_zero_limit_explains_blank_for_any_offer(self):
        self.assertIn('deixe vazio', self.errors(target='0,00')['target'])

    def test_capacity_is_required_only_for_ssd(self):
        self.assertEqual(self.errors(capacity=None), {})
        self.assertEqual(set(self.errors(kind='ssd', capacity=None)), {'capacity'})

    def test_ssd_capacity_cannot_silently_default_or_truncate(self):
        for capacity in [0, -1000, 1000.5, 'abc', float('inf'), float('nan')]:
            with self.subTest(capacity=capacity):
                self.assertEqual(set(self.errors(kind='ssd', capacity=capacity)), {'capacity'})

    def test_integer_ssd_capacity_and_card_limit_are_valid(self):
        self.assertEqual(self.errors(kind='ssd', capacity=1000.0, target='450,00', payment='card'), {})

    def test_unknown_identification_and_payment_are_rejected(self):
        self.assertEqual(set(self.errors(kind=None, payment=None)), {'kind', 'payment'})

    def test_draft_detects_changes_to_each_saved_condition(self):
        values = dict(name='Minha placa', kind='gpu', query='rtx 5060', capacity=1000,
                      target='2000', payment='pix', ignored_brands=['MSI'])
        baseline = component_draft(**values)
        for key, value in [('name', 'Outra placa'), ('kind', 'custom'), ('query', 'rtx 5060 ti'),
                           ('target', '-2000'), ('payment', 'card'), ('ignored_brands', ['Palit'])]:
            with self.subTest(key=key):
                self.assertNotEqual(component_draft(**dict(values, **{key: value})), baseline)
        self.assertEqual(component_draft(**values), baseline)

    def test_unused_capacity_and_payment_do_not_claim_unsaved_changes(self):
        values = dict(name='Minha placa', kind='gpu', query='rtx 5060', capacity=1000,
                      target='', payment='pix', ignored_brands=[])
        self.assertEqual(component_draft(**values), component_draft(**dict(values, capacity=2000, payment='card')))
        values['kind'] = 'ssd'
        self.assertNotEqual(component_draft(**values), component_draft(**dict(values, capacity=2000)))

    def test_reordered_brand_selection_is_the_same_draft(self):
        args = ('Minha placa', 'gpu', 'rtx 5060', 1000, '', 'pix')
        self.assertEqual(component_draft(*args, ['MSI', 'Palit']), component_draft(*args, ['Palit', 'MSI']))
        self.assertNotEqual(component_draft(*args, ['MSI']), component_draft(*args, []))


if __name__ == '__main__':
    unittest.main()
