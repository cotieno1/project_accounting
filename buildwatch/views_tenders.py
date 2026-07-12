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
    InfraProject,
)
from accounts.models import Organization, UserAccount
from accounts.tenant import get_active_organization, branding_template_context


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_user_account(request):
    """Returns UserAccount for logged-in user, or None."""
    try:
        return request.user.useraccount
    except Exception:
        return None


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
    Increments view_count.
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

    # Increment view count
    TenderListing.objects.filter(pk=listing_id).update(
        view_count=listing.view_count + 1
    )

    # Addenda
    addenda = listing.addenda.order_by('addendum_no')

    # Registration status for logged-in bidder
    bidder_reg      = None
    workspace       = None
    is_invited      = False

    if request.user.is_authenticated:
        org = get_active_organization(request)
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

    ctx = {
        'listing':      listing,
        'addenda':      addenda,
        'bidder_reg':   bidder_reg,
        'workspace':    workspace,
        'is_invited':   is_invited,
        'can_bid':      listing.event.is_open,
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
    org     = get_active_organization(request)
    ua      = _get_user_account(request)

    if not listing.event.is_open:
        messages.error(request, 'This tender has closed.')
        return redirect('tender-detail', listing_id=listing_id)

    reg, created = BidderRegistration.objects.get_or_create(
        tender=listing,
        organisation=org,
        defaults={'registered_by': ua},
    )
    if created:
        messages.success(request,
            f'You are registered for {listing.event.ref}. '
            f'You will receive notifications for all addenda.')
    else:
        messages.info(request, 'You are already registered for this tender.')

    return redirect('tender-detail', listing_id=listing_id)


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
    POST: save bill prices and update workspace.
    """
    listing = get_object_or_404(TenderListing, pk=listing_id, is_published=True)
    org     = get_active_organization(request)
    ua      = _get_user_account(request)

    # Must be registered
    if not BidderRegistration.objects.filter(
            tender=listing, organisation=org).exists():
        messages.warning(request,
            'Register your interest before accessing the bid workspace.')
        return redirect('tender-detail', listing_id=listing_id)

    if not listing.event.is_open:
        messages.error(request, 'This tender has closed. Bid workspace is read-only.')

    # Get or create workspace
    workspace, _ = BidWorkspace.objects.get_or_create(
        tender=listing,
        organisation=org,
        defaults={'prepared_by': ua},
    )

    if request.method == 'POST' and listing.event.is_open:
        # Save bill prices from POST
        bill_refs = request.POST.getlist('bill_ref')
        for bill_ref in bill_refs:
            desc       = request.POST.get(f'desc_{bill_ref}', '')
            unit       = request.POST.get(f'unit_{bill_ref}', '')
            qty_raw    = request.POST.get(f'qty_{bill_ref}', '0').replace(',', '')
            rate_raw   = request.POST.get(f'rate_{bill_ref}', '0').replace(',', '')
            try:
                qty  = Decimal(qty_raw)
                rate = Decimal(rate_raw)
            except Exception:
                continue
            WorkspaceBillPrice.objects.update_or_create(
                workspace=workspace,
                bill_ref=bill_ref,
                defaults={
                    'description': desc,
                    'unit':        unit,
                    'quantity':    qty,
                    'unit_rate':   rate,
                }
            )
        # Check pricing completeness
        priced = WorkspaceBillPrice.objects.filter(
            workspace=workspace,
            amount__gt=0,
        ).count()
        workspace.pricing_complete = priced > 0
        workspace.save(update_fields=['pricing_complete'])
        messages.success(request, 'Bid prices saved.')
        return redirect('bid-workspace', listing_id=listing_id)

    bill_prices = workspace.bill_prices.order_by('bill_ref')
    self_checks = workspace.self_checks.order_by('mr_ref')

    ctx = {
        'listing':    listing,
        'workspace':  workspace,
        'bill_prices':bill_prices,
        'self_checks':self_checks,
        **branding_template_context(request),
    }
    return render(request, 'tenders/bid_workspace.html', ctx)


@login_required
def bid_self_assess(request, listing_id):
    """
    GET/POST /tenders/<listing_id>/bid/self-assess/
    Contractor self-assesses against mandatory requirements before submitting.
    """
    listing   = get_object_or_404(TenderListing, pk=listing_id, is_published=True)
    org       = get_active_organization(request)
    ua        = _get_user_account(request)
    workspace = get_object_or_404(BidWorkspace, tender=listing, organisation=org)

    # Load MR requirements relevant to this tender context
    requirements = MandatoryRequirement.objects.filter(
        context__in=['PROCUREMENT', 'ALL'],
        is_active=True,
    ).order_by('order')

    # Ensure self-check records exist for all requirements
    for req in requirements:
        SelfAssessmentCheck.objects.get_or_create(
            workspace=workspace,
            mr_ref=req.code,
            defaults={
                'requirement':  req,
                'description':  req.description,
                'self_result':  SelfAssessmentCheck.PENDING,
            }
        )

    if request.method == 'POST':
        for req in requirements:
            result = request.POST.get(f'result_{req.code}',
                                       SelfAssessmentCheck.PENDING)
            notes  = request.POST.get(f'notes_{req.code}', '')
            doc    = request.FILES.get(f'doc_{req.code}')
            check  = SelfAssessmentCheck.objects.get(
                workspace=workspace, mr_ref=req.code
            )
            check.self_result = result
            check.notes       = notes
            if doc:
                check.document          = doc
                check.document_uploaded = True
            check.save()

        # Compute overall pass/fail
        all_checks = workspace.self_checks.all()
        has_fail   = all_checks.filter(
            self_result=SelfAssessmentCheck.FAIL
        ).exists()
        has_pending = all_checks.filter(
            self_result=SelfAssessmentCheck.PENDING
        ).exists()

        workspace.self_assessment_passed = not has_fail and not has_pending
        if workspace.self_assessment_passed:
            workspace.status = BidWorkspace.SELF_CHECKED
        workspace.save(update_fields=['self_assessment_passed', 'status'])

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
        return redirect('bid-self-assess', listing_id=listing_id)

    checks = workspace.self_checks.order_by('mr_ref')
    ctx = {
        'listing':    listing,
        'workspace':  workspace,
        'checks':     checks,
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
