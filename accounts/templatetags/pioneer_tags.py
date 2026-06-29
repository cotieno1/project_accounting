from django import template

register = template.Library()


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
