(()=>{
'use strict';
const db=JSON.parse(document.getElementById('db').textContent);
const combat=JSON.parse(document.getElementById('combat-db').textContent);
const $=id=>document.getElementById(id);
const byId=new Map(db.units.map(u=>[u.object_id,u]));
const requestedNative=typeof location==='undefined'?'':new URLSearchParams(location.search).get('unit');
let selected=db.units.find(x=>x.native_id===requestedNative)?.object_id||db.units.find(x=>x.native_id==='builder')?.object_id||db.units[0].object_id;
let selectedState='';
let combatExpanded=false;
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(x,suffix='')=>typeof x==='number'&&Number.isFinite(x)?new Intl.NumberFormat('zh-CN',{maximumFractionDigits:2}).format(x)+suffix:(x===false?'否':x===true?'是':x===null||x===undefined?'待核实':esc(x));
const yes=x=>x===true?'是':x===false?'否':'待核实';
const domainNames={ground:'地面／水面',air:'空中',underwater:'水下',surface:'水面',land:'地面'};
const movementNames={NONE:'固定',LAND:'陆地',AIR:'飞行',WATER:'水域',HOVER:'水陆悬浮',OVER_CLIFF:'陆地＋越崖',OVER_CLIFF_WATER:'水陆＋越崖'};
const list=x=>Array.isArray(x)?x:x?[x]:[];
function notes(items,cls='condition-list'){return items.length?'<ul class="'+cls+'">'+items.map(x=>'<li>'+esc(typeof x==='object'?JSON.stringify(x):x)+'</li>').join('')+'</ul>':''}
function attrs(rows){return '<dl class="attribute-grid">'+rows.map(([k,v])=>'<div><dt>'+esc(k)+'</dt><dd>'+v+'</dd></div>').join('')+'</dl>'}
function defenseText(x){if(typeof x==='string')return x;return (x.type==='laser_interception'?'激光拦截':'辅助防御')+(x.turret?'（炮位'+x.turret+'）':'')+'：范围 '+num(x.range)+'，每次耗能 '+num(x.energy_per_interception)+'。'+list(x.notes).join('；')}
function link(id,fallback){let o=byId.get(id);return o?'<button class="link" type="button" data-id="'+esc(id)+'">'+esc(o.name_zh)+' · '+esc(o.native_id)+'</button>':esc(fallback||id)}
function bind(root){root.querySelectorAll('[data-id]').forEach(b=>b.addEventListener('click',()=>select(b.dataset.id)))}
function drawList(){
 const needle=$('find').value.trim().toLowerCase(),cat=$('category').value,prio=$('prio').value;
 const matches=db.units.filter(o=>(!needle||[o.name_zh,o.native_id,o.object_id].some(v=>v.toLowerCase().includes(needle)))&&(!cat||o.category===cat)&&(!prio||o.priority===prio));
 $('count').textContent=matches.length+' / '+db.units.length;
 $('list').innerHTML=matches.map(o=>'<button type="button" aria-pressed="'+(o.object_id===selected)+'" class="unit '+(o.object_id===selected?'active':'')+'" data-id="'+esc(o.object_id)+'"><span><b>'+esc(o.name_zh)+'</b><small>'+esc(o.native_id)+' · '+esc(o.object_id)+'</small></span><span class="pill '+o.priority.toLowerCase()+'">'+esc(o.priority)+'</span></button>').join('')||'<p>没有匹配结果。请清空搜索或调整类别。</p>';
 bind($('list'));
}
function showEdges(rows,outbound){return rows.length?rows.map(r=>'<div class="row"><div class="type">'+esc(r.relation)+'　'+esc(r.source_state?.split('-').slice(-1)[0])+' → '+esc(r.target_state?.split('-').slice(-1)[0])+'</div>'+link(outbound?r.target_id:r.source_id,outbound?r.target_name:r.source_name)+'<small>动作：'+esc(r.native_action)+'　费用：'+(r.cost_credits===''?'未记录':esc(r.cost_credits)+'$')+'</small><small>'+esc(r.relation_id)+' · '+esc(r.evidence_level)+'</small></div>').join(''):'<p class="muted">当前公开范围无对应关系。</p>'}
function currentProfile(base){
 const state=list(base.states).find(x=>String(x.id)===selectedState);
 return !state?base:{...base,...state,attributes:{...base.attributes,...state.attributes},behavior:{...base.behavior,...state.behavior},notes:[...list(base.notes),...list(state.notes)],weapons:state.weapons??base.weapons,summary:state.summary??base.summary};
}
function weaponHtml(w){
 const d=w.derived||{},targets=list(w.domains).map(x=>domainNames[x]||x).join('、')||'按条件／非直接攻击';
 const energy=Number(w.energy_usage)>0;
 let out='<article class="weapon-section"><h4>炮位 '+esc(w.id||'未命名')+'</h4><p class="muted">目标：'+esc(targets)+'　射程：'+num(w.range)+'　'+(w.manual_fire?'手动动作触发':w.non_damage_role?'拦截／辅助用途':d.status==='energy_disabled'?'当前形态不能开火':'自动攻击')+'</p>';
 out+=attrs([['直接伤害',w.target_ground&&Number(w.damage)>0?'不参与落点伤害（配置 '+num(w.damage)+'）':num(w.damage)],['范围中心伤害',num(w.area_damage)],['范围半径',num(w.area_radius)],['冷却',num(w.delay_ticks,' tick')],['逐次／升温预热',num(w.warmup_ticks,' tick')],['满转冷却缩减',num(w.warmup_transfer,' tick')],['瞄准转速',num(w.aim_turn_speed,' 度／tick')],['瞄准控制炮位',w.aim_turret_id?esc(w.aim_turret_id):'待核实'],['联动主炮',w.linked_to?esc(w.linked_to):'无'],['耗能／发',num(w.energy_usage)],['瞬时命中',yes(w.instant)],['可被激光拦截',yes(w.instant===true?false:w.interceptable)],['弹速（初始）',w.instant?'瞬时，无飞行弹道':num(w.projectile_speed)],['弹速（目标值）',w.instant?'不适用':num(w.projectile_target_speed)],['落点散布',num(w.spread)]]);
 out+='<h4>派生火力与计算条件</h4>';
 const labels=[['开火阶段冷态DPS',d.cold_dps],['开火阶段满转DPS',d.full_dps],['单次循环',d.cycle_seconds,' 秒'],['首次预热',d.first_shot_seconds,' 秒'],['能源约束下的理论上界',d.energy_dps_cap]];
 out+=attrs(labels.map(([k,v,s])=>[k,num(v,s||'')]));
 if(d.burst_shots_from_full!==undefined)out+=attrs([['本炮独占满电池弹量上限',num(d.burst_shots_from_full)],['忽略回能的满电爆发上限',num(d.burst_damage_from_full)]]);
 if(d.formula)out+='<p class="weapon-formula">'+esc(d.formula)+'</p>';
 if(d.energy_cap_formula)out+='<p class="weapon-formula">能源上界：'+esc(d.energy_cap_formula)+'</p>';
 if(d.heat_ramp_seconds!==undefined||d.ramp_seconds!==undefined)out+='<p class="muted">持续接敌升温／光束爬升：'+num(d.heat_ramp_seconds??d.ramp_seconds,' 秒')+'。转火或断开接触会影响此状态。</p>';
 if(d.single_target_center_upper_bound||Number(w.area_damage)>0)out+='<p class="status-label">范围伤害只按单目标中心命中上限；没有乘以范围内敌人数。</p>';
 if(d.energy_limited)out+='<p class="status-label">能量受限：开火阶段DPS不是无限持续输出；能源上界也不是已验证的长期平均DPS。</p>';
 else if(energy)out+='<p class="muted">此炮位消耗能量；多个炮位仍须按共享电池合计资源需求。</p>';
 out+=attrs([['对盾伤害倍率',num(w.shield_damage_multiplier)],['护盾抵消HP伤害比例',num(w.shield_deflection_multiplier)],['对建筑倍率',num(w.building_damage_multiplier)],['有盾目标：削盾DPS',num(d.shield_dps)],['有盾目标：穿入本体DPS',num(d.shield_overflow_hp_dps)],['对建筑DPS',num(d.building_dps)]]);
 out+=notes([...list(d.conditions),...list(w.notes),...Object.entries(w.domain_conditions||{}).map(([k,v])=>(domainNames[k]||k)+'攻击条件：'+v),...(w.condition?['攻击条件：'+w.condition]:[]),...(w.target_constraints?['目标限制：'+(typeof w.target_constraints==='string'?w.target_constraints:JSON.stringify(w.target_constraints))]:[])]);
 return out+'</article>';
}
function combatHtml(base){
 if(!base)return '<section class="combat-section"><h3>战斗属性</h3><p>此对象尚未整理战斗资料。</p></section>';
 const p=currentProfile(base),a=p.attributes||{},b=p.behavior||{},weapons=list(p.weapons),summary=p.summary||{};
 let out='<section class="combat-section" id="combat"><h3>战斗属性与行为</h3><p class="muted combat-intro">速度用世界单位／秒，角速度用度／tick；60 tick＝1游戏秒。数字0表示已确认的零值，「待核实」表示当前未完成核定。</p>';
 if(list(base.states).length)out+='<div class="state-select"><label for="combat-state">查看状态</label><select id="combat-state" class="field"><option value="">默认记录状态</option>'+base.states.map(s=>'<option value="'+esc(s.id)+'" '+(String(s.id)===selectedState?'selected':'')+'>'+esc(s.label||s.id)+'</option>').join('')+'</select></div>';
 out+='<h4>耐久与资源</h4>'+attrs([['生命值',num(a.hp)],['护盾',num(a.shield)],['生命回复',num(a.hp_regen_per_second,'／秒')],['护盾回复',a.shield===0?'无护盾':num(a.shield_regen_per_second,'／秒')],['装甲',num(a.armor)],['能量上限',num(a.energy_max)],['能量回复',num(a.energy_regen_per_second,'／秒')],['耗尽须回满',a.energy_max===0?'不适用':yes(a.energy_needs_full_recharge??p.interception?.recharge_to_full_after_depletion)]]);
 out+='<h4>移动、视野与瞄准</h4>'+attrs([['通行类型',esc(movementNames[b.movement_type]||b.movement_type||'待核实')],['前进速度',num(b.forward_speed)],['倒车速度',num(b.reverse_speed)],['车体转速',num(b.turn_speed)],['固定朝向射击',yes(b.fixed_firing)],['炮塔随车体转动',yes(b.turret_rotates_with_body)],['上身独立转向',yes(b.upper_body_independent)],['视野（格）',num(a.sight_tiles??b.sight_tiles)],['直接攻击',yes(a.can_attack)],['攻击域',list(a.attack_domains).map(x=>esc(domainNames[x]||x)).join('、')||'见炮位／状态']]);
 if(a.support_range!==undefined)out+=attrs([['工具／拦截作用范围',num(a.support_range)]]);
 if(a.shield>0&&a.starts_shield_at_zero)out+='<p class="status-label">初始护盾从0开始回复；护盾上限不等于刚部署时已有的护盾。</p>';
 if(a.energy_recharge_regen_per_second!==undefined&&a.energy_recharge_regen_per_second!==a.energy_regen_per_second)out+=attrs([['充能阶段回复',num(a.energy_recharge_regen_per_second,'／秒')]]);
 out+=notes([...list(b.notes),...list(p.notes)]);
 if(list(p.defenses).length)out+='<h4>拦截与辅助防御</h4>'+notes(p.defenses.map(defenseText));
 if(p.interception)out+='<h4>拦截防御</h4>'+attrs([['拦截范围',num(p.interception.range)],['每次拦截耗能',num(p.interception.energy_usage_per_intercept)],['拦截充能回复',num(p.interception.energy_regen_per_second,'／秒')]]);
 out+='<h4>派生DPS：按攻击域分别计算</h4><p class="muted">假设合法目标持续处于射程内、全部命中、无转向与转火损失，不计目标装甲、回复和过量伤害。不同攻击域、互斥炮位与状态不能相加。</p>';
 if(weapons.length){
  out+='<div class="combat-table-wrap"><table class="combat-table"><thead><tr><th scope="col">攻击域</th><th scope="col">冷态开火DPS</th><th scope="col">满转开火DPS</th><th scope="col">能源DPS上界</th><th scope="col">说明</th></tr></thead><tbody>';
  for(const [domain,s] of Object.entries(summary.domains||{}))out+='<tr><td>'+esc(domainNames[domain]||domain)+'</td><td>'+num(s.cold_dps)+'</td><td>'+num(s.full_dps??s.full_dps_upper_bound)+(s.full_dps===null&&s.full_dps_upper_bound!==null?'（互斥上界）':'')+'</td><td>'+(list(s.energy_groups).length?num(s.energy_dps_cap):'不适用')+'</td><td>'+esc(list(s.conditions).join('；')||s.note||'见下方各炮位计算条件')+(s.energy_cap_formula?'<p class="weapon-formula">'+esc(s.energy_cap_formula)+'</p>':'')+'</td></tr>';
  if(!Object.keys(summary.domains||{}).length)out+='<tr><td colspan="5">当前模式、手动动作或复杂武器不提供简单合计，请查看逐炮位条件。</td></tr>';
  out+='</tbody></table></div>'+notes(list(summary.conditions));
  if(a.energy_max>0)out+='<div class="combat-note"><p>共享能量池：'+num(a.energy_max)+'；回复 '+num(a.energy_regen_per_second)+'／秒。各炮位的能源上界不能同时相加；'+(a.energy_needs_full_recharge?'耗尽后必须回满才能继续。':'发射节奏还受冷却与当前能量影响。')+'</p></div>';
  out+='<details class="combat-details" open><summary>逐炮位、公式与特殊机制（'+weapons.length+'）</summary>'+weapons.map(weaponHtml).join('')+'</details>';
 }else out+='<p>此对象没有常规直接伤害炮位；维修、生产、拦截和视野用途见行为说明。</p>';
 out+='<details class="combat-details"><summary>数据依据与核验范围</summary>'+notes(list(p.sources).map(x=>typeof x==='string'?x:JSON.stringify(x)),'source-list')+'<p class="muted">整理参数与静态派生计算，不等于游戏内对战验证；部署、飞行、潜水及条件炮位按当前状态判断。</p></details></section>';
 return out;
}
function select(id){if(!byId.has(id))return;selected=id;selectedState='';combatExpanded=false;if(typeof location!=='undefined'&&typeof history!=='undefined'){const address=new URL(location.href);address.searchParams.set('unit',byId.get(id).native_id);history.replaceState(null,'',address)}drawList();drawDetails()}
function drawDetails(){
 const o=byId.get(selected),tin=db.tech.filter(x=>x.target_id===selected),tout=db.tech.filter(x=>x.source_id===selected),cin=db.transform.filter(x=>x.target_id===selected),cout=db.transform.filter(x=>x.source_id===selected);
 for(const target of document.querySelectorAll?.('[data-workspace-view]')||[])target.href='workbench.html#view='+target.dataset.workspaceView+'&unit='+encodeURIComponent(o.native_id);
 $('detail').innerHTML='<h2>'+esc(o.name_zh)+' <span class="pill '+o.priority.toLowerCase()+'">'+esc(o.priority)+'</span></h2><div class="muted"><code>'+esc(o.native_id)+'</code> · '+esc(o.object_id)+' · '+esc(o.category)+' · '+esc(o.scope)+'</div><div class="facts" style="margin-top:15px"><span class="tag">已记录获取费用：'+(o.known_acquisition_prices?esc(o.known_acquisition_prices)+'$':'未列出')+'</span><span class="tag">'+esc(o.identity_status)+'</span></div>'+'<details id="combat-entry" class="combat-entry"'+(combatExpanded?' open':'')+'><summary><span class="when-closed">展开战斗属性与DPS</span><span class="when-open">收起战斗属性与DPS</span></summary>'+combatHtml(combat.units[o.native_id])+'</details><section class="combat-section"><h3>科技与获取关系</h3><p class="muted">价格受来源与科技状态影响。空白并非零元。</p><div class="cards"><div><h4>从哪里获得（'+tin.length+'）</h4>'+showEdges(tin,false)+'</div><div><h4>能够生产／建造／升级什么（'+tout.length+'）</h4>'+showEdges(tout,true)+'</div></div><h4>相关形态、模式与自动转换（'+(cin.length+cout.length)+'）</h4><div class="cards"><div>'+showEdges(cin,false)+'</div><div>'+showEdges(cout,true)+'</div></div></section>';
 bind($('detail'));
 const entry=$('combat-entry');
 entry.addEventListener('toggle',()=>{if($('combat-entry')===entry)combatExpanded=entry.open});
 if($('combat-state'))$('combat-state').addEventListener('change',e=>{selectedState=e.target.value;drawDetails()});
}
$('num-tech').textContent=db.tech.length;$('num-transform').textContent=db.transform.length;
['find','category','prio'].forEach(id=>$(id).addEventListener(id==='find'?'input':'change',drawList));
drawList();drawDetails();
})();
