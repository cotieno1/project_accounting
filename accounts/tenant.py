"""Resolve which client organization is active for the current request."""
from .models import Organization, UserAccount


def get_active_organization(request):
    """
    Multi-tenant resolution order:
    1. Platform admin session override (superuser switching companies)
    2. Logged-in user's assigned organization
    3. Platform default organization (fallback)
    """
    if request is not None and getattr(request, "user", None) and request.user.is_authenticated:
        if request.user.is_superuser:
            code = request.session.get("active_org_code")
            if code:
                org = Organization.objects.filter(org_code=code).first()
                if org:
                    return org

        try:
            ua = UserAccount.objects.select_related("organization").get(user=request.user)
            if ua.organization_id:
                return ua.organization
        except UserAccount.DoesNotExist:
            pass

    return Organization.get_default()


def branding_template_context(request=None):
    """Flat branding dict for PDF/offline template rendering (no request context processor)."""
    from .models import AppSettings
    from .currency import currency_context

    defaults = {
        "app_name": "Project Accounting",
        "app_short_name": "Project Accounting",
        "app_tagline": "Financial Operations Platform",
        "org_name": "",
        "org_short_name": "",
        "org_code": "",
        "org_registered_address": "",
        "org_contact_address": "",
        "org_address": "",
        "org_phone": "",
        "org_email": "",
        "org_tax_pin": "",
        "org_tagline": "",
        **currency_context(),
    }
    try:
        app = AppSettings.get()
        org = get_active_organization(request)
        return {
            "app_name": app.app_name,
            "app_short_name": app.app_short_name,
            "app_tagline": app.app_tagline,
            "org_name": org.name if org else "",
            "org_short_name": org.short_name if org else "",
            "org_code": org.org_code if org else "",
            "org_registered_address": org.registered_address if org else "",
            "org_contact_address": org.contact_address if org else "",
            "org_address": (org.contact_address or org.registered_address if org else ""),
            "org_phone": org.phone if org else "",
            "org_email": org.email if org else "",
            "org_tax_pin": org.tax_pin if org else "",
            "org_tagline": org.document_tagline if org else "",
            **currency_context(),
        }
    except Exception:
        return defaults


# BuildWatch tender exchange — two marketplace sides
# Persona is set at organisation registration and applies to every
# authorised staff member under that organisation (e.g. all Pioneer staff).
EMPLOYER_ORG_TYPES = {
    "GOV_NATIONAL",
    "GOV_COUNTY",
    "PARASTATAL",
    "FINANCIER",
    "DEVELOPER",
    "NGO",
    "CLIENT",
    "INSTITUTION",
    "PRIVATE",
    "INDIVIDUAL",
    "OTHER",
}
CONTRACTOR_ORG_TYPES = {
    "CONTRACTOR",
    "CONSULTANT",
    "BUILDING",
    "ROADS",
    "SPECIALIST",
    "GENERAL",
}


def get_exchange_persona(org=None, request=None):
    """Return contractor | employer | guest for BuildWatch UI customisation.

    Organisation-level: every authorised user under the org shares the same face.
    Guests never inherit the platform default tenant (e.g. Pioneer).
    """
    user = getattr(request, "user", None) if request is not None else None
    if request is not None and (not user or not user.is_authenticated):
        return "guest"

    if org is None and request is not None:
        org = get_active_organization(request)
    if org is None:
        return "guest"

    org_type = (getattr(org, "organization_type", "") or "").strip().upper()
    if org_type in EMPLOYER_ORG_TYPES:
        return "employer"
    if org_type in CONTRACTOR_ORG_TYPES:
        return "contractor"
    if org_type in {"QS", "ARCHITECT", "STRUCTURAL", "CIVIL", "MEP", "PM"}:
        return "contractor"

    ctype = (getattr(org, "contractor_type", "") or "").strip().upper()
    if ctype in {"BUILDING", "ROADS", "CONSULTANT"}:
        return "contractor"
    return "contractor"


def exchange_persona_context(request=None, org=None):
    user = getattr(request, "user", None) if request is not None else None
    authenticated = bool(user and user.is_authenticated)

    # Guests: never use default/platform org for labeling
    if request is not None and not authenticated:
        org = None
    elif org is None and authenticated:
        org = get_active_organization(request)

    persona = get_exchange_persona(org=org, request=request)
    # Prefer registered legal name (as on the portal), not short code/label
    org_name = ""
    if org is not None and authenticated:
        org_name = (getattr(org, "name", None) or getattr(org, "short_name", None) or "").strip()

    brand = f"BuildWatch - {org_name}" if org_name else "BuildWatch"

    labels = {
        "guest": {
            "bw_persona": "guest",
            "bw_persona_label": "Tender exchange",
            "bw_persona_kicker": "Public procurement exchange",
            "bw_persona_title": "Open tenders",
            "bw_persona_lead": (
                "One exchange for both sides: contractors bid on works; "
                "government departments, DFIs and private institutions publish and manage tenders."
            ),
            "bw_primary_cta_label": "Browse tenders",
            "bw_secondary_cta_label": "Publish a tender",
            "bw_org_display": "",
            "bw_brand_title": "BuildWatch",
        },
        "contractor": {
            "bw_persona": "contractor",
            "bw_persona_label": (f"{org_name} · Contractor" if org_name else "Contractor workspace"),
            "bw_persona_kicker": "Contractor · building & infrastructure",
            "bw_persona_title": "Tenders you can bid",
            "bw_persona_lead": (
                (f"Working under {org_name}. " if org_name else "")
                + "Browse published works, register interest, download BOQ packages "
                + "and submit bids for your organisation. Contractors do not publish tenders here."
            ),
            "bw_primary_cta_label": "My bids",
            "bw_secondary_cta_label": "Set alerts",
            "bw_org_display": org_name,
            "bw_brand_title": brand,
        },
        "employer": {
            "bw_persona": "employer",
            "bw_persona_label": (f"{org_name} · Employer" if org_name else "Employer / institution workspace"),
            "bw_persona_kicker": "Employer · government · DFI · private",
            "bw_persona_title": "Tenders you publish",
            "bw_persona_lead": (
                (f"Working under {org_name}. " if org_name else "")
                + "Publish and manage open procurement for works and services — "
                + "government departments, World Bank / AfDB programmes, "
                + "and private institutions or companies."
            ),
            "bw_primary_cta_label": "Publish tender",
            "bw_secondary_cta_label": "Manage projects",
            "bw_org_display": org_name,
            "bw_brand_title": brand,
        },
    }
    return labels[persona]
