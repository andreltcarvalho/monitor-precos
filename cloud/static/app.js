'use strict';
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const currency = value => value == null ? 'Não informado' : (value / 100).toLocaleString('pt-BR', {style:'currency', currency:'BRL'});
const time = stamp => stamp && !Number.isNaN(Date.parse(stamp)) ? new Date(stamp).toLocaleString('pt-BR', {timeZone:'America/Sao_Paulo',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}) : 'Não informado';
const safeLink = url => { try {const u=new URL(url); return u.protocol==='https:' && !u.username && !u.password ? u.href : ''; } catch {return '';} };
const state = {tab:'offers', catalog:null, offers:new Map(), comparison:[], busy:new Set(), session:null, coupons:null, pages:new Map(), activeGroup:null,historyRequest:0};
const icon = path => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;
const star = icon('m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z');
const tabIcons={offers:'M4 6h16v14H4ZM8 6V4h8v2M8 10h8M8 14h5',parts:'M7 7h10v10H7ZM9 3v4m6-4v4M9 17v4m6-4v4M3 9h4m-4 6h4m10-6h4m-4 6h4',coupons:'M4 6h16v4a2 2 0 0 0 0 4v4H4v-4a2 2 0 0 0 0-4ZM13 6v3m0 3v1m0 3v2',history:'M4 4v16h16M7 15l4-4 4 2 5-7',used:'M4 10l8-6 8 6v10H4ZM9 20v-6h6v6',sources:'M12 12V5M5 19v-6h14v6M9 5h6M2 19h6m8 0h6',activity:'M3 12h4l3-7 4 14 3-7h4'};
let noticeTimer;
function notice(message) { $('#notice-message').textContent=message; $('#notice').hidden=false; clearTimeout(noticeTimer); noticeTimer=setTimeout(()=>$('#notice').hidden=true,9000); }
function signedOut() {$('#boot').hidden=true; $('#workspace').hidden=true; $('#login').hidden=false; state.session=null;state.catalog=null;state.offers.clear();state.coupons=null; }
async function api(path, data, method, retried=false) {
  const response=await fetch(path, {method:method || (data===undefined?'GET':'POST'),credentials:'same-origin',headers:data===undefined?{}:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});
  if(response.status===401 && !path.startsWith('/api/auth/') && !retried) {
    const refreshed=await fetch('/api/auth/refresh',{method:'POST',credentials:'same-origin'});
    if(refreshed.ok) return api(path,data,method,true);
    signedOut(); throw new Error('Sessão expirada. Entre novamente.');
  }
  let body;try{body=await response.json();}catch{throw new Error('O servidor não respondeu como esperado. Tente novamente.');}
  if(!response.ok) {const error=new Error(typeof body.detail==='string'?body.detail:'Confira os campos informados.');error.fields=typeof body.detail==='object'?body.detail:null;throw error;}
  return body;
}
async function busy(button, operation) {
  const content=button.innerHTML;button.disabled=true;button.setAttribute('aria-busy','true');button.textContent='Aguarde…';
  try {return await operation();} catch(error) {notice(error.message);return null;} finally {button.disabled=false;button.removeAttribute('aria-busy');if(button.textContent==='Aguarde…')button.innerHTML=content;}
}
function options(select, values, allLabel) {
  const current=select.value;
  select.innerHTML=(allLabel?`<option value="">${escapeHtml(allLabel)}</option>`:'')+values.map(v=>`<option value="${escapeHtml(v.value??v)}">${escapeHtml(v.label??v)}</option>`).join('');
  if([...select.options].some(o=>o.value===current))select.value=current;
}
async function start() {
  try {
    state.session=await api('/api/session');$('#boot').hidden=true;$('#login').hidden=true;$('#workspace').hidden=false;
    $('#brands').innerHTML=state.session.brands.map(brand=>`<label><input type="checkbox" name="brand" value="${escapeHtml(brand)}">${escapeHtml(brand)}</label>`).join('');
    $('#panel-url').value=location.origin;
    loading('offer-groups');await reloadCatalog();$('#offer-groups').removeAttribute('aria-busy');await showTab(location.hash.slice(1)||'offers',false);
  } catch(error) {if(!state.session){signedOut();$('#login-message').textContent=error.message;}else loadError('offer-groups',error);}
}
async function reloadCatalog() {
  const initial=!state.catalog;
  state.catalog=await api('/api/catalog');state.offers.clear();
  for(const row of state.catalog.offers)state.offers.set(row.id,row);
  for(const group of state.catalog.groups)for(const row of group.offers)state.offers.set(row.id,row);
  state.comparison=state.comparison.filter(id=>state.offers.has(id)&&!state.offers.get(id).hidden);
  const parts=state.catalog.components.map(p=>({value:String(p.id),label:p.name}));
  options($('#offer-part'),parts,'Todas');options($('#history-part'),parts);
  if(initial&&parts.length)$('#offer-part').value=parts[0].value;
  options($('#offer-shop'),[...state.session.cloud_shops,...state.session.local_shops],'Todas');
  renderOffers();renderParts();renderActivity();
  const worker=state.catalog.status.find(row=>row.name==='PC conectado');
  const recent=worker&&Date.now()-Date.parse(worker.checked_at)<180000;
  $('#connection').textContent=recent?'PC conectado':'PC sem sincronização';
  $('#connection').className='connection-state text '+(recent?'connected':'disconnected');
  $('#connection').title=worker?'Última sincronização: '+time(worker.checked_at):'Conecte o monitor pela aba Fontes. O histórico da nuvem continua disponível.';
  const online=state.catalog.status.filter(row=>state.session.cloud_shops.includes(row.name)&&row.checked_at);
  const successes=new Set(online.filter(row=>row.count>0&&Date.now()-Date.parse(row.checked_at)<3600000).map(row=>row.name));
  $('#cloud-connection').textContent=online.length?successes.size+' '+(successes.size===1?'loja online com leitura recente.':'lojas online com leitura recente.'):'Buscas online independentes do PC.';
}
function filtered(row) {
  const search=$('#offer-search').value.trim().toLocaleLowerCase('pt-BR');
  return (!$('#offer-shop').value||row.shop===$('#offer-shop').value)&&(!search||`${row.title} ${row.shop} ${row.brand||''} ${row.seller||''}`.toLocaleLowerCase('pt-BR').includes(search));
}
function offerPrice(row) {
  const base=row.shop==='Mercado Livre'&&row.pix==null?row.announced:(row.pix??row.card??row.announced);
  const coupon=row.valid_until&&Date.parse(row.valid_until)>Date.now()&&row.coupon_price>0&&row.coupon_price<(base??Infinity);
  return {base,amount:coupon?row.coupon_price:base,coupon};
}
function age(stamp) {
  const minutes=Math.floor((Date.now()-Date.parse(stamp))/60000);
  if(!Number.isFinite(minutes)||minutes<0)return 'Horário não informado';
  if(minutes<1)return 'agora';if(minutes<60)return 'há '+minutes+' min';
  const hours=Math.floor(minutes/60);if(hours<24)return 'há '+hours+' h';
  return 'há '+Math.floor(hours/24)+' dia'+(hours<48?'':'s');
}
function empty(title,message,action='') {return `<div class="empty"><strong>${escapeHtml(title)}</strong><p>${escapeHtml(message)}</p>${action}</div>`;}
function loading(id) {const node=$('#'+id);node.setAttribute('aria-busy','true');if(!node.innerHTML)node.innerHTML='<div class="loading-state" role="status">Carregando…</div>';}
function loadError(id,error) {$('#'+id).innerHTML=empty('Não foi possível carregar',error.message,'<button class="secondary" data-action="retry-page">Tentar novamente</button>');}

function card(row) {
  const current=row.valid_until&&Date.parse(row.valid_until)>Date.now();
  const {base,amount,coupon}=offerPrice(row);
  const payment=coupon?'Com cupom na sua sessão':row.pix!=null?'no Pix':row.shop==='Mercado Livre'?'Pagamento não informado':row.card!=null?'total no cartão':'Pagamento não informado';
  const verified=(row.status||'').startsWith('Preço lido na loja')||(row.status||'').startsWith('Preço da loja lido');
  const label=!current?'Precisa conferir':verified?'Conferido':'Anunciado';
  const link=safeLink(row.url),display=row.display||{},title=display.title||row.title,selected=state.comparison.includes(row.id);
  const name=escapeHtml(title+' · '+row.shop),id=escapeHtml(row.id);
  const installment=row.installments&&row.installment?row.installments+'x de '+currency(row.installment):row.card!=null&&row.pix!=null?currency(row.card)+' no cartão':'';
  const detail=coupon?'Sem cupom: '+currency(base):installment;
  return `<article class="offer-card ${selected?'selected':''}" aria-label="${name}"><div class="offer-top"><span class="offer-shop">${escapeHtml(row.shop)}</span><button class="favorite-button" data-action="favorite" data-id="${id}" aria-pressed="${!!row.favorite}" aria-label="${row.favorite?'Remover favorita':'Salvar oferta'}: ${name}" title="${row.favorite?'Remover favorita':'Salvar oferta'}">${star}</button></div><div class="offer-model"><h4 class="offer-title" title="${escapeHtml(row.title)}">${escapeHtml(title)}</h4>${display.specs?`<p class="offer-specs">${escapeHtml(display.specs)}</p>`:''}${display.seller?`<p class="offer-seller">${escapeHtml(display.seller)}</p>`:''}</div><div class="price-block"><div class="offer-price">${currency(amount)}</div><p class="price-condition ${coupon?'coupon-price':''}">${payment}</p>${detail?`<p class="offer-payment">${escapeHtml(detail)}</p>`:''}</div><div class="offer-actions">${link?`<a class="offer-open" href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer" aria-label="Ver oferta: ${name}">Ver oferta ${icon('M7 17 17 7M7 7h10v10')}</a>`:''}<button class="text" data-action="details" data-id="${id}" aria-label="Detalhes: ${name}">Detalhes</button></div><div class="offer-preferences"><button class="text" data-action="compare" data-id="${id}" aria-pressed="${selected}" aria-label="${selected?'Remover comparação':'Comparar'}: ${name}"><span class="compare-box" aria-hidden="true"></span>${selected?'Selecionada':'Comparar'}</button>${row.hidden?`<button class="text" data-action="hidden" data-id="${id}">Restaurar</button>`:`<span class="offer-freshness ${!current?'stale':''}" title="${label} ${time(row.checked_at||row.received_at)}">${label} · ${age(row.checked_at||row.received_at)}</span>`}</div></article>`;
}

function offerRows(group) {
  const selection=$('#offer-selection').value;
  const rows=selection?[...state.offers.values()].filter(row=>row.component_id===group.id&&row[selection]):group.offers;
  return rows.filter(filtered).sort((a,b)=>(a.effective??a.coupon_price??a.pix??a.card??a.announced??Infinity)-(b.effective??b.coupon_price??b.pix??b.card??b.announced??Infinity)).slice(0,12);
}
function renderOffers() {
  if(!state.catalog)return;
  const focused=document.activeElement?.closest('[data-action]');
  const focus=focused&&{action:focused.dataset.action,id:focused.dataset.id};
  const selection=$('#offer-selection').value;let count=0;
  const groups=state.catalog.groups.filter(g=>!$('#offer-part').value||String(g.id)===$('#offer-part').value);
  $('#piece-picker').innerHTML=`<button data-action="select-piece" data-id="" aria-pressed="${!$('#offer-part').value}"><strong>Todas as peças</strong><span>${state.catalog.groups.length} acompanhadas</span></button>`+state.catalog.groups.map(group=>`<button data-action="select-piece" data-id="${group.id}" aria-pressed="${String(group.id)===$('#offer-part').value}"><strong>${escapeHtml(group.name)}</strong><span>${group.offers.length?'A partir de '+currency(offerPrice(group.offers[0]).amount):'Sem ofertas'}</span></button>`).join('');
  $$('.selection-tabs button').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.selection===selection)));
  $('#clear-filters').hidden=!($('#offer-search').value||$('#offer-shop').value);
  if(!groups.some(group=>group.id===state.activeGroup&&offerRows(group).length))state.activeGroup=groups.find(group=>offerRows(group).length)?.id??groups[0]?.id;
  $('#offer-groups').innerHTML=groups.map(group=>{
    const rows=offerRows(group);count+=rows.length;
    const page=Math.min(state.pages.get(group.id)||0,Math.max(0,Math.ceil(rows.length/6)-1));state.pages.set(group.id,page);
    const limit=group.target!=null?` · Até ${currency(group.target)} ${group.target_payment==='pix'?'no Pix':'no total do cartão'}`:'';
    const heading=`<div><h3 tabindex="-1" id="piece-${group.id}">${escapeHtml(group.name)}</h3><p>${rows.length} ${rows.length===1?'oferta':'ofertas'}${escapeHtml(limit)}</p></div>`;
    const scan=`<button class="secondary" data-action="scan" data-id="${group.id}" aria-label="Buscar ofertas de ${escapeHtml(group.name)}" ${state.busy.has(group.id)||!group.enabled?'disabled':''}>${state.busy.has(group.id)?'Buscando nas lojas…':'Atualizar esta peça'}</button>`;
    const content=rows.length?`<div class="offer-grid">${rows.slice(page*6,page*6+6).map(card).join('')}</div><div class="pagination"><span>${page*6+1}–${Math.min(page*6+6,rows.length)} de ${rows.length} ofertas · até 12 por peça</span>${rows.length>6?`<div class="actions"><button class="secondary" data-action="offer-page" data-id="${group.id}" data-page="${page-1}" ${page===0?'disabled':''} aria-label="Página anterior de ${escapeHtml(group.name)}">Anterior</button><button class="secondary" data-action="offer-page" data-id="${group.id}" data-page="${page+1}" ${page*6+6>=rows.length?'disabled':''} aria-label="Próxima página de ${escapeHtml(group.name)}">Próxima</button></div>`:''}</div>`:`<div class="empty"><strong>${selection?'Nenhuma oferta nesta seleção':'Nenhuma oferta disponível nos filtros'}</strong><p>${selection==='favorite'?'Use a estrela para salvar ofertas que quiser acompanhar.':selection==='hidden'?'Ofertas ocultadas aparecem aqui para você restaurá-las.':'Altere os filtros ou busque novas ofertas desta peça.'}</p></div>`;
    return groups.length>1?`<details class="group" data-group="${group.id}" ${group.id===state.activeGroup?'open':''}><summary>${escapeHtml(group.name)} · ${rows.length} ofertas</summary><div class="group-heading">${heading}<div class="actions"><button class="text" data-action="piece-history" data-id="${group.id}">Histórico</button>${scan}</div></div>${content}</details>`:`<section class="group" aria-label="${escapeHtml(group.name)}"><div class="group-heading">${heading}<div class="actions"><button class="text" data-action="piece-history" data-id="${group.id}">Histórico</button>${scan}</div></div>${content}</section>`;
  }).join('')||'<div class="empty"><strong>Comece pelas peças que você quer comprar</strong><p>Cadastre uma peça ou conecte o PC para importar suas buscas.</p><button data-action="add-first-part">Adicionar peça</button></div>';
  $('#catalog-meta').textContent=`${count} ${count===1?'oferta':'ofertas'} na seleção`+(state.catalog.record_limit_reached?' · leitura parcial':'');
  renderComparison();
  if(focus)requestAnimationFrame(()=>$$('[data-action]').find(button=>button.dataset.action===focus.action&&button.dataset.id===focus.id)?.focus());
}
function renderComparison() {
  const rows=state.comparison.map(id=>state.offers.get(id)).filter(Boolean);
  $('#comparison').hidden=!rows.length;
  if(!rows.length)return;
  const open=$('#comparison details')?.open;
  $('#comparison').innerHTML=`<details class="comparison-panel" ${open?'open':''}><summary>Comparar ${rows.length} de 3 ofertas ${rows.length===1?'· selecione outra oferta da mesma peça':''}</summary><div class="section-heading"><h3>${escapeHtml(state.catalog.components.find(p=>p.id===rows[0].component_id)?.name||'Comparação')}</h3><button class="text" data-action="clear-comparison">Limpar comparação</button></div><div class="table-scroll"><table><thead><tr><th>Condição</th>${rows.map(r=>`<th>${escapeHtml(r.display?.title||r.title)}<br>${escapeHtml(r.shop)}</th>`).join('')}</tr></thead><tbody>${[['Pix','pix'],['Total no cartão','card'],['Preço anunciado','announced'],['Com cupom','coupon_price']].map(([title,key])=>`<tr><th>${title}</th>${rows.map(r=>`<td>${currency(r[key])}</td>`).join('')}</tr>`).join('')}<tr><th>Frete</th>${rows.map(()=>'<td>Não consultado</td>').join('')}</tr></tbody></table></div></details>`;
}
function renderParts() {
  $('#parts-list').innerHTML=state.catalog.components.map(part=>{const brands=typeof part.ignored_brands==='string'?JSON.parse(part.ignored_brands):part.ignored_brands||[];return `<div class="row"><div class="copy"><h3>${escapeHtml(part.name)}</h3><p>Busca: ${escapeHtml(part.query)}</p><p class="muted">${part.enabled?'Monitorando':'Pausada'}${part.target!=null?' · Até '+currency(part.target):' · Sem preço máximo'}${brands.length?' · Ignorar '+escapeHtml(brands.join(', ')):''}</p></div><div class="row-actions"><button class="secondary" data-action="edit-part" data-id="${part.id}">Editar</button><button class="text danger" data-action="delete-part" data-id="${part.id}">Excluir</button></div></div>`;}).join('')||empty('Adicione sua primeira peça','Cadastre o que quer comprar para acompanhar as ofertas.');
}
function resetPart() {$('#part-form').reset();$('#part-form').elements.id.value='';$('#part-form-title').textContent='Adicionar peça';$('#part-save').textContent='Adicionar peça';$('#part-error').textContent='';$('#capacity-field').hidden=true;$('#part-form').hidden=true;$('#add-part').hidden=false;}
function addPart(){resetPart();$('#part-form').hidden=false;$('#add-part').hidden=true;$('#part-form').elements.name.focus();}
function editPart(id) {
  const part=state.catalog.components.find(p=>p.id===id);if(!part)return;const form=$('#part-form');form.hidden=false;$('#add-part').hidden=true;
  for(const key of ['id','name','kind','query','capacity_gb','target_payment'])form.elements[key].value=part[key]??'';
  form.elements.target_text.value=part.target==null?'':(part.target/100).toLocaleString('pt-BR',{minimumFractionDigits:2,useGrouping:false});form.elements.enabled.checked=!!part.enabled;
  const brands=typeof part.ignored_brands==='string'?JSON.parse(part.ignored_brands):part.ignored_brands||[];
  $$('#brands input').forEach(input=>input.checked=brands.includes(input.value));$('#capacity-field').hidden=part.kind!=='ssd';$('#part-form-title').textContent='Editar '+part.name;$('#part-save').textContent='Salvar alterações';$('#part-cancel').hidden=false;form.scrollIntoView({block:'start'});form.elements.name.focus();
}
async function command(action,payload) {const result=await api('/api/commands',{action,payload});notice(result.detail||'Pedido na fila do PC. Você pode acompanhar em Atividade.');await reloadCatalog();return result;}
async function loadSources() {
  const open=new Set($$('#shops-list details[open]').map(detail=>detail.dataset.shop));
  const body=await api('/api/sources');
  const shopRows=local=>body.shops.filter(shop=>shop.local===local).map(shop=>{
    const statuses=body.status.filter(row=>row.name===shop.name&&row.checked_at&&(!row.component_id||state.catalog.components.some(p=>p.id===row.component_id&&p.enabled))).sort((a,b)=>Date.parse(b.checked_at)-Date.parse(a.checked_at));
    const latest=statuses[0],failed=latest&&(latest.failures>0||/bloque|falh|indispon|403/i.test(latest.detail||latest.status||''));
    return `<div class="row"><div class="copy"><h3>${escapeHtml(shop.name)} <span class="badge ${!shop.enabled?'':failed?'warn':'good'}">${!shop.enabled?'Pausada':failed?'Requer atenção':'Ativa'}</span></h3><p class="muted">${latest?'Última consulta '+age(latest.checked_at):shop.local?'Sessão consultada pelo PC':'Aguardando primeira consulta'}</p>${latest?`<details class="source-status" data-shop="${escapeHtml(shop.name)}" ${open.has(shop.name)?'open':''}><summary>Resultado das consultas</summary>${statuses.slice(0,5).map(row=>`<p>${escapeHtml(state.catalog.components.find(p=>p.id===row.component_id)?.name||shop.name)}: ${escapeHtml(row.detail||row.status||'Resultado não informado')} <span class="muted">· ${time(row.checked_at)}</span></p>`).join('')}</details>`:''}</div><button class="secondary" data-action="shop-toggle" data-name="${escapeHtml(shop.name)}" data-enabled="${shop.enabled?'false':'true'}" aria-label="${shop.enabled?'Pausar':'Ativar'} ${escapeHtml(shop.name)}">${shop.enabled?'Pausar':'Ativar'}</button></div>`;
  }).join('');
  $('#shops-list').innerHTML=`<section class="source-section"><h3>Buscas na nuvem</h3><p class="muted">Continuam com o PC desligado. Cada peça ativa entra no agendamento.</p><div class="shop-grid">${shopRows(false)}</div></section><section class="source-section"><h3>Buscas com seu Chrome</h3><p class="muted">Usam as sessões do monitor e precisam do PC conectado.</p><div class="shop-grid">${shopRows(true)}</div></section>`;
  $('#telegram-list').innerHTML=body.telegram.map(source=>`<div class="row"><div class="copy"><h3>${escapeHtml(source.name)}</h3><p>${escapeHtml(source.reference)} · ${source.enabled?'Ativo':'Pausado'}</p></div><div class="row-actions"><button class="secondary" data-action="source-toggle" data-id="${source.id}" data-enabled="${!source.enabled}">${source.enabled?'Pausar':'Ativar'}</button><button class="text danger" data-action="source-delete" data-id="${source.id}">Excluir</button></div></div>`).join('')||empty('Nenhum grupo sincronizado','Conecte o monitor do PC para acompanhar mensagens novas do Telegram.');
}

async function loadCoupons() {const first=!state.coupons;state.coupons=await api('/api/coupons');const shops=[...new Set(state.coupons.coupons.map(c=>c.shop))].sort();options($('#coupon-shop'),shops,'Todas');if(first&&shops.includes('Mercado Livre'))$('#coupon-shop').value='Mercado Livre';renderCoupons();}
function renderCoupons() {
  if(!state.coupons)return;
  const search=$('#coupon-search').value.toLowerCase().trim(),shop=$('#coupon-shop').value,group=$('#coupon-state').value;
  const open=new Set($$('#coupons-list details[open]').map(detail=>detail.dataset.code));
  const applications=new Map(state.coupons.applications.map(c=>[c.code,c])),seen=new Set();
  const coupons=state.coupons.coupons.filter(c=>{const key=(c.shop||'')+':'+(c.code||c.url);if(seen.has(key))return false;seen.add(key);return true;});
  const application=c=>c.shop==='Mercado Livre'?applications.get((c.code||'').toUpperCase()):null;
  const couponGroup=c=>application(c)?.group||'new';
  const scoped=coupons.filter(c=>(!shop||c.shop===shop)&&(!search||`${c.code||''} ${c.conditions||''} ${c.shop}`.toLowerCase().includes(search)));
  const states=[['','Todos'],['new','Novos'],['active','Ativados'],['failed','Falhas'],['disabled','Desativados']];
  $('#coupon-tabs').innerHTML=states.map(([key,label])=>`<button class="text" data-action="coupon-filter" data-state="${key}" aria-pressed="${group===key}">${label}<span>${scoped.filter(c=>!key||couponGroup(c)===key).length}</span></button>`).join('');
  const newCount=state.coupons.applications.filter(c=>c.group==='new'&&!c.disabled).length,retryCount=state.coupons.applications.filter(c=>c.retryable&&!c.disabled).length;
  const queue=!!state.catalog?.commands?.some(c=>['coupon_batch','coupon_retry'].includes(c.action)&&['pending','running'].includes(c.status));
  $('#coupon-apply').disabled=!newCount||queue;$('#coupon-retry').disabled=!retryCount||queue;
  $('#coupon-apply').textContent='Aplicar novos'+(newCount?' ('+newCount+')':'');$('#coupon-retry').textContent='Retentar falhas'+(retryCount?' ('+retryCount+')':'');
  $('#coupon-batch-context').textContent=queue?'Aplicação na fila do PC. Acompanhe o andamento em Atividade.':'Ações em lote só enviam cupons de hoje ao Mercado Livre, pelo PC.';
  $('#coupons-list').innerHTML=scoped.filter(c=>!group||couponGroup(c)===group).map(c=>{
    const applied=application(c),status=applied?.group||'new',source=safeLink(c.source_url),link=safeLink(c.url);
    return `<article class="row coupon-row"><div class="copy"><div class="coupon-heading"><h3 class="coupon-code">${escapeHtml(c.code||'Ativação pelo link')}</h3><span class="badge ${status==='active'?'good':status==='failed'?'bad':''}">${escapeHtml(applied?.label||'Encontrado')}</span></div><p class="coupon-origin"><strong>${escapeHtml(c.shop||'Loja não identificada')}</strong> · ${escapeHtml(c.source||'Fonte não informada')} · ${time(c.stamp)}</p>${applied?.failure?`<p class="coupon-failure">${escapeHtml(applied.failure)}${applied.retryable?' · pode retentar':''}</p>`:''}<details class="coupon-conditions" data-code="${escapeHtml(c.code||c.url)}"><summary>Condições${applied?' e resultado':''}</summary><p>${escapeHtml(c.conditions||'Condições não informadas')}</p>${applied?`<p>${escapeHtml(applied.detail||'Ainda não enviado à loja.')}</p><p class="muted">${escapeHtml(applied.guidance)} · ${applied.attempts||0} tentativas</p>`:'<p class="muted">O desconto só é confirmado na loja, conforme as condições.</p>'}<div class="actions">${source?`<a href="${escapeHtml(source)}" target="_blank" rel="noopener noreferrer">Ver publicação</a>`:''}${applied?`<button class="text" data-action="coupon-disable" data-code="${escapeHtml(applied.code)}" data-enabled="${!applied.disabled}">${applied.disabled?'Reativar cupom':'Desativar cupom'}</button>`:''}</div></details></div><div class="row-actions">${c.code?`<button class="secondary" data-action="copy-coupon" data-code="${escapeHtml(c.code)}" aria-label="Copiar código ${escapeHtml(c.code)}">Copiar código</button>`:''}${link?`<a class="text-link" href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer">Abrir na loja</a>`:''}${applied?.retryable?`<button class="secondary" data-action="coupon-retry" data-code="${escapeHtml(applied.code)}">Retentar</button>`:''}</div></article>`;
  }).join('')||empty(group?'Nenhum cupom nesta seleção':'Nenhum cupom encontrado hoje',search||shop?'Altere a busca ou a loja para ver outros cupons.':'Novos códigos aparecem com as fontes públicas e mensagens do Telegram.');
  $$('#coupons-list details').forEach(detail=>detail.open=open.has(detail.dataset.code));
}

async function loadHistory() {
  const id=$('#history-part').value;if(!id){$('#history-result').innerHTML=empty('Seu histórico começa com uma peça','Cadastre uma peça para acompanhar a evolução dos preços.');return;}
  const payment=$('#history-payment').value,request=++state.historyRequest;
  const result=await api('/api/history/'+id+'?payment='+payment);
  if(request!==state.historyRequest)return;
  $('#history-context').textContent=payment==='effective'?'Inclui o cupom confirmado em cada leitura e pode comparar condições de pagamento diferentes.':'Somente leituras confirmadas nesta condição de pagamento.';
  if(!result.points.length){$('#history-result').innerHTML=empty('Ainda não há preços confirmados','As buscas alimentarão o histórico desta peça. Frete e cupons não confirmados ficam fora.');return;}
  $('#history-result').innerHTML=historyView(result);
}
function historyView(result) {
  const points=result.points,max=Math.max(...points.map(p=>p.price)),min=Math.min(...points.map(p=>p.price));
  const start=Date.parse(points[0].date),end=Date.parse(points.at(-1).date),range=Math.max(1,end-start),spread=Math.max(10000,max-min);
  const x=p=>points.length===1?465:90+(Date.parse(p.date)-start)*750/range;
  const y=p=>185-(p.price-min)*125/spread;
  const date=value=>value.split('-').reverse().join('/');
  // Segmentos só entre dias consecutivos: ausência de leitura não vira linha contínua.
  const lines=points.slice(1).map((p,i)=>Date.parse(p.date)-Date.parse(points[i].date)===86400000?`<line x1="${x(points[i])}" y1="${y(points[i])}" x2="${x(p)}" y2="${y(p)}" stroke="var(--action)" stroke-width="2.5"/>`:'').join('');
  const dots=points.map(p=>`<circle cx="${x(p)}" cy="${y(p)}" r="4" fill="var(--action)"><title>${date(p.date)}: ${currency(p.price)}</title></circle>`).join('');
  return `<div class="history-surface"><div class="history-summary"><div><span>Menor preço em 30 dias</span><strong>${currency(result.minimum)}</strong></div><div><span>Mediana dos mínimos diários</span><strong>${currency(result.median)}</strong></div><p>${points.length} ${points.length===1?'dia com leitura':'dias com leitura'}</p></div><svg class="history-chart" viewBox="0 0 900 245" role="img" aria-label="${escapeHtml(points.map(p=>date(p.date)+': '+currency(p.price)).join('; '))}"><line x1="90" y1="185" x2="840" y2="185" stroke="var(--line)"/><line x1="90" y1="60" x2="840" y2="60" stroke="var(--line)" stroke-dasharray="3 5"/><text x="8" y="189" fill="var(--muted)" font-size="12">${currency(min)}</text><text x="8" y="64" fill="var(--muted)" font-size="12">${currency(min+spread)}</text>${lines}${dots}<text x="${points.length===1?465:90}" y="220" fill="var(--muted)" font-size="12">${date(points[0].date)}</text>${points.length>1?`<text x="840" y="220" text-anchor="end" fill="var(--muted)" font-size="12">${date(points.at(-1).date)}</text>`:''}</svg><p class="muted history-note">Cada ponto é o menor valor confirmado naquele dia. Dias sem leitura ficam sem linha; frete não incluído.</p></div><details class="disclosure history-records"><summary>Ver os valores por dia</summary><div class="table-scroll"><table><thead><tr><th>Dia</th><th>Menor preço confirmado</th></tr></thead><tbody>${points.map(p=>`<tr><td>${date(p.date)}</td><td>${currency(p.price)}</td></tr>`).join('')}</tbody></table></div></details>${result.truncated?'<p class="muted">Histórico parcial: limite de leituras atingido nesta consulta.</p>':''}`;
}

async function loadUsed() {
  const body=await api('/api/used');$('#used-list').innerHTML=body.searches.map(search=>{
    const rows=body.listings.filter(row=>row.search_id===search.id);return `<section class="group"><div class="group-heading"><div><h3>${escapeHtml(search.name)}</h3><p class="muted">${escapeHtml(search.city)} / ${escapeHtml(search.state)} · ${escapeHtml(search.status)}</p></div><div class="actions"><button class="secondary" data-action="olx-scan" data-id="${search.id}">Consultar no PC</button><button class="text" data-action="olx-toggle" data-id="${search.id}" data-enabled="${!search.enabled}">${search.enabled?'Pausar':'Ativar'}</button><button class="text danger" data-action="olx-delete" data-id="${search.id}">Excluir</button></div></div><div class="offer-grid">${rows.map(row=>`<article class="offer-card"><h4 class="offer-title">${escapeHtml(row.title)}</h4><div class="offer-price">${currency(row.price)}</div><p>${escapeHtml(row.location)} · ${escapeHtml(row.published_text)}</p><p class="offer-freshness">Conferido ${time(row.checked_at)}</p>${safeLink(row.url)?`<a class="offer-open" href="${escapeHtml(safeLink(row.url))}" target="_blank" rel="noopener noreferrer">Ver anúncio</a>`:''}</article>`).join('')}</div>${!rows.length?'<p class="empty">Nenhum anúncio sincronizado para esta busca.</p>':''}</section>`;
  }).join('')||'<p class="empty">Cadastre uma busca ou conecte o PC para trazer suas buscas existentes.</p>';
}
function renderActivity() {
  const labels={scan:'Buscar ofertas da peça no PC',check:'Conferir oferta',coupon_batch:'Aplicar cupons de hoje',coupon_retry:'Retentar cupons',coupon_disabled:'Alterar cupom',component_delete:'Excluir peça',source_save:'Adicionar grupo',source_toggle:'Alterar grupo',source_delete:'Excluir grupo',olx_save:'Adicionar busca OLX',olx_scan:'Consultar OLX',olx_toggle:'Alterar busca OLX',olx_delete:'Excluir busca OLX'};
  const statuses={pending:'Aguardando o PC',running:'Recebido pelo PC',done:'Concluído',failed:'Falhou'};
  const rows=state.catalog?.commands||[];
  $('#activity-list').innerHTML=rows.map(row=>{
    const stale=row.status==='running'&&Date.now()-Date.parse(row.updated_at)>600000;
    return `<div class="row"><div class="copy"><h3>${escapeHtml(labels[row.action]||row.action)}</h3><p>${escapeHtml(row.detail||'Pedido salvo na fila.')} ${stale?'Sem confirmação recente; confira o monitor local antes de tentar novamente.':''}</p><p class="muted">${time(row.created_at)}</p></div><span class="badge ${row.status==='done'?'good':'warn'}">${stale?'Sem confirmação':statuses[row.status]}</span></div>`;
  }).join('')||'<p class="empty">Nenhum pedido enviado ao PC ainda.</p>';
}
function details(row) {
  if(!row)return;
  if(!$('#offer-details').open)state.detailTrigger=document.activeElement;
  const {amount,coupon}=offerPrice(row),current=row.valid_until&&Date.parse(row.valid_until)>Date.now();
  const priceRows=[['Pix',row.pix],['Total no cartão',row.card],['Preço anunciado',row.announced],[current?'Com cupom na sua sessão':'Último preço com cupom',row.coupon_price]].filter(([,value])=>value!=null);
  const records=[['Conferência',row.status],['Origem',row.origins||row.shop],['Conferido',time(row.checked_at)],['Recebido',time(row.received_at)]];
  const duplicates=(row.duplicate_ids||[]).map(id=>state.offers.get(id)).filter(item=>item&&item.id!==row.id&&safeLink(item.url));
  $('#details-content').innerHTML=`<p class="detail-store">${escapeHtml(row.shop)}${row.seller&&row.seller.toLowerCase().replace(/\W/g,'')!==row.shop.toLowerCase().replace(/\W/g,'')?' · '+escapeHtml(row.seller):''}</p><h3>${escapeHtml(row.title)}</h3><div class="detail-price"><strong>${currency(amount)}</strong><span>${!current?'Último valor lido · precisa conferir':coupon?'Com cupom na sua sessão':row.pix!=null?'no Pix':'Conforme anunciado pela loja'}</span></div><dl class="price-breakdown">${priceRows.map(([label,value])=>`<dt>${label}</dt><dd>${currency(value)}</dd>`).join('')}<dt>Frete</dt><dd>Não consultado</dd>${row.brand?`<dt>Marca</dt><dd>${escapeHtml(row.brand)}</dd>`:''}</dl><details class="disclosure"><summary>Origem e conferência</summary><dl>${records.map(([label,value])=>`<dt>${label}</dt><dd>${escapeHtml(value)}</dd>`).join('')}</dl>${duplicates.length?`<p class="muted">Outros anúncios reunidos nesta oferta:</p>${duplicates.map(item=>`<p><a href="${escapeHtml(safeLink(item.url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title)}</a></p>`).join('')}`:''}</details>${row.message?`<details class="disclosure"><summary>Mensagem original</summary><p>${escapeHtml(row.message)}</p></details>`:''}<div class="actions detail-actions">${safeLink(row.url)?`<a class="offer-open" href="${escapeHtml(safeLink(row.url))}" target="_blank" rel="noopener noreferrer">Ver oferta</a>`:''}<button class="secondary" data-action="check" data-id="${escapeHtml(row.id)}">${state.session.cloud_shops.includes(row.shop)?'Conferir preço online':'Conferir pelo PC'}</button><button class="text" data-action="hidden" data-id="${escapeHtml(row.id)}">${row.hidden?'Restaurar oferta':'Ocultar oferta'}</button></div>`;
  if(!$('#offer-details').open)$('#offer-details').showModal();
}

async function showTab(name,updateUrl=true) {
  if(!tabIcons[name])name='offers';state.tab=name;
  if(updateUrl&&location.hash!=='#'+name)location.hash=name;
  $$('.page').forEach(page=>page.hidden=page.id!==name);$$('#navigation button').forEach(button=>button.dataset.tab===name?button.setAttribute('aria-current','page'):button.removeAttribute('aria-current'));
  document.title=({offers:'Ofertas',parts:'Peças',coupons:'Cupons',history:'Histórico',used:'Usados',sources:'Fontes',activity:'Atividade'}[name])+' · Monitor de peças';
  window.scrollTo({top:0});
  const targets={sources:'shops-list',coupons:'coupons-list',history:'history-result',used:'used-list',activity:'activity-list',offers:'offer-groups'},id=targets[name];
  if(id)loading(id);
  try {if(name==='sources')await loadSources();if(name==='coupons')await loadCoupons();if(name==='history')await loadHistory();if(name==='used')await loadUsed();if(name==='activity'||name==='offers'&&!state.catalog)await reloadCatalog();}
  catch(error){if(id)loadError(id,error);else notice(error.message);}
  finally {if(id)$('#'+id).removeAttribute('aria-busy');}
}

$('#navigation').addEventListener('click',event=>{const button=event.target.closest('button');if(button)showTab(button.dataset.tab);});
window.addEventListener('hashchange',()=>{const tab=location.hash.slice(1);if(tab!==state.tab&&state.session)showTab(tab,false);});
$('#dismiss-notice').addEventListener('click',()=>$('#notice').hidden=true);
$('#login-form').addEventListener('submit',async event=>{event.preventDefault();const button=event.submitter;const body=Object.fromEntries(new FormData(event.currentTarget));await busy(button,async()=>{const result=await api('/api/auth/'+button.value,{email:body.email,password:body.password});$('#login-message').textContent=result.detail;if(result.detail==='Conectado.')await start();});});
$('#logout').addEventListener('click',()=>busy($('#logout'),async()=>{await api('/api/auth/logout',{});signedOut();}));
$('#reload-offers').addEventListener('click',()=>busy($('#reload-offers'),reloadCatalog));
$('#activity-refresh').addEventListener('click',()=>busy($('#activity-refresh'),reloadCatalog));
for(const selector of ['#offer-search','#offer-part','#offer-shop','#offer-selection'])$(selector).addEventListener(selector==='#offer-search'?'input':'change',()=>{state.pages.clear();renderOffers();});
$$('.selection-tabs button').forEach(button=>button.addEventListener('click',()=>{$('#offer-selection').value=button.dataset.selection;state.pages.clear();renderOffers();}));
$('#clear-filters').addEventListener('click',()=>{$('#offer-search').value='';$('#offer-shop').value='';state.pages.clear();renderOffers();$('#offer-search').focus();});
$('#add-part').addEventListener('click',addPart);
$('#part-form').elements.kind.addEventListener('change',()=>$('#capacity-field').hidden=$('#part-form').elements.kind.value!=='ssd');
$('#part-cancel').addEventListener('click',()=>{resetPart();$('#add-part').focus();});
$('#part-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget,body=Object.fromEntries(new FormData(form));body.id=body.id?Number(body.id):null;body.enabled=form.elements.enabled.checked;body.ignored_brands=$$('#brands input:checked').map(input=>input.value);$('#part-error').textContent='';await busy($('#part-save'),async()=>{try{await api('/api/components',body);resetPart();await reloadCatalog();notice('Peça salva. As buscas online usam este cadastro; o PC recebe a alteração ao conectar.');}catch(error){$('#part-error').textContent=error.fields?Object.values(error.fields).join(' '):error.message;const key=error.fields&&Object.keys(error.fields)[0];form.elements[key]?.focus();throw error;}});});
$('#source-form').addEventListener('submit',event=>{event.preventDefault();const form=event.currentTarget;busy(event.submitter,async()=>{await command('source_save',Object.fromEntries(new FormData(form)));form.reset();});});
$('#used-form').addEventListener('submit',event=>{event.preventDefault();const draft=Object.fromEntries(new FormData(event.currentTarget));draft.mode='fields';draft.url='';busy(event.submitter,()=>command('olx_save',draft));});
$('#copy-url').addEventListener('click',()=>busy($('#copy-url'),async()=>{await navigator.clipboard.writeText(location.origin);notice('Endereço copiado.');}));
for(const selector of ['#coupon-search','#coupon-shop','#coupon-state'])$(selector).addEventListener(selector==='#coupon-search'?'input':'change',renderCoupons);
$('#coupon-refresh').addEventListener('click',()=>busy($('#coupon-refresh'),async()=>{const body=await api('/api/coupons/refresh',{});notice(body.status.map(s=>s.detail).join(' · '));await loadCoupons();}));
$('#coupon-apply').addEventListener('click',async()=>{await busy($('#coupon-apply'),()=>command('coupon_batch',{}));renderCoupons();});
$('#coupon-retry').addEventListener('click',async()=>{await busy($('#coupon-retry'),()=>command('coupon_retry',{}));renderCoupons();});
$('#history-refresh').addEventListener('click',()=>busy($('#history-refresh'),loadHistory));
$('#history-part').addEventListener('change',()=>loadHistory().catch(e=>notice(e.message)));$('#history-payment').addEventListener('change',()=>loadHistory().catch(e=>notice(e.message)));
$('#close-details').addEventListener('click',()=>$('#offer-details').close());
$('#offer-details').addEventListener('close',()=>{const trigger=state.detailTrigger;if(trigger?.isConnected)trigger.focus();else $('#offer-search').focus();});
$('#offer-groups').addEventListener('toggle',event=>{if(event.target.matches('details[data-group]')&&event.target.open){state.activeGroup=Number(event.target.dataset.group);$$('#offer-groups details[data-group]').forEach(group=>{if(group!==event.target)group.open=false;});}},true);
$$('#navigation button').forEach(button=>button.insertAdjacentHTML('afterbegin',icon(tabIcons[button.dataset.tab])));
document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-action]');if(!button)return;const {action,id,code,name,enabled}=button.dataset;
  if(action==='open-sources'){await showTab('sources');return;}if(action==='retry-page'){await showTab(state.tab,false);return;}if(action==='coupon-filter'){$('#coupon-state').value=button.dataset.state;renderCoupons();return;}if(action==='piece-history'){$('#history-part').value=id;await showTab('history');return;}
  if(action==='edit-part'){editPart(Number(id));return;}if(action==='details'){details(state.offers.get(id));return;}if(action==='clear-comparison'){state.comparison=[];renderOffers();return;}
  if(action==='select-piece'){$('#offer-part').value=id;state.pages.clear();renderOffers();return;}
  if(action==='offer-page'){state.pages.set(Number(id),Number(button.dataset.page));renderOffers();requestAnimationFrame(()=>{$('#piece-'+id)?.focus({preventScroll:true});$('#piece-'+id)?.scrollIntoView({block:'start'});});return;}
  if(action==='add-first-part'){await showTab('parts');addPart();return;}
  if(action==='compare'){const row=state.offers.get(id);if(state.comparison.includes(id))state.comparison=state.comparison.filter(key=>key!==id);else{if(state.comparison.length===3){notice('Compare até três ofertas.');return;}if(state.comparison.length&&state.offers.get(state.comparison[0]).component_id!==row.component_id){notice('Compare ofertas da mesma peça.');return;}state.comparison.push(id);}renderOffers();return;}
  await busy(button,async()=>{
    if(action==='scan'){state.busy.add(Number(id));renderOffers();try{const result=await api('/api/scan/'+id,{});notice(result.detail);await reloadCatalog();}finally{state.busy.delete(Number(id));renderOffers();}}
    else if(action==='favorite'||action==='hidden'){const row=state.offers.get(id);const ids=row.duplicate_ids||[id];for(const key of ids)await api('/api/preferences/'+key,{field:action,enabled:!row[action]});if(action==='hidden'&&$('#offer-details').open)$('#offer-details').close();await reloadCatalog();notice(action==='favorite'?(row.favorite?'Oferta removida das favoritas.':'Oferta salva nas favoritas.'):(row.hidden?'Oferta restaurada.':'Oferta ocultada. Você pode restaurá-la em Ocultas.'));}
    else if(action==='delete-part'){if(!confirm('Excluir esta peça do monitor?'))return;await api('/api/components/'+id,undefined,'DELETE');await reloadCatalog();notice('Peça excluída. O histórico da nuvem foi preservado.');}
    else if(action==='shop-toggle'){await api('/api/shops',{name,enabled:enabled==='true'});await loadSources();}
    else if(action==='source-toggle'||action==='source-delete'){if(action==='source-delete'&&!confirm('Excluir este grupo?'))return;await command(action.replace('-','_'),{id:Number(id),enabled:enabled==='true'});}
    else if(action==='check'){await command('check',{key:id});const row=state.offers.get(id);if(row&&$('#offer-details').open)details(row);}
    else if(action==='copy-coupon'){await navigator.clipboard.writeText(code);notice('Código copiado.');}
    else if(action==='coupon-retry'){await command('coupon_retry',{code});renderCoupons();}
    else if(action==='coupon-disable'){await command('coupon_disabled',{code,disabled:enabled==='true'});}
    else if(action.startsWith('olx-')){if(action==='olx-delete'&&!confirm('Excluir esta busca da OLX?'))return;await command(action.replace('-','_'),{id:Number(id),enabled:enabled==='true'});}
  });
});
setInterval(async()=>{if(state.session&&document.visibilityState==='visible'&&['offers','activity','sources','coupons','used'].includes(state.tab)){try{await reloadCatalog();if(state.tab==='coupons')await loadCoupons();if(state.tab==='sources')await loadSources();if(state.tab==='used')await loadUsed();}catch(error){notice(error.message);}}},60000);
start();
