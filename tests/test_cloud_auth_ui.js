// Concurrent 401s must share one refresh, including the failure path.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
async function scenario(ok) {
  let refreshes=0,release;const gate=new Promise(resolve=>release=resolve),nodes=new Map(),calls=new Map();
  const node=s=>{if(!nodes.has(s))nodes.set(s,{hidden:false,textContent:''});return nodes.get(s);};
  const fetch=async path=>{
    if(path==='/api/auth/refresh'){refreshes++;await gate;return {ok};}
    const count=(calls.get(path)||0)+1;calls.set(path,count);
    return {status:count===1?401:200,ok:count>1,json:async()=>({path})};
  };
  const context=vm.createContext({document:{querySelector:node,querySelectorAll:()=>[]},fetch,URL,Date,console,AbortSignal});
  const source=fs.readFileSync('cloud/static/app.js','utf8');vm.runInContext(source.slice(0,source.indexOf("$('#navigation').addEventListener")),context);
  const run=code=>vm.runInContext(code,context),pending=run("Promise.allSettled([api('/api/catalog'),api('/api/sources'),api('/api/coupons')])");
  await new Promise(resolve=>setImmediate(resolve));assert.equal(refreshes,1);release();
  const results=await pending;
  assert.equal(results.filter(result=>result.status==='fulfilled').length,ok?3:0);
  if(!ok){assert.equal(node('#login').hidden,false);assert.equal(node('#workspace').hidden,true);}
}
async function networkErrors() {
  const context=vm.createContext({document:{querySelector:()=>({}),querySelectorAll:()=>[]},URL,Date,console,AbortSignal});
  const source=fs.readFileSync('cloud/static/app.js','utf8');vm.runInContext(source.slice(0,source.indexOf("$('#navigation').addEventListener")),context);
  const run=code=>vm.runInContext(code,context);
  context.fetch=async()=>{throw new TypeError('Failed to fetch');};
  await assert.rejects(run("api('/api/catalog')"),/conexão com o servidor/);
  await assert.rejects(run("api('/api/commands',{action:'coupon_batch'})"),/confirmar a resposta.*antes de enviar novamente/);
  context.fetch=async(path,options)=>new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error('Signal was not enforced')),50);
    options.signal.addEventListener('abort',()=>{clearTimeout(timer);reject(options.signal.reason);},{once:true});
  });
  await assert.rejects(run("apiFetch('/api/catalog',{method:'GET'},5)"),/demorou para responder/);
}
(async()=>{await scenario(true);await scenario(false);await networkErrors();console.log('Concurrent session renewal: success and expiration passed.');})().catch(error=>{console.error(error);process.exitCode=1;});
