// Concurrent responses and background refresh must not interrupt an active interaction.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const nodes=new Map(),blocked=new Set();
function node(key){if(['dialog[open]','form:focus-within','[aria-busy=true]'].includes(key))return blocked.has(key)?{}:null;if(!nodes.has(key))nodes.set(key,{innerHTML:'',textContent:'',contains:()=>false});return nodes.get(key);}
const context=vm.createContext({document:{querySelector:node,querySelectorAll:()=>[],activeElement:null,visibilityState:'visible'},Date,URL,console});
const source=fs.readFileSync('cloud/static/app.js','utf8');vm.runInContext(source.slice(0,source.indexOf("$('#navigation').addEventListener")),context);
const run=code=>vm.runInContext(code,context);
(async()=>{
  const requests=[];context.request=()=>new Promise((resolve,reject)=>requests.push({resolve,reject}));
  run("api=()=>request();state.session={};state.catalog={components:[],commands:[],status:[]}");
  const first=run('loadSources()'),second=run('loadSources()');
  requests[1].resolve({shops:[],status:[],telegram:[{id:1,name:'Mais recente',enabled:true}]});await second;
  requests[0].resolve({shops:[],status:[],telegram:[]});await first;
  assert.match(node('#telegram-list').innerHTML,/Mais recente/);
  const old=run('loadSources()'),latest=run('loadSources()');
  requests[3].resolve({shops:[],status:[],telegram:[]});await latest;
  requests[2].reject(new Error('Resposta antiga'));await old;
  run('renderUsed=()=>{}');
  const usedOld=run('loadUsed()'),usedNew=run('loadUsed()');
  requests[5].resolve({version:2});await usedNew;requests[4].resolve({version:1});await usedOld;
  assert.equal(run('state.used.version'),2);
  let reads=0,finish;context.catalog=()=>{reads++;return new Promise(resolve=>finish=resolve)};
  run("reloadCatalog=()=>catalog();state.tab='offers'");
  for(const selector of ['dialog[open]','form:focus-within','[aria-busy=true]']){blocked.add(selector);await run('refreshBackground()');blocked.clear();}
  assert.equal(reads,0);
  const poll=run('refreshBackground()');await run('refreshBackground()');assert.equal(reads,1);
  finish();await poll;assert.equal(run('state.polling'),false);
  const signedOut=run('loadUsed()');run('state.session=null;state.usedRequest++');requests[6].resolve({version:3});await signedOut;
  assert.equal(run('state.used.version'),2);
  console.log('Atualizações: concorrência, resposta antiga, interação ativa e sessão protegidas.');
})().catch(error=>{console.error(error);process.exitCode=1});
