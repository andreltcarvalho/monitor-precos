"""Resumo visual das ofertas; dados completos permanecem no detalhe."""
import re
import json
from datetime import datetime, timedelta, timezone

from core import alert_price, brl, catalog_price, group_offers, links, normalized, price_is_current, top_offers
from shops import COUPON_SHOPS, coupon_shop


def history_method(payment: str) -> str:
    return {'pix': 'Somente preços no Pix informados pela loja, sem aplicar cupons.',
            'card': 'Valor total no cartão, não o valor de cada parcela. Sem aplicar cupons.',
            'announced': 'Preço anunciado sem pagamento identificado, sem aplicar cupons.',
            'effective': 'Menor preço entre as condições disponíveis, incluindo o cupom exibido na sessão. Compara pagamentos diferentes.'}[payment]


def history_chart_options(history: dict, context: str = 'Histórico de preços') -> dict:
    points = {point['date']: point['price'] / 100 for point in history['points']}
    dates = []
    if points:
        first, last = datetime.fromisoformat(min(points)), datetime.fromisoformat(max(points))
        dates = [(first + timedelta(days=index)).date().isoformat() for index in range((last-first).days+1)]
    readings = '; '.join(datetime.fromisoformat(day).strftime('%d/%m/%Y') + ': ' + brl(round(points[day] * 100)) for day in sorted(points))
    description = context + '. Menor preço confirmado por dia, sem frete. ' + (readings + '.' if readings else 'Ainda não há leituras neste pagamento.')
    if len(dates) > len(points):
        description += ' Dias sem leitura ficam em branco, sem estimativa de preço.'
    return dict(animation=False, aria={'enabled': True, 'label': {'description': description}},
        grid={'left': 98, 'right': 24, 'top': 20, 'bottom': 36},
        tooltip={'trigger': 'axis', ':valueFormatter': 'value => "R$ " + value.toLocaleString("pt-BR", {minimumFractionDigits: 2, maximumFractionDigits: 2})'},
        xAxis={'type': 'category', 'data': [datetime.fromisoformat(day).strftime('%d/%m') for day in dates], 'axisLabel': {'color': '#49576b'}},
        yAxis={'type': 'value', 'scale': True, 'axisLabel': {'color': '#49576b', ':formatter': 'value => value.toLocaleString("pt-BR", {style: "currency", currency: "BRL"})'}, 'splitLine': {'lineStyle': {'color': '#d8dee8'}}},
        series=[{'name': 'Menor preço do dia', 'type': 'line', 'data': [points.get(day) for day in dates],
                 'connectNulls': False, 'showSymbol': True, 'symbolSize': 7,
                 'itemStyle': {'color': '#175cd3'}, 'lineStyle': {'width': 2}}])


def history_window_text(window: dict) -> dict:
    days = window['days']
    return dict(minimum=brl(window['minimum']) if days else '—',
                median=brl(window['median']) if days else '—',
                coverage=f"{days} {'dia observado' if days == 1 else 'dias observados'}" +
                         (' · histórico curto' if 0 < days < 3 else ''))


def new_dialog_choices(sources: list[dict], dialogs: list[dict]) -> dict[str, str]:
    existing = {str(value) for source in sources for value in (source.get('chat_id'), source.get('reference')) if value}
    return {str(dialog['id']): dialog['name'] for dialog in dialogs if str(dialog['id']) not in existing}


def filter_sources(sources: list[dict], query: str) -> list[dict]:
    needle = normalized(query).strip()
    return [source for source in sources if not needle or needle in normalized(source['name'] + ' ' + source['reference'])]


def catalog_summary(total: int, shown: int, filtered: bool, selection: str) -> str:
    noun = {'favorite': 'ofertas favoritas', 'hidden': 'ofertas ocultas'}.get(selection, 'ofertas')
    if filtered:
        return f'{shown} de {total} {noun} · filtros ativos'
    return f'{total} {noun}' + (' nas peças acompanhadas' if not selection else '')


def coupon_catalog(posts: list[dict], official: list[dict], public: list[dict], now: datetime | None = None) -> list[dict]:
    rows = []
    for post in posts:
        urls = list(dict.fromkeys(links(post['text']) + json.loads(post.get('links') or '[]')))
        rows.append(dict(key=f"{post['source']}:{post['message_id']}", codes=', '.join(json.loads(post['codes'])),
                         shop=coupon_shop(post['text'], urls), source=post['source'], conditions=post['text'],
                         stamp=post['published_at'], found_at=post.get('found_at') or post['published_at'], timestamp_kind='published', url=urls[0] if urls else '', source_url=post.get('message_url') or '', activation=False))
    for item in official:
        rows.append(dict(key='pichau:' + json.dumps([item['url'], item['code']]), codes=item['code'], shop='Pichau', source='Pichau oficial',
                         conditions=item['conditions'], stamp=item.get('checked_at'), found_at=item.get('found_at') or item.get('checked_at'), timestamp_kind='checked', url=item['url'],
                         source_url='https://www.pichau.com.br/promocao/cupons', activation=False))
    for item in public:
        if item.get('source') == 'Melhores Cartões' and item.get('shop') == 'Mercado Livre':
            continue
        try:
            stamp = datetime.fromisoformat(item['checked_at'])
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            age = ((now or datetime.now(timezone.utc)) - stamp).total_seconds()
            if not 0 <= age <= 43200:
                continue
        except (ValueError, TypeError, KeyError):
            continue
        rows.append(dict(key='public:' + json.dumps([item['source'], item['source_url'], item['url'], item['code'], item['activation']]), codes=item['code'], shop=item['shop'], source=item['source'],
                         conditions=item['conditions'], stamp=item['checked_at'], found_at=item.get('found_at') or item['checked_at'], timestamp_kind='checked', url=item['url'],
                         source_url=item['source_url'], activation=item['activation']))
    return rows


def coupon_refresh_notice(displayed: list[dict], latest: list[dict], visible: list[dict], expanded: set[str]) -> str:
    """Adia a troca da lista somente quando interromperia uma leitura aberta."""
    if displayed == latest or not expanded.intersection(row['key'] for row in visible):
        return ''
    known = {row['key'] for row in displayed}
    added = sum(row['key'] not in known for row in latest)
    text = (f'{added} nova publicação disponível' if added == 1 else f'{added} novas publicações disponíveis') if added else 'Atualização da lista disponível'
    return text + ' · sua leitura foi preservada.'


def coupon_shop_options(rows: list[dict]) -> dict[str, str]:
    shops = (*COUPON_SHOPS, 'Loja não identificada')
    options = {'': f'Todas as lojas ({len(rows)})'}
    for shop in shops:
        count = sum(shop in (row.get('shop') or '').split(' · ') for row in rows)
        options[shop] = f'{shop} ({count})'
    return options


def coupon_page(rows: list[dict], query: str, page: int, shop: str = '') -> tuple[list[dict], int, int]:
    needle = normalized(query).strip()
    matches = [row for row in rows if (not shop or shop in (row.get('shop') or '').split(' · '))
               and (not needle or needle in normalized(' '.join(
        str(row.get(key) or '') for key in ('codes', 'shop', 'source', 'conditions'))))]
    page = min(max(1, page), max(1, (len(matches) + 9) // 10))
    return matches[(page - 1) * 10:page * 10], len(matches), page


def filter_offers(offers: list[dict], query: str = '', shop: str = '', state: str = '', component_id: int = 0) -> list[dict]:
    needle = normalized(query).strip()
    return [offer for offer in offers
            if (not shop or offer.get('shop') == shop)
            and (not component_id or offer.get('component_id') == component_id)
            and (not state or offer_card_data(offer)['tone'] == state)
            and (not needle or needle in normalized(' '.join(str(offer.get(key) or '')
                 for key in ('component', 'title', 'shop', 'coupons'))))]


def offer_selection(components: list[dict], offers: list[dict], selection: str) -> dict[int, list[dict]]:
    if selection == 'hidden':
        return {key: rows[:12] for key, rows in group_offers(
            components, [row for row in offers if row.get('hidden')], include_hidden=True).items()}
    if selection == 'favorite':
        return {key: [row for row in rows if row.get('favorite')][:12]
                for key, rows in group_offers(components, offers).items()}
    parts = {part['id']: part for part in components}
    within_limit = []
    for offer in offers:
        part = parts.get(offer['component_id'])
        if part is None:
            continue
        target = part.get('target')
        value = alert_price(offer, part.get('target_payment', 'pix'))
        if target is None or value is not None and value <= target:
            within_limit.append(offer)
    return top_offers(components, within_limit)


def toggle_comparison(selected: list[dict], offer: dict) -> list[dict]:
    ids = set(offer.get('duplicate_ids') or [offer['id']])
    if any(ids.intersection(row.get('duplicate_ids') or [row['id']]) for row in selected):
        return [row for row in selected if not ids.intersection(row.get('duplicate_ids') or [row['id']])]
    if offer.get('hidden'):
        raise ValueError('Restaure a oferta antes de comparar.')
    if selected and selected[0]['component_id'] != offer['component_id']:
        raise ValueError('Compare ofertas da mesma peça. Limpe a comparação para escolher outra peça.')
    if len(selected) >= 3:
        raise ValueError('A comparação aceita até três ofertas. Remova uma para adicionar outra.')
    return selected + [offer]


def comparison_rows(offers: list[dict], differences_only=False) -> list[dict]:
    fields = [('Modelo', lambda row: row['title']), ('Loja', lambda row: row['shop']),
              ('Vendedor', lambda row: row.get('seller') or 'Não informado'),
              ('Pix', lambda row: brl(row.get('pix'))), ('Total no cartão', lambda row: brl(row.get('card'))),
              ('Preço anunciado', lambda row: brl(row.get('announced'))),
              ('Parcelamento', lambda row: f"{row['installments']}x de {brl(row['installment'])}"
               if row.get('installments') and row.get('installment') is not None else 'Não informado'),
              ('Preço com cupom', lambda row: brl(row.get('coupon_price')) +
               (' · disponível na sessão' if price_is_current(row) else ' · desatualizado')
               if row.get('coupon_price') else 'Não confirmado'),
              ('Códigos publicados', lambda row: ', '.join(json.loads(row.get('coupons') or '[]')) + ' · não validados'
               if json.loads(row.get('coupons') or '[]') else 'Nenhum informado'),
              ('Frete', lambda row: 'Não consultado'),
              ('Conferência', lambda row: offer_card_data(row)['verification']),
              ('Leitura / anúncio', offer_freshness)]
    rows = [dict(field=label, **{f'offer{index}': getter(offer) for index, offer in enumerate(offers)})
            for label, getter in fields]
    return [row for row in rows if not differences_only or len({row[f'offer{index}'] for index in range(len(offers))}) > 1]


def offer_filter_chips(query: str, shop: str, state: str, component_name: str = '') -> list[dict]:
    labels = {'verified': 'Preço conferido', 'announced': 'Anúncio do Telegram',
              'pending': 'Sem confirmação', 'unavailable': 'Indisponível'}
    return [dict(key=key, label=prefix + value) for key, prefix, value in
            [('query', 'Busca: ', query.strip()), ('component', 'Peça: ', component_name),
             ('shop', 'Loja: ', shop), ('state', '', labels.get(state, state))] if value]


def group_caption(component: dict, offers: list[dict]) -> str:
    available = [offer for offer in offers if price_is_current(offer) and offer.get('availability') != 'out'
                 and any(offer.get(key) is not None for key in ('pix', 'card', 'announced', 'coupon_price'))]
    if available:
        cheapest = min(available, key=catalog_price)
        card = offer_card_data(cheapest)
        coupon_is_lowest = card['coupon_amount'] and catalog_price(cheapest) == cheapest['coupon_price']
        text = ('Menor valor listado: ' + (card['coupon_amount'] if coupon_is_lowest else card['amount'])
                + ' · ' + ('com cupom na sua sessão' if coupon_is_lowest else card['payment']))
    elif offers:
        text = 'Sem preço disponível para comparar'
    else:
        text = 'Nenhuma oferta nesta seleção'
    if component.get('target') is not None:
        text += ' · Limite ' + brl(component['target']) + (' no Pix' if component['target_payment'] == 'pix' else ' no cartão')
    if not component.get('enabled', True):
        text += ' · Monitoramento pausado'
    return text


def shop_state(status: str) -> tuple[str, str]:
    text = normalized(status)
    if 'feche' in text and 'chrome' in text:
        return 'fechar Chrome e confirmar', 'pending'
    if 'verificacao humana' in text:
        return 'verificação humana', 'pending'
    if 'sessao ainda nao retornou anuncios' in text:
        return 'confirmar sessão', 'pending'
    if 'login' in text or 'sessao nao configurada' in text:
        return ('login em andamento' if 'andamento' in text else 'login necessário'), 'pending'
    if 'consultando' in text:
        return 'consultando', 'announced'
    if 'pausada' in text:
        return 'pausada', 'neutral'
    if 'anuncio(s) consultado(s)' in text:
        return ('ativa · falhas parciais', 'pending') if 'falharam' in text else ('ativa', 'verified')
    if text.startswith('aguardando') or 'aguardando consulta' in text:
        return 'aguardando', 'neutral'
    if 'recusou' in text or 'bloqueou' in text:
        return 'consulta bloqueada', 'pending'
    return 'consulta indisponível', 'pending'


def piece_scan_activity(component: dict, active_component: dict | None, statuses: dict, scanning: bool) -> str:
    if not component['enabled']:
        return 'Monitoramento pausado. Ative esta peça na aba Peças para consultar.'
    if not scanning:
        return 'Buscar novas ofertas nas lojas ativas só desta peça.'
    shop = next((name for name, status in statuses.items() if normalized(status).startswith('consultando')), '')
    if active_component is None:
        text = 'Consulta geral em andamento'
    elif active_component['id'] == component['id']:
        text = 'Atualizando esta peça'
    else:
        text = 'Aguarde a consulta de ' + active_component['name']
    return text + (' · ' + shop if shop else '') + '.'


def scan_outcome(statuses: dict) -> dict:
    tones = [shop_state(status)[1] for status in statuses.values()]
    counts = [(tones.count('verified'), 'com leitura'), (tones.count('pending'), 'com pendências'),
              (tones.count('neutral'), 'sem consulta'), (tones.count('announced'), 'em andamento')]
    summary = ' · '.join(f'{count} {"loja" if count == 1 else "lojas"} {label}' for count, label in counts if count)
    return dict(summary=summary or 'Nenhuma loja consultada',
                tone='pending' if 'pending' in tones else 'verified' if 'verified' in tones else 'neutral')


def offer_freshness(offer: dict, now: datetime | None = None) -> str:
    verified = offer.get('availability') != 'out' and offer.get('status', '').startswith(('Preço lido na loja', 'Preço da loja lido'))
    timestamp = offer.get('checked_at') if verified else offer.get('published_at')
    try:
        moment = datetime.fromisoformat(timestamp).astimezone()
    except (ValueError, TypeError):
        return 'Horário não informado'
    elapsed = ((now or datetime.now().astimezone()) - moment).total_seconds()
    if elapsed < -60:
        age = 'horário futuro informado'
    elif elapsed < 60:
        age = 'agora'
    elif elapsed < 3600:
        age = f'há {int(elapsed // 60)} min'
    elif elapsed < 86400:
        age = f'há {int(elapsed // 3600)} h'
    else:
        days = int(elapsed // 86400)
        age = f'há {days} {"dia" if days == 1 else "dias"}'
    return ('Preço lido ' if verified else 'Anúncio de ') + moment.strftime('%d/%m às %H:%M') + ' · ' + age


def offer_card_data(offer: dict) -> dict:
    chunks = [part.strip() for part in offer['title'].split(',')]
    title = re.sub(r'^(?:placa de v[ií]deo|fonte(?: de alimenta[çc][ãa]o)?|ssd)\s+', '', chunks[0], flags=re.I)
    title = re.sub(r'\bGeForce\s+', '', title, flags=re.I)
    specs = ' · '.join(chunks[1:3])
    if re.search(r'\b(?:RTX|GTX|RX)\s*\d{3,4}\b', title, re.I):
        title = re.sub(r'\bPlaca gr[aá]fica\s+', '', title, flags=re.I)
        title = re.sub(r'\s+\d{1,2}\s*GB?(?:\s*-\s*\d{1,2}\s*GB)?\s+GDDR[5-7]X?$', '', title, flags=re.I)
        memory = re.search(r'\b(\d{1,2})\s*GB?\b', offer['title'], re.I)
        generation = re.search(r'\bGDDR([5-7]X?)\b', offer['title'], re.I)
        if memory and generation:
            specs = memory[1] + 'GB · GDDR' + generation[1].upper()
    elif re.search(r'\bKingston\b', offer['title'], re.I) and re.search(r'\bNV3\b', offer['title'], re.I):
        capacities = re.findall(r'\b(\d+(?:[.,]\d+)?)\s*(TB|GB)\b(?!\s*/\s*s\b)', offer['title'], re.I)
        form = re.search(r'\b(2230|2242|2260|2280|22110)\b', offer['title'])
        if len(capacities) == 1 and not re.search(r'\b(?:kit|combo|unidades|estojo|case|capa|adaptador|gabinete|suporte|enclosure|notebook|computador)\b', offer['title'], re.I):
            capacity = capacities[0]
            title = 'Kingston NV3' + (' Mini' if re.search(r'\bMini\b', offer['title'], re.I) else '')
            if form:
                title += ' ' + form[1]
            features = [capacity[0] + capacity[1].upper()]
            if re.search(r'\bM\.?\s*2\b', offer['title'], re.I):
                features.append('M.2')
            if re.search(r'\bNVMe\b', offer['title'], re.I):
                features.append('NVMe')
            pcie = re.search(r'\bPCI[ -]?e\s*(\d\.\d)\b', offer['title'], re.I)
            if pcie:
                features.append('PCIe ' + pcie[1])
            specs = ' · '.join(features)
    if len(title) > 85:
        short = title[:82].rstrip()
        variants = [variant for variant in dict.fromkeys(re.findall(r'\b(?:White|Black|OC|V\d+)\b', title, re.I))
                    if not re.search(r'\b' + re.escape(variant) + r'\b', short, re.I)]
        title = short + '…' + (' · ' + ' / '.join(variants) if variants else '')
    pix, card, announced = (offer.get(key) for key in ('pix', 'card', 'announced'))
    if pix is not None:
        amount, payment = brl(pix), 'no Pix'
    elif offer.get('shop') == 'Mercado Livre' and announced is not None:
        amount, payment = brl(announced), 'pagamento não informado'
    elif card is not None:
        amount, payment = brl(card), 'total no cartão'
    elif announced is not None:
        amount, payment = brl(announced), 'pagamento não informado'
    else:
        amount, payment = '—', 'preço não informado'
    if card is not None and offer.get('installments') and offer.get('installment') is not None:
        secondary = f"{offer['installments']}x de {brl(offer['installment'])}"
    elif card is not None and pix is not None:
        secondary = brl(card) + ' no cartão'
    else:
        secondary = ''
    status = offer.get('status', '')
    if offer.get('availability') == 'out':
        verification, tone = 'Indisponível', 'unavailable'
    elif not price_is_current(offer) and (status.startswith(('Preço lido na loja', 'Preço da loja lido')) or status == 'Anunciado no Telegram'):
        verification, tone = 'Preço desatualizado', 'pending'
    elif status.startswith(('Preço lido na loja', 'Preço da loja lido')):
        verification, tone = 'Preço conferido', 'verified'
    elif status == 'Anunciado no Telegram':
        verification, tone = 'Anúncio do Telegram', 'announced'
    else:
        verification, tone = 'Sem confirmação', 'pending'
    seller = offer.get('seller') or ''
    own_store = re.sub(r'\W+', '', normalized(seller)) == re.sub(r'\W+', '', normalized(offer.get('shop') or ''))
    seller_text = 'Vendido por ' + seller if seller and not own_store else ''
    duplicates = len(offer.get('duplicate_ids') or [])
    current = price_is_current(offer)
    coupon_amount = brl(offer['coupon_price']) if (offer.get('coupon_price') or 0) > 0 else ''
    coupon_primary = bool(current and offer.get('availability') != 'out' and coupon_amount
                          and offer['coupon_price'] < catalog_price(dict(offer, coupon_price=None)))
    return dict(title=title, specs=specs, amount=amount, seller=seller_text,
                coupon_amount=coupon_amount, coupon_primary=coupon_primary,
                display_amount=coupon_amount if coupon_primary else amount,
                display_payment='com cupom na sua sessão' if coupon_primary else payment,
                grouped=f'{duplicates} anúncios agrupados' if duplicates > 1 else '',
                payment=payment, secondary=secondary, verification=verification, tone=tone, freshness=offer_freshness(offer), current=current)
