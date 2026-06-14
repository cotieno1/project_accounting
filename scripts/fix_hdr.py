from pathlib import Path
ROOT = Path(r"C:\project_accounting")
HEADER = ROOT / "templates/includes/print_correspondence_header.html"
HEADER.write_text('{% include "includes/org_letterhead.html" %}\n', encoding="utf-8")
styles = ROOT / "templates/lpo/styles.html"
assert b"\x00" not in HEADER.read_bytes()
print("header fixed", HEADER.read_text(encoding="utf-8"))
print("lpo styles has include?", "correspondence_theme" in styles.read_text(encoding="utf-8", errors="replace"))
