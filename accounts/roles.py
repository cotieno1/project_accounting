"""Pioneer access categories and permission helpers."""

USER_ADMIN = "USER_ADMIN"
REGULAR_USER = "REGULAR_USER"
SENIOR_SITE_MANAGER = "SENIOR_SITE_MANAGER"
GENERAL_MANAGER = "GENERAL_MANAGER"
CEO = "CEO"

ALL_ROLE_CODES = (USER_ADMIN, REGULAR_USER, SENIOR_SITE_MANAGER, GENERAL_MANAGER, CEO)

ROLE_DEFINITIONS = [
    {"code": USER_ADMIN, "description": "User Admin (Global)", "rank": 100, "summary": "Creates and onboards users."},
    {"code": REGULAR_USER, "description": "Regular User", "rank": 10, "summary": "GRN email, sourcing, Misc PO alerts."},
    {"code": SENIOR_SITE_MANAGER, "description": "Senior Site Manager", "rank": 30, "summary": "BOM, RO, LPO/GRN."},
    {"code": GENERAL_MANAGER, "description": "General Manager", "rank": 50, "summary": "Payments, bid eval, signatory copies."},
    {"code": CEO, "description": "CEO", "rank": 80, "summary": "Budget, disbursement, CC all email."},
]

PERM_MANAGE_USERS = "manage_users"
PERM_VIEW_ALL_PAYMENTS = "view_all_payments"
PERM_APPROVE_BUDGET = "approve_budget"
PERM_DISBURSE_FUNDS = "disburse_funds"
PERM_BUDGET_VARIANCE_ALERTS = "budget_variance_alerts"
PERM_EMAIL_CC_ALL = "email_cc_all"
PERM_BOM_AUTHOR = "bom_author"
PERM_RO_AUTHOR = "ro_author"
PERM_LPO_GRN_CONFIRM = "lpo_grn_confirm"
PERM_GM_PAYMENTS = "gm_payments"
PERM_BID_EVALUATION = "bid_evaluation"
PERM_GM_SIGNATORY_COPIES = "gm_signatory_copies"
PERM_VIEW_FUND_LEDGER = "view_fund_ledger"
PERM_GRN_EMAIL = "grn_email"
PERM_SOURCE_PROCUREMENT = "source_procurement"
PERM_NOTIFY_MISC_PO_APPROVED = "notify_misc_po_approved"

ROLE_PERMISSIONS = {
    USER_ADMIN: {PERM_MANAGE_USERS, PERM_VIEW_ALL_PAYMENTS, PERM_APPROVE_BUDGET, PERM_DISBURSE_FUNDS, PERM_BUDGET_VARIANCE_ALERTS, PERM_BOM_AUTHOR, PERM_RO_AUTHOR, PERM_LPO_GRN_CONFIRM, PERM_GM_PAYMENTS, PERM_BID_EVALUATION, PERM_GM_SIGNATORY_COPIES, PERM_GRN_EMAIL, PERM_SOURCE_PROCUREMENT, PERM_NOTIFY_MISC_PO_APPROVED, PERM_VIEW_FUND_LEDGER},
    REGULAR_USER: {PERM_GRN_EMAIL, PERM_SOURCE_PROCUREMENT, PERM_NOTIFY_MISC_PO_APPROVED},
    SENIOR_SITE_MANAGER: {PERM_BOM_AUTHOR, PERM_RO_AUTHOR, PERM_LPO_GRN_CONFIRM, PERM_GRN_EMAIL},
    GENERAL_MANAGER: {PERM_GM_PAYMENTS, PERM_BID_EVALUATION, PERM_RO_AUTHOR, PERM_GM_SIGNATORY_COPIES, PERM_VIEW_ALL_PAYMENTS, PERM_VIEW_FUND_LEDGER},
    CEO: {PERM_APPROVE_BUDGET, PERM_DISBURSE_FUNDS, PERM_BUDGET_VARIANCE_ALERTS, PERM_VIEW_ALL_PAYMENTS, PERM_EMAIL_CC_ALL, PERM_GM_SIGNATORY_COPIES, PERM_VIEW_FUND_LEDGER},
}

def get_user_account(user):
    if not user or not user.is_authenticated:
        return None
    try:
        return user.useraccount
    except Exception:
        return None

def get_role_code(user):
    if user and user.is_superuser:
        return USER_ADMIN
    ua = get_user_account(user)
    if not ua or not ua.access_level:
        return None
    return getattr(ua.access_level, "code", None) or None

def user_has_role(user, *role_codes):
    code = get_role_code(user)
    return code in role_codes if code else False

def user_can(user, permission):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    code = get_role_code(user)
    if not code:
        return False
    return permission in ROLE_PERMISSIONS.get(code, set())

def can_manage_users(user):
    return user_can(user, PERM_MANAGE_USERS)

def ceo_cc_emails():
    from .models import UserAccount
    qs = UserAccount.objects.filter(access_level__code=CEO).exclude(email="")
    return list(dict.fromkeys(a.email.strip() for a in qs if a.email.strip()))

def system_admin_emails():
    """Email addresses for system-admin copies (GRN print, support alerts)."""
    from django.conf import settings
    from django.contrib.auth import get_user_model

    from .models import AppSettings, UserAccount

    emails = []
    configured = getattr(settings, "SYSTEM_ADMIN_EMAIL", "").strip()
    if configured:
        emails.extend(part.strip() for part in configured.split(",") if part.strip())

    try:
        app = AppSettings.objects.first()
        if app and app.support_email.strip():
            emails.append(app.support_email.strip())
    except Exception:
        pass

    for acc in UserAccount.objects.filter(access_level__code=USER_ADMIN).exclude(email=""):
        if acc.email.strip():
            emails.append(acc.email.strip())

    User = get_user_model()
    for user in User.objects.filter(is_superuser=True).exclude(email=""):
        if user.email.strip():
            emails.append(user.email.strip())

    return list(dict.fromkeys(emails))
