from pathlib import Path

# --- patch views_tenders.py ---
vp = Path("buildwatch/views_tenders.py")
vt = vp.read_text(encoding="utf-8")

helper = '''
def _apply_boq_input_mode(listing, mode: str) -> dict:
    """Switch listing BOQ data source; keep the same bid form (packages/lines)."""
    from buildwatch.boq_ingest.persist import apply_standard_boq
    from buildwatch.boq_ingest.sources import load_hardwired_boq, load_pdf_auto_boq
    from buildwatch.models import BidWorkspace, WorkspaceBillPrice

    mode = (mode or "").strip().upper()
    if mode == TenderListing.BOQ_HARDWIRED:
        doc = load_hardwired_boq()
    elif mode == TenderListing.BOQ_PDF_AUTO:
        doc = load_pdf_auto_boq(listing)
    else:
        raise ValueError("Unknown BOQ mode")

    stats = apply_standard_boq(listing, doc)
    listing.boq_input_mode = mode
    listing.save(update_fields=["boq_input_mode"])

    # Clear package selections / prices so contractors re-select under new source
    for ws in BidWorkspace.objects.filter(tender=listing).exclude(
        status=BidWorkspace.SUBMITTED
    ):
        WorkspaceBillPrice.objects.filter(workspace=ws).delete()
        ws.selected_package_codes = []
        ws.pricing_complete = False
        ws.save(update_fields=["selected_package_codes", "pricing_complete"])

    stats["mode"] = mode
    stats["warnings"] = list(getattr(doc, "warnings", []) or [])
    stats["source_name"] = getattr(doc, "source_name", "")
    return stats

'''

if "_apply_boq_input_mode" not in vt:
    # insert before bid_workspace def
    anchor = "def bid_workspace(request, listing_id):"
    if anchor not in vt:
        raise SystemExit("bid_workspace not found")
    vt = vt.replace(anchor, helper + anchor, 1)
    print("helper inserted")
else:
    print("helper exists")

# Insert set_boq_mode action handling
old = '''    if request.method == "POST" and listing.event.is_open and workspace.status != BidWorkspace.SUBMITTED:
        action = (request.POST.get("action") or "save_prices").strip()

        if action == "select_packages":'''

# file uses single quotes
old = """    if request.method == 'POST' and listing.event.is_open and workspace.status != BidWorkspace.SUBMITTED:
        action = (request.POST.get('action') or 'save_prices').strip()

        if action == 'select_packages':"""

new = """    if request.method == 'POST' and listing.event.is_open and workspace.status != BidWorkspace.SUBMITTED:
        action = (request.POST.get('action') or 'save_prices').strip()

        if action == 'set_boq_mode':
            mode = (request.POST.get('boq_input_mode') or '').strip().upper()
            try:
                stats = _apply_boq_input_mode(listing, mode)
            except Exception as exc:
                messages.error(request, f'Could not switch BOQ source: {exc}')
                return redirect('bid-workspace', listing_id=listing_id)
            label = 'A (Hardwired)' if mode == TenderListing.BOQ_HARDWIRED else 'B (RFQ PDF auto)'
            messages.success(
                request,
                f'Switched to {label}: {stats[\"categories\"]} categories, '
                f'{stats[\"lines\"]} lines. Re-select categories to price.',
            )
            for wmsg in stats.get('warnings') or []:
                messages.warning(request, wmsg)
            return redirect('bid-workspace', listing_id=listing_id)

        # refresh packages after possible prior mode change in same process
        packages = list(
            TenderBoqPackage.objects.filter(tender=listing)
            .prefetch_related('lines')
            .order_by('sort_order', 'code')
        )

        if action == 'select_packages':"""

if "set_boq_mode" in vt:
    print("set_boq_mode already in view")
else:
    if old not in vt:
        raise SystemExit("POST block not found")
    vt = vt.replace(old, new, 1)
    print("set_boq_mode wired")

# Add boq_input_mode to context
ctx_old = """        'selected_codes': selected,
        'package_sections': package_sections,"""
ctx_new = """        'selected_codes': selected,
        'boq_input_mode': listing.boq_input_mode,
        'boq_mode_choices': TenderListing.BOQ_INPUT_MODE_CHOICES,
        'package_sections': package_sections,"""
if "boq_input_mode" in vt and "boq_mode_choices" in vt:
    print("context already has mode")
else:
    if ctx_old not in vt:
        raise SystemExit("ctx not found")
    vt = vt.replace(ctx_old, ctx_new, 1)
    print("context patched")

vp.write_text(vt, encoding="utf-8")
compile(vt, "views_tenders.py", "exec")
print("views compile ok")
