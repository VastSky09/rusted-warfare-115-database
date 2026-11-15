// Isolated DOM-event harness, not a browser or layout renderer. No network.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const script=fs.readFileSync(path.join(root,'tools/combat-app.js'),'utf8');
const readJson=id=>JSON.parse(html.match(new RegExp('<script type="application/json" id="'+id+'">([\\s\\S]*?)</script>'))[1]);
const db=readJson('db'),combat=readJson('combat-db');
class Element{
 constructor(id,owner){this.id=id;this.owner=owner;this.value='';this.textContent='';this.listeners={};this._html='';this.dataset={}}
 set innerHTML(value){this._html=value;this.buttons=null;if(this.id==='detail'){this.owner.state=null;this.owner.entry=null}}
 get innerHTML(){return this._html}
 addEventListener(name,fn){this.listeners[name]=fn}
 dispatch(name){assert.ok(this.listeners[name],`${this.id}: ${name} handler missing`);this.listeners[name]({target:this})}
 querySelectorAll(selector){assert.equal(selector,'[data-id]');return this.buttons??= [...this._html.matchAll(/<button\b[^>]*data-id="([^"]+)"/g)].map(m=>{const b=new Element('button',this.owner);b.dataset.id=m[1];return b})}
}
class Document{
 constructor(){this.elements=new Map();this.state=null;this.entry=null;for(const id of ['find','category','prio','list','detail','count','num-tech','num-transform','db','combat-db'])this.elements.set(id,new Element(id,this));this.elements.get('db').textContent=JSON.stringify(db);this.elements.get('combat-db').textContent=JSON.stringify(combat)}
 getElementById(id){if(id==='combat-entry'){
  if(!this.entry){this.entry=new Element(id,this);this.entry.open=/<details id="combat-entry" class="combat-entry" open>/.test(this.elements.get('detail').innerHTML)}
  return this.entry;
 }if(id==='combat-state'){
  const markup=this.elements.get('detail').innerHTML;
  if(!markup.includes('id="combat-state"'))return null;
  if(!this.state){this.state=new Element(id,this);this.state.value=markup.match(/<option value="([^"]+)" selected/)?.[1]||''}
  return this.state;
 }return this.elements.get(id)||null}
}
const document=new Document();
vm.runInNewContext(script,{document,console,Intl},{timeout:3000});
assert.equal(document.getElementById('count').textContent,'91 / 91');
assert.equal(document.getElementById('num-tech').textContent,212);
let selections=0,states=0;
for(const unit of db.units){
 const button=document.getElementById('list').querySelectorAll('[data-id]').find(b=>b.dataset.id===unit.object_id);
 assert.ok(button?.listeners.click,unit.native_id);
 button.dispatch('click');selections++;
 const markup=document.getElementById('detail').innerHTML;
 assert.ok(markup.includes(unit.native_id));
 assert.ok(markup.includes('战斗属性与行为'));
 assert.ok(markup.includes('科技与获取关系'));
 assert.equal(document.getElementById('combat-entry').open,false,'new unit must default collapsed');
 const entry=document.getElementById('combat-entry');entry.open=true;entry.dispatch('toggle');
 assert.ok(!/\bNaN\b|\bundefined\b|\[object Object\]/.test(markup),unit.native_id);
 for(const state of combat.units[unit.native_id].states||[]){
  const select=document.getElementById('combat-state');
  assert.ok(select,unit.native_id+' state selector');
  select.value=String(state.id);select.dispatch('change');states++;
  assert.ok(document.getElementById('detail').innerHTML.includes('value="'+state.id+'" selected'));
  assert.equal(document.getElementById('combat-entry').open,true,'state change must keep details expanded');
 }
}
const search=document.getElementById('find');search.value='没有这个单位';search.dispatch('input');
assert.equal(document.getElementById('count').textContent,'0 / 91');
assert.ok(document.getElementById('list').innerHTML.includes('清空搜索'));
search.value='mechArtillery';search.dispatch('input');assert.equal(document.getElementById('count').textContent,'1 / 91');
search.value='';search.dispatch('input');
const category=document.getElementById('category');category.value='建筑';category.dispatch('change');
assert.equal(document.getElementById('count').textContent,db.units.filter(u=>u.category==='建筑').length+' / 91');
// Catalogue names must never be interpreted as HTML.
db.units[0].name_zh='<img src=x onerror="attack()">';
const safeDoc=new Document();safeDoc.elements.get('db').textContent=JSON.stringify(db);
vm.runInNewContext(script,{document:safeDoc,console,Intl},{timeout:3000});
assert.ok(!safeDoc.getElementById('list').innerHTML.includes('<img'));
assert.ok(safeDoc.getElementById('list').innerHTML.includes('&lt;img'));
// Enter from a research view, select another unit, then refresh or change views.
const navDoc=new Document();
const viewLinks=['a','b','c'].map(view=>({dataset:{workspaceView:view},href:''}));
navDoc.querySelectorAll=selector=>{assert.equal(selector,'[data-workspace-view]');return viewLinks};
const navLocation={href:'https://example.test/index.html?unit=c_tank',search:'?unit=c_tank'};
const navHistory={replaceState(_state,_title,address){navLocation.href=String(address);navLocation.search=new URL(navLocation.href).search}};
vm.runInNewContext(script,{document:navDoc,console,Intl,URL,URLSearchParams,location:navLocation,history:navHistory},{timeout:3000});
assert.ok(navDoc.getElementById('detail').innerHTML.includes('<code>c_tank</code>'));
assert.ok(viewLinks.every(link=>link.href.endsWith('&unit=c_tank')));
navDoc.getElementById('list').querySelectorAll('[data-id]').find(button=>button.dataset.id===db.units.find(unit=>unit.native_id==='c_artillery').object_id).dispatch('click');
assert.equal(new URL(navLocation.href).searchParams.get('unit'),'c_artillery');
assert.ok(viewLinks.every(link=>link.href.endsWith('&unit=c_artillery')));
assert.equal(navDoc.getElementById('combat-entry').open,false);
console.log(JSON.stringify({unit_selections:selections,state_selections:states,defaults_collapsed:true,state_change_keeps_expanded:true,search_empty_and_category:true,html_escaped:true,deep_link_and_current_unit_navigation:true,layout_verified:false}));
