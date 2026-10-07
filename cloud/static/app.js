'use strict';
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const currency = value => value == null ? 'Não informado' : (value / 100).toLocaleString('pt-BR', {style:'currency', currency:'BRL'});
const time = stamp => stamp && !Number.isNaN(Date.parse(stamp)) ? new Date(stamp).toLocaleString('pt-BR', {timeZone:'America/Sao_Paulo',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}) : 'Não informado';
const safeLink = url => { try {const u=new URL(url); return u.protocol==='https:' && !u.username && !u.password ? u.href : ''; } catch {return '';} };
const state = {tab:'offers', catalog:null, offers:new Map(), comparison:[], busy:new Set(), session:null, coupons:null};
let noticeTimer;
function notice(message) { $('#notice').textContent=message; $('#notice').hidden=false; clearTimeout(noticeTimer); noticeTimer=setTimeout(()=>$('#notice').hidden=true,9000); }
function signedOut() { $('#workspace').hidden=true; $('#login').hidden=false; state.session=null; }
async function api(path, data, method, retried=false) {
  const response=await fetch(path, {method:method || (data===undefined?'GET':'POST'),credentials:'same-origin',headers:data===undefined?{}:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});
  if(response.status===401 && !path.startsWith('/api/auth/') && !retried) {
    const refreshed=await fetch('/api/auth/refresh',{method:'POST',credentials:'same-origin'});
    if(refreshed.ok) return api(path,data,method,true);
    signedOut(); throw new Error('Sessão expirada. Entre novamente.');
  }
  const body=await response.json();
  if(!response.ok) {const error=new Error(typeof body.detail==='string'?body.detail:'Confira os campos informados.');error.fields=typeof body.detail==='object'?body.detail:null;throw error;}
  return body;
}
async function busy(button, operation) {
  const text=button.textContent;button.disabled=true;button.textContent='Aguarde…';
  try {return await operation();} catch(error) {notice(error.message);return null;} finally {button.disabled=false;if(button.textContent==='Aguarde…')button.textContent=text;}
}
function options(select, values, allLabel) {
  const current=select.value;
  select.innerHTML=(allLabel?`<option value="">${escapeHtml(allLabel)}</option>`:'')+values.map(v=>`<option value="${escapeHtml(v.value??v)}">${escapeHtml(v.label??v)}</option>`).join('');
  if([...select.options].some(o=>o.value===current))select.value=current;
}
async function start() {
  try {
    state.session=await api('/api/session');$('#login').hidden=true;$('#workspace').hidden=false;
    $('#brands').innerHTML=state.session.brands.map(brand=>`<label><input type="checkbox" name="brand" value="${escapeHtml(brand)}">${escapeHtml(brand)}</label>`).join('');
    $('#panel-url').value=location.origin;
    await reloadCatalog();
  } catch(error) {signedOut();$('#login-message').textContent=error.message;}
}
async function reloadCatalog() {
  state.catalog=await api('/api/catalog');state.offers.clear();
  for(const row of state.catalog.offers)state.offers.set(row.id,row);
  for(const group of state.catalog.groups)for(const row of group.offers)state.offers.set(row.id,row);
  state.comparison=state.comparison.filter(id=>state.offers.has(id)&&!state.offers.get(id).hidden);
  const parts=state.catalog.components.map(p=>({value:String(p.id),label:p.name}));
  options($('#offer-part'),parts,'Todas');options($('#history-part'),parts);
  options($('#offer-shop'),[...state.session.cloud_shops,...state.session.local_shops],'Todas');
  renderOffers();renderParts();renderActivity();
  const worker=state.catalog.status.find(row=>row.name==='PC conectado');
  const recent=worker&&Date.now()-Date.parse(worker.checked_at)<180000;
  $('#connection').textContent=recent?'PC sincronizado':'Sem sincronização recente do PC';
  $('#connection').className='badge '+(recent?'good':'warn');
  $('#connection').title=worker?'Última sincronização: '+time(worker.checked_at):'Conecte o monitor pela aba Fontes. O histórico da nuvem continua disponível.';
}
function filtered(row) {
  const search=$('#offer-search').value.trim().toLocaleLowerCase('pt-BR');
  return (!$('#offer-shop').value||row.shop===$('#offer-shop').value)&&(!search||`${row.title} ${row.shop} ${row.brand||''}`.toLocaleLowerCase('pt-BR').includes(search));
}
function card(row) {
  const current=row.valid_until&&Date.parse(row.valid_until)>Date.now();
  const base=row.shop==='Mercado Livre'&&row.pix==null?row.announced:(row.pix??row.card??row.announced);
  const coupon=current&&row.coupon_price>0&&row.coupon_price<(base??Infinity);
  const amount=coupon?Math.min(base??Infinity,row.coupon_price):base;
  const payment=coupon?'Com cupom na sua sessão':row.pix!=null?'No Pix':row.card!=null?'Total no cartão':'Pagamento não informado';
  const verified=(row.status||'').startsWith('Preço lido na loja')||(row.status||'').startsWith('Preço da loja lido');
  const label=!current?'Precisa conferir':verified?'Preço conferido':'Anunciado';
  const link=safeLink(row.url);
  return `<article class="offer-card" aria-label="${escapeHtml(row.title+' · '+row.shop)}"><div class="offer-top"><span class="offer-shop">${escapeHtml(row.shop)}${row.seller?' · '+escapeHtml(row.seller):''}</span><span class="badge ${current&&verified?'good':'warn'}">${label}</span></div><h4 class="offer-title">${escapeHtml(row.title)}</h4><div><div class="offer-price">${currency(amount)}<small>${payment}</small></div>${coupon?`<p class="muted">Sem cupom: ${currency(base)}</p>`:''}${row.installments&&row.installment?`<p>${row.installments}x de ${currency(row.installment)}${row.card?' · total '+currency(row.card):''}</p>`:''}<p class="offer-freshness">${verified?'Conferido':'Recebido'} ${time(row.checked_at||row.received_at)}</p></div><div class="offer-actions">${link?`<a class="offer-open" href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer">Ver oferta</a>`:''}<button class="text" data-action="details" data-id="${escapeHtml(row.id)}">Detalhes</button></div><div class="offer-preferences"><button class="secondary" data-action="favorite" data-id="${escapeHtml(row.id)}">${row.favorite?'Remover favorita':'Salvar'}</button><button class="text" data-action="hidden" data-id="${escapeHtml(row.id)}">${row.hidden?'Restaurar':'Ocultar'}</button><button class="text" data-action="compare" data-id="${escapeHtml(row.id)}">${state.comparison.includes(row.id)?'Remover comparação':'Comparar'}</button></div></article>`;
}
function renderOffers() {
  if(!state.catalog)return;
  const selection=$('#offer-selection').value;let count=0;
  const groups=state.catalog.groups.filter(g=>!$('#offer-part').value||String(g.id)===$('#offer-part').value);
  $('#offer-groups').innerHTML=groups.map(group=>{
    let rows=selection?[...state.offers.values()].filter(row=>row.component_id===group.id&&row[selection]):group.offers;
    rows=rows.filter(filtered).sort((a,b)=>(a.effective??a.coupon_price??a.pix??a.card??a.announced??Infinity)-(b.effective??b.coupon_price??b.pix??b.card??b.announced??Infinity)).slice(0,12);count+=rows.length;
    const limit=group.target!=null?` · Até ${currency(group.target)} ${group.target_payment==='pix'?'no Pix':'no total do cartão'}`:'';
    return `<section class="group" aria-label="${escapeHtml(group.name)}"><div class="group-heading"><div><h3>${escapeHtml(group.name)} · ${rows.length} ofertas</h3><p class="muted">${escapeHtml(group.query)}${escapeHtml(limit)}</p></div><button class="secondary" data-action="scan" data-id="${group.id}" ${state.busy.has(group.id)?'disabled':''}>${state.busy.has(group.id)?'Buscando nas lojas…':'Buscar ofertas desta peça'}</button></div>${rows.length?`<div class="offer-grid">${rows.map(card).join('')}</div>`:`<p class="empty">${selection?'Nenhuma oferta nesta seleção.':'Nenhuma oferta atual dentro dos filtros desta peça. Busque nas lojas ou aguarde o coletor local.'}</p>`}</section>`;
  }).join('')||'<p class="empty">Adicione suas peças na aba Peças ou conecte o monitor em Fontes para importar seus cadastros.</p>';
  $('#catalog-meta').textContent=`${count} ofertas exibidas`+(state.catalog.record_limit_reached?' · Catálogo atingiu o limite de leitura; algumas ofertas antigas podem não estar nesta consulta.':'');
  renderComparison();
}
function renderComparison() {
  const rows=state.comparison.map(id=>state.offers.get(id)).filter(Boolean);
  $('#comparison').hidden=!rows.length;
  if(!rows.length)return;
  $('#comparison').innerHTML=`<div class="comparison-panel"><div class="section-heading"><h3>Comparação · ${rows.length} de 3 ofertas</h3><button class="text" data-action="clear-comparison">Limpar comparação</button></div><table><thead><tr><th>Condição</th>${rows.map(r=>`<th>${escapeHtml(r.title)}<br>${escapeHtml(r.shop)}</th>`).join('')}</tr></thead><tbody>${[['Pix','pix'],['Total no cartão','card'],['Preço anunciado','announced'],['Com cupom','coupon_price']].map(([title,key])=>`<tr><th>${title}</th>${rows.map(r=>`<td>${currency(r[key])}</td>`).join('')}</tr>`).join('')}<tr><th>Frete</th>${rows.map(()=>'<td>Não consultado</td>').join('')}</tr></tbody></table></div>`;
}
function renderParts() {
  $('#parts-list').innerHTML=state.catalog.components.map(part=>`<div class="row"><div class="copy"><h3>${escapeHtml(part.name)}</h3><p>Busca: ${escapeHtml(part.query)}</p><p class="muted">${part.enabled?'Monitorando':'Pausada'}${part.target!=null?' · Até '+currency(part.target):' · Sem preço máximo'}${part.ignored_brands?.length?' · Ignorar '+escapeHtml(typeof part.ignored_brands==='string'?JSON.parse(part.ignored_brands).join(', '):part.ignored_brands.join(', ')):''}</p></div><div class="row-actions"><button class="secondary" data-action="edit-part" data-id="${part.id}">Editar</button><button class="text danger" data-action="delete-part" data-id="${part.id}">Excluir</button></div></div>`).join('');
}
function resetPart() {$('#part-form').reset();$('#part-form').elements.id.value='';$('#part-form-title').textContent='Adicionar peça';$('#part-save').textContent='Adicionar peça';$('#part-cancel').hidden=true;$('#part-error').textContent='';$('#capacity-field').hidden=true;}
function editPart(id) {
  const part=state.catalog.components.find(p=>p.id===id);if(!part)return;const form=$('#part-form');
  for(const key of ['id','name','kind','query','capacity_gb','target_payment'])form.elements[key].value=part[key]??'';
  form.elements.target_text.value=part.target==null?'':(part.target/100).toLocaleString('pt-BR',{minimumFractionDigits:2,useGrouping:false});form.elements.enabled.checked=!!part.enabled;
  const brands=typeof part.ignored_brands==='string'?JSON.parse(part.ignored_brands):part.ignored_brands||[];
  $$('#brands input').forEach(input=>input.checked=brands.includes(input.value));$('#capacity-field').hidden=part.kind!=='ssd';$('#part-form-title').textContent='Editar '+part.name;$('#part-save').textContent='Salvar alterações';$('#part-cancel').hidden=false;form.scrollIntoView({block:'start'});form.elements.name.focus();
}
async function command(action,payload) {await api('/api/commands',{action,payload});notice('Pedido salvo. O monitor do PC vai executá-lo quando conectado.');await reloadCatalog();}
async function loadSources() {
  const body=await api('/api/sources');
  $('#shops-list').innerHTML=body.shops.map(shop=>`<div class="row"><div class="copy"><h3>${escapeHtml(shop.name)}</h3><p class="muted">${shop.local?'Consulta no PC, com sua sessão do Chrome':'Consulta online na nuvem'} · ${shop.enabled?'Ativa':'Pausada'}</p></div><button class="secondary" data-action="shop-toggle" data-name="${escapeHtml(shop.name)}" data-enabled="${shop.enabled?'false':'true'}">${shop.enabled?'Pausar':'Ativar'}</button></div>`).join('');
  $('#telegram-list').innerHTML=body.telegram.map(source=>`<div class="row"><div class="copy"><h3>${escapeHtml(source.name)}</h3><p>${escapeHtml(source.reference)} · ${source.enabled?'Ativo':'Pausado'}</p></div><div class="row-actions"><button class="secondary" data-action="source-toggle" data-id="${source.id}" data-enabled="${!source.enabled}">${source.enabled?'Pausar':'Ativar'}</button><button class="text danger" data-action="source-delete" data-id="${source.id}">Excluir</button></div></div>`).join('')||'<p class="empty">Seus grupos aparecerão aqui após conectar o monitor do PC.</p>';
}
async function loadCoupons() {state.coupons=await api('/api/coupons');options($('#coupon-shop'),[...new Set(state.coupons.coupons.map(c=>c.shop))].sort(),'Todas');renderCoupons();}
function renderCoupons() {
  if(!state.coupons)return;const search=$('#coupon-search').value.toLowerCase().trim(),shop=$('#coupon-shop').value,group=$('#coupon-state').value;
  const applications=new Map(state.coupons.applications.map(c=>[c.code,c]));const seen=new Set();
  const rows=state.coupons.coupons.filter(c=>(!shop||c.shop===shop)&&(!search||`${c.code||''} ${c.conditions||''} ${c.shop}`.toLowerCase().includes(search)));
  $('#coupons-list').innerHTML=rows.map(c=>{
    const applied=c.shop==='Mercado Livre'?applications.get((c.code||'').toUpperCase()):null;if(group&&(!applied||applied.group!==group))return '';if(applied&&seen.has(applied.code))return '';if(applied)seen.add(applied.code);
    const link=safeLink(c.url);return `<div class="row"><div class="copy"><h3>${escapeHtml(c.code||'Ativação pelo link')} <span class="badge ${applied?.group==='active'?'good':'warn'}">${escapeHtml(c.shop||'Loja não identificada')}</span></h3><p>${escapeHtml(c.conditions||'Condições não informadas')}</p><p class="muted">${escapeHtml(c.source||'Fonte não informada')} · ${time(c.stamp)}</p>${applied?`<p><strong>${escapeHtml(applied.label)}</strong>${applied.failure?' · '+escapeHtml(applied.failure):''}</p><p>${escapeHtml(applied.detail)}</p><p class="muted">${escapeHtml(applied.guidance)} · ${applied.attempts||0} tentativas</p>`:'<p class="muted">Encontrado; desconto ainda não validado na compra.</p>'}</div><div class="row-actions">${c.code?`<button class="secondary" data-action="copy-coupon" data-code="${escapeHtml(c.code)}">Copiar código</button>`:''}${link?`<a href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer">Ver fonte</a>`:''}${applied?.retryable?`<button class="secondary" data-action="coupon-retry" data-code="${escapeHtml(applied.code)}">Retentar este cupom</button>`:''}${applied?`<button class="text" data-action="coupon-disable" data-code="${escapeHtml(applied.code)}" data-enabled="${!applied.disabled}">${applied.disabled?'Reativar':'Desativar'}</button>`:''}</div></div>`;
  }).join('')||'<p class="empty">Nenhum cupom de hoje corresponde aos filtros. Busque cupons públicos ou aguarde as mensagens do Telegram.</p>';
}
async function loadHistory() {
  const id=$('#history-part').value;if(!id){$('#history-result').innerHTML='<p class="empty">Adicione uma peça para acompanhar seu histórico.</p>';return;}
  const payment=$('#history-payment').value;const result=await api('/api/history/'+id+'?payment='+payment);
  $('#history-context').textContent=payment==='effective'?'Compara condições diferentes e inclui o preço confirmado com cupom.':'Usa somente valores informados para esta condição. Frete e cupons não confirmados ficam fora.';
  if(!result.points.length){$('#history-result').innerHTML='<p class="empty">Ainda não há leituras confirmadas nos últimos 30 dias. Os resultados aparecerão após as buscas ou a sincronização do PC.</p>';return;}
  const points=result.points,max=Math.max(...points.map(p=>p.price)),min=Math.min(...points.map(p=>p.price));
  const coords=points.map((p,i)=>`${50+i*800/Math.max(1,points.length-1)},${210-160*(p.price-min)/Math.max(1,max-min)}`).join(' ');
  $('#history-result').innerHTML=`<div class="history-summary"><div>Menor preço<strong>${currency(result.minimum)}</strong></div><div>Mediana diária<strong>${currency(result.median)}</strong></div><div>${points.length} dias com leitura</div></div><svg class="history-chart" viewBox="0 0 900 260" role="img" aria-label="Menor preço confirmado por dia"><line x1="50" y1="220" x2="850" y2="220" stroke="#d8dee8"/><polyline fill="none" stroke="#175cd3" stroke-width="3" points="${coords}"/><text x="50" y="245" fill="#49576b" font-size="14">${escapeHtml(points[0].date)}</text><text x="740" y="245" fill="#49576b" font-size="14">${escapeHtml(points.at(-1).date)}</text></svg><table><thead><tr><th>Dia</th><th>Menor preço confirmado</th></tr></thead><tbody>${points.map(p=>`<tr><td>${escapeHtml(p.date.split('-').reverse().join('/'))}</td><td>${currency(p.price)}</td></tr>`).join('')}</tbody></table>${result.truncated?'<p class="muted">Histórico parcial: limite de leituras atingido nesta consulta.</p>':''}`;
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
  $('#details-content').innerHTML=`<h3>${escapeHtml(row.title)}</h3><dl>${[['Loja',row.shop],['Vendedor',row.seller||'Não informado'],['Pix',currency(row.pix)],['Total no cartão',currency(row.card)],['Preço anunciado',currency(row.announced)],['Com cupom',currency(row.coupon_price)],['Conferência',row.status],['Marca',row.brand||'Não identificada'],['Frete','Não consultado'],['Origem',row.origins||row.shop],['Conferido',time(row.checked_at)],['Recebido',time(row.received_at)],['Mensagem',row.message||'Sem mensagem de grupo']].map(([label,value])=>`<dt>${label}</dt><dd>${escapeHtml(value)}</dd>`).join('')}</dl><div class="actions"><button data-action="check" data-id="${escapeHtml(row.id)}">Conferir no PC</button>${safeLink(row.url)?`<a class="offer-open" href="${escapeHtml(safeLink(row.url))}" target="_blank" rel="noopener noreferrer">Ver oferta</a>`:''}</div>`;
  $('#offer-details').showModal();
}
async function showTab(name) {
  state.tab=name;$$('.page').forEach(page=>page.hidden=page.id!==name);$$('#navigation button').forEach(button=>button.getAttribute('data-tab')===name?button.setAttribute('aria-current','page'):button.removeAttribute('aria-current'));
  try {if(name==='sources')await loadSources();if(name==='coupons')await loadCoupons();if(name==='history')await loadHistory();if(name==='used')await loadUsed();if(name==='activity')await reloadCatalog();} catch(error){notice(error.message);}
}
$('#navigation').addEventListener('click',event=>{const button=event.target.closest('button');if(button)showTab(button.dataset.tab);});
$('#login-form').addEventListener('submit',async event=>{event.preventDefault();const button=event.submitter;const body=Object.fromEntries(new FormData(event.currentTarget));await busy(button,async()=>{const result=await api('/api/auth/'+button.value,{email:body.email,password:body.password});$('#login-message').textContent=result.detail;if(result.detail==='Conectado.')await start();});});
$('#logout').addEventListener('click',()=>busy($('#logout'),async()=>{await api('/api/auth/logout',{});signedOut();}));
$('#reload-offers').addEventListener('click',()=>busy($('#reload-offers'),reloadCatalog));
$('#activity-refresh').addEventListener('click',()=>busy($('#activity-refresh'),reloadCatalog));
for(const selector of ['#offer-search','#offer-part','#offer-shop','#offer-selection'])$(selector).addEventListener(selector==='#offer-search'?'input':'change',renderOffers);
$('#clear-filters').addEventListener('click',()=>{$('#offer-search').value='';$('#offer-part').value='';$('#offer-shop').value='';$('#offer-selection').value='';renderOffers();});
$('#part-form').elements.kind.addEventListener('change',()=>$('#capacity-field').hidden=$('#part-form').elements.kind.value!=='ssd');
$('#part-cancel').addEventListener('click',resetPart);
$('#part-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget,body=Object.fromEntries(new FormData(form));body.id=body.id?Number(body.id):null;body.enabled=form.elements.enabled.checked;body.ignored_brands=$$('#brands input:checked').map(input=>input.value);$('#part-error').textContent='';await busy($('#part-save'),async()=>{try{await api('/api/components',body);resetPart();await reloadCatalog();notice('Peça salva. O PC receberá o cadastro quando conectado.');}catch(error){$('#part-error').textContent=error.fields?Object.values(error.fields).join(' '):error.message;const key=error.fields&&Object.keys(error.fields)[0];form.elements[key]?.focus();throw error;}});});
$('#source-form').addEventListener('submit',event=>{event.preventDefault();const form=event.currentTarget;busy(event.submitter,async()=>{await command('source_save',Object.fromEntries(new FormData(form)));form.reset();});});
$('#used-form').addEventListener('submit',event=>{event.preventDefault();const draft=Object.fromEntries(new FormData(event.currentTarget));draft.mode='fields';draft.url='';busy(event.submitter,()=>command('olx_save',draft));});
$('#copy-url').addEventListener('click',()=>busy($('#copy-url'),async()=>{await navigator.clipboard.writeText(location.origin);notice('Endereço copiado.');}));
for(const selector of ['#coupon-search','#coupon-shop','#coupon-state'])$(selector).addEventListener(selector==='#coupon-search'?'input':'change',renderCoupons);
$('#coupon-refresh').addEventListener('click',()=>busy($('#coupon-refresh'),async()=>{const body=await api('/api/coupons/refresh',{});notice(body.status.map(s=>s.detail).join(' · '));await loadCoupons();}));
$('#coupon-apply').addEventListener('click',()=>busy($('#coupon-apply'),()=>command('coupon_batch',{})));
$('#coupon-retry').addEventListener('click',()=>busy($('#coupon-retry'),()=>command('coupon_retry',{})));
$('#history-refresh').addEventListener('click',()=>busy($('#history-refresh'),loadHistory));
$('#history-part').addEventListener('change',()=>loadHistory().catch(e=>notice(e.message)));$('#history-payment').addEventListener('change',()=>loadHistory().catch(e=>notice(e.message)));
$('#close-details').addEventListener('click',()=>$('#offer-details').close());
document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-action]');if(!button)return;const {action,id,code,name,enabled}=button.dataset;
  if(action==='edit-part'){editPart(Number(id));return;}if(action==='details'){details(state.offers.get(id));return;}if(action==='clear-comparison'){state.comparison=[];renderOffers();return;}
  if(action==='compare'){const row=state.offers.get(id);if(state.comparison.includes(id))state.comparison=state.comparison.filter(key=>key!==id);else{if(state.comparison.length===3){notice('Compare até três ofertas.');return;}if(state.comparison.length&&state.offers.get(state.comparison[0]).component_id!==row.component_id){notice('Compare ofertas da mesma peça.');return;}state.comparison.push(id);}renderOffers();return;}
  await busy(button,async()=>{
    if(action==='scan'){state.busy.add(Number(id));renderOffers();try{const result=await api('/api/scan/'+id,{});notice(result.detail);await reloadCatalog();}finally{state.busy.delete(Number(id));renderOffers();}}
    else if(action==='favorite'||action==='hidden'){const row=state.offers.get(id);const ids=row.duplicate_ids||[id];for(const key of ids)await api('/api/preferences/'+key,{field:action,enabled:!row[action]});await reloadCatalog();}
    else if(action==='delete-part'){if(!confirm('Excluir esta peça do monitor?'))return;await api('/api/components/'+id,undefined,'DELETE');await reloadCatalog();notice('Peça excluída. O histórico da nuvem foi preservado.');}
    else if(action==='shop-toggle'){await api('/api/shops',{name,enabled:enabled==='true'});await loadSources();}
    else if(action==='source-toggle'||action==='source-delete'){if(action==='source-delete'&&!confirm('Excluir este grupo?'))return;await command(action.replace('-','_'),{id:Number(id),enabled:enabled==='true'});}
    else if(action==='check'){await command('check',{key:id});}
    else if(action==='copy-coupon'){await navigator.clipboard.writeText(code);notice('Código copiado.');}
    else if(action==='coupon-retry'){await command('coupon_retry',{code});}
    else if(action==='coupon-disable'){await command('coupon_disabled',{code,disabled:enabled==='true'});}
    else if(action.startsWith('olx-')){if(action==='olx-delete'&&!confirm('Excluir esta busca da OLX?'))return;await command(action.replace('-','_'),{id:Number(id),enabled:enabled==='true'});}
  });
});
setInterval(async()=>{if(state.session&&document.visibilityState==='visible'&&['offers','activity','sources','coupons','used'].includes(state.tab)){try{await reloadCatalog();if(state.tab==='coupons')await loadCoupons();if(state.tab==='sources')await loadSources();if(state.tab==='used')await loadUsed();}catch(error){notice(error.message);}}},60000);
start();
