import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock

from cloud.app import get_coupons
from core import Store, utcnow
from ml_coupon_applicator import CouponApplicator
from presentation import coupon_catalog
from shops import pelando_coupons, public_coupons


class PelandoTests(unittest.TestCase):
    now = datetime(2026, 10, 8, 16, tzinfo=timezone.utc)

    def card(self, code='SITE50', title='Cupom Mercado Livre - R$50 OFF em Todo Site',
             description='', age='há 2 hs', status='active', shop='Mercado Livre'):
        # Classes e atributos observados no HTML público do Pelando.
        return f'''<article class="card" data-deal-id="test">
        <p class="card__author">Postado por @teste {age}</p>
        <h2 class="card__title">{title}</h2><p class="card__description">{description}</p>
        <button data-copy-code="{code}">Copiar</button>
        <a class="card__cta" data-store-name="{shop}" data-status="{status}" href="https://dpl.pelando.com.br/r/test">Pegar cupom</a>
        <a class="card__pill" href="https://www.pelando.com.br/d/cupom-test">Comentários</a>
        </article>'''

    def test_keeps_explicit_codes_and_restrictions_with_origin_and_publication(self):
        rows = pelando_coupons(self.card() + self.card(code='GPU10', title='10% OFF em informática selecionada'), self.now)
        self.assertEqual([r['code'] for r in rows], ['SITE50', 'GPU10'])
        self.assertEqual(rows[0]['source'], 'Pelando')
        self.assertEqual(rows[0]['source_url'], 'https://www.pelando.com.br/d/cupom-test')
        self.assertEqual(rows[0]['found_at'], '2026-10-08T14:00:00+00:00')
        self.assertIn('Todo Site', rows[0]['conditions'])
        self.assertFalse(rows[0]['activation'])

    def test_ignores_generic_selected_unrelated_expired_and_link_only(self):
        cases = [dict(title='30% OFF em Selecionados', description='Em itens selecionados'),
                 dict(title='15% OFF em Bebês e Pets'), dict(status='expired'),
                 dict(shop='Amazon'), dict(code=''), dict(code='BAD CODE'),
                 dict(description='Em produtos selecionados'),
                 dict(description='Somente para a primeira compra')]
        for case in cases:
            with self.subTest(case=case):
                self.assertEqual(pelando_coupons(self.card(**case), self.now), [])

    def test_only_today_and_no_unknown_or_renewed_dates(self):
        for age in ['há ontem', 'há 2 dias', 'Verificado hoje', 'há 23 hs']:
            with self.subTest(age=age):
                self.assertEqual(pelando_coupons(self.card(age=age), self.now), [])
        after_midnight = self.now.replace(hour=4)
        self.assertEqual(pelando_coupons(self.card(age='há 2 hs'), after_midnight), [])
        self.assertEqual(len(pelando_coupons(self.card(age='há 5 mins'), self.now)), 1)

    def test_duplicate_codes_are_single_candidates_and_blocked_page_is_failure(self):
        self.assertEqual(len(pelando_coupons(self.card() * 2, self.now)), 1)
        with self.assertRaisesRegex(ValueError, 'Pelando'):
            pelando_coupons('<h1>Cloudflare Access denied</h1>', self.now)

    def test_melhores_cartoes_no_longer_imports_mercado_livre(self):
        html = '''<table><tr><td>LOJA</td><td>REGRA</td><td>CUPOM</td><td>LINK</td></tr>
        <tr><td>Mercado Livre</td><td>Todo site</td><td>ANTIGO10</td><td><a href="https://www.mercadolivre.com.br/ofertas">abrir</a></td></tr>
        <tr><td>Amazon</td><td>Eletrônicos</td><td>AMAZON10</td><td><a href="https://www.amazon.com.br/promotion/test">abrir</a></td></tr></table>'''
        self.assertEqual([(r['code'], r['shop']) for r in public_coupons(html)], [('AMAZON10', 'Amazon')])


class LegacyCouponTests(unittest.IsolatedAsyncioTestCase):
    def cached(self, code='ANTIGO10', source='Melhores Cartões', shop='Mercado Livre'):
        return dict(code=code, source=source, shop=shop, conditions='Selecionados', checked_at=utcnow(),
                    found_at=utcnow(), source_url='https://www.pelando.com.br/d/cupom-test',
                    url='https://www.mercadolivre.com.br/cupons', activation=False)

    async def test_old_cache_and_retry_history_do_not_repopulate_local_queue(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / 'monitor.sqlite3')
            try:
                old = self.cached()
                other = self.cached('AMAZON10', shop='Amazon')
                store.set_setting('public_coupons', json.dumps([old, other]))
                self.assertEqual([r['codes'] for r in coupon_catalog([], [], [old, other])], ['AMAZON10'])
                applicator = CouponApplicator(store, MagicMock(), asyncio.Lock())
                applicator.record('ANTIGO10', 'Melhores Cartões', 'pending', 'Tivemos um problema')
                self.assertEqual(applicator.catalog(), [])
                self.assertEqual(applicator.candidates(), [])
                self.assertEqual([r['code'] for r in json.loads(store.get_setting('public_coupons'))], ['AMAZON10'])
            finally:
                store.close()

    async def test_same_code_from_pelando_preserves_prior_success_without_resubmission(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / 'monitor.sqlite3')
            try:
                applicator = CouponApplicator(store, MagicMock(), asyncio.Lock())
                applicator.record('SITE50', 'Melhores Cartões', 'inserted', 'Cupom adicionado')
                store.set_setting('public_coupons', json.dumps([self.cached('SITE50', 'Pelando')]))
                self.assertEqual(applicator.catalog()[0]['status'], 'inserted')
                self.assertEqual(applicator.catalog()[0]['source'], 'Pelando')
                self.assertEqual(applicator.candidates(), [])
            finally:
                store.close()

    async def test_cloud_hides_old_cache_and_orphan_attempts_but_preserves_shared_success(self):
        repo = MagicMock()
        legacy = dict(code='ANTIGO10', source='Melhores Cartões', status='pending', detail='Tivemos um problema', found_at=utcnow())
        success = dict(legacy, code='SITE50', status='inserted', detail='Cupom adicionado')
        records = {'coupons': [], 'settings': [{'record_key': 'public_coupons', 'data': {'value': json.dumps([
            self.cached(), self.cached('SITE50', 'Pelando')])}}],
            'coupon_applications': [{'record_key': r['code'], 'data': r} for r in [legacy, success]]}
        repo.records = AsyncMock(side_effect=lambda kind: records.get(kind, []))
        result = await get_coupons(repo)
        self.assertEqual([r['code'] for r in result['coupons']], ['SITE50'])
        self.assertEqual(result['applications'][0]['source'], 'Pelando')
        self.assertEqual([(r['code'], r['status']) for r in result['applications']], [('SITE50', 'inserted')])
