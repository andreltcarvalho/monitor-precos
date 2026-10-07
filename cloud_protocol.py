"""Contrato de dados públicos do monitor; nunca inclui arquivos de sessão."""
import hashlib
from core import alert_price, canonical_url, effective_price, price_is_current, top_offers

CLOUD_SHOPS = ('Pichau', 'KaBuM', 'Amazon', 'Terabyte Shop')
LOCAL_SHOPS = ('Mercado Livre', 'Shopee')
SYNC_KINDS = {'components', 'offers', 'observations', 'sources', 'settings', 'coupons',
              'coupon_applications', 'olx_searches', 'olx_listings', 'olx_observations', 'status'}
PUBLIC_SETTINGS = {'pichau_coupons', 'public_coupons', 'ml_coupon_last_run'} | {
    'shop:' + name for name in CLOUD_SHOPS + LOCAL_SHOPS}


def offer_key(component_id, url):
    return hashlib.sha256((str(component_id) + ':' + canonical_url(url)).encode()).hexdigest()


def catalog(components, offers, preferences=None):
    preferences = preferences or {}
    parts = {part['id']: part for part in components if part.get('enabled', 1)}
    eligible = []
    for raw in offers:
        part = parts.get(raw['component_id'])
        if not part:
            continue
        row = dict(raw, **preferences.get(str(raw['id']), {}))
        row.update(component=part['name'], target=part.get('target'), target_payment=part.get('target_payment', 'pix'))
        if not price_is_current(row):
            continue
        value = alert_price(row, part.get('target_payment', 'pix'))
        if part.get('target') is not None and (value is None or value > part['target']):
            continue
        eligible.append(row)
    grouped = top_offers(list(parts.values()), eligible)
    return [dict(part, offers=[dict(row, effective=effective_price(row)) for row in grouped[part['id']]])
            for part in parts.values()]
