from .models import AppSettings
from .tenant import get_active_organization
from .currency import currency_context


def branding(request):
    """Inject Project Accounting software brand + active client company."""
    app = AppSettings.get()
    org = get_active_organization(request)
    org_count = 0
    try:
        from .models import Organization
        org_count = Organization.objects.count()
    except Exception:
        pass
    return {
        "app_name": app.app_name,
        "app_short_name": app.app_short_name,
        "app_tagline": app.app_tagline,
        "app_support_email": app.support_email,
        "app_vendor_name": app.vendor_name,
        "org": org,
        "org_name": org.name if org else "",
        "org_short_name": org.short_name if org else "",
        "org_code": org.org_code if org else "",
        "org_registered_address": org.registered_address if org else "",
        "org_contact_address": org.contact_address if org else "",
        "org_address": (
            org.contact_address or org.registered_address if org else ""
        ),
        "org_phone": org.phone if org else "",
        "org_email": org.email if org else "",
        "org_tax_pin": org.tax_pin if org else "",
        "org_tagline": org.document_tagline if org else "",
        "tenant_count": org_count,
        **currency_context(),
    }