from buildwatch.models import SubcontractArrangement
from accounts.models import Organization, UserAccount
for a in SubcontractArrangement.objects.filter(tender_id=1).exclude(status="CANCELLED"):
    print("pk", a.pk, "company", a.sub_company_name, "email", a.sub_email, "contact", a.sub_contact_name, "sub_org", a.sub_organisation_id, "packages", a.package_codes, "status", a.status, "has_token", bool(a.invite_token))
print("lan orgs", list(Organization.objects.filter(org_code__icontains="LAN").values_list("org_code","name","short_name","organization_type","registration_status")))
print("lan users", list(UserAccount.objects.filter(organization_id__icontains="LAN").values_list("username","email","organization_id","must_change_password")[:10]))
