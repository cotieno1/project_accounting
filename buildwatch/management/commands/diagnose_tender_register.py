from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from accounts.models import Organization, UserAccount
from buildwatch.models import BidderRegistration, TenderListing


class Command(BaseCommand):
    help = "Diagnose tender register 500"

    def handle(self, *args, **options):
        User = get_user_model()
        for uname in ["cotieno", "dekow", "myusuf", "temp_admin"]:
            u = User.objects.filter(username=uname).first()
            if not u:
                continue
            try:
                ua = getattr(u, "useraccount", None)
                if ua is None:
                    raise UserAccount.DoesNotExist()
                ua_s = f"id={ua.id} org={ua.organization_id}"
            except Exception as exc:
                ua_s = f"MISSING ({exc.__class__.__name__})"
            self.stdout.write(f"USER {uname} id={u.id} ua={ua_s}")

        o = Organization.objects.filter(name__icontains="Pioneer").first()
        self.stdout.write(f"ORG {getattr(o, 'name', None)} code={getattr(o, 'org_code', None)}")
        listing = TenderListing.objects.filter(pk=1).first()
        self.stdout.write(f"LISTING {listing} boq={bool(listing and listing.boq_document)}")
        if listing and o:
            self.stdout.write(
                f"REGS {BidderRegistration.objects.filter(tender=listing, organisation=o).count()}"
            )
            ua = UserAccount.objects.filter(organization=o).order_by("id").first()
            self.stdout.write(f"PIONEER_UA {ua}")