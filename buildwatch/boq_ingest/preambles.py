"""Extract BOQ "Preambles" - the trade-by-trade measurement, materials and
workmanship rules that govern how the priced BOQ items must be priced.

Kenya SMM building BOQs publish these as "BILL NO. 1: PREAMBLES", grouped by
trade (Excavation, Concrete, Walling, ...). We capture each trade as a
:class:`PreambleSection` so the tender can present navigable rules and the
contractor/sponsor work from the same conditions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# ?? Trade section headings (delimiters). First match wins per line. ???????????
TRADE_SECTIONS = [
    (re.compile(r"(?i)EXCAVATION\s+AND\s+EARTHWORK"), "EXCAVATION", "Excavation and Earthwork"),
    (re.compile(r"(?i)CONCRETE\s+WORK"), "CONCRETE", "Concrete Work"),
    (re.compile(r"(?i)^WALLING\b"), "WALLING", "Walling"),
    (re.compile(r"(?i)ROOFING"), "ROOFING", "Roofing & Asphalt Works"),
    (re.compile(r"(?i)CARPENTRY"), "CARPENTRY", "Carpentry & Joinery"),
    (re.compile(r"(?i)STRUCTURAL\s+STEELWORK"), "STEELWORK", "Structural Steelwork"),
    (re.compile(r"(?i)^METALWORK\b"), "METALWORK", "Metalwork"),
    (re.compile(r"(?i)PLUMBING"), "PLUMBING", "Plumbing & Engineering Installation"),
    (re.compile(r"(?i)FLOOR\s+WALL\s+AND\s+CEILING\s+FINISH"), "FINISHINGS", "Floor, Wall & Ceiling Finishings"),
    (re.compile(r"(?i)^GLAZING\b"), "GLAZING", "Glazing"),
    (re.compile(r"(?i)^PAINTING\b"), "PAINTING", "Painting & Decorating"),
    (re.compile(r"(?i)^DRAINAGE\b"), "DRAINAGE", "Drainage"),
    (re.compile(r"(?i)EXTERNAL\s+PAVING"), "PAVINGS", "External Pavings"),
    (re.compile(r"(?i)GENERAL\s+SPECIFICATION"), "GENERAL", "General Specifications"),
]

_START_RE = re.compile(r"(?i)EXCAVATION\s+AND\s+EARTHWORK")
_END_RE = re.compile(r"(?i)PARTICULAR\s+PRELIMINARIES|^\s*BILL\s*NO\.?\s*2\b")
_PAGE_MARK = re.compile(r"^---PAGE\s+(\d+)---\s*$")
_BILL_HDR_RE = re.compile(r"(?i)^\s*BILL\s*NO\.?\s*\d+\b.*$")
_NOISE_RE = re.compile(
    r"(?i)^(ITEM\s+DESCRIPTION|COLLECTION|Total\s+brought|"
    r"Carried\s+(to|forward)|Page\s+\d)"
)
# Clause markers like "A The...", "B. The...", "J) ..."
_CLAUSE_RE = re.compile(r"^[A-Z][.\)]?\s+\S")


@dataclass
class PreambleSection:
    trade_code: str
    title: str
    body: str
    source_page: int | None = None


def _extract_text_with_pages(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix != ".pdf":
        raise ValueError("preambles extraction expects .pdf or .txt, got %s" % suffix)
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts = []
    for i, page in enumerate(reader.pages):
        parts.append("---PAGE %d---\n%s" % (i + 1, page.extract_text() or ""))
    return "\n".join(parts)


def _is_footer(s: str) -> bool:
    """Page-reference footer such as '2/3', 'S/1', '-1/2-', '1/12'."""
    s = s.strip()
    if not s or "/" not in s:
        return False
    return len(s) <= 8 and re.fullmatch(r"[-\u2013\sSs0-9/]+", s) is not None


def _looks_subheading(s: str) -> bool:
    if len(s) > 45:
        return False
    words = s.split()
    if not words:
        return False
    caps = sum(1 for w in words if w[:1].isupper())
    return caps >= max(1, len(words) - 1) and not s.endswith(".")


def _reflow(lines: list[str]) -> str:
    """Join PDF-wrapped lines back into one line per clause / sub-heading."""
    blocks: list[str] = []
    cur = ""
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        if _CLAUSE_RE.match(s) or _looks_subheading(s):
            if cur:
                blocks.append(cur.strip())
            cur = s
        else:
            cur = (cur + " " + s).strip() if cur else s
    if cur:
        blocks.append(cur.strip())
    return "\n".join(blocks)


def parse_preamble_text(text: str) -> list[PreambleSection]:
    sections: list[PreambleSection] = []
    current: dict | None = None
    started = False
    current_page: int | None = None

    def flush() -> None:
        nonlocal current
        if current and current["lines"]:
            body = _reflow(current["lines"])
            if body.strip():
                sections.append(
                    PreambleSection(
                        trade_code=current["code"],
                        title=current["title"],
                        body=body,
                        source_page=current["page"],
                    )
                )
        current = None

    for raw in text.splitlines():
        pm = _PAGE_MARK.match(raw.strip())
        if pm:
            current_page = int(pm.group(1))
            continue
        stripped = raw.strip()
        if not started:
            if _START_RE.search(stripped):
                started = True
            else:
                continue
        if _END_RE.search(stripped):
            break
        if _is_footer(stripped) or _BILL_HDR_RE.match(stripped) or _NOISE_RE.match(stripped):
            continue

        # A real trade heading is a short, standalone ALL-CAPS line - never a
        # clause sentence that merely mentions the trade.
        heading = None
        if len(stripped) <= 60 and not any(c.islower() for c in stripped):
            for rx, code, title in TRADE_SECTIONS:
                if rx.search(stripped):
                    heading = (code, title)
                    break
        if heading:
            flush()
            current = {
                "code": heading[0],
                "title": heading[1],
                "page": current_page,
                "lines": [],
            }
            continue

        if current is not None and stripped:
            current["lines"].append(stripped)

    flush()

    # De-duplicate trade_code (keep first, longest body wins on collision).
    best: dict[str, PreambleSection] = {}
    order: list[str] = []
    for sec in sections:
        if sec.trade_code not in best:
            best[sec.trade_code] = sec
            order.append(sec.trade_code)
        elif len(sec.body) > len(best[sec.trade_code].body):
            best[sec.trade_code] = sec
    return [best[c] for c in order]


def extract_boq_preambles(path: str | Path) -> list[PreambleSection]:
    """Parse the BOQ PDF/TXT and return ordered trade preamble sections."""
    path = Path(path)
    text = _extract_text_with_pages(path)
    return parse_preamble_text(text)
