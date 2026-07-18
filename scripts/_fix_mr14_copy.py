from pathlib import Path

def read_html(path):
    raw = Path(path).read_bytes()
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")

p = Path("templates/tenders/bid_subcontract.html")
t = read_html(p)
idx = t.find("Isiolo electrical")
if idx < 0:
    idx = t.find("RFQ MR14 (bid preparation)")
if idx < 0:
    raise SystemExit("RFQ card marker not found")
start = t.rfind('<div class="bw-card"', 0, idx)
end = t.find('<div class="bw-card-header">Active arrangements')
end = t.rfind('<div class="bw-card">', 0, end)
new_card = """<div class="bw-card" style="margin-bottom:14px;">
        <div class="bw-card-header">RFQ MR14 (bid preparation)</div>
        <div class="bw-card-body" style="font-size:.82rem;color:var(--bw-mid);line-height:1.5;">
          <p style="margin:0 0 10px;"><strong style="color:var(--bw-navy);">When</strong> -
            During bid prep, before submit - not after award.</p>
          <p style="margin:0 0 10px;"><strong style="color:var(--bw-navy);">Document</strong> -
            Duly signed and stamped Domestic Sub-Contractor Agreement, not earlier than 1 month,
            between the Electrical Services sub and the main contractor.</p>
          <p style="margin:0 0 10px;"><strong style="color:var(--bw-navy);">Effect</strong> -
            Lodging the PDF marks MR14 complete on the certificate checklist.</p>
          <p style="margin:0;"><strong style="color:var(--bw-navy);">Exception</strong> -
            N/A if the main contractor is registered for all Electrical Services Works
            (set on the Certificates page).</p>
        </div>
      </div>

      """
if start < 0 or end < 0 or end <= start:
    raise SystemExit(f"markers not found start={start} end={end}")
p.write_text(t[:start] + new_card + t[end:], encoding="utf-8")
print("subcontract list ok")

d = Path("templates/tenders/bid_subcontract_detail.html")
dt = read_html(d).replace("\ufffd", "-")
# normalize common mojibake headers
dt = dt.replace("2 - Signed agreement ? satisfies MR14", "2 - Signed agreement - satisfies MR14")
d.write_text(dt, encoding="utf-8")
print("detail ok")
