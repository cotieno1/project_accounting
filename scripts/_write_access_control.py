"""One-off writer for access control modules (run once)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

(ROOT / "accounts" / "roles.py").write_text(
    '''"""
Pioneer access categories (UserCategory.code) and permission helpers.
"""

USER_ADMIN = "USER_ADMIN"
REGULAR_USER = "REGULAR_USER"
SENIOR_SITE_MANAGER = "SENIOR_SITE_MANAGER"
GENERAL_MANAGER = "GENERAL_MANAGER"
CEO = "CEO"

ALL_ROLE_CODES = (
    USER_ADMIN,
    REGULAR_USER,
    SENIOR_SITE_MANAGER,
    GENERAL_MANAGER,
    CEO,
)

ROLE_DEFINITIONS = [
    {
        "code": USER_ADMIN,
        "description": "User Admin (Global)",
        "rank": 100,
        "summary": "Creates and onboards users, assigns access categories, global platform administration.",
    },
    {
        "code": REGULAR_USER,
        "description": "Regular User",
        "rank": 10,
        "summary": "Receives GRN by email, sources items/services, notified when Misc PO is approved.",
    },
    {
        "code": SENIOR_SITE_MANAGER,
        "description": "Senior Site Manager",
        "rank": 30,
        "summary": "Prepares and authorises BOM and RO; receives and confirms LPO / GRNs.",
    },
    {
        "code": GENERAL_MANAGER,
        "description": "General Manager",
        "rank": 50,
        "summary": "Approves payments, bid evaluation, RO; Misc Purchase signatory document copies.",
    },
    {
        "code": CEO,
        "description": "CEO",
        "rank": 80,
        "summary": "Budget approval and fund disbursement; variance alerts; all payments; CC on all emails.",
    },
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
PERM_GRN_EMAIL = "grn_email"
PERM_SOURCE_PROCUREMENT = "source_procurement"
PERM_NOTIFY_MISC_PO_APPROVED = "notify_misc_po_approved"

ROLE_PERMISSIONS = {
    USER_ADMIN: {
        PERM_MANAGE_USERS, PERM_VIEW_ALL_PAYMENTS, PERM_APPROVE_BUDGET, PERM_DISBURSE_FUNDS,
        PERM_BUDGET_VARIANCE_ALERTS, PERM_BOM_AUTHOR, PERM_RO_AUTHOR, PERM_LPO_GRN_CONFIRM,
        PERM_GM_PAYMENTS, PERM_BID_EVALUATION, PERM_GM_SIGNATORY_COPIES, PERM_GRN_EMAIL,
        PERM_SOURCE_PROCUREMENT, PERM_NOTIFY_MISC_PO_APPROVED,
    },
    REGULAR_USER: {PERM_GRN_EMAIL, PERM_SOURCE_PROCUREMENT, PERM_NOTIFY_MISC_PO_APPROVED},
    SENIOR_SITE_MANAGER: {PERM_BOM_AUTHOR, PERM_RO_AUTHOR, PERM_LPO_GRN_CONFIRM, PERM_GRN_EMAIL},
    GENERAL_MANAGER: {
        PERM_GM_PAYMENTS, PERM_BID_EVALUATION, PERM_RO_AUTHOR,
        PERM_GM_SIGNATORY_COPIES, PERM_VIEW_ALL_PAYMENTS,
    },
    CEO: {
        PERM_APPROVE_BUDGET, PERM_DISBURSE_FUNDS, PERM_BUDGET_VARIANCE_ALERTS,
        PERM_VIEW_ALL_PAYMENTS, PERM_EMAIL_CC_ALL, PERM_GM_SIGNATORY_COPIES,
    },
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
''',
    encoding="utf-8",
)

print("wrote roles.py")
