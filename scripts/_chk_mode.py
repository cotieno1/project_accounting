from buildwatch.models import TenderListing
l = TenderListing.objects.get(pk=1)
print("mode", getattr(l, "boq_input_mode", "MISSING"))
print("pkgs", l.boq_packages.count())
print("lines", sum(p.lines.count() for p in l.boq_packages.all()))
