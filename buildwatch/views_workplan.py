# -*- coding: utf-8 -*-
"""Project Work Plan workspace - rollout, staggered financing, programme BOM."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.tenant import branding_template_context, get_active_organization
from buildwatch.models import InfraProject
from buildwatch.models_inception import ProjectInception
from buildwatch.models_workplan import ProjectWorkPlan
from buildwatch.workplan.services import get_or_create_work_plan, save_work_plan_from_post


def _username(request) -> str:
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        return user.get_username() or "user"
    return "guest"


def _org_projects(org):
    if org is None:
        return InfraProject.objects.none()
    return (
        InfraProject.objects.filter(owner_org=org, is_active=True)
        .select_related("task")
        .order_by("-created_at")
    )


@login_required
@require_http_methods(["GET", "POST"])
def work_plan_workspace(request, project_id=None):
    """
    Programme work plan for a minted InfraProject:
    BOM + rollout stagger + financing from test to commissioning.
    """
    org = get_active_organization(request)
    projects = list(_org_projects(org))

    project = None
    if project_id:
        project = get_object_or_404(InfraProject, pk=project_id)
        if (
            org
            and project.owner_org_id
            and project.owner_org_id != getattr(org, "pk", None)
            and not request.user.is_superuser
        ):
            messages.error(request, "That project is outside your organisation.")
            return redirect("work-plan-workspace")
    elif projects:
        # Prefer project linked from this org's latest inception
        inception = (
            ProjectInception.objects.filter(sponsor_org=org, infra_project__isnull=False)
            .exclude(stage=ProjectInception.STAGE_CANCELLED)
            .order_by("-updated_at")
            .first()
        )
        if inception and inception.infra_project_id:
            project = inception.infra_project
        else:
            project = projects[0]

    if project is None:
        messages.info(
            request,
            "Approve a Project Concept first so a BuildWatch project identity exists, "
            "then open the Work Plan.",
        )
        return redirect("inception-workspace")

    inception = (
        ProjectInception.objects.filter(infra_project=project).order_by("-updated_at").first()
    )
    who = _username(request)
    plan = get_or_create_work_plan(
        infra_project=project,
        inception=inception,
        profile_id=inception.profile_id if inception else "",
        who=who,
    )

    if request.method == "POST":
        action = (request.POST.get("action") or "save").strip()
        plan = save_work_plan_from_post(plan, request.POST, who)
        if action == "approve_plan":
            plan.status = ProjectWorkPlan.STATUS_APPROVED
            plan.save(update_fields=["status", "updated_at"])
            messages.success(request, "Work plan approved.")
        elif action == "activate_plan":
            plan.status = ProjectWorkPlan.STATUS_ACTIVE
            plan.save(update_fields=["status", "updated_at"])
            messages.success(request, "Work plan marked active for rollout.")
        else:
            messages.success(request, "Work plan saved.")
        return redirect("work-plan-project", project_id=project.pk)

    phases = list(plan.phases.all())
    bom_lines = list(plan.bom_lines.select_related("phase"))
    activities = list(plan.activities.all()[:30])

    ctx = {
        "active_org": org,
        "org_projects": projects,
        "project": project,
        "inception": inception,
        "plan": plan,
        "phases": phases,
        "bom_lines": bom_lines,
        "activities": activities,
        "financing_allocated": plan.financing_allocated,
        "bom_total": plan.bom_total,
        "bw_nav_mode": "inception",
        **branding_template_context(request),
        "org_name": (org.name if org else "") or "",
        "org_short_name": (org.short_name if org else "") or "",
    }
    return render(request, "buildwatch/work_plan_workspace.html", ctx)
