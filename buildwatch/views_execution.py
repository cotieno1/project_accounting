# ============================================================================
# buildwatch/views_execution.py
#
# Contractor "Works Execution" workspace: break a tender's BOQ into
# Task A -> sub-tasks A-1..n, drive each to completion (start -> inspection ->
# approval -> completion certificate) and watch profitability (earned value vs
# actual cost from the linked Pioneer ops task).
#
#   works_execution          GET  /tenders/<id>/execution/
#   works_execution_action   POST /tenders/<id>/execution/action/
#   works_subtask_cert_pdf   GET  /tenders/<id>/execution/subtask/<sid>/certificate.pdf
# ============================================================================
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.tenant import branding_template_context

from .execution import generate_wbs_for_tender, wbs_overview
from .models import ComplianceCheckpoint, TenderListing, WorkSubTask
from .views_compliance import _access, _current_ua, _name


def _project(listing):
    return getattr(listing.event, "project", None)


@login_required
def works_execution(request, listing_id):
    listing = get_object_or_404(
        TenderListing.objects.select_related("event", "event__project", "event__project__owner_org"),
        pk=listing_id,
    )
    caps = _access(request, listing)
    if caps is None:
        messages.error(request, "You do not have access to this tender's works execution.")
        return redirect("tender-detail", listing_id=listing.pk)

    project = _project(listing)
    if project is None:
        messages.error(request, "This tender is not linked to a project.")
        return redirect("tender-detail", listing_id=listing.pk)

    overview = wbs_overview(project, listing)
    ctx = {
        "listing": listing,
        "project": project,
        "caps": caps,
        "overview": overview,
        "org_name": getattr(getattr(project, "owner_org", None), "name", ""),
        **branding_template_context(request),
    }
    return render(request, "tenders/works_execution.html", ctx)


@login_required
@require_POST
def works_execution_action(request, listing_id):
    listing = get_object_or_404(
        TenderListing.objects.select_related("event", "event__project"),
        pk=listing_id,
    )
    caps = _access(request, listing)
    if caps is None:
        messages.error(request, "You do not have access to this tender's works execution.")
        return redirect("tender-detail", listing_id=listing.pk)

    project = _project(listing)
    if project is None:
        messages.error(request, "This tender is not linked to a project.")
        return redirect("tender-detail", listing_id=listing.pk)

    ua = _current_ua(request)
    action = (request.POST.get("action") or "").strip()
    can_drive = caps["is_bidder"] or caps["is_admin"]
    can_approve = caps["is_sponsor"] or caps["is_admin"]

    if action == "generate_wbs":
        created = generate_wbs_for_tender(listing, ua)
        if created:
            messages.success(
                request,
                "Work breakdown generated from the BOQ - %d sub-task(s) created across the "
                "trade phases." % created,
            )
        else:
            messages.info(
                request,
                "No new sub-tasks to create. Load the BOQ / compliance checkpoints first, or "
                "the breakdown already exists.",
            )
        return redirect("works-execution", listing_id=listing.pk)

    # Remaining actions target a single sub-task.
    st = get_object_or_404(
        WorkSubTask, pk=request.POST.get("subtask_id"), project=project
    )

    if action == "start_subtask":
        if not can_drive:
            messages.error(request, "Only the contractor can start a sub-task.")
            return redirect("works-execution", listing_id=listing.pk)
        st.status = WorkSubTask.STATUS_IN_PROGRESS
        st.started_at = timezone.now()
        st.started_by = ua
        st.save(update_fields=["status", "started_at", "started_by", "updated_at"])
        _touch_milestone_progress(st)
        messages.success(request, "Started %s - %s." % (st.code, st.name))

    elif action == "request_inspection":
        if not can_drive:
            messages.error(request, "Only the contractor can request inspection.")
            return redirect("works-execution", listing_id=listing.pk)
        st.status = WorkSubTask.STATUS_INSPECTION
        st.save(update_fields=["status", "updated_at"])
        cp = st.checkpoint
        if cp and cp.status in (ComplianceCheckpoint.STATUS_PENDING, ComplianceCheckpoint.STATUS_REJECTED):
            cp.status = ComplianceCheckpoint.STATUS_SUBMITTED
            cp.submitted_at = timezone.now()
            if ua and not cp.responsible_user_id:
                cp.responsible_user = ua
            cp.save(update_fields=["status", "submitted_at", "responsible_user", "updated_at"])
        messages.success(request, "Inspection requested for %s." % st.code)

    elif action == "approve_subtask":
        if not can_approve:
            messages.error(request, "Only the employer / PM can approve an inspection.")
            return redirect("works-execution", listing_id=listing.pk)
        st.status = WorkSubTask.STATUS_APPROVED
        st.approved_at = timezone.now()
        st.approved_by = ua
        st.save(update_fields=["status", "approved_at", "approved_by", "updated_at"])
        cp = st.checkpoint
        if cp and cp.status != ComplianceCheckpoint.STATUS_APPROVED:
            cp.status = ComplianceCheckpoint.STATUS_APPROVED
            cp.signed_off_by = ua
            cp.signed_off_at = timezone.now()
            cp.save(update_fields=["status", "signed_off_by", "signed_off_at", "updated_at"])
        messages.success(request, "Inspected & approved: %s." % st.code)

    elif action == "complete_subtask":
        if not can_drive:
            messages.error(request, "Only the contractor can mark a sub-task complete.")
            return redirect("works-execution", listing_id=listing.pk)
        if not st.is_approved:
            messages.error(request, "Sub-task must be inspected & approved before completion.")
            return redirect("works-execution", listing_id=listing.pk)
        st.status = WorkSubTask.STATUS_DONE
        st.completed_at = timezone.now()
        st.completed_by = ua
        if not st.certificate_ref:
            st.certificate_ref = "WSC-%s-%s" % (
                (listing.event.ref or "T").split("/")[0][:8], st.pk,
            )
        st.save(update_fields=["status", "completed_at", "completed_by", "certificate_ref", "updated_at"])
        messages.success(
            request,
            "Completed %s - completion certificate %s is ready." % (st.code, st.certificate_ref),
        )

    else:
        messages.error(request, "Unknown action.")

    return redirect("works-execution", listing_id=listing.pk)


def _touch_milestone_progress(st):
    from .models import ProjectMilestone

    m = st.milestone
    if m and m.status == ProjectMilestone.STATUS_PENDING:
        m.status = ProjectMilestone.STATUS_IN_PROGRESS
        m.save(update_fields=["status", "updated_at"])


@login_required
def works_subtask_certificate_pdf(request, listing_id, subtask_id):
    listing = get_object_or_404(
        TenderListing.objects.select_related("event", "event__project", "event__project__owner_org"),
        pk=listing_id,
    )
    caps = _access(request, listing)
    if caps is None:
        messages.error(request, "You do not have access to this certificate.")
        return redirect("tender-detail", listing_id=listing.pk)

    project = _project(listing)
    st = get_object_or_404(WorkSubTask, pk=subtask_id, project=project)
    ctx = {
        "listing": listing,
        "project": project,
        "st": st,
        "owner_org": getattr(project, "owner_org", None),
        "approved_by_name": _name(st.approved_by) if st.approved_by_id else "",
        "completed_by_name": _name(st.completed_by) if st.completed_by_id else "",
        "today": timezone.now().date(),
    }
    from accounts.misc_doc_pdf import build_pdf_bytes, pdf_inline_response

    pdf = build_pdf_bytes("tenders/works_subtask_certificate_print.html", ctx)
    ref = (st.certificate_ref or ("subtask-%s" % st.pk)).replace("/", "-")
    return pdf_inline_response(pdf, ref)
