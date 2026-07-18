from pathlib import Path

p = Path("templates/gm_aie_disbursement.html")
text = p.read_text(encoding="utf-8")

start = text.index('<h2 style="color: var(--primary); margin: 0;">PIONEER</h2>')
core = text[start:]
core = core.replace("\n{% endif %}\n</body>\n</html>\n", "\n")

core = core.replace(
    "\n    </div>\n\n    <div class=\"main-content\">\n        <div class=\"workspace-scroller\">",
    "\nSIDEBAR_END\nWORKSPACE_START\n",
    1,
)
core = core.replace(
    "\n        </div>\n    </div>\n\n    <div id=\"grnPeriodModal\"",
    "\nWORKSPACE_END\nMODALS_START\n    <div id=\"grnPeriodModal\"",
    1,
)
core = core.replace(
    "\n    <script>\n        const lineData = {",
    "\nMODALS_END\nSCRIPTS_START\n    <script>\n        const lineData = {",
    1,
)

sidebar, rest = core.split("SIDEBAR_END\n", 1)
_, rest = rest.split("WORKSPACE_START\n", 1)
workspace, rest = rest.split("WORKSPACE_END\n", 1)
modals, scripts = rest.split("MODALS_START\n", 1)[1].split("MODALS_END\nSCRIPTS_START\n", 1)

header = """{% extends "layouts/cockpit.html" %}
{% load static %}
{% block title %}Pioneer | GM AIE Disbursement{% endblock %}
{% block body_class %}gm-desk{% endblock %}
{% block extra_css %}
<link rel="stylesheet" href="{% static 'css/pioneer/modules/gm-aie-disbursement.css' %}">
{% endblock %}
{% block sidebar %}
{% if not no_tasks %}
"""

sidebar_tail = """{% else %}
<h2 style="color: var(--primary); margin: 0;">PIONEER</h2>
<p style="color: var(--muted); font-size: 14px;">No project tasks in the system.</p>
{% endif %}
{% endblock %}
{% block workspace %}
{% if no_tasks %}
<div class="panel" style="color:var(--muted);">No project tasks in the system.</div>
{% else %}
"""

workspace_tail = """{% endif %}
{% endblock %}
{% block modals %}
{% if not no_tasks %}
"""

modals_tail = """{% endif %}
{% endblock %}
{% block extra_js %}
{% if not no_tasks %}
"""

scripts_tail = """{% endif %}
{% endblock %}
"""

final = header + sidebar + sidebar_tail + workspace + workspace_tail + modals + modals_tail + scripts + scripts_tail
p.write_text(final, encoding="utf-8")
print("OK", p, "lines", len(final.splitlines()))
