from pathlib import Path
import csv
root=Path(__file__).resolve().parents[1]/"data"
def read(name):
    with (root/name).open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))
units=read("units.csv")
tech=read("tech_relations.csv")
trans=read("transformations.csv")
assert len(units)==91
ids={x["object_id"] for x in units}
assert len(ids)==91
for rows in (tech,trans):
    assert len({x["relation_id"] for x in rows})==len(rows)
    assert all(x["source_id"] in ids and x["target_id"] in ids for x in rows)
    assert all(x["cost_credits"]=="" or float(x["cost_credits"])>=0 for x in rows)
print("PASS units",len(units),"tech",len(tech),"transform",len(trans))
