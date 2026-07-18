from pathlib import Path
p = Path("buildwatch/management/commands/seed_isiolo_boq.py")
t = p.read_text(encoding="utf-8")
t2 = t.replace(
    'bill_ref=ref,\n                    defaults={\n                        "description": line["description"],\n                        "unit": line["unit"],',
    'bill_ref=ref[:20],\n                    defaults={\n                        "description": (line.get("description") or "")[:255],\n                        "unit": (line.get("unit") or "No")[:30],',
)
if t2 == t:
    raise SystemExit("no change")
p.write_text(t2, encoding="utf-8")
print("seed patched")
