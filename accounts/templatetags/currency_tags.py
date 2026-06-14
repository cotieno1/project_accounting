from django import template

from accounts.currency import fmt_money

register = template.Library()


@register.filter(name="money")
def money_filter(amount):
    return fmt_money(amount)


@register.simple_tag
def money(amount):
    return fmt_money(amount)
