from django.template.loader import render_to_string
from buildwatch.models import TenderListing, BidWorkspace, TenderBoqPackage, SubcontractArrangement
from buildwatch.views_tenders import (
    _active_subcontracted_codes, _active_subcontracts,
    _pending_subcontract_quotes, _can_print_draft_for_approval,
)

listing = TenderListing.objects.get(pk=1)
ws = BidWorkspace.objects.filter(tender=listing, organisation_id="PIONEER").first()
org = ws.organisation
packages = list(TenderBoqPackage.objects.filter(tender=listing).prefetch_related("lines").order_by("sort_order", "code"))
subcontracted = sorted(_active_subcontracted_codes(listing, org))
main_packages = [p for p in packages if p.code.upper() not in set(subcontracted)]
html = render_to_string(
    "tenders/bid_workspace.html",
    {
        "listing": listing,
        "workspace": ws,
        "packages": packages,
        "main_packages": main_packages,
        "subcontracted_codes": subcontracted,
        "selected_codes": ws.selected_codes(),
        "boq_input_mode": listing.boq_input_mode,
        "boq_mode_choices": [],
        "can_switch_boq_mode": False,
        "package_sections": [],
        "category_summary": [],
        "category_grand_total": 0,
        "bill_prices": ws.bill_prices.none(),
        "self_checks": ws.self_checks.none(),
        "subcontract_count": 0,
        "subcontract_arrangements": [],
        "pending_sub_quotes": _pending_subcontract_quotes(listing, org),
        "can_print_draft_bid": _can_print_draft_for_approval(listing, org),
        "request": type("R", (), {"user": type("U", (), {"is_authenticated": True})()})(),
    },
)
print("bytes", len(html))
for needle in [
    "Apply Sub Contracting",
    "Step 1",
    "Step 2",
    ">Apply</button>",
    "Print draft bid for approval",
    "BOQ Workspace",
    "Apply selection",
]:
    print(needle, needle in html)
# public registered count logic
from buildwatch.models import BidderRegistration
print("db_regs", BidderRegistration.objects.filter(tender=listing).count())
print("published", listing.is_published, "open", listing.event.is_open)
idx = html.find("Apply Sub Contracting")
print("snippet", html[max(0, idx-120):idx+80].replace("\n", " ") if idx>=0 else "MISSING")
