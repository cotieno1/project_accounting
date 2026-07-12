from pathlib import Path

from django.core.management.base import BaseCommand
from django.test import RequestFactory
from django.contrib.auth import get_user_model

from accounts.misc_doc_pdf import build_pdf_bytes
from accounts.models import Organization
from buildwatch.models import BidWorkspace, TenderListing
from buildwatch.views_tenders import _bid_pack_context


class Command(BaseCommand):
    help = "Generate Isiolo draft bid PDF for Pioneer (local or Railway)"

    def add_arguments(self, parser):
        parser.add_argument("--out", default="")

    def handle(self, *args, **options):
        listing = TenderListing.objects.filter(pk=1).first() or TenderListing.objects.filter(
            event__ref="SK/004/2025-2026"
        ).first()
        if not listing:
            self.stderr.write("Isiolo listing not found")
            return

        org = (
            Organization.objects.filter(name__icontains="Pioneer").first()
            or Organization.objects.filter(short_name__icontains="Pioneer").first()
        )
        if not org:
            self.stderr.write("Pioneer org not found")
            for o in Organization.objects.all()[:20]:
                self.stdout.write("  org %s %s" % (o.pk, o.short_name))
            return

        ws = BidWorkspace.objects.filter(tender=listing, organisation=org).first()
        if not ws:
            self.stderr.write("No BidWorkspace for Pioneer on listing %s" % listing.pk)
            return

        User = get_user_model()
        user = User.objects.filter(is_staff=True).first() or User.objects.first()
        request = RequestFactory().get("/tenders/%s/bid/draft.pdf/" % listing.pk)
        request.user = user
        request.session = {}

        ctx = _bid_pack_context(request, listing, ws, org, getattr(ws, "prepared_by", None))
        pdf = build_pdf_bytes("tenders/bid_draft_print.html", ctx)

        out = options["out"]
        if out:
            out_path = Path(out)
        else:
            status = "DRAFT" if ctx["is_draft"] else "SUBMITTED"
            out_path = Path("/tmp") / ("Bid_Isiolo_Pioneer_%s.pdf" % status)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(pdf)

        self.stdout.write("OK listing=%s ref=%s" % (listing.pk, listing.event.ref))
        self.stdout.write("org=%s %s" % (org.pk, org.short_name))
        self.stdout.write("workspace=%s status=%s" % (ws.pk, ws.status))
        self.stdout.write("selected=%s" % ws.selected_codes())
        self.stdout.write("pricing_complete=%s self_assess=%s" % (
            ws.pricing_complete, ws.self_assessment_passed))
        self.stdout.write("checks=%s bill_prices=%s" % (
            ws.self_checks.count(), ws.bill_prices.count()))
        self.stdout.write("grand_total=%s sections=%s" % (
            ctx["grand_total"], len(ctx["package_sections"])))
        self.stdout.write("pdf_bytes=%s" % len(pdf))
        self.stdout.write("out=%s" % out_path)
