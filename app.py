"""Painel NiceGUI local. Execute com a venv do projeto."""
import asyncio
from datetime import datetime
import json
import logging
import os
from pathlib import Path

from nicegui import app, ui
from starlette.middleware.trustedhost import TrustedHostMiddleware

from core import BRAND_ALIASES, Store, brl, coupon_is_today, group_offers, money, price_is_current, top_offers, valid_url
from forms import component_draft, component_input_errors
from monitor import Monitor
from ml_coupon_applicator import GROUPS
from presentation import catalog_summary, comparison_rows, coupon_catalog, coupon_page, coupon_refresh_notice, coupon_shop_options, filter_offers, filter_sources, group_caption, history_chart_options, history_method, history_window_text, new_dialog_choices, offer_card_data, offer_filter_chips, offer_freshness, offer_selection, piece_scan_activity, scan_outcome, shop_state, toggle_comparison
from shops import SHOP_NAMES
from olx_ui import render_olx

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
OFFERS_PER_PAGE = 6
store = Store(DATA / 'monitor.sqlite3')
monitor = Monitor(store, DATA)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost'])


def local_time(value):
    return datetime.fromisoformat(value).astimezone().strftime('%d/%m %H:%M:%S') if value else '—'


@app.get('/health')
def health():
    return {'app': 'monitor-precos', 'running': monitor.running, 'telegram_configured': (DATA / 'telegram-credentials.bin').exists()}


@ui.page('/')
def page():
    ui.page_title('Monitor de peças')
    ui.colors(primary='#175cd3', negative='#b42318')
    ui.add_css('''
        :root {--background:#f6f7f9;--surface:#fff;--foreground:#18212f;--muted:#49576b;--line:#d8dee8;--action:#175cd3}
        body {background:var(--background); color:var(--foreground); font-family:Segoe UI,Arial,sans-serif; font-size:15px}
        html {scroll-padding-top:64px}
        .nicegui-content {max-width:1440px;margin:auto;padding:24px;width:100%}
        .q-tab-panel {padding:16px 0}.q-tabs {background:var(--surface);border-bottom:1px solid var(--line)}
        .q-tab {text-transform:none;font-size:15px}.q-field__label {color:var(--muted)}
        .main-tabs {position:sticky;top:0;z-index:50;min-height:48px}
        .monitor-panels,.monitor-panels>.q-panel {overflow:visible}
        .muted {color:var(--muted)}.page-title {font-size:26px;font-weight:650;line-height:1.3}
        .section-title {font-size:19px;font-weight:600;margin-top:12px}
        .q-table th {font-size:13px;font-weight:600;color:var(--muted);background:#f1f4f8}
        .q-table td {font-size:14px;vertical-align:top}.q-table {font-variant-numeric:tabular-nums}
        .q-table__container {box-shadow:none;border:1px solid var(--line);border-radius:8px}
        .q-field--outlined .q-field__control:before {border-color:#9aa7b9}
        .q-btn {text-transform:none}a {text-underline-offset:3px}
        :focus-visible {outline:3px solid var(--action);outline-offset:3px}
        ::selection {background:#d5e5ff;color:#18212f}input {caret-color:var(--action)}
        .offer-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;width:100%;padding:16px 0}
        .offer-card {background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:20px;display:flex;flex-direction:column;gap:16px;min-width:0}
        .offer-card.is-compared {border-color:var(--action)}
        .offer-title {font-size:18px;font-weight:600;line-height:1.35;margin:0;overflow-wrap:anywhere}
        .offer-specs {font-size:13px;color:var(--muted);margin-top:6px}
        .offer-price {font-size:30px;font-weight:650;line-height:1.2;letter-spacing:-.025em;font-variant-numeric:tabular-nums}
        .offer-payment,.offer-installments {font-size:14px;line-height:1.5}
        .offer-payment {color:var(--muted)}.offer-installments {margin-top:6px}
        .offer-status {font-size:12px;line-height:1.4;padding:4px 8px;border-radius:6px;background:#fff7ed;color:#854a0e}
        .offer-status.verified {background:#ecfdf3;color:#067647}.offer-status.announced {background:#eff6ff;color:#175cd3}
        .offer-status.unavailable {background:#fef3f2;color:#b42318}
        .coupon-manager-row {display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;width:100%;padding:18px 0;border-bottom:1px solid var(--line)}
        .coupon-manager-row:last-child {border-bottom:0}
        .coupon-manager-detail {max-width:75ch;overflow-wrap:anywhere;font-size:14px}
        .coupon-manager-actions {display:flex;gap:8px;align-items:start}
        .offer-shop {font-size:13px;font-weight:600;overflow-wrap:anywhere}
        .offer-coupon {font-size:12px;color:#854a0e;overflow-wrap:anywhere}
        .offer-actions {display:flex;align-items:center;gap:12px;margin-top:auto;padding-top:8px}
        .offer-preferences {display:flex;align-items:center;gap:4px;flex-wrap:wrap;border-top:1px solid var(--line);padding-top:8px}
        .comparison-panel {background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:20px;width:100%;gap:16px}
        .comparison-tray {background:var(--surface);border:1px solid var(--line);border-radius:12px;width:100%;margin:8px 0}
        .comparison-host.is-collapsed {position:sticky;top:49px;z-index:40}
        .comparison-host.is-collapsed .comparison-tray {margin:0}
        html:has(.comparison-host.is-collapsed) {scroll-padding-top:144px}
        .comparison-tray .q-item {padding:12px 16px;min-height:48px}
        .comparison-tray .q-item__label {font-weight:600}.comparison-body {padding:0 16px 16px;width:100%;gap:12px}
        .comparison-summary {display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;padding:8px 16px}
        .comparison-table td {white-space:normal;overflow-wrap:anywhere;max-width:360px;min-width:180px}
        .offer-open {display:inline-flex;align-items:center;justify-content:center;background:var(--action);color:white;padding:10px 16px;border-radius:8px;font-size:14px;font-weight:600;text-decoration:none;min-height:42px}
        .offer-open:hover {background:#134cae}.offer-open:active {background:#104090}
        .offer-section .q-item {padding:12px 0}.offer-section .q-item__label {font-size:18px;font-weight:600}
        .offer-section .nicegui-expansion-content {gap:8px}
        .offer-section .q-item__label--caption {font-size:13px;font-weight:400;line-height:1.5;color:var(--muted);margin-top:6px}
        .offer-section {border-bottom:1px solid var(--line)}.source-pill {font-size:12px;background:#edf1f7;color:var(--muted);padding:5px 10px;border-radius:6px}
        .price-history {background:var(--surface);border:1px solid var(--line);border-radius:12px;margin:16px 0;width:100%}
        .price-history .q-item {padding:14px 18px}.price-history .q-item__label {font-size:15px}
        .history-body {padding:0 20px 16px;width:100%;gap:16px}
        .history-summary {display:grid;grid-template-columns:90px repeat(3,minmax(0,1fr));gap:16px;align-items:center;width:100%;font-variant-numeric:tabular-nums}
        .history-price {font-size:18px;font-weight:600}.history-period {font-weight:600}
        .source-pill.verified {background:#ecfdf3;color:#067647}.source-pill.pending {background:#fff7ed;color:#854a0e}
        .source-pill.announced {background:#eff6ff;color:#175cd3}.offer-freshness {font-size:12px;color:var(--muted);margin-top:2px}
        .offer-toolbar {background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px;width:100%;gap:12px}
        .offer-toolbar-main {display:flex;align-items:center;gap:12px;flex-wrap:wrap;width:100%}
        .offer-search {flex:1 1 220px;min-width:180px}.offer-selection .q-btn {min-height:40px;font-size:13px;padding:6px 12px}
        .filter-chips {display:flex;align-items:center;flex-wrap:wrap;gap:8px;width:100%}
        .filter-chip {background:#edf1f7;color:var(--foreground);font-size:13px;max-width:100%;border-radius:6px}
        .filter-chip .q-btn__content {overflow-wrap:anywhere;white-space:normal;text-align:left}
        .catalog-meta {display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;width:100%;padding:0 2px}
        .catalog-sources {display:flex;align-items:center;gap:8px;flex-wrap:wrap;width:100%}
        .undo-offer {background:#eff6ff;color:#175cd3;border:1px solid #b2ccff;border-radius:8px;padding:8px 12px;width:100%;gap:12px;align-items:center;justify-content:space-between}
        .q-btn--dense {min-height:32px}.offer-section .q-item {min-height:48px}
        .settings-panel {background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:24px;width:100%}
        .part-form-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;width:100%}
        .part-form-grid .q-field {min-width:0;width:100%}.form-title {font-size:18px;font-weight:600;margin:0 0 16px}
        .part-list .part-row {padding:18px 0;border-bottom:1px solid var(--line)}
        .part-name {font-size:17px;font-weight:600}.part-query {font-size:13px;color:var(--muted)}
        .sources-layout {display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:24px;width:100%;align-items:start}
        .source-row {padding:16px 0;border-bottom:1px solid var(--line)}.source-row:last-child {border-bottom:0}
        .source-row .source-name {font-size:15px;font-weight:600;overflow-wrap:anywhere}
        .source-state {font-size:13px;color:var(--muted)}.store-row {display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--line)}
        .session-help {font-size:14px;line-height:1.6;color:var(--muted)}.session-state {font-size:13px;line-height:1.5;overflow-wrap:anywhere;padding:12px 0}
        .offer-detail {width:880px;max-width:calc(100vw - 48px)!important;padding:0;max-height:85vh;gap:0}
        .detail-body {padding:24px;overflow-y:auto;min-height:0;width:100%;gap:16px}
        .detail-title {font-size:21px;font-weight:600;line-height:1.4;margin:0;overflow-wrap:anywhere}
        .detail-prices {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;width:100%}
        .detail-price {font-size:24px;font-weight:650;font-variant-numeric:tabular-nums}
        .detail-footer {padding:16px 24px;border-top:1px solid var(--line);width:100%;flex-shrink:0;display:flex;align-items:center;gap:12px;background:var(--surface)}
        .detail-message {white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;line-height:1.6}
        .coupon-list {width:100%;gap:12px}.coupon-row {background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:20px;width:100%;gap:12px;display:flex;flex-direction:column}
        .coupon-code {font-size:17px;font-weight:650;letter-spacing:.025em;border:1px dashed #9aa7b9;padding:6px 10px;border-radius:6px;user-select:all;overflow-wrap:anywhere}
        @media(max-width:1100px){.offer-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
        @media(max-width:700px){.offer-grid{grid-template-columns:1fr}.offer-card{padding:18px}.offer-price{font-size:28px}}
        @media(max-width:640px){.nicegui-content{padding:16px}.q-tab{padding:0 10px}.page-title{font-size:23px}}
    ''')
    with ui.row().classes('w-full items-center justify-between gap-4'):
        with ui.column().classes('gap-1'):
            ui.label('Monitor de peças').classes('page-title').props('role=heading aria-level=1')
            ui.label('Ofertas recentes das peças que você está acompanhando.').classes('muted')
        def shutdown():
            with ui.dialog().props('no-refocus') as dialog, ui.card():
                dialog.props['aria-label'] = 'Encerrar o monitor'
                ui.label('Encerrar o monitor?').classes('section-title').props('role=heading aria-level=2')
                ui.label('Os dados serão mantidos. Abra Iniciar-Monitor.cmd para voltar a acompanhar.')
                with ui.row():
                    ui.button('Continuar monitorando', on_click=dialog.close).props('flat')
                    ui.button('Encerrar monitor', on_click=app.shutdown, color='negative')
            dialog.on('hide', lambda: restore_button_focus(shutdown_button))
            dialog.open()
        with ui.row().classes('items-center gap-3'):
            telegram_status = ui.label(monitor.telegram_status).classes('source-pill')
            shutdown_button = ui.button('Encerrar', on_click=shutdown).props('flat')
    with ui.tabs().classes('w-full main-tabs').props('aria-label="Áreas do monitor"') as tabs:
        offers_tab = ui.tab('Ofertas')
        used_tab = ui.tab('Usados')
        parts_tab = ui.tab('Peças')
        sources_tab = ui.tab('Fontes')
        coupons_tab = ui.tab('Cupons')
        telegram_tab = ui.tab('Telegram')
    with tabs:
        ui.run_javascript('''
            const navigation = document.getElementById(''' + json.dumps(tabs.html_id) + ''');
            const beginArea = event => {
                if (!event.target.closest('[role="tab"]')) return;
                requestAnimationFrame(() => window.scrollTo({top:0, behavior:'instant'}));
            };
            navigation.addEventListener('click', beginArea);
            navigation.addEventListener('keydown', event => {
                if (['Enter',' '].includes(event.key)) beginArea(event);
            });
            window.addEventListener('beforeunload', event => {
                if (navigation.dataset.unsavedPart !== 'true') return;
                event.preventDefault();
                event.returnValue = '';
            });
        ''')
    def restore_button_focus(button, fallback=None):
        with tabs:
            ui.run_javascript('''
                await new Promise(resolve => requestAnimationFrame(resolve));
                const button = document.getElementById(''' + json.dumps(button.html_id) + ''');
                const fallback = document.getElementById(''' + json.dumps(fallback.html_id if fallback else '') + ''');
                const target = button && button.getClientRects().length ? button : fallback?.querySelector('input') || fallback;
                target?.focus();
            ''')
    with ui.tab_panels(tabs, value=offers_tab, animated=False).classes('w-full bg-transparent monitor-panels'):
        with ui.tab_panel(used_tab):
            render_olx(monitor.olx)
        with ui.tab_panel(offers_tab):
            comparison = {'ids': [], 'rows': None, 'expanded': False, 'differences': False}
            hidden_undo = {'ids': [], 'title': ''}
            filter_state = {'expanded': False}
            with ui.column().classes('offer-toolbar'):
                with ui.element('div').classes('offer-toolbar-main'):
                    search = ui.input('Buscar nas ofertas', placeholder='Peça, loja ou cupom').props('outlined dense clearable').classes('offer-search')
                    part_filter = ui.select({0: 'Todas as peças', **{part['id']: part['name'] for part in store.components()}}, value=0, label='Peça').props('outlined dense').classes('w-52')
                    selection_filter = ui.toggle({'': 'Mais baratas', 'favorite': 'Favoritas', 'hidden': 'Ocultas'}, value='').props('unelevated no-caps').classes('offer-selection')
                    selection_filter.props['aria-label'] = 'Seleção de ofertas'
                    def toggle_filters():
                        filter_state['expanded'] = not filter_state['expanded']
                        filters_panel.set_visibility(filter_state['expanded'])
                        filters_button.props['aria-expanded'] = str(filter_state['expanded']).lower()
                    filters_button = ui.button('Filtros', icon='tune', on_click=toggle_filters).props('outline')
                    filters_button.props['aria-expanded'] = 'false'
                    def clear_filters():
                        search.value = shop_filter.value = state_filter.value = ''
                        part_filter.value = 0
                    clear_filter_button = ui.button('Limpar filtros', icon='filter_alt_off', on_click=clear_filters).props('flat dense')
                    async def scan():
                        if monitor.shop_lock.locked():
                            ui.notify('Já existe uma consulta às lojas em andamento.')
                            return
                        scan_button.disable()
                        scan_button.text = 'Consultando lojas…'
                        try:
                            await monitor.scan_shops(force_ml=True)
                        finally:
                            scan_button.enable()
                            scan_button.text = 'Consultar lojas agora'
                    scan_button = ui.button('Consultar lojas agora', icon='refresh', on_click=scan).props('outline')
                with ui.row().classes('w-full gap-3') as filters_panel:
                    shop_filter = ui.select({'': 'Todas as lojas', **{name: name for name in SHOP_NAMES}}, value='', label='Loja').props('outlined dense').classes('w-52')
                    state_filter = ui.select({'': 'Todos os anúncios', 'verified': 'Preço conferido', 'announced': 'Anúncio do Telegram', 'pending': 'Sem confirmação', 'unavailable': 'Indisponível'}, value='', label='Conferência').props('outlined dense').classes('w-52')
                filters_panel.set_visibility(False)
                filters_button.props['aria-controls'] = filters_panel.html_id
                filter_chips = ui.element('div').classes('filter-chips')
            with ui.element('div').classes('catalog-meta'):
                filter_summary = ui.label('').classes('muted text-sm').props('role=status aria-live=polite aria-atomic=true')
                scan_activity = ui.label('').classes('muted text-sm').props('role=status aria-live=polite aria-atomic=true')
            with ui.element('div').classes('catalog-sources'):
                shop_indicators = {name: ui.button(name, color=None, on_click=lambda shop=name: go_to_shop(shop)).props('flat no-caps').classes('source-pill') for name in monitor.shop_status}
                source_expansion = ui.expansion('Estado das fontes').props('dense').classes('text-sm')
            with source_expansion:
                last_event = ui.label('Aguardando mensagens novas.').classes('muted text-sm')
                shop_labels = {name: ui.label(f'{name}: {status}').classes('muted text-sm') for name, status in monitor.shop_status.items()}
                ui.label('Telegram acompanha mensagens novas após ativar a fonte. Só entram ofertas das peças acompanhadas; cupons gerais ficam na aba Cupons.').classes('muted text-sm max-w-3xl')
            empty = ui.label('Nenhuma oferta recebida ainda. Conecte o Telegram na aba Telegram e selecione suas fontes, ou consulte as lojas.').classes('muted my-4 max-w-3xl')
            def open_catalog():
                selection_filter.value = ''
                clear_filters()
                refresh()
                search.run_method('focus')
            with ui.row().classes('gap-3 mb-3') as empty_actions:
                empty_clear = ui.button('Limpar filtros', on_click=clear_filters).props('outline')
                empty_catalog = ui.button('Ver catálogo completo', on_click=open_catalog).props('outline')
            empty_actions.set_visibility(False)
            selection_help = ui.label('').classes('muted text-sm my-2')
            comparison_host = ui.column().classes('w-full comparison-host')
            with comparison_host:
                ui.run_javascript('''
                    await new Promise(resolve => requestAnimationFrame(resolve));
                    let focused = null;
                    document.addEventListener('focusin', event => {
                        const host = document.getElementById(''' + json.dumps(comparison_host.html_id) + ''');
                        const target = event.target.closest('.comparison-toggle,[data-comparison-action]');
                        focused = target && host?.contains(target) ? {
                            element:target, action:target.dataset.comparisonAction || 'toggle'
                        } : null;
                    });
                    new MutationObserver(() => {
                        if (!focused || focused.element.isConnected || document.activeElement !== document.body) return;
                        const host = document.getElementById(''' + json.dumps(comparison_host.html_id) + ''');
                        if (!host?.getClientRects().length) return;
                        const selector = focused.action === 'toggle' ? '.comparison-toggle' : '[data-comparison-action="' + focused.action + '"]';
                        const target = host.querySelector(selector);
                        focused = null;
                        if (target && target.getClientRects().length) target.focus();
                        else document.getElementById(''' + json.dumps(search.html_id) + ''')?.querySelector('input')?.focus();
                    }).observe(document.body, {childList:true, subtree:true});
                ''')
            with ui.row().classes('undo-offer') as undo_banner:
                undo_label = ui.label('').classes('text-sm').props('role=status aria-live=polite aria-atomic=true')
                def undo_hide():
                    offer_id = hidden_undo['ids'][0] if hidden_undo['ids'] else None
                    store.set_offer_preference(hidden_undo['ids'], 'hidden', False)
                    hidden_undo['ids'] = []
                    ui.notify('Ocultação desfeita.')
                    refresh()
                    if offer_id:
                        focus_offer(offer_id, 'hide')
                ui.button('Desfazer', icon='undo', on_click=undo_hide).props('flat dense')
                ui.button('Dispensar', icon='close', on_click=lambda: undo_banner.set_visibility(False)).props('flat dense')
            undo_banner.set_visibility(False)

            def focus_offer(offer_id, action):
                with comparison_host:
                    ui.run_javascript('''
                        await new Promise(resolve => requestAnimationFrame(resolve));
                        const button = document.querySelector('[data-offer-id="''' + str(offer_id) + '''"] [data-offer-action="''' + action + '''"]');
                        const fallback = document.getElementById(''' + json.dumps(search.html_id) + ''')?.querySelector('input');
                        const target = button && button.getClientRects().length ? button : fallback;
                        target?.focus();
                    ''')

            def selected_comparison(rows=None, parts=None):
                grouped = group_offers(parts or store.components(), rows if rows is not None else store.offers())
                selected = []
                for offer_id in comparison['ids']:
                    row = next((row for group in grouped.values() for row in group if offer_id in row['duplicate_ids']), None)
                    if row and row['id'] not in {item['id'] for item in selected}:
                        selected.append(row)
                return selected

            def focus_comparison():
                with comparison_host:
                    ui.run_javascript('''
                        await new Promise(resolve => requestAnimationFrame(resolve));
                        const host = document.getElementById(''' + json.dumps(comparison_host.html_id) + ''');
                        const title = host?.querySelector('.comparison-toggle');
                        if (title && title.getClientRects().length) {
                            host.scrollIntoView({block:'start'});
                            title.focus({preventScroll:true});
                        } else document.getElementById(''' + json.dumps(search.html_id) + ''')?.querySelector('input')?.focus();
                    ''')

            def compare_offer(offer, focus_catalog=True):
                try:
                    selected = toggle_comparison(selected_comparison(), offer)
                    comparison['ids'] = [row['id'] for row in selected]
                    refresh()
                    if focus_catalog:
                        focus_offer(offer['id'], 'compare')
                    else:
                        focus_comparison()
                except ValueError as exc:
                    ui.notify(str(exc), type='warning')

            def clear_comparison():
                comparison['ids'] = []
                refresh()
                search.run_method('focus')

            def set_preference(offer, preference, enabled):
                store.set_offer_preference(offer.get('duplicate_ids') or [offer['id']], preference, enabled)
                if preference == 'hidden':
                    ui.notify('Oferta oculta. Restaure em Seleção → Ofertas ocultas.' if enabled else 'Oferta restaurada.')
                    if enabled:
                        hidden_undo.update(ids=offer.get('duplicate_ids') or [offer['id']], title=offer_card_data(offer)['title'])
                        undo_label.text = hidden_undo['title'] + ' foi ocultada da lista e dos alertas.'
                        undo_banner.set_visibility(True)
                    else:
                        hidden_undo['ids'] = []
                        undo_banner.set_visibility(False)
                refresh()
                focus_offer(offer['id'], 'favorite' if preference == 'favorite' else 'hide')

            def render_comparison(selected):
                comparison_host.clear()
                comparison_host.set_visibility(bool(selected))
                comparison_host.classes(remove='is-collapsed', add='is-collapsed' if selected and not comparison['expanded'] else '')
                if not selected:
                    return
                def toggle_tray(event):
                    comparison['expanded'] = event.value
                    comparison_host.classes(remove='is-collapsed', add='' if event.value else 'is-collapsed')
                    if event.value:
                        focus_comparison()
                with comparison_host:
                    tray = ui.expansion(f"Comparar ofertas · {selected[0]['component']} · {len(selected)} de 3 selecionadas", icon='compare_arrows',
                        caption='Selecione mais uma oferta desta peça.' if len(selected) == 1 else 'Preços e condições lado a lado.',
                        value=comparison['expanded'], on_value_change=toggle_tray).props('header-class=comparison-toggle').classes('comparison-tray')
                    with tray, ui.column().classes('comparison-body'):
                        with ui.row().classes('w-full items-center justify-between'):
                            ui.label('Preços sem frete; códigos publicados não garantem desconto.').classes('muted text-sm')
                            ui.button('Limpar comparação', icon='clear', on_click=clear_comparison).props('flat dense data-comparison-action=clear')
                        for index, offer in enumerate(selected):
                            with ui.row().classes('items-center gap-3'):
                                ui.label(f"Oferta {index + 1} · {offer_card_data(offer)['title']} · {offer['shop']}").classes('font-medium')
                                ui.link('Ver oferta', offer['url'], new_tab=True)
                                remove = ui.button('Remover', icon='close', on_click=lambda row=offer: compare_offer(row, False)).props('flat dense')
                                remove.props['data-comparison-action'] = 'remove-' + str(offer['id'])
                                remove.props['aria-label'] = 'Remover da comparação: ' + offer_card_data(offer)['title'] + ' · ' + offer['shop']
                        if len(selected) > 1:
                            columns = [dict(name='field', label='Condição', field='field', align='left')]
                            columns += [dict(name=f'offer{index}', label=f"Oferta {index + 1} · {offer['shop']}", field=f'offer{index}', align='left') for index, offer in enumerate(selected)]
                            def update_differences(event):
                                comparison['differences'] = event.value
                                table.rows = comparison_rows(selected, event.value)
                                table.update()
                            ui.switch('Mostrar apenas diferenças', value=comparison['differences'], on_change=update_differences).props('data-comparison-action=differences')
                            table = ui.table(columns=columns, rows=comparison_rows(selected, comparison['differences']), row_key='field').props('flat hide-bottom no-data-label="Nenhuma diferença nas condições exibidas."').classes('w-full comparison-table')
            detail_host = ui.element('div').classes('contents')
            def details(offer_id):
                offer = store.offer(offer_id)
                if not offer:
                    return
                detail_host.clear()
                detail_state = {'offer': offer}
                with detail_host, ui.dialog().props('no-refocus') as dialog, ui.card().classes('offer-detail'):
                    dialog.props['aria-label'] = 'Detalhes: ' + offer_card_data(offer)['title'] + ' · ' + offer['shop']
                    with ui.column().classes('detail-body'):
                        @ui.refreshable
                        def detail_summary():
                            current = detail_state['offer']
                            with ui.column().classes('w-full gap-4'):
                                with ui.row().classes('w-full items-center justify-between gap-2'):
                                    ui.label(current['shop'] + ((' · Vendedor: ' + current['seller']) if current['seller'] else '')).classes('offer-shop')
                                    card = offer_card_data(current)
                                    ui.label(card['verification']).classes('offer-status ' + card['tone'])
                                ui.label(current['title']).classes('detail-title').props('role=heading aria-level=2')
                                with ui.element('div').classes('detail-prices'):
                                    for key, label in [('pix', 'No Pix'), ('card', 'Total no cartão'), ('announced', 'Preço anunciado'), ('coupon_price', 'Com cupom na sua sessão')]:
                                        if current.get(key) is not None:
                                            with ui.column().classes('gap-1'):
                                                ui.label(label).classes('muted text-sm')
                                                ui.label(brl(current[key])).classes('detail-price')
                                    if all(current[key] is None for key in ('pix', 'card', 'announced')):
                                        ui.label('Preço não informado.').classes('muted')
                                if card['secondary']:
                                    ui.label(card['secondary']).classes('text-sm')
                                if card['coupon_amount']:
                                    ui.label('Preço com cupom exibido na sua sessão do Mercado Livre; confira as condições no anúncio.' if card['current'] else 'Último preço com cupom lido na sessão; fora da comparação até nova conferência.').classes('muted text-sm')
                                ui.label(current['status']).classes('text-sm')
                                ui.label('Frete não consultado.').classes('muted text-sm')
                                codes = json.loads(current['coupons'])
                                if codes:
                                    ui.label('Cupons: ' + ', '.join(codes) + ' · desconto não validado').classes('offer-coupon')
                                ui.label('Encontrado: ' + local_time(current['published_at']) + ' · Última tentativa de conferência: ' + local_time(current['checked_at'])).classes('muted text-sm')
                        detail_summary()
                        detail_queue = ui.label('').classes('muted text-sm')
                        detail_queue.set_visibility(offer_id in monitor.queued)
                        if offer['message']:
                            with ui.expansion('Mensagem original').classes('w-full'):
                                ui.label(offer['message']).classes('detail-message')
                        grouped = group_offers(store.components(), store.offers())
                        related_ids = next((row['duplicate_ids'] for row in grouped[offer['component_id']]
                                            if offer_id in row['duplicate_ids']), [offer_id])
                        if len(related_ids) > 1:
                            with ui.expansion(f'Anúncios agrupados nesta loja · {len(related_ids)}').classes('w-full'):
                                for related_id in related_ids:
                                    related = store.offer(related_id)
                                    ui.link(related['title'], related['url'], new_tab=True).classes('text-sm')
                        def history_rows():
                            observations = store.rows('SELECT * FROM observations WHERE offer_id IN (' + ','.join('?' for _ in related_ids) + ') ORDER BY id DESC LIMIT 30', related_ids)
                            return [dict(id=row['id'], time=local_time(row['observed_at']), pix=brl(row['pix']), card=brl(row['card']), announced=brl(row['announced']), coupon_price=brl(row['coupon_price']), status=row['status']) for row in observations]
                        observations = history_rows()
                        with ui.expansion('Histórico observado').classes('w-full'):
                            ui.label('Até 30 leituras recentes; preço original e valor com cupom da sessão separados, sem frete. Descontos antigos não são reconstruídos.').classes('muted text-sm')
                            detail_history_table = ui.table(columns=[{'name': key, 'field': key, 'label': label, 'align': 'left'}
                                                                    for key, label in [('time', 'Conferência'), ('pix', 'Pix'), ('card', 'Total cartão'), ('announced', 'Anunciado'), ('coupon_price', 'Com cupom'), ('status', 'Resultado')]],
                                                           rows=observations, row_key='id', pagination=5).classes('w-full')
                            detail_history_table.set_visibility(bool(observations))
                            detail_history_empty = ui.label('Nenhuma leitura registrada ainda.').classes('muted text-sm')
                            detail_history_empty.set_visibility(not observations)
                        origins = store.rows('SELECT * FROM origins WHERE offer_id IN (' + ','.join('?' for _ in related_ids) + ')', related_ids)
                        message_origins = [origin for origin in origins if origin['message_url']]
                        if message_origins:
                            with ui.expansion('Publicações do Telegram').classes('w-full'):
                                for origin in message_origins:
                                    ui.link('Mensagem em ' + origin['source'], origin['message_url'], new_tab=True)
                    def check_price():
                        monitor.enqueue(offer_id, manual=True)
                        if offer_id in monitor.queued:
                            ui.notify('Conferência na fila. Preço e resultado serão atualizados aqui.', type='info')
                        else:
                            ui.notify('A fila está cheia. Tente conferir novamente em instantes.', type='warning')
                        update_detail()
                    with ui.element('div').classes('detail-footer'):
                        detail_link = ui.link('Ver oferta', offer['url'], new_tab=True).classes('offer-open')
                        detail_check = ui.button('Conferir preço agora', on_click=check_price).props('outline')
                        ui.button('Fechar', on_click=dialog.close).props('flat').classes('ml-auto')
                    def update_detail():
                        current = store.offer(offer_id)
                        if not current:
                            detail_queue.text = 'Este anúncio não está mais disponível no monitor.'
                            detail_queue.set_visibility(True)
                            detail_check.disable()
                            return
                        current['price_current'] = price_is_current(current)
                        if current != detail_state['offer']:
                            detail_state['offer'] = current
                            detail_summary.refresh()
                            detail_link.props['href'] = current['url']
                            detail_link.update()
                            observations = history_rows()
                            detail_history_table.rows = observations
                            detail_history_table.update()
                            detail_history_table.set_visibility(bool(observations))
                            detail_history_empty.set_visibility(not observations)
                        queued = offer_id in monitor.queued
                        detail_queue.text = 'Conferência na fila ou em andamento…'
                        detail_queue.set_visibility(queued)
                        detail_check.set_enabled(not queued)
                        detail_check.text = 'Conferindo…' if queued else 'Conferir preço agora'
                    update_detail()
                    ui.timer(2, update_detail)
                def close_detail():
                    dialog.delete()
                    section = group_widgets.get(offer['component_id'], {}).get('section')
                    section_id = section.html_id if section else ''
                    ui.run_javascript('''
                        const card = document.querySelector('[data-offer-id="''' + str(offer_id) + '''"] .offer-actions .q-btn');
                        const section = document.getElementById(''' + json.dumps(section_id) + ''');
                        const search = document.getElementById(''' + json.dumps(search.html_id) + ''');
                        const target = [card, section?.querySelector('.q-item'), search?.querySelector('input')]
                            .find(element => element && element.getClientRects().length);
                        target?.focus();
                    ''')
                dialog.on('hide', close_detail)
                dialog.open()
            offer_groups = ui.column().classes('w-full gap-3')
            group_widgets = {}
            with offer_groups:
                ui.run_javascript('''
                    await new Promise(resolve => requestAnimationFrame(resolve));
                    let focused = null;
                    document.addEventListener('focusin', event => {
                        const catalog = document.getElementById(''' + json.dumps(offer_groups.html_id) + ''');
                        const action = event.target.closest('[data-offer-action]');
                        const card = action?.closest('[data-offer-id]');
                        focused = card && catalog?.contains(card) ? {
                            element: action, id: card.dataset.offerId, action: action.dataset.offerAction
                        } : null;
                    });
                    new MutationObserver(() => {
                        if (!focused || focused.element.isConnected || document.activeElement !== document.body) return;
                        const catalog = document.getElementById(''' + json.dumps(offer_groups.html_id) + ''');
                        if (!catalog?.getClientRects().length) return;
                        const target = catalog.querySelector('[data-offer-id="' + focused.id + '"] [data-offer-action="' + focused.action + '"]');
                        if (target && target.getClientRects().length) {
                            target.focus();
                        } else {
                            focused = null;
                            document.getElementById(''' + json.dumps(search.html_id) + ''')?.querySelector('input')?.focus();
                        }
                    }).observe(document.body, {childList:true, subtree:true});
                ''')

            def render_cards(part_id):
                widgets = group_widgets[part_id]
                offers = widgets['rows']
                pages = max(1, (len(offers) + OFFERS_PER_PAGE - 1) // OFFERS_PER_PAGE)
                widgets['page'] = min(max(1, widgets['page']), pages)
                start = (widgets['page'] - 1) * OFFERS_PER_PAGE
                widgets['previous'].set_enabled(widgets['page'] > 1)
                widgets['next'].set_enabled(widgets['page'] < pages)
                widgets['range'].text = f"{start + 1}–{min(start + OFFERS_PER_PAGE, len(offers))} de {len(offers)} {'oferta' if len(offers) == 1 else 'ofertas'}"
                widgets['pager'].set_visibility(bool(offers))
                widgets['empty'].set_visibility(not offers)
                widgets['cards'].clear()
                widgets['freshness'] = []
                comparison_ids = {offer_id for row in selected_comparison() for offer_id in row['duplicate_ids']}
                with widgets['cards']:
                    for offer in offers[start:start + OFFERS_PER_PAGE]:
                        card = offer_card_data(offer)
                        with ui.element('article').classes('offer-card').props(f'data-offer-id={offer["id"]}') as article:
                            article.props['aria-label'] = card['title'] + ' · ' + offer['shop']
                            action_context = card['title'] + ' · ' + offer['shop'] + ' · ' + card['display_amount']
                            if comparison_ids.intersection(offer['duplicate_ids']):
                                article.classes('is-compared')
                            with ui.row().classes('w-full items-center justify-between gap-2'):
                                ui.label(offer['shop']).classes('offer-shop')
                                ui.label(card['verification']).classes('offer-status ' + card['tone'])
                            with ui.column().classes('gap-0'):
                                ui.label(card['title']).classes('offer-title').props('role=heading aria-level=3 tabindex=-1')
                                if card['specs']:
                                    ui.label(card['specs']).classes('offer-specs')
                                if card['seller']:
                                    ui.label(card['seller']).classes('muted text-xs mt-2 break-words')
                                if card['grouped']:
                                    ui.label(card['grouped']).classes('muted text-xs mt-1')
                            with ui.column().classes('gap-0'):
                                ui.label(card['display_amount']).classes('offer-price')
                                ui.label(card['display_payment']).classes('offer-payment')
                                if card['coupon_primary'] and card['amount'] != '—':
                                    ui.label('Sem cupom: ' + card['amount'] + ' · ' + card['payment']).classes('offer-installments')
                                if card['secondary']:
                                    ui.label(card['secondary']).classes('offer-installments')
                                if card['coupon_amount'] and not card['coupon_primary']:
                                    ui.label(card['coupon_amount'] + ' com cupom').classes('offer-installments font-semibold')
                                    ui.label('Disponível na sua sessão' if card['current'] else 'Último valor lido; precisa de nova conferência').classes('muted text-xs')
                                if not card['current']:
                                    ui.label('Fora da comparação até uma nova leitura da loja.').classes('muted text-xs')
                            freshness = ui.label(card['freshness']).classes('offer-freshness')
                            widgets['freshness'].append((freshness, offer))
                            codes = json.loads(offer['coupons'])
                            if codes:
                                ui.label('Cupom ' + ', '.join(codes) + ' · não validado').classes('offer-coupon')
                            if offer['telegram_origin']:
                                ui.label('Encontrado no Telegram').classes('muted text-xs')
                            with ui.element('div').classes('offer-actions'):
                                offer_link = ui.link('Ver oferta', offer['url'], new_tab=True).classes('offer-open').props('data-offer-action=open')
                                offer_link.props['aria-label'] = 'Abrir oferta: ' + action_context
                                offer_link.props['aria-description'] = 'Abre em uma nova aba.'
                                detail_button = ui.button('Detalhes', on_click=lambda offer_id=offer['id']: details(offer_id)).props('flat no-caps data-offer-action=details').classes('text-sm')
                                detail_button.props['aria-label'] = 'Detalhes: ' + action_context
                            with ui.element('div').classes('offer-preferences'):
                                favorite = ui.button('Salva' if offer.get('favorite') else 'Salvar', icon='star' if offer.get('favorite') else 'star_border',
                                    on_click=lambda row=offer: set_preference(row, 'favorite', not row.get('favorite'))).props('flat dense')
                                favorite.props['aria-label'] = ('Remover dos favoritos: ' if offer.get('favorite') else 'Salvar nos favoritos: ') + action_context
                                favorite.props['aria-pressed'] = str(bool(offer.get('favorite'))).lower()
                                favorite.props['data-offer-action'] = 'favorite'
                                if offer.get('hidden'):
                                    restore = ui.button('Restaurar', icon='visibility', on_click=lambda row=offer: set_preference(row, 'hidden', False)).props('flat dense')
                                    restore.props['aria-label'] = 'Restaurar oferta: ' + card['title'] + ' · ' + offer['shop']
                                    restore.props['data-offer-action'] = 'hide'
                                else:
                                    selected = bool(comparison_ids.intersection(offer['duplicate_ids']))
                                    compare = ui.button('Selecionada' if selected else 'Comparar', icon='check' if selected else 'compare_arrows',
                                        on_click=lambda row=offer: compare_offer(row)).props('flat dense')
                                    compare.props['aria-pressed'] = str(selected).lower()
                                    compare.props['aria-label'] = 'Comparar: ' + action_context
                                    compare.props['data-offer-action'] = 'compare'
                                    hide = ui.button('Ocultar', icon='visibility_off', on_click=lambda row=offer: set_preference(row, 'hidden', True)).props('flat dense')
                                    hide.props['title'] = 'Ocultar estes anúncios agrupados e seus alertas; histórico preservado.'
                                    hide.props['aria-description'] = hide.props['title']
                                    hide.props['aria-label'] = 'Ocultar oferta: ' + card['title'] + ' · ' + offer['shop']
                                    hide.props['data-offer-action'] = 'hide'

            def change_page(part_id, step):
                group_widgets[part_id]['page'] += step
                render_cards(part_id)
                with group_widgets[part_id]['cards']:
                    ui.run_javascript('''
                        await new Promise(resolve => requestAnimationFrame(resolve));
                        const card = document.getElementById(''' + json.dumps(group_widgets[part_id]['cards'].html_id) + ''')?.querySelector('article');
                        if (card && card.getClientRects().length) {
                            card.scrollIntoView({block:'start'});
                            card.querySelector('[role="heading"]')?.focus({preventScroll:true});
                        }
                    ''')

            def refresh_history(part_id):
                widgets = group_widgets[part_id]['history']
                history = store.price_history(part_id, widgets['payment'].value)
                for window in ('7', '30'):
                    text = history_window_text(history[window])
                    for key, label in widgets[window].items():
                        label.text = text[key]
                widgets['empty'].set_visibility(not history['points'])
                widgets['chart'].set_visibility(bool(history['points']))
                payment = widgets['payment'].value
                context = widgets['name'] + ' · ' + widgets['payment'].options[payment]
                widgets['method'].text = history_method(payment)
                widgets['title'].text = 'Menor preço diário · ' + widgets['payment'].options[payment] + ' · últimos 30 dias'
                widgets['chart'].options.clear()
                widgets['chart'].options.update(history_chart_options(history, context))
                widgets['chart'].update()

            async def scan_part(part_id):
                if monitor.shop_lock.locked():
                    ui.notify('Já existe uma consulta às lojas em andamento. Aguarde a conclusão.')
                    return
                button = group_widgets[part_id]['scan']
                button.disable()
                button.text = 'Atualizando…'
                button.props('loading')
                previous_scan = monitor.last_shop_scan_started
                try:
                    await monitor.scan_shops(force_ml=True, component_id=part_id)
                    widgets = group_widgets.get(part_id)
                    if widgets and monitor.last_shop_scan_started != previous_scan and monitor.shop_scan_component_id == part_id:
                        result = scan_outcome(monitor.shop_status)
                        widgets['result'].text = 'Consulta de ' + local_time(monitor.last_shop_scan_finished)
                        widgets['result'].props['caption'] = result['summary']
                        widgets['result'].set_visibility(True)
                        widgets['result'].set_value(result['tone'] == 'pending')
                        widgets['result_body'].clear()
                        with widgets['result_body']:
                            for shop, status in monitor.shop_status.items():
                                with ui.row().classes('w-full items-start gap-3'):
                                    label, tone = shop_state(status)
                                    ui.label(shop + ' · ' + label).classes('source-pill ' + tone)
                                    ui.label(status).classes('muted text-sm flex-1 break-words')
                                    if tone == 'pending':
                                        source_button = ui.button('Ver fonte', on_click=lambda name=shop: go_to_shop(name)).props('flat dense')
                                        source_button.props['aria-label'] = 'Ver configuração de ' + shop
                        with offer_groups:
                            ui.notify('Consulta concluída com pendências. Confira o resultado nesta peça.' if result['tone'] == 'pending'
                                      else 'Consulta desta peça concluída.', type='warning' if result['tone'] == 'pending' else 'positive')
                finally:
                    widgets = group_widgets.get(part_id)
                    if widgets:
                        widgets['scan'].props('loading=false')
                        widgets['scan'].text = 'Atualizar peça'
                    refresh()

            def create_offer_groups(parts):
                opened = {key for key, widgets in group_widgets.items() if widgets['section'].value}
                opened = set(sorted(opened)[:1])
                first_render = not group_widgets
                offer_groups.clear()
                group_widgets.clear()
                with offer_groups:
                    for index, part in enumerate(parts):
                        with ui.expansion(part['name'], group='offer-parts', value=part['id'] in opened or first_render and index == 0).classes('w-full offer-section') as section:
                            with ui.row().classes('w-full items-center justify-between gap-3'):
                                active_part = next((row for row in parts if row['id'] == monitor.shop_scan_component_id), None)
                                part_activity = ui.label(piece_scan_activity(part, active_part, monitor.shop_status, monitor.shop_lock.locked())).classes('muted text-sm').props('role=status aria-live=polite aria-atomic=true')
                                part_scan = ui.button('Atualizar peça', icon='refresh', on_click=lambda part_id=part['id']: scan_part(part_id)).props('outline')
                                part_scan.set_enabled(not monitor.shop_lock.locked() and bool(part['enabled']))
                                part_scan.props['aria-label'] = 'Atualizar ofertas de ' + part['name']
                            with ui.expansion('Resultado da consulta', icon='fact_check').classes('w-full') as part_result:
                                result_body = ui.column().classes('w-full gap-3')
                            part_result.set_visibility(False)
                            history_widgets = {'name': part['name']}
                            with ui.expansion('Histórico de preços · ' + part['name'], icon='show_chart').classes('price-history') as history_section:
                                with ui.column().classes('history-body'):
                                    history_widgets['payment'] = ui.select({'effective': 'Melhor preço, incluindo cupom', 'pix': 'Pix sem cupom', 'card': 'Total no cartão sem cupom', 'announced': 'Anunciado sem cupom'},
                                        value='pix', label='Pagamento do histórico', on_change=lambda part_id=part['id']: refresh_history(part_id)).props('outlined dense').classes('w-72')
                                    for window in ('7', '30'):
                                        with ui.element('div').classes('history-summary'):
                                            ui.label(window + ' dias').classes('history-period')
                                            with ui.column().classes('gap-1'):
                                                ui.label('Menor preço').classes('muted text-sm')
                                                minimum = ui.label('—').classes('history-price')
                                            with ui.column().classes('gap-1'):
                                                ui.label('Mediana diária').classes('muted text-sm')
                                                median_label = ui.label('—').classes('history-price')
                                            coverage = ui.label('').classes('muted text-sm')
                                        history_widgets[window] = dict(minimum=minimum, median=median_label, coverage=coverage)
                                    history_widgets['method'] = ui.label('').classes('muted text-sm max-w-3xl').props('role=status aria-live=polite')
                                    with ui.expansion('Como interpretar este histórico').classes('w-full'):
                                        ui.label('A mediana usa os menores preços de cada dia. Menos de três dias de leituras é um histórico curto. Frete não incluído; leituras esgotadas não contam, dias sem dados ficam em branco e descontos antigos não são reconstruídos.').classes('muted text-sm max-w-3xl')
                                    history_widgets['empty'] = ui.label('Ainda não há leituras confirmadas neste pagamento. O histórico cresce conforme as lojas são consultadas.').classes('muted py-3')
                                    history_widgets['title'] = ui.label('').classes('muted text-sm')
                                    history_widgets['chart'] = ui.echart(history_chart_options({'points': []})).classes('w-full h-56')
                            group_empty = ui.label('Nenhuma oferta desta peça encontrada.').classes('muted py-4')
                            cards = ui.element('div').classes('offer-grid')
                            with ui.row().classes('w-full items-center justify-between py-3') as pager:
                                count = ui.label('').classes('muted text-sm').props('role=status aria-live=polite aria-atomic=true')
                                with ui.row().classes('gap-2'):
                                    previous = ui.button('Anterior', icon='chevron_left', on_click=lambda part_id=part['id']: change_page(part_id, -1)).props('flat no-caps')
                                    next_button = ui.button('Próxima', icon='chevron_right', on_click=lambda part_id=part['id']: change_page(part_id, 1)).props('flat no-caps')
                                    previous.props['aria-label'] = 'Página anterior de ' + part['name']
                                    next_button.props['aria-label'] = 'Próxima página de ' + part['name']
                            history_section.move(section)
                        group_widgets[part['id']] = dict(section=section, cards=cards, empty=group_empty, rows=[], page=1,
                                                        previous=previous, next=next_button, range=count, pager=pager, history=history_widgets, scan=part_scan,
                                                        activity=part_activity, result=part_result, result_body=result_body)
                        refresh_history(part['id'])

            def open_offer_group(part_id):
                for key, widgets in group_widgets.items():
                    widgets['section'].set_value(key == part_id)

        with ui.tab_panel(parts_tab):
            with ui.row().classes('w-full items-center justify-between'):
                ui.label('Componentes acompanhados').classes('section-title').props('role=heading aria-level=2')
                new_part_button = ui.button('Adicionar peça', icon='add', on_click=lambda: start_part()).props('outline')
            ui.label('Avisos só para ofertas entre os 10% mais baratos da peça. Com limite, o preço também precisa respeitar o teto e o pagamento escolhido. A mesma oferta só avisa novamente após queda de pelo menos 2%.').classes('muted')
            parts_summary = ui.label('').classes('muted text-sm')
            editing = {'id': None, 'baseline': None, 'open': False}
            with ui.element('section').classes('settings-panel mt-4') as part_form:
                form_title = ui.label('Adicionar peça').classes('form-title').props('role=heading aria-level=2')
                part_form.props['aria-labelledby'] = form_title.html_id
                with ui.element('div').classes('part-form-grid'):
                    part_name = ui.input('Nome da peça', placeholder='Ex.: Minha placa de vídeo').props('outlined')
                    part_kind = ui.select({'custom': 'Busca por texto · outro modelo', 'gpu': 'RTX 5060 · sem Ti', 'psu': 'Corsair CX750 · sem M/F', 'ssd': 'Kingston NV3'}, value='custom', label='Filtro do modelo').props('outlined')
                    part_query = ui.input('Busca nas lojas', placeholder='Ex.: kingston nv3 1tb').props('outlined')
                with ui.element('div').classes('part-form-grid mt-4'):
                    part_target = ui.input('Preço máximo em R$ (opcional)', placeholder='Ex.: 2.000,00').props('outlined hint="Limita alertas e Mais baratas no pagamento escolhido. Vazio: sem teto de preço."')
                    part_payment = ui.select({'pix': 'Pix', 'card': 'Total no cartão'}, value='pix', label='Pagamento do limite').props('outlined')
                    part_capacity = ui.number('Capacidade em GB (NV3)', value=1000, min=1, precision=0).props('outlined hint="Para 1 TB, use 1000 GB"')
                part_capacity.set_visibility(False)
                part_kind.on_value_change(lambda event: part_capacity.set_visibility(event.value == 'ssd'))
                part_matching_hint = ui.label('').classes('muted text-sm mt-3')
                def matching_hint():
                    part_matching_hint.text = {'custom': 'Busca por texto: todos os termos da busca devem aparecer na oferta. Use para modelos como RX 9060.',
                                               'gpu': 'Filtro específico para RTX 5060: exclui versões Ti e anúncios de computadores completos.',
                                               'psu': 'Filtro específico para Corsair CX750: exclui modelos CX750M e CX750F.',
                                               'ssd': 'Filtro específico para Kingston NV3, na capacidade indicada.'}.get(part_kind.value, '')
                part_kind.on_value_change(matching_hint)
                matching_hint()
                part_ignored_brands = ui.select(sorted(BRAND_ALIASES), value=[], multiple=True, with_input=True,
                                               label='Marcas ignoradas').props('outlined use-chips').classes('w-full mt-4')
                ui.label('Ofertas dessas marcas ficam fora do catálogo e dos avisos. Você pode removê-las desta lista para voltar a acompanhar.').classes('muted text-sm')
                draft_status = ui.label('').classes('muted text-sm mt-3').props('role=status aria-live=polite')
                part_payment.disable()
                part_target.on_value_change(lambda event: part_payment.set_enabled(bool((event.value or '').strip())))
            fields = dict(name=part_name, kind=part_kind, query=part_query, capacity=part_capacity, target=part_target, payment=part_payment)
            part_form.set_visibility(False)

            def current_draft():
                return component_draft(part_name.value, part_kind.value, part_query.value,
                                       part_capacity.value, part_target.value, part_payment.value, part_ignored_brands.value)

            def update_draft_status():
                unsaved = editing['open'] and current_draft() != editing['baseline']
                draft_status.text = 'Alterações ainda não salvas.' if unsaved else ''
                tabs.props['data-unsaved-part'] = str(unsaved).lower()

            for field in [*fields.values(), part_ignored_brands]:
                field.on_value_change(update_draft_status)

            async def can_discard():
                if not editing['open'] or current_draft() == editing['baseline']:
                    return True
                with ui.dialog().props('no-refocus') as discard, ui.card().classes('max-w-md'):
                    discard.props['aria-label'] = 'Descartar alterações da peça'
                    ui.label('Descartar alterações?').classes('section-title').props('role=heading aria-level=2')
                    ui.label('Esta peça tem alterações que ainda não foram salvas.')
                    with ui.row().classes('gap-3'):
                        ui.button('Continuar editando', on_click=lambda: discard.submit(False)).props('outline autofocus')
                        ui.button('Descartar alterações', on_click=lambda: discard.submit(True), color='negative')
                result = await discard
                discard.delete()
                if not result:
                    part_name.run_method('focus')
                return bool(result)

            def show_part_form():
                editing['baseline'] = current_draft()
                editing['open'] = True
                update_draft_status()
                part_form.set_visibility(True)
                new_part_button.disable()
                with part_form:
                    ui.run_javascript('''
                        await new Promise(resolve => requestAnimationFrame(resolve));
                        document.getElementById(''' + json.dumps(part_name.html_id) + ''')?.querySelector('input')?.focus();
                    ''')

            def start_part():
                clear_part()
                show_part_form()

            def focus_new_part():
                with part_form:
                    ui.run_javascript('''
                        await new Promise(resolve => requestAnimationFrame(resolve));
                        document.getElementById(''' + json.dumps(new_part_button.html_id) + ''')?.focus();
                    ''')

            async def cancel_part():
                if not await can_discard():
                    return
                close_part_form()
                focus_new_part()

            def close_part_form():
                editing['open'] = False
                clear_part()
                part_form.set_visibility(False)
                new_part_button.enable()

            def clear_part():
                editing['id'] = None
                part_name.value = part_query.value = part_target.value = ''
                part_kind.value = 'custom'
                part_capacity.value = 1000
                part_payment.value = 'pix'
                part_ignored_brands.value = []
                form_title.text = 'Adicionar peça'
                save_part_button.text = 'Salvar peça'
                clear_part_button.text = 'Cancelar'
                for field in fields.values():
                    field.error = None
                editing['baseline'] = current_draft()
                update_draft_status()

            def save_part():
                errors = component_input_errors(part_name.value, part_kind.value, part_query.value,
                                                part_capacity.value, part_target.value, part_payment.value)
                for key, field in fields.items():
                    field.error = errors.get(key)
                if errors:
                    fields[next(iter(errors))].run_method('focus')
                    ui.notify('Confira os campos destacados. A peça ainda não foi salva.', type='warning')
                    return
                try:
                    store.save_component(part_name.value or '', part_kind.value, part_query.value or '',
                                         int(part_capacity.value) if part_kind.value == 'ssd' else None,
                                         money(part_target.value) if part_target.value and part_target.value.strip() else None,
                                         part_payment.value, editing['id'], part_ignored_brands.value or [])
                    close_part_form()
                    component_list.refresh()
                    ui.notify('Peça salva.', type='positive')
                    focus_new_part()
                except (ValueError, TypeError) as exc:
                    ui.notify(str(exc), type='negative')

            with part_form, ui.row().classes('mt-4 gap-3'):
                save_part_button = ui.button('Salvar peça', on_click=save_part)
                clear_part_button = ui.button('Cancelar', on_click=cancel_part).props('flat')

            async def edit_part(part):
                if editing['open'] and editing['id'] == part['id']:
                    with part_form:
                        ui.run_javascript('document.getElementById(' + json.dumps(part_name.html_id) + ')?.querySelector("input")?.focus();')
                    return
                if not await can_discard():
                    return
                editing['id'] = part['id']
                part_name.value, part_kind.value, part_query.value = part['name'], part['kind'], part['query']
                part_capacity.value = part['capacity_gb'] or 1000
                part_target.value = str(part['target'] / 100).replace('.', ',') if part['target'] is not None else ''
                part_payment.value = part['target_payment']
                part_ignored_brands.value = json.loads(part.get('ignored_brands') or '[]')
                form_title.text = 'Editar ' + part['name']
                save_part_button.text = 'Salvar alterações'
                clear_part_button.text = 'Cancelar edição'
                for field in fields.values():
                    field.error = None
                show_part_form()

            def remove_part(part, trigger):
                with ui.dialog().props('no-refocus') as dialog, ui.card():
                    dialog.props['aria-label'] = 'Remover ' + part['name']
                    ui.label('Remover ' + part['name'] + '?').classes('section-title').props('role=heading aria-level=2')
                    ui.label('As ofertas e o histórico desta peça também serão removidos.')
                    def confirm():
                        store.delete('components', part['id'])
                        if editing['id'] == part['id']:
                            close_part_form()
                        component_list.refresh()
                        dialog.close()
                    with ui.row():
                        ui.button('Cancelar', on_click=dialog.close).props('flat')
                        ui.button('Remover peça', on_click=confirm, color='negative')
                dialog.on('hide', lambda: restore_button_focus(trigger, new_part_button))
                dialog.open()

            @ui.refreshable
            def component_list():
                if not store.components():
                    ui.label('Nenhuma peça cadastrada. Use Adicionar peça para escolher o que acompanhar.').classes('muted py-4')
                for part in store.components():
                    with ui.row().classes('w-full items-center justify-between part-row gap-3') as part_row:
                        part_row.props['role'] = 'group'
                        part_row.props['aria-label'] = part['name']
                        with ui.column().classes('gap-1'):
                            ui.label(part['name']).classes('part-name')
                            ui.label('Busca: ' + part['query']).classes('part-query')
                            ignored = json.loads(part.get('ignored_brands') or '[]')
                            if ignored:
                                ui.label('Ignoradas: ' + ', '.join(ignored)).classes('muted text-sm')
                            ui.label('Entre os 10% mais baratos' if part['target'] is None else
                                     f"Entre os 10% mais baratos · até {brl(part['target'])} · {'Pix' if part['target_payment']=='pix' else 'total parcelado'}").classes('muted text-sm')
                        with ui.row().classes('items-center'):
                            toggle_part = ui.switch('Acompanhar', value=bool(part['enabled']), on_change=lambda event, p=part: store.toggle('components', p['id'], event.value))
                            toggle_part.props['aria-label'] = 'Acompanhar ' + part['name']
                            edit = ui.button('Editar', on_click=lambda p=part: edit_part(p)).props('flat')
                            edit.props['aria-label'] = 'Editar ' + part['name']
                            remove = ui.button('Remover', on_click=lambda event, p=part: remove_part(p, event.sender)).props('flat color=negative')
                            remove.props['aria-label'] = 'Remover ' + part['name']
            with ui.column().classes('w-full gap-0 part-list'):
                component_list()

        with ui.tab_panel(sources_tab):
            ui.label('Fontes de ofertas').classes('section-title').props('role=heading aria-level=2')
            ui.label('Selecione grupos e canais em que sua conta já participa. O app não entra em grupos automaticamente.').classes('muted')
            with ui.element('div').classes('sources-layout mt-4'):
                telegram_panel = ui.element('section').classes('settings-panel')
                shops_panel = ui.element('section').classes('settings-panel')
            source_work = {'loading': False, 'saving': False}
            with telegram_panel:
                with ui.row().classes('w-full items-center justify-between mb-2'):
                    ui.label('Grupos do Telegram').classes('form-title mb-0').props('role=heading aria-level=2')
                    sources_connection = ui.label('').classes('offer-status')
                add_source_expansion = ui.expansion('Adicionar grupo ou canal', icon='add').classes('w-full')
                with ui.row().classes('w-full items-center gap-2 mt-2'):
                    source_search = ui.input('Buscar nas fontes', placeholder='Nome, @grupo ou ID').props('outlined dense clearable').classes('flex-1')
                    def clear_source_search():
                        source_search.value = ''
                        source_search.run_method('focus')
                    source_clear = ui.button('Limpar busca', icon='close', on_click=clear_source_search).props('flat dense')
                source_summary = ui.label('').classes('muted text-sm').props('role=status aria-live=polite aria-atomic=true')
            with add_source_expansion:
                ui.label('Da sua conta').classes('font-medium mt-2')
                choices = ui.select({}, label='Grupos e canais da minha conta', with_input=True).props('outlined dense').classes('w-full')
                choices.disable()
                dialogs_feedback = ui.label('Carregue os grupos para escolher uma nova fonte.').classes('muted text-sm')
                account_actions = ui.row().classes('gap-2')
                ui.separator().classes('my-3')
                ui.label('Por link ou ID').classes('font-medium')
                source_name = ui.input('Nome da fonte').props('outlined dense').classes('w-full')
                source_ref = ui.input('@nome, link público ou ID', placeholder='@ofertasadrenaline').props('outlined dense').classes('w-full')

            async def add_source():
                source_name.error = None if (source_name.value or '').strip() else 'Informe um nome para esta fonte.'
                source_ref.error = None if (source_ref.value or '').strip() else 'Informe o link, @nome ou ID do grupo.'
                if source_name.error or source_ref.error or source_work['saving']:
                    if source_name.error or source_ref.error:
                        (source_name if source_name.error else source_ref).run_method('focus')
                    return
                source_work['saving'] = True
                add_source_button.disable()
                add_selected_button.disable()
                add_source_button.props('loading')
                try:
                    store.save_source(source_name.value or '', source_ref.value or '')
                    source_name.value = source_ref.value = ''
                    await monitor.sync_sources()
                    source_list.refresh()
                    update_group_choices([dict(id=peer_id, name=name) for peer_id, name in choices.options.items()])
                    add_source_expansion.close()
                    ui.notify('Fonte cadastrada. Ao conectar, o app acompanhará mensagens novas.', type='positive')
                except ValueError as exc:
                    source_ref.error = str(exc)
                    source_ref.run_method('focus')
                    ui.notify(str(exc), type='negative')
                finally:
                    source_work['saving'] = False
                    add_source_button.enable()
                    add_source_button.props(remove='loading')
            with add_source_expansion:
                add_source_button = ui.button('Adicionar fonte', on_click=add_source)

            def update_group_choices(available):
                choices.options = new_dialog_choices(store.sources(), available)
                choices.value = None
                choices.update()
                choices.set_enabled(bool(choices.options) and not source_work['loading'])
                dialogs_feedback.text = f'{len(choices.options)} grupos ou canais disponíveis para adicionar.' if choices.options else 'Nenhum novo grupo encontrado. As fontes cadastradas já estão na lista abaixo.'

            async def load_dialogs():
                if not monitor.client or not monitor.client.is_connected():
                    ui.notify('Conecte o Telegram primeiro, na aba Telegram.', type='warning')
                    return
                available = []
                from telethon import utils
                source_work['loading'] = True
                load_groups_button.disable()
                load_groups_button.props('loading')
                choices.disable()
                dialogs_feedback.text = 'Carregando grupos da sua conta…'
                try:
                    async for dialog in monitor.client.iter_dialogs(limit=200):
                        peer_id = str(utils.get_peer_id(dialog.entity))
                        if dialog.is_group or dialog.is_channel:
                            available.append(dict(id=peer_id, name=dialog.name))
                    update_group_choices(available)
                except Exception:
                    dialogs_feedback.text = 'Não foi possível carregar os grupos. Confira a conexão e tente novamente.'
                    ui.notify('Não foi possível listar os grupos agora. Tente novamente depois.', type='negative')
                finally:
                    source_work['loading'] = False
                    load_groups_button.enable()
                    load_groups_button.props(remove='loading')
                    choices.set_enabled(bool(choices.options))

            async def select_dialog():
                if not choices.value:
                    ui.notify('Escolha um grupo ou canal.')
                    return
                source_name.value = choices.options[choices.value]
                source_ref.value = choices.value
                await add_source()
            with account_actions:
                load_groups_button = ui.button('Carregar meus grupos', on_click=load_dialogs).props('outline')
                add_selected_button = ui.button('Adicionar grupo selecionado', on_click=select_dialog).props('outline')
                add_selected_button.disable()
            choices.on_value_change(lambda event: add_selected_button.set_enabled(bool(event.value) and not source_work['saving']))

            async def source_toggle(event, source):
                store.toggle('sources', source['id'], event.value)
                if event.value:
                    from core import utcnow
                    store.db.execute('UPDATE sources SET baseline=? WHERE id=?', (utcnow(), source['id']))
                    store.db.commit()
                await monitor.sync_sources()
                source_list.refresh()

            def source_remove(source, trigger):
                with ui.dialog().props('no-refocus') as dialog, ui.card():
                    dialog.props['aria-label'] = 'Remover ' + source['name']
                    ui.label('Remover ' + source['name'] + '?').classes('section-title').props('role=heading aria-level=2')
                    ui.label('O monitor deixará de acompanhar este grupo. As ofertas recebidas continuarão salvas.')
                    async def confirm():
                        store.delete('sources', source['id'])
                        await monitor.sync_sources()
                        source_list.refresh()
                        dialog.close()
                    with ui.row():
                        ui.button('Cancelar', on_click=dialog.close).props('flat')
                        ui.button('Remover fonte', on_click=confirm, color='negative')
                dialog.on('hide', lambda: restore_button_focus(trigger, source_search))
                dialog.open()

            @ui.refreshable
            def source_list():
                source_labels.clear()
                all_sources = store.sources()
                selected = filter_sources(all_sources, source_search.value or '')
                filtered = bool((source_search.value or '').strip())
                source_clear.set_visibility(filtered)
                source_summary.text = f'{len(selected)} de {len(all_sources)} fontes' if filtered else f'{len(all_sources)} fontes cadastradas · {sum(bool(row["enabled"]) for row in all_sources)} ativas'
                if not selected:
                    ui.label('Nenhuma fonte corresponde à busca. Use Limpar busca para ver os grupos cadastrados.' if filtered else 'Nenhum grupo selecionado. Use Adicionar grupo ou canal para começar a receber ofertas novas.').classes('muted py-4')
                for source in selected:
                    with ui.column().classes('w-full source-row gap-2') as source_row:
                        source_row.props['role'] = 'group'
                        source_row.props['aria-label'] = source['name']
                        with ui.column().classes('gap-1'):
                            ui.label(source['name']).classes('source-name')
                            ui.label(source['reference']).classes('muted text-sm')
                            source_labels[source['id']] = ui.label(monitor.source_status.get(source['id'], 'Será verificada ao conectar o Telegram')).classes('source-state')
                        with ui.row().classes('w-full items-center justify-between gap-2'):
                            follow = ui.switch('Acompanhar', value=bool(source['enabled']), on_change=lambda event, s=source: source_toggle(event, s))
                            follow.props['aria-label'] = 'Acompanhar ' + source['name']
                            remove = ui.button('Remover', icon='delete_outline', on_click=lambda event, s=source: source_remove(s, event.sender)).props('flat color=negative dense')
                            remove.props['aria-label'] = 'Remover ' + source['name']
            source_labels = {}
            with telegram_panel:
                source_list()
            source_search.on_value_change(source_list.refresh)
            with shops_panel:
                ui.label('Consultas das lojas').classes('form-title').props('role=heading aria-level=2')
                ui.label('Demais lojas a cada 10 minutos; Mercado Livre por último, a cada 30 minutos. Consultar lojas agora antecipa a consulta.').classes('muted text-sm mb-2')
                settings_shop_states = {}
                shop_rows = {}
                for name in SHOP_NAMES:
                    with ui.element('div').classes('store-row') as shop_row:
                        shop_rows[name] = shop_row
                        shop_row.props['role'] = 'group'
                        shop_row.props['aria-label'] = name
                        ui.switch(name, value=store.get_setting('shop:' + name, '1') == '1',
                                  on_change=lambda event, n=name: store.set_setting('shop:' + n, '1' if event.value else '0'))
                        settings_shop_states[name] = ui.label('').classes('offer-status')
                ml_session_section = ui.expansion('Sessão do Mercado Livre', icon='account_circle', value=monitor.shops.ml_browser.login_open).classes('w-full mt-4')
            with ml_session_section:
                with ui.column().classes('gap-1 session-help'):
                    ui.label('1. Abra a janela do Chrome e entre na sua conta.')
                    ui.label('2. Feche as janelas do Chrome do Mercado Livre.')
                    ui.label('3. Clique em Confirmar sessão para testar a busca.')
                    ui.label('Se a consulta sem janela for bloqueada, o app usará uma janela própria do Chrome. Pode minimizá-la; deixe-a aberta durante as consultas.')
                ui.label('Seu Chrome pessoal pode continuar aberto. A sessão fica salva somente neste PC.').classes('muted text-xs mt-3')
                ml_session_status = ui.label(monitor.shops.ml_browser.status).classes('session-state')
                ml_actions = ui.row().classes('gap-2')
            ml_work = {'busy': False}

            async def open_ml_session():
                if ml_work['busy']:
                    return
                ml_work['busy'] = True
                ml_open_button.disable()
                ml_confirm_button.disable()
                ml_open_button.props('loading')
                try:
                    await monitor.shops.ml_browser.open_login()
                    ui.notify('Entre no Mercado Livre, feche a janela do Chrome do monitor e depois clique Confirmar sessão.', type='info')
                except ValueError as exc:
                    ui.notify(str(exc), type='negative')
                finally:
                    ml_work['busy'] = False
                    ml_open_button.enable()
                    ml_confirm_button.enable()
                    ml_open_button.props(remove='loading')

            async def confirm_ml_session():
                component = next((part for part in store.components() if part['enabled']), None)
                if not component:
                    ui.notify('Ative uma peça para testar a consulta.', type='warning')
                    return
                if ml_work['busy']:
                    return
                ml_work['busy'] = True
                ml_open_button.disable()
                ml_confirm_button.disable()
                ml_confirm_button.props('loading')
                try:
                    await monitor.shops.ml_browser.confirm(component)
                    monitor.shop_status['Mercado Livre'] = 'Sessão salva · aguardando consulta'
                    ui.notify('Sessão salva. As consultas usarão esse perfil do Chrome, com janela quando necessário.', type='positive')
                    asyncio.create_task(monitor.scan_shops(force_ml=True))
                except ValueError as exc:
                    ui.notify(str(exc), type='warning')
                finally:
                    ml_work['busy'] = False
                    ml_open_button.enable()
                    ml_confirm_button.enable()
                    ml_confirm_button.props(remove='loading')

            with ml_actions:
                ml_open_button = ui.button('Abrir sessão do Mercado Livre', icon='open_in_new', on_click=open_ml_session).props('outline')
                ml_confirm_button = ui.button('Confirmar sessão', on_click=confirm_ml_session)
                ml_confirm_button.props['aria-label'] = 'Confirmar sessão do Mercado Livre'

            shopee_work = {'busy': False}

            async def shopee_session(confirm=False):
                if shopee_work['busy']:
                    return
                shopee_work['busy'] = True
                shopee_open.disable()
                shopee_confirm.disable()
                action = shopee_confirm if confirm else shopee_open
                action.props('loading')
                try:
                    if confirm:
                        component = next((part for part in store.components() if part['enabled']), None)
                        if not component:
                            ui.notify('Ative uma peça para testar a consulta.', type='warning')
                            return
                        await monitor.shops.shopee_browser.confirm(component)
                        monitor.shop_status['Shopee'] = 'Sessão salva · aguardando consulta'
                        ui.notify('Sessão Shopee salva. O Chrome próprio ficará aberto durante as consultas.', type='positive')
                    else:
                        await monitor.shops.shopee_browser.open_login()
                        ui.notify('Entre na Shopee, feche essa janela e clique Confirmar sessão da Shopee.', type='info')
                except (ValueError, OSError) as exc:
                    ui.notify(str(exc) if isinstance(exc, ValueError) else 'Não foi possível abrir o Chrome da Shopee.', type='warning')
                finally:
                    shopee_work['busy'] = False
                    shopee_open.enable()
                    shopee_confirm.enable()
                    action.props(remove='loading')

            with shops_panel:
                shopee_session_section = ui.expansion('Sessão da Shopee', icon='account_circle', value=monitor.shops.shopee_browser.login_open).classes('w-full mt-4')
            with shopee_session_section:
                ui.label('Abra o Chrome próprio, entre na Shopee, feche essa janela e confirme a sessão. As consultas precisam do login e usam uma janela que pode ficar minimizada.').classes('muted text-sm')
                ui.label('Sessão salva somente neste PC; seu Chrome pessoal e o perfil do Mercado Livre permanecem separados.').classes('muted text-xs')
                shopee_session_status = ui.label(monitor.shops.shopee_browser.status).classes('session-state')
                with ui.row().classes('gap-2'):
                    shopee_open = ui.button('Abrir sessão da Shopee', icon='open_in_new', on_click=lambda: shopee_session()).props('outline')
                    shopee_confirm = ui.button('Confirmar sessão da Shopee', on_click=lambda: shopee_session(True))

            def go_to_shop(name):
                tabs.set_value(sources_tab)
                target = shop_rows[name]
                if name == 'Mercado Livre':
                    target = ml_session_section
                    ml_session_section.open()
                elif name == 'Shopee':
                    target = shopee_session_section
                    shopee_session_section.open()
                with shops_panel:
                    ui.run_javascript('''
                        await new Promise(resolve => requestAnimationFrame(resolve));
                        const section = document.getElementById(''' + json.dumps(target.html_id) + ''');
                        section?.scrollIntoView({block:'center'});
                        section?.querySelector('[tabindex="0"]')?.focus({preventScroll:true});
                    ''')

        with ui.tab_panel(coupons_tab):
            ui.label('Cupons do Mercado Livre').classes('section-title').props('role=heading aria-level=2')
            ui.label('Somente cupons encontrados hoje, no horário de São Paulo. Registros anteriores são apagados. Aplicação e retentativas recuperáveis a cada hora; ativados e desativados não são reenviados. Ativado significa adicionado à conta, sujeito às condições do anúncio.').classes('muted max-w-3xl')
            with ui.column().classes('settings-panel mt-4 gap-3'):
                ml_coupon_status = ui.label(monitor.ml_coupons.status).classes('text-sm').props('role=status aria-live=polite')
                ml_state = {'rows': None, 'page': 1, 'busy': None}

                async def apply_ml_coupons(retry_only=False, code=None):
                    ml_coupon_button.disable()
                    ml_retry_button.disable()
                    if code:
                        ml_search.run_method('focus')
                    try:
                        await monitor.ml_coupons.run(retry_only=retry_only, code=code)
                        ml_coupon_status.text = monitor.ml_coupons.status
                    finally:
                        render_ml_coupons()

                with ui.row().classes('items-center gap-3'):
                    ml_coupon_button = ui.button('Aplicar cupons agora', icon='local_offer', on_click=lambda: apply_ml_coupons()).props('outline')
                    ml_retry_button = ui.button('Retentar falhas', icon='replay', on_click=lambda: apply_ml_coupons(True)).props('outline')
                    ml_retry_count = ui.label('').classes('muted text-sm')
                with ui.row().classes('w-full gap-3 items-start'):
                    ml_filter = ui.select({'': 'Todos', **GROUPS}, value='', label='Estado dos códigos').props('outlined dense').classes('w-64')
                    ml_failure_filter = ui.select({'': 'Todas as falhas', 'retry': 'Podem retentar', 'terminal': 'Sem retentativa'}, value='', label='Tipo de falha').props('outlined dense').classes('w-56')
                    ml_search = ui.input('Buscar código ou resposta', placeholder='Código, fonte ou motivo').props('outlined dense clearable').classes('flex-1')
                ml_summary = ui.label('').classes('muted text-sm').props('role=status aria-live=polite')
                ml_list = ui.column().classes('w-full gap-0')
                with ui.row().classes('w-full justify-between items-center') as ml_pager:
                    ml_range = ui.label('').classes('muted text-sm')
                    with ui.row().classes('gap-2'):
                        ml_previous = ui.button('Anterior', on_click=lambda: change_ml_page(-1)).props('outline')
                        ml_next = ui.button('Próxima', on_click=lambda: change_ml_page(1)).props('outline')
                        ml_previous.props['aria-label'] = 'Página anterior dos códigos do Mercado Livre'
                        ml_next.props['aria-label'] = 'Próxima página dos códigos do Mercado Livre'

                def toggle_ml_coupon(code, disabled):
                    monitor.ml_coupons.set_disabled(code, disabled)
                    render_ml_coupons()
                    ml_search.run_method('focus')
                    with ml_list:
                        ui.notify(('Desativado: ' if disabled else 'Reativado: ') + code)

                def render_ml_coupons():
                    rows = monitor.ml_coupons.catalog()
                    busy = monitor.ml_coupons.lock.locked()
                    ml_state.update(rows=rows, busy=busy)
                    counts = {key: sum(row['group'] == key for row in rows) for key in GROUPS}
                    ml_filter.set_options({'': f'Todos ({len(rows)})', **{key: f'{label} ({counts[key]})' for key, label in GROUPS.items()}}, value=ml_filter.value)
                    ml_failure_filter.set_enabled(ml_filter.value in ('', 'failed'))
                    recoverable = sum(row['retryable'] for row in rows)
                    ml_coupon_button.set_enabled(not busy and any(row['status'] == 'new' and not row['disabled'] or row['retryable'] for row in rows))
                    ml_retry_button.set_enabled(not busy and bool(recoverable))
                    ml_retry_count.text = f'{recoverable} falha(s) recuperável(is) de hoje · desativados não são enviados'
                    needle = (ml_search.value or '').casefold().strip()
                    matches = [row for row in rows if (not ml_filter.value or row['group'] == ml_filter.value)
                        and (not ml_failure_filter.value or row['group'] == 'failed' and row['retryable'] == (ml_failure_filter.value == 'retry'))
                        and (not needle or needle in ' '.join(str(row.get(key) or '') for key in ('code', 'source', 'detail', 'failure')).casefold())]
                    total = len(matches)
                    ml_state['page'] = min(ml_state['page'], max(1, (total + 9) // 10))
                    page = ml_state['page']
                    ml_summary.text = f'{total} de {len(rows)} códigos · estado e última resposta salvos neste PC'
                    ml_pager.set_visibility(total > 10)
                    ml_previous.set_enabled(page > 1)
                    ml_next.set_enabled(page * 10 < total)
                    ml_range.text = f'{(page - 1) * 10 + 1}–{min(page * 10, total)} de {total}'
                    ml_list.clear()
                    with ml_list:
                        if not matches:
                            ui.label('Nenhum código neste filtro. Altere o estado ou limpe a busca.' if rows else
                                     'Ainda não há códigos do Mercado Livre. Novas publicações aparecerão aqui.').classes('muted py-4')
                        for row in matches[(page - 1) * 10:page * 10]:
                            with ui.element('article').classes('coupon-manager-row') as article:
                                article.props['aria-label'] = row['code'] + ' · ' + GROUPS[row['group']]
                                with ui.column().classes('gap-2 min-w-0'):
                                    with ui.row().classes('items-center gap-3'):
                                        ui.label(row['code']).classes('coupon-code').props('role=heading aria-level=3 tabindex=-1')
                                        ui.label(row['label']).classes('offer-status ' + ('verified' if row['group'] == 'active' else 'unavailable' if row['group'] == 'failed' and not row['retryable'] else ''))
                                        if row['failure']:
                                            ui.label(row['failure']).classes('text-sm font-semibold')
                                    if row['detail']:
                                        ui.label(row['detail']).classes('coupon-manager-detail')
                                    ui.label(row['guidance']).classes('muted text-sm')
                                    ui.label(f'Fonte: {row["source"]} · encontrado: {local_time(row["found_at"])} · {row["attempts"]} tentativa(s) · última: {local_time(row["attempted_at"])}').classes('muted text-xs')
                                with ui.element('div').classes('coupon-manager-actions'):
                                    if row['retryable']:
                                        retry = ui.button('Retentar', icon='replay', on_click=lambda c=row['code']: apply_ml_coupons(True, c)).props('outline dense')
                                        retry.props['aria-label'] = 'Retentar cupom ' + row['code']
                                        retry.set_enabled(not busy)
                                    toggle = ui.button('Reativar' if row['disabled'] else 'Desativar', on_click=lambda c=row['code'], d=not row['disabled']: toggle_ml_coupon(c, d)).props('flat dense')
                                    toggle.props['aria-label'] = ('Reativar cupom ' if row['disabled'] else 'Desativar cupom ') + row['code']
                                    toggle.set_enabled(row['code'] != monitor.ml_coupons.current_code)

                def change_ml_page(delta):
                    ml_state['page'] += delta
                    render_ml_coupons()
                    with ml_list:
                        ui.run_javascript('''
                            await new Promise(resolve => requestAnimationFrame(resolve));
                            const heading = document.getElementById(''' + json.dumps(ml_list.html_id) + ''')?.querySelector('[role="heading"]');
                            if (heading) {
                                heading.scrollIntoView({block:'center'});
                                heading.focus({preventScroll:true});
                            }
                        ''')

                def filter_ml_coupons():
                    ml_state['page'] = 1
                    if ml_filter.value not in ('', 'failed'):
                        ml_failure_filter.value = ''
                    render_ml_coupons()

                ml_filter.on_value_change(filter_ml_coupons)
                ml_failure_filter.on_value_change(filter_ml_coupons)
                ml_search.on_value_change(filter_ml_coupons)
                render_ml_coupons()
            ui.label('Publicações de hoje e condições de todas as lojas').classes('section-title mt-6').props('role=heading aria-level=2')
            ui.label('Mensagens originais dos grupos e sites públicos. A publicação não confirma ativação nem desconto; códigos do Mercado Livre têm o acompanhamento acima.').classes('muted')
            with ui.row().classes('w-full items-start gap-4 mt-4'):
                coupon_search = ui.input('Buscar cupons', placeholder='Código, fonte ou condição').props('outlined dense clearable').classes('w-96 max-w-full')
                coupon_shop_filter = ui.select(coupon_shop_options([]), value='', label='Loja dos cupons').props('outlined dense hint="Publicações por loja, antes da busca"').classes('w-72')
                coupon_clear = ui.button('Limpar filtros', icon='filter_alt_off', on_click=lambda: clear_coupon_filters()).props('flat')
            coupon_source_status = ui.label(monitor.coupon_status).classes('muted text-sm')
            coupon_summary = ui.label('').classes('muted text-sm').props('role=status aria-live=polite aria-atomic=true')
            with ui.row().classes('undo-offer') as coupon_updates:
                coupon_notice = ui.label('').classes('text-sm').props('role=status aria-live=polite aria-atomic=true')
                ui.button('Atualizar lista', on_click=lambda: apply_coupon_updates()).props('outline dense')
            coupon_updates.set_visibility(False)
            coupon_empty = ui.label('Nenhum cupom encontrado ainda.').classes('muted my-4')
            coupon_list = ui.column().classes('coupon-list')
            with ui.row().classes('w-full items-center justify-between mt-4') as coupon_pager:
                coupon_range = ui.label('').classes('muted text-sm').props('role=status aria-live=polite aria-atomic=true')
                with ui.row().classes('gap-2'):
                    coupon_previous = ui.button('Anterior', on_click=lambda: change_coupon_page(-1)).props('outline')
                    coupon_next = ui.button('Próxima', on_click=lambda: change_coupon_page(1)).props('outline')
                    coupon_previous.props['aria-label'] = 'Página anterior de cupons'
                    coupon_next.props['aria-label'] = 'Próxima página de cupons'
            coupon_state = {'rows': [], 'page': 1, 'expanded': set(), 'options': None, 'pending': None}

            async def copy_coupon(code):
                copied = await ui.run_javascript('navigator.clipboard ? navigator.clipboard.writeText(' + json.dumps(code) + ').then(() => true).catch(() => false) : false')
                ui.notify('Código copiado: ' + code if copied else 'Não foi possível copiar. Selecione o código e use Ctrl+C.', type='positive' if copied else 'warning')

            def render_coupons():
                query = coupon_search.value or ''
                options = coupon_shop_options(coupon_state['rows'])
                if options != coupon_state['options']:
                    coupon_state['options'] = options
                    coupon_shop_filter.set_options(options, value=coupon_shop_filter.value)
                rows, total, current = coupon_page(coupon_state['rows'], query, coupon_state['page'], coupon_shop_filter.value or '')
                coupon_state['page'] = current
                filtered = bool(query.strip() or coupon_shop_filter.value)
                coupon_clear.set_visibility(filtered)
                coupon_summary.text = f'{total} de {len(coupon_state["rows"])} publicações · filtros ativos' if filtered else f'{total} publicações de cupons · descontos não validados'
                coupon_empty.text = 'Nenhum cupom corresponde aos filtros. Use Limpar filtros para ver todas as publicações.' if filtered else 'Nenhum cupom encontrado ainda. Novas publicações aparecerão aqui.'
                coupon_empty.set_visibility(not total)
                coupon_pager.set_visibility(total > 10)
                coupon_previous.set_enabled(current > 1)
                coupon_next.set_enabled(current * 10 < total)
                coupon_range.text = f'{(current - 1) * 10 + 1}–{min(current * 10, total)} de {total} publicações'
                coupon_state['expanded'].intersection_update(row['key'] for row in coupon_state['rows'])
                coupon_list.clear()
                with coupon_list:
                    for row in rows:
                        with ui.element('article').classes('coupon-row') as coupon_article:
                            coupon_article.props['aria-label'] = row['shop'] + ' · ' + row['source'] + ' · ' + row['time']
                            coupon_article.props['data-coupon-key'] = row['key']
                            with ui.row().classes('w-full items-center justify-between gap-2'):
                                ui.label(row['shop']).classes('offer-shop').props('role=heading aria-level=3 tabindex=-1')
                                ui.label(row['time']).classes('muted text-xs')
                            ui.label('Fonte: ' + row['source'] + ' · aplicabilidade não confirmada').classes('muted text-sm')
                            with ui.row().classes('items-center gap-3'):
                                for code in filter(None, row['codes'].split(', ')):
                                    ui.label(code).classes('coupon-code')
                                    copy = ui.button('Copiar', icon='content_copy', on_click=lambda c=code: copy_coupon(c)).props('flat dense')
                                    copy.props['aria-label'] = 'Copiar ' + code + ' · ' + row['shop'] + ' · ' + row['source']
                                if row['activation']:
                                    ui.label('Ativar no link · sem código').classes('text-sm')
                                if row['url'] and valid_url(row['url']):
                                    ui.link('Abrir link' if row['shop'] == 'Loja não identificada' else 'Abrir na loja', row['url'], new_tab=True).classes('text-sm')
                                if row['source_url'] and valid_url(row['source_url']):
                                    ui.link('Ver publicação', row['source_url'], new_tab=True).classes('text-sm')
                            with ui.expansion('Condições e mensagem', value=row['key'] in coupon_state['expanded'],
                                on_value_change=lambda event, key=row['key']: coupon_state['expanded'].add(key) if event.value else coupon_state['expanded'].discard(key)).classes('w-full'):
                                ui.label(row['conditions'] or 'Condições não informadas na publicação.').classes('detail-message')

            def focus_coupon_page():
                with coupon_list:
                    ui.run_javascript('''
                        await new Promise(resolve => requestAnimationFrame(resolve));
                        const article = document.getElementById(''' + json.dumps(coupon_list.html_id) + ''')?.querySelector('article');
                        if (article && article.getClientRects().length) {
                            article.scrollIntoView({block:'start'});
                            article.querySelector('[role="heading"]')?.focus({preventScroll:true});
                        } else {
                            document.getElementById(''' + json.dumps(coupon_search.html_id) + ''')?.querySelector('input')?.focus();
                        }
                    ''')

            def update_coupon_rows(latest):
                # A virada do dia apaga também publicações com condições abertas.
                if any(not coupon_is_today(row['found_at']) for row in coupon_state['rows']):
                    coupon_state['pending'] = None
                    coupon_state['rows'] = latest
                    coupon_updates.set_visibility(False)
                    render_coupons()
                    return
                visible, _, _ = coupon_page(coupon_state['rows'], coupon_search.value or '', coupon_state['page'], coupon_shop_filter.value or '')
                notice = coupon_refresh_notice(coupon_state['rows'], latest, visible, coupon_state['expanded'])
                if latest != coupon_state['rows'] and (notice or coupon_state['pending'] is not None):
                    coupon_state['pending'] = latest
                    coupon_notice.text = notice or 'Atualização da lista disponível · escolha quando carregar.'
                    coupon_updates.set_visibility(True)
                    return
                coupon_state['pending'] = None
                coupon_updates.set_visibility(False)
                if latest != coupon_state['rows']:
                    coupon_state['rows'] = latest
                    render_coupons()

            def apply_coupon_updates(focus=True):
                if coupon_state['pending'] is not None:
                    coupon_state['rows'] = coupon_state['pending']
                    coupon_state['pending'] = None
                    coupon_updates.set_visibility(False)
                    if focus:
                        render_coupons()
                        focus_coupon_page()

            def change_coupon_page(delta):
                apply_coupon_updates(False)
                coupon_state['page'] += delta
                render_coupons()
                focus_coupon_page()

            def search_coupons():
                apply_coupon_updates(False)
                coupon_state['page'] = 1
                render_coupons()

            def clear_coupon_filters():
                coupon_search.value = ''
                coupon_shop_filter.value = ''
                search_coupons()
                coupon_search.run_method('focus')
            coupon_search.on_value_change(search_coupons)
            coupon_shop_filter.on_value_change(search_coupons)
            render_coupons()

        with ui.tab_panel(telegram_tab):
            ui.label('Telegram e notificações').classes('section-title').props('role=heading aria-level=2')
            with ui.column().classes('settings-panel gap-3 mt-4'):
                with ui.row().classes('w-full items-center justify-between'):
                    ui.label('Conexão do Telegram').classes('form-title mb-0').props('role=heading aria-level=2')
                    telegram_connection = ui.label('').classes('offer-status')
                telegram_description = ui.label('').classes('muted')
                telegram_activity = ui.label('').classes('muted text-sm')
                ui.button('Gerenciar grupos', icon='forum', on_click=lambda: tabs.set_value(sources_tab)).props('outline')
                connection_help = ui.expansion('Como conectar ou trocar a conta', value=not bool(monitor.client and monitor.client.is_connected())).classes('w-full')
                telegram_connection_state = {'connected': None}
                with connection_help:
                    ui.label('A autenticação acontece em um terminal local. A sessão fica neste PC; os códigos não passam pelo painel.').classes('muted max-w-3xl')
                    ui.label('1. Clique em Encerrar no topo do painel para parar o monitor.').classes('mt-2')
                    ui.label('2. Abra Conectar-Telegram.cmd na pasta do projeto e siga as instruções.')
                    ui.label('3. Abra Iniciar-Monitor.cmd e selecione seus grupos na aba Fontes.')
                    ui.link('Obter API ID e API hash no Telegram', 'https://my.telegram.org', new_tab=True)
                    ui.label(str(ROOT / 'Conectar-Telegram.cmd')).classes('muted text-sm break-all')
                    ui.label('A sessão concede acesso à sua conta. Mantenha a pasta data privada.').classes('muted mt-2')
                ui.label('Mensagens novas são acompanhadas em tempo real. Ao retomar a conexão, só entram mensagens dos últimos 5 minutos; ofertas precisam corresponder às peças cadastradas.').classes('muted text-sm')
            with ui.column().classes('settings-panel gap-3 mt-4') as notification_panel:
                ui.label('Avisos no Windows').classes('form-title mb-0').props('role=heading aria-level=2')
                ui.label('Avisos explicam por que a oferta entrou nos 10% mais baratos. Repetições do mesmo modelo, loja e vendedor só avisam após queda de pelo menos 2%, no mesmo pagamento e respeitando seu limite. Se a confirmação esclarecer o pagamento, essa primeira leitura vira a referência sem repetir o aviso. Teste a exibição no seu desktop.').classes('muted text-sm')
                notification_state = ui.label(monitor.notification_status).classes('text-sm')
            async def test_toast():
                test_toast_button.disable()
                test_toast_button.props('loading')
                try:
                    accepted = await monitor.test_notification()
                    notification_state.text = monitor.notification_status
                    ui.notify('Pedido enviado ao Windows. Confira se o aviso apareceu.' if accepted else 'O Windows recusou o aviso de teste.',
                              type='positive' if accepted else 'negative')
                finally:
                    test_toast_button.enable()
                    test_toast_button.props(remove='loading')
            with notification_panel:
                test_toast_button = ui.button('Testar aviso no Windows', on_click=test_toast).props('outline')

    last_rows = {'offers': None, 'coupons': None, 'parts': None, 'filters': None, 'history': None}

    def refresh():
        ml_session_status.text = monitor.shops.ml_browser.status
        shopee_session_status.text = monitor.shops.shopee_browser.status
        telegram_status.text = 'Telegram conectado' if monitor.telegram_status.startswith('Conectado') else monitor.telegram_status
        connected = bool(monitor.client and monitor.client.is_connected())
        telegram_status.classes(remove='verified pending', add='verified' if connected else 'pending')
        if telegram_connection_state['connected'] != connected:
            connection_help.set_value(not connected)
            telegram_connection_state['connected'] = connected
        telegram_connection.text = 'Conectado' if connected else 'Conexão pendente'
        telegram_connection.classes(remove='verified pending', add='verified' if connected else 'pending')
        active_sources = sum(bool(source['enabled']) for source in store.sources())
        telegram_description.text = (f'{active_sources} fontes selecionadas para acompanhar novas mensagens.' if connected else monitor.telegram_status)
        telegram_activity.text = 'Última mensagem recebida: ' + local_time(monitor.last_received) if monitor.last_received else 'Aguardando mensagens novas das fontes selecionadas.'
        sources_connection.text = 'Conectado' if connected else 'Conexão pendente'
        sources_connection.classes(remove='verified pending', add='verified' if connected else 'pending')
        load_groups_button.set_enabled(connected and not source_work['loading'])
        add_selected_button.set_enabled(bool(choices.value) and not source_work['loading'] and not source_work['saving'])
        last_event.text = ('Última mensagem: ' + local_time(monitor.last_received) +
                           (f' · atraso de recebimento: {monitor.last_delay:.1f}s' if monitor.last_delay is not None else '')
                           if monitor.last_received else 'Aguardando mensagens novas das fontes selecionadas.')
        for name, label in shop_labels.items():
            status = (monitor.shops.ml_browser.status if name == 'Mercado Livre' and monitor.shops.ml_browser.login_open
                      else monitor.shops.shopee_browser.status if name == 'Shopee' and monitor.shops.shopee_browser.login_open
                      else monitor.shop_status[name])
            label.text = name + ': ' + status
            short, tone = shop_state(status)
            shop_indicators[name].text = name + ' · ' + short
            shop_indicators[name].classes(remove='verified pending announced neutral', add=tone)
            settings_shop_states[name].text = short
            settings_shop_states[name].classes(remove='verified pending announced neutral', add=tone)
        for browser, section, name in [(monitor.shops.ml_browser, ml_session_section, 'Mercado Livre'),
                                       (monitor.shops.shopee_browser, shopee_session_section, 'Shopee')]:
            profile = 'Confirmação pendente' if browser.login_open else 'Perfil salvo neste PC' if browser.configured else 'Login necessário'
            section.props['caption'] = profile + ' · ' + settings_shop_states[name].text
        scanning = monitor.shop_lock.locked()
        scan_activity.text = ('Consulta em andamento desde ' + local_time(monitor.last_shop_scan_started)
                              if scanning else 'Último ciclo concluído: ' + local_time(monitor.last_shop_scan_finished)
                              if monitor.last_shop_scan_finished else 'Aguardando primeira consulta das lojas')
        scan_activity.text += ' · até 12 mais baratas por peça · demais lojas: 10 min · Mercado Livre: 30 min'
        scan_part_name = next((part['name'] for part in store.components() if part['id'] == monitor.shop_scan_component_id), None)
        if scan_part_name:
            scan_activity.text = (f'Atualizando {scan_part_name} desde ' + local_time(monitor.last_shop_scan_started) if scanning
                                  else f'Última consulta de {scan_part_name}: ' + local_time(monitor.last_shop_scan_finished)
                                  if monitor.last_shop_scan_finished else f'Consulta de {scan_part_name} interrompida')
        scan_button.set_enabled(not scanning)
        scan_button.text = 'Consultando lojas…' if scanning else 'Consultar lojas agora'
        for source_id, label in source_labels.items():
            label.text = monitor.source_status.get(source_id, 'Será verificada ao conectar o Telegram')
        rows = [dict(row, price_current=price_is_current(row)) for row in store.offers()]
        parts = store.components()
        parts_summary.text = f"{len(parts)} peças cadastradas · {sum(bool(part['enabled']) for part in parts)} com monitoramento ativo"
        active_part = next((part for part in parts if part['id'] == monitor.shop_scan_component_id), None)
        for part in parts:
            if part['id'] in group_widgets:
                button = group_widgets[part['id']]['scan']
                updating = scanning and monitor.shop_scan_component_id == part['id']
                button.set_enabled(not scanning and bool(part['enabled']))
                button.text = 'Atualizando…' if updating else 'Atualizar peça'
                group_widgets[part['id']]['activity'].text = piece_scan_activity(part, active_part, monitor.shop_status, scanning)
                button.props('loading' if updating else 'loading=false')
        part_options = {0: 'Todas as peças', **{part['id']: part['name'] for part in parts}}
        if part_filter.options != part_options:
            part_filter.options = part_options
            if part_filter.value not in part_options:
                part_filter.value = 0
            part_filter.update()
        filters = ((search.value or '').strip(), shop_filter.value or '', state_filter.value or '', part_filter.value or 0, selection_filter.value or '')
        selected = selected_comparison(rows, parts)
        comparison['ids'] = [row['id'] for row in selected]
        comparison_changed = comparison['rows'] != selected
        if comparison_changed:
            render_comparison(selected)
            comparison['rows'] = selected
        selection_help.text = {'favorite': 'Até 12 favoritas salvas por peça, incluindo anúncios fora do catálogo ou indisponíveis. Salvar não muda a prioridade das consultas nem os alertas.',
                               'hidden': 'Anúncios ocultos não aparecem no catálogo, nas consultas automáticas ou nos alertas. Restaure para acompanhá-los novamente; até 12 por peça nesta seleção.'}.get(selection_filter.value, '')
        selection_help.set_visibility(bool(selection_filter.value))
        offers_changed = last_rows['offers'] != rows
        filtering = any(filters[:4])
        clear_filter_button.set_visibility(filtering)
        filters_button.text = 'Filtros' + (f" ({sum(bool(value) for value in filters[1:3])})" if any(filters[1:3]) else '')
        if last_rows['filters'] != filters or last_rows['parts'] != parts:
            chips = offer_filter_chips(*filters[:3], part_options.get(part_filter.value, '') if part_filter.value else '')
            filter_chips.clear()
            filter_chips.set_visibility(bool(chips))
            with filter_chips:
                for chip in chips:
                    field = {'query': search, 'component': part_filter, 'shop': shop_filter, 'state': state_filter}[chip['key']]
                    remove_chip = ui.button(chip['label'], icon='close', on_click=lambda control=field: control.set_value(0 if control is part_filter else '')).props('flat dense no-caps').classes('filter-chip')
                    remove_chip.props['aria-label'] = 'Remover filtro: ' + chip['label']
        if hidden_undo['ids'] and not any(row['id'] in hidden_undo['ids'] and row.get('hidden') for row in rows):
            hidden_undo['ids'] = []
            undo_banner.set_visibility(False)
        parts_changed = last_rows['parts'] != parts
        if parts_changed:
            create_offer_groups(parts)
        if last_rows['offers'] != rows or last_rows['parts'] != parts or last_rows['filters'] != filters or comparison_changed:
            grouped = offer_selection(parts, rows, selection_filter.value or '')
            visible = {part_id: filter_offers(group_rows, *filters[:4]) for part_id, group_rows in grouped.items()}
            total, shown = sum(map(len, grouped.values())), sum(map(len, visible.values()))
            filter_summary.text = catalog_summary(total, shown, filtering, selection_filter.value or '')
            if last_rows['filters'] != filters:
                for widgets in group_widgets.values():
                    widgets['page'] = 1
                first_match = next((part_id for part_id, group_rows in visible.items() if group_rows), None)
                if first_match is not None:
                    open_offer_group(first_match)
            for part_id, group_rows in visible.items():
                widgets = group_widgets[part_id]
                part = next(item for item in parts if item['id'] == part_id)
                widgets['section'].text = f"{part['name']} · {len(group_rows)} {'oferta' if len(group_rows) == 1 else 'ofertas'}"
                widgets['section'].set_visibility(bool(group_rows) or not filtering and not selection_filter.value)
                widgets['section'].props['caption'] = 'Ocultas da lista e dos alertas · histórico preservado' if selection_filter.value == 'hidden' else group_caption(part, group_rows)
                widgets['empty'].text = 'Salve uma oferta usando Salvar no cartão.' if selection_filter.value == 'favorite' else 'Nenhuma oferta oculta nesta peça.' if selection_filter.value == 'hidden' else 'Nenhuma oferta desta peça corresponde aos filtros. Use Limpar filtros para ver todos os anúncios.' if filtering else 'Nenhuma oferta desta peça encontrada. A consulta das lojas e as mensagens novas aparecerão aqui.'
                if not selection_filter.value and not filtering and part.get('target') is not None:
                    widgets['empty'].text = f"Nenhuma oferta com preço {'no Pix' if part['target_payment'] == 'pix' else 'total no cartão'} até {brl(part['target'])}. Ajuste o limite em Peças ou aguarde novas ofertas."
                if widgets['rows'] != group_rows or last_rows['filters'] != filters or comparison_changed:
                    widgets['rows'] = group_rows
                    render_cards(part_id)
                elif not group_rows:
                    widgets['pager'].set_visibility(False)
            empty.text = 'Nenhuma oferta corresponde aos filtros. Limpe os filtros ou tente outra busca.' if filtering else 'Você ainda não salvou ofertas. Abra o catálogo e use Salvar nos cartões.' if selection_filter.value == 'favorite' else 'Nenhuma oferta oculta. O catálogo continua disponível em Mais baratas.' if selection_filter.value == 'hidden' else 'Nenhuma oferta recebida ainda. Conecte o Telegram ou consulte as lojas.'
            if not filtering and not selection_filter.value and any(part.get('target') is not None for part in parts):
                empty.text = 'Nenhuma oferta disponível dentro dos limites configurados. Ajuste o preço máximo em Peças ou aguarde novas ofertas.'
            empty.set_visibility(not shown)
            empty_actions.set_visibility(not shown and bool(filtering or selection_filter.value))
            empty_clear.set_visibility(filtering)
            empty_catalog.set_visibility(bool(selection_filter.value))
            last_rows['offers'] = rows
            last_rows['parts'] = parts
            last_rows['filters'] = filters
        history_key = (store.db.execute('SELECT MAX(id) FROM observations').fetchone()[0], datetime.now().date())
        if parts_changed or last_rows['history'] != history_key or offers_changed:
            for part in parts:
                refresh_history(part['id'])
            last_rows['history'] = history_key
        for widgets in group_widgets.values():
            for label, offer in widgets.get('freshness', []):
                label.text = offer_freshness(offer)
        store.prune_coupons()
        coupon_rows = coupon_catalog(store.rows('SELECT * FROM coupon_posts ORDER BY published_at DESC LIMIT 100'),
                                     json.loads(store.get_setting('pichau_coupons', '[]')), json.loads(store.get_setting('public_coupons', '[]')))
        for row in coupon_rows:
            row['time'] = (('Publicado ' if row['timestamp_kind'] == 'published' else 'Consultado ') + local_time(row['stamp'])) if row['stamp'] else 'Horário não informado'
        coupon_source_status.text = monitor.coupon_status
        ml_coupon_status.text = monitor.ml_coupons.status
        if monitor.ml_coupons.catalog() != ml_state['rows'] or monitor.ml_coupons.lock.locked() != ml_state['busy']:
            render_ml_coupons()
        if coupon_rows != last_rows['coupons']:
            update_coupon_rows(coupon_rows)
            last_rows['coupons'] = coupon_rows
        notification_state.text = monitor.notification_status
    refresh()
    search.on_value_change(refresh)
    shop_filter.on_value_change(refresh)
    state_filter.on_value_change(refresh)
    part_filter.on_value_change(refresh)
    selection_filter.on_value_change(refresh)
    ui.timer(2, refresh)


app.on_startup(monitor.start)
app.on_shutdown(monitor.stop)

if __name__ in {'__main__', '__mp_main__'}:
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(name)s: %(message)s')
    ui.run(host='127.0.0.1', port=8765, title='Monitor de peças', reload=False,
           show=os.environ.get('MONITOR_NO_BROWSER') != '1',
           language='pt-BR', show_welcome_message=True)
