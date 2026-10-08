// Favorites respond before the network and reconcile partial failure without false success.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('cloud/static/app.js','utf8');
async function scenario(failure, expire=false) {
  const context=vm.createContext({document:{querySelector:()=>({}),querySelectorAll:()=>[],activeElement:null},URL,Date,console});
  vm.runInContext(source.slice(0,source.indexOf("$('#navigation').addEventListener")),context);
  const run=code=>vm.runInContext(code,context);
  run(`state.session={};state.catalog={groups:[{offers:[]}]};
    const a={id:'a',favorite:false,duplicate_ids:['a','b']},b={id:'b',favorite:true};
    state.offers=new Map([['a',a],['b',b]]);state.catalog.groups[0].offers=[{...a}];
    let renders=0,reloads=0,messages=[];renderOffers=()=>renders++;notice=message=>messages.push(message);
    reloadCatalog=async()=>{reloads++;};`);
  let release,calls=0;const gate=new Promise(resolve=>release=resolve);
  context.save=async()=>{calls++;if(calls===1)await gate;if(failure&&calls===2){if(expire)run('state.session=null;state.catalog=null;state.offers.clear();');throw new Error('Falha de teste');}};
  run('api=()=>save()');
  const saving=run("saveFavorite('a')");
  assert.equal(run("state.offers.get('a').favorite"),true);
  assert.equal(run('state.catalog.groups[0].offers[0].favorite'),true);
  assert.equal(run("state.pendingFavorites.has('a')"),true);
  assert.match(run("card(state.offers.get('a'))"),/disabled aria-busy="true"/);
  await run("saveFavorite('a')");assert.equal(calls,1,'Repeated click must not send again');
  release();await saving;
  assert.equal(run('state.pendingFavorites.size'),0);
  if(failure){
    assert.equal(run('messages[0]'),'Falha de teste');
    if(!expire){assert.equal(run("state.offers.get('a').favorite"),false);assert.equal(run("state.offers.get('b').favorite"),true);assert.equal(run('reloads'),1);}
    else assert.equal(run('reloads'),0);
  } else {assert.equal(run('reloads'),0);assert.equal(run('messages[0]'),'Oferta salva nas favoritas.');}
}
(async()=>{await scenario(false);await scenario(true);await scenario(true,true);console.log('Favorites: immediate state, repeated click, grouped rollback and session expiration passed.');})().catch(error=>{console.error(error);process.exitCode=1;});
