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
  const context=vm.createContext({document:{querySelector:node,querySelectorAll:()=>[]},fetch,URL,Date,console});
  const source=fs.readFileSync('cloud/static/app.js','utf8');vm.runInContext(source.slice(0,source.indexOf("$('#navigation').addEventListener")),context);
  const run=code=>vm.runInContext(code,context),pending=run("Promise.allSettled([api('/api/catalog'),api('/api/sources'),api('/api/coupons')])");
  await new Promise(resolve=>setImmediate(resolve));assert.equal(refreshes,1);release();
  const results=await pending;
  assert.equal(results.filter(result=>result.status==='fulfilled').length,ok?3:0);
  if(!ok){assert.equal(node('#login').hidden,false);assert.equal(node('#workspace').hidden,true);}
}
(async()=>{await scenario(true);await scenario(false);console.log('Concurrent session renewal: success and expiration passed.');})().catch(error=>{console.error(error);process.exitCode=1;});
