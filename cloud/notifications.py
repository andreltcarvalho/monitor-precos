"""Alertas por limite próprio; preços e critérios são os mesmos do monitor."""
import hashlib
import json
import re
from datetime import datetime

import httpx
from fastapi import HTTPException

from core import brl, confirmed_price, effective_price, offer_group_key, offer_matches, price_is_current, reading_valid_until, valid_url


def candidates(parts, offers, receipts=(), settings=None):
    settings = settings or {}
    notified = {}
    for row in receipts:
        if row.get('identity') and type(row.get('price')) is int:
            notified[row['identity']] = min(row['price'], notified.get(row['identity'], row['price']))
    selected = {}
    by_id = {p['id']: p for p in parts if p.get('enabled') and type(p.get('notification_target')) is int and p['notification_target'] > 0}
    for offer in offers:
        part = by_id.get(offer.get('component_id'))
        if (not part or offer.get('hidden') or offer.get('availability') == 'out'
                or settings.get('shop:' + str(offer.get('shop')), '1') != '1'
                or not offer_matches(part, offer) or not price_is_current(offer)
                or not offer.get('url') or not valid_url(offer['url'])):
            continue
        # Só o cupom lido na loja pode reduzir o preço usado para avisar.
        priced = offer if confirmed_price(offer.get('status') or '') else dict(offer, coupon_price=None)
        price = effective_price(priced)
        if type(price) is not int or not 0 < price < part['notification_target']:
            continue
        identity = hashlib.sha256(json.dumps([part['id'], offer_group_key(offer)], ensure_ascii=False).encode()).hexdigest()
        if notified.get(identity, float('inf')) <= price:
            continue
        deadline = offer.get('valid_until') or reading_valid_until(offer)
        if not deadline:  # Persistência sempre precisa de uma leitura datada.
            continue
        text = (f"{part['name'][:120]} abaixo do seu limite\n{offer.get('title', '')[:220]}\n"
                f"{brl(price)} · {offer.get('shop', '')[:60]}\nLimite: {brl(part['notification_target'])}")
        if priced.get('coupon_price') == price:
            text += '\nCom cupom da sua sessão; confira as condições na loja.'
        if not confirmed_price(offer.get('status') or ''):
            text += '\nPreço anunciado; ainda não conferido na loja.'
        text += '\nFrete não incluído.\n' + offer['url'][:1500]
        row = dict(identity=identity, offer_id=str(offer['id']), component_key=str(part['id']),
                   price=price, threshold=part['notification_target'], checked_at=offer.get('checked_at'),
                   valid_until=deadline, text=text, component=part, reading=offer)
        if identity not in selected or price < selected[identity]['price']:
            selected[identity] = row
    return sorted(selected.values(), key=lambda row: (row['price'], row['identity']))[:100]


async def bot_call(client, token, method, payload=None):
    if not isinstance(token, str) or not re.fullmatch(r'\d{5,15}:[A-Za-z0-9_-]{20,100}', token):
        raise HTTPException(422, 'Token do bot inválido. Copie o token fornecido pelo BotFather.')
    try:
        response = await client.post('https://api.telegram.org/bot' + token + '/' + method, json=payload or {})
        body = response.json()
    except (httpx.HTTPError, ValueError):
        # Nunca propagar exceções HTTP: elas incluem o token na URL.
        raise HTTPException(502, 'Telegram não respondeu. Tente novamente em alguns minutos.') from None
    if not isinstance(body, dict) or not body.get('ok'):
        code = body.get('error_code') if isinstance(body, dict) else None
        detail = {401: 'Token recusado pelo Telegram. Configure novamente.',
                  403: 'Abra o bot e toque em Iniciar; confira se ele está bloqueado.',
                  409: 'Este bot está sendo usado por outra integração. Use um bot exclusivo para o monitor.',
                  429: 'Telegram pediu uma pausa. Tente novamente em alguns minutos.'}.get(code, 'Telegram recusou a operação. Tente novamente.')
        raise HTTPException(502, detail)
    return body['result']


def recipient(updates, nonce, since):
    for update in reversed(updates):
        message = update.get('message') or {}
        chat = message.get('chat') or {}
        if (chat.get('type') == 'private' and chat.get('id') == (message.get('from') or {}).get('id')
                and message.get('text') == '/start ' + nonce
                and message.get('date', 0) >= datetime.fromisoformat(since).timestamp()):
            return str(chat['id'])
    return None
