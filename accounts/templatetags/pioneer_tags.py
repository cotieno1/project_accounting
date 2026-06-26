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
