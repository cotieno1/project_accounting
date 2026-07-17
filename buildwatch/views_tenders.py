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
#   tender_load_pdf_boq  POST /tenders/<id>/boq/load/
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
from django.urls import reverse
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

# Explicit packs — never dump the full global library onto every Kenya tender.
MR_CHECKLIST_CODES = {
    TenderListing.MR_CHECKLIST_KE_ELECTRICAL_RFQ: [
        'MR-PROC-KE-01',
        'MR-PROC-KE-02',
        'MR-PROC-KE-03',
        'MR-PROC-KE-04',
        'MR-PROC-KE-05',
        'MR-PROC-KE-06',
        'MR-PROC-KE-07',
        'MR-PROC-KE-08',
        'MR-PROC-KE-09',
        'MR-PROC-KE-10',
        'MR-PROC-KE-11',
        'MR-PROC-KE-12',
        'MR-PROC-KE-13',
        'MR-PROC-KE-14',
    ],
}


def _procurement_requirements(listing=None):
    """
    Active procurement MRs for this tender only.
    Requires an explicit listing.mr_checklist pack — otherwise empty
    (prevents Isiolo electrical MRs appearing on unrelated tenders like Emurua).
    """
    qs = MandatoryRequirement.objects.filter(
        context__in=[
            MandatoryRequirement.PROCUREMENT,
            MandatoryRequirement.ALL,
        ],
        is_active=True,
    )
    if listing is None:
        return qs.order_by('order', 'code')

    checklist = (getattr(listing, 'mr_checklist', None) or '').strip()
    if not checklist:
        return MandatoryRequirement.objects.none()

    codes = MR_CHECKLIST_CODES.get(checklist)
    if codes:
        qs = qs.filter(code__in=codes)
    else:
        return MandatoryRequirement.objects.none()

    country = getattr(listing, 'country', None)
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
    "Domestic Contractor's Agreement - A duly signed and stamped Agreement not earlier than "
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


def _active_subcontracted_codes(listing, org):
    """BOQ package codes already committed to an active subcontract on this bid."""
    codes = set()
    if listing is None or org is None:
        return codes
    try:
        qs = SubcontractArrangement.objects.filter(
            tender=listing,
            main_organisation=org,
        ).exclude(status=SubcontractArrangement.CANCELLED)
        for arr in qs.only("package_codes"):
            codes.update(arr.selected_codes())
    except Exception:
        return set()
    return codes


# Sub has updated / lodged their authorised BOQ slice with the main contractor.
_SUB_QUOTE_READY = frozenset({
    SubcontractArrangement.QUOTE_SUBMITTED,
    SubcontractArrangement.QUOTE_ACKNOWLEDGED,
    SubcontractArrangement.QUOTE_INCLUDED,
})


def _active_subcontracts(listing, org):
    if listing is None or org is None:
        return []
    try:
        return list(
            SubcontractArrangement.objects.filter(
                tender=listing,
                main_organisation=org,
            ).exclude(status=SubcontractArrangement.CANCELLED)
            .select_related("sub_organisation")
            .prefetch_related("quote_lines")
            .order_by("-created_at")
        )
    except Exception:
        return []


def _bill_category_key(bill_ref):
    """
    BOQ bill category from ref mask, e.g. '1/1.01' -> '1', '2/2.05' -> '2'.
    Used for per-bill (cat) sub-totals on live main BOQ.
    """
    ref = (bill_ref or "").strip()
    if "/" in ref:
        return ref.split("/", 1)[0].strip() or ref
    return ref or "?"


def _bill_category_label(bill_key):
    """Display mask for a bill category, e.g. '1' -> '1/x.xx'."""
    key = (bill_key or "").strip() or "?"
    return f"{key}/x.xx"


def _group_rows_by_bill(rows):
    """Group priced BOQ rows into bill categories with running subtotals."""
    groups = []
    current_key = None
    current = None
    for row in rows:
        ref = getattr(row.get("line"), "bill_ref", None) or row.get("bill_ref") or ""
        key = _bill_category_key(ref)
        if key != current_key:
            current = {
                "bill_key": key,
                "bill_label": _bill_category_label(key),
                "rows": [],
                "subtotal": Decimal("0"),
            }
            groups.append(current)
            current_key = key
        amount = row.get("amount") or Decimal("0")
        current["rows"].append(row)
        current["subtotal"] += amount
    return groups


def _subcontract_package_sections(listing, org, packages):
    """
    Read-only BOQ sections for packages assigned to sub-contractors.
    Amounts come from the sub quote portal (qty x unit rate).
    """
    arrangements = _active_subcontracts(listing, org)
    if not arrangements:
        return [], Decimal("0")

    pkg_to_arr = {}
    for arr in arrangements:
        for code in arr.selected_codes():
            pkg_to_arr[code.upper()] = arr

    sections = []
    grand = Decimal("0")
    for pkg in packages:
        code_u = pkg.code.upper()
        arr = pkg_to_arr.get(code_u)
        if not arr:
            continue
        price_map = {ql.bill_ref: ql for ql in arr.quote_lines.all()}
        rows = []
        subtotal = Decimal("0")
        for line in pkg.lines.all():
            ql = price_map.get(line.bill_ref)
            qty = line.quantity or Decimal("0")
            rate = ql.unit_rate if ql else Decimal("0")
            amount = (qty * rate).quantize(Decimal("0.01"))
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
            "arrangement": arr,
            "sub_company": arr.sub_company_name,
            "quote_status": arr.get_quote_status_display() or "No quote yet",
        })
    return sections, grand


def _pending_subcontract_quotes(listing, org):
    """Arrangements still waiting for the sub to submit priced BOQ."""
    return [
        arr for arr in _active_subcontracts(listing, org)
        if (arr.quote_status or "") not in _SUB_QUOTE_READY
    ]


def _can_print_draft_for_approval(listing, org):
    """
    Draft bid price for approval is available only after every active
    subcontract has submitted an updated BOQ quote (or there is no sub).
    """
    return len(_pending_subcontract_quotes(listing, org)) == 0


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


def _can_publish_tender(request):
    """Employers / sponsors and platform admins can publish to the exchange."""
    if not request.user.is_authenticated:
        return False
    if getattr(request.user, "is_superuser", False) or getattr(request.user, "is_staff", False):
        return True
    try:
        from accounts.roles import USER_ADMIN, get_role_code

        if get_role_code(request.user) == USER_ADMIN:
            return True
    except Exception:
        pass
    org = get_active_organization(request)
    return get_exchange_persona(org=org, request=request) == "employer"


def _ensure_publish_user_account(request, org):
    ua = _get_user_account(request)
    if ua is not None:
        return ua
    try:
        return _ensure_user_account(request, org)
    except Exception as exc:
        raise PermissionError(f"User profile required to publish: {exc}") from exc


def _create_project_for_tender(org, *, project_code, description, country, county_region, sector="BUILDINGS"):
    """Create / reuse an InfraProject so a tender can be published from a BOQ PDF alone."""
    from accounts.models import ProjectTask

    code = (project_code or "").strip().upper()
    code = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in code)[:40] or "TENDER"
    base = code
    n = 1
    while ProjectTask.objects.filter(project_id=code).exists():
        # reuse existing task if description matches same owner later
        existing = ProjectTask.objects.filter(project_id=code).first()
        if existing and hasattr(existing, "infra_profile"):
            proj = existing.infra_profile
            if proj.owner_org_id == org.pk:
                return proj
        code = f"{base[:36]}_{n}"
        n += 1

    task, _ = ProjectTask.objects.get_or_create(
        project_id=code,
        defaults={"description": (description or code)[:255]},
    )
    project, _ = InfraProject.objects.get_or_create(
        task=task,
        defaults={
            "owner_org": org,
            "country": country,
            "sector": sector or "BUILDINGS",
            "project_type": "GOV",
            "county": (county_region or "")[:100],
            "contract_value": Decimal("0"),
            "is_active": True,
        },
    )
    return project


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
        'can_publish_tender': _can_publish_tender(request),
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
    can_load_pdf_boq = bool(
        can_upload_mr
        and listing.event.is_open
        and (workspace is None or workspace.status != BidWorkspace.SUBMITTED)
    )

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
        'can_load_pdf_boq': can_load_pdf_boq,
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


def _load_pdf_boq_into_workspace(listing, workspace):
    """
    Parse the tender's attached RFQ/BOQ PDF (or shipped extract) into packages/lines
    and reset this contractor workspace so Pioneer can price from the PDF source.
    """
    from buildwatch.boq_ingest.persist import apply_standard_boq
    from buildwatch.boq_ingest.sources import load_pdf_auto_boq

    doc = load_pdf_auto_boq(listing)
    stats = apply_standard_boq(listing, doc)
    listing.boq_input_mode = TenderListing.BOQ_PDF_AUTO
    listing.save(update_fields=["boq_input_mode"])

    if workspace.status != BidWorkspace.SUBMITTED:
        WorkspaceBillPrice.objects.filter(workspace=workspace).delete()
        workspace.selected_package_codes = []
        workspace.pricing_complete = False
        workspace.save(update_fields=["selected_package_codes", "pricing_complete"])

    stats["warnings"] = list(getattr(doc, "warnings", []) or [])
    stats["source_name"] = getattr(doc, "source_name", "") or ""
    stats["document_name"] = (doc.meta or {}).get("document_name") or stats["source_name"]
    return stats


@login_required
@require_POST
def tender_load_pdf_boq(request, listing_id):
    """
    POST /tenders/<listing_id>/boq/load/
    Pioneer (contractor): register interest if needed, parse the attached PDF BOQ
    into the online bid workspace, then open pricing.
    """
    listing = get_object_or_404(TenderListing, pk=listing_id, is_published=True)

    if not listing.event.is_open:
        messages.error(request, 'This tender has closed.')
        return redirect('tender-detail', listing_id=listing_id)

    try:
        org, ua, reg, workspace = _ensure_bidder_workspace(request, listing)
    except PermissionError as exc:
        messages.error(request, str(exc))
        return redirect('tender-detail', listing_id=listing_id)

    if workspace.status == BidWorkspace.SUBMITTED:
        messages.warning(
            request,
            'Bid already submitted — PDF BOQ cannot be reloaded for this tender.',
        )
        return redirect('bid-workspace', listing_id=listing_id)

    try:
        stats = _load_pdf_boq_into_workspace(listing, workspace)
    except Exception as exc:
        messages.error(
            request,
            f'Could not load PDF BOQ into the workspace: {exc}',
        )
        return redirect('tender-detail', listing_id=listing_id)

    try:
        reg.record_boq_download()
    except Exception:
        pass

    listing.registered_bidder_count = BidderRegistration.objects.filter(
        tender=listing
    ).count()
    listing.save(update_fields=['registered_bidder_count'])

    src = stats.get("document_name") or stats.get("source_name") or "RFQ/BOQ PDF"
    messages.success(
        request,
        f'{org.short_name or org.name}: loaded PDF BOQ ({src}) — '
        f'{stats.get("categories", 0)} categories, {stats.get("lines", 0)} lines. '
        f'Select categories and enter unit rates.',
    )
    for wmsg in stats.get("warnings") or []:
        messages.warning(request, wmsg)
    return redirect('bid-workspace', listing_id=listing_id)


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

    # Subcontract quotes that the main can carry into the approval draft.
    subcontract_arrangements = _active_subcontracts(listing, org)
    sub_ready = [
        arr for arr in subcontract_arrangements
        if (arr.quote_status or "") in _SUB_QUOTE_READY
    ]
    sub_price_by_ref = {}
    sub_pkg_codes = set()
    subcontract_sections = []
    subcontract_quote_total = Decimal("0")
    for arr in sub_ready:
        sub_pkg_codes.update(arr.selected_codes())
        subcontract_quote_total += arr.quote_total or Decimal("0")
        for ql in arr.quote_lines.all():
            sub_price_by_ref[ql.bill_ref] = ql

    package_sections = []
    category_summary = []
    bill_summary = []
    grand_total = Decimal("0")
    for pkg in packages:
        code_u = pkg.code.upper()
        included_main = code_u in selected
        included_sub = code_u in sub_pkg_codes and code_u not in selected
        rows = []
        subtotal = Decimal("0")
        line_count = pkg.lines.count()
        if included_main:
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
                "source": "main",
            })
            category_summary.append({
                "code": pkg.code,
                "title": pkg.title,
                "subtotal": subtotal,
                "line_count": len(rows),
            })
        elif included_sub:
            for line in pkg.lines.all():
                ql = sub_price_by_ref.get(line.bill_ref)
                amount = ql.amount if ql else Decimal("0")
                rate = ql.unit_rate if ql else Decimal("0")
                subtotal += amount
                rows.append({"line": line, "rate": rate, "amount": amount})
            grand_total += subtotal
            section = {
                "package": pkg,
                "rows": rows,
                "subtotal": subtotal,
                "line_count": len(rows),
                "source": "subcontract",
            }
            package_sections.append(section)
            subcontract_sections.append(section)
            category_summary.append({
                "code": pkg.code,
                "title": pkg.title + " (subcontract)",
                "subtotal": subtotal,
                "line_count": len(rows),
            })
        bill_summary.append({
            "code": pkg.code,
            "title": pkg.title + (" (subcontract)" if included_sub else ""),
            "line_count": line_count,
            "included": included_main or included_sub,
            "subtotal": subtotal if (included_main or included_sub) else Decimal("0"),
            "source": "subcontract" if included_sub else ("main" if included_main else ""),
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
        "subcontract_arrangements": sub_ready,
        "subcontract_sections": subcontract_sections,
        "subcontract_quote_total": subcontract_quote_total,
        "has_subcontract_quotes": bool(sub_ready),
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

    if org is None:
        messages.warning(
            request,
            'Select the Pioneer (contractor) organisation first, then open the BOQ workspace.',
        )
        return redirect('tender-detail', listing_id=listing_id)

    if not BidderRegistration.objects.filter(
            tender=listing, organisation=org).exists():
        # Signed-in contractor: auto-register interest so /bid/ is reachable
        # instead of silently bouncing back to the public tender page.
        from accounts.tenant import get_exchange_persona
        if get_exchange_persona(org=org, request=request) == 'contractor' and ua is not None:
            BidderRegistration.objects.get_or_create(
                tender=listing,
                organisation=org,
                defaults={'registered_by': ua},
            )
            BidWorkspace.objects.get_or_create(
                tender=listing,
                organisation=org,
                defaults={'prepared_by': ua},
            )
            listing.registered_bidder_count = BidderRegistration.objects.filter(
                tender=listing
            ).count()
            listing.save(update_fields=['registered_bidder_count'])
            messages.success(
                request,
                f'{org.short_name or org.name} registered for {listing.event.ref}. '
                'Continue with Step 1 — Apply Sub Contracting.',
            )
        else:
            messages.warning(
                request,
                'Register your interest on the tender page before accessing the BOQ workspace.',
            )
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
            subcontracted = _active_subcontracted_codes(listing, org)
            selected = [
                c.strip().upper()
                for c in request.POST.getlist('package_code')
                if c.strip()
            ]
            valid = {p.code.upper() for p in packages} - subcontracted
            selected = [c for c in selected if c in valid]
            if not selected and packages and (len(packages) > len(subcontracted)):
                messages.error(request, 'Select at least one remaining BOQ component to bid.')
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
                f'{len(selected)} component(s) selected for main BOQ. Enter unit rates below.',
            )
            return redirect('bid-workspace', listing_id=listing_id)

        if action == 'set_planned_subcontractors':
            raw_n = (request.POST.get('planned_subcontractor_count') or '').strip()
            try:
                planned_n = int(raw_n)
            except (TypeError, ValueError):
                messages.error(
                    request,
                    'Enter how many sub-contractors you need (0 if none).',
                )
                return redirect('bid-workspace', listing_id=listing_id)
            if planned_n < 0 or planned_n > 50:
                messages.error(request, 'Sub-contractor count must be between 0 and 50.')
                return redirect('bid-workspace', listing_id=listing_id)

            active_n = len(_active_subcontracts(listing, org))
            if planned_n < active_n:
                messages.error(
                    request,
                    f'You already have {active_n} active sub-contractor(s). '
                    f'Set N to at least {active_n}, or cancel an arrangement first.',
                )
                return redirect('bid-workspace', listing_id=listing_id)

            workspace.planned_subcontractor_count = planned_n
            workspace.save(update_fields=['planned_subcontractor_count'])
            if planned_n == 0:
                try:
                    _mark_mr14_not_applicable(workspace)
                except Exception as exc:
                    messages.warning(request, f'N set to 0, but MR14 N/A note failed: {exc}')
                    return redirect('bid-workspace', listing_id=listing_id)
                messages.success(
                    request,
                    'Planned sub-contractors = 0. MR14 marked N/A. '
                    'Subcontracting controls stay locked. Continue with main BOQ.',
                )
            else:
                remaining = planned_n - active_n
                messages.success(
                    request,
                    f'Planned sub-contractors set to {planned_n}. '
                    f'Invite {remaining} more, then the form locks.',
                )
            return redirect('bid-workspace', listing_id=listing_id)

        if action == 'begin_subcontract':
            # Step 1: subcontract first — create invite here (fixes Process 500 redirect).
            import secrets

            active_subs = _active_subcontracts(listing, org)
            planned_n = workspace.planned_subcontractor_count
            if planned_n is None:
                messages.error(
                    request,
                    'Set how many sub-contractors you need (N) first, then invite.',
                )
                return redirect('bid-workspace', listing_id=listing_id)
            if planned_n == 0:
                messages.warning(
                    request,
                    'Planned sub-contractors is 0 — subcontracting is locked (MR14 N/A).',
                )
                return redirect('bid-workspace', listing_id=listing_id)
            if len(active_subs) >= planned_n:
                messages.warning(
                    request,
                    f'Sub-contractor quota filled ({len(active_subs)}/{planned_n}). '
                    'Subcontracting controls are locked.',
                )
                return redirect('bid-workspace', listing_id=listing_id)

            required = (request.POST.get('subcontract_required') or '').strip().upper()
            if required == 'NO':
                try:
                    workspace.planned_subcontractor_count = 0
                    workspace.save(update_fields=['planned_subcontractor_count'])
                    _mark_mr14_not_applicable(workspace)
                    messages.success(
                        request,
                        'Subcontracting not required — N set to 0, MR14 marked N/A. '
                        'Continue with main BOQ categories below.',
                    )
                except Exception as exc:
                    messages.error(request, f'Could not update MR14: {exc}')
                return redirect('bid-workspace', listing_id=listing_id)

            if required != 'YES':
                messages.error(request, 'Choose whether subcontracting is required.')
                return redirect('bid-workspace', listing_id=listing_id)

            arr_type = (request.POST.get('arrangement_type') or 'A').strip().upper()
            if arr_type in {'B', 'TYPE_B', 'NOMINATED'}:
                arr_type = SubcontractArrangement.NOMINATED
            else:
                arr_type = SubcontractArrangement.DOMESTIC

            selected_sub = [
                c.strip().upper()
                for c in request.POST.getlist('sub_package_code')
                if c.strip()
            ]
            valid = {p.code.upper() for p in packages}
            already = _active_subcontracted_codes(listing, org)
            selected_sub = [c for c in selected_sub if c in valid and c not in already]
            company = (request.POST.get('sub_company_name') or '').strip()
            email = (request.POST.get('sub_email') or '').strip().lower()
            contact = (request.POST.get('sub_contact_name') or '').strip()
            phone = (request.POST.get('sub_phone') or '').strip()
            notes = (request.POST.get('notes') or '').strip()

            if not selected_sub:
                messages.error(
                    request,
                    'Select at least one available BOQ category to subcontract '
                    '(already-subcontracted categories are excluded).',
                )
                return redirect('bid-workspace', listing_id=listing_id)
            if not company:
                messages.error(request, 'Sub-contractor company name is required.')
                return redirect('bid-workspace', listing_id=listing_id)
            if not email or '@' not in email:
                messages.error(request, 'A valid sub-contractor invite email is required.')
                return redirect('bid-workspace', listing_id=listing_id)

            try:
                arrangement = SubcontractArrangement.objects.create(
                    tender=listing,
                    workspace=workspace,
                    main_organisation=org,
                    arrangement_type=arr_type,
                    status=SubcontractArrangement.INVITED,
                    package_codes=selected_sub,
                    sub_company_name=company,
                    sub_contact_name=contact,
                    sub_email=email,
                    sub_phone=phone,
                    notes=notes,
                    payment_via_main=True,
                    approval_by_consultant=(
                        arr_type == SubcontractArrangement.NOMINATED
                    ),
                    invite_token=secrets.token_urlsafe(32),
                    invited_by=ua,
                    invited_at=timezone.now(),
                )
            except Exception as exc:
                messages.error(
                    request,
                    'Could not start subcontract (database may need migrate). '
                    f'Detail: {exc}',
                )
                return redirect('bid-workspace', listing_id=listing_id)

            # Create / link contractor ID so the sub firm is a first-class BuildWatch org
            # (same contractor can later be main on another project).
            try:
                from buildwatch.subcontract_orgs import (
                    ensure_contractor_organisation,
                    ensure_subcontractor_employee,
                    link_arrangement_to_contractor,
                )
                sub_org, _ = ensure_contractor_organisation(
                    company_name=company, email=email, phone=phone
                )
                link_arrangement_to_contractor(arrangement, sub_org)
                ensure_subcontractor_employee(
                    organization=sub_org,
                    email=email,
                    contact_name=contact or company,
                    phone=phone,
                )
            except Exception as exc:
                messages.warning(
                    request,
                    f'Subcontract invite saved, but contractor-ID link failed: {exc}',
                )

            kept = [
                c for c in workspace.selected_codes() if c not in set(selected_sub)
            ]
            workspace.selected_package_codes = kept
            WorkspaceBillPrice.objects.filter(
                workspace=workspace, package_code__in=selected_sub
            ).delete()
            workspace.pricing_complete = False
            workspace.save(
                update_fields=['selected_package_codes', 'pricing_complete']
            )

            try:
                ok, err = _send_subcontract_invite_email(arrangement, request)
            except Exception as exc:
                ok, err = False, str(exc)
            arrangement.invite_email_sent = bool(ok)
            arrangement.invite_email_error = (err or '')[:400]
            try:
                arrangement.save(
                    update_fields=[
                        'invite_email_sent',
                        'invite_email_error',
                        'updated_at',
                    ]
                )
            except Exception:
                pass

            filled = len(active_subs) + 1
            slot_msg = f'Slots {filled}/{planned_n} filled.'
            if filled >= planned_n:
                slot_msg += ' Subcontracting controls are now locked.'

            if ok:
                messages.success(
                    request,
                    f'Subcontract invite sent to {email} for '
                    f'{", ".join(selected_sub)}. {slot_msg} '
                    f'Those categories are off your main BOQ — price the remainder next.',
                )
            else:
                messages.warning(
                    request,
                    f'Subcontract saved for {", ".join(selected_sub)}, but email '
                    f'failed: {err}. {slot_msg} Resend from the arrangement page.',
                )
            return redirect('bid-workspace', listing_id=listing_id)

        if action != 'save_prices':
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
    subcontracted_codes = sorted(_active_subcontracted_codes(listing, org))
    subcontracted_set = set(subcontracted_codes)
    # Keep main selection free of subcontracted categories
    if subcontracted_set and any(c in subcontracted_set for c in selected):
        selected = [c for c in selected if c not in subcontracted_set]
        workspace.selected_package_codes = selected
        WorkspaceBillPrice.objects.filter(
            workspace=workspace, package_code__in=list(subcontracted_set)
        ).delete()
        workspace.save(update_fields=['selected_package_codes'])

    main_packages = [p for p in packages if p.code.upper() not in subcontracted_set]
    subcontract_package_sections, subcontract_grand_total = _subcontract_package_sections(
        listing, org, packages
    )
    subcontract_subtotal_by_code = {
        s["package"].code.upper(): s["subtotal"] for s in subcontract_package_sections
    }
    # Default: if packages exist and none selected yet, leave empty so UI prompts
    selected_packages = [p for p in main_packages if p.code.upper() in selected]
    price_map = {
        bp.bill_ref: bp
        for bp in workspace.bill_prices.all()
    }

    package_sections = []
    category_summary = []
    grand_total = Decimal('0')

    for pkg in packages:
        if pkg.code.upper() not in subcontracted_set:
            continue
        sub_pkg_total = subcontract_subtotal_by_code.get(pkg.code.upper(), Decimal("0"))
        arr = next(
            (s["arrangement"] for s in subcontract_package_sections if s["package"].pk == pkg.pk),
            None,
        )
        category_summary.append({
            'code': pkg.code,
            'title': pkg.title + ' (sub-contract)',
            'subtotal': sub_pkg_total,
            'line_count': pkg.lines.count(),
            'subcontracted': True,
            'sub_company': arr.sub_company_name if arr else '',
            'quote_status': arr.get_quote_status_display() if arr else '',
        })

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
                'bill_key': _bill_category_key(line.bill_ref),
                'bill_label': _bill_category_label(_bill_category_key(line.bill_ref)),
            })
        bill_groups = _group_rows_by_bill(rows)
        grand_total += subtotal
        package_sections.append({
            'package': pkg,
            'rows': rows,
            'bill_groups': bill_groups,
            'subtotal': subtotal,
            'line_count': len(rows),
        })
        category_summary.append({
            'code': pkg.code,
            'title': pkg.title,
            'subtotal': subtotal,
            'line_count': len(rows),
            'bill_groups': bill_groups,
        })

    # Also show unselected main categories in summary (exclude already subcontracted)
    for pkg in main_packages:
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

    subcontract_count = 0
    subcontract_arrangements = []
    pending_sub_quotes = []
    can_print_draft_bid = True
    planned_sub_n = None
    try:
        planned_sub_n = workspace.planned_subcontractor_count
    except Exception:
        planned_sub_n = None
    subcontract_quota_full = False
    subcontract_slots_remaining = None
    if org is not None:
        try:
            all_active = _active_subcontracts(listing, org)
            subcontract_arrangements = all_active[:8]
            subcontract_count = len(all_active)
            # If Pioneer already invited subs before N existed, lock to that count.
            if planned_sub_n is None and subcontract_count > 0:
                workspace.planned_subcontractor_count = subcontract_count
                try:
                    workspace.save(update_fields=['planned_subcontractor_count'])
                    planned_sub_n = subcontract_count
                except Exception:
                    planned_sub_n = subcontract_count
            pending_sub_quotes = _pending_subcontract_quotes(listing, org)
            can_print_draft_bid = _can_print_draft_for_approval(listing, org)
            if planned_sub_n is not None:
                subcontract_quota_full = subcontract_count >= planned_sub_n
                subcontract_slots_remaining = max(planned_sub_n - subcontract_count, 0)
        except Exception:
            subcontract_count = 0
            subcontract_arrangements = []
            pending_sub_quotes = []
            can_print_draft_bid = True

    ctx = {
        'listing': listing,
        'workspace': workspace,
        'packages': packages,
        'main_packages': main_packages,
        'subcontracted_codes': subcontracted_codes,
        'selected_codes': selected,
        'boq_input_mode': listing.boq_input_mode,
        'boq_mode_choices': TenderListing.BOQ_INPUT_MODE_CHOICES,
        'can_switch_boq_mode': can_switch_boq_mode,
        'package_sections': package_sections,
        'subcontract_package_sections': subcontract_package_sections,
        'subcontract_grand_total': subcontract_grand_total,
        'combined_grand_total': grand_total + subcontract_grand_total,
        'category_summary': category_summary,
        'category_grand_total': grand_total,
        'bill_prices': workspace.bill_prices.order_by('bill_ref'),
        'self_checks': workspace.self_checks.order_by('mr_ref'),
        'subcontract_count': subcontract_count,
        'subcontract_arrangements': subcontract_arrangements,
        'pending_sub_quotes': pending_sub_quotes,
        'can_print_draft_bid': can_print_draft_bid,
        'planned_subcontractor_count': planned_sub_n,
        'subcontract_quota_full': subcontract_quota_full,
        'subcontract_slots_remaining': subcontract_slots_remaining,
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
    pending_subs = _pending_subcontract_quotes(listing, org)
    if pending_subs and workspace.status != BidWorkspace.SUBMITTED:
        names = ", ".join(
            f"{a.sub_company_name} ({', '.join(a.selected_codes()) or 'packages'})"
            for a in pending_subs
        )
        messages.warning(
            request,
            "Draft bid for approval unlocks after the sub-contractor updates "
            f"their BOQ quote. Waiting on: {names}.",
        )
        return redirect("bid-workspace", listing_id=listing_id)

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
def my_subcontracts(request):
    """
    GET /tenders/my-subcontracts/
    Sub-contractor login home: authorised BOQ work for this contractor ID
    across tenders/projects (e.g. LANBase on Isiolo under Pioneer).
    """
    org = get_active_organization(request)
    ua = _get_user_account(request)
    if org is None:
        messages.warning(request, 'Select your contractor organisation to see subcontract work.')
        return redirect('tender-list')

    arrangements = list(
        SubcontractArrangement.objects.filter(sub_organisation=org)
        .exclude(status=SubcontractArrangement.CANCELLED)
        .select_related('tender', 'tender__event', 'main_organisation')
        .order_by('-created_at')
    )
    # Also match by invitation email if org link is still catching up
    if ua and ua.email and not arrangements:
        arrangements = list(
            SubcontractArrangement.objects.filter(sub_email__iexact=ua.email.strip())
            .exclude(status=SubcontractArrangement.CANCELLED)
            .select_related('tender', 'tender__event', 'main_organisation')
            .order_by('-created_at')
        )

    ctx = {
        'organisation': org,
        'arrangements': arrangements,
        'partial_bid_access_ended': bool(
            ua and getattr(ua, 'partial_bid_access_ended_at', None)
        ),
        **branding_template_context(request),
    }
    return render(request, 'tenders/my_subcontracts.html', ctx)


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
    Employer / platform admin uploads a new tender (with BOQ PDF from local drive)
    and publishes it to the exchange — same listing + bidder functions as Isiolo.
    """
    if not _can_publish_tender(request):
        messages.error(
            request,
            'Only employer / sponsor organisations (or platform admin) can publish tenders.',
        )
        return redirect('tender-list')

    org = get_active_organization(request)
    if org is None:
        messages.error(request, 'Select an organisation before publishing a tender.')
        return redirect('tender-list')

    try:
        ua = _ensure_publish_user_account(request, org)
    except PermissionError as exc:
        messages.error(request, str(exc))
        return redirect('tender-list')

    projects = InfraProject.objects.filter(
        owner_org=org, is_active=True
    ).select_related('task')
    countries = Country.objects.filter(is_active=True).order_by('name')
    form_ctx = {
        'projects': projects,
        'countries': countries,
        'TENDER_TYPES': TenderListing.TENDER_TYPE_CHOICES,
        'VISIBILITY': TenderListing.VISIBILITY_CHOICES,
        'FUNDING_TYPES': TenderListing.FUNDING_CHOICES,
        'SECTORS': [
            ('ROADS', 'Roads & Bridges'),
            ('BUILDINGS', 'Buildings'),
            ('WATER', 'Water & Sanitation'),
            ('ENERGY', 'Energy'),
            ('ICT', 'ICT Infrastructure'),
            ('OTHER', 'Other'),
        ],
        **branding_template_context(request),
    }

    if request.method == 'POST':
        p = request.POST

        project_id = p.get('project_id')
        create_new = p.get('create_new_project') == '1' or not project_id
        ref = p.get('ref', '').strip()
        description = p.get('description', '').strip()
        tender_type = p.get('tender_type', TenderListing.WORKS)
        visibility = p.get('visibility', TenderListing.PUBLIC)
        funding = p.get('funding_source', TenderListing.GOV)
        country_code = p.get('country', '')
        county_region = p.get('county_region', '').strip()
        sector = p.get('sector', 'BUILDINGS').strip() or 'BUILDINGS'
        issue_date = p.get('issue_date')
        closing_date = p.get('closing_date')
        summary = p.get('summary', '').strip()
        val_min_raw = p.get('value_min', '').replace(',', '')
        val_max_raw = p.get('value_max', '').replace(',', '')
        currency = p.get('currency', 'KES').strip()
        boq_file = request.FILES.get('boq_document')

        errors = []
        if not ref:
            errors.append('Tender reference is required.')
        if not description:
            errors.append('Description is required.')
        if not issue_date:
            errors.append('Issue date is required.')
        if not closing_date:
            errors.append('Closing date is required.')
        if not boq_file:
            errors.append('Upload the tender BOQ PDF from your local drive.')
        if EvaluationEvent.objects.filter(ref=ref).exists():
            errors.append(f'Tender reference {ref} already exists.')
        if not create_new and not project_id:
            errors.append('Select an existing project, or create one with this tender.')

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'tenders/tender_publish.html', form_ctx)

        country = Country.objects.filter(code=country_code).first()
        if create_new:
            project = _create_project_for_tender(
                org,
                project_code=p.get('new_project_code') or ref,
                description=description,
                country=country,
                county_region=county_region,
                sector=sector,
            )
        else:
            project = get_object_or_404(InfraProject, pk=project_id, owner_org=org)

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
            summary=summary or description[:500],
            created_by=ua,
            boq_input_mode=TenderListing.BOQ_PDF_AUTO,
        )

        listing.boq_document = boq_file
        for field in ['specification', 'drawings']:
            f = request.FILES.get(field)
            if f:
                setattr(listing, field, f)
        listing.save()

        if p.get('publish_now') == '1':
            listing.publish(ua)
            messages.success(
                request,
                f'Tender {ref} published to the BuildWatch exchange with BOQ PDF.',
            )
            return redirect('tender-detail', listing_id=listing.pk)

        messages.success(
            request,
            f'Tender {ref} saved as draft. Publish it when ready.',
        )
        return redirect('tender-manage', listing_id=listing.pk)

    return render(request, 'tenders/tender_publish.html', form_ctx)


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


def _send_subcontract_main_signed_agreement(arrangement, request=None):
    """Email the main contractor that the signed Domestic Sub Contract is on file."""
    from accounts.emails import send_system_email, _site_base_url

    main = arrangement.main_organisation
    to_email = (getattr(main, "email", None) or "").strip()
    if not to_email:
        return False, "Main contractor organisation has no email on file."

    base = _site_base_url(request)
    detail_url = f"{base}/tenders/{arrangement.tender_id}/bid/subcontract/{arrangement.pk}/"
    agree_url = f"{detail_url}agreement/"
    main_name = main.name or main.short_name or "Main contractor"
    ref = arrangement.tender.event.ref
    subject = f"BuildWatch - Signed Domestic Sub Contract received - {ref}"
    text_body = (
        f"A signed Domestic Sub Contract (MR14) from {arrangement.sub_company_name} "
        f"has been uploaded for tender {ref}.\n\n"
        f"Main contractor: {main_name}\n"
        f"Sub-contractor: {arrangement.sub_company_name}\n"
        f"Contact: {arrangement.sub_email}\n"
        f"Packages: {', '.join(arrangement.selected_codes()) or '-'}\n\n"
        f"View agreement:\n{agree_url}\n"
        f"Subcontract hub:\n{detail_url}\n"
    )
    return send_system_email(
        subject=subject,
        to=to_email,
        text_body=text_body,
        include_ceo_cc=False,
    )


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

    # Prefill from Filter 2 on BOQ workspace (?type=A|B&pkg=...)
    type_q = (request.GET.get("type") or "").strip().upper()
    if type_q in {"B", "TYPE_B", "NOMINATED"}:
        prefill_type = SubcontractArrangement.NOMINATED
    else:
        prefill_type = SubcontractArrangement.DOMESTIC
    prefill_packages = [
        c.strip().upper() for c in request.GET.getlist("pkg") if c.strip()
    ]
    if not prefill_packages:
        prefill_packages = workspace.selected_codes()

    return render(
        request,
        "tenders/bid_subcontract.html",
        {
            "listing": listing,
            "workspace": workspace,
            "packages": packages,
            "arrangements": ctx["arrangements"],
            "selected_codes": prefill_packages or workspace.selected_codes(),
            "prefill_type": prefill_type,
            "DOMESTIC": SubcontractArrangement.DOMESTIC,
            "NOMINATED": SubcontractArrangement.NOMINATED,
        },
    )


def _arrangement_for_listing(listing_id, pk):
    listing = get_object_or_404(TenderListing, pk=listing_id, is_published=True)
    arrangement = get_object_or_404(
        SubcontractArrangement.objects.select_related(
            "main_organisation",
            "sub_organisation",
            "tender",
            "tender__event",
        ),
        pk=pk,
        tender=listing,
    )
    if arrangement.status == SubcontractArrangement.CANCELLED:
        return listing, arrangement, False
    return listing, arrangement, True


def _subcontract_package_labels(listing, arrangement):
    codes = set(arrangement.selected_codes())
    return {
        p.code.upper(): p.title
        for p in TenderBoqPackage.objects.filter(tender=listing).order_by(
            "sort_order", "code"
        )
        if p.code.upper() in codes
    }


def _fmt_dt(dt):
    if not dt:
        return ""
    try:
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return timezone.localtime(dt).strftime("%d %b %Y - %H:%M")
    except Exception:
        try:
            return dt.strftime("%d %b %Y - %H:%M")
        except Exception:
            return ""


def _main_bid_workspace(arrangement):
    """Main contractor BOQ workspace for this subcontract tender."""
    if arrangement.workspace_id:
        return arrangement.workspace
    return BidWorkspace.objects.filter(
        tender_id=arrangement.tender_id,
        organisation_id=arrangement.main_organisation_id,
    ).first()


def _handle_subcontract_agreement_upload(arrangement, request, workspace=None):
    """Sub or main uploads signed Domestic Sub Contract; email main contractor."""
    f = request.FILES.get("agreement_file")
    if not f:
        return False, "Choose a signed agreement PDF to upload."

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
    ws = workspace or _main_bid_workspace(arrangement)
    if ws:
        _link_mr14_from_subcontract(ws, arrangement)
    ok, err = _send_subcontract_main_signed_agreement(arrangement, request)
    if ok:
        return True, (
            "Signed copy uploaded and emailed to the main contractor."
        )
    return True, (
        "Signed copy uploaded. Email to main contractor failed: "
        f"{err}"
    )


def _subcontract_progress(arrangement, workspace=None):
    """
    Progress steps driven by real activities (portal, upload, main bid submit, award).
    """
    ws = workspace or _main_bid_workspace(arrangement)
    qs = arrangement.quote_status or ""

    invited = bool(arrangement.invited_at or arrangement.invite_email_sent)
    accepted = bool(
        arrangement.accepted_at
        or arrangement.status
        in {
            SubcontractArrangement.ACCEPTED,
            SubcontractArrangement.AGREEMENT_UPLOADED,
            SubcontractArrangement.SHARED_WITH_SPONSOR,
        }
    )
    quote_submitted = qs in {
        SubcontractArrangement.QUOTE_SUBMITTED,
        SubcontractArrangement.QUOTE_ACKNOWLEDGED,
        SubcontractArrangement.QUOTE_INCLUDED,
        SubcontractArrangement.AWARD_NOTED,
    }
    quote_draft = qs == SubcontractArrangement.QUOTE_DRAFT
    agreement_ok = bool(arrangement.agreement_file and arrangement.agreement_uploaded_at)
    main_bid_submitted = bool(
        ws and ws.status == BidWorkspace.SUBMITTED and ws.submitted_at
    ) or qs in {
        SubcontractArrangement.QUOTE_INCLUDED,
        SubcontractArrangement.AWARD_NOTED,
    }
    main_bid_at = _fmt_dt(ws.submitted_at) if ws and ws.submitted_at else _fmt_dt(
        arrangement.included_in_main_bid_at
    )
    evaluation_complete = qs == SubcontractArrangement.AWARD_NOTED
    award_ok = bool(arrangement.award_noted_at or evaluation_complete)

    steps = [
        {
            "key": "invite",
            "label": "Invite sent",
            "done": invited,
            "at": _fmt_dt(arrangement.invited_at),
            "detail": (
                "Portal invitation emailed"
                if arrangement.invite_email_sent
                else (
                    f"Email failed: {arrangement.invite_email_error}"
                    if arrangement.invite_email_error
                    else "Invite created"
                )
            ),
            "pending": "Send portal invite to the sub-contractor",
            "action": "resend_invite",
        },
        {
            "key": "accepted",
            "label": "Portal opened",
            "done": accepted,
            "at": _fmt_dt(arrangement.accepted_at),
            "detail": "Sub-contractor opened the pricing portal",
            "pending": "Open pricing portal",
            "action": "open_portal",
        },
        {
            "key": "quote",
            "label": "Sub Contract Quotation submitted",
            "done": quote_submitted,
            "at": _fmt_dt(arrangement.quote_submitted_at),
            "detail": (
                f"KES {arrangement.quote_total:,.2f} submitted to main contractor"
                if quote_submitted and arrangement.quote_total
                else "Quote submitted to main contractor"
            ),
            "pending": (
                "Pricing in progress — save and submit in portal"
                if quote_draft
                else "Price Sub Contract Item's and submit quote"
            ),
            "action": "open_portal",
        },
        {
            "key": "agreement",
            "label": "Sub Contract Signed and emailed to Main Contractor",
            "done": agreement_ok,
            "at": _fmt_dt(arrangement.agreement_uploaded_at) if agreement_ok else "",
            "detail": (
                f"Done : {_fmt_dt(arrangement.agreement_uploaded_at)}"
                if agreement_ok
                else ""
            ),
            "pending": "Upload Signed Copy Email to main contractor",
            "action": "upload_agreement",
        },
        {
            "key": "main_bid",
            "label": "Main Contracter Submits Bid",
            "done": main_bid_submitted,
            "at": main_bid_at,
            "detail": (
                "Main bid submitted to employer"
                + (
                    f" · KES {ws.total_bid_amount:,.2f}"
                    if ws and ws.total_bid_amount
                    else ""
                )
            ),
            "pending": "Main contractor to submit bid from BOQ workspace",
            "action": "main_bid_workspace",
        },
        {
            "key": "evaluation",
            "label": "Waiting Final Bid Evaluation",
            "done": evaluation_complete,
            "at": (
                _fmt_dt(arrangement.included_in_main_bid_at)
                if main_bid_submitted
                else ""
            ),
            "detail": (
                "Employer evaluation complete · main contractor awarded"
                if evaluation_complete
                else "Bid lodged with employer · awaiting evaluation outcome"
            ),
            "pending": "Waiting final bid evaluation by employer",
            "action": "wait_evaluation",
        },
        {
            "key": "execution",
            "label": "Execution",
            "done": award_ok,
            "at": _fmt_dt(arrangement.award_noted_at),
            "detail": (
                "Execution phase started"
                + (" · email sent" if arrangement.award_note_sent else "")
            ),
            "pending": "Notify sub when main contractor is awarded",
            "action": "notify_award",
        },
    ]

    complete = all(s["done"] for s in steps)
    found_current = False
    for step in steps:
        if complete or step["done"]:
            step["state"] = "done"
        elif not found_current:
            step["state"] = "current"
            found_current = True
        else:
            step["state"] = "pending"

    current = next((s for s in steps if s["state"] == "current"), None)
    if complete:
        pending_label = ""
        pending_key = ""
        pending_action = ""
    else:
        pending_label = (current or {}).get("pending") or ""
        pending_key = (current or {}).get("key") or ""
        pending_action = (current or {}).get("action") or ""

    return {
        "steps": steps,
        "current": current,
        "complete": complete,
        "pending_label": pending_label,
        "pending_key": pending_key,
        "pending_action": pending_action,
        "workspace": ws,
    }


def _as_agreement_date(value):
    """Coerce stored datetimes/dates to a local calendar date for the MR14 form."""
    from datetime import date as date_cls
    from datetime import datetime as datetime_cls

    if value is None:
        value = timezone.now()
    if isinstance(value, date_cls) and not isinstance(value, datetime_cls):
        return value
    if isinstance(value, datetime_cls):
        try:
            if timezone.is_naive(value):
                value = timezone.make_aware(value, timezone.get_current_timezone())
            return timezone.localtime(value).date()
        except Exception:
            return value.date() if hasattr(value, "date") else timezone.localdate()
    return timezone.localdate()


def _domestic_agreement_context(request, listing, arrangement):
    package_labels = _subcontract_package_labels(listing, arrangement)
    main = arrangement.main_organisation
    sub_name = arrangement.sub_company_name or "Domestic Sub-Contractor"
    sub_code = ""
    try:
        if arrangement.sub_organisation_id and arrangement.sub_organisation:
            sub_name = (
                arrangement.sub_organisation.name
                or arrangement.sub_organisation.short_name
                or sub_name
            )
            sub_code = arrangement.sub_organisation.org_code or ""
    except Exception:
        pass
    agreement_date = _as_agreement_date(
        arrangement.agreement_uploaded_at
        or arrangement.accepted_at
        or arrangement.invited_at
        or arrangement.created_at
    )
    return {
        "listing": listing,
        "arrangement": arrangement,
        "package_labels": package_labels,
        "main_name": (main.name or main.short_name or "Main Contractor") if main else "Main Contractor",
        "main_code": (main.org_code or "") if main else "",
        "sub_name": sub_name,
        "sub_code": sub_code,
        "agreement_date": agreement_date,
        "generated_at": timezone.now(),
        "mr14_text": MR14_RFQ_TEXT,
        "hub_url": f"/tenders/{listing.pk}/bid/subcontract/{arrangement.pk}/",
        "pdf_url": f"/tenders/{listing.pk}/bid/subcontract/{arrangement.pk}/agreement.pdf",
        **branding_template_context(request),
    }


def bid_subcontract_detail(request, listing_id, pk):
    """
    Subcontract hub for one arrangement.

    While SUBCONTRACT_OPEN_CYCLE is on, guests (no password) can open this URL to
    view / process / submit via the portal and to open the Domestic Contractor
    Agreement. Main-contractor admins who are signed in still get management tools.
    """
    from django.conf import settings

    listing, arrangement, open_ok = _arrangement_for_listing(listing_id, pk)
    if not open_ok:
        messages.error(request, "This subcontract arrangement has been cancelled.")
        return redirect("tender-detail", listing_id=listing_id)

    package_labels = _subcontract_package_labels(listing, arrangement)
    portal_path = f"/tenders/subcontract/portal/{arrangement.invite_token}/"
    ws = _main_bid_workspace(arrangement)
    org = None
    if request.user.is_authenticated:
        org = get_active_organization(request)
    is_main_admin = bool(
        request.user.is_authenticated
        and org
        and org.org_code == arrangement.main_organisation_id
    )

    if request.method == "POST" and not is_main_admin:
        action = (request.POST.get("action") or "").strip()
        if action == "upload_agreement":
            ok, msg = _handle_subcontract_agreement_upload(
                arrangement, request, workspace=ws
            )
            if ok and "failed" not in msg.lower():
                messages.success(request, msg)
            elif ok:
                messages.warning(request, msg)
            else:
                messages.error(request, msg)
        return redirect("bid-subcontract-detail", listing_id=listing_id, pk=pk)

    # Public / open-cycle hub: view process + agreement without login
    if not is_main_admin:
        if not getattr(settings, "SUBCONTRACT_OPEN_CYCLE", True):
            messages.error(
                request,
                "Sign in as the main contractor to manage this subcontract.",
            )
            return redirect("login")
        return render(
            request,
            "tenders/subcontract_public_hub.html",
            {
                "listing": listing,
                "arrangement": arrangement,
                "package_labels": package_labels,
                "progress": _subcontract_progress(arrangement, workspace=ws),
                "portal_path": portal_path,
                **branding_template_context(request),
            },
        )

    ctx = _bid_subcontract_context(request, listing_id)
    if ctx is None:
        return redirect("tender-detail", listing_id=listing_id)

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
            ok, msg = _handle_subcontract_agreement_upload(
                arrangement, request, workspace=ctx["workspace"]
            )
            if ok and "failed" not in msg.lower():
                messages.success(
                    request,
                    msg + " MR14 on your certificate checklist is now satisfied.",
                )
            elif ok:
                messages.warning(
                    request,
                    msg + " MR14 on your certificate checklist is now satisfied.",
                )
            else:
                messages.error(request, msg)
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

    return render(
        request,
        "tenders/bid_subcontract_detail.html",
        {
            "listing": listing,
            "arrangement": arrangement,
            "package_labels": package_labels,
            "portal_path": portal_path,
            "accept_path": portal_path,
            "progress": _subcontract_progress(arrangement, workspace=ctx["workspace"]),
            **branding_template_context(request),
        },
    )


def bid_subcontract_agreement(request, listing_id, pk):
    """
    GET /tenders/<id>/bid/subcontract/<pk>/agreement/
    View the Domestic Sub Contract Agreement (MR14) — no password required.
    """
    listing, arrangement, open_ok = _arrangement_for_listing(listing_id, pk)
    if not open_ok:
        messages.error(request, "This subcontract arrangement has been cancelled.")
        return redirect("tender-detail", listing_id=listing_id)
    try:
        ctx = _domestic_agreement_context(request, listing, arrangement)
        return render(request, "tenders/domestic_contractor_agreement.html", ctx)
    except Exception as exc:
        messages.error(request, f"Could not open the Domestic Sub Contract: {exc}")
        return redirect("bid-subcontract-detail", listing_id=listing_id, pk=pk)


def bid_subcontract_agreement_pdf(request, listing_id, pk):
    """PDF download of the Domestic Sub Contract Agreement (MR14)."""
    from accounts.misc_doc_pdf import build_pdf_bytes, pdf_attachment_response

    listing, arrangement, open_ok = _arrangement_for_listing(listing_id, pk)
    if not open_ok:
        messages.error(request, "This subcontract arrangement has been cancelled.")
        return redirect("tender-detail", listing_id=listing_id)
    try:
        ctx = _domestic_agreement_context(request, listing, arrangement)
        ctx["pdf_url"] = ""
        pdf_bytes = build_pdf_bytes(
            "tenders/domestic_contractor_agreement.html", ctx
        )
        ref = (listing.event.ref or "tender").replace("/", "-")
        return pdf_attachment_response(
            pdf_bytes,
            f"MR14_Domestic_Sub_Contract_{ref}_arr{arrangement.pk}.pdf",
        )
    except Exception as exc:
        messages.error(
            request,
            f"PDF export failed ({exc}). Opening the printable agreement page instead.",
        )
        return redirect("bid-subcontract-agreement", listing_id=listing_id, pk=pk)


def subcontract_accept(request, token):
    """Legacy URL — send invitees into the authorised pricing portal."""
    return redirect("subcontract-portal", token=token)
