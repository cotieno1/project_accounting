from accounts.models import Organization
o = Organization.objects.filter(org_code="PIONEER").first()
if not o:
    print("MISSING")
else:
    if not (o.organization_type or "").strip():
        o.organization_type = "CONTRACTOR"
        o.save(update_fields=["organization_type"])
        print("SET", o.organization_type)
    else:
        print("OK", o.organization_type)