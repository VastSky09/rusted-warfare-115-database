(()=>{
'use strict';
const {db,combat}=window.RW_DATA,units=db.units,byNative=new Map(units.map(u=>[u.native_id,u]));
const e=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const n=x=>typeof x==='number'&&Number.isFinite(x)?new Intl.NumberFormat('zh-CN',{maximumFractionDigits:2}).format(x):'待核实';
const list=x=>Array.isArray(x)?x:x?[x]:[];
const price=u=>u?.known_acquisition_prices?'<span class="cost">'+e(u.known_acquisition_prices)+' $</span>':'<span class="muted">未记录</span>';
const aliases={c_tank:['普坦','普通坦克'],heavyTank:['重坦'],heavyInterceptor:['重拦'],mechArtillery:['火炮甲','炮甲'],mechMinigun:['机枪甲'],plasmaTank:['等离子'],c_mammothTank:['猛犸'],gunShip:['武直'],c_artillery:['自炮'],mechFactory:['机甲厂'],landFactory:['陆厂'],airFactory:['空厂']};
let state={view:'a',unit:'landFactory',query:'',filter:'all',history:[],compareIds:['mechArtillery','c_artillery','mechMinigun'],notice:''};
const params=new URLSearchParams(location.hash.slice(1)),searchParams=new URLSearchParams(location.search);
const initialView=params.get('view')??searchParams.get('view'),initialUnit=params.get('unit')??searchParams.get('unit');
if(['a','b','c'].includes(initialView))state.view=initialView;if(byNative.has(initialUnit))state.unit=initialUnit;
function getProfile(id){return combat.units[id]}
function getUnit(id){return byNative.get(id)}
function relations(id){return {incoming:db.tech.filter(x=>x.target_native_id===id),outgoing:db.tech.filter(x=>x.source_native_id===id),xIn:db.transform.filter(x=>x.target_native_id===id),xOut:db.transform.filter(x=>x.source_native_id===id)}}
function link(id,label,cls=''){return '<button class="unit-link '+e(cls)+'" data-unit="'+e(id)+'">'+e(label??getUnit(id)?.name_zh??id)+'</button>'}
function fullBattleLink(id=state.unit,label='查看完整战斗属性与状态'){return '<a class="unit-link full-battle-link" href="index.html?unit='+e(encodeURIComponent(id))+'">'+e(label)+'</a>'}
function phase(s){const value=String(s||'').split('-').slice(-1)[0];return value.startsWith('mode_')?'模式切换':value||'未记录状态'}
function money(x){return x===''?'<span class="muted">未记录</span>':Number(x)===0?'<span class="muted">免费</span>':'<span class="cost">'+n(Number(x))+' $</span>'}
function rows(data,outbound){
 if(!data.length)return '<div class="empty"><strong>没有对应关系</strong>当前公开范围未记录此类生产、获取或转换。</div>';
 const groups=new Map();for(const r of data){const id=outbound?r.target_native_id:r.source_native_id,key=[id,r.relation,r.cost_credits].join('|');if(!groups.has(key))groups.set(key,{id,name:outbound?r.target_name:r.source_name,kind:r.relation,cost:r.cost_credits,phases:new Set(),ids:[]});const g=groups.get(key);g.phases.add(phase(r.source_state)+' → '+phase(r.target_state));g.ids.push(r.relation_id)}
 return '<div class="relation-scroll"><table class="relation-table"><thead><tr><th scope="col">'+(outbound?'产出对象':'来源对象')+'</th><th scope="col">方式／阶段</th><th scope="col">费用</th></tr></thead><tbody>'+[...groups.values()].map(g=>'<tr><td>'+link(g.id,g.name)+'</td><td><span class="relation-kind">'+e(g.kind)+'</span><div class="phase">'+e([...g.phases].join(' · '))+'</div></td><td>'+money(g.cost)+'</td></tr>').join('')+'</tbody></table></div>';
}
function matches(){return units.filter(u=>{const p=getProfile(u.native_id),movement=p.behavior.movement_type;const cat=u.category==='建筑'?'building':movement==='AIR'?'air':movement==='WATER'?'water':'ground';return (state.filter==='all'||state.filter===cat)&&(!state.query||[u.name_zh,u.native_id,...aliases[u.native_id]||[]].join(' ').toLowerCase().includes(state.query.trim().toLowerCase()))})}
function catalogRows(){const visible=matches();return visible.length?visible.map(u=>'<button class="catalog-unit '+(u.native_id===state.unit?'active':'')+'" aria-pressed="'+(u.native_id===state.unit)+'" data-unit="'+e(u.native_id)+'"><span><b>'+e(u.name_zh)+'</b><small>'+e(u.category)+' · '+e(u.native_id)+'</small></span>'+(u.native_id===state.unit?'<span class="selected-mark">当前</span>':'')+'</button>').join(''):'<p class="empty"><strong>没有找到对应单位</strong>试试中文名、内部名或常用简称。</p>'}
function sidebar(){return '<section class="catalog" aria-label="单位目录"><div class="catalog-head"><div class="catalog-title"><strong>原版资料库</strong><span class="catalog-count">'+matches().length+' / '+units.length+'</span></div><label class="sr-only" for="unit-search">搜索单位</label><input class="catalog-search" id="unit-search" type="search" value="'+e(state.query)+'" placeholder="搜索单位、重拦、火炮甲…"><div class="catalog-filters">'+[['all','全部'],['ground','陆军'],['air','空军'],['water','海军'],['building','建筑']].map(([id,label])=>'<button data-filter="'+id+'" aria-pressed="'+(state.filter===id)+'">'+label+'</button>').join('')+'</div></div><div class="unit-results">'+catalogRows()+'</div></section>'}
function toolbar(){return '<nav class="toolbar" aria-label="访问路径"><button class="btn small" data-back '+(!state.history.length?'disabled':'')+'>返回上一对象</button><div class="trail"><span>最近访问</span>'+state.history.slice(-3).map(x=>link(x.unit)).join('<span aria-hidden="true">/</span>')+'<span>'+e(getUnit(state.unit).name_zh)+'</span></div></nav>'}
function info(){const u=getUnit(state.unit);return '<details class="info-details"><summary>资料编号与研究范围</summary><p>'+e(u.native_id)+' · '+e(u.object_id)+' · '+e(u.priority)+' · '+e(u.scope)+'</p><p>采用当前原版资料快照；价格受获取方式和状态影响，关系记录不保证任何局面均可执行。</p></details>'}
function weaponNotes(id){const p=getProfile(id);return p.weapons.length?p.weapons.map(w=>'<p><strong>炮位 '+e(w.id)+'</strong></p><p class="formula">'+e(w.derived?.formula||'此动作不计算常驻DPS')+'</p>'+list(w.derived?.conditions).map(t=>'<p>'+e(t)+'</p>').join('')).join(''):'<p>无常规直接伤害炮位。</p>'}
function battle(id=state.unit){
 const p=getProfile(id),a=p.attributes,b=p.behavior,domains=p.summary.domains;
 const fact=(name,v)=>'<div><dt>'+name+'</dt><dd>'+v+'</dd></div>';
 const rates=Object.entries(domains).map(([key,r])=>'<tr><td>'+e({ground:'地面／水面',air:'空中',underwater:'水下'}[key]||key)+'</td><td>'+n(r.cold_dps)+'</td><td>'+n(r.full_dps)+'</td><td>'+(r.energy_groups?.length?n(r.energy_dps_cap):'不适用')+'</td></tr>').join('');
 return '<details class="battle-panel"><summary>展开战斗属性与DPS <small>耐久、移动、火力与成立条件</small></summary><div class="battle-body"><div class="battle-facts"><section><h3>耐久</h3><dl>'+fact('生命值',n(a.hp))+fact('护盾上限',n(a.shield))+fact('护盾回复',n(a.shield_regen_per_second)+'／秒')+'</dl></section><section><h3>移动与瞄准</h3><dl>'+fact('前进速度',n(b.forward_speed))+fact('倒车速度',n(b.reverse_speed))+fact('固定朝向射击',b.fixed_firing?'是':'否')+'</dl></section><section><h3>攻击</h3><dl>'+fact('最大射程',n(a.range))+fact('能量容量',n(a.energy_max))+fact('能量回复',n(a.energy_regen_per_second)+'／秒')+'</dl></section></div><p class="battle-warning">默认记录状态。DPS假设合法目标持续在射程内、全部命中；范围项为单目标中心上限。能源上界不等于实际长期DPS，削盾与穿入本体也不能相加成普通伤害。</p><p class="battle-complete">'+fullBattleLink(id)+'</p><div class="relation-scroll"><table class="battle-rate-table"><thead><tr><th>目标域</th><th>冷态DPS</th><th>满转DPS</th><th>能源上界</th></tr></thead><tbody>'+(rates||'<tr><td colspan="4">没有常规自动伤害火力</td></tr>')+'</tbody></table></div><div class="battle-formulas"><details><summary>查看逐炮位公式与计算条件</summary>'+weaponNotes(id)+'</details></div></div></details>';
}
function updateHash(){history.replaceState(null,'','#view='+state.view+'&unit='+encodeURIComponent(state.unit))}
function render(){
 const app=document.getElementById('app'),r=relations(state.unit);
 app.className='workspace view-'+state.view;
 const api={u:getUnit(state.unit),p:getProfile(state.unit),...r,e,n,price,link,fullBattleLink,sidebar,rows,battle,info,toolbar,getUnit,getProfile,relations,compareIds:state.compareIds,notice:state.notice,weaponNotes};
 app.innerHTML=window.RWViews[state.view](api);
 document.querySelectorAll('[data-view]').forEach(el=>el.setAttribute('aria-pressed',String(el.dataset.view===state.view)));
 document.getElementById('scheme-caption').innerHTML={a:'<span>紧凑查询台：目录与获取关系并排显示。</span><strong>检索单位、来源和产出对象</strong>',b:'<span>科技路径浏览：以当前对象为中心，沿上下游继续追查。</span><strong>查看生产、建造与升级路径</strong>',c:'<span>战术对比工作台：对齐获取来源，按需展开战斗差异。</span><strong>保留目标域、状态和计算条件</strong>'}[state.view];
 document.querySelectorAll('a[data-home]').forEach(el=>el.setAttribute('href','index.html?unit='+encodeURIComponent(state.unit)));
 updateHash();
}
function select(id){if(!byNative.has(id))return;if(id!==state.unit){state.history.push({unit:state.unit,query:state.query,filter:state.filter,scroll:document.querySelector('.unit-results')?.scrollTop||0});state.unit=id}state.notice='';render()}
document.addEventListener('input',event=>{if(event.target.id==='unit-search'){state.query=event.target.value;document.querySelector('.unit-results').innerHTML=catalogRows();document.querySelector('.catalog-count').textContent=matches().length+' / '+units.length}});
document.addEventListener('click',event=>{
 const el=event.target.closest('button');if(!el||el.disabled)return;
 if(el.dataset.view){state.view=el.dataset.view;state.notice='';render();return}
 if(el.dataset.unit){select(el.dataset.unit);return}
 if(el.dataset.filter){state.filter=el.dataset.filter;document.querySelector('.unit-results').innerHTML=catalogRows();document.querySelector('.catalog-count').textContent=matches().length+' / '+units.length;document.querySelectorAll('[data-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.filter===state.filter)));return}
 if(el.hasAttribute('data-back')){const prev=state.history.pop();if(prev){Object.assign(state,{unit:prev.unit,query:prev.query,filter:prev.filter});render();document.querySelector('.unit-results').scrollTop=prev.scroll}return}
 if(el.dataset.add){if(!state.compareIds.includes(el.dataset.add)&&state.compareIds.length<4)state.compareIds.push(el.dataset.add);render();return}
 if(el.dataset.remove){if(state.compareIds.length>1)state.compareIds=state.compareIds.filter(id=>id!==el.dataset.remove);else state.notice='至少保留一个对比对象';render();return}
 if(el.dataset.preset){state.compareIds=['mechArtillery','c_artillery','mechMinigun'];state.notice='已载入炮兵与机枪机甲对照';render()}
});
document.addEventListener('keydown',event=>{if(event.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)){event.preventDefault();const input=document.getElementById('unit-search');const directory=input?.closest('details');if(directory)directory.open=true;input?.focus()}if(event.key==='Escape'&&document.activeElement.id==='unit-search'){state.query='';document.activeElement.value='';document.querySelector('.unit-results').innerHTML=catalogRows();document.querySelector('.catalog-count').textContent=matches().length+' / '+units.length}});
render();
})();
