from pathlib import Path

txt_path = Path("templates/emails/onboarding_set_password.txt")
txt = txt_path.read_text(encoding="utf-8")
txt = txt.replace(
    "You have been invited to {{ app_name }}{% if invited_by %} by {{ invited_by }}{% endif %}.",
    "You have been invited to {{ org_name|default:app_name }}{% if invited_by %} by {{ invited_by }}{% endif %} on {{ app_name }}.",
)
txt_path.write_text(txt, encoding="utf-8", newline="\n")

html_path = Path("templates/emails/onboarding_set_password.html")
html = html_path.read_text(encoding="utf-8")
html = html.replace(
    "<p>You have been invited to <strong>{{ app_name }}</strong>{% if invited_by %} by {{ invited_by }}{% endif %}.</p>",
    "<p>You have been invited to <strong>{{ org_name|default:app_name }}</strong>{% if invited_by %} by {{ invited_by }}{% endif %} on <strong>{{ app_name }}</strong>.</p>",
)
html_path.write_text(html, encoding="utf-8", newline="\n")

for p in (txt_path, html_path):
    b = p.read_bytes()
    print(p, len(b), b.count(b"\x00"))