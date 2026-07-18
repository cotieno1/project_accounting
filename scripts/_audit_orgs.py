import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "UN_accounting_system.settings")
django.setup()

from django.contrib.auth.models import User
from accounts.models import Organization, UserAccount, ProjectTask, MiscPurchaseOrder, BOMHeader

print("=== ORGANIZATIONS ===")
for o in Organization.objects.all().order_by("org_code"):
    users = UserAccount.objects.filter(organization=o)
    unames = []
    for ua in users:
        unames.append(ua.user.username if ua.user else ua.staff_no)
    print(f"  code={o.org_code!r} name={o.name!r} short={o.short_name!r} default={o.is_default}")
    print(f"    linked users: {unames}")

print()
print("=== ALL USER ACCOUNTS ===")
for ua in UserAccount.objects.select_related("user", "organization").all():
    u = ua.user
    uname = u.username if u else "?"
    superuser = u.is_superuser if u else False
    print(f"  {uname} staff={ua.staff_no} org={ua.organization_id!r} super={superuser}")

print()
print("=== DATA (global, not org-scoped) ===")
print(f"  tasks: {ProjectTask.objects.count()}")
print(f"  mpos: {MiscPurchaseOrder.objects.count()}")
print(f"  boms: {BOMHeader.objects.count()}")
