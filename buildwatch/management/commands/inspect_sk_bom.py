from django.core.management.base import BaseCommand

from accounts.models import BOMHeader, BOMItem, BOMTransaction, ProjectTask, RFQTransaction
from buildwatch.models import TenderListing


class Command(BaseCommand):
    help = "Inspect SK_004 BOM/RFQ lines for Isiolo BOQ mapping"

    def handle(self, *args, **options):
        listing = TenderListing.objects.filter(pk=1).first()
        if listing:
            self.stdout.write(
                f"LISTING boq_document={bool(listing.boq_document)} "
                f"path={listing.boq_document.name if listing.boq_document else '-'}"
            )

        for t in ProjectTask.objects.filter(project_id__icontains="SK"):
            self.stdout.write(f"TASK {t.project_id} | {t.description}")
            for h in BOMHeader.objects.filter(task=t):
                items = list(h.items.all()[:80])
                self.stdout.write(f"  BOMHeader {h.bom_id} items={len(items)}")
                for it in items:
                    self.stdout.write(
                        f"    BOMItem pillar={it.pillar_id} qty={it.qty} uom={it.uom} | {it.description}"
                    )

            txs = list(BOMTransaction.objects.filter(project_task=t).select_related("product")[:80])
            self.stdout.write(f"  BOMTransaction count={len(txs)}")
            for tx in txs:
                prod = tx.product
                desc = getattr(prod, "description", "") if prod else ""
                unit = getattr(prod, "unit_of_measure", None) or getattr(prod, "uom", None) or getattr(prod, "unit", "") or ""
                self.stdout.write(
                    f"    TX qty={tx.quantity_required} unit={unit} | {desc}"
                )

            rfqs = list(RFQTransaction.objects.filter(project_task=t)[:20])
            self.stdout.write(f"  RFQ count={len(rfqs)}")
