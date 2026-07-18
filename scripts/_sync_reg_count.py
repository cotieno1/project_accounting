from buildwatch.models import TenderListing, BidderRegistration
listing = TenderListing.objects.get(pk=1)
n = BidderRegistration.objects.filter(tender=listing).count()
listing.registered_bidder_count = n
listing.save(update_fields=["registered_bidder_count"])
print("synced registered_bidder_count", n)
