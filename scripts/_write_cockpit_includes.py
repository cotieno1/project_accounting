from pathlib import Path
lane = Path("templates/includes/cockpit_lane_subtitle.html")
brand = Path("templates/includes/cockpit_sidebar_brand.html")
lane.write_text("Ops Command | {{ lane }}{% if process %} ({{ process }}){% endif %}\n", encoding="utf-8", newline="\n")
brand.write_text("""<div class=\"cockpit-sidebar-brand{% if brand_class %} {{ brand_class }}{% endif %}\">
    <h2{% if title_class %} class=\"{{ title_class }}\"{% endif %}>{{ brand_title|default:\"PIONEER\" }}</h2>
    <small>{% include \"includes/cockpit_lane_subtitle.html\" with lane=lane process=process only %}</small>
</div>
""", encoding="utf-8", newline="\n")
print(lane.read_bytes()[:8].hex())
print(brand.read_bytes()[:8].hex())
