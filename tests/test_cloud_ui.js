// Run with node tests/test_cloud_ui.js. No browser or external services required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const nodes = new Map();
const node = selector => {
  if (selector === '#comparison details') return null;
  if (!nodes.has(selector)) nodes.set(selector, {value:'', innerHTML:'', textContent:'', hidden:false, setAttribute(){},removeAttribute(){}});
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
  state.catalog.groups[1].offers.push({id:'psu',component_id:2,title:'Fonte Corsair',shop:'Pichau',pix:40000});`);
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
console.log('Cloud UI: catalogue, payment, coupon states, batch guards and history gaps passed.');
