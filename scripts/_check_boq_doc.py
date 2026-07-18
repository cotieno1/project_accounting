from buildwatch.models import TenderListing
l = TenderListing.objects.filter(pk=1).first()
if not l:
    l = TenderListing.objects.filter(event__ref="SK/004/2025-2026").first()
print("listing", getattr(l, "pk", None))
print("boq", bool(l and l.boq_document), (l.boq_document.name if l and l.boq_document else None))
print("spec", bool(l and l.specification), (l.specification.name if l and l.specification else None))
print("draw", bool(l and l.drawings), (l.drawings.name if l and l.drawings else None))
print("published", getattr(l, "is_published", None))
print("created_by", getattr(l, "created_by_id", None))
