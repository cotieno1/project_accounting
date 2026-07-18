from pathlib import Path

def w(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.replace("\r\n", "\n"), encoding="utf-8")
    print("wrote", p)

# fix normalize
w("buildwatch/boq_ingest/normalize.py", r'''"""Shared unit / quantity / description normalization."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


def normalize_unit(raw: str) -> str:
    u = (raw or "").rstrip(".").strip()
    ul = u.lower()
    if ul.startswith("no"):
        return "No"
    if ul.startswith("lm") or ul == "m":
        return "Lm"
    if ul == "sum":
        return "Sum"
    if ul == "item":
        return "Item"
    if ul == "lot":
        return "Lot"
    if ul == "set":
        return "Set"
    return (u or "No")[:30]


def parse_qty(raw) -> Decimal:
    if isinstance(raw, Decimal):
        return raw
    s = str(raw).replace(",", "").strip()
    try:
        q = Decimal(s)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid quantity: %r" % (raw,)) from exc
    if q <= 0:
        raise ValueError("quantity must be > 0: %r" % (raw,))
    return q


def clean_description(text: str, max_len: int = 255) -> str:
    desc = re.sub(r"\s+", " ", (text or "").strip(" -.,"))
    return desc[:max_len]
''')

# isiolo adapter - full parser with RFQ bill categories matching production
w("buildwatch/boq_ingest/adapters/isiolo_domestic_pdf.py", r'''"""Adapter for Sports Kenya Isiolo domestic electrical tender PDF."""
from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from ..normalize import clean_description, normalize_unit, parse_qty
from ..schema import StandardBoq, StandardBoqCategory, StandardBoqLine
from .base import BoqAdapter

ADAPTER_ID = "isiolo_domestic_pdf"

# Tender schedule number -> RFQ bill category (matches live Isiolo seed shape)
SCHEDULE_PKG = {
    1: "B2A", 2: "B2A", 3: "B2A", 4: "B2A",
    5: "B2B",
    6: "B2C",
    7: "B2D",
    8: "B2E",
    9: "B2F",
    10: "B3A", 11: "B3A", 12: "B3A", 13: "B3A",
    14: "B3CCTV",
    15: "B3B",
    16: "B3E",
    17: "B4",
    18: "B5",
    19: "B6",
    20: "B7",
    21: "B8",
    22: "B9",
    23: "B10",
    24: "B11",
}

PKG_META = [
    ("B2A", "Western Pavilion - Electrical", 10),
    ("B2B", "Western Pavilion - CCTV", 20),
    ("B2C", "Western Pavilion - Solar", 30),
    ("B2D", "Western Pavilion - Structured Cabling and Access", 40),
    ("B2E", "Western Pavilion - Lightning Protection", 50),
    ("B2F", "Western Pavilion - MATV", 60),
    ("B3A", "Eastern Pavilion - Electrical", 70),
    ("B3CCTV", "Eastern Pavilion - CCTV", 80),
    ("B3B", "Eastern Pavilion - Solar", 90),
    ("B3E", "Eastern Pavilion - Lightning Protection", 100),
    ("B4", "Ablution Block - Electrical", 110),
    ("B5", "Gate House - Electrical", 120),
    ("B6", "Area Lighting", 130),
    ("B7", "Terrace Lighting", 140),
    ("B8", "High Mast Floodlighting", 150),
    ("B9", "Power Reticulation", 160),
    ("B10", "Project Manager's Stationery", 170),
    ("B11", "Provisional Sums and Contingency", 180),
]

SCHED_RE = re.compile(
    r"(?i)SCHEDULE\s+NO\.?\s*(?:NO\.?\s*)?(\d+)\s*:\s*([^\n]{0,120})"
)
ITEM_START = re.compile(r"^(\d+\.\d+)\s+(.*)$")
UNIT_QTY = re.compile(
    r"(?i)(?<![A-Za-z0-9])(No\.?|Nos\.?|Lm\.?|Sum|Item|Lot|Set|Kg)\s+"
    r"(\d+(?:,\d{3})*(?:\.\d+)?)\b"
)
QTY_UNIT = re.compile(
    r"(?i)(?<![A-Za-z0-9])(\d+(?:,\d{3})*(?:\.\d+)?)\s+"
    r"(No\.?|Nos\.?|Lm\.?|Sum|Item|Lot|Set)\b"
)
UNIT_UNIT = re.compile(r"(?i)\b(Item|Sum|Lot)\s+\1\b")
SKIP_SECTION = re.compile(
    r"(?i)^\s*(LIGHTING|SOCKET|DISTRIBUTION|SUB-MAINS|FIRE ALARM|CCTV|"
    r"HORIZONTAL|BACKBONE|ACTIVE|ACCESS|POWER|EARTHING|AIR TERMINATION|"
    r"LIGHT FITTINGS|DATA AND TV)\b"
)


def _extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts = []
        for i, page in enumerate(reader.pages):
            parts.append("---PAGE %d---\n%s" % (i + 1, page.extract_text() or ""))
        return "\n".join(parts)
    raise ValueError("isiolo_domestic_pdf expects .pdf or .txt, got %s" % suffix)


def _extract_unit_qty(rest: str):
    mu = UNIT_UNIT.search(rest)
    if mu and mu.start() >= 8:
        return (
            clean_description(rest[: mu.start()]),
            normalize_unit(mu.group(1)),
            Decimal("1"),
        )

    candidates = []
    for m in UNIT_QTY.finditer(rest):
        if m.start() < 8:
            continue
        candidates.append(
            (m.start(), normalize_unit(m.group(1)), parse_qty(m.group(2)), m.end())
        )
    for m in QTY_UNIT.finditer(rest):
        if m.start() < 8:
            continue
        candidates.append(
            (m.start(), normalize_unit(m.group(2)), parse_qty(m.group(1)), m.end())
        )
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    start, unit, qty, end = candidates[0]
    desc = rest[:start].strip(" -.,")
    trailing = rest[end:].strip()
    if trailing and not UNIT_QTY.search(trailing) and not QTY_UNIT.search(trailing):
        if len(trailing) < 220 and not trailing[:1].isdigit():
            desc = (desc + " " + trailing).strip()
    desc = clean_description(desc)
    if len(desc) < 3:
        return None
    return desc, unit, qty


def parse_isiolo_text(text: str, source_name: str) -> StandardBoq:
    warnings = []
    marker = text.find("PROVISIONAL SUMS")
    if marker > 0:
        cut = text.find("BILL NO.1: SCHEDULE 1: PRELIMINARIES", marker + 50)
        if cut > 0:
            text = text[:cut]

    lines = text.splitlines()
    sections = []
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

    if not sections:
        warnings.append("No SCHEDULE NO. sections found")

    packages = defaultdict(list)
    seen_refs = set()

    for idx, (sno, stitle, start) in enumerate(sections):
        end = sections[idx + 1][2] if idx + 1 < len(sections) else len(lines)
        chunk_lines = []
        for j in range(start + 1, end):
            up = lines[j].upper()
            if "COLLECTION PAGE" in up:
                break
            if re.match(r"(?i)^\s*Total for", lines[j]):
                break
            chunk_lines.append(lines[j])

        buf = ""
        items_raw = []
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
                buf = buf + " " + stripped
        if buf:
            items_raw.append(buf)

        pkg = SCHEDULE_PKG[sno]
        for raw in items_raw:
            m = ITEM_START.match(raw)
            if not m:
                continue
            ref_num, rest = m.group(1), m.group(2)
            parsed = _extract_unit_qty(rest)
            if not parsed:
                continue
            desc, unit, qty = parsed
            if desc.upper().startswith("SCHEDULE"):
                continue
            bill_ref = ("%s/%s" % (sno, ref_num))[:20]
            if bill_ref in seen_refs:
                continue
            seen_refs.add(bill_ref)
            packages[pkg].append(
                StandardBoqLine(
                    bill_ref=bill_ref,
                    description=desc,
                    unit=unit,
                    quantity=qty,
                    sort_order=len(packages[pkg]) + 1,
                    extras={"schedule": sno},
                )
            )

    categories = []
    for code, title, order in PKG_META:
        if not packages[code]:
            continue
        categories.append(
            StandardBoqCategory(
                code=code,
                title=title,
                sort_order=order,
                lines=packages[code],
            )
        )

    return StandardBoq(
        source_name=source_name,
        adapter_id=ADAPTER_ID,
        categories=categories,
        warnings=warnings,
        meta={"schedules_found": len(sections), "category_count": len(categories)},
    )


class IsioloDomesticPdfAdapter(BoqAdapter):
    id = ADAPTER_ID
    label = "Isiolo Stadium domestic electrical tender PDF"

    def can_handle(self, path: Path, text_sample: str = "") -> float:
        name = path.name.lower()
        score = 0.0
        if "isiolo" in name:
            score += 0.45
        if "stadium" in name:
            score += 0.15
        if path.suffix.lower() in {".pdf", ".txt"}:
            score += 0.1
        sample = (text_sample or "").lower()
        if "isiolo" in sample:
            score += 0.2
        if "schedule no" in sample and "western pav" in sample.replace("pavilion", "pav"):
            score += 0.25
        if "sk/004" in sample or "sk_004" in sample:
            score += 0.2
        return min(score, 1.0)

    def parse(self, path: Path) -> StandardBoq:
        text = _extract_text(path)
        return parse_isiolo_text(text, source_name=path.name)
''')

w("buildwatch/boq_ingest/adapters/__init__.py", '''"""Format-specific RFQ/BOQ adapters."""
from .base import BoqAdapter
from .isiolo_domestic_pdf import IsioloDomesticPdfAdapter
from ..registry import register

register(IsioloDomesticPdfAdapter())

__all__ = ["BoqAdapter", "IsioloDomesticPdfAdapter"]
''')

# dry-run command - NO DB writes to TenderBoq*
w("buildwatch/management/commands/dry_run_boq_ingest.py", r'''"""Dry-run RFQ/BOQ ingest -> StandardBoq JSON (no TenderBoq DB writes)."""
from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from buildwatch.boq_ingest import detect_adapter, get_adapter, list_adapters


class Command(BaseCommand):
    help = (
        "Parse an RFQ/BOQ file into StandardBoq JSON without writing "
        "TenderBoqPackage/Line or touching the live Isiolo seed."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to PDF/TXT/…")
        parser.add_argument(
            "--adapter",
            default="auto",
            help="Adapter id or 'auto' (available: %s)" % ", ".join(list_adapters() or ["isiolo_domestic_pdf"]),
        )
        parser.add_argument(
            "--out",
            default="",
            help="Optional output JSON path (default: stdout summary + scripts/_dry_run_*.json)",
        )

    def handle(self, *args, **options):
        path = Path(options["file"]).expanduser().resolve()
        if not path.exists():
            raise CommandError("File not found: %s" % path)

        adapter_id = (options["adapter"] or "auto").strip()
        if adapter_id == "auto":
            adapter, score = detect_adapter(path)
            self.stdout.write("auto-detected %s (confidence %.2f)" % (adapter.id, score))
        else:
            adapter = get_adapter(adapter_id)
            self.stdout.write("using adapter %s" % adapter.id)

        doc = adapter.parse(path)
        payload = doc.to_dict()

        out = options["out"]
        if out:
            out_path = Path(out).expanduser().resolve()
        else:
            out_path = Path("scripts") / ("_dry_run_%s.json" % adapter.id)
            out_path.parent.mkdir(parents=True, exist_ok=True)

        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(
            "OK adapter=%s categories=%d lines=%d warnings=%d -> %s"
            % (
                doc.adapter_id,
                len(doc.categories),
                doc.line_count,
                len(doc.warnings),
                out_path,
            )
        ))
        for cat in doc.categories:
            self.stdout.write(
                "  %s  %3d  %s" % (cat.code, len(cat.lines), cat.title)
            )
        for wmsg in doc.warnings:
            self.stdout.write(self.style.WARNING("  warn: %s" % wmsg))
        self.stdout.write(
            "NOTE: dry-run only — did not modify TenderBoqPackage/Line or seed_isiolo_boq."
        )
''')

print("adapter + dry-run written")