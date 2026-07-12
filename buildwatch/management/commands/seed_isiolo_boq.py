from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand

from buildwatch.models import TenderBoqLine, TenderBoqPackage, TenderListing, WorkspaceBillPrice

# Prefer packaged JSON next to this command, else scripts/
_CANDIDATES = [
    Path(__file__).resolve().parents[3] / "scripts" / "isiolo_boq_lines.json",
    Path(__file__).resolve().parent / "isiolo_boq_lines.json",
]


class Command(BaseCommand):
    help = "Seed Isiolo BOQ packages from RFQ/tender measured quantities"

    def handle(self, *args, **options):
        data_path = next((p for p in _CANDIDATES if p.exists()), None)
        if not data_path:
            self.stderr.write("isiolo_boq_lines.json not found — run scripts/parse_isiolo_boq.py")
            return

        import json

        payload = json.loads(data_path.read_text(encoding="utf-8"))
        listing = TenderListing.objects.filter(
            event__ref="SK/004/2025-2026"
        ).first() or TenderListing.objects.filter(pk=1).first()
        if not listing:
            self.stderr.write("Isiolo tender listing not found")
            return

        keep_codes = set()
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
                ref = line["bill_ref"]
                keep_refs.add(ref)
                TenderBoqLine.objects.update_or_create(
                    package=pkg,
                    bill_ref=ref,
                    defaults={
                        "description": line["description"],
                        "unit": line["unit"],
                        "quantity": Decimal(str(line["quantity"])),
                        "sort_order": line["sort_order"],
                    },
                )
            deleted, _ = pkg.lines.exclude(bill_ref__in=keep_refs).delete()
            self.stdout.write(self.style.SUCCESS(
                f"  {code}: {pkg.lines.count()} lines (removed {deleted} stale)"
            ))

        # Drop packages not in the RFQ set
        TenderBoqPackage.objects.filter(tender=listing).exclude(code__in=keep_codes).delete()

        # Align saved contractor prices to master qty/unit where refs still exist
        master = {
            ln.bill_ref: ln
            for ln in TenderBoqLine.objects.filter(package__tender=listing)
        }
        synced = 0
        for bp in WorkspaceBillPrice.objects.filter(workspace__tender=listing):
            ln = master.get(bp.bill_ref)
            if not ln:
                continue
            if bp.quantity != ln.quantity or bp.unit != ln.unit:
                bp.quantity = ln.quantity
                bp.unit = ln.unit
                bp.save()
                synced += 1

        self.stdout.write(self.style.SUCCESS(
            f"Isiolo BOQ seeded from {data_path.name} "
            f"listing_id={listing.pk} synced_prices={synced}"
        ))
