# -*- coding: utf-8 -*-
"""BuildWatch Inception - collaborative living brief (pre-project).

Phase 1: profile-driven UI + session-backed draft scoped per org + user.
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.tenant import branding_template_context, get_active_organization
from buildwatch.inception.loader import (
    default_profile_id,
    empty_brief,
    get_profile,
    list_profiles,
    readiness,
)

SESSION_STORE = "inception_briefs_by_tenant"
PRODUCT_DEFINITION = (
    "BuildWatch Inception is an open collaboration and decision platform where any "
    "sponsor, business owner, and technical team co-develop a living brief, resolve "
    "asset custody and resource commitment, and earn a project identity through "
    "explicit gates - with sector-specific behaviour supplied by profiles, not "
    "hardcoded in the core."
)

# Known tenant packs: preferred inception profile + working title seed
TENANT_INCEPTION_DEFAULTS = {
    "MTNSS": {
        "profile_id": "ict.telecom_operator",
        "title": "MTN South Sudan - Telecommunications Network Programme",
        "project_ref": "MTN-SSD-TEL-001",
    },
    "MTNTEL": {
        "profile_id": "ict.telecom_operator",
        "title": "MTN South Sudan - Telecommunications Network Programme",
        "project_ref": "MTN-SSD-TEL-001",
    },
}


def _username(request) -> str:
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        return user.get_username() or "user"
    return "guest"


def _tenant_key(request, org) -> str:
    org_code = getattr(org, "org_code", None) or "NONE"
    uid = getattr(getattr(request, "user", None), "id", None) or "anon"
    return f"{org_code}:{uid}"


def _session_store(request) -> dict:
    store = request.session.get(SESSION_STORE)
    if not isinstance(store, dict):
        store = {}
        request.session[SESSION_STORE] = store
    return store


def _load_brief(request, profile: dict, org) -> dict:
    key = _tenant_key(request, org)
    store = _session_store(request)
    stored = store.get(key) or {}
    # Drop legacy shared key so MoW / other tenants cannot leak into this workspace
    request.session.pop("inception_brief_v1", None)

    if (
        stored.get("org_code") == getattr(org, "org_code", None)
        and stored.get("profile_id") == profile.get("id")
        and stored.get("lanes")
    ):
        brief = empty_brief(profile)
        brief.update({k: v for k, v in stored.items() if k != "lanes"})
        for lid, lane in (stored.get("lanes") or {}).items():
            if lid in brief["lanes"]:
                brief["lanes"][lid] = lane
        brief["profile_id"] = profile["id"]
        brief["org_code"] = getattr(org, "org_code", "") or ""
        return brief

    brief = empty_brief(profile)
    brief["org_code"] = getattr(org, "org_code", "") or ""
    defaults = TENANT_INCEPTION_DEFAULTS.get(brief["org_code"] or "", {})
    if defaults.get("title"):
        brief["title"] = defaults["title"]
    if defaults.get("project_ref"):
        brief["seed_project_ref"] = defaults["project_ref"]
    return brief


def _save_brief(request, brief: dict, org) -> None:
    key = _tenant_key(request, org)
    store = _session_store(request)
    brief["org_code"] = getattr(org, "org_code", "") or ""
    store[key] = brief
    request.session[SESSION_STORE] = store
    request.session.modified = True


def _append_activity(brief: dict, text: str, who: str) -> None:
    activity = list(brief.get("activity") or [])
    activity.insert(
        0,
        {
            "at": timezone.now().strftime("%Y-%m-%d %H:%M"),
            "who": who,
            "text": text,
        },
    )
    brief["activity"] = activity[:40]


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
    """Collaborative inception canvas - one living brief, three lanes, gates."""
    org = get_active_organization(request)
    profiles = list_profiles()
    profile_id = _preferred_profile_id(org, request)
    profile = get_profile(profile_id) or get_profile(default_profile_id())
    if profile is None:
        messages.error(request, "No inception profiles are configured.")
        return redirect("platform_admin")

    brief = _load_brief(request, profile, org)
    who = _username(request)

    if request.method == "POST":
        action = (request.POST.get("action") or "save").strip()

        if action == "switch_profile":
            new_id = (
                (request.POST.get("profile_pick") or request.POST.get("profile_id") or "")
                .strip()
            )
            new_profile = get_profile(new_id)
            if new_profile:
                brief = empty_brief(new_profile)
                brief["org_code"] = getattr(org, "org_code", "") or ""
                defaults = TENANT_INCEPTION_DEFAULTS.get(brief["org_code"], {})
                if defaults.get("title"):
                    brief["title"] = defaults["title"]
                if defaults.get("project_ref"):
                    brief["seed_project_ref"] = defaults["project_ref"]
                _append_activity(brief, f"Switched profile to {new_profile.get('title')}", who)
                _save_brief(request, brief, org)
                return redirect(f"{request.path}?profile={new_profile['id']}")
            messages.error(request, "Unknown profile.")
            return redirect("inception-workspace")

        brief["title"] = (request.POST.get("title") or "").strip()[:200]
        for lane in profile.get("lanes") or []:
            lid = lane["id"]
            body = (request.POST.get(f"lane_{lid}") or "").strip()
            prev = (brief.get("lanes") or {}).get(lid) or {}
            if body != (prev.get("body") or ""):
                brief.setdefault("lanes", {})[lid] = {
                    "body": body,
                    "updated_by": who,
                    "updated_at": timezone.now().strftime("%Y-%m-%d %H:%M"),
                }
                _append_activity(brief, f"Updated {lane.get('label', lid)}", who)
            else:
                brief.setdefault("lanes", {})[lid] = prev or {
                    "body": body,
                    "updated_by": "",
                    "updated_at": "",
                }

        custody = brief.setdefault("custody", {})
        custody["type_id"] = (request.POST.get("custody_type") or "").strip()
        custody["status"] = (request.POST.get("custody_status") or "UNKNOWN").strip()
        custody["owner_note"] = (request.POST.get("custody_owner") or "").strip()[:500]
        custody["route_note"] = (request.POST.get("custody_route") or "").strip()[:500]

        funding = brief.setdefault("funding", {})
        funding["type_id"] = (request.POST.get("funding_type") or "").strip()
        funding["status"] = (request.POST.get("funding_status") or "UNFUNDED").strip()
        funding["envelope"] = (request.POST.get("funding_envelope") or "").strip()[:80]
        funding["source_note"] = (request.POST.get("funding_note") or "").strip()[:500]

        _append_activity(brief, "Saved living brief", who)

        if action == "request_concept":
            ready = readiness(brief, profile)
            if not ready["concept_ready"]:
                messages.warning(
                    request,
                    "Concept gate not ready - complete mandate, requirements, "
                    "feasibility, custody, and funding first.",
                )
            else:
                stamp = timezone.now().strftime("%Y%m%d%H%M")
                slug = (brief.get("title") or "initiative").upper().replace(" ", "-")[:24]
                provisional = f"INCEPT-{slug}-{stamp}"
                brief["project_id"] = provisional
                decisions = list(brief.get("decisions") or [])
                decisions.insert(
                    0,
                    {
                        "gate": "concept_approved",
                        "by": who,
                        "at": timezone.now().strftime("%Y-%m-%d %H:%M"),
                        "note": (request.POST.get("decision_note") or "").strip()[:400],
                        "project_id": provisional,
                    },
                )
                brief["decisions"] = decisions
                _append_activity(
                    brief,
                    f"Concept approved - provisional identity {provisional}",
                    who,
                )
                messages.success(
                    request,
                    f"Concept approved. Provisional BuildWatch identity: {provisional}. "
                    "Persistent project minting lands with Django models next.",
                )

        _save_brief(request, brief, org)
        return redirect(f"{request.path}?profile={profile['id']}")

    ready = readiness(brief, profile)
    lanes_ui = []
    for lane in profile.get("lanes") or []:
        data = (brief.get("lanes") or {}).get(lane["id"]) or {}
        lanes_ui.append({**lane, "body": data.get("body", ""), "meta": data})

    ctx = {
        "product_definition": PRODUCT_DEFINITION,
        "profiles": profiles,
        "profile": profile,
        "lanes_ui": lanes_ui,
        "brief": brief,
        "readiness": ready,
        "inception_org": org,
        "inception_user": request.user,
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
        # Force branding to the logged-in tenant (never bleed another org)
        "org_name": (org.name if org else "") or "",
        "org_short_name": (org.short_name if org else "") or "",
    }
    return render(request, "buildwatch/inception_workspace.html", ctx)
