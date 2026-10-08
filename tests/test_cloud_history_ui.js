// History must reflect the last selection, even if responses arrive out of order.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const nodes=new Map(),node=s=>{if(!nodes.has(s))nodes.set(s,{value:'',hidden:true,textContent:'',innerHTML:'',attrs:{},setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];}});return nodes.get(s);};
const context=vm.createContext({document:{querySelector:node,querySelectorAll:()=>[],activeElement:null},URL,Date,console});
const source=fs.readFileSync('cloud/static/app.js','utf8');vm.runInContext(source.slice(0,source.indexOf("$('#navigation').addEventListener")),context);
const run=code=>vm.runInContext(code,context),pending=[];
context.read=()=>new Promise((resolve,reject)=>pending.push({resolve,reject}));run('api=()=>read()');
const reading=price=>({minimum:price,median:price,points:[{date:'2026-10-08',price}]});
(async()=>{
  node('#history-part').value='1';node('#history-payment').value='pix';
  const first=run('loadHistory()');assert.equal(node('#history-loading').hidden,false);assert.equal(node('#history-result').attrs['aria-busy'],'true');
  node('#history-payment').value='card';const second=run('loadHistory()');
  pending[1].resolve(reading(300000));await second;
  assert.match(node('#history-result').innerHTML,/3\.000,00/);assert.equal(node('#history-loading').hidden,true);
  pending[0].resolve(reading(200000));await first;assert.doesNotMatch(node('#history-result').innerHTML,/2\.000,00/);
  const failed=run('loadHistory()');pending[2].reject(new Error('Erro de teste'));await failed;
  assert.match(node('#history-result').innerHTML,/Tentar novamente/);assert.doesNotMatch(node('#history-result').innerHTML,/history-chart/);assert.equal(node('#history-loading').hidden,true);
  const old=run('loadHistory()'),latest=run('loadHistory()');pending[3].reject(new Error('Resposta antiga falhou'));await old;
  assert.equal(node('#history-loading').hidden,false);assert.equal(node('#history-result').attrs['aria-busy'],'true');
  pending[4].resolve(reading(400000));await latest;assert.match(node('#history-result').innerHTML,/4\.000,00/);
  node('#history-part').value='';await run('loadHistory()');assert.match(node('#history-result').innerHTML,/Cadastre uma peça/);assert.equal(node('#history-loading').hidden,true);
  console.log('History: loading, latest response, failure, retry and empty state passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
