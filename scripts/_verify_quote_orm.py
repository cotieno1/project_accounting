from buildwatch.models import SubcontractArrangement
print("fields ok", hasattr(SubcontractArrangement, "quote_status"))
print("default", SubcontractArrangement._meta.get_field("quote_status").default)
# ORM touch without writing
qs = SubcontractArrangement.objects.all()[:1]
print("queryset ok", list(qs.values_list("id", "quote_status", "status")))
print("READY")
