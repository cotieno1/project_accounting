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