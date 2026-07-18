from buildwatch.models import TenderListing, EvaluationEvent
print("listings", TenderListing.objects.count())
for l in TenderListing.objects.select_related("event","country").all():
    print("id", l.pk, "pub", l.is_published, "vis", l.visibility, "ref", getattr(l.event,"ref",None), "status", getattr(l.event,"status",None), "close", getattr(l.event,"closing_date",None))
print("events", EvaluationEvent.objects.count())
for e in EvaluationEvent.objects.all()[:10]:
    print("event", e.pk, e.ref, e.status, e.closing_date)