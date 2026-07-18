from pathlib import Path

p = Path("templates/misc_purchase.html")
text = p.read_text(encoding="utf-8")

if "<!-- MISC_PURCHASE_STYLE_REMOVED" in text:
    start = text.index("<!-- MISC_PURCHASE_STYLE_REMOVED")
    marker = '<h2 style="color: var(--primary); margin: 0;">PIONEER</h2>'
    end = text.index(marker)
    text = text[:start] + text[end:]

text = text.replace(
    '\n    </div>\n\n    <div class="main-content">\n        <div class="workspace-scroller">',
    "\n{% endblock %}\n{% block workspace %}",
    1,
)
text = text.replace(
    '\n        </div>\n    </div>\n\n    <div id="reviewModal"',
    '\n{% endblock %}\n{% block modals %}\n    <div id="reviewModal"',
    1,
)
text = text.replace(
    "\n    <script>\n        const CURRENCY_SYMBOL",
    "\n{% endblock %}\n{% block extra_js %}\n    <script>\n        const CURRENCY_SYMBOL",
    1,
)
text = text.replace("\n    </script>\n</body>\n</html>\n", "\n    </script>\n{% endblock %}\n")

p.write_text(text, encoding="utf-8")
print("Refactored", p)
