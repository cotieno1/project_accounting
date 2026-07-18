"""Parse Isiolo tender PDF text extract into BOQ package JSON."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

TEXT_PATH = Path(__file__).with_name("_isiolo_tender_all.txt")
OUT_PATH = Path(__file__).with_name("isiolo_boq_lines.json")

# Map BOQ schedule numbers -> selectable packages (RFQ disciplines)
SCHEDULE_PKG = {
    1: "ELEC",
    2: "ELEC",
    3: "ELEC",
    4: "ELEC",
    5: "CCTV",
    6: "SOLAR",
    7: "CABLING",
    8: "ELEC",  # lightning protection
    9: "ELEC",  # MATV
    10: "ELEC",
    11: "ELEC",
    12: "ELEC",
    13: "ELEC",
    14: "CCTV",
    15: "SOLAR",
    16: "ELEC",  # eastern lightning
    17: "ELEC",  # ablution
    18: "ELEC",  # gate house
    19: "ELEC",  # area lighting
    20: "ELEC",  # terrace lighting
    21: "ELEC",  # high mast
    22: "ELEC",  # power reticulation
    23: "ELEC",  # stationery
    24: "ELEC",  # provisional sums
}

PKG_TITLES = {
    "ELEC": "Electrical Works",
    "CABLING": "Structured Cabling",
    "CCTV": "CCTV Works",
    "SOLAR": "Solar Installation Works",
}

SCHED_RE = re.compile(
    r"(?i)SCHEDULE\s+NO\.?\s*(?:NO\.?\s*)?(\d+)\s*:\s*([^\n]{0,120})"
)
ITEM_START = re.compile(r"^(\d+\.\d+)\s+(.*)$")
UNIT_QTY = re.compile(
    r"(?i)(?:^|\s)(No\.?|Nos\.?|Lm\.?|m\.?|Sum|Item|Lot|Set|Kg|kg|Pairs?)"
    r"\s*[.\s]*(\d+(?:,\d{3})*(?:\.\d+)?)\s*$"
)
QTY_UNIT = re.compile(
    r"(?i)(?:^|\s)(\d+(?:,\d{3})*(?:\.\d+)?)\s+"
    r"(No\.?|Nos\.?|Lm\.?|m\.?|Sum|Item|Lot|Set)\s*$"
)
UNIT_UNIT = re.compile(r"(?i)\b(Item|Sum|Lot)\s+\1\s*$")
SKIP_SECTION = re.compile(
    r"(?i)^\s*(LIGHTING|SOCKET|DISTRIBUTION|SUB-MAINS|FIRE ALARM|CCTV|"
    r"HORIZONTAL|BACKBONE|ACTIVE|ACCESS|POWER|EARTHING|AIR TERMINATION)\b"
)


def normalize_unit(u: str) -> str:
    u = u.rstrip(".").strip()
    ul = u.lower()
    if ul.startswith("no"):
        return "No"
    if ul.startswith("lm") or ul == "m":
        return "Lm"
    if ul == "sum":
        return "Sum"
    if ul == "item":
        return "Item"
    return u[:12]


def parse_qty(s: str) -> Decimal:
    return Decimal(s.replace(",", ""))


def main() -> None:
    text = TEXT_PATH.read_text(encoding="utf-8", errors="replace")
    # Drop duplicated summary appendix after provisional sums
    marker = text.find("PROVISIONAL SUMS")
    if marker > 0:
        cut = text.find("BILL NO.1: SCHEDULE 1: PRELIMINARIES", marker + 50)
        if cut > 0:
            text = text[:cut]

    lines = text.splitlines()
    sections: list[tuple[int, str, int]] = []
    for i, ln in enumerate(lines):
        m = SCHED_RE.search(ln)
        if not m:
            continue
        if re.match(r"^\s*\d+\.\d+\s+SCHEDULE", ln.strip()):
            continue
        sno = int(m.group(1))
        title = m.group(2).strip()
        if sno in SCHEDULE_PKG:
            sections.append((sno, title, i))

    packages: dict[str, list[dict]] = defaultdict(list)
    seen_refs: set[str] = set()

    for idx, (sno, stitle, start) in enumerate(sections):
        end = sections[idx + 1][2] if idx + 1 < len(sections) else len(lines)
        chunk_lines: list[str] = []
        for j in range(start + 1, end):
            up = lines[j].upper()
            if "COLLECTION PAGE" in up:
                break
            if re.match(r"(?i)^\s*Total for", lines[j]):
                break
            chunk_lines.append(lines[j])

        buf = ""
        items_raw: list[str] = []
        for ln in chunk_lines:
            raw = ln.rstrip()
            if re.search(r"(?i)ITEM\s+DESCRIPTION\s+UNIT", raw):
                continue
            if re.search(r"(?i)Sub\s*-\s*Total", raw):
                continue
            if re.search(r"(?i)Carried Forward|brought Forward", raw):
                continue
            if re.search(r"(?i)^Supply, Deliver", raw):
                continue
            stripped = raw.strip()
            m = ITEM_START.match(stripped)
            if m:
                if buf:
                    items_raw.append(buf)
                buf = stripped
            elif buf and stripped:
                if SKIP_SECTION.match(stripped) and not ITEM_START.match(stripped):
                    continue
                buf = f"{buf} {stripped}"
        if buf:
            items_raw.append(buf)

        pkg = SCHEDULE_PKG[sno]
        count = 0
        for raw in items_raw:
            m = ITEM_START.match(raw)
            if not m:
                continue
            ref_num, rest = m.group(1), m.group(2)
            unit = None
            qty = None
            desc = ""

            mu = UNIT_UNIT.search(rest)
            if mu:
                unit = normalize_unit(mu.group(1))
                qty = Decimal("1")
                desc = rest[: mu.start()].strip(" -.,")
            else:
                mq = UNIT_QTY.search(rest)
                if mq:
                    unit = normalize_unit(mq.group(1))
                    qty = parse_qty(mq.group(2))
                    desc = rest[: mq.start()].strip(" -.,")
                else:
                    mq2 = QTY_UNIT.search(rest)
                    if mq2:
                        qty = parse_qty(mq2.group(1))
                        unit = normalize_unit(mq2.group(2))
                        desc = rest[: mq2.start()].strip(" -.,")
                    else:
                        continue

            if not desc or len(desc) < 3:
                continue
            if desc.upper().startswith("SCHEDULE"):
                continue

            bill_ref = f"{sno}/{ref_num}"
            if bill_ref in seen_refs:
                continue
            seen_refs.add(bill_ref)
            desc = re.sub(r"\s+", " ", desc)[:400]
            packages[pkg].append(
                {
                    "bill_ref": bill_ref,
                    "description": desc,
                    "unit": unit,
                    "quantity": str(qty),
                    "sort_order": len(packages[pkg]) + 1,
                    "schedule": sno,
                }
            )
            count += 1
        print(f"schedule {sno} ({stitle[:50]}) -> {pkg}: {count} lines")

    out = {
        "packages": [
            {
                "code": code,
                "title": PKG_TITLES[code],
                "sort_order": i,
                "lines": packages[code],
            }
            for i, code in enumerate(["ELEC", "CABLING", "CCTV", "SOLAR"], 1)
        ]
    }
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    total = sum(len(packages[c]) for c in PKG_TITLES)
    print(f"wrote {OUT_PATH} total_lines={total}")
    for code in PKG_TITLES:
        sample = packages[code][:1]
        print(f"  {code}: {len(packages[code])}  sample={sample}")


if __name__ == "__main__":
    main()
