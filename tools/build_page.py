"""Build the offline page from canonical catalogue CSV and combat JSON."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def csv_rows(name):
    with (ROOT / 'data' / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def embedded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')


def main():
    db = dict(units=csv_rows('units.csv'), tech=csv_rows('tech_relations.csv'),
              transform=csv_rows('transformations.csv'))
    combat = json.loads((ROOT / 'data/combat.json').read_text(encoding='utf-8'))
    assert {u['native_id'] for u in db['units']} == set(combat['units']), 'Combat/catalogue ID mismatch'
    template = (ROOT / 'tools/page_template.html').read_text(encoding='utf-8')
    replacements = {'__DATABASE_JSON__': embedded(db), '__COMBAT_JSON__': embedded(combat),
                    '__APPLICATION_JS__': (ROOT / 'tools/combat-app.js').read_text(encoding='utf-8'),
                    '__COMBAT_CSS__': (ROOT / 'tools/combat.css').read_text(encoding='utf-8')}
    for key, value in replacements.items():
        assert template.count(key) == 1, key
        template = template.replace(key, value)
    (ROOT / 'index.html').write_text(template, encoding='utf-8')
    (ROOT / 'ui').mkdir(exist_ok=True)
    (ROOT / 'ui/data.js').write_text('window.RW_DATA=' + embedded(dict(db=db, combat=combat)) + ';\n', encoding='utf-8')
    print('Built offline catalogue and research-view data:', len(db['units']), 'objects with combat profiles')


if __name__ == '__main__':
    main()
