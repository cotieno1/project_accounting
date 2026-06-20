# Pioneer access control

## Roles (UserCategory.code)

| Code | Title |
|------|-------|
| USER_ADMIN | User Admin (Global) - create/onboard users |
| REGULAR_USER | GRN email, source items, Misc PO approved alerts |
| SENIOR_SITE_MANAGER | BOM, RO, LPO/GRN confirm |
| GENERAL_MANAGER | Payments, bid eval, signatory copies |
| CEO | Budget, disbursement, variance alerts, CC all email |

See accounts/roles.py for permissions.

## Onboarding

User Admin creates user -> onboarding email -> /accounts/set-password/ -> login.

Railway: set EMAIL_* and SITE_BASE_URL.

Seed: python manage.py seed_access_roles
