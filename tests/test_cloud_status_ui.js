const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const context=vm.createContext({document:{querySelector:()=>({}),querySelectorAll:()=>[]},Date,URL});
const source=fs.readFileSync('cloud/static/app.js','utf8');
vm.runInContext(source.slice(0,source.indexOf("$('#navigation').addEventListener")),context);
assert.equal(vm.runInContext("sourceResultText({discovered:22,detail:'22 anúncios encontrados · 12 preços conferidos',reason:'Uma leitura falhou'})",context),'22 anúncios encontrados · 12 preços conferidos · Uma leitura falhou');
assert.equal(vm.runInContext("sourceResultText({discovered:0,detail:'Consulta indisponível',reason:'HTTP 403'})",context),'HTTP 403');
assert.equal(vm.runInContext("sourceResultText({detail:'0 ofertas consultadas'})",context),'0 ofertas consultadas');
console.log('Source status: successful readings stay visible with partial errors; blocked requests preserve the reason.');
