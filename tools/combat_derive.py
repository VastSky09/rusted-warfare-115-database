"""Conditional RW fire-rate derivation, not a combat or movement simulator.

Inputs are independently extracted weapon facts. Missing damage/timing stays
unknown. A shared battery is never duplicated for each turret. Values called
``full_dps`` describe uninterrupted full-heat firing *before* energy starvation;
``sustained_dps`` is deliberately absent when the energy cycle is not solved.
"""
from __future__ import annotations

from collections import defaultdict
from math import floor, isfinite
from typing import Any

TICKS_PER_SECOND = 60.0


def _number(value: Any, default=None):
    if value is None or isinstance(value, bool):
        return default
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if isfinite(value) else default


def _fmt(value):
    return f"{value:.6g}"


def _energy_values(attributes, weapon):
    """An explicit battery map is needed before treating batteries as separate."""
    key = weapon.get("energy_group") or "unit"
    values = attributes
    if key != "unit":
        values = attributes.get("energy_groups", {}).get(key, attributes)
    maximum = _number(values.get("energy_max"))
    normal = _number(values.get("energy_regen_per_second"))
    recharge = _number(values.get("energy_recharge_regen_per_second"), normal)
    known_rates = [r for r in (normal, recharge) if r is not None and r >= 0]
    ceiling = max(known_rates) if known_rates else None
    return key, maximum, normal, recharge, ceiling


def derive_weapon(weapon: dict, attributes: dict | None = None) -> dict:
    """Derive a real turret's conditional rates from normalized input fields.

    Supported linked timing overrides: linked_period_ticks,
    linked_cold_period_ticks and linked_full_period_ticks. The linked parent's
    period is the event interval; a slave's warmup is a phase, not an additional
    delay added to that event interval. Unverified linked timing is not summed.
    """
    w, a = weapon, attributes or {}
    out = {
        "status": "unavailable", "metric_kind": "conditional_firing_profile",
        "cold_dps": None, "full_dps": None, "sustained_dps": None,
        "cycle_seconds": None, "cold_cycle_seconds": None,
        "first_shot_seconds": None, "formula": "未取得完整伤害与实际射击周期",
        "conditions": [], "energy_limited": False, "energy_dps_cap": None,
        "shield_dps": None, "shield_overflow_hp_dps": None,
        "building_dps": None, "single_target_center_upper_bound": False,
        "timing_verified": True,
    }
    notes = out["conditions"]
    if w.get("manual_fire") is True:
        out.update(status="non_damage_role", metric_kind="not_applicable",
                   formula="手动动作触发武器；未计算自动持续DPS，伤害与动作条件单列")
        return out
    if w.get("can_shoot") is False or w.get("mechanism") in (
            "none", "support", "interception", "command"):
        out.update(status="non_damage_role", metric_kind="not_applicable",
                   formula="此炮位不发射伤害武器，不计入火力")
        return out
    if w.get("timing_verified") is False:
        out.update(status="timing_unverified", timing_verified=False)
        notes.append("此武器实际射击周期尚未核实，暂停派生DPS")
        return out

    direct = _number(w.get("damage"))
    area = _number(w.get("area_damage"))
    if w.get("target_ground") is True and direct is not None:
        # targetGround shots store a map position, not Projectile.l. The direct
        # hit branch requires a concrete collided/target Unit; stock artillery
        # has no such direct target, even though it retains directDamage:1.
        out["configured_direct_damage"] = direct
        direct = 0.0
        notes.append("定点轰击弹体按落点范围伤害计算；配置中的directDamage不作为对该地图落点的额外直伤")
    damage_multiplier = _number(w.get("damage_multiplier"), 1.0)
    hull_multiplier = _number(w.get("hull_damage_multiplier"), 1.0)
    shield_multiplier = _number(w.get("shield_damage_multiplier"), 1.0)
    deflection = _number(w.get("shield_deflection_multiplier"), 1.0)
    building_multiplier = _number(w.get("building_damage_multiplier"), 1.0)
    is_beam = w.get("mechanism") == "continuous_beam"

    if is_beam:
        raw_full = _number(w.get("full_dps"))
        raw_cold = _number(w.get("cold_dps"), raw_full)
        if raw_full is None or raw_cold is None:
            notes.append("持续光束缺少经核查的每秒伤害，不能按炮位冷却乘算")
            return out
        ramp = _number(w.get("ramp_seconds"))
        out.update(metric_kind="continuous_beam", status="derived",
                   first_shot_seconds=_number(w.get("first_shot_seconds"),
                                              _number(w.get("warmup_ticks"), 0.0) / TICKS_PER_SECOND),
                   ramp_seconds=ramp,
                   formula=f"持续光束：冷态 {_fmt(raw_cold)} → 满强度 {_fmt(raw_full)} 伤害/秒；不按射击tick间隔重复相乘")
        if ramp is not None:
            notes.append(f"持续锁定同一目标约 {_fmt(ramp)} 秒达到满强度；转火与断开接触改变输出")
        raw_damage = None
    else:
        if direct is None and area is None:
            notes.append("伤害未知保留为空，不以零代替")
            return out
        # An omitted direct term is not invented when only AoE was extracted.
        raw_damage = ((direct or 0.0) + (area or 0.0)) * damage_multiplier
        if raw_damage < 0:
            notes.append("伤害值无效，暂停派生")
            return out
        delay = _number(w.get("delay_ticks"))
        warmup = _number(w.get("warmup_ticks"), 0.0)
        delay_multiplier = _number(w.get("delay_multiplier"), 1.0)
        transfer = _number(w.get("warmup_transfer"), 0.0)
        no_reset = w.get("warmup_no_reset") is True
        linked = bool(w.get("linked_to"))
        if warmup < 0 or transfer < 0 or delay_multiplier <= 0:
            notes.append("射击时间参数无效，暂停派生")
            return out
        if linked:
            common = _number(w.get("linked_period_ticks"))
            full_ticks = _number(w.get("linked_full_period_ticks"), common)
            cold_ticks = _number(w.get("linked_cold_period_ticks"), full_ticks)
            verified = w.get("linked_timing_verified") is True
            if full_ticks is None or cold_ticks is None:
                # A supplied actual cycle is permitted only with verification.
                full_ticks = _number(w.get("cycle_ticks"))
                cold_ticks = _number(w.get("cold_cycle_ticks"), full_ticks)
            out["timing_verified"] = verified and full_ticks is not None and cold_ticks is not None
            if not out["timing_verified"]:
                notes.append("联动炮位的主炮事件周期尚未核实，不独立推算或并入总DPS")
                out["status"] = "linked_timing_unverified"
                return out
            if not no_reset and warmup > full_ticks:
                out.update(status="linked_timing_unverified", timing_verified=False)
                notes.append("副炮预热长于主炮事件间隔，不能假设每次触发都能发射，需单独核查时序")
                return out
            notes.append("联动周期按主炮触发事件计；副炮预热决定相位，未再次叠加到主炮周期")
            period_formula = f"经核查的主炮事件周期 {_fmt(full_ticks)} ticks"
        else:
            if delay is None:
                notes.append("冷却时间未知保留为空，不以零代替")
                return out
            effective_delay = delay * delay_multiplier
            cold_ticks = effective_delay if no_reset else effective_delay + warmup
            full_ticks = effective_delay - transfer if no_reset else cold_ticks
            override = _number(w.get("cycle_ticks"))
            if override is not None:
                full_ticks = override
                cold_ticks = _number(w.get("cold_cycle_ticks"), override)
                period_formula = f"经核查周期 {_fmt(full_ticks)} ticks"
            elif no_reset:
                period_formula = f"({_fmt(delay)} × {_fmt(delay_multiplier)} − {_fmt(transfer)}) ticks"
            else:
                period_formula = f"({_fmt(delay)} × {_fmt(delay_multiplier)} + {_fmt(warmup)}) ticks"
        if full_ticks is None or cold_ticks is None or full_ticks <= 0 or cold_ticks <= 0:
            notes.append("周期非正或未知，暂停派生")
            return out
        raw_full = raw_damage * TICKS_PER_SECOND / full_ticks
        raw_cold = raw_damage * TICKS_PER_SECOND / cold_ticks
        out.update(status="derived", cycle_seconds=full_ticks / TICKS_PER_SECOND,
                   cold_cycle_seconds=cold_ticks / TICKS_PER_SECOND,
                   first_shot_seconds=0.0 if no_reset else warmup / TICKS_PER_SECOND,
                   formula=f"{_fmt(raw_damage)} × 60 / {period_formula}",
                   damage_per_shot=raw_damage,
                   direct_damage_component=(direct or 0.0) * damage_multiplier,
                   area_damage_component=(area or 0.0) * damage_multiplier)
        if no_reset:
            out["heat_ramp_seconds"] = warmup / TICKS_PER_SECOND
            notes.append(f"冷态即可开始射击；持续接敌升温约 {_fmt(warmup / TICKS_PER_SECOND)} 秒。满转速率不包含冷启动过渡")
        elif warmup:
            notes.append(f"每次射击含 {_fmt(warmup)} ticks预热；首次就绪也需预热，不仅计冷却")
        if area is not None and area > 0:
            out["single_target_center_upper_bound"] = True
            out["aoe"] = {
                "area_damage": area * damage_multiplier,
                "radius": _number(w.get("area_radius")),
                "scatter": _number(w.get("scatter")),
                "targets_multiplied": False,
            }
            notes.append("仅为一名合法目标承受直伤＋范围中心伤害的上限；散布、距离衰减和落点会降低输出，未乘目标数量")

    out.update(cold_dps=raw_cold * hull_multiplier,
               full_dps=raw_full * hull_multiplier,
               sustained_dps=raw_full * hull_multiplier,
               raw_full_dps=raw_full,
               shield_dps=raw_full * shield_multiplier,
               shield_overflow_hp_dps=raw_full * max(0.0, 1 - deflection) * hull_multiplier,
               building_dps=raw_full * building_multiplier * hull_multiplier,
               hull_damage_multiplier=hull_multiplier,
               shield_damage_multiplier=shield_multiplier,
               shield_deflection_multiplier=deflection,
               building_damage_multiplier=building_multiplier)
    if raw_damage is not None:
        out.update(shield_damage_per_shot=raw_damage * shield_multiplier,
                   hp_through_full_shield_per_shot=raw_damage * max(0.0, 1 - deflection) * hull_multiplier)
    notes.extend([
        "持续接敌且全部命中；未计移动、转向、射程进入、弹道、护甲、目标回复、转火或过量伤害",
        "护盾每秒削减与穿入HP分别列出；穿盾值仅适用于目标护盾足以吸收该次盾伤害的阶段，不能直接相加为普通HP伤害",
    ])
    if building_multiplier != 1:
        notes.append(f"建筑伤害倍率 {_fmt(building_multiplier)}；建筑列仅计算无额外护甲的目标")
    if w.get("condition"):
        notes.append(f"攻击条件：{w['condition']}")

    usage = _number(w.get("energy_usage"), 0.0)
    if usage > 0:
        key, maximum, normal, recharge, ceiling = _energy_values(a, w)
        out.update(energy_group=key, energy_usage=usage,
                   energy_regen_per_second=normal,
                   energy_recharge_regen_per_second=recharge,
                   energy_needs_full_recharge=a.get("energy_needs_full_recharge") is True)
        if maximum is not None:
            affordable = maximum + 1e-10 >= usage
            shots = floor(maximum / usage + 1e-10) if maximum >= 0 else 0
            out.update(energy_affordable=affordable,
                       burst_shots_from_full=shots,
                       burst_damage_from_full=(shots * raw_damage * hull_multiplier if raw_damage is not None else None))
            notes.append(f"本炮独占满电池时，不计开火期间回能可支付 {shots} 次；多炮共享此电池，不能逐炮相加弹量")
            if not affordable:
                out.update(nominal_unconstrained_full_dps=out["full_dps"],
                           nominal_unconstrained_cold_dps=out["cold_dps"],
                           cold_dps=0.0, full_dps=0.0, sustained_dps=0.0,
                           shield_dps=0.0, shield_overflow_hp_dps=0.0,
                           building_dps=0.0, first_shot_seconds=None,
                           energy_dps_cap=0.0, energy_limited=True,
                           status="energy_disabled")
                notes.append("单次能量需求超过此形态电池容量，当前形态不能发射；名义火力不作为可用DPS")
                return out
        else:
            out["energy_affordable"] = None
            notes.append("电池容量未知，无法确认该炮位是否可发射")
        firing_cost = None if out["cycle_seconds"] is None else usage / out["cycle_seconds"]
        out["firing_energy_per_second"] = firing_cost
        limited = (firing_cost is None or normal is None or firing_cost > normal + 1e-9)
        out["energy_limited"] = limited
        if raw_damage is not None and ceiling is not None:
            cap = min(out["full_dps"], ceiling * raw_damage * hull_multiplier / usage)
            out["energy_dps_cap"] = cap
            out["energy_cap_formula"] = (
                f"min(未缺能火力, 最高回能 {_fmt(ceiling)} × 单次伤害 {_fmt(raw_damage * hull_multiplier)} / 耗能 {_fmt(usage)})")
        if limited or maximum is None:
            out["sustained_dps"] = None
            out["metric_kind"] = "energy_limited_firing_profile"
        notes.append("能源列是按最高回能速率得到的长期资源上界，不是已求解的长期实际DPS；必须另计满充锁定、预热、各炮竞争与充能阶段")
        if recharge is not None and normal is not None and recharge != normal:
            notes.append(f"普通回能 {_fmt(normal)}/秒，充能阶段 {_fmt(recharge)}/秒，不能用单一回能率冒充全周期输出")
        if a.get("energy_needs_full_recharge"):
            notes.append("能量耗尽后须回满才能恢复射击；满电爆发与长期输出分开")
    return out


def _domains(weapon):
    domains = weapon.get("domains") or []
    if isinstance(domains, str):
        domains = [domains]
    return ["ground" if d == "land" else d for d in domains]


def _domain_condition(weapon, domain):
    # A unit-wide canAttackLandUnits expression must not leak into its air gun.
    specific = weapon.get("domain_conditions")
    if isinstance(specific, dict):
        return specific.get(domain)
    return weapon.get("condition")


def derive_unit_summary(weapons: list[dict], attributes: dict | None = None) -> dict:
    """Aggregate only simultaneously meaningful, same-domain fire profiles.

    No ground+air grand total is exposed. Alternative same-domain payloads are
    shown as a ceiling, never added as two real guns. Battery ceilings are
    computed once per shared battery, not summed from per-turret ceilings.
    """
    a = attributes or {}
    rows = []
    for w in weapons:
        derived = w.get("derived") if isinstance(w.get("derived"), dict) else derive_weapon(w, a)
        if derived.get("status") == "non_damage_role":
            continue
        rows.append((w, derived))
    grouped = defaultdict(list)
    for w, d in rows:
        for domain in _domains(w):
            grouped[domain].append((w, d))
    result = {
        "status": "no_damage_weapons" if not rows else "conditional",
        "domains": {}, "no_cross_domain_sum": True, "all_domains_total_dps": None,
        "conditions": [
            "按目标域分别列射击条件值，不能把地面、空中、水下相加为一个总DPS",
            "仅相同目标、所有相关炮位能同时就绪并命中的条件下可相加；不表示实际对局的命中输出",
        ],
    }
    if rows and not grouped:
        result["conditions"].append("炮位攻击域缺失，无法安全合计")
    for domain, entries in grouped.items():
        notes = []
        summary = {
            "cold_dps": None, "full_dps": None, "sustained_dps": None,
            "full_dps_upper_bound": None, "energy_dps_cap": None,
            "single_target_center_upper_bound": any(d.get("single_target_center_upper_bound") for _, d in entries),
            "weapon_ids": [w.get("id") for w, _ in entries],
            "status": "derived", "conditions": notes, "energy_groups": [],
        }
        unknown = any(d.get("full_dps") is None or d.get("cold_dps") is None or not d.get("timing_verified", True) for _, d in entries)
        alternatives = defaultdict(list)
        independent = []
        for w, d in entries:
            key = w.get("alternative_group") or w.get("cooldown_group")
            if key:
                alternatives[key].append((w, d))
            else:
                independent.append((w, d))
        has_alternatives = any(len(items) > 1 for items in alternatives.values())
        for items in alternatives.values():
            if len(items) == 1:
                independent.extend(items)
        conditions = {str(_domain_condition(w, domain)) for w, _ in entries
                      if _domain_condition(w, domain) and not w.get("condition_resolved")}
        conflicting_conditions = len(conditions) > 1
        if unknown:
            notes.append("存在未知伤害、未核实周期或联动炮位；不把已知子集当作完整单位DPS")
            summary["status"] = "incomplete"
        elif conflicting_conditions:
            notes.append("炮位含多个未解析攻击条件，无法证明能同时射击，暂停总DPS合计")
            summary["status"] = "conditional_unresolved"
        elif has_alternatives:
            bound = sum(d["full_dps"] for _, d in independent)
            bound += sum(max(d["full_dps"] for _, d in items) for items in alternatives.values() if len(items) > 1)
            summary.update(full_dps_upper_bound=bound, status="alternative_payloads")
            notes.append("同一炮位的互斥弹体/分支只取较高条件值作为上界，不累加，也不当作已选定分支的实际DPS")
        else:
            summary.update(cold_dps=sum(d["cold_dps"] for _, d in entries),
                           full_dps=sum(d["full_dps"] for _, d in entries),
                           sustained_dps=sum(d["full_dps"] for _, d in entries))
            if conditions:
                summary["status"] = "conditional"
                notes.append("合计还要求攻击条件成立：" + next(iter(conditions)))

        # Group the same battery once, including simultaneous linked turrets.
        batteries = defaultdict(list)
        free = []
        for w, d in entries:
            if _number(w.get("energy_usage"), 0) > 0 and d.get("status") != "energy_disabled":
                batteries[w.get("energy_group") or "unit"].append((w, d))
            else:
                free.append((w, d))
        free_profile = sum(d.get("full_dps") or 0 for _, d in free)
        energy_upper = free_profile
        cap_formulas = []
        energy_known = not unknown and not conflicting_conditions and not has_alternatives
        has_limited_energy = False
        for key, items in batteries.items():
            _, maximum, normal, recharge, ceiling = _energy_values(a, items[0][0])
            firing = sum(d.get("firing_energy_per_second") or 0 for _, d in items)
            group_profile = sum(d.get("full_dps") or 0 for _, d in items)
            efficiency = []
            for w, d in items:
                per_shot = d.get("damage_per_shot")
                if per_shot is None:
                    continue
                usage = _number(w.get("energy_usage"))
                if usage and usage > 0:
                    efficiency.append(per_shot * d.get("hull_damage_multiplier", 1) / usage)
            cap = None
            if efficiency and ceiling is not None and len(efficiency) == len(items):
                cap = min(group_profile, ceiling * max(efficiency))
                energy_upper += cap
                cap_formula = (f"{key}: min(未缺能火力 {_fmt(group_profile)}, "
                               f"最高回能 {_fmt(ceiling)} × 最大单次伤害/能量 {_fmt(max(efficiency))}) "
                               f"= {_fmt(cap)}")
            else:
                energy_known = False
                cap_formula = f"{key}: 伤害/能量或回能数据不足，暂停计算"
            cap_formulas.append(cap_formula)
            limited = normal is None or firing > normal + 1e-9 or any(d.get("energy_affordable") is None for _, d in items)
            has_limited_energy |= limited
            summary["energy_groups"].append({
                "group": key, "capacity": maximum,
                "normal_regen_per_second": normal, "recharge_regen_per_second": recharge,
                "firing_energy_per_second": firing, "dps_upper_bound": cap,
                "formula": cap_formula,
                "weapon_ids": [w.get("id") for w, _ in items],
            })
        if batteries:
            summary["energy_dps_cap"] = energy_upper if energy_known else None
            summary["energy_cap_formula"] = (f"无耗能炮位 {_fmt(free_profile)} + "
                                              + " + ".join(cap_formulas))
            notes.append("同电池全部炮位共享回能；能源上界只计算一次，且假设仅对此目标域开火")
            notes.append("能源上界≠实际长期DPS；未求解回满锁定、不同炮位的资源竞争、转火或动作回能")
            if has_limited_energy:
                summary["sustained_dps"] = None
                if summary["status"] in ("derived", "conditional"):
                    summary["status"] = "energy_limited"
        if summary["single_target_center_upper_bound"]:
            notes.append("含范围伤害中心命中上限，未乘目标数；不是整群每秒总伤害")
        result["domains"][domain] = summary
    return result
