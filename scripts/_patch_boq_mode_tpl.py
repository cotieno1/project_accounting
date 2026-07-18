from pathlib import Path

p = Path("templates/tenders/bid_workspace.html")
t = p.read_text(encoding="utf-8")
marker = """  {% if not listing.event.is_open %}
  <div class=\"bw-alert bw-alert--warning\">This tender has closed. Workspace is read-only.</div>
  {% endif %}"""

# actual file may not escape
marker = """  {% if not listing.event.is_open %}
  <div class="bw-alert bw-alert--warning">This tender has closed. Workspace is read-only.</div>
  {% endif %}"""

block = """  {% if not listing.event.is_open %}
  <div class="bw-alert bw-alert--warning">This tender has closed. Workspace is read-only.</div>
  {% endif %}

  {% if listing.event.is_open and workspace.status != 'SUBMITTED' %}
  <div class="bw-card" style="margin-bottom:16px;">
    <div class="bw-card-header">BOQ input source</div>
    <div class="bw-card-body">
      <p style="font-size:.86rem;color:var(--bw-mid);margin:0 0 12px;">
        Same bid form either way. Switch A uses the curated hardwired BOQ;
        Switch B rebuilds categories/lines from the RFQ/BOQ PDF (or shipped extract).
      </p>
      <form method="POST" action="{% url 'bid-workspace' listing.pk %}"
            style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;">
        {% csrf_token %}
        <input type="hidden" name="action" value="set_boq_mode">
        <label style="display:flex;gap:8px;align-items:center;padding:10px 14px;border:1px solid var(--bw-rule);border-radius:8px;cursor:pointer;background:{% if boq_input_mode == 'HARDWIRED' %}#f0fdf9{% else %}var(--bw-white){% endif %};">
          <input type="radio" name="boq_input_mode" value="HARDWIRED"
                 {% if boq_input_mode == 'HARDWIRED' %}checked{% endif %}>
          <span><strong>A — Hardwired</strong><br>
            <span style="font-size:.75rem;color:var(--bw-mid);">Curated seed (current production baseline)</span>
          </span>
        </label>
        <label style="display:flex;gap:8px;align-items:center;padding:10px 14px;border:1px solid var(--bw-rule);border-radius:8px;cursor:pointer;background:{% if boq_input_mode == 'PDF_AUTO' %}#f0fdf9{% else %}var(--bw-white){% endif %};">
          <input type="radio" name="boq_input_mode" value="PDF_AUTO"
                 {% if boq_input_mode == 'PDF_AUTO' %}checked{% endif %}>
          <span><strong>B — RFQ PDF auto</strong><br>
            <span style="font-size:.75rem;color:var(--bw-mid);">Parse RFQ/BOQ PDF into the same BQT categories</span>
          </span>
        </label>
        <button type="submit" class="bw-btn bw-btn--teal">Apply source</button>
      </form>
      <div style="margin-top:10px;font-family:var(--bw-mono);font-size:.72rem;color:var(--bw-mid);">
        Active: {{ boq_input_mode }}
      </div>
    </div>
  </div>
  {% endif %}"""

if "set_boq_mode" in t or "BOQ input source" in t:
    print("template already has switch")
else:
    if marker not in t:
        raise SystemExit("marker missing")
    p.write_text(t.replace(marker, block, 1), encoding="utf-8")
    print("template patched")
