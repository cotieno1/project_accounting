from django.core.management.base import BaseCommand

from accounts.models import BOMHeader, BOMItem, BOMTransaction, ProjectTask, RFQTransaction
from buildwatch.models import TenderListing


class Command(BaseCommand):
    help = 'Inspect SK_004 BOM/RFQ lines for Isiolo BOQ mapping'

    def handle(self, *args, **options):
        listing = TenderListing.objects.filter(pk=1).first()
        if listing:
            self.stdout.write(
                f'LISTING boq_document={bool(listing.boq_document)} '
                f'path={listing.boq_document.name if listing.boq_document else "-"}'
            )

        for t in ProjectTask.objects.filter(project_id__icontains='SK'):
            self.stdout.write(f'TASK {t.project_id} | {t.description}')
            for h in BOMHeader.objects.filter(task=t):
                self.stdout.write(f'  BOMHeader pk={h.pk}')
                items = BOMItem.objects.filter(header=h)[:50] if hasattr(BOMItem, 'header') else []
                if not items:
                    try:
                        items = h.items.all()[:50]
                    except Exception:
                        items = BOMTransaction.objects.filter(project_task=t)[:50]
                for it in items:
                    self.stdout.write(f'    {it}')

            txs = BOMTransaction.objects.filter(project_task=t)[:40]
            self.stdout.write(f'  BOMTransaction count shown={txs.count()}')
            for tx in txs:
                prod = getattr(tx, 'product', None)
                desc = getattr(prod, 'description', None) or getattr(tx, 'description', '') or ''
                qty = getattr(tx, 'quantity_required', None)
                unit = getattr(prod, 'unit', None) or getattr(tx, 'unit', '') or ''
                self.stdout.write(f'    TX {tx.pk} qty={qty} unit={unit} | {desc[:80]}')

            try:
                rfqs = RFQTransaction.objects.filter(project_task=t)[:20]
            except Exception:
                rfqs = RFQTransaction.objects.none()
            self.stdout.write(f'  RFQ count={rfqs.count()}')
            for r in rfqs:
                self.stdout.write(f'    RFQ {r}')
