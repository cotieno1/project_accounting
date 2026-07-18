"""Resolve hardwired vs PDF-auto StandardBoq sources for a listing."""
from __future__ import annotations

import json
import tempfile
from decimal import Decimal
from pathlib import Path

from .adapters.isiolo_domestic_pdf import parse_isiolo_text
from .registry import detect_adapter
from .schema import StandardBoq, StandardBoqCategory, StandardBoqLine

HARDWIRED_JSON_CANDIDATES = [
    Path(__file__).resolve().parent.parent
    / "management"
    / "commands"
    / "isiolo_boq_lines.json",
    Path(__file__).resolve().parents[2] / "scripts" / "isiolo_boq_lines.json",
]

PDF_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "isiolo_tender_extract.txt"


def _standard_from_seed_json(payload: dict, source_name: str) -> StandardBoq:
    categories = []
    for pkg in payload.get("packages", []):
        lines = []
        for i, row in enumerate(pkg.get("lines", []), 1):
            lines.append(
                StandardBoqLine(
                    bill_ref=row["bill_ref"],
                    description=row.get("description") or "",
                    unit=row.get("unit") or "No",
                    quantity=Decimal(str(row["quantity"])),
                    sort_order=row.get("sort_order") or i,
                )
            )
        categories.append(
            StandardBoqCategory(
                code=pkg["code"],
                title=pkg["title"],
                sort_order=pkg.get("sort_order") or 0,
                lines=lines,
            )
        )
    return StandardBoq(
        source_name=source_name,
        adapter_id="hardwired_json",
        categories=categories,
        meta={"source": "hardwired"},
    )


def load_hardwired_boq() -> StandardBoq:
    path = next((p for p in HARDWIRED_JSON_CANDIDATES if p.exists()), None)
    if not path:
        raise FileNotFoundError("isiolo_boq_lines.json not found for hardwired mode")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _standard_from_seed_json(payload, source_name=path.name)


def _reject_empty(doc: StandardBoq) -> StandardBoq:
    if doc.line_count <= 0:
        warn = "; ".join(doc.warnings) if doc.warnings else "no priced lines matched"
        raise ValueError(
            "PDF BOQ parse produced 0 lines via adapter %r (%s)."
            % (doc.adapter_id, warn)
        )
    return doc


def load_pdf_auto_boq(listing) -> StandardBoq:
    """
    Prefer listing.boq_document PDF with auto-detected adapter;
    else fall back to the shipped Isiolo text fixture (legacy demos only).
    """
    if listing.boq_document:
        name = Path(listing.boq_document.name).name
        suffix = Path(name).suffix.lower() or ".pdf"
        with listing.boq_document.open("rb") as fh:
            data = fh.read()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            adapter, score = detect_adapter(tmp_path)
            doc = adapter.parse(tmp_path)
            doc.meta["source"] = "listing.boq_document"
            doc.meta["document_name"] = name
            doc.meta["detect_score"] = score
            doc.meta["adapter_id"] = adapter.id
            return _reject_empty(doc)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    # Only safe for Isiolo-shaped demos — never invent Emurua lines from this.
    listing_name = (
        (getattr(getattr(listing, "event", None), "ref", None) or "")
        + " "
        + (getattr(listing, "summary", None) or "")
    ).lower()
    if any(tok in listing_name for tok in ("emurua", "dikirr", "ed-ahp", "ahp")):
        raise FileNotFoundError(
            "This tender has no boq_document attached; cannot invent an Emurua BOQ."
        )

    if PDF_FIXTURE.exists():
        text = PDF_FIXTURE.read_text(encoding="utf-8", errors="replace")
        doc = parse_isiolo_text(text, source_name=PDF_FIXTURE.name)
        doc.meta["source"] = "fixture_extract"
        doc.warnings.append(
            "No boq_document on listing - used shipped Isiolo tender text extract."
        )
        return _reject_empty(doc)

    raise FileNotFoundError(
        "PDF auto mode needs listing.boq_document or the Isiolo fixture extract."
    )
