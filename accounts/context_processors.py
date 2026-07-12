from django.urls import reverse

from .models import AppSettings
from .tenant import get_active_organization, exchange_persona_context
from .currency import currency_context


def _main_dashboard_url(request):
    """Platform admin → /platform/; tenant staff → /dashboard/; guests → home."""
    from .roles import USER_ADMIN, get_role_code

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return reverse("home")
    if user.is_superuser or get_role_code(user) == USER_ADMIN:
        return reverse("platform_admin")
    return reverse("dashboard")


def branding(request):
    """Inject Project Accounting software brand + active client company."""
    persona = exchange_persona_context(request)
    defaults = {
        "app_name": "Project Accounting",
        "app_short_name": "Project Accounting",
        "app_tagline": "Financial Operations Platform",
        "app_support_email": "",
        "app_vendor_name": "",
        "org": None,
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
        "tenant_count": 0,
        "currency_code": "USD",
        "currency_symbol": "US$",
        "main_dashboard_url": reverse("home"),
        **persona,
    }
    try:
        app = AppSettings.get()
        org = get_active_organization(request)
        org_count = 0
        try:
            from .models import Organization
            from .views import _organizations_canonical_list

            org_count = len(_organizations_canonical_list(Organization.objects.all()))
        except Exception:
            pass
        return {
            "app_name": app.app_name,
            "app_short_name": app.app_short_name,
            "app_tagline": app.app_tagline,
            "app_support_email": app.support_email,
            "app_vendor_name": app.vendor_name,
            "org": org if request.user.is_authenticated else None,
            "org_name": org.name if org and request.user.is_authenticated else "",
            "org_short_name": org.short_name if org and request.user.is_authenticated else "",
            "org_code": org.org_code if org and request.user.is_authenticated else "",
            "org_registered_address": org.registered_address if org and request.user.is_authenticated else "",
            "org_contact_address": org.contact_address if org and request.user.is_authenticated else "",
            "org_address": (
                (org.contact_address or org.registered_address)
                if org and request.user.is_authenticated
                else ""
            ),
            "org_phone": org.phone if org and request.user.is_authenticated else "",
            "org_email": org.email if org and request.user.is_authenticated else "",
            "org_tax_pin": org.tax_pin if org and request.user.is_authenticated else "",
            "org_tagline": org.document_tagline if org and request.user.is_authenticated else "",
            "tenant_count": org_count,
            "main_dashboard_url": _main_dashboard_url(request),
            # Persona only for signed-in staff of their organisation (never default tenant for guests)
            **exchange_persona_context(
                request,
                org if request.user.is_authenticated else None,
            ),
            **currency_context(),
        }
    except Exception:
        return defaults
