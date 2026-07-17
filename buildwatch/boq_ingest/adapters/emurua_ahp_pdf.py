"""Adapter for Emurua Dikirr AHP (Kenya SMM housing) priced BOQ PDFs."""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from ..normalize import clean_description, normalize_unit, parse_qty
from ..schema import StandardBoq, StandardBoqCategory, StandardBoqLine
from .base import BoqAdapter

ADAPTER_ID = "emurua_ahp_pdf"

UNIT_TOKEN = (
    r"(SM|Sm|LM|Lm|CM|Cm|KG|Kg|NO|No|Nr|ITEM|Item|PC|Pcs|SUM|Sum|PR|Pr|m2|m3)"
)
# UNIT QTY RATE AMOUNT (priced BOQ rows)
PRICED_TAIL = re.compile(
    rf"(?i)(?<![A-Za-z]){UNIT_TOKEN}\s*"
    rf"([\d,]+(?:\.\d+)?)\s+"
    rf"([\d,]+(?:\.\d+)?)\s+"
    rf"([\d,]+(?:\.\d+)?)"
)
BILL_RE = re.compile(r"(?i)BILL\s*NO\.?\s*(\d+)\s*[-:]?\s*([^\n]{0,90})")
ELEM_RE = re.compile(r"(?i)ELEMENT\s*No\.?\s*(\d+)\s*[-:]?\s*([^\n]{0,90})")
ITEM_START = re.compile(r"^([A-Z])(?:\.|\s+|$)(.*)$")
SKIP_LINE = re.compile(
    r"(?i)^(ITEM\s+DESCRIPTION|COLLECTION|Total brought|Carried to|"
    r"PROPOSED|Page\s|SPECIFICATIONS\b)"
)

# (regex, code, title) - first match wins when scanning a line
BUILDING_RULES = [
    (
        re.compile(r"(?i)TYPE\s*A\s*G\s*\+?\s*9|BLOCK\s*A\b"),
        "BA",
        "Block A (Type A G+9)",
    ),
    (
        re.compile(r"(?i)TYPE\s*B\s*G\s*\+?\s*9|BLOCK\s*B\b"),
        "BB",
        "Block B (Type B G+9)",
    ),
    (re.compile(r"(?i)SOCIAL\s+HALL"), "SH", "Social Hall"),
    (re.compile(r"(?i)CIVIL\s+WORKS"), "CV", "Civil Works"),
    (re.compile(r"(?i)\bMARKET\b"), "MK", "Market"),
    (re.compile(r"(?i)GATE\s*HOUSE"), "GH", "Gate House"),
    (
        re.compile(r"(?i)GENERAL\s+PRELIMINARIES"),
        "GP",
        "General Preliminaries",
    ),
    (re.compile(r"(?i)\bPREAMBLES\b"), "PR", "Preambles"),
]


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
    raise ValueError("emurua_ahp_pdf expects .pdf or .txt, got %s" % suffix)


def _sample_text(path: Path, max_pages: int = 8) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")[:12000]
    if suffix != ".pdf":
        return ""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts = []
    for i, page in enumerate(reader.pages[:max_pages]):
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _split_glued_items(line: str) -> list[str]:
    """Break PDF rows glued after amount columns onto one physical line."""
    s = re.sub(r"\s+", " ", (line or "")).strip()
    if not s:
        return []
    # "...4,302,150.00         -                        B 200mm..."
    s = re.sub(r"\s+-\s+(?=[A-Z]\s+\S)", "\n", s)
    # "...150.00            B 200mm..." (amount then letter item)
    s = re.sub(r"(?<=\d)\s{2,}(?=[A-Z]\s+\S)", "\n", s)
    return [p.strip(" -") for p in s.split("\n") if p.strip(" -")]


def _detect_building(line: str, current_code: str, current_title: str):
    for rx, code, title in BUILDING_RULES:
        if rx.search(line):
            return code, title
    return current_code, current_title


def _pkg_code(building: str, bill: int | None, elem: int | None) -> str:
    b = (building or "GE")[:4]
    return ("%s-B%02d-E%02d" % (b, bill or 0, elem or 0))[:20]


def _pkg_title(building_title: str, bill: int | None, bill_title: str,
               elem: int | None, elem_title: str) -> str:
    parts = [building_title or "Works"]
    if bill:
        bt = (bill_title or "").strip(" -:")
        parts.append("Bill %d%s" % (bill, (" " + bt) if bt else ""))
    if elem:
        et = (elem_title or "").strip(" -:")
        parts.append("El %d%s" % (elem, (" " + et) if et else ""))
    return " / ".join(parts)[:120]


def parse_emurua_text(text: str, source_name: str) -> StandardBoq:
    warnings: list[str] = []
    raw_lines: list[str] = []
    for ln in text.splitlines():
        if ln.startswith("---PAGE"):
            continue
        for part in _split_glued_items(ln):
            raw_lines.append(part)

    building_code = "GE"
    building_title = "General"
    bill = None
    bill_title = ""
    elem = None
    elem_title = ""
    buf: list[str] | None = None
    packages: dict[str, list[StandardBoqLine]] = defaultdict(list)
    package_meta: dict[str, tuple[str, int]] = {}
    seen_refs: dict[str, set[str]] = defaultdict(set)
    sort_counter = 0

    def flush() -> None:
        nonlocal buf, sort_counter
        if not buf:
            return
        raw = " ".join(buf)
        buf = None
        m = re.match(r"^([A-Z])\s*(.*)$", raw)
        if not m:
            return
        letter, rest = m.group(1), m.group(2)
        tm = PRICED_TAIL.search(rest)
        if not tm:
            return
        try:
            qty = parse_qty(tm.group(2))
        except ValueError:
            return
        unit = normalize_unit(tm.group(1))
        desc = clean_description(rest[: tm.start()])
        if len(desc) < 3:
            return
        # Skip obvious collection / narrative noise
        up = desc.upper()
        if up.startswith("TOTAL ") or "CARRIED TO" in up:
            return

        code = _pkg_code(building_code, bill, elem)
        title = _pkg_title(building_title, bill, bill_title, elem, elem_title)
        if code not in package_meta:
            sort_counter += 10
            package_meta[code] = (title, sort_counter)

        # bill_ref unique within package - include element when present
        if elem:
            bill_ref = ("E%02d-%s" % (elem, letter))[:20]
        elif bill:
            bill_ref = ("B%02d-%s" % (bill, letter))[:20]
        else:
            bill_ref = letter[:20]
        if bill_ref in seen_refs[code]:
            # duplicate letter in same element - make unique
            n = 2
            while ("%s%d" % (bill_ref[:18], n))[:20] in seen_refs[code]:
                n += 1
            bill_ref = ("%s%d" % (bill_ref[:18], n))[:20]
        seen_refs[code].add(bill_ref)

        packages[code].append(
            StandardBoqLine(
                bill_ref=bill_ref,
                description=desc,
                unit=unit,
                quantity=qty,
                sort_order=len(packages[code]) + 1,
                extras={
                    "building": building_code,
                    "bill": bill,
                    "element": elem,
                    "item": letter,
                    "rate": tm.group(3),
                    "amount": tm.group(4),
                },
            )
        )

    for ln in raw_lines:
        building_code, building_title = _detect_building(
            ln, building_code, building_title
        )

        bm = BILL_RE.search(ln)
        if bm and "SCHEDULE" not in ln.upper():
            flush()
            bill = int(bm.group(1))
            bill_title = bm.group(2).strip()[:80]
            # BILL NO.4 -BLOCK A also updates building
            building_code, building_title = _detect_building(
                bill_title, building_code, building_title
            )
            continue

        em = ELEM_RE.search(ln)
        if em:
            flush()
            elem = int(em.group(1))
            elem_title = em.group(2).strip()[:80]
            continue

        if SKIP_LINE.match(ln):
            continue

        if ITEM_START.match(ln):
            flush()
            buf = [ln]
            continue

        if buf:
            if (
                "Carried to" in ln
                or ln.upper().startswith("COLLECTION")
                or BILL_RE.search(ln)
                or ELEM_RE.search(ln)
            ):
                flush()
                # re-process structural headers on next loop - push back by
                # handling inline below is awkward; just flush and drop
                continue
            buf.append(ln)

    flush()

    if not packages:
        warnings.append(
            "No priced SMM BOQ lines found (expected BILL NO. / ELEMENT + unit qty rate amount)."
        )

    categories = []
    for code, (title, order) in sorted(
        package_meta.items(), key=lambda kv: (kv[1][1], kv[0])
    ):
        lines = packages.get(code) or []
        if not lines:
            continue
        categories.append(
            StandardBoqCategory(
                code=code,
                title=title,
                sort_order=order,
                lines=lines,
            )
        )

    return StandardBoq(
        source_name=source_name,
        adapter_id=ADAPTER_ID,
        categories=categories,
        warnings=warnings,
        meta={
            "package_count": len(categories),
            "line_count": sum(len(c.lines) for c in categories),
            "buildings": sorted({c.code.split("-")[0] for c in categories}),
        },
    )


class EmuruaAhpPdfAdapter(BoqAdapter):
    id = ADAPTER_ID
    label = "Emurua Dikirr AHP / Kenya SMM housing priced BOQ PDF"

    def can_handle(self, path: Path, text_sample: str = "") -> float:
        name = path.name.lower()
        score = 0.0
        if "emurua" in name or "dikirr" in name:
            score += 0.5
        if "ahp" in name or "affordable" in name:
            score += 0.15
        if path.suffix.lower() in {".pdf", ".txt"}:
            score += 0.05
        sample = text_sample or ""
        if not sample and path.exists() and path.suffix.lower() == ".pdf":
            try:
                sample = _sample_text(path, max_pages=6)
            except Exception:
                sample = ""
        sl = sample.lower()
        if "emurua" in sl or "dikirr" in sl:
            score += 0.25
        if "affordable housing" in sl:
            score += 0.15
        if "bill no" in sl and "element no" in sl:
            score += 0.2
        if "schedule no" in sl and "western pav" in sl.replace("pavilion", "pav"):
            score -= 0.35
        return max(0.0, min(score, 1.0))

    def parse(self, path: Path) -> StandardBoq:
        text = _extract_text(path)
        return parse_emurua_text(text, source_name=path.name)
