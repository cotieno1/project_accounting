from pathlib import Path

def w(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text.replace("\r\n", "\n"), encoding="utf-8")
    print("wrote", path)

w("buildwatch/boq_ingest/persist.py", r'''"""Apply StandardBoq onto TenderBoqPackage/Line (explicit opt-in only)."""
from __future__ import annotations

from decimal import Decimal

from buildwatch.models import TenderBoqLine, TenderBoqPackage, TenderListing


def apply_standard_boq(listing: TenderListing, doc) -> dict:
    """
    Replace BOQ packages/lines for a listing with a StandardBoq document.
    Does not change bid workspace UI — only the data behind the same form.
    """
    keep_codes = set()
    ref_to_pkg = {}
    for cat in doc.categories:
        keep_codes.add(cat.code)
        pkg, _ = TenderBoqPackage.objects.update_or_create(
            tender=listing,
            code=cat.code,
            defaults={
                "title": cat.title[:120],
                "sort_order": cat.sort_order,
            },
        )
        keep_refs = set()
        for line in cat.lines:
            ref = (line.bill_ref or "")[:20]
            keep_refs.add(ref)
            ref_to_pkg[ref] = cat.code
            TenderBoqLine.objects.update_or_create(
                package=pkg,
                bill_ref=ref,
                defaults={
                    "description": (line.description or "")[:255],
                    "unit": (line.unit or "No")[:30],
                    "quantity": Decimal(str(line.quantity)),
                    "sort_order": line.sort_order,
                },
            )
        pkg.lines.exclude(bill_ref__in=keep_refs).delete()

    TenderBoqPackage.objects.filter(tender=listing).exclude(
        code__in=keep_codes
    ).delete()

    return {
        "categories": len(keep_codes),
        "lines": sum(len(c.lines) for c in doc.categories),
        "adapter_id": getattr(doc, "adapter_id", ""),
        "ref_to_pkg": ref_to_pkg,
    }
''')

w("buildwatch/boq_ingest/sources.py", r'''"""Resolve hardwired vs PDF-auto StandardBoq sources for a listing."""
from __future__ import annotations

import json
import tempfile
from decimal import Decimal
from pathlib import Path

from .adapters.isiolo_domestic_pdf import (
    IsioloDomesticPdfAdapter,
    parse_isiolo_text,
)
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


def load_pdf_auto_boq(listing) -> StandardBoq:
    """
    Prefer listing.boq_document PDF; else Isiolo text fixture shipped with the app.
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
            adapter = IsioloDomesticPdfAdapter()
            doc = adapter.parse(tmp_path)
            doc.meta["source"] = "listing.boq_document"
            doc.meta["document_name"] = name
            return doc
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    if PDF_FIXTURE.exists():
        text = PDF_FIXTURE.read_text(encoding="utf-8", errors="replace")
        doc = parse_isiolo_text(text, source_name=PDF_FIXTURE.name)
        doc.meta["source"] = "fixture_extract"
        doc.warnings.append(
            "No boq_document on listing — used shipped Isiolo tender text extract."
        )
        return doc

    raise FileNotFoundError(
        "PDF auto mode needs listing.boq_document or the Isiolo fixture extract."
    )
''')

print("persist+sources ok")