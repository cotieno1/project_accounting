from buildwatch.models import BidWorkspace, SubcontractArrangement, TenderListing
listing = TenderListing.objects.get(pk=1)
ws = BidWorkspace.objects.filter(tender=listing, organisation_id="PIONEER").first()
active = list(SubcontractArrangement.objects.filter(tender=listing, main_organisation_id="PIONEER").exclude(status="CANCELLED").values_list("sub_company_name","status","quote_status","package_codes"))
print("open", listing.event.is_open)
print("ws", ws.status if ws else None, "planned_n", getattr(ws, "planned_subcontractor_count", None) if ws else None, "selected", ws.selected_codes() if ws else None)
print("active_subs", active)
from django.db import connection
with connection.cursor() as c:
    c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='buildwatch_bidworkspace' AND column_name='planned_subcontractor_count'")
    print("planned_col", c.fetchall())
