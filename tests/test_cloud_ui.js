// Run with node tests/test_cloud_ui.js. No browser or external services required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const nodes = new Map();
const node = selector => {
  if (selector === '#comparison details') return null;
  if (!nodes.has(selector)) nodes.set(selector, {value:'', innerHTML:'', textContent:'', hidden:false, setAttribute(){},removeAttribute(){},classList:{toggle(){}}});
  return nodes.get(selector);
};
const context = vm.createContext({document:{querySelector:node,querySelectorAll:()=>[],activeElement:null},URL,Date,console});
const source = fs.readFileSync('cloud/static/app.js','utf8');
vm.runInContext(source.slice(0,source.indexOf("$('#navigation').addEventListener")),context);
const run = code => vm.runInContext(code,context);
run(`state.catalog={groups:[{id:1,name:'Placa',offers:[]},{id:2,name:'Fonte',offers:[]}],components:[]};
  for(let i=0;i<14;i++){
    const row={id:String(i),component_id:1,title:'Modelo '+i,shop:'Pichau',pix:200000+i*1000,effective:200000+i*1000,
      valid_until:new Date(Date.now()+600000).toISOString(),favorite:i===10};
    state.catalog.groups[0].offers.push(row);state.offers.set(row.id,row);
  }
  state.catalog.groups[1].offers.push({id:'psu',component_id:2,title:'Fonte Corsair',shop:'Pichau',pix:40000,valid_until:new Date(Date.now()+600000).toISOString()});`);
node('#offer-part').value='1';
run('renderOffers()');
assert.equal((node('#offer-groups').innerHTML.match(/class="offer-card/g)||[]).length,6);
assert.match(node('#offer-groups').innerHTML,/1–6 de 12/);
assert.doesNotMatch(node('#offer-groups').innerHTML,/Modelo 6</);
run('state.pages.set(1,1);renderOffers()');
assert.match(node('#offer-groups').innerHTML,/7–12 de 12/);
assert.match(node('#offer-groups').innerHTML,/Modelo 11</);
assert.doesNotMatch(node('#offer-groups').innerHTML,/Modelo 12</);
node('#offer-selection').value='favorite';
run('renderOffers()');
assert.equal((node('#offer-groups').innerHTML.match(/class="offer-card/g)||[]).length,1);
assert.match(node('#offer-groups').innerHTML,/Modelo 10</);
assert.match(node('#offer-groups').innerHTML,/1–1 de 1/);
node('#offer-selection').value='';node('#offer-part').value='';node('#offer-search').value='Corsair';
run('renderOffers()');
assert.equal(run('state.activeGroup'),2,'Search opens the group containing matching offers');
assert.match(node('#offer-groups').innerHTML,/data-group="2" open/);
run("state.catalog.groups[0].offers[0].pix=null;state.catalog.groups[0].offers[0].announced=200000;state.catalog.groups[0].offers[0].coupon_price=180000;state.catalog.groups[0].offers[0].shop='Mercado Livre'");
const couponCard=run('card(state.catalog.groups[0].offers[0])');
assert.match(couponCard,/Com cupom na sua sessão/);
assert.doesNotMatch(couponCard,/No Pix/);
assert.match(couponCard,/Sem cupom:/);
run("state.catalog.groups[0].offers[0].coupon_price=null;state.catalog.groups[0].offers[0].card=240000");
const announcedCard=run('card(state.catalog.groups[0].offers[0])');
assert.match(announcedCard,/Pagamento não informado/);
assert.doesNotMatch(announcedCard,/Total no cartão/);
assert.match(announcedCard,/2\.000,00/);
assert.equal(run('state.catalog.groups[0].offers[0].card'),240000);
// Coupon filters include new codes without an application; states never imply activation.
run(`state.coupons={coupons:[{code:'NOVO',shop:'Pichau',source:'Oficial',conditions:'Desconto'},
 {code:'OK',shop:'Mercado Livre',source:'Telegram',source_url:'https://t.me/ofertas/1',url:'https://mercadolivre.com.br/cupons'},
 {code:'FALHA',shop:'Mercado Livre',source:'Pelando'}],applications:[{code:'OK',group:'active',label:'Inserido'},
 {code:'FALHA',group:'failed',label:'Pode retentar',retryable:true,failure:'Temporário'}]};renderCoupons();`);
assert.match(node('#coupons-list').innerHTML,/NOVO/);
assert.match(node('#coupons-list').innerHTML,/https:\/\/t.me\/ofertas\/1/);
assert.match(node('#coupons-list').innerHTML,/Ver publicação/);
assert.equal(node('#coupon-apply').disabled,true,'No new Mercado Livre code to apply');
assert.equal(node('#coupon-retry').disabled,false);
node('#coupon-state').value='new';run('renderCoupons()');
assert.match(node('#coupons-list').innerHTML,/NOVO/);
assert.doesNotMatch(node('#coupons-list').innerHTML,/coupon-code">OK/);
node('#coupon-state').value='active';run('renderCoupons()');
assert.match(node('#coupons-list').innerHTML,/coupon-code">OK/);
assert.doesNotMatch(node('#coupons-list').innerHTML,/NOVO/);
run("state.catalog.commands=[{action:'coupon_batch',status:'pending'}];renderCoupons()");
assert.equal(node('#coupon-retry').disabled,true,'Queued batches cannot be sent twice');
const chart=run(`historyView({points:[{date:'2026-10-01',price:200000},{date:'2026-10-02',price:210000},{date:'2026-10-05',price:190000}],minimum:190000,median:200000})`);
assert.equal((chart.match(/stroke-width="2.5"/g)||[]).length,1,'Missing days do not become connected readings');
assert.match(chart,/<details class="disclosure history-records">/);
assert.match(chart,/<circle[^>]*><title>05\/10\/2026:/);
run("state.catalog.components=[{id:1,name:'GPU',query:'rtx',enabled:true,ignored_brands:'[]'}];renderParts()");
assert.doesNotMatch(node('#parts-list').innerHTML,/ · Ignorar/);
run("state.catalog.scan_next_at={'1':new Date(Date.now()+120000).toISOString()};state.catalog.groups[0].enabled=true;state.catalog.components=[];renderOffers()");
assert.match(node('#offer-groups').innerHTML,/Atualizar em [12] min/);
console.log('Cloud UI: catalogue, payment, coupon states, batch guards and history gaps passed.');

// Long lists retain navigation; other shops do not inherit Mercado Livre states/actions.
run(`state.coupons={coupons:Array.from({length:27},(_,i)=>({code:'CUPOM'+i,shop:'KaBuM',stamp:new Date(2026,9,8,0,i).toISOString()})),applications:[]};state.couponPage=0;`);
node('#coupon-shop').value='KaBuM';node('#coupon-state').value='active';run('renderCoupons()');
assert.equal((node('#coupons-list').innerHTML.match(/coupon-row/g)||[]).length,12);
assert.equal(node('#coupon-batch').hidden,true);
assert.equal(node('#coupon-tabs').hidden,true);
assert.match(node('#coupons-list').innerHTML,/CUPOM26/);
assert.doesNotMatch(node('#coupons-list').innerHTML,/CUPOM0</);
run('state.couponPage=2;renderCoupons()');
assert.equal((node('#coupons-list').innerHTML.match(/coupon-row/g)||[]).length,3);
assert.match(node('#coupon-pagination').innerHTML,/25–27 de 27/);
run(`state.catalog.commands=[{id:'old',action:'scan',status:'pending',created_at:'2026-10-01T00:00:00Z'},...Array.from({length:25},(_,i)=>({id:String(i),action:'check',status:'done',created_at:'2026-10-08T00:00:00Z'}))];state.activityFilter=null;renderActivity()`);
assert.equal(run('state.activityFilter'),'pending');assert.match(node('#activity-list').innerHTML,/Aguardando o PC/);
assert.doesNotMatch(node('#activity-list').innerHTML,/Concluído/);assert.equal(node('#activity-count').textContent,1);
run("state.activityFilter='history';renderActivity()");assert.equal((node('#activity-list').innerHTML.match(/class="row"/g)||[]).length,10);
assert.match(node('#activity-pagination').innerHTML,/1–10 de 25/);
console.log('List focus: coupon pagination, shop scope and outstanding commands passed.');

// Saved offers rank by the displayed amount; an expired coupon cannot move one to the top.
run(`state.offers=new Map([['old',{id:'old',component_id:1,title:'Antigo',shop:'Mercado Livre',announced:250000,coupon_price:100000,favorite:true,valid_until:'2000-01-01T00:00:00Z'}],['current',{id:'current',component_id:1,title:'Atual',shop:'Pichau',pix:200000,favorite:true}]]);`);
node('#offer-search').value='';node('#offer-shop').value='';node('#offer-selection').value='favorite';
assert.equal(run('offerRows(state.catalog.groups[0])[0].id'),'current');
run("state.comparison=['old','current'];renderComparison()");
assert.match(node('#comparison').innerHTML,/Sem confirmação atual/);
console.log('Saved prices: expired coupon ranking and comparison warning passed.');

// Clock passage must expire worker presence even without a new HTTP response.
run(`state.catalog.status=[{name:'PC conectado',checked_at:new Date(Date.now()-60000).toISOString()}];renderConnection();`);
assert.equal(node('#connection').textContent,'PC conectado');
run(`state.catalog.status[0].checked_at=new Date(Date.now()-181000).toISOString();renderConnection();`);
assert.equal(node('#connection').textContent,'PC sem sincronização');
run(`state.catalog.status=[];renderConnection();`);
assert.equal(node('#connection').textContent,'PC sem sincronização');
console.log('Worker presence expires from the clock, not only a refresh.');

assert.equal(run('age(new Date(Date.now()+20000).toISOString())'),'agora','Small server clock skew must not hide a fresh reading');
assert.equal(run('age(new Date(Date.now()+600000).toISOString())'),'Horário não informado');
run(`state.catalog.status=[{name:'PC conectado',checked_at:new Date(Date.now()+600000).toISOString()}];renderConnection();`);
assert.equal(node('#connection').textContent,'PC sem sincronização');

assert.equal(run("commandContext({action:'coupon_retry',payload:{code:'NOVO'}})"),'NOVO');
assert.equal(run("commandContext({action:'scan',payload:{component_id:9,label:'Placa escolhida'}})"),'Placa escolhida');
assert.equal(run("commandContext({action:'source_toggle',payload:{id:1}})"),'Grupo #1');
assert.equal(run("commandContext({action:'scan',payload:{component_id:999}})"),'Peça #999');

run(`state.catalog.commands=[{action:'source_toggle',payload:{id:1,label:'<img src=x onerror=alert(1)>'},status:'pending',created_at:new Date().toISOString()}];state.activityFilter='pending';renderActivity();`);
assert.match(node('#activity-list').innerHTML,/&lt;img/);assert.doesNotMatch(node('#activity-list').innerHTML,/<img/);
console.log('Activity: named requests, old-request fallback and escaping passed.');

run(`state.catalog.commands=[];state.used={searches:[{id:1,name:'Teste OLX',city:'Piracicaba',state:'SP',enabled:1,target:300000,checked_at:new Date().toISOString()}],listings:[]};
for(let i=0;i<8;i++)state.used.listings.push({id:i,search_id:1,price:200000+(7-i)*1000,title:'Anúncio '+i,location:'Piracicaba, SP',checked_at:'2000-01-01T00:00:00Z',eligible:true,url:'https://www.olx.com.br/anuncio'});
state.used.listings.push({id:99,search_id:1,price:1,title:'Fora dos critérios',eligible:false});renderUsed();`);
assert.equal((node('#used-list').innerHTML.match(/class="offer-card/g)||[]).length,6);
assert.match(node('#used-list').innerHTML,/1–6 de 8/);
assert.doesNotMatch(node('#used-list').innerHTML,/Fora dos critérios/);
assert.match(node('#used-list').innerHTML,/Presença e preço atuais não confirmados/);
assert.equal(run('usedRows(state.used.searches[0])[0].id'),7);
run('state.usedPages.set(1,1);renderUsed();');assert.match(node('#used-list').innerHTML,/7–8 de 8/);
run(`state.catalog.commands=[{action:'olx_scan',status:'pending',payload:{id:1}}];renderUsed();`);
assert.match(node('#used-list').innerHTML,/disabled>Pedido enviado/);
console.log('Used listings: eligibility, price order, pagination, stale data and queued requests passed.');

run(`state.catalog.groups=[{id:1,name:'Placa',offers:[{id:'expired',component_id:1,title:'Expirada',pix:100000,shop:'Pichau',valid_until:'2000-01-01T00:00:00Z'},{id:'live',component_id:1,title:'Atual',pix:200000,shop:'Pichau',valid_until:new Date(Date.now()+60000).toISOString()}]}];state.offers=new Map(state.catalog.groups[0].offers.map(row=>[row.id,row]));`);
node('#offer-selection').value='';node('#offer-part').value='1';node('#offer-search').value='';
run('state.catalogExpiry=0;refreshTimedPrices();');
assert.doesNotMatch(node('#offer-groups').innerHTML,/offer-title[^>]*>Expirada/);
assert.match(node('#piece-picker').innerHTML,/A partir de.*2\.000,00/);
assert.equal(run('offerRows(state.catalog.groups[0]).length'),1);
assert.ok(run('state.catalogExpiry>Date.now()'));
run(`state.offers.get('expired').favorite=true;`);node('#offer-selection').value='favorite';run('renderOffers();');
assert.match(node('#offer-groups').innerHTML,/Precisa conferir/);
console.log('Price validity: expired catalogue data disappears without a response; saved prices stay explicit.');
