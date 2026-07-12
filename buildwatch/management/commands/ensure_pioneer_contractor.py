from django.core.management.base import BaseCommand

from accounts.models import Organization
from buildwatch.models import MandatoryRequirement, SelfAssessmentCheck, TenderListing


class Command(BaseCommand):
    help = "Ensure Pioneer is CONTRACTOR and report MR/upload state"

    def handle(self, *args, **options):
        o = (
            Organization.objects.filter(name__icontains="Pioneer").first()
            or Organization.objects.filter(org_code__icontains="PIO").first()
            or Organization.get_default()
        )
        if not o:
            self.stderr.write("No organisation found")
            return
        changed = []
        if (o.organization_type or "").upper() != "CONTRACTOR":
            o.organization_type = "CONTRACTOR"
            changed.append("organization_type")
        if "Pioneer" in (o.name or "") and o.name != "Pioneer Contracting Limited":
            o.name = "Pioneer Contracting Limited"
            changed.append("name")
        if changed:
            o.save(update_fields=changed)
            self.stdout.write(self.style.SUCCESS(f"Updated {o.name}: {', '.join(changed)}"))
        else:
            self.stdout.write(f"OK {o.name} type={o.organization_type}")

        mr = MandatoryRequirement.objects.filter(
            context__in=["PROCUREMENT", "ALL"], is_active=True
        ).count()
        listing = TenderListing.objects.filter(pk=1).select_related("event").first()
        docs = SelfAssessmentCheck.objects.filter(document_uploaded=True).count()
        self.stdout.write(f"MR_PROC={mr} SELF_DOCS={docs}")
        if listing:
            self.stdout.write(
                f"LISTING id={listing.pk} pub={listing.is_published} "
                f"status={listing.event.status} close={listing.event.closing_date}"
            )