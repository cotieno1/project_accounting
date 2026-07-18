from buildwatch.models import TenderListing, BidderRegistration, BidWorkspace
from accounts.models import Organization

listing = TenderListing.objects.filter(pk=1).first()
print("listing", listing.pk if listing else None, getattr(getattr(listing, "event", None), "ref", None), "open", getattr(getattr(listing, "event", None), "is_open", None))

orgs = list(Organization.objects.filter(name__icontains="Pioneer") | Organization.objects.filter(short_name__icontains="Pioneer"))
print("pioneer orgs:", [(o.pk, o.short_name, o.name, getattr(o, "organization_type", None), getattr(o, "org_type", None)) for o in orgs])

print("regs tender1:", list(BidderRegistration.objects.filter(tender_id=1).values_list("organisation_id", "organisation__short_name", "organisation__name")))
print("workspaces tender1:", list(BidWorkspace.objects.filter(tender_id=1).values_list("organisation_id", "organisation__short_name", "status", "selected_package_codes")))
print("all regs count", BidderRegistration.objects.filter(tender_id=1).count())
