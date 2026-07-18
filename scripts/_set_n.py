from buildwatch.models import BidWorkspace, SubcontractArrangement
ws = BidWorkspace.objects.filter(tender_id=1, organisation_id="PIONEER").first()
if not ws:
    print("no workspace"); raise SystemExit
active = SubcontractArrangement.objects.filter(tender_id=1, main_organisation_id="PIONEER").exclude(status="CANCELLED").count()
print("before", ws.planned_subcontractor_count, "active", active)
if ws.planned_subcontractor_count is None:
    # default Isiolo known case: 1 if any already, else leave unset for Set N UI
    if active > 0:
        ws.planned_subcontractor_count = active
        ws.save(update_fields=["planned_subcontractor_count"])
print("after", ws.planned_subcontractor_count, "companies", list(SubcontractArrangement.objects.filter(tender_id=1, main_organisation_id="PIONEER").exclude(status="CANCELLED").values_list("sub_company_name", flat=True)))
