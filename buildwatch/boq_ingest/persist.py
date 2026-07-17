"""Apply StandardBoq onto TenderBoqPackage/Line (explicit opt-in only)."""
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
            page = getattr(line, "source_page", None)
            if page is None and isinstance(getattr(line, "extras", None), dict):
                page = line.extras.get("page") or line.extras.get("source_page")
            try:
                page = int(page) if page is not None else None
            except (TypeError, ValueError):
                page = None
            if page is not None and page < 1:
                page = None
            TenderBoqLine.objects.update_or_create(
                package=pkg,
                bill_ref=ref,
                defaults={
                    "description": (line.description or "")[:255],
                    "unit": (line.unit or "No")[:30],
                    "quantity": Decimal(str(line.quantity)),
                    "sort_order": line.sort_order,
                    "source_page": page,
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
