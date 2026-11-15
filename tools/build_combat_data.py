"""Build a public combat fact projection from the locally audited extraction.

The generated file contains normalized facts and references, never game source
text, original INI files, original assets, or absolute local filesystem paths.
"""
from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

from combat_derive import derive_weapon, derive_unit_summary

BASE = Path(__file__).resolve().parents[1]
WORKSPACE = BASE.parent
TICKS = 60
DOMAIN_KEYS = {"ground": "canAttackLandUnits", "air": "canAttackFlyingUnits", "underwater": "canAttackUnderwaterUnits"}
MOVEMENT_LABELS = {
    "NONE": "固定建筑/已部署形态，不能移动。",
    "LAND": "普通陆路通行；水面、悬崖和熔岩仍受地图通行限制。",
    "WATER": "沿可通行水域行动；不能把熔岩当作水面。",
    "HOVER": "可走普通陆地与水面；不据此推定可跨悬崖或熔岩。",
    "AIR": "飞行时可跨普通地面障碍；攻击资格仍受飞行/降落状态影响。",
    "OVER_CLIFF": "可越崖，不能据此推定可跨水面或熔岩。",
    "OVER_CLIFF_WATER": "支持越崖与水域通行，具体仍受地图与当前形态限制。",
}


def num(value, default=None):
    if isinstance(value, bool):
        return default
    try:
        result = float(value)
    except (ValueError, TypeError):
        return default
    if not math.isfinite(result):
        return default
    return int(result) if result.is_integer() else result


def bool_value(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return default


def ticks(value, default=None):
    if isinstance(value, str) and value.strip().endswith("s"):
        v = num(value.strip()[:-1])
        return None if v is None else v * TICKS
    return num(value, default)


def times(value, scale=1):
    return None if value is None else value * scale


def build_seconds(value):
    if isinstance(value, str) and value.strip().endswith("s"):
        return num(value.strip()[:-1])
    progress = num(value)
    if progress is None or progress < 0:
        return None
    return 1 / (progress * TICKS) if progress else 0


def aim_turret(turret, turrets, attack):
    current, visited = turret, set()
    while bool_value(current["values"].get("slave")):
        key = str(current["id"])
        if key in visited:
            return None, None
        visited.add(key)
        parent = current["values"].get("attachedTo")
        if parent is None or str(parent) not in turrets:
            return None, None
        current = turrets[str(parent)]
    return str(current["id"]), num(current["values"].get("turnSpeed", attack.get("turretTurnSpeed")))


def reference(source):
    """Make a short public locator without revealing the research checkout."""
    source = str(source or "").replace("\\", "/")
    if "/assets/" in source:
        return "assets/" + source.split("/assets/", 1)[1]
    if "/com/corrodinggames/" in source:
        return "com/corrodinggames/" + source.split("/com/corrodinggames/", 1)[1]
    if re.match(r"^[A-Za-z]:/", source) or source.startswith("/"):
        return source.rsplit("/", 1)[-1]
    return source


def source_ref(provenance, fallback=None):
    if not isinstance(provenance, dict):
        return reference(fallback)
    src = reference(provenance.get("source_file", fallback))
    line = provenance.get("source_line")
    return src + (f":{line}" if line else "")


def source_refs(provenance, keys, fallback):
    refs = [source_ref(provenance.get(k), fallback) for k in keys if k in provenance]
    return list(dict.fromkeys(x for x in refs if x))


def allowed(value):
    # A conditional expression means the domain can be legal under that
    # expression. It must not be flattened to either false or unconditional true.
    if isinstance(value, str) and value.strip().lower() not in ("true", "false"):
        return True
    return bool_value(value)


def expression(value):
    return value if isinstance(value, str) and value.strip().lower() not in ("true", "false") else None


def derive_link_timing(turret, turrets, multiplier):
    """Resolve a slave's cadence from its main gun, retaining own phase.

    The linked gun's own warmup is a phase after the main trigger, not an
    independent extra cooldown added to the main complete cycle. We only mark
    timing verified where the linked warmup fits within that complete cycle.
    """
    values = turret["values"]
    linked = values.get("linkDelayWithTurret")
    if linked is None:
        return {}
    linked = str(linked)
    main = turrets.get(linked)
    result = {"linked_to": linked, "linked_timing_verified": False}
    if not main or main["values"].get("linkDelayWithTurret") is not None:
        return result
    mv = main["values"]
    delay = num(main.get("delay_ticks"))
    mw = num(main.get("warmup_ticks"), 0)
    own_warmup = num(turret.get("warmup_ticks"), 0)
    if delay is None or multiplier is None:
        return result
    delay *= multiplier
    retained = bool_value(mv.get("warmupNoReset"))
    transfer = num(mv.get("warmupShootDelayTransfer"), 0)
    cold = delay if retained else delay + mw
    full = delay - transfer if retained else cold
    own_retained = bool_value(values.get("warmupNoReset"))
    # Phase handling beyond a cycle or unlike ramp retention is not established.
    if full <= 0 or (not own_retained and own_warmup >= full) or own_retained != retained:
        return result
    result.update({"linked_timing_verified": True,
                   "linked_period_ticks": full,
                   "linked_cold_period_ticks": cold,
                   "linked_full_period_ticks": full})
    return result


def make_weapon(unit, turret, projectiles, all_turrets, manual_ids):
    core, attack, norm = unit["core"], unit["attack"], unit["normalized"]
    tv = turret["values"]
    pid = str(turret.get("projectile_id", tv.get("projectile", "1")))
    p = projectiles.get(pid)
    pv = p["values"] if p else {}
    tid = str(turret["id"])
    interception = any(k.startswith("interceptProjectiles_") for k in tv)
    manual = tid in manual_ids
    can_shoot = bool_value(turret.get("can_shoot"), True)
    if not can_shoot and not manual:
        return None
    unit_auto = allowed(attack.get("canAttack", False))
    if not unit_auto and not interception and not manual:
        return None
    domains, conditions, constraints, domain_conditions = [], [], [], {}
    for domain, key in DOMAIN_KEYS.items():
        parent = attack.get(key, False)
        child = tv.get(key, True)
        if allowed(parent) and allowed(child):
            domains.append(domain)
            conditional = list(dict.fromkeys(value for value in (parent, child) if expression(value)))
            if conditional:
                domain_conditions[domain] = "；".join(conditional)
    for value in (attack.get("canAttack"), tv.get("canAttackCondition")):
        if expression(value) and value not in conditions:
            conditions.append(value)
    touching = tv.get("canAttackNotTouchingWaterUnits", attack.get("canAttackNotTouchingWaterUnits", True))
    if touching is False:
        constraints.append("只能攻击接触水面的目标；ground域不表示可任意攻击岸上单位。")
    elif expression(touching):
        conditions.append(touching)
    if interception:
        domains = []
    scale = num(norm.get("global_scale"), 1)
    base_range = num(norm.get("attack_range_scaled"))
    limit = num(tv.get("limitingRange"))
    actual_range = min(base_range, limit * scale) if base_range is not None and limit is not None else base_range
    delay_multiplier = num(norm.get("shoot_delay_multiplier"), 1)
    damage_multiplier = num(norm.get("shoot_damage_multiplier"), 1)
    link = derive_link_timing(turret, all_turrets, delay_multiplier)
    direct = num(p.get("direct_damage"), 0 if "directDamage" not in pv else None) if p else None
    area = num(p.get("area_damage"), 0 if "areaDamage" not in pv else None) if p else None
    notes = []
    if p is None:
        notes.append("关联弹体未解析，伤害保持未知，不以零伤害代替。")
    spawn_chain = any(k in pv for k in ("spawnProjectilesOnCreate", "spawnProjectilesOnExplode", "spawnProjectilesOnEndOfLife"))
    continuation = False
    if unit["id"] == "heavySub" and pid == "torpedo":
        locked = projectiles.get("torpedoLocked", {})
        continuation = (pv.get("spawnProjectilesOnEndOfLife") == "torpedoLocked"
                        and num(locked.get("direct_damage")) == direct == 95
                        and str(locked.get("values", {}).get("spawnProjectilesOnEndOfLife", "")).lower() == "none")
        if continuation:
            spawn_chain = False
            notes.append("鱼雷寿命结束后改为同伤害的锁定鱼雷继续追踪；命中伤害仍按95，不把两阶段累计成190。")
    if spawn_chain:
        notes.append("弹体还会派生子弹体；本炮位派生伤害未合并，不把表层伤害作为总输出。")
    if manual:
        notes.append("由动作手动发射，不能按自动射击周期给出常驻DPS。")
    if interception:
        notes.append("这是弹体拦截炮位，伤害数值不是对单位的持续输出。")
    if link:
        notes.append("联动副炮由主炮触发；自身预热保留为相位，不重复计算为独立主炮。")
        if not link["linked_timing_verified"]:
            notes.append("复杂联动周期尚未建立，DPS不强行合计。")
    instant = bool_value(pv.get("instant"))
    deflection = num(pv.get("deflectionPower"), 1)
    interceptable = False if instant or deflection < .5 else True
    if bool_value(pv.get("nukeWeapon")):
        interceptable = False
        notes.append("核弹由专用反核拦截，普通激光防御不能拦截。")
    if bool_value(pv.get("targetGround")):
        notes.append("对地面落点射击；实际命中受目标移动、散布和弹道影响。")
    if bool_value(pv.get("flameWeapon")):
        notes.append("火焰标记本身不赋予隐藏的克盾或建筑倍率。")
    energy_usage = num(tv.get("energyUsage"), 0)
    energy_max = num(norm.get("energy_max"), 0)
    if energy_usage and energy_max is not None and energy_usage > energy_max:
        notes.append("单次能量消耗超过容量，当前形态不能用该炮位开火。")
    if tv.get("resourceUsage"):
        notes.append("每次射击另消耗资源/弹药：" + str(tv["resourceUsage"]))
    aim_id, aim_speed = aim_turret(turret, all_turrets, attack)
    result = {
        "id": tid, "projectile_id": pid, "domains": domains,
        "damage": direct, "area_damage": area, "area_radius": num(p.get("area_radius"), 0 if not area else None) if p else None,
        "damage_multiplier": damage_multiplier, "delay_multiplier": delay_multiplier,
        "delay_ticks": num(turret.get("delay_ticks")), "warmup_ticks": num(turret.get("warmup_ticks"), 0),
        "warmup_no_reset": bool_value(tv.get("warmupNoReset")),
        "warmup_transfer": num(tv.get("warmupShootDelayTransfer"), 0),
        "warmup_decay_per_tick": num(tv.get("warmupCallDownRate"), 0),
        "energy_usage": energy_usage, "linked_to": None,
        "can_shoot": can_shoot, "automatic_fire": bool(unit_auto and can_shoot and not interception),
        "manual_fire": manual, "range": actual_range,
        "minimum_range": times(num(tv.get("limitingMinRange"), 0), scale),
        "shield_damage_multiplier": num(pv.get("shieldDamageMultiplier"), 1),
        "shield_deflection_multiplier": num(pv.get("shieldDefectionMultiplier"), 1),
        "hull_damage_multiplier": num(pv.get("hullDamageMultiplier"), 1),
        "building_damage_multiplier": num(pv.get("buildingDamageMultiplier"), 1),
        "instant": instant, "interceptable": interceptable,
        "deflection_power": deflection, "projectile_speed": num(pv.get("speed")),
        "projectile_target_speed": num(pv.get("targetSpeed")),
        "projectile_life_ticks": ticks(pv.get("life")),
        "ground_targeted": bool_value(pv.get("targetGround")),
        "target_ground": bool_value(pv.get("targetGround")),
        "spread": num(pv.get("targetGroundSpread"), 0),
        "ballistic": bool_value(pv.get("ballistic")) or "gravity" in pv,
        "gravity": num(pv.get("gravity")), "flame_weapon": bool_value(pv.get("flameWeapon")),
        "beam_visual": bool(pv.get("beamImage")),
        "turret_turn_speed": num(tv.get("turnSpeed", attack.get("turretTurnSpeed"))),
        "aim_turret_id": aim_id, "aim_turn_speed": aim_speed,
        "turret_attached_to": str(tv["attachedTo"]) if tv.get("attachedTo") is not None else None,
        "condition": "；".join(conditions) or None,
        "domain_conditions": domain_conditions,
        "target_constraints": constraints, "notes": notes,
        "sources": source_refs(turret.get("provenance", {}), ["canShoot", "projectile", "delay", "warmup", "energyUsage", "linkDelayWithTurret"], unit["source_file"])
                   + source_refs(p.get("provenance", {}) if p else {}, ["directDamage", "areaDamage", "shieldDamageMultiplier", "shieldDefectionMultiplier", "deflectionPower"], unit["source_file"]),
    }
    result.update(link)
    if manual:
        result["mechanism"] = "manual_action"
    elif interception:
        result["mechanism"] = "interception"
        result["non_damage_role"] = "projectile_interception"
    elif spawn_chain:
        result["mechanism"] = "spawn_chain"
        result["timing_verified"] = False
        # Unknown combined payload must not masquerade as zero/known total.
        result["damage"] = None
        result["area_damage"] = None
    return result


def make_ini(unit, catalog):
    core, attack, movement, norm = (unit[k] for k in ("core", "attack", "movement", "normalized"))
    hp, shield = num(norm.get("max_hp")), num(norm.get("max_shield"), 0)
    forward = num(norm.get("move_speed_per_second"))
    reverse_multiplier = num(movement.get("reverseSpeedPercentage"), .6)
    movement_type = norm.get("movement_type")
    energy_regen = times(num(norm.get("energy_regen_per_tick")), TICKS)
    recharge_regen = times(num(core.get("energyRegenWhenRecharging"), num(norm.get("energy_regen_per_tick"))), TICKS)
    attributes = {
        "hp": hp, "shield": shield,
        "hp_regen_per_second": times(num(norm.get("hp_regen_per_tick")), TICKS),
        "shield_regen_per_second": times(num(norm.get("shield_regen_per_tick")), TICKS) if shield else 0,
        "armor": num(norm.get("armour")), "armor_min_damage": num(norm.get("armour_min_damage")),
        "range": num(norm.get("attack_range_scaled")),
        "energy_max": num(norm.get("energy_max")), "energy_regen_per_second": energy_regen,
        "energy_recharge_regen_per_second": recharge_regen,
        "energy_needs_full_recharge": bool_value(core.get("energyNeedsToRechargeToFull")),
        "energy_starting_percentage": num(core.get("energyStartingPercentage"), 1),
        "sight_tiles": num(norm.get("fog_of_war_sight_range_tiles")),
        "can_attack": allowed(attack.get("canAttack", False)),
        "attack_domains": [d for d, k in DOMAIN_KEYS.items() if allowed(attack.get(k, False)) and allowed(attack.get("canAttack", False))],
        "starts_shield_at_zero": bool_value(core.get("startShieldAtZero")),
        "is_building": bool_value(norm.get("is_building")),
        "radius": num(norm.get("radius")),
    }
    behavior_notes = [MOVEMENT_LABELS.get(movement_type, "通行类型尚待确认。")]
    fixed = bool_value(attack.get("isFixedFiring"))
    rotates = bool_value(attack.get("turretRotateWithBody"), True)
    if forward:
        if fixed:
            behavior_notes.append("固定朝向开火；前进撤退与回头射击受车体转向限制。不能仅凭前进速度推断可无限风筝。")
        elif not rotates:
            behavior_notes.append("炮塔/上身与移动朝向独立；退射仍须满足目标角度与炮塔跟踪。")
        behavior_notes.append(f"倒车倍率{reverse_multiplier:g}，最大速度不代表实际持续速度，仍受加减速、转向与碰撞影响。")
    if expression(attack.get("canAttackLandUnits")):
        behavior_notes.append("对地攻击带状态条件：" + attack["canAttackLandUnits"])
    if core.get("startShieldAtZero"):
        behavior_notes.append("该形态从零护盾开始回复，不能视为出生即有满盾。")
    if bool_value(core.get("dieOnZeroEnergy")):
        behavior_notes.append("能量耗尽时死亡；能量还限制存活时间，不只是武器弹药。")
    if movement.get("landOnGround"):
        behavior_notes.append("可降落，攻击/被攻击资格须按当前高度判断；降落配置：" + str(movement["landOnGround"]))
    if bool_value(core.get("canRepairUnits")) or bool_value(core.get("canRepairBuildings")):
        behavior_notes.append("具有维修能力；维修与建造/移动占用同一单位行动，不能同时执行。")
    if core.get("nukeOnDeath"):
        behavior_notes.append(f"死亡核爆：名义伤害{core.get('nukeOnDeathDamage')}，范围{core.get('nukeOnDeathRange')}；受禁核与伤害衰减条件影响。")
    defense = []
    manual_ids = set()
    states, transitions = [], []
    for section, values in unit.get("sections", {}).items():
        if section.startswith(("action_", "hiddenAction_")):
            tid = values.get("fireTurretXAtGround")
            if tid is not None:
                manual_ids.add(str(tid))
            if values.get("convertTo"):
                transitions.append({"id": section, "label": str(values.get("text", values["convertTo"])),
                               "target_native_id": str(values["convertTo"]),
                               "condition": values.get("isActive", values.get("isVisible")),
                               "transition_seconds": build_seconds(values.get("buildSpeed")),
                               "notes": ["转换后的属性以目标对象为准；此记录不承诺当前状态可执行。"]})
    all_turrets = {str(t["id"]): t for t in unit.get("turrets", [])}
    for tid, t in all_turrets.items():
        v = t["values"]
        if v.get("laserDefenceEnergyUse") is not None:
            defense.append({"type": "laser_interception", "turret": tid,
                            "range": num(v.get("limitingRange"), attributes["range"]),
                            "energy_per_interception": num(v["laserDefenceEnergyUse"]),
                            "notes": "只拦满足引擎筛选条件的弹体，受能量限制。"})
    projectiles = {str(p["id"]): p for p in unit.get("projectiles", [])}
    death_turret = all_turrets.get(str(core.get("fireTurretXAtSelfOnDeath")))
    if death_turret:
        death_p = projectiles.get(str(death_turret.get("projectile_id")), {})
        behavior_notes.append(f"死亡触发自爆弹体：直接伤害{death_p.get('direct_damage', '未知')}，范围伤害{death_p.get('area_damage', '未知')}，半径{death_p.get('area_radius', '未知')}；不计为存活期间DPS。")
    weapons = [w for t in all_turrets.values() if (w := make_weapon(unit, t, projectiles, all_turrets, manual_ids)) is not None]
    if unit["id"] == "experimentalDropship":
        flight_weapons, landed_weapons = copy.deepcopy(weapons), copy.deepcopy(weapons)
        for w in flight_weapons:
            w["domains"] = [d for d in w["domains"] if d != "ground"]
            w["domain_conditions"].pop("ground", None)
        for w in landed_weapons:
            w["domain_conditions"].pop("ground", None)
        states = [
            {"id": "flight", "label": "稳定飞行", "attributes": {"attack_domains": ["air"]},
             "weapons": flight_weapons,
             "notes": ["飞行状态只对空；对地条件 if not self.flying 不成立。"]},
            {"id": "landed", "label": "降落静止", "attributes": {"attack_domains": ["air", "ground"]},
             "behavior": {"forward_speed": 0, "reverse_speed": 0}, "weapons": landed_weapons,
             "notes": ["以稳定降落且静止状态观察；移动起飞后失去对地攻击资格。"]},
        ]
    notes = []
    if not attributes["can_attack"]:
        notes.append("无自动对单位攻击；建造、维修、拦截、运输或手动动作不能算成普通武器DPS。")
    if attributes["energy_max"]:
        notes.append("同一单位炮位共享能量池；逐炮位理论火力不能直接当作全单位长期输出。")
    if attributes["shield"]:
        notes.append("HP与护盾分别展示；穿盾、破盾溢出和回复会改变有效耐久。")
    return {
        "native_id": unit["id"], "object_id": catalog["object_id"], "name_zh": catalog["name_zh"],
        "source_kind": "ini", "attributes": attributes,
        "behavior": {"movement_type": movement_type, "forward_speed": forward,
                     "reverse_speed": times(forward, reverse_multiplier), "reverse_multiplier": reverse_multiplier,
                     "turn_speed": num(norm.get("max_turn_speed")),
                     "turn_acceleration": num(movement.get("turnAcceleration")),
                     "acceleration_per_tick": num(norm.get("move_acceleration")),
                     "deceleration_per_tick": num(norm.get("move_deceleration")),
                     "fixed_firing": fixed, "turret_rotates_with_body": rotates,
                     "upper_body_independent": False if fixed else True if not rotates else None,
                     "sliding": bool_value(movement.get("moveSlidingMode")),
                     "ignores_body_direction": bool_value(movement.get("moveIgnoringBody")),
                     "attack_movement": attack.get("attackMovement"),
                     "can_fire_while_moving": None,
                     "notes": behavior_notes},
        "weapons": weapons, "defenses": defense, "notes": notes, "states": states, "transitions": transitions,
        "sources": [reference(unit["source_file"])] + source_refs(unit.get("normalized_provenance", {}),
                   ["max_hp", "max_shield", "shield_regen_per_tick", "move_speed", "attack_range"], unit["source_file"]),
    }


def enrich(profile):
    attr = profile["attributes"]
    if "damage_domains" in attr:
        attr["attack_domains"] = attr["damage_domains"]
    attr.setdefault("attack_domains", list(dict.fromkeys(d for w in profile.get("weapons", []) for d in w.get("domains", []))))
    attr.setdefault("can_attack", bool(attr["attack_domains"]))
    attr.setdefault("energy_recharge_regen_per_second", attr.get("energy_regen_per_second"))
    for w in profile.get("weapons", []):
        w.setdefault("notes", [])
        w.setdefault("can_shoot", True)
        w.setdefault("damage_multiplier", 1)
        w.setdefault("delay_multiplier", 1)
        # Manual launch cadence and interceptors do not have automatic unit DPS.
        if w.get("manual_fire"):
            derivative = {"cold_dps": None, "full_dps": None, "sustained_dps": None,
                          "formula": "手动动作，无自动射击DPS",
                          "conditions": ["显示单次伤害；实际施放依赖动作、弹药与冷却。"]}
        else:
            derivative = derive_weapon(w, attr)
        w["derived"] = derivative
    profile["summary"] = derive_unit_summary([w for w in profile.get("weapons", []) if not w.get("manual_fire")], attr)
    for state in profile.get("states", []):
        merged = {
            "attributes": {**attr, **state.get("attributes", {})},
            "behavior": {**profile.get("behavior", {}), **state.get("behavior", {})},
            "weapons": copy.deepcopy(state.get("weapons", profile.get("weapons", []))),
            "notes": state.get("notes", []), "states": [],
        }
        # A state changing attack domains must not inherit the base alias.
        if "attack_domains" in state.get("attributes", {}) and "damage_domains" not in state["attributes"]:
            merged["attributes"].pop("damage_domains", None)
        enrich(merged)
        state.update(merged)
    return profile


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", type=Path, default=WORKSPACE / "outputs/raw_units.json")
    ap.add_argument("--snapshot", type=Path, default=WORKSPACE / "outputs/rw_units.json")
    ap.add_argument("--catalog", type=Path, default=BASE / "data/units.csv")
    ap.add_argument("--native", type=Path, default=BASE / "tools/native_combat_profiles.json")
    ap.add_argument("--output", type=Path, default=BASE / "data/combat.json")
    args = ap.parse_args()
    raw = {u["id"]: u for u in json.loads(args.raw.read_text(encoding="utf-8-sig"))}
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8-sig"))
    with args.catalog.open(encoding="utf-8-sig", newline="") as f:
        catalog = {u["native_id"]: u for u in csv.DictReader(f)}
    assert set(catalog) == {u["id"] for u in snapshot["units"]}, "Catalog/extraction identity mismatch"
    native = json.loads(args.native.read_text(encoding="utf-8-sig"))
    profiles = {}
    for uid, item in catalog.items():
        source = raw[uid]
        if source["source_kind"] == "ini":
            profile = make_ini(source, item)
        else:
            if uid not in native:
                raise ValueError("Missing reviewed native profile: " + uid)
            profile = native[uid]
            profile.update({"native_id": uid, "object_id": item["object_id"], "name_zh": item["name_zh"], "source_kind": "java"})
            profile.setdefault("sources", [reference(source["source_file"])])
            profile.setdefault("notes", [])
            profile.setdefault("states", [])
            profile.setdefault("defenses", [])
            # Preserve known catalog facts without replacing reviewed state data.
            flat = next(u for u in snapshot["units"] if u["id"] == uid)
            profile["attributes"].setdefault("can_attack", flat.get("can_attack"))
            profile["attributes"]["is_building"] = item.get("category") == "建筑"
            profile["attributes"].setdefault("radius", flat.get("radius"))
            profile["attributes"].setdefault("sight_tiles", source.get("stats", {}).get("sight_tiles"))
        profiles[uid] = enrich(profile)
    output = {
        "schema_version": 1,
        "meta": {"version": "PC 1.15 combat facts v0.2", "generated_at": datetime.now(timezone.utc).isoformat(),
                 "ticks_per_second": TICKS, "speed_unit": "world_units_per_second", "range_unit": "world_units",
                 "turn_speed_unit": "degrees_per_tick", "object_count": len(profiles),
                 "source_jar_sha256": snapshot["manifest"]["jar_sha256"],
                 "extraction_sha256": hashlib.sha256(args.raw.read_bytes()).hexdigest(),
                 "dps_scope": "Continuous-time conditional reference, not match simulation or guaranteed hit rate",
                 "unknown_values": "null means unestablished/conditional; zero means confirmed zero; no weapon means no ordinary attack",
                 "common_conditions": ["60 simulation ticks/s；正常生产倍率与单位定义状态。", "DPS假定合法单目标、持续接敌、有效命中；不含走位、转向、弹道和过量伤害。", "范围项仅为单个目标中心命中上限，不乘附近单位数量。", "护盾扣除与穿入本体分开，回复与破盾边界需逐发计算。", "有能量限制时，满火力是可开火阶段的条件值，能源上界不是实际长期输出。"]},
        "units": profiles,
    }
    serialized = json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False)
    assert not re.search(r"[A-Za-z]:[\\/]", serialized), "Absolute filesystem path leaked"
    for token in ("raw_methods", "raw_sections", "raw_firing_method", "public strictfp"):
        assert token not in serialized, "Game source leaked: " + token
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialized + "\n", encoding="utf-8")
    print(json.dumps({"objects": len(profiles), "weapon_profiles": sum(len(p["weapons"]) for p in profiles.values()),
                      "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
