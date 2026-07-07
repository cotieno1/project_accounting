from django import template

register = template.Library()


@register.filter(name="org_display_short_name")
def org_display_short_name(org):
    from accounts.views import _organization_display_short_name

    return _organization_display_short_name(org)


@register.filter(name="org_display_name")
def org_display_name(org):
    from accounts.views import _organization_display_name

    return _organization_display_name(org)


@register.filter(name="org_display_code")
def org_display_code(org):
    from accounts.views import _normalize_org_code

    if org is None:
        return ""
    return _normalize_org_code(getattr(org, "org_code", "")) or str(org.org_code or "")


@register.filter(name="clean_task_id")
def clean_task_id(value):
    from accounts.views import _normalize_task_id

    return _normalize_task_id(value)


@register.filter(name="clean_task_description")
def clean_task_description(value):
    from accounts.views import _normalize_task_description

    return _normalize_task_description(value)


@register.filter(name="money")
def money(value):
    """Comma-separated amount, e.g. 1,000.00"""
    from accounts.currency import _money_amount

    return _money_amount(value)


@register.filter(name="fmt_money")
def fmt_money_tag(value):
    """Symbol + comma amount, e.g. US$ 1,000.00"""
    from accounts.currency import fmt_money

    return fmt_money(value)
