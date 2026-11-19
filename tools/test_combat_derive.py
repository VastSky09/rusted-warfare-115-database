"""Regression tests for mistakes that change RW combat conclusions."""
import unittest

from combat_derive import derive_unit_summary, derive_weapon


def weapon(**kwargs):
    return {"id": "gun", "domains": ["ground"], "can_shoot": True, **kwargs}


class ConditionalDpsTests(unittest.TestCase):
    def test_empty_domain_map_preserves_global_attack_condition(self):
        result = derive_unit_summary([weapon(damage=50, delay_ticks=60,
            condition="if self.overwater", domain_conditions={})])["domains"]["ground"]
        self.assertEqual(result["status"], "conditional")
        self.assertTrue(any("if self.overwater" in c for c in result["conditions"]))

    def test_global_and_domain_conditions_are_both_retained(self):
        gun = weapon(damage=50, delay_ticks=60, domains=["ground", "air"],
            condition="if self.hasFlag(id=1)", domain_conditions={"ground": "if not self.flying"})
        result = derive_unit_summary([gun])["domains"]
        ground = " ".join(result["ground"]["conditions"])
        air = " ".join(result["air"]["conditions"])
        self.assertIn("if self.hasFlag(id=1)", ground)
        self.assertIn("if not self.flying", ground)
        self.assertIn("if self.hasFlag(id=1)", air)
        self.assertNotIn("if not self.flying", air)

    def test_opposite_global_conditions_do_not_become_simultaneous_firepower(self):
        guns = [weapon(id="on",damage=50,delay_ticks=60,condition="if self.hasFlag(id=0)",domain_conditions={}),
                weapon(id="off",damage=80,delay_ticks=60,condition="if not self.hasFlag(id=0)",domain_conditions={})]
        result = derive_unit_summary(guns)["domains"]["ground"]
        self.assertEqual(result["status"], "conditional_unresolved")
        self.assertIsNone(result["full_dps"])
        self.assertIsNone(result["sustained_dps"])

    def test_per_shot_warmup_is_in_every_cycle(self):
        mech = derive_weapon(weapon(damage=23, delay_ticks=30, warmup_ticks=7))
        plasma = derive_weapon(weapon(damage=100, delay_ticks=90, warmup_ticks=10))
        self.assertAlmostEqual(mech["full_dps"], 23 * 60 / 37)
        self.assertAlmostEqual(mech["first_shot_seconds"], 7 / 60)
        self.assertEqual(plasma["full_dps"], 60)

    def test_heavy_interceptor_has_two_real_guns_not_three(self):
        main = weapon(id="left", domains=["air"], damage=12, delay_ticks=20,
                      warmup_ticks=200, warmup_no_reset=True, warmup_transfer=10)
        slave = weapon(id="right", domains=["air"], damage=12, delay_ticks=None,
                       warmup_ticks=200, warmup_no_reset=True, linked_to="left",
                       linked_cold_period_ticks=20, linked_full_period_ticks=10,
                       linked_timing_verified=True)
        body = weapon(id="body", domains=["air"], damage=12, delay_ticks=20, can_shoot=False)
        result = derive_unit_summary([main, slave, body])["domains"]["air"]
        self.assertEqual(result["cold_dps"], 72)
        self.assertEqual(result["full_dps"], 144)
        self.assertEqual(derive_weapon(main)["first_shot_seconds"], 0)
        self.assertAlmostEqual(derive_weapon(main)["heat_ramp_seconds"], 200 / 60)

    def test_unknown_linked_event_period_is_not_invented(self):
        slave = weapon(damage=140, delay_ticks=None, warmup_ticks=35, linked_to="main")
        self.assertIsNone(derive_weapon(slave)["full_dps"])
        self.assertIsNone(derive_unit_summary([slave])["domains"]["ground"]["full_dps"])

    def test_linked_warmup_is_a_phase_not_a_second_cycle_addition(self):
        slave = weapon(damage=140, delay_ticks=None, warmup_ticks=35, linked_to="main",
                       linked_period_ticks=115, linked_timing_verified=True)
        self.assertAlmostEqual(derive_weapon(slave)["full_dps"], 140 * 60 / 115)

    def test_experimental_tank_linked_phases_do_not_lengthen_each_cycle(self):
        guns = [weapon(id="main", damage=0, area_damage=120, delay_ticks=160)]
        guns += [weapon(id=str(phase), damage=0, area_damage=120, delay_ticks=None,
                        warmup_ticks=phase, linked_to="main", linked_period_ticks=160,
                        linked_timing_verified=True) for phase in (30, 60, 80)]
        result = derive_unit_summary(guns)["domains"]["ground"]
        self.assertEqual(result["full_dps"], 180)

    def test_energy_full_recharge_ceiling_is_not_actual_sustained_dps(self):
        beam = weapon(damage=22, delay_ticks=5, energy_usage=.5,
                      shield_damage_multiplier=.75)
        attrs = {"energy_max": 6, "energy_regen_per_second": .6,
                 "energy_recharge_regen_per_second": 3,
                 "energy_needs_full_recharge": True}
        result = derive_weapon(beam, attrs)
        self.assertEqual(result["full_dps"], 264)
        self.assertEqual(result["shield_dps"], 198)
        self.assertEqual(result["burst_shots_from_full"], 12)
        self.assertEqual(result["energy_dps_cap"], 132)
        self.assertIsNone(result["sustained_dps"])

    def test_shared_battery_is_not_counted_twice(self):
        guns = [weapon(id=str(i), damage=50, delay_ticks=60, energy_usage=1) for i in range(2)]
        result = derive_unit_summary(guns, {"energy_max": 6, "energy_regen_per_second": .5})["domains"]["ground"]
        self.assertEqual(result["full_dps"], 100)
        self.assertEqual(result["energy_dps_cap"], 25)
        self.assertIn("最大单次伤害/能量 50", result["energy_cap_formula"])
        self.assertIsNone(result["sustained_dps"])
        self.assertEqual(len(result["energy_groups"]), 1)

    def test_battery_can_be_limited_only_when_both_guns_fire(self):
        attrs = {"energy_max": 6, "energy_regen_per_second": 1.5}
        guns = [weapon(id=str(i), damage=50, delay_ticks=60, energy_usage=1) for i in range(2)]
        self.assertFalse(derive_weapon(guns[0], attrs)["energy_limited"])
        result = derive_unit_summary(guns, attrs)["domains"]["ground"]
        self.assertEqual(result["energy_dps_cap"], 75)
        self.assertIsNone(result["sustained_dps"])

    def test_afterburn_energy_cost_cannot_fire_from_six_capacity(self):
        result = derive_weapon(weapon(damage=22, delay_ticks=5, energy_usage=99),
                               {"energy_max": 6, "energy_regen_per_second": .6})
        self.assertEqual(result["status"], "energy_disabled")
        self.assertEqual(result["full_dps"], 0)
        self.assertEqual(result["nominal_unconstrained_full_dps"], 264)

    def test_aoe_is_one_target_center_ceiling_not_a_density_multiplier(self):
        result = derive_weapon(weapon(damage=70, area_damage=45, area_radius=65,
                                      delay_ticks=130, warmup_ticks=2, target_count=10))
        self.assertAlmostEqual(result["full_dps"], 115 * 60 / 132)
        self.assertTrue(result["single_target_center_upper_bound"])
        self.assertFalse(result["aoe"]["targets_multiplied"])

    def test_target_ground_artillery_does_not_invent_direct_hit(self):
        result = derive_weapon(weapon(damage=1, area_damage=80, area_radius=45,
                                      target_ground=True, delay_ticks=240))
        self.assertEqual(result["configured_direct_damage"], 1)
        self.assertEqual(result["damage_per_shot"], 80)
        self.assertEqual(result["full_dps"], 20)

    def test_mammoth_drains_full_shield_and_bypasses_hp_separately(self):
        result = derive_weapon(weapon(damage=130, delay_ticks=50, warmup_ticks=30,
                                      shield_damage_multiplier=1,
                                      shield_deflection_multiplier=.1,
                                      building_damage_multiplier=.5))
        self.assertEqual(result["full_dps"], 97.5)
        self.assertEqual(result["shield_damage_per_shot"], 130)
        self.assertEqual(result["hp_through_full_shield_per_shot"], 117)
        self.assertEqual(result["shield_dps"], 97.5)
        self.assertEqual(result["building_dps"], 48.75)

    def test_continuous_beam_does_not_multiply_by_eight_tick_event(self):
        result = derive_weapon(weapon(mechanism="continuous_beam", full_dps=380,
                                      cold_dps=380 * 70 / 230, ramp_seconds=160 / 60,
                                      delay_ticks=8, warmup_ticks=8, shield_damage_multiplier=.75))
        self.assertEqual(result["full_dps"], 380)
        self.assertAlmostEqual(result["cold_dps"], 380 * 70 / 230)
        self.assertAlmostEqual(result["first_shot_seconds"], 8 / 60)
        self.assertEqual(result["shield_dps"], 285)
        self.assertIsNone(result["cycle_seconds"])

    def test_continuous_beam_explicit_initial_delay_overrides_warmup(self):
        result = derive_weapon(weapon(mechanism="continuous_beam", full_dps=380,
                                      warmup_ticks=8, first_shot_seconds=.5))
        self.assertEqual(result["first_shot_seconds"], .5)

    def test_unknown_damage_or_period_stays_unknown(self):
        self.assertIsNone(derive_weapon(weapon(delay_ticks=30))["full_dps"])
        self.assertIsNone(derive_weapon(weapon(damage=100))["full_dps"])
        self.assertIsNone(derive_unit_summary([weapon(damage=100)])["domains"]["ground"]["full_dps"])
        self.assertIsNone(derive_weapon(weapon(damage=100, delay_ticks=30, timing_verified=False))["full_dps"])

    def test_same_gun_domain_branches_have_no_cross_domain_total(self):
        guns = [weapon(id="land", damage=50, delay_ticks=70, cooldown_group="cannon"),
                weapon(id="air", domains=["air"], damage=50, delay_ticks=70, cooldown_group="cannon")]
        result = derive_unit_summary(guns)
        self.assertAlmostEqual(result["domains"]["ground"]["full_dps"], 50 * 60 / 70)
        self.assertAlmostEqual(result["domains"]["air"]["full_dps"], 50 * 60 / 70)
        self.assertIsNone(result["all_domains_total_dps"])

    def test_same_domain_alternatives_are_not_added(self):
        guns = [weapon(id="a", damage=50, delay_ticks=60, alternative_group="gun"),
                weapon(id="b", damage=80, delay_ticks=60, alternative_group="gun")]
        result = derive_unit_summary(guns)["domains"]["ground"]
        self.assertIsNone(result["full_dps"])
        self.assertEqual(result["full_dps_upper_bound"], 80)

    def test_landed_ground_condition_does_not_pollute_air_summary(self):
        gun = weapon(domains=["ground", "air"], damage=50, delay_ticks=60,
                     domain_conditions={"ground": "if not self.flying"})
        result = derive_unit_summary([gun])
        self.assertEqual(result["domains"]["air"]["status"], "derived")
        self.assertEqual(result["domains"]["air"]["conditions"], [])
        self.assertIn("if not self.flying", " ".join(result["domains"]["ground"]["conditions"]))

    def test_body_and_interceptor_only_unit_have_no_fake_zero_dps(self):
        result = derive_unit_summary([weapon(can_shoot=False), weapon(mechanism="interception")])
        self.assertEqual(result["status"], "no_damage_weapons")
        self.assertEqual(result["domains"], {})

    def test_manual_action_weapon_is_not_automatic_dps(self):
        gun = weapon(damage=0, area_damage=5400, delay_ticks=60, manual_fire=True)
        self.assertIsNone(derive_weapon(gun)["full_dps"])
        self.assertEqual(derive_unit_summary([gun])["status"], "no_damage_weapons")


if __name__ == "__main__":
    unittest.main()
