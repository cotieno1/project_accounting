# ============================================================================
# buildwatch/views_open_tender.py
#
# Open Tender - Financial Dashboard
# Public Tender Internal Fin Ops
# ============================================================================
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import ProjectTask
from accounts.tenant import branding_template_context, get_active_organization

from .models import (
    ActivityDependency,
    PublicTenderProfile,
    SubTaskResource,
    SubTaskResourcePhase,
    TenderListing,
    WorkSubTask,
)
from .open_tender import (
    add_resource,
    build_project_wbs,
    ensure_public_profile,
    fin_ops_overview,
    generate_activities_from_boq_lines,
    generate_subtasks_from_boq,
    open_tender_overview,
    set_resource_phases,
)
from .views_compliance import _current_ua, _name


def _contractor_org(request):
    return get_active_organization(request)


def _can_access_profile(request, profile):
    if request.user.is_superuser:
        return True
    org = _contractor_org(request)
    if org and profile.contractor_org_id and org.pk == profile.contractor_org_id:
        return True
    if org and profile.tender.event.project.owner_org_id == org.pk:
        return True
    return False


@login_required
def open_tender_dashboard(request):
    """Open Tender - Financial Dashboard: list PUBLIC_TENDER (and siblings) profiles."""
    org = _contractor_org(request)
    qs = PublicTenderProfile.objects.select_related(
        "tender", "tender__event", "tender__event__project", "contractor_org", "task",
    )
    if not request.user.is_superuser and org:
        qs = qs.filter(contractor_org=org) | qs.filter(
            tender__event__project__owner_org=org
        )
    profiles = list(qs.distinct())
    rows = []
    for p in profiles:
        subs = p.subtasks.all()
        total = subs.count()
        done = subs.filter(status=WorkSubTask.STATUS_DONE).count()
        rows.append({
            "profile": p,
            "ref": p.tender.event.ref,
            "title": p.tender.event.description,
            "category": p.get_category_display(),
            "subtasks": total,
            "done": done,
            "pct": int(round(done * 100 / total)) if total else 0,
        })

    # Awarded / registered tenders not yet turned into an Open Tender task.
    candidates = []
    if org:
        from .models import BidderRegistration
        linked = set(PublicTenderProfile.objects.values_list("tender_id", flat=True))
        regs = (
            BidderRegistration.objects.filter(organisation=org)
            .select_related("tender", "tender__event")
            .exclude(tender_id__in=linked)
        )
        for r in regs:
            candidates.append(r.tender)

    ctx = {
        "rows": rows,
        "candidates": candidates,
        "org_name": getattr(org, "name", ""),
        **branding_template_context(request),
    }
    return render(request, "tenders/open_tender_dashboard.html", ctx)


@login_required
def open_tender_detail(request, task_id):
    profile = get_object_or_404(
        PublicTenderProfile.objects.select_related(
            "tender", "tender__event", "tender__event__project", "contractor_org", "task",
        ),
        pk=task_id,
    )
    if not _can_access_profile(request, profile):
        messages.error(request, "You do not have access to this Open Tender dashboard.")
        return redirect("open-tender-dashboard")
    overview = open_tender_overview(profile)
    ctx = {
        "overview": overview,
        "profile": profile,
        "org_name": getattr(_contractor_org(request), "name", ""),
        **branding_template_context(request),
    }
    return render(request, "tenders/open_tender_detail.html", ctx)


@login_required
def tender_project_wbs(request, listing_id):
    """Complete Project WBS for Pioneer from the tender BOQ (packages -> activities)."""
    listing = get_object_or_404(
        TenderListing.objects.select_related("event", "event__project"),
        pk=listing_id,
        is_published=True,
    )
    wbs = build_project_wbs(listing)
    profile = PublicTenderProfile.objects.filter(tender=listing).first()
    ctx = {
        "listing": listing,
        "wbs": wbs,
        "profile": profile,
        "org_name": getattr(_contractor_org(request), "name", ""),
        **branding_template_context(request),
    }
    return render(request, "tenders/project_wbs.html", ctx)


@login_required
@require_POST
def open_tender_action(request, task_id):
    profile = get_object_or_404(PublicTenderProfile, pk=task_id)
    if not _can_access_profile(request, profile):
        messages.error(request, "Access denied.")
        return redirect("open-tender-dashboard")

    ua = _current_ua(request)
    action = (request.POST.get("action") or "").strip()

    if action == "generate_subtasks":
        n = generate_subtasks_from_boq(profile, ua)
        if n:
            messages.success(
                request,
                "Generated %d sub-task(s) from priced BOQ categories + internal items." % n,
            )
        else:
            messages.info(request, "No new sub-tasks to create (already seeded).")
        return redirect("open-tender-detail", task_id=profile.pk)

    if action == "generate_activities":
        # Ensure category sub-tasks exist first.
        generate_subtasks_from_boq(profile, ua)
        result = generate_activities_from_boq_lines(profile, with_draft_budget=True)
        messages.success(
            request,
            "Activities from BOQ lines: %d new; draft activity-budget lines: %d "
            "(pilot: R.C Frame + Internal Finishes / tiling)."
            % (result["activities"], result["budget_lines"]),
        )
        return redirect("open-tender-detail", task_id=profile.pk)

    st = get_object_or_404(WorkSubTask, pk=request.POST.get("subtask_id"), profile=profile)

    def _advance(to_status, ok_msg, extra_fields=None):
        if not st.can_advance_to(to_status):
            messages.error(
                request,
                "Gate order is finish-to-start on this sub-task. Next allowed step: %s (now %s)."
                % (st.next_gate() or "none - complete", st.status),
            )
            return False
        st.status = to_status
        fields = ["status", "updated_at"]
        if extra_fields:
            for k, v in extra_fields.items():
                setattr(st, k, v)
                fields.append(k)
            fields = list(dict.fromkeys(fields))
        st.save(update_fields=fields)
        messages.success(request, ok_msg)
        return True

    def _fs_ok_to_start():
        blockers = []
        for link in st.predecessor_links.select_related("predecessor_subtask"):
            if not link.is_satisfied():
                blockers.append(
                    "%s must reach %s first"
                    % (link.predecessor_subtask.code, link.required_status)
                )
        return blockers

    if action == "start_subtask":
        blockers = _fs_ok_to_start()
        if blockers:
            messages.error(
                request,
                "Cannot start %s yet (FS dependency): %s"
                % (st.code, "; ".join(blockers)),
            )
        else:
            _advance(
                WorkSubTask.STATUS_IN_PROGRESS,
                "Started %s (work in progress). Parallel OK with other sub-tasks unless FS-linked."
                % st.code,
                {"started_at": timezone.now(), "started_by": ua},
            )

    elif action == "request_inspection":
        _advance(
            WorkSubTask.STATUS_INSPECTION,
            "Inspection requested for %s." % st.code,
        )

    elif action == "signoff_subtask":
        authority = (request.POST.get("signoff_authority") or "").strip()
        _advance(
            WorkSubTask.STATUS_INSPECTED,
            "Inspected %s (%s)." % (st.code, authority or "QA / MoW / local"),
            {
                "inspected_at": timezone.now(),
                "inspected_by": ua,
                "signoff_authority": authority[:200],
            },
        )

    elif action == "certify_subtask":
        products = (request.POST.get("certified_products") or "")[:4000]
        proof = (request.POST.get("proof_notes") or "")[:4000]
        ref = st.certificate_ref
        if not ref:
            base = (profile.tender.event.ref or "T").split("/")[0][:8]
            ref = "OTC-%s-%s" % (base, st.pk)
        _advance(
            WorkSubTask.STATUS_CERTIFIED,
            "Certified %s - %s (proof retained for audit)." % (st.code, ref),
            {
                "certified_products": products,
                "proof_notes": proof,
                "certificate_ref": ref,
                "completed_at": timezone.now(),
                "completed_by": ua,
            },
        )

    elif action == "authorize_subtask":
        _advance(
            WorkSubTask.STATUS_AUTHORIZED,
            "Authorized (Engineer nod): %s." % st.code,
            {"approved_at": timezone.now(), "approved_by": ua},
        )

    elif action == "mark_payable":
        _advance(
            WorkSubTask.STATUS_PAYABLE,
            "%s is payable - raise payment certificate then RO -> PV." % st.code,
        )

    elif action == "mark_paid":
        _advance(
            WorkSubTask.STATUS_PAID,
            "%s marked paid (PV / funds transferred)." % st.code,
        )

    elif action == "add_fs_dependency":
        pred = get_object_or_404(
            WorkSubTask, pk=request.POST.get("predecessor_id"), profile=profile,
        )
        succ = get_object_or_404(
            WorkSubTask, pk=request.POST.get("successor_id"), profile=profile,
        )
        if pred.pk == succ.pk:
            messages.error(request, "A sub-task cannot depend on itself.")
        else:
            req = (request.POST.get("required_status") or WorkSubTask.STATUS_AUTHORIZED)[:15]
            ActivityDependency.objects.update_or_create(
                predecessor_subtask=pred,
                successor_subtask=succ,
                defaults={
                    "profile": profile,
                    "dep_type": ActivityDependency.TYPE_FS,
                    "required_status": req,
                    "note": (request.POST.get("note") or "")[:200],
                },
            )
            messages.success(
                request,
                "FS link: %s must reach %s before %s may start. Other sub-tasks stay parallel."
                % (pred.code, req, succ.code),
            )

    # Legacy alias from older UI
    elif action == "complete_subtask":
        messages.error(
            request,
            "Use Certify -> Authorize -> Payable -> Paid (confirmed gate order).",
        )
    else:
        messages.error(request, "Unknown action.")

    return redirect("open-tender-detail", task_id=profile.pk)


@login_required
def public_tender_fin_ops(request, task_id=None):
    """Public Tender Internal Fin Ops - products/resources with phased quantities."""
    org = _contractor_org(request)
    if task_id:
        profile = get_object_or_404(
            PublicTenderProfile.objects.select_related("tender", "tender__event", "task"),
            pk=task_id,
        )
        if not _can_access_profile(request, profile):
            messages.error(request, "Access denied.")
            return redirect("public-tender-fin-ops-index")
        overview = fin_ops_overview(profile)
        ctx = {
            "overview": overview,
            "profile": profile,
            "subtasks": list(profile.subtasks.all()),
            "org_name": getattr(org, "name", ""),
            **branding_template_context(request),
        }
        return render(request, "tenders/public_tender_fin_ops.html", ctx)

    qs = PublicTenderProfile.objects.select_related("tender", "tender__event", "task")
    if not request.user.is_superuser and org:
        qs = qs.filter(contractor_org=org) | qs.filter(
            tender__event__project__owner_org=org
        )
    ctx = {
        "profiles": list(qs.distinct()),
        "org_name": getattr(org, "name", ""),
        **branding_template_context(request),
    }
    return render(request, "tenders/public_tender_fin_ops_index.html", ctx)


@login_required
@require_POST
def public_tender_fin_ops_action(request, task_id):
    profile = get_object_or_404(PublicTenderProfile, pk=task_id)
    if not _can_access_profile(request, profile):
        messages.error(request, "Access denied.")
        return redirect("public-tender-fin-ops-index")

    action = (request.POST.get("action") or "").strip()

    if action == "add_resource":
        st = get_object_or_404(WorkSubTask, pk=request.POST.get("subtask_id"), profile=profile)
        try:
            qty = Decimal(request.POST.get("total_qty") or "0")
        except (InvalidOperation, TypeError):
            qty = Decimal("0")
        add_resource(
            st,
            name=request.POST.get("name") or "Resource",
            resource_kind=request.POST.get("resource_kind") or SubTaskResource.KIND_MATERIAL,
            unit=request.POST.get("unit") or "No",
            total_qty=qty,
            notes=request.POST.get("notes") or "",
        )
        messages.success(request, "Resource added under %s." % st.code)

    elif action == "set_phases":
        resource = get_object_or_404(
            SubTaskResource, pk=request.POST.get("resource_id"), subtask__profile=profile,
        )
        raw = (request.POST.get("phase_qtys") or "").strip()
        # Comma-separated quantities e.g. "5000,2500,2500"
        parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
        try:
            qtys = [Decimal(p) for p in parts]
        except (InvalidOperation, TypeError):
            messages.error(request, "Phase quantities must be numbers, e.g. 5000,2500,2500")
            return redirect("public-tender-fin-ops", task_id=profile.pk)
        if not qtys:
            messages.error(request, "Provide at least one phase quantity.")
            return redirect("public-tender-fin-ops", task_id=profile.pk)
        set_resource_phases(resource, qtys)
        messages.success(
            request,
            "Phased %s into %d phase(s)." % (resource.name, len(qtys)),
        )

    elif action == "raise_phase_ro":
        phase = get_object_or_404(
            SubTaskResourcePhase,
            pk=request.POST.get("phase_id"),
            resource__subtask__profile=profile,
        )
        phase.status = SubTaskResourcePhase.STATUS_RO_RAISED
        phase.ro_ref = (request.POST.get("ro_ref") or phase.ro_ref or "INT-RO-%s" % phase.pk)[:80]
        phase.save(update_fields=["status", "ro_ref"])
        messages.success(
            request,
            "Internal RO raised for %s - %s (qty %s). Continue in RO builder for task %s."
            % (phase.resource.name, phase.phase_name or ("P%s" % phase.phase_index),
               phase.qty, profile.task_id),
        )

    else:
        messages.error(request, "Unknown action.")

    return redirect("public-tender-fin-ops", task_id=profile.pk)


@login_required
@require_POST
def create_open_tender_from_listing(request, listing_id):
    """
    Create / link a PUBLIC_TENDER ProjectTask + profile for an awarded tender.
    Does not modify existing Close Tender tasks.
    """
    listing = get_object_or_404(
        TenderListing.objects.select_related("event", "event__project"),
        pk=listing_id,
    )
    org = _contractor_org(request)
    project = getattr(listing.event, "project", None)
    if project is None:
        messages.error(request, "Tender is not linked to a project.")
        return redirect("tender-detail", listing_id=listing.pk)

    # Prefer a dedicated PUBLIC_TENDER ProjectTask (never steal Close Tender tasks).
    existing = PublicTenderProfile.objects.filter(tender=listing).select_related("task").first()
    if existing:
        profile = existing
        task = existing.task
    else:
        base = "PT-%s" % (listing.event.ref or str(listing.pk)).replace("/", "-").replace(" ", "")[:40]
        candidate = base
        n = 1
        while ProjectTask.objects.filter(project_id=candidate).exists():
            n += 1
            candidate = "%s-%d" % (base[:36], n)
        task = ProjectTask.objects.create(
            project_id=candidate,
            description=("Public Tender: %s" % (listing.event.description or listing.event.ref))[:200],
        )
        profile = ensure_public_profile(
            tender=listing,
            contractor_org=org,
            task=task,
            category=PublicTenderProfile.CATEGORY_PUBLIC_TENDER,
            award_ref=request.POST.get("award_letter_ref") or "",
        )

    generate_subtasks_from_boq(profile)
    messages.success(
        request,
        "Open Tender task %s ready. Use Open Tender Financial Dashboard and Public Tender Internal Fin Ops."
        % task.project_id,
    )
    return redirect("open-tender-detail", task_id=profile.pk)
