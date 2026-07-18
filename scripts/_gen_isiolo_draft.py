from pathlib import Path
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from buildwatch.models import TenderListing, BidWorkspace, BidderRegistration
from buildwatch.views_tenders import _bid_pack_context
from accounts.misc_doc_pdf import build_pdf_bytes
from accounts.models import Organization

listing = TenderListing.objects.filter(pk=1).first() or TenderListing.objects.filter(event__ref="SK/004/2025-2026").first()
if not listing:
    raise SystemExit("Isiolo listing not found")

org = (
    Organization.objects.filter(name__icontains="Pioneer").first()
    or Organization.objects.filter(short_name__icontains="Pioneer").first()
)
if not org:
    raise SystemExit("Pioneer org not found: " + str(list(Organization.objects.values_list("id", "short_name")[:20])))

ws = BidWorkspace.objects.filter(tender=listing, organisation=org).first()
if not ws:
    raise SystemExit("No BidWorkspace for Pioneer on listing %s" % listing.pk)

User = get_user_model()
user = User.objects.filter(is_staff=True).first() or User.objects.first()
rf = RequestFactory()
request = rf.get("/tenders/%s/bid/draft.pdf/" % listing.pk)
request.user = user

# Minimal session/org stubs if branding needs them
if not hasattr(request, "session"):
    request.session = {}

ctx = _bid_pack_context(request, listing, ws, org, getattr(ws, "prepared_by", None))
pdf = build_pdf_bytes("tenders/bid_draft_print.html", ctx)

out = Path("/tmp") / ("Bid_Isiolo_Pioneer_%s.pdf" % ("DRAFT" if ctx["is_draft"] else "SUBMITTED"))
out.write_bytes(pdf)
print("OK")
print("listing", listing.pk, listing.event.ref)
print("org", org.pk, org.short_name)
print("workspace", ws.pk, ws.status)
print("selected", ws.selected_codes())
print("pricing_complete", ws.pricing_complete)
print("self_assessment_passed", ws.self_assessment_passed)
print("checks", ws.self_checks.count())
print("bill_prices", ws.bill_prices.count())
print("grand_total", ctx["grand_total"])
print("sections", len(ctx["package_sections"]))
print("pdf_bytes", len(pdf))
print("out", out)
