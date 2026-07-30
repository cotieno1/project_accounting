# -*- coding: utf-8 -*-
"""BuildWatch Inception - collaborative living brief (pre-project).

Persisted on ProjectInception (+ related models). Sector packs via profiles.
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from accounts.models import UserAccount
from accounts.tenant import branding_template_context, get_active_organization
from buildwatch.inception.loader import (
    default_profile_id,
    get_profile,
    list_profiles,
    readiness,
)
from buildwatch.inception.services import (
    TENANT_INCEPTION_DEFAULTS,
    approve_concept,
    get_or_create_workspace,
    inception_to_brief,
    reset_for_profile_switch,
    save_workspace_from_post,
)
from buildwatch.models_inception import ProjectInception

PRODUCT_DEFINITION = (
    "BuildWatch Inception is an open collaboration and decision platform where any "
    "sponsor, business owner, and technical team co-develop a living brief, resolve "
    "asset custody and resource commitment, and earn a project identity through "
    "explicit gates - with sector-specific behaviour supplied by profiles, not "
    "hardcoded in the core."
)


def _username(request) -> str:
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        return user.get_username() or "user"
    return "guest"


def _user_account(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None
    return UserAccount.objects.filter(user=user).select_related("organization").first()


def _preferred_profile_id(org, request) -> str:
    org_code = getattr(org, "org_code", "") or ""
    tenant = TENANT_INCEPTION_DEFAULTS.get(org_code, {})
    return (
        request.POST.get("profile_id")
        or request.GET.get("profile")
        or tenant.get("profile_id")
        or default_profile_id()
    )


@login_required
@require_http_methods(["GET", "POST"])
def inception_workspace(request):
    """Collaborative inception canvas backed by ProjectInception."""
    org = get_active_organization(request)
    if org is None:
        messages.error(
            request,
            "Your account needs an organisation before Project Concept can open.",
        )
        return redirect("platform_admin")

    ua = _user_account(request)
    profiles = list_profiles()
    profile_id = _preferred_profile_id(org, request)
    profile = get_profile(profile_id) or get_profile(default_profile_id())
    if profile is None:
        messages.error(request, "No inception profiles are configured.")
        return redirect("platform_admin")

    who = _username(request)
    defaults = TENANT_INCEPTION_DEFAULTS.get(getattr(org, "org_code", "") or "", {})

    inception = get_or_create_workspace(
        org=org,
        profile_id=profile["id"],
        user_account=ua,
        title=defaults.get("title") or "",
        seed_project_ref=defaults.get("project_ref") or "",
    )

    if request.method == "GET":
        if request.GET.get("profile") and inception.profile_id != profile["id"]:
            inception = reset_for_profile_switch(inception, profile, who)
        else:
            stored = get_profile(inception.profile_id)
            if stored:
                profile = stored

    if request.method == "POST":
        action = (request.POST.get("action") or "save").strip()

        if action == "switch_profile":
            new_id = (
                (request.POST.get("profile_pick") or request.POST.get("profile_id") or "")
                .strip()
            )
            new_profile = get_profile(new_id)
            if new_profile:
                inception = reset_for_profile_switch(inception, new_profile, who)
                return redirect(f"{request.path}?profile={new_profile['id']}")
            messages.error(request, "Unknown profile.")
            return redirect("inception-workspace")

        profile = get_profile(inception.profile_id) or profile
        inception = save_workspace_from_post(
            inception=inception,
            profile=profile,
            post=request.POST,
            who=who,
            user_account=ua,
            org=org,
        )

        if action == "request_concept":
            try:
                approval, _project = approve_concept(
                    inception=inception,
                    profile=profile,
                    who=who,
                    user_account=ua,
                    comments=(request.POST.get("decision_note") or "").strip()[:400],
                )
                messages.success(
                    request,
                    f"Concept approved. BuildWatch identity: {approval.minted_project_id}. "
                    "Inception is in Design stage.",
                )
            except ValueError:
                messages.warning(
                    request,
                    "Concept gate not ready - complete mandate, requirements, "
                    "feasibility, custody, and funding first.",
                )

        return redirect(f"{request.path}?profile={profile['id']}")

    brief = inception_to_brief(inception)
    ready = readiness(brief, profile)
    lanes_ui = []
    for lane in profile.get("lanes") or []:
        data = (brief.get("lanes") or {}).get(lane["id"]) or {}
        lanes_ui.append({**lane, "body": data.get("body", ""), "meta": data})

    budget = getattr(inception, "concept_budget", None)
    budget_lines = list(budget.lines.all()) if budget else []

    ctx = {
        "product_definition": PRODUCT_DEFINITION,
        "profiles": profiles,
        "profile": profile,
        "lanes_ui": lanes_ui,
        "brief": brief,
        "readiness": ready,
        "inception": inception,
        "inception_org": org,
        "inception_user": request.user,
        "budget": budget,
        "budget_lines": budget_lines,
        "stage_choices": ProjectInception.STAGE_CHOICES,
        "custody_statuses": [
            ("UNKNOWN", "Unknown"),
            ("UNDER_INQUIRY", "Under inquiry"),
            ("ROUTE_IDENTIFIED", "Route identified"),
            ("ACQUISITION_IN_PROGRESS", "Acquisition in progress"),
            ("SECURED", "Secured"),
            ("PROCEED_AT_RISK", "Proceed at risk (sponsor waiver)"),
        ],
        "funding_statuses": [
            ("UNFUNDED", "Unfunded"),
            ("INDICATIVE", "Indicative"),
            ("BUDGET_PROVISIONED", "Budget provisioned"),
            ("COMMITTED", "Committed"),
            ("RELEASE_PATH_CONFIRMED", "Release path confirmed"),
        ],
        "active_org": org,
        **branding_template_context(request),
        "bw_nav_mode": "inception",
        "org_name": (org.name if org else "") or "",
        "org_short_name": (org.short_name if org else "") or "",
    }
    return render(request, "buildwatch/inception_workspace.html", ctx)
