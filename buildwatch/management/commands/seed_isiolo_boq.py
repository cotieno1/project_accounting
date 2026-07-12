from decimal import Decimal

from django.core.management.base import BaseCommand

from buildwatch.models import TenderBoqLine, TenderBoqPackage, TenderListing, WorkspaceBillPrice

ISIOLO_PACKAGES = [
    ("ELEC", "Electrical Works", 1, [
        ("ELEC-01", "Main LV switchboard and distribution boards"),
        ("ELEC-02", "Power reticulation - cable trays, conduits and wiring"),
        ("ELEC-03", "High-mast floodlighting installation"),
        ("ELEC-04", "Testing, commissioning and as-built documentation"),
    ]),
    ("CABLING", "Structured Cabling", 2, [
        ("CAB-01", "Horizontal and backbone structured cabling"),
        ("CAB-02", "Network cabinets, patch panels and fibre terminations"),
        ("CAB-03", "Testing, labelling and certification"),
    ]),
    ("CCTV", "CCTV Works", 3, [
        ("CCTV-01", "IP cameras, mounts and field cabling"),
        ("CCTV-02", "NVR / recording and monitoring workstation"),
        ("CCTV-03", "Configuration, viewing client and handover"),
    ]),
    ("SOLAR", "Solar Installation Works", 4, [
        ("SOL-01", "Solar PV modules, mounting structure and DC cabling"),
        ("SOL-02", "Inverters, AC interconnection and protection"),
        ("SOL-03", "Commissioning, training and documentation"),
    ]),
]


class Command(BaseCommand):
    help = "Seed Isiolo BOQ packages (Electrical, Cabling, CCTV, Solar)"

    def handle(self, *args, **options):
        listing = TenderListing.objects.filter(
            event__ref="SK/004/2025-2026"
        ).first() or TenderListing.objects.filter(pk=1).first()
        if not listing:
            self.stderr.write("Isiolo tender listing not found")
            return

        for code, title, order, lines in ISIOLO_PACKAGES:
            pkg, created = TenderBoqPackage.objects.get_or_create(
                tender=listing,
                code=code,
                defaults={"title": title, "sort_order": order},
            )
            if not created:
                pkg.title = title
                pkg.sort_order = order
                pkg.save(update_fields=["title", "sort_order"])
            for i, (ref, desc) in enumerate(lines, 1):
                TenderBoqLine.objects.update_or_create(
                    package=pkg,
                    bill_ref=ref,
                    defaults={
                        "description": desc,
                        "unit": "Unit",
                        "quantity": Decimal("1"),
                        "sort_order": i,
                    },
                )
            self.stdout.write(self.style.SUCCESS(
                f"  {code}: {pkg.lines.count()} lines (qty=1 Unit)"
            ))

        # Normalize any already-saved contractor prices to qty 1 Unit
        updated = WorkspaceBillPrice.objects.filter(
            workspace__tender=listing
        ).exclude(quantity=Decimal("1"), unit="Unit").update(
            quantity=Decimal("1"),
            unit="Unit",
        )
        # Recalc amounts
        for bp in WorkspaceBillPrice.objects.filter(workspace__tender=listing):
            bp.save()

        self.stdout.write(self.style.SUCCESS(
            f"Isiolo BOQ packages ready for listing id={listing.pk} (normalized {updated} priced rows)"
        ))
