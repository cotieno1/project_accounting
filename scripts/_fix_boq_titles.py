import json
from pathlib import Path

TITLES = {
    "B2A": "Western Pavilion - Electrical",
    "B2B": "Western Pavilion - CCTV",
    "B2C": "Western Pavilion - Solar",
    "B2D": "Western Pavilion - Structured Cabling and Access",
    "B2E": "Western Pavilion - Lightning Protection",
    "B2F": "Western Pavilion - MATV",
    "B3A": "Eastern Pavilion - Electrical",
    "B3CCTV": "Eastern Pavilion - CCTV",
    "B3B": "Eastern Pavilion - Solar",
    "B3E": "Eastern Pavilion - Lightning Protection",
    "B4": "Ablution Block - Electrical",
    "B5": "Gate House - Electrical",
    "B6": "Area Lighting",
    "B7": "Terrace Lighting",
    "B8": "High Mast Floodlighting",
    "B9": "Power Reticulation",
    "B10": "Project Manager's Stationery",
    "B11": "Provisional Sums and Contingency",
}

for path in [
    Path("scripts/isiolo_boq_lines.json"),
    Path("buildwatch/management/commands/isiolo_boq_lines.json"),
]:
    data = json.loads(path.read_text(encoding="utf-8"))
    for pkg in data["packages"]:
        pkg["title"] = TITLES.get(pkg["code"], pkg["title"])
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(path.name, len(data["packages"]), "ok")
