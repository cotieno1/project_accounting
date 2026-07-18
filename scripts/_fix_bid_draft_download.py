from pathlib import Path

# 1) Force attachment download helper
p = Path("accounts/misc_doc_pdf.py")
t = p.read_text(encoding="utf-8")
if "pdf_attachment_response" not in t:
    t = t.replace(
        '''def pdf_inline_response(pdf_bytes, filename):
    from django.http import HttpResponse

    safe = _safe_filename(filename)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{safe}.pdf"'
    response["Cache-Control"] = "private, max-age=300"
    return response
''',
        '''def pdf_inline_response(pdf_bytes, filename):
    from django.http import HttpResponse

    safe = _safe_filename(filename)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{safe}.pdf"'
    response["Cache-Control"] = "private, max-age=300"
    return response


def pdf_attachment_response(pdf_bytes, filename):
    """Force browser download (more reliable than inline for large bid packs)."""
    from django.http import HttpResponse

    safe = _safe_filename(filename)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{safe}.pdf"'
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
'''
    )
    p.write_text(t, encoding="utf-8")
    print("attachment helper added")
else:
    print("attachment helper exists")

# 2) Harden bid_draft_pdf view
vp = Path("buildwatch/views_tenders.py")
vt = vp.read_text(encoding="utf-8")
old = '''@login_required
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

new = '''@login_required
def bid_draft_pdf(request, listing_id):
    """
    GET /tenders/<listing_id>/bid/draft.pdf/
    Completed draft (or submitted) bid pack PDF: certificates + priced BOQ.
    """
    from accounts.misc_doc_pdf import build_pdf_bytes, pdf_attachment_response

    listing = get_object_or_404(TenderListing, pk=listing_id, is_published=True)
    org = get_active_organization(request)
    try:
        ua = _ensure_user_account(request, org)
    except Exception:
        ua = _get_user_account(request)

    # Prefer workspace/registration for this user's org; fall back to any Pioneer workspace
    workspace = None
    if org:
        workspace = BidWorkspace.objects.filter(tender=listing, organisation=org).first()
        if workspace is None and not BidderRegistration.objects.filter(
            tender=listing, organisation=org
        ).exists():
            messages.warning(
                request,
                "Register your interest before downloading the bid pack.",
            )
            return redirect("tender-detail", listing_id=listing_id)

    if workspace is None and ua is not None:
        # Staff / mismatched session: use the caller's prepared workspace if any
        workspace = BidWorkspace.objects.filter(
            tender=listing, prepared_by=ua
        ).first()

    if workspace is None and getattr(request.user, "is_staff", False):
        workspace = BidWorkspace.objects.filter(tender=listing).order_by("-started_at").first()

    if workspace is None:
        messages.error(
            request,
            "No bid workspace found for your organisation on this tender. "
            "Open the BOQ workspace first, then download the draft again.",
        )
        return redirect("bid-workspace", listing_id=listing_id)

    org = workspace.organisation
    try:
        ctx = _bid_pack_context(request, listing, workspace, org, ua)
        pdf = build_pdf_bytes("tenders/bid_draft_print.html", ctx)
    except Exception as exc:
        messages.error(request, f"Could not build bid PDF: {exc}")
        return redirect("bid-workspace", listing_id=listing_id)

    status = "DRAFT" if ctx["is_draft"] else "SUBMITTED"
    filename = "Bid_%s_%s_%s" % (
        str(listing.event.ref).replace("/", "-"),
        str(org.short_name or "bidder").replace(" ", "_"),
        status,
    )
    return pdf_attachment_response(pdf, filename)
'''

if "pdf_attachment_response" in vt and "No bid workspace found for your organisation" in vt:
    print("view already hardened")
else:
    if old not in vt:
        raise SystemExit("old bid_draft_pdf block not found")
    vt = vt.replace(old, new, 1)
    vp.write_text(vt, encoding="utf-8")
    print("view hardened")

# 3) Fix template CSS em units for xhtml2pdf
tp = Path("templates/tenders/bid_draft_print.html")
tt = tp.read_text(encoding="utf-8")
tt2 = tt.replace("0.06em", "0.5pt").replace("0.04em", "0.4pt")
# Safer project line
tt2 = tt2.replace(
    "<tr><th>Employer / project</th><td>{{ listing.event.project }}</td></tr>",
    "<tr><th>Employer / project</th><td>{{ listing.event.project|default:listing.event.description }}</td></tr>",
)
# Avoid cut filter path issues
tt2 = tt2.replace(
    "{% if c.document %}{{ c.document.name|cut:\"bids/self_assess/\" }}{% elif c.document_uploaded %}Uploaded{% else %}—{% endif %}",
    "{% if c.document %}Yes{% elif c.document_uploaded %}Uploaded{% else %}—{% endif %}",
)
tp.write_text(tt2, encoding="utf-8")
print("template fixed")

# 4) Make download open in new tab + download attribute hint
wp = Path("templates/tenders/bid_workspace.html")
wt = wp.read_text(encoding="utf-8")
wt = wt.replace(
    '''<a href="{% url 'bid-draft-pdf' listing.pk %}" class="bw-btn bw-btn--ghost"
             style="width:100%;justify-content:center;margin-bottom:10px;">
            Download draft bid PDF
          </a>''',
    '''<a href="{% url 'bid-draft-pdf' listing.pk %}" class="bw-btn bw-btn--ghost"
             style="width:100%;justify-content:center;margin-bottom:10px;"
             target="_blank" rel="noopener" download>
            Download draft bid PDF
          </a>'''
)
wt = wt.replace(
    '''<a href="{% url 'bid-draft-pdf' listing.pk %}" class="bw-btn bw-btn--ghost"
         style="width:100%;justify-content:center;margin-top:10px;">
        Download submitted bid PDF
      </a>''',
    '''<a href="{% url 'bid-draft-pdf' listing.pk %}" class="bw-btn bw-btn--ghost"
         style="width:100%;justify-content:center;margin-top:10px;"
         target="_blank" rel="noopener" download>
        Download submitted bid PDF
      </a>'''
)
wp.write_text(wt, encoding="utf-8")
print("workspace links updated")

compile(vp.read_text(encoding="utf-8"), "v", "exec")
compile(Path("accounts/misc_doc_pdf.py").read_text(encoding="utf-8"), "p", "exec")
print("compile ok")
