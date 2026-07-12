from decimal import Decimal
from pathlib import Path
import json

from django.core.management.base import BaseCommand

from buildwatch.models import (
    BidWorkspace,
    TenderBoqLine,
    TenderBoqPackage,
    TenderListing,
    WorkspaceBillPrice,
)

_CANDIDATES = [
    Path(__file__).resolve().parent / "isiolo_boq_lines.json",
    Path(__file__).resolve().parents[3] / "scripts" / "isiolo_boq_lines.json",
]


class Command(BaseCommand):
    help = "Seed Isiolo BOQ packages from RFQ/tender measured quantities"

    def handle(self, *args, **options):
        data_path = next((p for p in _CANDIDATES if p.exists()), None)
        if not data_path:
            self.stderr.write("isiolo_boq_lines.json not found - run scripts/parse_isiolo_boq.py")
            return

        payload = json.loads(data_path.read_text(encoding="utf-8"))
        listing = TenderListing.objects.filter(
            event__ref="SK/004/2025-2026"
        ).first() or TenderListing.objects.filter(pk=1).first()
        if not listing:
            self.stderr.write("Isiolo tender listing not found")
            return

        keep_codes = set()
        ref_to_pkg = {}
        for pkg_data in payload["packages"]:
            code = pkg_data["code"]
            keep_codes.add(code)
            pkg, _ = TenderBoqPackage.objects.update_or_create(
                tender=listing,
                code=code,
                defaults={
                    "title": pkg_data["title"],
                    "sort_order": pkg_data["sort_order"],
                },
            )
            keep_refs = set()
            for line in pkg_data["lines"]:
                ref = (line["bill_ref"] or "")[:20]
                keep_refs.add(ref)
                ref_to_pkg[ref] = code
                TenderBoqLine.objects.update_or_create(
                    package=pkg,
                    bill_ref=ref,
                    defaults={
                        "description": (line.get("description") or "")[:255],
                        "unit": (line.get("unit") or "No")[:30],
                        "quantity": Decimal(str(line["quantity"])),
                        "sort_order": line["sort_order"],
                    },
                )
            deleted, _ = pkg.lines.exclude(bill_ref__in=keep_refs).delete()
            self.stdout.write(self.style.SUCCESS(
                f"  {code}: {pkg.lines.count()} lines (removed {deleted} stale) - {pkg.title}"
            ))

        TenderBoqPackage.objects.filter(tender=listing).exclude(
            code__in=keep_codes
        ).delete()

        synced = 0
        dropped = 0
        for bp in WorkspaceBillPrice.objects.filter(workspace__tender=listing):
            code = ref_to_pkg.get(bp.bill_ref)
            if not code:
                bp.delete()
                dropped += 1
                continue
            ln = TenderBoqLine.objects.filter(
                package__tender=listing, bill_ref=bp.bill_ref
            ).first()
            changed = False
            if bp.package_code != code:
                bp.package_code = code
                changed = True
            if ln and (bp.quantity != ln.quantity or bp.unit != ln.unit):
                bp.quantity = ln.quantity
                bp.unit = ln.unit
                changed = True
            if changed:
                bp.save()
                synced += 1

        for ws in BidWorkspace.objects.filter(tender=listing):
            codes = [c for c in (ws.selected_package_codes or []) if c in keep_codes]
            if codes != (ws.selected_package_codes or []):
                ws.selected_package_codes = codes
                ws.pricing_complete = False
                ws.save(update_fields=["selected_package_codes", "pricing_complete"])

        self.stdout.write(self.style.SUCCESS(
            f"Isiolo BOQ seeded from {data_path.name} "
            f"listing_id={listing.pk} categories={len(keep_codes)} "
            f"synced_prices={synced} dropped_prices={dropped}"
        ))
