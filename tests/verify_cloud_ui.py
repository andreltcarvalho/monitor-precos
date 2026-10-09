"""Regressões de interação no Chrome com API ASGI e banco isolado em memória.
Execute: .venv/Scripts/python.exe tests/verify_cloud_ui.py
Não envia comandos nem modifica a conta de produção.
"""
import asyncio
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import sys
from unittest.mock import AsyncMock,patch
from types import SimpleNamespace
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1])]
import httpx
from playwright.async_api import async_playwright
from cloud.app import app,repository
from test_cloud import FakeRepository,offer,part
from core import utcnow

async def main():
    class BrowserRepository(FakeRepository):
        async def command(self,action,payload):
            row=await super().command(action,payload);row.update(id=str(len(self.queued)),status='pending',created_at=utcnow(),updated_at=utcnow());return row
    repo=BrowserRepository();repo.data['components','1']=part()
    for i in range(8):
        row=offer(i,200000+i*1000);repo.data['offers',row['id']]=row
    repo.data['coupon_applications','RECUPERAR']={'code':'RECUPERAR','status':'pending','detail':'Tivemos um problema','found_at':utcnow(),'attempts':1,'source':'Teste'}
    repo.data['coupon_applications','ATIVADO']={'code':'ATIVADO','status':'inserted','detail':'Adicionado','found_at':utcnow(),'attempts':1,'source':'Teste'}
    repo.data['settings','public_coupons']={'value':json.dumps([{'code':'NOVOCODIGO','shop':'Mercado Livre','source':'Pelando','conditions':'Informática','activation':False,'found_at':utcnow(),'checked_at':utcnow(),'url':'https://www.mercadolivre.com.br/cupons','source_url':'https://www.pelando.com.br/cupons-de-descontos/mercado-livre'}])}
    repo.data['sources','1']={'id':1,'name':'Grupo teste','reference':'-100123456789','enabled':1}
    repo.data['status','worker']={'name':'PC conectado','checked_at':utcnow(),'sessions':{'Mercado Livre':{'configured':True,'login_open':False,'detail':'Perfil salvo'}}}
    stamp=utcnow()
    repo.data['olx_searches','1']={'id':1,'name':'Teste OLX — dados sintéticos','query':'rtx 5060','city':'Piracicaba','state':'SP','target':300000,'excluded':'quebrado','enabled':1,'checked_at':stamp,'status':'8 anúncios lidos'}
    for i in range(8):
        repo.data['olx_listings',str(i)]={'id':i,'search_id':1,'price':200000+i*1000,'title':'Placa local modelo '+str(i),'location':'Piracicaba, SP','checked_at':stamp if i else '2000-01-01T00:00:00Z','published_text':'Hoje, 12:30','url':'https://www.olx.com.br/anuncio-'+str(i)}
    repo.data['olx_listings','foreign']={'id':99,'search_id':1,'price':10000,'title':'Outra cidade','location':'São Paulo, SP','checked_at':stamp}
    app.dependency_overrides[repository]=lambda:repo
    errors=[];requests=[];favorite_gate=asyncio.Event();favorite_gate.set();history_gate=asyncio.Event();history_gate.set();source_gate=asyncio.Event();source_gate.set()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://monitor.test') as client,async_playwright() as p:
            browser=await p.chromium.launch(channel='chrome',headless=True)
            context=await browser.new_context(viewport={'width':1440,'height':1000},locale='pt-BR',reduced_motion='reduce')
            async def route(request):
                from urllib.parse import urlsplit
                parsed=urlsplit(request.request.url)
                if parsed.path=='/api/sources':
                    await source_gate.wait()
                if parsed.path.startswith('/api/history/'):
                    await history_gate.wait()
                if parsed.path.startswith('/api/preferences/'):
                    await favorite_gate.wait()
                response=await client.request(request.request.method,parsed.path+('?' +parsed.query if parsed.query else ''),content=request.request.post_data,headers={'Origin':'https://monitor.test','Content-Type':'application/json'})
                requests.append((request.request.method,parsed.path,response.status_code,response.text[:100] if response.status_code>=400 else ''))
                await request.fulfill(status=response.status_code,body=response.content,content_type=response.headers.get('content-type','application/json'))
            await context.route('https://monitor.test/**',route)
            page=await context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
            await page.goto('https://monitor.test/');await page.locator('.offer-card').first.wait_for()
            assert await page.locator('.offer-card').count()==6
            tops=await page.locator('.offer-card .offer-price').evaluate_all('(nodes)=>nodes.slice(0,3).map(node=>Math.round(node.getBoundingClientRect().top))')
            assert len(set(tops))==1,tops
            await page.get_by_role('button',name='Próxima página de Placa').click()
            assert '7–8 de 8' in await page.locator('#offer-groups .pagination').inner_text()
            await page.locator('#offer-search').fill('Modelo 0');assert await page.locator('.offer-card').count()==1
            await page.locator('[data-action="details"]').click();assert await page.locator('#offer-details').is_visible()
            await page.keyboard.press('Escape');assert await page.locator('[data-action="details"]').evaluate('(el)=>el===document.activeElement')
            await page.locator('#clear-filters').click()
            await page.locator('[data-action="compare"]').nth(0).click();assert await page.locator('[data-action="open-comparison"]').is_disabled()
            await page.locator('[data-action="compare"]').nth(1).click();await page.locator('[data-action="open-comparison"]').click()
            assert await page.locator('#compare-dialog').is_visible()
            assert '2.000,00' in await page.locator('#comparison').inner_text()
            await page.keyboard.press('Escape');assert await page.locator('[data-action="open-comparison"]').evaluate('(el)=>el===document.activeElement')
            await page.locator('[data-action="clear-comparison"]').click();assert await page.locator('#comparison-tray').is_hidden()
            favorite_gate.clear()
            catalog_reads=sum(path=='/api/catalog' for method,path,status,detail in requests)
            await page.locator('[data-action="favorite"]').first.click()
            assert await page.locator('[data-action="favorite"]').first.is_disabled()
            assert await page.locator('[data-action="favorite"]').first.get_attribute('aria-pressed')=='true'
            assert not any(kind=='preferences' for kind,key in repo.data), 'A estrela deve mudar antes da API responder'
            favorite_gate.set()
            await page.wait_for_function('!document.querySelector("[data-action=favorite]").disabled')
            assert sum(path=='/api/catalog' for method,path,status,detail in requests)==catalog_reads
            try:await page.wait_for_function('document.querySelector("[data-action=favorite]").getAttribute("aria-pressed")==="true"',timeout=5000)
            except Exception:
                print({'requests':requests,'errors':errors,'notice':await page.locator('#notice').inner_text(),'preferences':[(key,value) for (kind,key),value in repo.data.items() if kind=='preferences']});raise
            await page.locator('[data-selection="favorite"]').click();assert await page.locator('.offer-card').count()==1
            await page.locator('#navigation [data-tab="history"]').click()
            await page.wait_for_function('document.querySelector("#history-loading").hidden')
            history_gate.clear()
            await page.locator('#history-payment').select_option('card')
            assert await page.locator('#history-loading').is_visible()
            assert await page.locator('#history-result').get_attribute('aria-busy')=='true'
            history_gate.set()
            await page.wait_for_function('document.querySelector("#history-loading").hidden')
            await page.locator('#navigation [data-tab="coupons"]').click()
            await page.wait_for_function('document.querySelector("#coupons-list").getAttribute("aria-busy")===null')
            assert await page.locator('#coupon-shop').input_value()=='Mercado Livre'
            await page.locator('[data-action="coupon-filter"][data-state="failed"]').click()
            assert await page.locator('.coupon-row').count()==1
            await page.locator('.coupon-conditions summary').click();assert await page.locator('.coupon-conditions').get_attribute('open') is not None
            await page.locator('.coupon-conditions summary').focus()
            await page.evaluate('loadCoupons()')
            assert await page.locator('.coupon-conditions').get_attribute('open') is not None
            assert await page.locator('.coupon-conditions summary').evaluate('(el)=>el===document.activeElement')
            await page.locator('#coupon-search').fill('RECUPERAR');assert await page.locator('.coupon-conditions').get_attribute('open') is not None
            await page.locator('[data-action="coupon-disable"]').click();await page.wait_for_function('document.querySelector("#coupons-list").innerText.includes("Nenhum cupom")');
            await page.locator('[data-action="coupon-filter"][data-state="disabled"]').click();assert await page.locator('.coupon-row').count()==1
            await page.locator('.coupon-conditions summary').click();await page.locator('[data-action="coupon-disable"]').click()
            await page.wait_for_function('document.querySelector("#coupons-list").innerText.includes("Nenhum cupom")');await page.locator('[data-action="coupon-filter"][data-state="failed"]').click()
            assert not repo.queued,'Desativar/reativar não depende do PC'
            await page.locator('#coupon-retry').click();await page.wait_for_function('!document.querySelector("#coupon-retry").hasAttribute("aria-busy")');assert await page.locator('#coupon-retry').is_disabled()
            await page.locator('#navigation [data-tab="parts"]').click();await page.locator('#parts [data-action="edit-part"]').click()
            await page.locator('#brand-summary').click();await page.locator('#brand-search').fill('Asus')
            assert await page.locator('#brands label:visible').count()==1
            await page.locator('#brands input[value="ASUS"]').check()
            assert await page.locator('[data-action="remove-brand"]').count()==1
            await page.locator('#part-form [name="target_text"]').fill('1.950x');await page.locator('#part-save').click()
            await page.wait_for_function('document.querySelector("[name=target_text]").getAttribute("aria-invalid")==="true"')
            assert await page.locator('[name="target_text"]').evaluate('(el)=>el===document.activeElement')
            assert await page.locator('[name="target_text"]').input_value()=='1.950x'
            await page.locator('#part-form [name="target_text"]').fill('1.950,00');await page.locator('#part-save').click()
            await page.wait_for_function('document.querySelector("#part-form").hidden')
            await page.locator('#navigation [data-tab="offers"]').click();await page.locator('[data-selection=""]').click()
            assert await page.locator('.offer-card').count()==0
            assert 'Nenhuma oferta' in await page.locator('#offer-groups').inner_text()
            assert '1.950,00 no Pix' in await page.locator('#offer-groups').inner_text()
            assert await page.get_by_role('button',name='Revisar critérios da peça').is_visible()
            await page.go_back();assert await page.locator('#parts').is_visible()
            await page.locator('#parts [data-action="edit-part"]').click()
            assert 'ASUS' in await page.locator('#brand-selected').inner_text()
            await page.locator('[data-action="remove-brand"]').click();assert await page.locator('#brand-selected').is_hidden()
            await page.locator('#part-cancel').click()
            await page.locator('#navigation [data-tab="sources"]').click();await page.wait_for_function('document.querySelector("#shops-list").getAttribute("aria-busy")===null')
            assert not await page.get_by_text('-100123456789',exact=True).is_visible()
            assert not await page.locator('[data-action="source-toggle"]').is_visible()
            await page.locator('#telegram-section>summary').click()
            await page.locator('[data-action="source-toggle"]').click();await page.wait_for_function('document.querySelector("#telegram-list").innerText.includes("Alteração na fila")')
            assert 'Alteração na fila' in await page.locator('#telegram-list').inner_text()
            assert repo.queued[-1]['action']=='source_toggle'
            await page.locator('#telegram-section>details.disclosure>summary').click()
            source_form=page.locator('#source-form');count=len(repo.queued)
            await source_form.locator('[name="name"]').fill('Outro grupo')
            await source_form.locator('[name="reference"]').fill('@abc')
            await source_form.locator('button[type="submit"]').click()
            await page.wait_for_function('document.querySelector("#source-error").innerText.length>0')
            assert len(repo.queued)==count
            assert await source_form.locator('[name="reference"]').input_value()=='@abc'
            await source_form.locator('[name="reference"]').fill('https://t.me/grupotestexyz')
            await source_form.locator('button[type="submit"]').click()
            await page.wait_for_function('!document.querySelector("#source-form").closest("details").open')
            assert repo.queued[-1]['action']=='source_save'
            assert repo.queued[-1]['payload']['reference']=='@grupotestexyz'
            session=page.locator('.session-controls[data-shop="Mercado Livre"]')
            source_gate.clear();await page.evaluate('void(window.sourceRefresh=loadSources())')
            await session.locator('summary').click();await session.locator('[data-action="session-confirm"]').focus()
            source_gate.set();await page.evaluate('window.sourceRefresh')
            assert await session.get_attribute('open') is not None
            assert await session.locator('[data-action="session-confirm"]').evaluate('(el)=>el===document.activeElement')
            await page.evaluate('refreshBackground()');assert await session.get_attribute('open') is not None
            session=page.locator('.session-controls[data-shop="Mercado Livre"]');await session.locator('[data-action="session-open"]').click();await page.wait_for_function('document.querySelector("[data-action=session-open]").disabled');assert repo.queued[-1]['action']=='session_open'
            for i in range(30):
                repo.data['coupon_applications','CODIGO'+str(i)]={'code':'CODIGO'+str(i),'status':'inserted','detail':'Ativado','found_at':utcnow(),'source':'Teste'}
            await page.locator('#navigation [data-tab="coupons"]').click();await page.wait_for_function('!document.querySelector("#coupons-list").hasAttribute("aria-busy")')
            await page.locator('#coupon-search').fill('');await page.locator('[data-action="coupon-filter"][data-state="active"]').click()
            assert await page.locator('.coupon-row').count()==12
            await page.get_by_role('button',name='Próxima página de cupons').click()
            assert '13–24 de 31' in await page.locator('#coupon-pagination').inner_text()
            await page.locator('#coupon-search').fill('CODIGO29');assert await page.locator('.coupon-row').count()==1
            assert await page.locator('#coupon-pagination').is_hidden()
            await page.locator('#navigation [data-tab="used"]').click()
            await page.wait_for_function('!document.querySelector("#used-list").hasAttribute("aria-busy")')
            await page.locator('.used-reading summary').first.click()
            await page.locator('.used-reading summary').first.focus()
            await page.evaluate('loadUsed()')
            assert await page.locator('.used-reading').first.get_attribute('open') is not None
            assert await page.locator('.used-reading summary').first.evaluate('(el)=>el===document.activeElement')
            await page.locator('#used>details>summary').click()
            form=page.locator('#used-form')
            await form.locator('[name="name"]').fill('Nova busca')
            await form.locator('[name="query"]').fill('rtx 5060')
            await form.locator('[name="target"]').fill('inválido')
            count=len(repo.queued)
            await form.locator('button[type="submit"]').click()
            await page.wait_for_function('document.querySelector("#used-error").innerText.length>0')
            assert len(repo.queued)==count
            assert await form.locator('[name="target"]').input_value()=='inválido'
            await form.locator('[name="target"]').fill('2800')
            await form.locator('[name="excluded"]').fill('quebrado\ndefeito')
            await form.locator('button[type="submit"]').click()
            await page.wait_for_function('!document.querySelector("#used-form").closest("details").open')
            assert repo.queued[-1]['action']=='olx_save'
            assert repo.queued[-1]['payload']['excluded']=='quebrado,defeito'
            assert await form.locator('[name="state"]').input_value()=='SP'
            if await page.locator('#notice').is_visible():await page.locator('#dismiss-notice').click()
            assert await page.locator('#used-list .offer-card').count()==6
            assert 'Outra cidade' not in await page.locator('#used-list').inner_text()
            assert 'Presença e preço atuais não confirmados' in await page.locator('#used-list').inner_text()
            out=Path('tmp/ux-2026-10-08');out.mkdir(parents=True,exist_ok=True)
            await page.screenshot(path=out/'synthetic-used.png',full_page=True)
            await page.locator('[data-action="used-page"]').last.click()
            assert await page.locator('#used-list .offer-card').count()==2
            assert await page.locator('#used-search-1').evaluate('(el)=>el===document.activeElement')
            await page.locator('[data-action="olx-scan"]').click()
            await page.wait_for_function('document.querySelector("[data-action=olx-scan]").innerText.includes("Pedido enviado")')
            assert 'Pedido enviado' in await page.locator('[data-action="olx-scan"]').inner_text()
            assert repo.queued[-1]['action']=='olx_scan'
            await page.locator('#navigation [data-tab="activity"]').click()
            await page.wait_for_function('!document.querySelector("#activity-list").hasAttribute("aria-busy")')
            await page.locator('#activity-tabs [data-state="pending"]').click()
            cancel=page.locator('#activity-list [data-action="command-cancel"]').first
            await cancel.focus();await page.evaluate('reloadCatalog()')
            assert await cancel.evaluate('(el)=>el===document.activeElement')
            await page.locator('[data-action="activity-filter"][data-state="pending"]').click()
            assert 'Aguardando o PC' in await page.locator('#activity-list').inner_text()
            await page.locator('[data-action="activity-filter"][data-state="history"]').click()
            assert 'Nenhum pedido finalizado' in await page.locator('#activity-list').inner_text()
            await page.set_viewport_size({'width':1024,'height':900});assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
            await page.locator('#navigation [data-tab="offers"]').click();await page.locator('[data-selection="favorite"]').click()
            await page.locator('[data-action="details"]').click()
            await page.locator('#details-content [data-action="check"]').focus()
            await page.evaluate("state.offers.get(state.detailId).valid_until='2000-01-01T00:00:00Z';state.catalogExpiry=0;refreshTimedPrices()")
            assert 'Último valor lido' in await page.locator('#details-content').inner_text()
            assert await page.locator('#details-content [data-action="check"]').evaluate('(el)=>el===document.activeElement')
            await page.route('https://monitor.test/api/catalog',lambda route:route.fulfill(status=401,json={'detail':'Sessão expirada'}))
            await page.route('https://monitor.test/api/auth/refresh',lambda route:route.fulfill(status=401,json={'detail':'Sessão expirada'}))
            await page.locator('#reload-offers').dispatch_event('click')
            await page.locator('#login').wait_for();assert not await page.locator('#offer-details').is_visible()
            assert not errors,errors
            await browser.close()
    finally:app.dependency_overrides.clear()
    print('Chrome + API ASGI: paginação, filtros, favoritos, foco, estados/retentativa, limite e navegação aprovados.')

if __name__=='__main__':asyncio.run(main())
