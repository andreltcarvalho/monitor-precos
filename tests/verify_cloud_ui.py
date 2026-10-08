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
    app.dependency_overrides[repository]=lambda:repo
    errors=[];requests=[]
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://monitor.test') as client,async_playwright() as p:
            browser=await p.chromium.launch(channel='chrome',headless=True)
            context=await browser.new_context(viewport={'width':1440,'height':1000},locale='pt-BR',reduced_motion='reduce')
            async def route(request):
                from urllib.parse import urlsplit
                parsed=urlsplit(request.request.url)
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
            await page.locator('#clear-filters').click();await page.locator('[data-action="favorite"]').first.click()
            try:await page.wait_for_function('document.querySelector("[data-action=favorite]").getAttribute("aria-pressed")==="true"',timeout=5000)
            except Exception:
                print({'requests':requests,'errors':errors,'notice':await page.locator('#notice').inner_text(),'preferences':[(key,value) for (kind,key),value in repo.data.items() if kind=='preferences']});raise
            await page.locator('[data-selection="favorite"]').click();assert await page.locator('.offer-card').count()==1
            await page.locator('#navigation [data-tab="coupons"]').click()
            await page.wait_for_function('document.querySelector("#coupons-list").getAttribute("aria-busy")===null')
            assert await page.locator('#coupon-shop').input_value()=='Mercado Livre'
            await page.locator('[data-action="coupon-filter"][data-state="failed"]').click()
            assert await page.locator('.coupon-row').count()==1
            await page.locator('.coupon-conditions summary').click();assert await page.locator('.coupon-conditions').get_attribute('open') is not None
            await page.locator('#coupon-search').fill('RECUPERAR');assert await page.locator('.coupon-conditions').get_attribute('open') is not None
            await page.locator('[data-action="coupon-disable"]').click();await page.wait_for_function('document.querySelector("#coupons-list").innerText.includes("Nenhum cupom")');
            await page.locator('[data-action="coupon-filter"][data-state="disabled"]').click();assert await page.locator('.coupon-row').count()==1
            await page.locator('.coupon-conditions summary').click();await page.locator('[data-action="coupon-disable"]').click()
            await page.wait_for_function('document.querySelector("#coupons-list").innerText.includes("Nenhum cupom")');await page.locator('[data-action="coupon-filter"][data-state="failed"]').click()
            assert not repo.queued,'Desativar/reativar não depende do PC'
            await page.locator('#coupon-retry').click();await page.wait_for_function('!document.querySelector("#coupon-retry").hasAttribute("aria-busy")');assert await page.locator('#coupon-retry').is_disabled()
            await page.locator('#navigation [data-tab="parts"]').click();await page.locator('[data-action="edit-part"]').click()
            await page.locator('#part-form [name="target_text"]').fill('1.950,00');await page.locator('#part-save').click()
            await page.wait_for_function('document.querySelector("#part-form").hidden')
            await page.locator('#navigation [data-tab="offers"]').click();await page.locator('[data-selection=""]').click()
            assert await page.locator('.offer-card').count()==0
            assert 'Nenhuma oferta' in await page.locator('#offer-groups').inner_text()
            await page.go_back();assert await page.locator('#parts').is_visible()
            await page.locator('#navigation [data-tab="sources"]').click();await page.wait_for_function('document.querySelector("#shops-list").getAttribute("aria-busy")===null')
            assert not await page.get_by_text('-100123456789',exact=True).is_visible()
            await page.locator('[data-action="source-toggle"]').click();await page.wait_for_function('document.querySelector("#telegram-list").innerText.includes("Alteração na fila")')
            assert 'Alteração na fila' in await page.locator('#telegram-list').inner_text()
            assert repo.queued[-1]['action']=='source_toggle'
            session=page.locator('.session-controls[data-shop="Mercado Livre"]');await session.locator('summary').click();await session.locator('[data-action="session-open"]').click();await page.wait_for_function('document.querySelector("[data-action=session-open]").disabled');assert repo.queued[-1]['action']=='session_open'
            for i in range(30):
                repo.data['coupon_applications','CODIGO'+str(i)]={'code':'CODIGO'+str(i),'status':'inserted','detail':'Ativado','found_at':utcnow(),'source':'Teste'}
            await page.locator('#navigation [data-tab="coupons"]').click();await page.wait_for_function('!document.querySelector("#coupons-list").hasAttribute("aria-busy")')
            await page.locator('#coupon-search').fill('');await page.locator('[data-action="coupon-filter"][data-state="active"]').click()
            assert await page.locator('.coupon-row').count()==12
            await page.get_by_role('button',name='Próxima página de cupons').click()
            assert '13–24 de 31' in await page.locator('#coupon-pagination').inner_text()
            await page.locator('#coupon-search').fill('CODIGO29');assert await page.locator('.coupon-row').count()==1
            assert await page.locator('#coupon-pagination').is_hidden()
            await page.locator('#navigation [data-tab="activity"]').click();await page.wait_for_function('!document.querySelector("#activity-list").hasAttribute("aria-busy")')
            await page.locator('[data-action="activity-filter"][data-state="pending"]').click()
            assert 'Aguardando o PC' in await page.locator('#activity-list').inner_text()
            await page.locator('[data-action="activity-filter"][data-state="history"]').click()
            assert 'Nenhum pedido finalizado' in await page.locator('#activity-list').inner_text()
            await page.set_viewport_size({'width':1024,'height':900});assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
            assert not errors,errors
            await browser.close()
    finally:app.dependency_overrides.clear()
    print('Chrome + API ASGI: paginação, filtros, favoritos, foco, estados/retentativa, limite e navegação aprovados.')

if __name__=='__main__':asyncio.run(main())
