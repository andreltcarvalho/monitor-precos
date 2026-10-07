"""Validação dos campos do painel, sem alterar as regras dos coletores."""
import re

from core import money


def component_draft(name, kind, query, capacity, target, payment, ignored_brands) -> tuple:
    """Campos efetivos do rascunho, para proteger edições ainda não salvas."""
    return (name or '', kind, query or '', capacity if kind == 'ssd' else None,
            target or '', payment if (target or '').strip() else None,
            tuple(sorted(ignored_brands or [])))


def component_input_errors(name, kind, query, capacity, target, payment) -> dict[str, str]:
    errors = {}
    if not (name or '').strip():
        errors['name'] = 'Dê um nome para identificar esta peça.'
    if kind not in {'custom', 'gpu', 'psu', 'ssd'}:
        errors['kind'] = 'Escolha a identificação da peça.'
    if not (query or '').strip():
        errors['query'] = 'Informe o modelo a buscar nas lojas.'
    if kind == 'ssd':
        try:
            value = float(capacity)
            if value < 1 or not value.is_integer():
                errors['capacity'] = 'Informe a capacidade em GB, maior que zero e sem fração.'
        except (ValueError, TypeError, OverflowError):
            errors['capacity'] = 'Informe a capacidade em GB. Para 1 TB, use 1000.'
    text = (target or '').strip()
    if text:
        if not re.fullmatch(r'(?:R\$\s*)?(?:\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:[,.]\d{1,2})?)', text):
            errors['target'] = 'Use um valor como 2.000,00, sem sinal negativo.'
        elif money(text) <= 0:
            errors['target'] = 'O preço máximo deve ser maior que zero; deixe vazio para qualquer oferta.'
    if payment not in {'pix', 'card'}:
        errors['payment'] = 'Escolha Pix ou o total no cartão.'
    return errors
