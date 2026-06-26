"""Template filters used only by bom_builder.html."""

import ast

from django import template

register = template.Library()


@register.filter
def clean_task_id(value):
    """Strip brackets and quotes from task ids for BOM builder display."""
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, (list, tuple)) and parsed:
                s = str(parsed[0]).strip()
            elif isinstance(parsed, str):
                s = parsed.strip()
        except (ValueError, SyntaxError):
            inner = s[1:-1].strip().strip("'\"")
            if inner:
                s = inner.split(",")[0].strip().strip("'\"")
    return s.strip("'\"[]")[:50]
