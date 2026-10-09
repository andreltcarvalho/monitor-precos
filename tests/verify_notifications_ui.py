"""Chrome real + API real; bot e banco sintéticos, nenhum envio externo."""
import asyncio
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys
from unittest.mock import patch
from urllib.parse import urlsplit
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1])]
import httpx
from playwright.async_api import async_playwright
from cloud.app import app,repository
from test_cloud import FakeRepository,part,offer
from test_notifications import TOKEN

async def main():
    class Repo(FakeRepository):
        config={}
        async def request(self,method,path,**kwargs):
            data=kwargs.get('data') or {}
            if path.endswith('monitor_telegram_save'):
                self.config=dict(token=data['bot_token'],username=data['bot_username'],nonce='fixture_nonce',
                  paired_at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
                  pair_until=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat(),enabled=False)
            elif path.endswith('monitor_telegram_recipient'):
                self.config.update(chat_id=data['recipient_id'],enabled=True,pair_until=datetime.now(timezone.utc).isoformat())
            elif path.endswith('monitor_telegram_toggle'):
                self.config['enabled']=data['is_enabled']
            return self.config
    repo=Repo();repo.data['components','1']=part();repo.data['offers','1']=offer(1,200000)
    started=False;sent=[]
    async def bot(client,token,method,payload=None):
        assert token==TOKEN
        if method=='getMe':return {'username':'fixture_bot'}
        if method=='getUpdates':return [{'message':{'text':'/start fixture_nonce','date':int(datetime.now(timezone.utc).timestamp()),'chat':{'id':123,'type':'private'},'from':{'id':123}}}] if started else []
        sent.append(payload);return {'message_id':1}
    app.dependency_overrides[repository]=lambda:repo
    errors=[];bad=[]
    try:
        with patch('cloud.app.bot_call',bot):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://monitor.test') as client,async_playwright() as p:
                browser=await p.chromium.launch(channel='chrome',headless=True)
                context=await browser.new_context(viewport={'width':1440,'height':1000},locale='pt-BR')
                async def route(request):
                    r=request.request;parsed=urlsplit(r.url)
                    response=await client.request(r.method,parsed.path,content=r.post_data,headers={'Origin':'https://monitor.test','Content-Type':'application/json'})
                    if response.status_code>=500:bad.append((parsed.path,response.status_code))
                    await request.fulfill(status=response.status_code,body=response.content,content_type=response.headers.get('content-type','application/json'))
                await context.route('https://monitor.test/**',route)
                page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                await page.goto('https://monitor.test/');await page.locator('.offer-card').wait_for()
                await page.locator('#navigation [data-tab=parts]').click();await page.locator('[data-action=edit-part]').click()
                await page.locator('[name=notification_target_text]').fill('-10')
                await page.locator('#part-save').click();await page.locator('[name=notification_target_text][aria-invalid=true]').wait_for()
                await page.locator('[name=notification_target_text]').fill('2.500,00')
                await page.locator('#part-save').click();await page.locator('#parts-list').wait_for()
                assert repo.data['overrides','component:1']['notification_target']==250000
                assert 'Telegram: abaixo de' in await page.locator('#parts-list').inner_text()
                await page.locator('[data-action=edit-part]').click()
                assert await page.locator('[name=notification_target_text]').input_value()=='2500,00'
                out=Path('tmp/telegram-notifications');out.mkdir(parents=True,exist_ok=True)
                await page.screenshot(path=out/'synthetic-threshold-1440.png',full_page=True)
                await page.set_viewport_size({'width':1024,'height':900})
                assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
                await page.screenshot(path=out/'synthetic-threshold-1024.png',full_page=True)
                await page.locator('#part-cancel').click()
                await page.locator('#navigation [data-tab=sources]').click()
                await page.locator('#notification-summary').get_by_text('Não conectado').wait_for()
                await page.locator('#notification-settings>summary').click()
                await page.get_by_text('Configurar ou trocar o bot',exact=True).click()
                await page.locator('#notification-form input').fill(TOKEN)
                await page.locator('#notification-form button').click()
                await page.locator('#notification-pair-link').wait_for()
                assert TOKEN not in await page.content()
                assert await page.locator('#notification-form input').input_value()==''
                await page.locator('#notification-pair').click()
                await page.wait_for_function('document.querySelector("#notification-error").textContent.length>0')
                assert 'Iniciar' in await page.locator('#notification-error').inner_text()
                started=True
                await page.locator('#notification-pair').click();await page.locator('#notification-test').wait_for()
                await page.locator('#notification-test').click()
                await page.wait_for_function('document.querySelector("#notice-message").textContent.includes("Mensagem de teste")')
                assert len(sent)==1 and sent[0]['chat_id']=='123'
                await page.locator('#notification-toggle').click()
                await page.wait_for_function('document.querySelector("#notification-toggle").textContent.includes("Ativar")')
                assert not repo.config['enabled']
                await page.screenshot(path=out/'synthetic-connection-1024.png',full_page=True)
                assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
                assert not errors and not bad,(errors,bad)
                await browser.close()
    finally:app.dependency_overrides.clear()
    print('Chrome + API ASGI: limite/validação/persistência, pareamento, teste, pausa, token oculto e desktop 1440/1024 aprovados. Bot sintético; nenhum envio externo.')

if __name__=='__main__':asyncio.run(main())
