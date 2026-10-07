"""Área de buscas OLX, usando os componentes e estilos do painel existente."""
import asyncio
import json
from datetime import datetime, timezone

from nicegui import ui

from core import brl
from olx import STATES, eligible, search_url


def render_olx(olx):
    def local_time(stamp):
        return datetime.fromisoformat(stamp).astimezone().strftime('%d/%m %H:%M') if stamp else 'Ainda não consultada'

    pages = {}
    snapshot = {'value': None}
    with ui.column().classes('w-full gap-4') as area:
        title = ui.label('Usados na OLX').classes('section-title').props('role=heading aria-level=2 tabindex=-1')
        ui.label('Acompanhe até 50 anúncios recentes por busca a cada dez minutos. A primeira consulta cria uma referência sem enviar avisos.').classes('muted')
        ui.label('A busca pode incluir produtos novos. Conservação, pagamento e frete precisam ser conferidos no anúncio.').classes('muted text-sm')
        with ui.expansion('Adicionar busca', icon='add', value=False).classes('w-full') as form:
            with ui.column().classes('w-full gap-3'):
                mode = ui.toggle({'link': 'Colar busca da OLX', 'fields': 'Produto e cidade'}, value='link').props('no-caps')
                mode.props['aria-label'] = 'Forma de cadastrar busca OLX'
                name = ui.input('Nome da busca', placeholder='Ex.: cadeira para o escritório').props('outlined').classes('w-full')
                url = ui.input('Link da busca na OLX', placeholder='https://www.olx.com.br/...').props('outlined').classes('w-full')
                with ui.row().classes('w-full gap-3 items-start') as fields:
                    query = ui.input('Produto', placeholder='Ex.: cadeira escritório').props('outlined').classes('grow')
                    state = ui.select(STATES, value='SP', label='UF').props('outlined').classes('w-24')
                    city = ui.input('Cidade', placeholder='Ex.: Piracicaba').props('outlined').classes('grow')
                fields.set_visibility(False)
                def set_mode():
                    fields.set_visibility(mode.value == 'fields')
                    url.set_visibility(mode.value == 'link')
                mode.on_value_change(set_mode)
                with ui.row().classes('w-full gap-3'):
                    target = ui.input('Preço máximo (opcional)', placeholder='Ex.: 700,00').props('outlined').classes('grow')
                    excluded = ui.input('Excluir do título (opcional)', placeholder='Ex.: quebrado, peças, conserto').props('outlined').classes('grow')
                ui.label('Separe termos a excluir por vírgula. No cadastro por link, os filtros da OLX são mantidos; a ordenação passa a Mais recentes.').classes('muted text-sm')
                error = ui.label().classes('text-negative').props('role=alert')
                def save():
                    try:
                        olx.save_search(name=name.value, mode=mode.value, url=url.value or '', query=query.value or '',
                                        state=state.value, city=city.value or '', target=target.value or '', excluded=excluded.value or '')
                    except ValueError as exc:
                        error.text = str(exc)
                        return
                    for field in (name, url, query, city, target, excluded):
                        field.value = ''
                    error.text = ''
                    form.value = False
                    refresh(force=True)
                    ui.notify('Busca salva. Consulte agora ou aguarde o próximo ciclo.', type='positive')
                ui.button('Salvar busca', on_click=save).props('no-caps')
        status = ui.label(olx.status).classes('muted').props('role=status')
        container = ui.column().classes('w-full gap-6')
        ui.run_javascript('''
            await new Promise(resolve => requestAnimationFrame(resolve));
            const host = document.getElementById(''' + json.dumps(container.html_id) + ''');
            let focused = null;
            document.addEventListener('focusin', event => {
                const target = event.target.closest('[data-olx-focus]');
                focused = host?.contains(target) ? {element: target, key: target.dataset.olxFocus} : null;
            });
            new MutationObserver(() => {
                if (!focused || focused.element.isConnected || document.activeElement !== document.body) return;
                if (!host?.getClientRects().length) return;
                const target = host.querySelector('[data-olx-focus="' + focused.key + '"]');
                if (target && target.getClientRects().length && !target.disabled) target.focus();
                else document.getElementById(''' + json.dumps(title.html_id) + ''')?.focus();
            }).observe(host, {childList:true, subtree:true});
        ''')

    def restore_focus(key):
        ui.run_javascript('''
            await new Promise(resolve => requestAnimationFrame(resolve));
            const target = document.querySelector('[data-olx-focus="''' + key + '''"]');
            const fallback = document.getElementById(''' + json.dumps(title.html_id) + ''');
            [target, fallback].find(element => element?.getClientRects().length)?.focus();
        ''')

    async def scan(search_id):
        if olx.lock.locked():
            ui.notify('Aguarde a consulta da OLX em andamento.')
            return
        task = asyncio.create_task(olx.scan(search_id))
        # A primeira execução permite que o lock/estado sejam publicados.
        await asyncio.sleep(0)
        refresh(force=True)
        try:
            await task
        finally:
            refresh(force=True)

    async def open_browser(search):
        if olx.lock.locked():
            ui.notify('Aguarde a consulta da OLX em andamento.')
            return
        async with olx.lock:
            try:
                await olx.collector.open_browser(search_url(search))
                ui.notify('Confira a busca no Chrome da OLX. Feche essa janela antes de consultar novamente.')
            except Exception:
                ui.notify('Não foi possível abrir o Chrome da OLX. Feche as janelas desse perfil e tente novamente.', type='negative')

    def pause(search):
        olx.store.db.execute('UPDATE olx_searches SET enabled=? WHERE id=?', (0 if search['enabled'] else 1, search['id']))
        olx.store.db.commit()
        refresh(force=True)

    def remove(search):
        with area, ui.dialog().props('no-refocus') as dialog, ui.card():
            ui.label('Remover busca ' + search['name'] + '?').classes('section-title')
            ui.label('Os anúncios e o histórico desta busca serão removidos do monitor.')
            def confirm():
                olx.store.db.execute('DELETE FROM olx_searches WHERE id=?', (search['id'],))
                olx.store.db.commit()
                dialog.close()
                refresh(force=True)
            with ui.row():
                ui.button('Cancelar', on_click=dialog.close).props('flat')
                ui.button('Remover busca', on_click=confirm, color='negative')
        def close():
            dialog.delete()
            restore_focus('search-' + str(search['id']))
        dialog.on('hide', close)
        dialog.open()

    def history(item):
        with area, ui.dialog().props('no-refocus') as dialog, ui.card().classes('w-full max-w-2xl'):
            ui.label(item['title']).classes('section-title')
            ui.label('Preço anunciado; pagamento, frete e conservação não verificados.').classes('muted')
            rows = olx.store.rows('SELECT * FROM olx_observations WHERE listing_id=? ORDER BY id DESC', (item['id'],))
            ui.table(columns=[dict(name='time', label='Lido em', field='time'), dict(name='price', label='Preço anunciado', field='price')],
                     rows=[dict(id=row['id'], time=local_time(row['observed_at']), price=brl(row['price']) if row['price'] else 'Não informado') for row in rows],
                     row_key='id', pagination=8).classes('w-full')
            ui.button('Fechar', on_click=dialog.close).props('flat')
        def close():
            dialog.delete()
            restore_focus('history-' + str(item['id']))
        dialog.on('hide', close)
        dialog.open()

    def render_search(search):
        with ui.column().classes('w-full gap-3'):
            with ui.row().classes('w-full items-center justify-between'):
                ui.label(search['name'] + (' · pausada' if not search['enabled'] else '')).classes('section-title').props(f'role=heading aria-level=3 tabindex=-1 data-olx-focus=search-{search["id"]}')
                with ui.row().classes('gap-2 items-center'):
                    button = ui.button('Consultar agora', on_click=lambda: scan(search['id'])).props(f'outline no-caps data-olx-focus=scan-{search["id"]}')
                    button.set_enabled(bool(search['enabled']) and not olx.lock.locked())
                    browser = ui.button('Abrir Chrome da OLX', on_click=lambda: open_browser(search)).props(f'flat no-caps data-olx-focus=browser-{search["id"]}')
                    browser.set_enabled(not olx.lock.locked())
                    ui.button('Pausar' if search['enabled'] else 'Retomar', on_click=lambda: pause(search)).props(f'flat no-caps data-olx-focus=pause-{search["id"]}')
                    ui.button('Remover', on_click=lambda: remove(search), color='negative').props(f'flat no-caps data-olx-focus=remove-{search["id"]}')
            ui.label(search['status']).classes('muted').props('role=status')
            ui.label('Última leitura: ' + local_time(search['checked_at']) +
                     (' · teto ' + brl(search['target']) if search['target'] else '')).classes('muted text-sm')
            ui.link('Ver busca na OLX', search_url(search), new_tab=True).classes('text-primary')
            rows = [row for row in olx.listings(search['id']) if eligible(search, row)]
            if not rows:
                ui.label('Nenhum anúncio com preço informado dentro dos seus filtros. Confira o resultado da consulta acima.').classes('muted')
                return
            count = (len(rows) + 5) // 6
            page = min(pages.get(search['id'], 1), count)
            pages[search['id']] = page
            ui.label(f'{len(rows)} anúncios salvos · página {page} de {count}').classes('muted text-sm')
            with ui.element('div').classes('offer-grid w-full'):
                for item in rows[(page - 1) * 6:page * 6]:
                    with ui.element('article').classes('offer-card') as card:
                        card.props['aria-label'] = item['title'] + ' · OLX'
                        card.props['data-olx-search'] = str(search['id'])
                        ui.label(item['title']).classes('offer-title').props(f'role=heading aria-level=4 tabindex=-1 data-olx-focus=title-{item["id"]}')
                        ui.label(brl(item['price'])).classes('offer-price')
                        ui.label('Preço anunciado').classes('muted text-sm')
                        ui.label(item['location'] or 'Localização não informada').classes('muted')
                        ui.label('Na OLX: ' + (item['published_text'] or 'data não informada')).classes('muted text-sm')
                        age = (datetime.now(timezone.utc) - datetime.fromisoformat(item['checked_at'])).total_seconds()
                        stale = age > 1800 or item['checked_at'] != search['checked_at'] or not search['enabled']
                        ui.label(('Último preço lido em ' if stale else 'Lido em ') + local_time(item['checked_at'])).classes('muted text-sm')
                        if stale:
                            ui.label('Presença e preço atuais não confirmados').classes('muted text-sm')
                        with ui.row().classes('gap-2 items-center'):
                            ui.button('Ver anúncio', on_click=lambda listing=item: ui.navigate.to(listing['url'], new_tab=True)).props(f'no-caps data-olx-focus=link-{item["id"]}')
                            ui.button('Histórico', on_click=lambda listing=item: history(listing)).props(f'flat no-caps data-olx-focus=history-{item["id"]}')
            if count > 1:
                def paginate(event):
                    pages[search['id']] = int(event.value)
                    refresh(force=True)
                    container.client.run_javascript('''
                        await new Promise(resolve => requestAnimationFrame(resolve));
                        const title = document.querySelector('[data-olx-focus="title-''' + str(rows[(int(event.value) - 1) * 6]['id']) + '''"]');
                        if (title?.getClientRects().length) {
                            title.closest('article').scrollIntoView({block:'start'});
                            title.focus({preventScroll:true});
                        }
                    ''')
                ui.pagination(1, count, value=page, on_change=paginate).props('direction-links boundary-links')

    def refresh(force=False):
        searches = olx.searches()
        signature = (searches, olx.store.rows('SELECT id,price,checked_at,pending FROM olx_listings ORDER BY id'),
                     olx.lock.locked(), int(datetime.now(timezone.utc).timestamp() // 60))
        status.text = olx.status
        if not force and signature == snapshot['value']:
            return
        snapshot['value'] = signature
        container.clear()
        with container:
            if not searches:
                ui.label('Nenhuma busca cadastrada. Abra Adicionar busca e cole uma busca da OLX ou informe produto e cidade.').classes('muted')
            for search in searches:
                render_search(search)
    refresh()
    ui.timer(2, refresh)
