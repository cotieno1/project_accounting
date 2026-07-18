from accounts.models import Organization, UserAccount
from django.contrib.auth import get_user_model
User=get_user_model()
uas=list(UserAccount.objects.filter(email__iexact="otieno.charles@gmail.com").values("id","username","email","organization_id","must_change_password","user_id","staff_no"))
print("ua", uas)
for u in User.objects.filter(email__iexact="otieno.charles@gmail.com"):
    print("auth", u.username, u.is_superuser, u.is_staff)
print("default cats", list(__import__("accounts.models",fromlist=["UserCategory"]).UserCategory.objects.values_list("code","id")[:8]))
