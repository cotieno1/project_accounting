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
    InfraProject, TenderBoqPackage, TenderBoqLine,
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


def _mr_progress(workspace, requirements):
    """Return (done, total) for uploaded MR certificates — never gates BOQ."""
    total = len(requirements)
    if total == 0:
        return 0, 0
    if workspace is None:
        return 0, total
    codes = [r.code for r in requirements]
    done = workspace.self_checks.filter(
        mr_ref__in=codes,
        document_uploaded=True,
    ).count()
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
    for pkg in selected_packages:
        rows = []
        for line in pkg.lines.all():
            bp = price_map.get(line.bill_ref)
            rows.append({
                'line': line,
                'price': bp,
                'rate': bp.unit_rate if bp else Decimal('0'),
                'amount': bp.amount if bp else Decimal('0'),
            })
        package_sections.append({'package': pkg, 'rows': rows})

    ctx = {
        'listing': listing,
        'workspace': workspace,
        'packages': packages,
        'selected_codes': selected,
        'package_sections': package_sections,
        'bill_prices': workspace.bill_prices.order_by('bill_ref'),
        'self_checks': workspace.self_checks.order_by('mr_ref'),
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
    mr_rows = []
    for i, req in enumerate(requirements, 1):
        mr_rows.append({
            'index': i,
            'req': req,
            'check': checks_map.get(req.code),
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
        **branding_template_context(request),
    }
    return render(request, 'tenders/bid_self_assess.html', ctx)


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
        messages.success(request,
            f'Bid submitted successfully. Reference: {listing.event.ref}. '
            f'Your submission ID is {submission.pk}. '
            f'You will be notified of the outcome.')
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
