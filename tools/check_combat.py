"""Check catalogue integration and regressions in published combat facts."""
import csv
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    text = (ROOT / 'data/combat.json').read_text(encoding='utf-8')
    data = json.loads(text)
    units = data['units']
    with (ROOT / 'data/units.csv').open(encoding='utf-8-sig', newline='') as f:
        catalog = list(csv.DictReader(f))
    assert len(units) == 91
    assert set(units) == {u['native_id'] for u in catalog}
    assert 'tree' not in units and 'fogRevealer' not in units
    assert not re.search(r'[A-Za-z]:[\\/]', text), 'Private absolute path'
    assert not any(x in text for x in ('raw_methods', 'raw_sections', 'public strictfp'))
    for uid, profile in units.items():
        assert profile['attributes']['hp'] > 0, uid
        assert profile['behavior']['forward_speed'] is not None, uid
        for state in profile.get('states', []):
            assert 'summary' in state and 'weapons' in state, (uid, state['id'])

    def close(value, expected):
        assert value is not None and math.isclose(value, expected, rel_tol=1e-9), (value, expected)

    def rate(uid, domain='ground'):
        return units[uid]['summary']['domains'][domain]

    close(rate('mechGun')['full_dps'], 23 * 60 / 37)
    close(rate('plasmaTank')['full_dps'], 60)
    close(rate('heavyInterceptor', 'air')['cold_dps'], 72)
    close(rate('heavyInterceptor', 'air')['full_dps'], 144)
    assert len(units['heavyInterceptor']['weapons']) == 2
    close(rate('mechMinigun')['cold_dps'], 55 * 60 / 34)
    close(rate('mechMinigun')['full_dps'], 220)
    close(rate('c_artillery')['full_dps'], 20)
    close(rate('heavyArtillery')['full_dps'], 44)
    assert rate('c_artillery')['single_target_center_upper_bound']
    close(units['mechArtillery']['behavior']['reverse_speed'], 36)
    close(units['c_artillery']['behavior']['reverse_speed'], 32.4)
    assert units['c_artillery']['behavior']['fixed_firing'] is True
    close(units['mechArtillery']['weapons'][0]['aim_turn_speed'], 2.9)
    close(rate('c_mammothTank')['full_dps'], 97.5)
    close(units['c_mammothTank']['weapons'][0]['derived']['hp_through_full_shield_per_shot'], 117)
    close(units['c_mammothTank']['weapons'][0]['derived']['shield_damage_per_shot'], 130)
    close(rate('aaBeamGunship', 'air')['full_dps'], 264)
    assert rate('aaBeamGunship', 'air')['sustained_dps'] is None
    close(rate('aaBeamGunship_afterburn', 'air')['full_dps'], 0)
    close(rate('mechLaser')['full_dps'], 270)
    close(rate('mechLaser')['energy_dps_cap'], 59.4)
    assert rate('mechLaser')['sustained_dps'] is None
    close(rate('experimentalHoverTank')['full_dps'], 380)
    close(units['experimentalHoverTank']['weapons'][0]['derived']['first_shot_seconds'], 8 / 60)
    close(rate('heavyTank')['full_dps'], 50 * 60 / 70)
    close(rate('heavyTank', 'air')['full_dps'], 50 * 60 / 70)
    assert units['heavyTank']['summary']['all_domains_total_dps'] is None
    close(rate('battleShip')['full_dps'], 65 * 60 / 120 + 65 * 60 / 122)
    close(rate('heavySub', 'underwater')['full_dps'], 114)
    assert not units['nukeLauncherC']['summary']['domains']
    assert not units['antiNukeLauncherC']['summary']['domains']
    states = {s['id']: s for s in units['amphibiousJet']['states']}
    assert set(states['submerged']['summary']['domains']) == {'ground', 'underwater'}
    close(states['submerged']['behavior']['forward_speed'], 24)
    fortress = {s['id']: s for s in units['experimentalDropship']['states']}
    assert set(fortress['flight']['summary']['domains']) == {'air'}
    assert set(fortress['landed']['summary']['domains']) == {'ground', 'air'}
    html = (ROOT / 'index.html').read_text(encoding='utf-8')
    embedded = json.loads(re.search(r'<script type="application/json" id="combat-db">(.*?)</script>', html, re.S).group(1))
    assert embedded == data, 'HTML combat data drift'
    db = json.loads(re.search(r'<script type="application/json" id="db">(.*?)</script>', html, re.S).group(1))
    assert db['units'] == catalog, 'HTML catalogue drift'
    for key, filename in [('tech', 'tech_relations.csv'), ('transform', 'transformations.csv')]:
        with (ROOT / 'data' / filename).open(encoding='utf-8-sig', newline='') as f:
            assert db[key] == list(csv.DictReader(f)), 'HTML relation data drift'
    print(json.dumps({'objects': len(units), 'weapon_profiles': sum(len(p['weapons']) for p in units.values()),
                      'states': sum(len(p.get('states', [])) for p in units.values()),
                      'critical_regressions': 'pass', 'embedded_data': 'matches'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
