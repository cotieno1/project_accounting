from pathlib import Path

vp = Path("buildwatch/views_tenders.py")
vt = vp.read_text(encoding="utf-8")

helper = '''
def _bid_pack_context(request, listing, workspace, org, ua):
    """Shared context for draft/submitted bid PDF pack."""
    from decimal import Decimal
    from django.utils import timezone
    from accounts.branding import branding_template_context

    selected = workspace.selected_codes()
    packages = list(
        TenderBoqPackage.objects.filter(tender=listing)
        .prefetch_related("lines")
        .order_by("sort_order", "code")
    )
    selected_packages = [p for p in packages if p.code.upper() in selected]
    price_map = {bp.bill_ref: bp for bp in workspace.bill_prices.all()}

    package_sections = []
    category_summary = []
    grand_total = Decimal("0")
    for pkg in selected_packages:
        rows = []
        subtotal = Decimal("0")
        for line in pkg.lines.all():
            bp = price_map.get(line.bill_ref)
            amount = bp.amount if bp else Decimal("0")
            rate = bp.unit_rate if bp else Decimal("0")
            subtotal += amount
            rows.append({"line": line, "rate": rate, "amount": amount})
        grand_total += subtotal
        package_sections.append({
            "package": pkg,
            "rows": rows,
            "subtotal": subtotal,
            "line_count": len(rows),
        })
        category_summary.append({
            "code": pkg.code,
            "title": pkg.title,
            "subtotal": subtotal,
            "line_count": len(rows),
        })

    prepared_by_name = ""
    if ua:
        prepared_by_name = (
            getattr(ua, "get_full_name", lambda: "")()
            or getattr(ua, "username", "")
            or str(ua)
        )

    is_draft = workspace.status != BidWorkspace.SUBMITTED
    ctx = {
        "listing": listing,
        "workspace": workspace,
        "org": org,
        "self_checks": workspace.self_checks.order_by("mr_ref"),
        "package_sections": package_sections,
        "category_summary": category_summary,
        "grand_total": grand_total,
        "is_draft": is_draft,
        "prepared_by_name": prepared_by_name,
        "generated_at": timezone.now(),
        **branding_template_context(request),
    }
    return ctx


'''

if "_bid_pack_context" not in vt:
    anchor = "def _apply_boq_input_mode(listing, mode: str) -> dict:"
    if anchor not in vt:
        # try after imports / before bid_workspace
        anchor = "def bid_workspace(request, listing_id):"
        vt = vt.replace(anchor, helper + "\n" + anchor, 1)
    else:
        vt = vt.replace(anchor, helper + anchor, 1)
    print("helper inserted")
else:
    print("helper exists")

view = '''
@login_required
def bid_draft_pdf(request, listing_id):
    """
    GET /tenders/<listing_id>/bid/draft.pdf/
    Completed draft (or submitted) bid pack PDF: certificates + priced BOQ.
    """
    from accounts.misc_doc_pdf import build_pdf_bytes, pdf_inline_response

    listing = get_object_or_404(TenderListing, pk=listing_id, is_published=True)
    org = get_active_organization(request)
    try:
        ua = _ensure_user_account(request, org)
    except Exception:
        ua = _get_user_account(request)

    if not BidderRegistration.objects.filter(tender=listing, organisation=org).exists():
        messages.warning(request, "Register your interest before downloading the bid pack.")
        return redirect("tender-detail", listing_id=listing_id)

    workspace = get_object_or_404(BidWorkspace, tender=listing, organisation=org)
    ctx = _bid_pack_context(request, listing, workspace, org, ua)

    # Soft readiness: allow download anytime, but warn if incomplete for draft
    ready = (
        bool(workspace.selected_codes())
        and workspace.pricing_complete
        and workspace.self_assessment_passed
    )
    if not ready and ctx["is_draft"]:
        messages.warning(
            request,
            "Draft PDF generated with incomplete gates "
            "(categories / pricing / certificates). Complete all before submit.",
        )

    try:
        pdf = build_pdf_bytes("tenders/bid_draft_print.html", ctx)
    except Exception as exc:
        messages.error(request, f"Could not build bid PDF: {exc}")
        return redirect("bid-workspace", listing_id=listing_id)

    status = "DRAFT" if ctx["is_draft"] else "SUBMITTED"
    filename = f"Bid_{listing.event.ref}_{org.short_name}_{status}".replace("/", "-")
    return pdf_inline_response(pdf, filename)


'''

if "def bid_draft_pdf" not in vt:
    # insert before bid_submit
    a = "@login_required\n@require_POST\ndef bid_submit(request, listing_id):"
    if a not in vt:
        raise SystemExit("bid_submit not found")
    vt = vt.replace(a, view + a, 1)
    print("bid_draft_pdf added")
else:
    print("bid_draft_pdf exists")

# after successful submit redirect message - also mention PDF
old_msg = """        messages.success(request,
            f'Bid submitted successfully. Reference: {listing.event.ref}. '
            f'Your submission ID is {submission.pk}. '
            f'You will be notified of the outcome.')
"""
new_msg = """        messages.success(request,
            f'Bid submitted successfully. Reference: {listing.event.ref}. '
            f'Your submission ID is {submission.pk}. '
            f'Download your submitted bid pack from the workspace if needed.')
"""
if "Download your submitted bid pack" not in vt:
    if old_msg in vt:
        vt = vt.replace(old_msg, new_msg, 1)
        print("submit message updated")

vp.write_text(vt, encoding="utf-8")
compile(vp.read_text(encoding="utf-8"), "views", "exec")
print("views compile ok")

# URL
up = Path("buildwatch/urls.py")
ut = up.read_text(encoding="utf-8")
if "bid-draft-pdf" not in ut:
    needle = """    path('<int:listing_id>/bid/submit/',
         t.bid_submit,
         name='bid-submit'),
"""
    insert = """    path('<int:listing_id>/bid/draft.pdf/',
         t.bid_draft_pdf,
         name='bid-draft-pdf'),

    path('<int:listing_id>/bid/submit/',
         t.bid_submit,
         name='bid-submit'),
"""
    if needle not in ut:
        raise SystemExit("url needle missing")
    up.write_text(ut.replace(needle, insert, 1), encoding="utf-8")
    print("url added")
else:
    print("url exists")
