# ============================================================================
# buildwatch/views_tenders.py
#
# DOMAIN: Tender Exchange — Publisher side + Bidder side
#
# URL prefix: /tenders/
#
# Public views (no login):
#   tender_list          GET /tenders/
#   tender_detail        GET /tenders/<id>/
#
# Authenticated views:
#   tender_register      POST /tenders/<id>/register/
#   tender_boq_download  GET  /tenders/<id>/boq/
#   bid_workspace        GET/POST /tenders/<id>/bid/
#   bid_self_assess      GET/POST /tenders/<id>/bid/self-assess/
#   bid_draft_pdf        GET  /tenders/<id>/bid/draft.pdf/
#   bid_submit           POST /tenders/<id>/bid/submit/
#   my_bids              GET /tenders/my-bids/
#   tender_alerts        GET/POST /tenders/alerts/
#   tender_publish       GET/POST /tenders/publish/
#   tender_manage        GET /tenders/manage/<id>/
#   tender_addendum      POST /tenders/manage/<id>/addendum/
# ============================================================================

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, FileResponse, Http404
from django.utils import timezone
from django.db.models import Q, Count
from django.views.decorators.http import require_POST
from decimal import Decimal

from .models import (
    TenderListing, TenderInvitation, TenderAddendum, TenderAlert,
    BidderRegistration, BidWorkspace, SelfAssessmentCheck, WorkspaceBillPrice,
    EvaluationEvent, MandatoryRequirement, Submission, AuditLedger, Country,
    InfraProject, TenderBoqPackage, TenderBoqLine, SubcontractArrangement,
)
from accounts.models import Organization, UserAccount
from accounts.tenant import (
    get_active_organization,
    branding_template_context,
    get_exchange_persona,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _procurement_requirements(listing=None):
    """Active procurement MRs, preferably matching the tender country."""
    qs = MandatoryRequirement.objects.filter(
        context__in=[
            MandatoryRequirement.PROCUREMENT,
            MandatoryRequirement.ALL,
        ],
        is_active=True,
    )
    country = getattr(listing, 'country', None) if listing else None
    if country is not None:
        scoped = qs.filter(Q(country=country) | Q(country__isnull=True))
        if scoped.exists():
            return scoped.order_by('order', 'code')
    return qs.order_by('order', 'code')


def _ensure_bidder_workspace(request, listing):
    """
    Ensure contractor org has interest registration + private bid workspace.
    Returns (org, ua, registration, workspace) or raises PermissionError.
    """
    org = get_active_organization(request)
    if org is None:
        raise PermissionError('Organisation account required to upload documents.')
    try:
        ua = _ensure_user_account(request, org)
    except Exception as exc:
        raise PermissionError(f'User profile required: {exc}') from exc
    if get_exchange_persona(org=org, request=request) != 'contractor':
        raise PermissionError(
            'Only contractor organisations can upload mandatory requirement documents.'
        )
    reg, _ = BidderRegistration.objects.get_or_create(
        tender=listing,
        organisation=org,
        defaults={'registered_by': ua},
    )
    workspace, _ = BidWorkspace.objects.get_or_create(
        tender=listing,
        organisation=org,
        defaults={'prepared_by': ua},
    )
    return org, ua, reg, workspace


def _sync_self_assessment_checks(workspace, requirements):
    """Create missing SelfAssessmentCheck rows for each MR."""
    for req in requirements:
        SelfAssessmentCheck.objects.get_or_create(
            workspace=workspace,
            mr_ref=req.code,
            defaults={
                'requirement': req,
                'description': req.description,
                'self_result': SelfAssessmentCheck.PENDING,
            },
        )


def _save_self_assessment_uploads(request, workspace, requirements):
    """Persist pass/fail + certificate files from POST; update workspace gate."""
    for req in requirements:
        result = request.POST.get(
            f'result_{req.code}', SelfAssessmentCheck.PENDING
        )
        notes = request.POST.get(f'notes_{req.code}', '')
        doc = request.FILES.get(f'doc_{req.code}')
        check = SelfAssessmentCheck.objects.get(
            workspace=workspace, mr_ref=req.code
        )
        # Uploading a certificate implies the contractor asserts compliance
        if doc and result == SelfAssessmentCheck.PENDING:
            result = SelfAssessmentCheck.PASS
        check.self_result = result
        check.notes = notes
        if doc:
            check.document = doc
            check.document_uploaded = True
        check.save()

    return _refresh_self_assessment_gate(workspace)


def _save_single_mr_upload(request, workspace, req):
    """Save one MR certificate from an inline upload form."""
    check, _ = SelfAssessmentCheck.objects.get_or_create(
        workspace=workspace,
        mr_ref=req.code,
        defaults={
            'requirement': req,
            'description': req.description,
            'self_result': SelfAssessmentCheck.PENDING,
        },
    )
    doc = (
        request.FILES.get('document')
        or request.FILES.get(f'doc_{req.code}')
    )
    if not doc:
        raise ValueError('Choose a certificate file to upload.')
    check.document = doc
    check.document_uploaded = True
    check.self_result = SelfAssessmentCheck.PASS
    check.requirement = req
    check.description = req.description
    check.save()
    _refresh_self_assessment_gate(workspace)
    return check


def _refresh_self_assessment_gate(workspace):
    all_checks = workspace.self_checks.all()
    has_fail = all_checks.filter(
        self_result=SelfAssessmentCheck.FAIL
    ).exists()
    has_pending = all_checks.filter(
        self_result=SelfAssessmentCheck.PENDING
    ).exists()
    workspace.self_assessment_passed = (
        all_checks.exists() and not has_fail and not has_pending
    )
    if workspace.self_assessment_passed:
        workspace.status = BidWorkspace.SELF_CHECKED
    workspace.save(update_fields=['self_assessment_passed', 'status'])
    return all_checks


MR14_CODE = "MR-PROC-KE-14"
MR14_RFQ_TEXT = (
    "Domestic Contractor's Agreement — A duly signed and stamped Agreement not earlier than "
    "1 month between the Electrical Services Sub-Contractor and the main contractor stating "
    "that if the Main Contractor is awarded the contract, they shall work with the firm as "
    "their domestic sub-contractor (Not necessary if Main Contractor is also registered for "
    "all Electrical Services Works)."
)


def _mr14_requirement():
    return MandatoryRequirement.objects.filter(code=MR14_CODE).first()


def _link_mr14_from_subcontract(workspace, arrangement):
    """
    Bid-prep: lodging the signed domestic agreement satisfies MR14 on the
    certificate checklist (same workspace gate used before bid submit).
    """
    if not arrangement or not arrangement.agreement_file:
        return None
    req = _mr14_requirement()
    check, _ = SelfAssessmentCheck.objects.get_or_create(
        workspace=workspace,
        mr_ref=MR14_CODE,
        defaults={
            "requirement": req,
            "description": (req.description if req else MR14_RFQ_TEXT)[:500],
            "self_result": SelfAssessmentCheck.PENDING,
        },
    )
    # Point at the same stored file path used for the subcontract record
    check.document = arrangement.agreement_file
    check.document_uploaded = True
    check.self_result = SelfAssessmentCheck.PASS
    if req is not None:
        check.requirement = req
        check.description = (req.description or MR14_RFQ_TEXT)[:500]
    check.notes = (
        f"Bid-prep MR14 · {arrangement.get_arrangement_type_display()} with "
        f"{arrangement.sub_company_name} · packages: "
        f"{', '.join(arrangement.selected_codes()) or '—'}"
    )[:300]
    check.save()
    _refresh_self_assessment_gate(workspace)
    return check


def _mark_mr14_not_applicable(workspace, reason=""):
    """RFQ exception: main contractor registered for all Electrical Services Works."""
    req = _mr14_requirement()
    check, _ = SelfAssessmentCheck.objects.get_or_create(
        workspace=workspace,
        mr_ref=MR14_CODE,
        defaults={
            "requirement": req,
            "description": (req.description if req else MR14_RFQ_TEXT)[:500],
            "self_result": SelfAssessmentCheck.PENDING,
        },
    )
    note = (
        reason.strip()
        or "N/A — Main Contractor registered for all Electrical Services Works (RFQ MR14 exception)"
    )
    check.self_result = SelfAssessmentCheck.PASS
    check.document_uploaded = True
    check.notes = note[:300]
    if req is not None:
        check.requirement = req
        check.description = (req.description or MR14_RFQ_TEXT)[:500]
    check.save()
    _refresh_self_assessment_gate(workspace)
    return check


def _mr_progress(workspace, requirements):
    """Return (done, total) for uploaded / satisfied MR certificates — never gates BOQ."""
    total = len(requirements)
    if total == 0:
        return 0, 0
    if workspace is None:
        return 0, total
    codes = [r.code for r in requirements]
    done = workspace.self_checks.filter(
        mr_ref__in=codes,
    ).filter(
        Q(document_uploaded=True) | Q(self_result=SelfAssessmentCheck.PASS)
    ).distinct().count()
    return done, total


def _get_user_account(request):
    """Returns UserAccount for logged-in user, or None."""
    try:
        return request.user.useraccount
    except Exception:
        pass
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return None
    # Fallback: match by email and link the login
    email = (getattr(user, 'email', '') or '').strip()
    if email:
        ua = UserAccount.objects.filter(email__iexact=email).first()
        if ua is not None:
            if ua.user_id is None:
                ua.user = user
                ua.save(update_fields=['user'])
            return ua
    return None


def _ensure_user_account(request, org):
    """
    Resolve or create a UserAccount so bidder FKs (registered_by / prepared_by)
    never receive NULL.
    """
    ua = _get_user_account(request)
    if ua is not None:
        if org is not None and ua.organization_id is None:
            ua.organization = org
            ua.save(update_fields=['organization'])
        return ua

    user = request.user
    email = (getattr(user, 'email', '') or f'{user.username}@pioneer.local').strip()
    base_staff = f"USR-{user.id}"
    staff_no = base_staff
    n = 1
    while UserAccount.objects.filter(staff_no=staff_no).exists():
        n += 1
        staff_no = f"{base_staff}-{n}"

    ua = UserAccount.objects.create(
        user=user,
        staff_no=staff_no,
        first_name=getattr(user, 'first_name', '') or user.username,
        last_name=getattr(user, 'last_name', '') or '',
        designation='Authorised user',
        contact_address='',
        phone='',
        email=email,
        organization=org,
    )
    return ua


def _tender_visible_to(listing, request):
    """Returns True if this listing is visible to the current visitor."""
    if listing.visibility == TenderListing.PUBLIC:
        return True
    if not request.user.is_authenticated:
        return False
    ua = _get_user_account(request)
    if not ua:
        return False
    if listing.visibility == TenderListing.PRIVATE:
        org = get_active_organization(request)
        return TenderInvitation.objects.filter(
            tender=listing, organisation=org
        ).exists()
    # RESTRICTED — same country as the tender
    if listing.visibility == TenderListing.RESTRICTED:
        org = get_active_organization(request)
        return (listing.country is None or
                org.contact_address or True)  # TODO: org.country FK
    return False


# ── PUBLIC VIEWS ─────────────────────────────────────────────────────────────

def tender_list(request):
    """
    GET /tenders/
    Public tender exchange listing. No login required to browse.
    Supports filtering by type, sector, country, funding, closing soon.
    """
    qs = TenderListing.objects.filter(
        is_published=True,
        event__status=EvaluationEvent.STATUS_OPEN,
    ).select_related('event', 'event__project', 'country', 'created_by')

    # ── Filters from GET params ───────────────────────────────────────────
    tender_type  = request.GET.get('type', '')
    sector       = request.GET.get('sector', '')
    country_code = request.GET.get('country', '')
    funding      = request.GET.get('funding', '')
    closing_soon = request.GET.get('closing_soon', '')
    search       = request.GET.get('q', '').strip()

    if tender_type:
        qs = qs.filter(tender_type=tender_type)
    if sector:
        qs = qs.filter(event__project__sector=sector)
    if country_code:
        qs = qs.filter(country__code=country_code)
    if funding:
        qs = qs.filter(funding_source=funding)
    if closing_soon:
        from datetime import timedelta
        cutoff = timezone.now() + timedelta(days=7)
        qs = qs.filter(event__closing_date__lte=cutoff,
                       event__closing_date__gte=timezone.now())
    if search:
        qs = qs.filter(
            Q(event__ref__icontains=search) |
            Q(event__description__icontains=search) |
            Q(summary__icontains=search) |
            Q(county_region__icontains=search)
        )

    # ── Visibility filter ─────────────────────────────────────────────────
    # Public listings always shown; private only if logged in and invited
    if not request.user.is_authenticated:
        qs = qs.filter(visibility=TenderListing.PUBLIC)

    # ── Stats for sidebar ─────────────────────────────────────────────────
    total_active  = TenderListing.objects.filter(
        is_published=True,
        event__status=EvaluationEvent.STATUS_OPEN
    ).count()
    closing_week  = TenderListing.objects.filter(
        is_published=True,
        event__status=EvaluationEvent.STATUS_OPEN,
        event__closing_date__lte=timezone.now() + timezone.timedelta(days=7),
        event__closing_date__gte=timezone.now(),
    ).count()

    countries = Country.objects.filter(is_active=True).order_by('name')

    ctx = {
        'listings':      qs.order_by('-published_at'),
        'total_active':  total_active,
        'closing_week':  closing_week,
        'countries':     countries,
        'filter_type':   tender_type,
        'filter_sector': sector,
        'filter_country':country_code,
        'filter_funding':funding,
        'filter_closing':closing_soon,
        'search':        search,
        'TENDER_TYPES':  TenderListing.TENDER_TYPE_CHOICES,
        'FUNDING_TYPES': TenderListing.FUNDING_CHOICES,
        'SECTORS': [
            ('ROADS',     'Roads & Bridges'),
            ('BUILDINGS', 'Buildings'),
            ('WATER',     'Water & Sanitation'),
            ('ENERGY',    'Energy'),
            ('ICT',       'ICT Infrastructure'),
            ('OTHER',     'Other'),
        ],
    }
    if request.user.is_authenticated:
        ctx.update(branding_template_context(request))
    return render(request, 'tenders/tender_list.html', ctx)


def tender_detail(request, listing_id):
    """
    GET /tenders/<listing_id>/
    Tender detail page — public. BOQ download and bid workspace require login.
    Contractors may POST certificate uploads against mandatory requirements.
    Increments view_count on GET.
    """
    listing = get_object_or_404(
        TenderListing,
        pk=listing_id,
        is_published=True,
    )

    if not _tender_visible_to(listing, request):
        messages.warning(request,
            'This tender is by invitation only. '
            'Contact the procuring entity to request an invitation.')
        return redirect('tender-list')

    requirements = list(_procurement_requirements(listing))

    # Registration status for logged-in bidder
    bidder_reg = None
    workspace = None
    is_invited = False
    can_upload_mr = False
    mr_rows = []

    if request.user.is_authenticated:
        org = get_active_organization(request)
        persona = get_exchange_persona(org=org, request=request)
        try:
            bidder_reg = BidderRegistration.objects.get(
                tender=listing, organisation=org
            )
        except BidderRegistration.DoesNotExist:
            pass
        try:
            workspace = BidWorkspace.objects.get(
                tender=listing, organisation=org
            )
        except BidWorkspace.DoesNotExist:
            pass
        is_invited = TenderInvitation.objects.filter(
            tender=listing, organisation=org
        ).exists()

        # Signed-in contractors can upload while the tender is open.
        # First upload also registers interest + creates the bid workspace.
        can_upload_mr = (
            persona == 'contractor'
            and listing.event.is_open
        )

        # Inline single-MR upload (or legacy bulk save)
        if request.method == 'POST' and can_upload_mr:
            try:
                _, _, bidder_reg, workspace = _ensure_bidder_workspace(
                    request, listing
                )
            except PermissionError as exc:
                messages.error(request, str(exc))
                return redirect('tender-detail', listing_id=listing_id)

            _sync_self_assessment_checks(workspace, requirements)
            mr_code = (request.POST.get('mr_code') or '').strip()
            if mr_code:
                req = next((r for r in requirements if r.code == mr_code), None)
                if req is None:
                    messages.error(request, 'Unknown mandatory requirement.')
                    return redirect('tender-detail', listing_id=listing_id)
                try:
                    check = _save_single_mr_upload(request, workspace, req)
                    messages.success(
                        request,
                        f'{check.mr_ref} certificate saved.',
                    )
                except ValueError as exc:
                    messages.error(request, str(exc))
                return redirect('tender-detail', listing_id=listing_id)

            all_checks = _save_self_assessment_uploads(
                request, workspace, requirements
            )
            uploaded = sum(
                1 for req in requirements
                if request.FILES.get(f'doc_{req.code}')
            )
            if workspace.self_assessment_passed:
                messages.success(
                    request,
                    'Mandatory documents saved. All requirements marked complete.',
                )
            elif uploaded:
                messages.success(
                    request,
                    f'{uploaded} document(s) uploaded.',
                )
            else:
                pending = all_checks.filter(
                    self_result__in=[
                        SelfAssessmentCheck.FAIL,
                        SelfAssessmentCheck.PENDING,
                    ]
                ).count()
                messages.warning(
                    request,
                    f'Saved. {pending} requirement(s) still pending or failing.',
                )
            return redirect('tender-detail', listing_id=listing_id)

        if workspace is not None and requirements:
            _sync_self_assessment_checks(workspace, requirements)
            checks = {
                c.mr_ref: c
                for c in workspace.self_checks.filter(
                    mr_ref__in=[r.code for r in requirements]
                )
            }
            for i, req in enumerate(requirements, 1):
                mr_rows.append({
                    'index': i,
                    'req': req,
                    'check': checks.get(req.code),
                })
        else:
            for i, req in enumerate(requirements, 1):
                mr_rows.append({
                    'index': i,
                    'req': req,
                    'check': None,
                })
    else:
        for i, req in enumerate(requirements, 1):
            mr_rows.append({
                'index': i,
                'req': req,
                'check': None,
            })

    # Increment view count on GET only
    if request.method == 'GET':
        TenderListing.objects.filter(pk=listing_id).update(
            view_count=listing.view_count + 1
        )

    addenda = listing.addenda.order_by('addendum_no')
    mr_done, mr_total = _mr_progress(workspace, requirements)

    ctx = {
        'listing': listing,
        'addenda': addenda,
        'bidder_reg': bidder_reg,
        'workspace': workspace,
        'is_invited': is_invited,
        'can_bid': listing.event.is_open,
        'requirements': requirements,
        'mr_rows': mr_rows,
        'can_upload_mr': can_upload_mr,
        'mr_done_count': mr_done,
        'mr_total': mr_total,
        'mr_progress_pct': int((mr_done * 100) / mr_total) if mr_total else 0,
    }
    if request.user.is_authenticated:
        ctx.update(branding_template_context(request))
    return render(request, 'tenders/tender_detail.html', ctx)


# ── BIDDER VIEWS (login required) ────────────────────────────────────────────

@login_required
@require_POST
def tender_register(request, listing_id):
    """
    POST /tenders/<listing_id>/register/
    Contractor registers interest — required before BOQ download or bid workspace.
    """
    listing = get_object_or_404(TenderListing, pk=listing_id, is_published=True)
    org = get_active_organization(request)
    ua = _get_user_account(request)

    if not listing.event.is_open:
        messages.error(request, 'This tender has closed.')
        return redirect('tender-detail', listing_id=listing_id)

    if org is None:
        messages.error(
            request,
            'No organisation is linked to your login. Contact your administrator.',
        )
        return redirect('tender-detail', listing_id=listing_id)

    try:
        ua = _ensure_user_account(request, org)
    except Exception as exc:
        messages.error(
            request,
            f'Could not resolve your user profile: {exc}',
        )
        return redirect('tender-detail', listing_id=listing_id)

    try:
        reg, created = BidderRegistration.objects.get_or_create(
            tender=listing,
            organisation=org,
            defaults={'registered_by': ua},
        )
    except Exception as exc:
        messages.error(
            request,
            f'Could not register interest: {exc}',
        )
        return redirect('tender-detail', listing_id=listing_id)

    # Ensure private bid workspace exists so BOQ pricing is available immediately
    BidWorkspace.objects.get_or_create(
        tender=listing,
        organisation=org,
        defaults={'prepared_by': ua},
    )

    if created:
        messages.success(
            request,
            f'You are registered for {listing.event.ref}. '
            f'Opening the BOQ workspace.',
        )
    else:
        messages.info(request, 'You are already registered for this tender.')

    # Prefer BOQ file download when available; otherwise open the workspace
    if listing.boq_document:
        return redirect('tender-boq-download', listing_id=listing_id)
    return redirect('bid-workspace', listing_id=listing_id)


@login_required
def tender_boq_download(request, listing_id):
    """
    GET /tenders/<listing_id>/boq/
    Serve the BOQ document. Requires registration. Records download.
    """
    listing = get_object_or_404(TenderListing, pk=listing_id, is_published=True)
    org     = get_active_organization(request)

    try:
        reg = BidderRegistration.objects.get(tender=listing, organisation=org)
    except BidderRegistration.DoesNotExist:
        messages.error(request,
            'You must register interest before downloading the BOQ.')
        return redirect('tender-detail', listing_id=listing_id)

    if not listing.boq_document:
        messages.warning(request, 'BOQ document not yet uploaded by the procuring entity.')
        return redirect('tender-detail', listing_id=listing_id)

    reg.record_boq_download()
    return FileResponse(
        listing.boq_document.open('rb'),
        as_attachment=True,
        filename=f"BOQ_{listing.event.ref.replace('/', '_')}.pdf",
    )


@login_required


def _bid_pack_context(request, listing, workspace, org, ua):
    """Shared context for RFQ-compliant draft/submitted bid PDF pack."""
    from buildwatch.amount_words import amount_in_words

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
    bill_summary = []
    grand_total = Decimal("0")
    for pkg in packages:
        included = pkg.code.upper() in selected
        rows = []
        subtotal = Decimal("0")
        line_count = pkg.lines.count()
        if included:
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
        bill_summary.append({
            "code": pkg.code,
            "title": pkg.title,
            "line_count": line_count,
            "included": included,
            "subtotal": subtotal if included else Decimal("0"),
        })

    prepared_by_name = ""
    if ua:
        prepared_by_name = (
            getattr(ua, "get_full_name", lambda: "")()
            or getattr(ua, "username", "")
            or str(ua)
        )

    self_checks = list(workspace.self_checks.order_by("mr_ref"))
    mr_pass = sum(1 for c in self_checks if c.self_result == SelfAssessmentCheck.PASS)
    mr_docs = sum(1 for c in self_checks if c.document or c.document_uploaded)
    mr_total = len(self_checks)
    if mr_total == 0:
        mr_summary = "No MR rows — complete Certificates before submit."
    elif workspace.self_assessment_passed:
        mr_summary = "Self-assessment PASSED (%s/%s) · documents attached %s/%s." % (
            mr_pass, mr_total, mr_docs, mr_total,
        )
    else:
        mr_summary = "Self-assessment incomplete (%s PASS of %s) · documents %s/%s." % (
            mr_pass, mr_total, mr_docs, mr_total,
        )

    priced_lines = workspace.bill_prices.filter(amount__gt=0).count()
    rfq_checklist = [
        {
            "label": "Completed Form of Tender with grand total (figures and words)",
            "status": "Included (Section B)" if grand_total > 0 else "Incomplete — enter BOQ rates",
        },
        {
            "label": "Fully priced Bills of Quantities with unit rates and amounts",
            "status": "Included (Section F) — %s priced lines" % priced_lines
            if priced_lines else "Incomplete — no priced lines yet",
        },
        {
            "label": "Mandatory Requirement documents MR1–MR14 (certified copies)",
            "status": "Checklist Section D — %s/%s docs attached" % (mr_docs, mr_total or 14),
        },
        {
            "label": "Technical Schedules (Section III) — equipment make/model/catalogue",
            "status": "Attach separately (not generated in this pack)",
        },
        {
            "label": "Manufacturer brochures/catalogues (highlighted models)",
            "status": "Attach separately (not generated in this pack)",
        },
        {
            "label": "Personnel forms PER-1 and PER-2",
            "status": "Attach separately (not generated in this pack)",
        },
        {
            "label": "Experience forms EXP-3.4 / EXP-4.1 / EXP-4.2a / EXP-4.2b",
            "status": "Attach separately (not generated in this pack)",
        },
        {
            "label": "Form EQU — Equipment Schedule with evidence",
            "status": "Attach separately (not generated in this pack)",
        },
    ]

    is_draft = workspace.status != BidWorkspace.SUBMITTED
    currency_words = "Kenya Shillings" if (listing.currency or "").upper() in ("", "KES") else listing.currency
    ctx = {
        "listing": listing,
        "workspace": workspace,
        "org": org,
        "self_checks": self_checks,
        "package_sections": package_sections,
        "category_summary": category_summary,
        "bill_summary": bill_summary,
        "grand_total": grand_total,
        "grand_total_words": amount_in_words(grand_total, currency=currency_words),
        "is_draft": is_draft,
        "prepared_by_name": prepared_by_name,
        "signatory_designation": "",
        "vat_certificate_no": getattr(org, "tax_pin", "") or "",
        "generated_at": timezone.now(),
        "tender_title": "Proposed Completion of Isiolo Stadium — Electrical Services",
        "employer_name": "Sports Kenya Ltd (The Director General)",
        "employer_address": "P.O. Box Private Bag, Kasarani, Nairobi, Kenya · Tel: +254 20 2390500/1",
        "closing_note": "10th July 2025 at 11:00 HRS (per RFQ)",
        "partial_offer": bool(packages) and len(selected_packages) < len(packages),
        "rfq_checklist": rfq_checklist,
        "mr_summary": mr_summary,
        **branding_template_context(request),
    }
    return ctx


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

def bid_workspace(request, listing_id):
    """
    GET/POST /tenders/<listing_id>/bid/
    Contractor's private bid preparation workspace.
    Supports multi-select of BOQ packages (partial or all) then rate entry.
    """
    listing = get_object_or_404(TenderListing, pk=listing_id, is_published=True)
    org = get_active_organization(request)
    try:
        ua = _ensure_user_account(request, org)
    except Exception:
        ua = _get_user_account(request)

    if not BidderRegistration.objects.filter(
            tender=listing, organisation=org).exists():
        messages.warning(request,
            'Register your interest before accessing the bid workspace.')
        return redirect('tender-detail', listing_id=listing_id)

    if not listing.event.is_open:
        messages.error(request, 'This tender has closed. Bid workspace is read-only.')

    if ua is None:
        messages.error(request, 'Your user profile could not be resolved.')
        return redirect('tender-detail', listing_id=listing_id)

    workspace, _ = BidWorkspace.objects.get_or_create(
        tender=listing,
        organisation=org,
        defaults={'prepared_by': ua},
    )

    packages = list(
        TenderBoqPackage.objects.filter(tender=listing)
        .prefetch_related('lines')
        .order_by('sort_order', 'code')
    )

    if request.method == 'POST' and listing.event.is_open and workspace.status != BidWorkspace.SUBMITTED:
        action = (request.POST.get('action') or 'save_prices').strip()

        if action == 'set_boq_mode':
            can_switch = (
                getattr(request.user, 'is_staff', False)
                or (ua and listing.created_by_id == getattr(ua, 'pk', None))
                or (
                    org
                    and getattr(listing.event, 'project', None)
                    and listing.event.project.owner_org_id == org.pk
                )
            )
            if not can_switch:
                messages.error(
                    request,
                    'Only the employer (or staff) can switch BOQ input source.',
                )
                return redirect('bid-workspace', listing_id=listing_id)
            mode = (request.POST.get('boq_input_mode') or '').strip().upper()
            try:
                stats = _apply_boq_input_mode(listing, mode)
            except Exception as exc:
                messages.error(request, f'Could not switch BOQ source: {exc}')
                return redirect('bid-workspace', listing_id=listing_id)
            label = 'A (Hardwired)' if mode == TenderListing.BOQ_HARDWIRED else 'B (RFQ PDF auto)'
            messages.success(
                request,
                f'Switched to {label}: {stats["categories"]} categories, '
                f'{stats["lines"]} lines. Re-select categories to price.',
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

        if action == 'select_packages':
            selected = [
                c.strip().upper()
                for c in request.POST.getlist('package_code')
                if c.strip()
            ]
            valid = {p.code.upper() for p in packages}
            selected = [c for c in selected if c in valid]
            if not selected and packages:
                messages.error(request, 'Select at least one BOQ component to bid.')
                return redirect('bid-workspace', listing_id=listing_id)
            workspace.selected_package_codes = selected
            # Drop priced lines for deselected packages
            WorkspaceBillPrice.objects.filter(workspace=workspace).exclude(
                package_code__in=selected
            ).delete()
            workspace.pricing_complete = False
            workspace.save(update_fields=[
                'selected_package_codes', 'pricing_complete',
            ])
            messages.success(
                request,
                f'{len(selected)} component(s) selected. Enter unit rates below.',
            )
            return redirect('bid-workspace', listing_id=listing_id)

        if action == 'start_subcontract':
            import secrets

            required = (request.POST.get('subcontract_required') or '').strip().upper()
            if required == 'NO':
                _mark_mr14_not_applicable(workspace)
                messages.success(
                    request,
                    'Subcontracting not required — MR14 marked N/A '
                    '(main contractor registered for all Electrical Services Works).',
                )
                return redirect('bid-workspace', listing_id=listing_id)

            if required != 'YES':
                messages.error(request, 'Choose whether subcontracting is required.')
                return redirect('bid-workspace', listing_id=listing_id)

            arr_type = (request.POST.get('arrangement_type') or '').strip().upper()
            # Filter 2 Type A = domestic, Type B = nominated
            if arr_type in {'A', 'TYPE_A', 'DOMESTIC'}:
                arr_type = SubcontractArrangement.DOMESTIC
            elif arr_type in {'B', 'TYPE_B', 'NOMINATED'}:
                arr_type = SubcontractArrangement.NOMINATED
            if arr_type not in {
                SubcontractArrangement.DOMESTIC,
                SubcontractArrangement.NOMINATED,
            }:
                messages.error(request, 'Select Type A (Domestic) or Type B (Nominated).')
                return redirect('bid-workspace', listing_id=listing_id)

            company = (request.POST.get('sub_company_name') or '').strip()
            email = (request.POST.get('sub_email') or '').strip().lower()
            contact = (request.POST.get('sub_contact_name') or '').strip()
            phone = (request.POST.get('sub_phone') or '').strip()
            notes = (request.POST.get('notes') or '').strip()
            selected = [
                c.strip().upper()
                for c in request.POST.getlist('sub_package_code')
                if c.strip()
            ]
            valid = {p.code.upper() for p in packages}
            selected = [c for c in selected if c in valid]
            if not company:
                messages.error(request, 'Sub-contractor company name is required.')
                return redirect('bid-workspace', listing_id=listing_id)
            if not email or '@' not in email:
                messages.error(request, 'A valid sub-contractor email is required.')
                return redirect('bid-workspace', listing_id=listing_id)
            if not selected:
                messages.error(
                    request,
                    'Select at least one BOQ category to subcontract.',
                )
                return redirect('bid-workspace', listing_id=listing_id)

            is_nominated = arr_type == SubcontractArrangement.NOMINATED
            arrangement = SubcontractArrangement.objects.create(
                tender=listing,
                workspace=workspace,
                main_organisation=org,
                arrangement_type=arr_type,
                status=SubcontractArrangement.INVITED,
                package_codes=selected,
                sub_company_name=company,
                sub_contact_name=contact,
                sub_email=email,
                sub_phone=phone,
                notes=notes,
                payment_via_main=True,
                approval_by_consultant=is_nominated,
                invite_token=secrets.token_urlsafe(32),
                invited_by=ua,
                invited_at=timezone.now(),
            )
            ok, err = _send_subcontract_invite_email(arrangement, request)
            arrangement.invite_email_sent = ok
            arrangement.invite_email_error = (err or '')[:400]
            arrangement.save(
                update_fields=['invite_email_sent', 'invite_email_error', 'updated_at']
            )
            if ok:
                messages.success(
                    request,
                    f'Portal invitation sent to {email}. Sub can price the selected '
                    f'categories, draft PDF, and submit their quote for your ack.',
                )
            else:
                messages.warning(
                    request,
                    f'Arrangement created, but email could not be sent: {err}. '
                    f'Resend from the arrangement page.',
                )
            return redirect(
                'bid-subcontract-detail', listing_id=listing_id, pk=arrangement.pk
            )

        # save_prices
        selected = workspace.selected_codes()
        if packages and not selected:
            messages.error(request, 'Select BOQ components before saving prices.')
            return redirect('bid-workspace', listing_id=listing_id)

        bill_refs = request.POST.getlist('bill_ref')
        for bill_ref in bill_refs:
            desc = request.POST.get(f'desc_{bill_ref}', '')
            unit = request.POST.get(f'unit_{bill_ref}', '')
            pkg = request.POST.get(f'pkg_{bill_ref}', '')
            qty_raw = request.POST.get(f'qty_{bill_ref}', '0').replace(',', '')
            rate_raw = request.POST.get(f'rate_{bill_ref}', '0').replace(',', '')
            try:
                qty = Decimal(qty_raw)
                rate = Decimal(rate_raw)
            except Exception:
                continue
            if qty <= 0:
                continue
            WorkspaceBillPrice.objects.update_or_create(
                workspace=workspace,
                bill_ref=bill_ref,
                defaults={
                    'description': desc,
                    'unit': unit or 'Nr',
                    'quantity': qty,
                    'unit_rate': rate,
                    'package_code': pkg,
                },
            )

        # Completeness: every line in every selected package must have amount > 0
        complete = True
        if selected:
            for pkg in packages:
                if pkg.code.upper() not in selected:
                    continue
                for line in pkg.lines.all():
                    bp = WorkspaceBillPrice.objects.filter(
                        workspace=workspace, bill_ref=line.bill_ref
                    ).first()
                    if not bp or bp.amount <= 0:
                        complete = False
                        break
                if not complete:
                    break
        else:
            priced = WorkspaceBillPrice.objects.filter(
                workspace=workspace, amount__gt=0
            ).count()
            complete = priced > 0

        workspace.pricing_complete = complete
        workspace.save(update_fields=['pricing_complete'])
        if complete:
            messages.success(request, 'Bid prices saved. Selected components are fully priced.')
        else:
            messages.warning(
                request,
                'Prices saved. Some lines in selected components still need rates.',
            )
        return redirect('bid-workspace', listing_id=listing_id)

    selected = workspace.selected_codes()
    # Default: if packages exist and none selected yet, leave empty so UI prompts
    selected_packages = [p for p in packages if p.code.upper() in selected]
    price_map = {
        bp.bill_ref: bp
        for bp in workspace.bill_prices.all()
    }

    package_sections = []
    category_summary = []
    grand_total = Decimal('0')
    for pkg in selected_packages:
        rows = []
        subtotal = Decimal('0')
        for line in pkg.lines.all():
            bp = price_map.get(line.bill_ref)
            amount = bp.amount if bp else Decimal('0')
            subtotal += amount
            rows.append({
                'line': line,
                'price': bp,
                'rate': bp.unit_rate if bp else Decimal('0'),
                'amount': amount,
            })
        grand_total += subtotal
        package_sections.append({
            'package': pkg,
            'rows': rows,
            'subtotal': subtotal,
            'line_count': len(rows),
        })
        category_summary.append({
            'code': pkg.code,
            'title': pkg.title,
            'subtotal': subtotal,
            'line_count': len(rows),
        })

    # Also show unselected categories in summary as zero / not bidding
    for pkg in packages:
        if pkg.code.upper() in selected:
            continue
        category_summary.append({
            'code': pkg.code,
            'title': pkg.title,
            'subtotal': None,  # not selected
            'line_count': pkg.lines.count(),
        })

    can_switch_boq_mode = (
        getattr(request.user, 'is_staff', False)
        or (ua and listing.created_by_id == getattr(ua, 'pk', None))
        or (
            org
            and getattr(listing.event, 'project', None)
            and listing.event.project.owner_org_id == org.pk
        )
    )

    subcontract_arrangements = []
    if org is not None:
        subcontract_arrangements = list(
            SubcontractArrangement.objects.filter(
                tender=listing,
                main_organisation=org,
            ).exclude(status=SubcontractArrangement.CANCELLED).order_by('-created_at')[:8]
        )
    subcontract_count = len(subcontract_arrangements)

    ctx = {
        'listing': listing,
        'workspace': workspace,
        'packages': packages,
        'selected_codes': selected,
        'boq_input_mode': listing.boq_input_mode,
        'boq_mode_choices': TenderListing.BOQ_INPUT_MODE_CHOICES,
        'can_switch_boq_mode': can_switch_boq_mode,
        'package_sections': package_sections,
        'category_summary': category_summary,
        'category_grand_total': grand_total,
        'bill_prices': workspace.bill_prices.order_by('bill_ref'),
        'self_checks': workspace.self_checks.order_by('mr_ref'),
        'subcontract_count': subcontract_count,
        'subcontract_arrangements': subcontract_arrangements,
        'DOMESTIC': SubcontractArrangement.DOMESTIC,
        'NOMINATED': SubcontractArrangement.NOMINATED,
        **branding_template_context(request),
    }
    return render(request, 'tenders/bid_workspace.html', ctx)


@login_required
def bid_self_assess(request, listing_id):
    """
    GET/POST /tenders/<listing_id>/bid/self-assess/
    Contractor self-assesses against mandatory requirements before submitting.
    """
    listing = get_object_or_404(TenderListing, pk=listing_id, is_published=True)
    requirements = list(_procurement_requirements(listing))

    try:
        _, _, _, workspace = _ensure_bidder_workspace(request, listing)
    except PermissionError as exc:
        messages.error(request, str(exc))
        return redirect('tender-detail', listing_id=listing_id)

    _sync_self_assessment_checks(workspace, requirements)

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'mr14_not_applicable':
            _mark_mr14_not_applicable(workspace)
            messages.success(
                request,
                'MR14 marked not applicable — main contractor registered for all '
                'Electrical Services Works (RFQ exception).',
            )
            return redirect('bid-self-assess', listing_id=listing_id)

        mr_code = (request.POST.get('mr_code') or '').strip()
        if mr_code:
            req = next((r for r in requirements if r.code == mr_code), None)
            if req is None:
                messages.error(request, 'Unknown mandatory requirement.')
            else:
                try:
                    check = _save_single_mr_upload(request, workspace, req)
                    messages.success(request, f'{check.mr_ref} certificate saved.')
                except ValueError as exc:
                    messages.error(request, str(exc))
            return redirect('bid-self-assess', listing_id=listing_id)

        all_checks = _save_self_assessment_uploads(
            request, workspace, requirements
        )
        if workspace.self_assessment_passed:
            messages.success(request,
                'Self-assessment complete. All mandatory requirements satisfied. '
                'You can now submit your bid.')
        else:
            fails = all_checks.filter(
                self_result__in=[SelfAssessmentCheck.FAIL,
                                 SelfAssessmentCheck.PENDING]
            ).count()
            messages.warning(request,
                f'{fails} requirement(s) still failing or pending. '
                f'Resolve these before submitting.')
        next_target = request.POST.get('next') or request.GET.get('next')
        if next_target == 'detail':
            return redirect('tender-detail', listing_id=listing_id)
        return redirect('bid-self-assess', listing_id=listing_id)

    checks_qs = workspace.self_checks.filter(
        mr_ref__in=[r.code for r in requirements]
    )
    checks_map = {c.mr_ref: c for c in checks_qs}
    org = workspace.organisation
    mr14_arrangements = list(
        SubcontractArrangement.objects.filter(
            tender=listing,
            main_organisation=org,
        ).exclude(status=SubcontractArrangement.CANCELLED).order_by('-created_at')[:5]
    )
    mr_rows = []
    for i, req in enumerate(requirements, 1):
        is_mr14 = req.code == MR14_CODE
        check = checks_map.get(req.code)
        mr_rows.append({
            'index': i,
            'req': req,
            'check': check,
            'is_mr14': is_mr14,
            'mr14_satisfied': bool(
                check
                and (
                    check.self_result == SelfAssessmentCheck.PASS
                    or check.document_uploaded
                )
            ),
            'mr14_is_na': bool(
                check and (check.notes or '').startswith('N/A')
            ),
            'display_description': MR14_RFQ_TEXT if is_mr14 else req.description,
        })
    mr_done, mr_total = _mr_progress(workspace, requirements)

    ctx = {
        'listing': listing,
        'workspace': workspace,
        'checks': checks_qs.order_by('mr_ref'),
        'mr_rows': mr_rows,
        'mr_done_count': mr_done,
        'mr_total': mr_total,
        'mr_progress_pct': int((mr_done * 100) / mr_total) if mr_total else 0,
        'mr14_arrangements': mr14_arrangements,
        'mr14_rfq_text': MR14_RFQ_TEXT,
        **branding_template_context(request),
    }
    return render(request, 'tenders/bid_self_assess.html', ctx)



@login_required
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


@login_required
@require_POST
def bid_submit(request, listing_id):
    """
    POST /tenders/<listing_id>/bid/submit/
    Final bid submission. Self-assessment must pass first.
    """
    listing   = get_object_or_404(TenderListing, pk=listing_id, is_published=True)
    org       = get_active_organization(request)
    ua        = _get_user_account(request)
    workspace = get_object_or_404(BidWorkspace, tender=listing, organisation=org)

    if not listing.event.is_open:
        messages.error(request, 'This tender has closed. Submissions are no longer accepted.')
        return redirect('bid-workspace', listing_id=listing_id)

    try:
        submission = workspace.submit(submitted_by=ua)
        from buildwatch.views_subcontract_portal import mark_subcontracts_included_on_main_submit
        mark_subcontracts_included_on_main_submit(workspace, request=request)
        messages.success(request,
            f'Bid submitted successfully. Reference: {listing.event.ref}. '
            f'Your submission ID is {submission.pk}. '
            f'Download your submitted bid pack from the workspace if needed.')
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('bid-workspace', listing_id=listing_id)

    return redirect('my-bids')


@login_required
def my_bids(request):
    """
    GET /tenders/my-bids/
    Contractor's bid history — all workspaces across all tenders.
    """
    org        = get_active_organization(request)
    workspaces = BidWorkspace.objects.filter(
        organisation=org
    ).select_related(
        'tender', 'tender__event', 'tender__country', 'submission'
    ).order_by('-started_at')

    registrations = BidderRegistration.objects.filter(
        organisation=org
    ).select_related('tender', 'tender__event').order_by('-registered_at')

    ctx = {
        'workspaces':     workspaces,
        'registrations':  registrations,
        **branding_template_context(request),
    }
    return render(request, 'tenders/my_bids.html', ctx)


@login_required
def tender_alerts(request):
    """
    GET/POST /tenders/alerts/
    Manage saved search alerts — get notified when matching tenders published.
    """
    org = get_active_organization(request)
    ua  = _get_user_account(request)

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'create':
            TenderAlert.objects.create(
                organisation=org,
                created_by=ua,
                sector=request.POST.get('sector', ''),
                tender_type=request.POST.get('tender_type', ''),
                county_region=request.POST.get('county_region', ''),
                funding_source=request.POST.get('funding_source', ''),
                channel=request.POST.get('channel', TenderAlert.EMAIL),
                is_active=True,
            )
            messages.success(request, 'Alert created. You will be notified when matching tenders are published.')

        elif action == 'delete':
            alert_id = request.POST.get('alert_id')
            TenderAlert.objects.filter(
                pk=alert_id, organisation=org
            ).delete()
            messages.success(request, 'Alert deleted.')

        return redirect('tender-alerts')

    alerts    = TenderAlert.objects.filter(organisation=org).order_by('-created_at')
    countries = Country.objects.filter(is_active=True).order_by('name')
    ctx = {
        'alerts':    alerts,
        'countries': countries,
        **branding_template_context(request),
    }
    return render(request, 'tenders/tender_alerts.html', ctx)


# ── PUBLISHER VIEWS (Employer side) ──────────────────────────────────────────

@login_required
def tender_publish(request):
    """
    GET/POST /tenders/publish/
    Employer creates and publishes a new tender to the exchange.
    """
    ua  = _get_user_account(request)
    org = get_active_organization(request)

    projects = InfraProject.objects.filter(
        owner_org=org, is_active=True
    ).select_related('task')
    countries = Country.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        p = request.POST

        project_id    = p.get('project_id')
        ref           = p.get('ref', '').strip()
        description   = p.get('description', '').strip()
        tender_type   = p.get('tender_type', TenderListing.WORKS)
        visibility    = p.get('visibility', TenderListing.PUBLIC)
        funding       = p.get('funding_source', TenderListing.GOV)
        country_code  = p.get('country', '')
        county_region = p.get('county_region', '').strip()
        issue_date    = p.get('issue_date')
        closing_date  = p.get('closing_date')
        summary       = p.get('summary', '').strip()
        val_min_raw   = p.get('value_min', '').replace(',', '')
        val_max_raw   = p.get('value_max', '').replace(',', '')
        currency      = p.get('currency', 'KES').strip()

        errors = []
        if not project_id: errors.append('Project is required.')
        if not ref:        errors.append('Tender reference is required.')
        if not description:errors.append('Description is required.')
        if not issue_date: errors.append('Issue date is required.')
        if not closing_date: errors.append('Closing date is required.')
        if EvaluationEvent.objects.filter(ref=ref).exists():
            errors.append(f'Tender reference {ref} already exists.')

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'tenders/tender_publish.html', {
                'projects': projects, 'countries': countries,
                **branding_template_context(request),
            })

        project = get_object_or_404(InfraProject, pk=project_id)
        country = Country.objects.filter(code=country_code).first()

        # Create EvaluationEvent
        event = EvaluationEvent.objects.create(
            project=project,
            context=EvaluationEvent.PROCUREMENT,
            ref=ref,
            description=description,
            issue_date=issue_date,
            closing_date=closing_date,
            status=EvaluationEvent.STATUS_OPEN,
            created_by=ua,
        )

        # Create TenderListing
        val_min = Decimal(val_min_raw) if val_min_raw else None
        val_max = Decimal(val_max_raw) if val_max_raw else None

        listing = TenderListing.objects.create(
            event=event,
            tender_type=tender_type,
            visibility=visibility,
            funding_source=funding,
            country=country,
            county_region=county_region,
            estimated_value_min=val_min,
            estimated_value_max=val_max,
            currency=currency,
            summary=summary,
            created_by=ua,
        )

        # Handle document uploads
        for field in ['boq_document', 'specification', 'drawings']:
            f = request.FILES.get(field)
            if f:
                setattr(listing, field, f)
        listing.save()

        # Publish immediately if requested
        if p.get('publish_now') == '1':
            listing.publish(ua)
            messages.success(request,
                f'Tender {ref} published to the BuildWatch exchange.')
        else:
            messages.success(request,
                f'Tender {ref} saved as draft. Publish it when ready.')

        return redirect('tender-manage', listing_id=listing.pk)

    return render(request, 'tenders/tender_publish.html', {
        'projects':  projects,
        'countries': countries,
        'TENDER_TYPES':  TenderListing.TENDER_TYPE_CHOICES,
        'VISIBILITY':    TenderListing.VISIBILITY_CHOICES,
        'FUNDING_TYPES': TenderListing.FUNDING_CHOICES,
        **branding_template_context(request),
    })


@login_required
def tender_manage(request, listing_id):
    """
    GET /tenders/manage/<listing_id>/
    Employer views and manages their tender — submissions, addenda, status.
    """
    listing     = get_object_or_404(TenderListing, pk=listing_id)
    org         = get_active_organization(request)

    # Only the owning org can manage
    if listing.event.project.owner_org != org:
        messages.error(request, 'You do not have permission to manage this tender.')
        return redirect('tender-list')

    submissions = Submission.objects.filter(
        event=listing.event
    ).select_related('submitter_org', 'submitted_by').order_by('rank')

    registrations = BidderRegistration.objects.filter(
        tender=listing
    ).select_related('organisation').order_by('-registered_at')

    addenda = listing.addenda.order_by('addendum_no')

    ctx = {
        'listing':       listing,
        'submissions':   submissions,
        'registrations': registrations,
        'addenda':       addenda,
        **branding_template_context(request),
    }
    return render(request, 'tenders/tender_manage.html', ctx)


@login_required
@require_POST
def tender_addendum(request, listing_id):
    """
    POST /tenders/manage/<listing_id>/addendum/
    Employer issues an addendum. All registered bidders notified.
    """
    listing = get_object_or_404(TenderListing, pk=listing_id)
    org     = get_active_organization(request)
    ua      = _get_user_account(request)

    if listing.event.project.owner_org != org:
        messages.error(request, 'Permission denied.')
        return redirect('tender-list')

    next_no = (listing.addenda.count() or 0) + 1
    addendum = TenderAddendum.objects.create(
        tender     = listing,
        addendum_no= next_no,
        subject    = request.POST.get('subject', '').strip(),
        content    = request.POST.get('content', '').strip(),
        issued_by  = ua,
        document   = request.FILES.get('document'),
    )

    # TODO: trigger notification to all BidderRegistration emails via AlertEngine
    notified = BidderRegistration.objects.filter(tender=listing).count()
    TenderAddendum.objects.filter(pk=addendum.pk).update(notified_count=notified)

    messages.success(request,
        f'Addendum {next_no} issued. {notified} registered bidder(s) will be notified.')
    return redirect('tender-manage', listing_id=listing_id)


@login_required
@require_POST
def tender_publish_toggle(request, listing_id):
    """
    POST /tenders/manage/<listing_id>/toggle-publish/
    Publish or unpublish a tender.
    """
    listing = get_object_or_404(TenderListing, pk=listing_id)
    org     = get_active_organization(request)
    ua      = _get_user_account(request)

    if listing.event.project.owner_org != org:
        messages.error(request, 'Permission denied.')
        return redirect('tender-list')

    if listing.is_published:
        listing.is_published = False
        listing.save(update_fields=['is_published'])
        messages.success(request, f'{listing.event.ref} unpublished from exchange.')
    else:
        listing.publish(ua)
        messages.success(request, f'{listing.event.ref} published to exchange.')

    return redirect('tender-manage', listing_id=listing_id)


def _bid_subcontract_context(request, listing_id):
    """Shared access gate for main-contractor subcontract screens."""
    listing = get_object_or_404(TenderListing, pk=listing_id, is_published=True)
    org = get_active_organization(request)
    try:
        ua = _ensure_user_account(request, org)
    except Exception:
        ua = _get_user_account(request)
    if org is None or ua is None:
        messages.error(request, "Sign in as a contractor organisation to manage subcontracts.")
        return None
    if not BidderRegistration.objects.filter(tender=listing, organisation=org).exists():
        messages.warning(request, "Register interest before starting a subcontract.")
        return None
    workspace, _ = BidWorkspace.objects.get_or_create(
        tender=listing,
        organisation=org,
        defaults={"prepared_by": ua},
    )
    packages = list(
        TenderBoqPackage.objects.filter(tender=listing).order_by("sort_order", "code")
    )
    arrangements = list(
        SubcontractArrangement.objects.filter(
            tender=listing,
            main_organisation=org,
        ).exclude(status=SubcontractArrangement.CANCELLED)
    )
    return {
        "listing": listing,
        "org": org,
        "ua": ua,
        "workspace": workspace,
        "packages": packages,
        "arrangements": arrangements,
    }


def _send_subcontract_invite_email(arrangement, request=None):
    """Email the sub-contractor portal hyperlink for authorised BOQ pricing."""
    from buildwatch.views_subcontract_portal import send_subcontract_portal_invite

    return send_subcontract_portal_invite(arrangement, request=request)


def _send_subcontract_sponsor_notice(arrangement, request=None):
    """Notify project owner / sponsor that a signed subcontract agreement was shared."""
    from accounts.emails import send_system_email, _site_base_url

    project = getattr(arrangement.tender.event, "project", None)
    owner = getattr(project, "owner_org", None) if project else None
    to_email = (getattr(owner, "email", None) or "").strip() if owner else ""
    if not to_email:
        return False, "Sponsor organisation has no email on file."

    base = _site_base_url(request)
    detail_url = f"{base}/tenders/{arrangement.tender_id}/bid/subcontract/{arrangement.pk}/"
    main_name = arrangement.main_organisation.name or arrangement.main_organisation.short_name
    ref = arrangement.tender.event.ref
    subject = f"BuildWatch — Subcontract agreement shared · {ref}"
    text_body = (
        f"A {arrangement.get_arrangement_type_display().lower()} agreement has been lodged "
        f"by {main_name} for tender {ref}.\n\n"
        f"Sub-contractor: {arrangement.sub_company_name}\n"
        f"Contact: {arrangement.sub_email}\n"
        f"Packages: {', '.join(arrangement.selected_codes()) or '—'}\n"
        f"Payment via main contractor: {'Yes' if arrangement.payment_via_main else 'No'}\n"
        f"Consultant approval path: {'Yes' if arrangement.approval_by_consultant else 'No'}\n\n"
        f"View on BuildWatch:\n{detail_url}\n"
    )
    ok, err = send_system_email(
        subject=subject,
        to=to_email,
        text_body=text_body,
        include_ceo_cc=False,
    )
    return ok, err


@login_required
def bid_subcontract(request, listing_id):
    """
    GET/POST /tenders/<id>/bid/subcontract/
    Main contractor jump-starts domestic or nominated subcontract onboarding.
    """
    import secrets

    ctx = _bid_subcontract_context(request, listing_id)
    if ctx is None:
        return redirect("tender-detail", listing_id=listing_id)

    listing = ctx["listing"]
    org = ctx["org"]
    ua = ctx["ua"]
    workspace = ctx["workspace"]
    packages = ctx["packages"]

    if request.method == "POST":
        if not listing.event.is_open:
            messages.error(request, "This tender has closed.")
            return redirect("bid-subcontract", listing_id=listing_id)

        arr_type = (request.POST.get("arrangement_type") or "").strip().upper()
        if arr_type not in {
            SubcontractArrangement.DOMESTIC,
            SubcontractArrangement.NOMINATED,
        }:
            messages.error(request, "Select Domestic or Nominated sub-contractor.")
            return redirect("bid-subcontract", listing_id=listing_id)

        company = (request.POST.get("sub_company_name") or "").strip()
        email = (request.POST.get("sub_email") or "").strip().lower()
        contact = (request.POST.get("sub_contact_name") or "").strip()
        phone = (request.POST.get("sub_phone") or "").strip()
        notes = (request.POST.get("notes") or "").strip()
        selected = [
            c.strip().upper()
            for c in request.POST.getlist("package_code")
            if c.strip()
        ]
        valid = {p.code.upper() for p in packages}
        selected = [c for c in selected if c in valid]

        if not company:
            messages.error(request, "Sub-contractor company name is required.")
            return redirect("bid-subcontract", listing_id=listing_id)
        if not email or "@" not in email:
            messages.error(request, "A valid sub-contractor email is required.")
            return redirect("bid-subcontract", listing_id=listing_id)
        if not selected:
            messages.error(request, "Select at least one BOQ package to subcontract.")
            return redirect("bid-subcontract", listing_id=listing_id)

        is_nominated = arr_type == SubcontractArrangement.NOMINATED
        arrangement = SubcontractArrangement.objects.create(
            tender=listing,
            workspace=workspace,
            main_organisation=org,
            arrangement_type=arr_type,
            status=SubcontractArrangement.INVITED,
            package_codes=selected,
            sub_company_name=company,
            sub_contact_name=contact,
            sub_email=email,
            sub_phone=phone,
            notes=notes,
            payment_via_main=True,
            approval_by_consultant=is_nominated,
            invite_token=secrets.token_urlsafe(32),
            invited_by=ua,
            invited_at=timezone.now(),
        )
        ok, err = _send_subcontract_invite_email(arrangement, request)
        arrangement.invite_email_sent = ok
        arrangement.invite_email_error = (err or "")[:400]
        arrangement.save(
            update_fields=["invite_email_sent", "invite_email_error", "updated_at"]
        )
        if ok:
            messages.success(
                request,
                f"Portal invitation sent to {email}. The sub-contractor can open the "
                f"link to price authorised BOQ packages, download a draft PDF, and "
                f"submit their quote to you for acknowledgement.",
            )
        else:
            messages.warning(
                request,
                f"Arrangement created, but email could not be sent: {err}. "
                f"You can resend from the arrangement page.",
            )
        return redirect("bid-subcontract-detail", listing_id=listing_id, pk=arrangement.pk)

    return render(
        request,
        "tenders/bid_subcontract.html",
        {
            "listing": listing,
            "workspace": workspace,
            "packages": packages,
            "arrangements": ctx["arrangements"],
            "selected_codes": workspace.selected_codes(),
            "DOMESTIC": SubcontractArrangement.DOMESTIC,
            "NOMINATED": SubcontractArrangement.NOMINATED,
        },
    )


@login_required
def bid_subcontract_detail(request, listing_id, pk):
    """Manage one subcontract: resend invite, upload agreement, share with sponsor."""
    ctx = _bid_subcontract_context(request, listing_id)
    if ctx is None:
        return redirect("tender-detail", listing_id=listing_id)

    listing = ctx["listing"]
    org = ctx["org"]
    arrangement = get_object_or_404(
        SubcontractArrangement,
        pk=pk,
        tender=listing,
        main_organisation=org,
    )

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "resend_invite":
            ok, err = _send_subcontract_invite_email(arrangement, request)
            arrangement.invite_email_sent = ok
            arrangement.invite_email_error = (err or "")[:400]
            arrangement.invited_at = timezone.now()
            if arrangement.status == SubcontractArrangement.DRAFT:
                arrangement.status = SubcontractArrangement.INVITED
            arrangement.save(
                update_fields=[
                    "invite_email_sent",
                    "invite_email_error",
                    "invited_at",
                    "status",
                    "updated_at",
                ]
            )
            if ok:
                messages.success(request, f"Invitation resent to {arrangement.sub_email}.")
            else:
                messages.error(request, f"Could not send email: {err}")
        elif action == "upload_agreement":
            f = request.FILES.get("agreement_file")
            if not f:
                messages.error(request, "Choose a signed agreement PDF to upload.")
            else:
                arrangement.agreement_file = f
                arrangement.agreement_uploaded_at = timezone.now()
                if arrangement.status in {
                    SubcontractArrangement.INVITED,
                    SubcontractArrangement.ACCEPTED,
                    SubcontractArrangement.DRAFT,
                }:
                    arrangement.status = SubcontractArrangement.AGREEMENT_UPLOADED
                arrangement.save(
                    update_fields=[
                        "agreement_file",
                        "agreement_uploaded_at",
                        "status",
                        "updated_at",
                    ]
                )
                workspace = ctx["workspace"]
                _link_mr14_from_subcontract(workspace, arrangement)
                messages.success(
                    request,
                    "Signed agreement lodged for bid preparation — MR14 on your "
                    "certificate checklist is now satisfied. You can still share "
                    "a copy with the sponsor after award notice if required.",
                )
        elif action == "share_sponsor":
            if not arrangement.agreement_file:
                messages.error(request, "Upload the signed agreement before sharing with the sponsor.")
            else:
                ok, err = _send_subcontract_sponsor_notice(arrangement, request)
                arrangement.shared_with_sponsor_at = timezone.now()
                arrangement.status = SubcontractArrangement.SHARED_WITH_SPONSOR
                arrangement.sponsor_notified = ok
                arrangement.save(
                    update_fields=[
                        "shared_with_sponsor_at",
                        "status",
                        "sponsor_notified",
                        "updated_at",
                    ]
                )
                if ok:
                    messages.success(request, "Agreement shared with the project sponsor.")
                else:
                    messages.warning(
                        request,
                        f"Marked as shared on BuildWatch. Sponsor email notice: {err}",
                    )
        elif action == "cancel":
            arrangement.status = SubcontractArrangement.CANCELLED
            arrangement.save(update_fields=["status", "updated_at"])
            messages.info(request, "Subcontract arrangement cancelled.")
            return redirect("bid-subcontract", listing_id=listing_id)
        return redirect("bid-subcontract-detail", listing_id=listing_id, pk=pk)

    package_labels = {
        p.code.upper(): p.title
        for p in ctx["packages"]
        if p.code.upper() in set(arrangement.selected_codes())
    }
    return render(
        request,
        "tenders/bid_subcontract_detail.html",
        {
            "listing": listing,
            "arrangement": arrangement,
            "package_labels": package_labels,
            "portal_path": f"/tenders/subcontract/portal/{arrangement.invite_token}/",
            "accept_path": f"/tenders/subcontract/portal/{arrangement.invite_token}/",
        },
    )


def subcontract_accept(request, token):
    """Legacy URL — send invitees into the authorised pricing portal."""
    return redirect("subcontract-portal", token=token)
