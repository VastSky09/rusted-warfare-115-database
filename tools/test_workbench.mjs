// Run actual shared renderers against a narrow, read-only VM fixture.
// Usage: node tools/test_workbench.mjs [--root <repository-directory>]
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(process.argv[2]==='--root'?process.argv[3]:process.argv[2]||path.join(here,'..'));
const read=f=>fs.readFileSync(path.join(root,f),'utf8');
const data=()=>JSON.parse(read('ui/data.js').replace(/^window\.RW_DATA=/,'').replace(/;\s*$/,''));
const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const list=x=>Array.isArray(x)?x:x?[x]:[];
function render(unit,dataset=data()){
  const app={innerHTML:'',className:''},caption={innerHTML:''};let captured;
  const ctx={console,Intl,URLSearchParams,location:{hash:'#view=a&unit='+encodeURIComponent(unit),search:''},history:{replaceState(){}},RW_DATA:dataset,
    document:{getElementById(id){if(id==='app')return app;if(id==='scheme-caption')return caption;return null},querySelectorAll(){return []},querySelector(){return null},addEventListener(){}}};
  ctx.window=ctx;vm.createContext(ctx);
  for(const f of ['ui/views/compact.js','ui/views/path.js','ui/views/compare.js'])vm.runInContext(read(f),ctx,{filename:f,timeout:3000});
  const original=ctx.RWViews.a;ctx.RWViews.a=api=>{captured=api;return original(api)};
  vm.runInContext(read('ui/app.js'),ctx,{filename:'ui/app.js',timeout:3000});
  if(!captured)throw new Error('Actual research-view API was not called');
  return {api:captured,html:app.innerHTML,compare:()=>ctx.RWViews.c({...captured,compareIds:[unit]})};
}
const checks=[];
function check(name,pass,detail){checks.push({name,pass:!!pass,...(detail?{detail}:{} )})}
function contains(text,expected){return text.includes(esc(expected))}
for(const uid of ['experimentalDropship','heavySub','nautilusSubmarine','missileShip']){
  const d=data(),p=d.combat.units[uid],x=render(uid,d),notes=x.api.weaponNotes(uid),comparison=x.compare();
  let constraints=0;
  for(const w of p.weapons){
    if(w.condition){constraints++;check(`${uid}/${w.id}:global-condition`,contains(notes,w.condition),w.condition)}
    for(const [domain,value] of Object.entries(w.domain_conditions||{})){constraints++;check(`${uid}/${w.id}:domain-${domain}`,contains(notes,value),value);check(`${uid}/${w.id}:domain-condition-in-comparison`,contains(comparison,value),value)}
    for(const value of list(w.target_constraints)){constraints++;check(`${uid}/${w.id}:target-constraint`,contains(notes,value),value);check(`${uid}/${w.id}:target-constraint-in-comparison`,contains(comparison,value),value)}
  }
  check(`${uid}:real-profile-has-condition-fixture`,constraints>0);
  for(const [domain,s] of Object.entries(p.summary.domains||{}))for(const value of list(s.conditions))check(`${uid}:summary-${domain}`,contains(x.api.battle(uid),value),value);
}
// Sentinels ensure the helper reads fields rather than surviving on coincidentally
// duplicated derived.conditions or summary text. This changes memory only.
const markerData=data(),marker=markerData.combat.units.experimentalDropship;
marker.weapons[0].condition='AUDIT global <condition> & "quoted"';
marker.weapons[0].domain_conditions={ground:'AUDIT ground <condition> & "quoted"'};
marker.weapons[0].target_constraints=['AUDIT target <condition> & "quoted"'];
marker.weapons[0].derived.conditions=[];
marker.summary.domains.ground.conditions=['AUDIT summary <condition> & "quoted"'];
const marked=render('experimentalDropship',markerData),notes=marked.api.weaponNotes('experimentalDropship');
for(const [key,value] of [['global',marker.weapons[0].condition],['domain',marker.weapons[0].domain_conditions.ground],['target',marker.weapons[0].target_constraints[0]]])check('independent-escaped-'+key,contains(notes,value)&&!notes.includes(value),value);
check('independent-escaped-summary',contains(marked.api.battle('experimentalDropship'),marker.summary.domains.ground.conditions[0]));
const result={root,scope:'actual ui/app.js helper and views in narrow VM fixture; not browser layout or game validation',checks,passed:checks.filter(x=>x.pass).length,failed:checks.filter(x=>!x.pass).length};
console.log(JSON.stringify(result,null,2));
if(result.failed)process.exitCode=1;
