# -*- coding: utf-8 -*-
"""BuildWatch Inception - three-column collaboration workspace."""
from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import UserAccount
from accounts.tenant import branding_template_context, get_active_organization
from buildwatch.inception.collaboration import (
    column_blocks,
    mark_documented_if_ready,
    save_typed_contribution,
    sections_complete,
)
from buildwatch.inception.loader import (
    default_profile_id,
    get_profile,
    list_profiles,
    readiness,
)
from buildwatch.inception.services import (
    TENANT_INCEPTION_DEFAULTS,
    append_activity,
    approve_concept,
    ensure_budget,
    get_or_create_workspace,
    inception_to_brief,
    reset_for_profile_switch,
)
from buildwatch.models_inception import (
    InceptionApproval,
    InceptionDocument,
    InceptionParticipant,
    ProjectInception,
)

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


def _participant(inception, ua):
    if ua is None:
        return None
    return (
        InceptionParticipant.objects.filter(inception=inception, user=ua)
        .select_related("organisation", "user")
        .first()
    )


def _is_sponsor(inception, ua, org) -> bool:
    if ua and inception.sponsor_contact_id == ua.pk:
        return True
    part = _participant(inception, ua)
    if part and part.role == InceptionParticipant.SPONSOR:
        return True
    if org and inception.sponsor_org_id == getattr(org, "pk", None):
        # Org member acting as sponsor contact for this tenant inception
        if part is None or part.role == InceptionParticipant.SPONSOR:
            return True
    return False


def _workspace_context(request, inception, profile):
    org = get_active_organization(request)
    ua = _user_account(request)
    participant = _participant(inception, ua)
    # Auto-accept sponsor contact
    if (
        ua
        and participant is None
        and org
        and inception.sponsor_org_id == getattr(org, "pk", None)
    ):
        participant, _ = InceptionParticipant.objects.get_or_create(
            inception=inception,
            user=ua,
            defaults={
                "role": InceptionParticipant.SPONSOR,
                "organisation": org,
                "accepted": True,
                "accepted_at": timezone.now(),
            },
        )
    cols = column_blocks(inception, inception.profile_id)
    budget = getattr(inception, "concept_budget", None)
    if budget is None:
        budget = ensure_budget(inception, profile, ua)
    brief = inception_to_brief(inception)
    ready = readiness(brief, profile)
    documents = list(inception.documents.all()[:40])
    participants = list(
        inception.participants.select_related("user", "organisation").all()
    )
    is_sponsor = _is_sponsor(inception, ua, org)
    return {
        "product_definition": PRODUCT_DEFINITION,
        "profiles": list_profiles(),
        "profile": profile,
        "inception": inception,
        "brief": brief,
        "readiness": ready,
        "budget": budget,
        "budget_lines": list(budget.lines.all()) if budget else [],
        "documents": documents,
        "participants": participants,
        "participant": participant,
        "is_sponsor": is_sponsor,
        "all_sections_done": sections_complete(inception, inception.profile_id),
        "doc_types": InceptionDocument.DOC_TYPE_CHOICES,
        "approvals": list(inception.approvals.all()[:20]),
        "inception_org": org,
        "active_org": org,
        "bw_nav_mode": "inception",
        **cols,
        **branding_template_context(request),
        "org_name": (org.name if org else "") or "",
        "org_short_name": (org.short_name if org else "") or "",
    }


@login_required
@require_http_methods(["GET"])
def inception_list(request):
    org = get_active_organization(request)
    if org is None:
        messages.error(request, "Organisation required.")
        return redirect("platform_admin")
    rows = (
        ProjectInception.objects.filter(sponsor_org=org)
        .exclude(stage=ProjectInception.STAGE_CANCELLED)
        .order_by("-updated_at")
    )
    return render(
        request,
        "buildwatch/inception_list.html",
        {
            "inceptions": rows,
            "active_org": org,
            "bw_nav_mode": "inception",
            **branding_template_context(request),
            "org_name": org.name or "",
            "org_short_name": org.short_name or "",
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def inception_workspace(request, pk=None):
    """Three-column Sponsor / Business / Technical inception workspace."""
    org = get_active_organization(request)
    if org is None:
        messages.error(
            request,
            "Your account needs an organisation before Project Concept can open.",
        )
        return redirect("platform_admin")

    ua = _user_account(request)
    who = _username(request)
    defaults = TENANT_INCEPTION_DEFAULTS.get(getattr(org, "org_code", "") or "", {})

    if pk:
        inception = get_object_or_404(ProjectInception, pk=pk)
        if (
            inception.sponsor_org_id != getattr(org, "pk", None)
            and not request.user.is_superuser
        ):
            messages.error(request, "That inception is outside your organisation.")
            return redirect("inception-list")
        profile = get_profile(inception.profile_id) or get_profile(default_profile_id())
    else:
        profile_id = (
            request.GET.get("profile")
            or defaults.get("profile_id")
            or default_profile_id()
        )
        profile = get_profile(profile_id) or get_profile(default_profile_id())
        if profile is None:
            messages.error(request, "No inception profiles are configured.")
            return redirect("platform_admin")
        inception = get_or_create_workspace(
            org=org,
            profile_id=profile["id"],
            user_account=ua,
            title=defaults.get("title") or "",
            seed_project_ref=defaults.get("project_ref") or "",
        )
        if request.method == "GET" and request.GET.get("profile"):
            if inception.profile_id != profile["id"]:
                inception = reset_for_profile_switch(inception, profile, who)
        else:
            stored = get_profile(inception.profile_id)
            if stored:
                profile = stored

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "switch_profile":
            new_id = (request.POST.get("profile_pick") or "").strip()
            new_profile = get_profile(new_id)
            if new_profile:
                inception = reset_for_profile_switch(inception, new_profile, who)
                return redirect("inception-detail", pk=inception.pk)
            messages.error(request, "Unknown profile.")
            return redirect("inception-workspace")

        if action == "save_meta":
            inception.title = (request.POST.get("title") or inception.title)[:300]
            inception.county_region = (request.POST.get("county_region") or "")[:100]
            inception.custody_type_id = (request.POST.get("custody_type") or "")[:80]
            inception.custody_status = (request.POST.get("custody_status") or "UNKNOWN")[
                :40
            ]
            inception.funding_type_id = (request.POST.get("funding_type") or "")[:80]
            inception.funding_status = (request.POST.get("funding_status") or "UNFUNDED")[
                :40
            ]
            inception.funding_envelope = (request.POST.get("funding_envelope") or "")[
                :80
            ]
            inception.save()
            # Budget line amounts
            budget = ensure_budget(inception, profile, ua)
            for line in budget.lines.all():
                key = f"budget_line_{line.code}"
                if key in request.POST:
                    from decimal import Decimal, InvalidOperation

                    raw = (request.POST.get(key) or "0").replace(",", "").strip()
                    try:
                        line.amount = Decimal(raw or "0")
                    except (InvalidOperation, ValueError):
                        pass
                    else:
                        line.save(update_fields=["amount"])
            append_activity(inception, "Updated inception metadata / budget", who)
            inception.save(update_fields=["activity_log", "updated_at"])
            mark_documented_if_ready(inception, inception.profile_id)
            messages.success(request, "Saved.")
            return redirect("inception-detail", pk=inception.pk)

    ctx = _workspace_context(request, inception, profile)
    return render(request, "buildwatch/inception_workspace.html", ctx)


@login_required
@require_POST
def inception_contribute(request, pk):
    inception = get_object_or_404(ProjectInception, pk=pk)
    ua = _user_account(request)
    participant = _participant(inception, ua)
    if participant is None or participant.accepted is False:
        return JsonResponse({"ok": False, "error": "Not an accepted participant"}, status=403)
    if participant.accepted is None:
        return JsonResponse({"ok": False, "error": "Accept invitation first"}, status=403)

    ctype = (request.POST.get("contribution_type") or "").strip()[:40]
    content = (request.POST.get("content") or "").strip()
    if not ctype:
        return JsonResponse({"ok": False, "error": "Missing type"}, status=400)

    # Sponsor (or sole org lead) may edit any column during inception
    role = participant.role
    if role not in (
        InceptionParticipant.SPONSOR,
        InceptionParticipant.BUSINESS,
        InceptionParticipant.TECHNICAL,
    ):
        return JsonResponse({"ok": False, "error": "Invalid role"}, status=403)
    if role == InceptionParticipant.BUSINESS and ctype.startswith("TECH"):
        return JsonResponse({"ok": False, "error": "Technical role required"}, status=403)
    if role == InceptionParticipant.TECHNICAL and ctype.startswith("SPONSOR"):
        return JsonResponse({"ok": False, "error": "Sponsor role required"}, status=403)
    if role == InceptionParticipant.BUSINESS and ctype.startswith("SPONSOR"):
        return JsonResponse({"ok": False, "error": "Sponsor role required"}, status=403)
    if role == InceptionParticipant.TECHNICAL and ctype.startswith("BUSINESS"):
        return JsonResponse({"ok": False, "error": "Business role required"}, status=403)

    who = _username(request)
    contrib = save_typed_contribution(
        inception=inception,
        contribution_type=ctype,
        content=content,
        participant=participant,
        who=who,
    )
    append_activity(inception, f"Updated {ctype}", who)
    inception.save(update_fields=["activity_log", "updated_at"])
    mark_documented_if_ready(inception, inception.profile_id)
    return JsonResponse(
        {
            "ok": True,
            "type": ctype,
            "content": contrib.content,
            "stage": inception.stage,
        }
    )


@login_required
@require_POST
def inception_upload(request, pk):
    inception = get_object_or_404(ProjectInception, pk=pk)
    ua = _user_account(request)
    participant = _participant(inception, ua)
    if participant is None or not participant.accepted:
        return JsonResponse({"ok": False, "error": "Not an accepted participant"}, status=403)
    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"ok": False, "error": "No file"}, status=400)
    doc = InceptionDocument.objects.create(
        inception=inception,
        uploaded_by=ua,
        doc_type=(request.POST.get("doc_type") or InceptionDocument.OTHER)[:20],
        title=(request.POST.get("title") or f.name)[:255],
        file=f,
    )
    append_activity(inception, f"Uploaded document {doc.title}", _username(request))
    inception.save(update_fields=["activity_log", "updated_at"])
    return JsonResponse({"ok": True, "title": doc.title, "id": doc.pk})


@login_required
@require_POST
def inception_invite(request, pk):
    inception = get_object_or_404(ProjectInception, pk=pk)
    org = get_active_organization(request)
    ua = _user_account(request)
    if not _is_sponsor(inception, ua, org):
        messages.error(request, "Only the sponsor can invite participants.")
        return redirect("inception-detail", pk=pk)

    email = (request.POST.get("email") or "").strip()
    role = (request.POST.get("role") or InceptionParticipant.TECHNICAL).strip()
    discipline = (request.POST.get("discipline") or "").strip()[:50]
    target = UserAccount.objects.filter(email__iexact=email).select_related(
        "organization"
    ).first()
    if target is None:
        messages.error(request, f"No BuildWatch user with email {email}.")
        return redirect("inception-detail", pk=pk)
    if role not in (
        InceptionParticipant.BUSINESS,
        InceptionParticipant.TECHNICAL,
        InceptionParticipant.SPONSOR,
    ):
        role = InceptionParticipant.TECHNICAL
    part_org = target.organization or inception.sponsor_org
    InceptionParticipant.objects.update_or_create(
        inception=inception,
        user=target,
        defaults={
            "role": role,
            "organisation": part_org,
            "technical_discipline": discipline,
            "accepted": None,
            "accepted_at": None,
        },
    )
    append_activity(inception, f"Invited {email} as {role}", _username(request))
    inception.save(update_fields=["activity_log", "updated_at"])
    messages.success(request, f"Invitation sent to {email}.")
    return redirect("inception-detail", pk=pk)


@login_required
@require_POST
def inception_accept(request, pk):
    inception = get_object_or_404(ProjectInception, pk=pk)
    ua = _user_account(request)
    participant = _participant(inception, ua)
    if participant is None:
        messages.error(request, "No invitation found for your account.")
        return redirect("inception-detail", pk=pk)
    participant.accepted = True
    participant.accepted_at = timezone.now()
    participant.save(update_fields=["accepted", "accepted_at"])
    messages.success(request, "Invitation accepted.")
    return redirect("inception-detail", pk=pk)


@login_required
@require_POST
def inception_submit_review(request, pk):
    inception = get_object_or_404(ProjectInception, pk=pk)
    ua = _user_account(request)
    participant = _participant(inception, ua)
    if not sections_complete(inception, inception.profile_id):
        messages.warning(request, "All three columns must be complete first.")
        return redirect("inception-detail", pk=pk)
    if participant and participant.role not in (
        InceptionParticipant.TECHNICAL,
        InceptionParticipant.SPONSOR,
    ):
        messages.error(request, "Technical lead or sponsor submits for review.")
        return redirect("inception-detail", pk=pk)
    inception.stage = ProjectInception.STAGE_SPONSOR_REVIEW
    append_activity(inception, "Submitted for sponsor review", _username(request))
    inception.save()
    messages.success(request, "Inception submitted for sponsor review.")
    return redirect("inception-detail", pk=pk)


@login_required
@require_POST
def inception_approve(request, pk):
    inception = get_object_or_404(ProjectInception, pk=pk)
    org = get_active_organization(request)
    ua = _user_account(request)
    if not _is_sponsor(inception, ua, org):
        messages.error(request, "Only the sponsor can approve.")
        return redirect("inception-detail", pk=pk)

    action = (request.POST.get("action") or "").strip()
    comments = (request.POST.get("comments") or "").strip()
    who = _username(request)
    profile = get_profile(inception.profile_id) or {}

    if action == InceptionApproval.REVISE:
        InceptionApproval.objects.create(
            inception=inception,
            actioned_by=ua,
            actioned_by_name=who,
            action=InceptionApproval.REVISE,
            comments=comments,
        )
        inception.stage = ProjectInception.STAGE_WORKSHOP
        append_activity(inception, "Returned to workshop for revision", who)
        inception.save()
        messages.info(request, "Returned to workshop.")
        return redirect("inception-detail", pk=pk)

    if action == InceptionApproval.CANCELLED:
        InceptionApproval.objects.create(
            inception=inception,
            actioned_by=ua,
            actioned_by_name=who,
            action=InceptionApproval.CANCELLED,
            comments=comments,
        )
        inception.stage = ProjectInception.STAGE_CANCELLED
        append_activity(inception, "Inception cancelled", who)
        inception.save()
        messages.warning(request, "Inception cancelled.")
        return redirect("inception-list")

    if action == InceptionApproval.APPROVED:
        # Ensure custody/funding minimally set for readiness if sponsor already funded in contrib
        if not inception.funding_envelope and comments:
            inception.funding_envelope = "See approval"
        if not inception.funding_type_id:
            inception.funding_type_id = "commercial"
        if not inception.funding_status or inception.funding_status == "UNFUNDED":
            inception.funding_status = "INDICATIVE"
        if not inception.custody_type_id:
            inception.custody_type_id = "tower_site"
        if not inception.custody_status or inception.custody_status == "UNKNOWN":
            inception.custody_status = "ROUTE_IDENTIFIED"
        inception.save()
        try:
            approval, project = approve_concept(
                inception=inception,
                profile=profile,
                who=who,
                user_account=ua,
                comments=comments,
            )
            ceiling = (request.POST.get("approved_budget") or "").strip()
            if ceiling:
                from decimal import Decimal, InvalidOperation

                try:
                    approval.approved_budget = Decimal(ceiling.replace(",", ""))
                    approval.save(update_fields=["approved_budget"])
                except (InvalidOperation, ValueError):
                    pass
            messages.success(
                request,
                f"Approved. BuildWatch identity: {approval.minted_project_id}.",
            )
            return redirect("work-plan-project", project_id=project.pk)
        except ValueError as exc:
            messages.warning(
                request,
                "Concept gate not ready - complete contributions, custody, and funding. "
                f"({exc})",
            )
            return redirect("inception-detail", pk=pk)

    messages.error(request, "Select a valid decision.")
    return redirect("inception-detail", pk=pk)


@login_required
@require_http_methods(["GET"])
def inception_pack(request, pk):
    inception = get_object_or_404(ProjectInception, pk=pk)
    profile = get_profile(inception.profile_id) or {}
    ctx = _workspace_context(request, inception, profile)
    ctx["pack_mode"] = True
    return render(request, "buildwatch/inception_pack.html", ctx)


@login_required
@require_http_methods(["GET", "POST"])
def concept_budget(request, pk):
    """Jump to budget section on the workspace (TECH_BUDGET entry)."""
    inception = get_object_or_404(ProjectInception, pk=pk)
    if request.method == "POST":
        return inception_workspace(request, pk=pk)
    return redirect(f"/buildwatch/inception/{pk}/#budget-section")
