# ============================================================================
# buildwatch/views_subcontract_portal.py
#
# Token-authorised domestic / nominated sub-contractor portal:
# price authorised BOQ packages, draft PDF, submit quote to main,
# receive ack + inclusion + award notes.
# ============================================================================

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.tenant import branding_template_context, get_active_organization

from .models import (
    BidWorkspace,
    SubcontractArrangement,
    SubcontractQuoteLine,
    TenderBoqPackage,
    WorkspaceBillPrice,
)


def _arrangement_by_token(token):
    return get_object_or_404(SubcontractArrangement, invite_token=token)


def _portal_packages(arrangement):
    codes = set(arrangement.selected_codes())
    return list(
        TenderBoqPackage.objects.filter(tender=arrangement.tender)
        .prefetch_related("lines")
        .order_by("sort_order", "code")
    ) if not codes else list(
        TenderBoqPackage.objects.filter(
            tender=arrangement.tender,
            code__in=list(codes),
        )
        .prefetch_related("lines")
        .order_by("sort_order", "code")
    )


def _portal_sections(arrangement):
    codes = set(arrangement.selected_codes())
    packages = list(
        TenderBoqPackage.objects.filter(tender=arrangement.tender)
        .prefetch_related("lines")
        .order_by("sort_order", "code")
    )
    packages = [p for p in packages if p.code.upper() in codes]
    price_map = {ql.bill_ref: ql for ql in arrangement.quote_lines.all()}
    sections = []
    grand = Decimal("0")
    for pkg in packages:
        rows = []
        subtotal = Decimal("0")
        for line in pkg.lines.all():
            ql = price_map.get(line.bill_ref)
            rate = ql.unit_rate if ql else Decimal("0")
            amount = ql.amount if ql else Decimal("0")
            subtotal += amount
            rows.append({
                "line": line,
                "quote": ql,
                "rate": rate,
                "amount": amount,
            })
        grand += subtotal
        sections.append({
            "package": pkg,
            "rows": rows,
            "subtotal": subtotal,
            "line_count": len(rows),
        })
    return sections, grand


def _send_sub_portal_email(arrangement, *, subject, text_body, html_body=None, request=None):
    from accounts.emails import send_system_email

    return send_system_email(
        subject=subject,
        to=arrangement.sub_email,
        text_body=text_body,
        html_body=html_body,
        include_ceo_cc=False,
    )


def send_subcontract_portal_invite(arrangement, request=None):
    """Primary invite: portal hyperlink for authorised BOQ pricing."""
    from accounts.emails import _site_base_url

    base = _site_base_url(request)
    portal_url = f"{base}/tenders/subcontract/portal/{arrangement.invite_token}/"
    main_name = arrangement.main_organisation.name or arrangement.main_organisation.short_name
    ref = arrangement.tender.event.ref
    title = arrangement.tender.event.description or ref
    packages = ", ".join(arrangement.selected_codes()) or "Authorised packages"
    type_label = arrangement.get_arrangement_type_display()
    contractor_id = ""
    if arrangement.sub_organisation_id:
        contractor_id = arrangement.sub_organisation.org_code
    subject = f"BuildWatch - Price your subcontract BOQ - {ref}"
    text_body = (
        f"Dear {arrangement.sub_contact_name or arrangement.sub_company_name},\n\n"
        f"{main_name} invites you as {type_label.lower()} on tender {ref}.\n"
        f"{title}\n\n"
        f"Your contractor ID on BuildWatch: {contractor_id or '(being created)'}\n"
        f"Open your authorised portal to:\n"
        f"  1) View only your BOQ packages ({packages})\n"
        f"  2) Enter unit rates (BOM pricing)\n"
        f"  3) Download a draft quote PDF\n"
        f"  4) Submit your quote to the main contractor\n\n"
        f"Portal link (keep this private):\n{portal_url}\n\n"
        f"After you set your password, sign in and open My subcontracts "
        f"({base}/tenders/my-subcontracts/) to return to this work anytime "
        f"while the project is active.\n\n"
        f"After you submit, {main_name} will acknowledge your quote.\n\n"
        f"- BuildWatch\n"
    )
    html_body = (
        f"<p>Dear {arrangement.sub_contact_name or arrangement.sub_company_name},</p>"
        f"<p><strong>{main_name}</strong> invites you as "
        f"<strong>{type_label.lower()}</strong> on <strong>{ref}</strong>.</p>"
        f"<p>{title}</p>"
        f"<p>Contractor ID: <strong>{contractor_id or 'pending'}</strong></p>"
        f"<p>Authorised BOQ packages: <strong>{packages}</strong></p>"
        f"<ol>"
        f"<li>Enter unit rates on your packages</li>"
        f"<li>Download a draft quote PDF</li>"
        f"<li>Submit your quote to the main contractor</li>"
        f"</ol>"
        f"<p><a href=\"{portal_url}\" style=\"display:inline-block;padding:12px 18px;"
        f"background:#1A7A6E;color:#fff;text-decoration:none;border-radius:8px;"
        f"font-weight:600;\">Open subcontract portal</a></p>"
        f"<p style=\"font-size:0.85rem;color:#64748b;\">Or paste: {portal_url}</p>"
        f"<p style=\"font-size:0.85rem;color:#64748b;\">After onboarding, return via "
        f"<a href=\"{base}/tenders/my-subcontracts/\">My subcontracts</a>.</p>"
    )
    return _send_sub_portal_email(
        arrangement, subject=subject, text_body=text_body, html_body=html_body, request=request
    )


def notify_sub_quote_acknowledged(arrangement, request=None):
    from accounts.emails import _site_base_url

    base = _site_base_url(request)
    portal_url = f"{base}/tenders/subcontract/portal/{arrangement.invite_token}/"
    main_name = arrangement.main_organisation.name or arrangement.main_organisation.short_name
    ref = arrangement.tender.event.ref
    subject = f"BuildWatch  Quote acknowledged by {main_name}  {ref}"
    text_body = (
        f"Your subcontract quote (KES {arrangement.quote_total:,.2f}) for {ref} "
        f"has been acknowledged by {main_name}.\n\n"
        f"It will be carried in their main bid package to the employer when they submit.\n"
        f"Portal: {portal_url}\n"
    )
    return _send_sub_portal_email(arrangement, subject=subject, text_body=text_body)


def notify_sub_included_in_main_bid(arrangement, request=None):
    from accounts.emails import _site_base_url

    base = _site_base_url(request)
    portal_url = f"{base}/tenders/subcontract/portal/{arrangement.invite_token}/"
    main_name = arrangement.main_organisation.name or arrangement.main_organisation.short_name
    ref = arrangement.tender.event.ref
    subject = f"BuildWatch  Your quote is in the main bid pack  {ref}"
    text_body = (
        f"{main_name} has submitted the main bid package for {ref} to the employer.\n\n"
        f"Your subcontract quote (KES {arrangement.quote_total:,.2f}) was included "
        f"with that submission.\n\n"
        f"If {main_name} is awarded the contract, you will receive a further note that "
        f"execution (phase 2) is starting.\n\n"
        f"Portal: {portal_url}\n"
    )
    html_body = (
        f"<p><strong>{main_name}</strong> has submitted the main bid for "
        f"<strong>{ref}</strong> to the employer.</p>"
        f"<p>Your subcontract quote (<strong>KES {arrangement.quote_total:,.2f}</strong>) "
        f"was included in that package.</p>"
        f"<p><a href=\"{portal_url}\">Open portal</a></p>"
    )
    return _send_sub_portal_email(
        arrangement, subject=subject, text_body=text_body, html_body=html_body
    )


def notify_sub_award_execution_phase(arrangement, request=None):
    from accounts.emails import _site_base_url

    base = _site_base_url(request)
    portal_url = f"{base}/tenders/subcontract/portal/{arrangement.invite_token}/"
    main_name = arrangement.main_organisation.name or arrangement.main_organisation.short_name
    ref = arrangement.tender.event.ref
    subject = f"BuildWatch  {main_name} awarded  execution phase starting  {ref}"
    text_body = (
        f"{main_name} has been awarded the contract for {ref}.\n\n"
        f"Phase 2 (execution) is starting. Your domestic / nominated subcontract "
        f"works will proceed under the main contractor, with payment through the "
        f"main contractor's certificates (unless otherwise agreed).\n\n"
        f"Portal: {portal_url}\n"
    )
    return _send_sub_portal_email(arrangement, subject=subject, text_body=text_body)


def mark_subcontracts_included_on_main_submit(workspace, request=None):
    """When main submits bid, confirm to each acknowledged (or submitted) sub."""
    qs = SubcontractArrangement.objects.filter(
        workspace=workspace,
        tender=workspace.tender,
        main_organisation=workspace.organisation,
    ).exclude(status=SubcontractArrangement.CANCELLED).filter(
        quote_status__in=[
            SubcontractArrangement.QUOTE_ACKNOWLEDGED,
            SubcontractArrangement.QUOTE_SUBMITTED,
            SubcontractArrangement.QUOTE_INCLUDED,
        ]
    )
    now = timezone.now()
    for arr in qs:
        arr.quote_status = SubcontractArrangement.QUOTE_INCLUDED
        arr.included_in_main_bid_at = now
        arr.save(update_fields=["quote_status", "included_in_main_bid_at", "updated_at"])
        notify_sub_included_in_main_bid(arr, request=request)


def subcontract_portal(request, token):
    """
    GET/POST /tenders/subcontract/portal/<token>/
    Authorised BOQ pricing portal for the invited sub-contractor.
    """
    arrangement = _arrangement_by_token(token)
    if not arrangement.portal_open():
        messages.error(request, "This subcontract invitation has been cancelled.")
        return redirect("tender-detail", listing_id=arrangement.tender_id)

    listing = arrangement.tender
    # Opening the portal counts as acceptance of the invite
    if arrangement.status == SubcontractArrangement.INVITED:
        arrangement.status = SubcontractArrangement.ACCEPTED
        arrangement.accepted_at = timezone.now()
        arrangement.save(update_fields=["status", "accepted_at", "updated_at"])

    if request.method == "POST" and arrangement.quote_status not in {
        SubcontractArrangement.QUOTE_INCLUDED,
        SubcontractArrangement.AWARD_NOTED,
    }:
        action = (request.POST.get("action") or "save_prices").strip()
        codes = set(arrangement.selected_codes())
        packages = [
            p for p in TenderBoqPackage.objects.filter(tender=listing).prefetch_related("lines")
            if p.code.upper() in codes
        ]
        if action == "save_prices":
            for pkg in packages:
                for line in pkg.lines.all():
                    raw = (request.POST.get(f"rate_{line.bill_ref}") or "").strip().replace(",", "")
                    try:
                        rate = Decimal(raw) if raw else Decimal("0")
                    except (InvalidOperation, ValueError):
                        rate = Decimal("0")
                    ql, _ = SubcontractQuoteLine.objects.update_or_create(
                        arrangement=arrangement,
                        bill_ref=line.bill_ref,
                        defaults={
                            "package_code": pkg.code.upper(),
                            "description": (line.description or "")[:255],
                            "unit": line.unit or "",
                            "quantity": line.quantity or Decimal("0"),
                            "unit_rate": rate,
                        },
                    )
                    ql.save()
            from django.db.models import Sum
            total = arrangement.quote_lines.aggregate(s=Sum("amount")).get("s") or Decimal("0")
            arrangement.quote_total = total
            if arrangement.quote_status in {
                "",
                SubcontractArrangement.QUOTE_NONE,
                SubcontractArrangement.QUOTE_ACKNOWLEDGED,
            }:
                arrangement.quote_status = SubcontractArrangement.QUOTE_DRAFT
            elif not arrangement.quote_status:
                arrangement.quote_status = SubcontractArrangement.QUOTE_DRAFT
            arrangement.save(update_fields=["quote_total", "quote_status", "updated_at"])
            messages.success(request, "Prices saved. Download a draft PDF or submit to the main contractor.")
            return redirect("subcontract-portal", token=token)

        if action == "submit_quote":
            from django.db.models import Sum
            total = arrangement.quote_lines.aggregate(s=Sum("amount")).get("s") or Decimal("0")
            if total <= 0:
                messages.error(request, "Enter and save unit rates before submitting your quote.")
                return redirect("subcontract-portal", token=token)
            arrangement.quote_total = total
            arrangement.quote_status = SubcontractArrangement.QUOTE_SUBMITTED
            arrangement.quote_submitted_at = timezone.now()
            arrangement.save(
                update_fields=[
                    "quote_total",
                    "quote_status",
                    "quote_submitted_at",
                    "updated_at",
                ]
            )
            # Notify main contractor contact email if available
            main_email = (arrangement.main_organisation.email or "").strip()
            if main_email:
                from accounts.emails import send_system_email, _site_base_url
                base = _site_base_url(request)
                detail = (
                    f"{base}/tenders/{arrangement.tender_id}/bid/subcontract/{arrangement.pk}/"
                )
                send_system_email(
                    subject=f"BuildWatch  Subcontract quote received  {listing.event.ref}",
                    to=main_email,
                    text_body=(
                        f"{arrangement.sub_company_name} submitted a subcontract quote "
                        f"(KES {total:,.2f}) for {listing.event.ref}.\n\n"
                        f"Review and acknowledge:\n{detail}\n"
                    ),
                    include_ceo_cc=False,
                )
            messages.success(
                request,
                "Quote submitted to the main contractor. You will receive an email "
                "when they acknowledge it.",
            )
            return redirect("subcontract-portal", token=token)

    sections, grand = _portal_sections(arrangement)
    locked = arrangement.quote_status in {
        SubcontractArrangement.QUOTE_INCLUDED,
        SubcontractArrangement.AWARD_NOTED,
    }
    return render(
        request,
        "tenders/subcontract_portal.html",
        {
            "arrangement": arrangement,
            "listing": listing,
            "package_sections": sections,
            "grand_total": grand,
            "locked": locked,
            "can_edit": not locked and arrangement.quote_status != SubcontractArrangement.QUOTE_INCLUDED,
            **branding_template_context(request),
        },
    )


def subcontract_portal_draft_pdf(request, token):
    """Draft quote PDF for the authorised packages only."""
    from accounts.misc_doc_pdf import build_pdf_bytes, pdf_attachment_response
    from buildwatch.amount_words import amount_in_words

    arrangement = _arrangement_by_token(token)
    if not arrangement.portal_open():
        messages.error(request, "This invitation has been cancelled.")
        return redirect("tender-detail", listing_id=arrangement.tender_id)

    sections, grand = _portal_sections(arrangement)
    listing = arrangement.tender
    main_name = arrangement.main_organisation.name or arrangement.main_organisation.short_name
    ctx = {
        "arrangement": arrangement,
        "listing": listing,
        "package_sections": sections,
        "grand_total": grand,
        "amount_words": amount_in_words(grand),
        "main_name": main_name,
        "generated_at": timezone.now(),
    }
    pdf = build_pdf_bytes("tenders/subcontract_quote_print.html", ctx)
    fname = f"Subcontract_Quote_{listing.event.ref}_{arrangement.pk}"
    return pdf_attachment_response(pdf, fname)


@login_required
@require_POST
def subcontract_ack_quote(request, listing_id, pk):
    """Main contractor acknowledges sub quote and imports rates into main BOQ workspace."""
    from .views_tenders import _bid_subcontract_context, _get_user_account, _ensure_user_account

    ctx = _bid_subcontract_context(request, listing_id)
    if ctx is None:
        return redirect("tender-detail", listing_id=listing_id)

    arrangement = get_object_or_404(
        SubcontractArrangement,
        pk=pk,
        tender=ctx["listing"],
        main_organisation=ctx["org"],
    )
    if arrangement.quote_status not in {
        SubcontractArrangement.QUOTE_SUBMITTED,
        SubcontractArrangement.QUOTE_ACKNOWLEDGED,
    }:
        messages.error(request, "No submitted quote to acknowledge yet.")
        return redirect("bid-subcontract-detail", listing_id=listing_id, pk=pk)

    workspace = ctx["workspace"]
    # Import sub rates into main workspace bill prices for authorised packages
    for ql in arrangement.quote_lines.all():
        WorkspaceBillPrice.objects.update_or_create(
            workspace=workspace,
            bill_ref=ql.bill_ref,
            defaults={
                "description": ql.description,
                "unit": ql.unit,
                "quantity": ql.quantity,
                "unit_rate": ql.unit_rate,
                "package_code": ql.package_code,
            },
        )
    # Ensure packages are selected on main workspace
    selected = set(workspace.selected_codes())
    selected.update(arrangement.selected_codes())
    workspace.selected_package_codes = sorted(selected)
    # Pricing completeness: leave to main to re-save; mark incomplete if any zero
    from django.db.models import Sum
    total = workspace.bill_prices.aggregate(s=Sum("amount")).get("s") or Decimal("0")
    workspace.total_bid_amount = total
    workspace.save(update_fields=["selected_package_codes", "total_bid_amount"])

    arrangement.quote_status = SubcontractArrangement.QUOTE_ACKNOWLEDGED
    arrangement.quote_acknowledged_at = timezone.now()
    arrangement.quote_acknowledged_by = ctx["ua"]
    arrangement.save(
        update_fields=[
            "quote_status",
            "quote_acknowledged_at",
            "quote_acknowledged_by",
            "updated_at",
        ]
    )
    notify_sub_quote_acknowledged(arrangement, request=request)
    messages.success(
        request,
        f"Quote from {arrangement.sub_company_name} acknowledged. Rates imported into "
        f"your BOQ workspace. The sub-contractor has been emailed.",
    )
    return redirect("bid-subcontract-detail", listing_id=listing_id, pk=pk)


@login_required
@require_POST
def subcontract_notify_award(request, listing_id, pk):
    """Main notifies sub that they were awarded  execution phase starts."""
    from .views_tenders import _bid_subcontract_context

    ctx = _bid_subcontract_context(request, listing_id)
    if ctx is None:
        return redirect("tender-detail", listing_id=listing_id)

    arrangement = get_object_or_404(
        SubcontractArrangement,
        pk=pk,
        tender=ctx["listing"],
        main_organisation=ctx["org"],
    )
    arrangement.quote_status = SubcontractArrangement.AWARD_NOTED
    arrangement.award_noted_at = timezone.now()
    ok, err = notify_sub_award_execution_phase(arrangement, request=request)
    arrangement.award_note_sent = ok
    arrangement.save(
        update_fields=[
            "quote_status",
            "award_noted_at",
            "award_note_sent",
            "updated_at",
        ]
    )
    if ok:
        messages.success(request, "Award / execution-phase note emailed to the sub-contractor.")
    else:
        messages.warning(request, f"Marked award noted; email issue: {err}")
    return redirect("bid-subcontract-detail", listing_id=listing_id, pk=pk)


def subcontract_accept(request, token):
    """Legacy accept URL  redirect straight into the pricing portal."""
    arrangement = _arrangement_by_token(token)
    return redirect("subcontract-portal", token=arrangement.invite_token)
