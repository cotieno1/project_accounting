# -*- coding: utf-8 -*-
"""Services for DB-backed Project Concept / Inception."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from accounts.models import ProjectTask
from buildwatch.inception.loader import get_profile, readiness
from buildwatch.models import Country, InfraProject
from buildwatch.models_inception import (
    ConceptBudget,
    ConceptBudgetLine,
    InceptionApproval,
    InceptionParticipant,
    ProjectInception,
    WorkshopContribution,
)

TENANT_INCEPTION_DEFAULTS = {
    "MTNSS": {
        "profile_id": "ict.telecom_operator",
        "title": "MTN South Sudan - Telecommunications Network Programme",
        "project_ref": "MTN-SSD-TEL-001",
        "sector": "ICT",
    },
    "MTNTEL": {
        "profile_id": "ict.telecom_operator",
        "title": "MTN South Sudan - Telecommunications Network Programme",
        "project_ref": "MTN-SSD-TEL-001",
        "sector": "ICT",
    },
}

PROFILE_SECTOR = {
    "infrastructure.dam": "WATER",
    "ict.telecom_fibre": "ICT",
    "ict.telecom_operator": "ICT",
    "space.lunar_facility": "OTHER",
    "buildings.works": "BUILDINGS",
}

LANE_ROLE = {
    "mandate": InceptionParticipant.SPONSOR,
    "requirements": InceptionParticipant.BUSINESS,
    "feasibility": InceptionParticipant.TECHNICAL,
}


def append_activity(inception: ProjectInception, text: str, who: str) -> None:
    activity = list(inception.activity_log or [])
    activity.insert(
        0,
        {
            "at": timezone.now().strftime("%Y-%m-%d %H:%M"),
            "who": who,
            "text": text,
        },
    )
    inception.activity_log = activity[:40]


def ensure_participant(inception, user_account, org, role: str) -> InceptionParticipant | None:
    if user_account is None or org is None:
        return None
    participant, _ = InceptionParticipant.objects.get_or_create(
        inception=inception,
        user=user_account,
        defaults={
            "role": role,
            "organisation": org,
            "accepted": True,
            "accepted_at": timezone.now(),
        },
    )
    return participant


def seed_budget_lines(budget: ConceptBudget, profile: dict) -> None:
    lines = profile.get("budget_lines") or []
    if not lines:
        return
    existing = {ln.code: ln for ln in budget.lines.all()}
    for i, row in enumerate(lines):
        code = (row.get("id") or row.get("code") or "").strip()
        if not code:
            continue
        label = (row.get("label") or code).strip()
        group = (row.get("group") or "").strip()
        sort_order = int(row.get("sort_order", i * 10))
        if code in existing:
            line = existing[code]
            line.label = label
            line.group = group
            line.sort_order = sort_order
            line.save(update_fields=["label", "group", "sort_order"])
        else:
            ConceptBudgetLine.objects.create(
                budget=budget,
                code=code,
                label=label,
                group=group,
                sort_order=sort_order,
                amount=Decimal("0"),
            )


def ensure_budget(inception: ProjectInception, profile: dict, user_account=None) -> ConceptBudget:
    budget, created = ConceptBudget.objects.get_or_create(
        inception=inception,
        defaults={"prepared_by": user_account},
    )
    if created and user_account and not budget.prepared_by_id:
        budget.prepared_by = user_account
        budget.save(update_fields=["prepared_by"])
    seed_budget_lines(budget, profile)
    return budget


@transaction.atomic
def get_or_create_workspace(
    *,
    org,
    profile_id: str,
    user_account=None,
    title: str = "",
    seed_project_ref: str = "",
) -> ProjectInception:
    """One active (non-cancelled) inception per sponsor org."""
    defaults = TENANT_INCEPTION_DEFAULTS.get(getattr(org, "org_code", "") or "", {})
    profile_id = profile_id or defaults.get("profile_id") or ""
    profile = get_profile(profile_id) or {}
    who = "system"
    if user_account and getattr(user_account, "user_id", None):
        who = user_account.user.get_username() or who

    inception = (
        ProjectInception.objects.filter(sponsor_org=org)
        .exclude(stage=ProjectInception.STAGE_CANCELLED)
        .order_by("-updated_at")
        .first()
    )
    if inception is None:
        inception = ProjectInception(
            sponsor_org=org,
            sponsor_contact=user_account,
            profile_id=profile_id,
            title=title or defaults.get("title") or (profile.get("title") or ""),
            seed_project_ref=seed_project_ref or defaults.get("project_ref") or "",
            sector=defaults.get("sector")
            or PROFILE_SECTOR.get(profile_id, "OTHER"),
            stage=ProjectInception.STAGE_CONCEPT,
        )
        inception.save()
        append_activity(inception, "Inception workspace created", who)
        inception.save(update_fields=["activity_log", "updated_at"])
    else:
        changed = False
        if title and not inception.title:
            inception.title = title
            changed = True
        if seed_project_ref and not inception.seed_project_ref:
            inception.seed_project_ref = seed_project_ref
            changed = True
        if user_account and not inception.sponsor_contact_id:
            inception.sponsor_contact = user_account
            changed = True
        if changed:
            inception.save()

    ensure_budget(inception, get_profile(inception.profile_id) or profile, user_account)
    if user_account and org:
        ensure_participant(
            inception,
            user_account,
            org,
            InceptionParticipant.SPONSOR,
        )
    return inception


def inception_to_brief(inception: ProjectInception) -> dict:
    lanes = {}
    for contrib in inception.contributions.filter(
        contribution_type__in=[
            WorkshopContribution.LANE_MANDATE,
            WorkshopContribution.LANE_REQUIREMENTS,
            WorkshopContribution.LANE_FEASIBILITY,
        ]
    ):
        lanes[contrib.contribution_type] = {
            "body": contrib.content or "",
            "updated_by": contrib.updated_by_name or "",
            "updated_at": contrib.updated_at.strftime("%Y-%m-%d %H:%M")
            if contrib.updated_at
            else "",
        }
    for lid in (
        WorkshopContribution.LANE_MANDATE,
        WorkshopContribution.LANE_REQUIREMENTS,
        WorkshopContribution.LANE_FEASIBILITY,
    ):
        lanes.setdefault(lid, {"body": "", "updated_by": "", "updated_at": ""})

    decisions = []
    for appr in inception.approvals.all()[:20]:
        decisions.append(
            {
                "gate": "concept_approved"
                if appr.action == InceptionApproval.APPROVED
                else appr.action.lower(),
                "by": appr.actioned_by_name
                or (
                    str(appr.actioned_by)
                    if appr.actioned_by_id
                    else ""
                ),
                "at": appr.actioned_at.strftime("%Y-%m-%d %H:%M")
                if appr.actioned_at
                else "",
                "note": appr.comments or "",
                "project_id": appr.minted_project_id or "",
            }
        )

    return {
        "title": inception.title or "",
        "profile_id": inception.profile_id,
        "org_code": getattr(inception.sponsor_org, "org_code", "") or "",
        "seed_project_ref": inception.seed_project_ref or "",
        "inception_ref": inception.inception_ref,
        "stage": inception.stage,
        "stage_label": inception.get_stage_display(),
        "lanes": lanes,
        "custody": {
            "type_id": inception.custody_type_id or "",
            "status": inception.custody_status or "UNKNOWN",
            "owner_note": inception.custody_owner_note or "",
            "route_note": inception.custody_route_note or "",
        },
        "funding": {
            "type_id": inception.funding_type_id or "",
            "status": inception.funding_status or "UNFUNDED",
            "envelope": inception.funding_envelope or "",
            "source_note": inception.funding_source_note or "",
        },
        "activity": list(inception.activity_log or []),
        "decisions": decisions,
        "project_id": inception.minted_project_id,
    }


def _parse_amount(raw) -> Decimal:
    text = (raw or "").strip().replace(",", "")
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return Decimal("0")


@transaction.atomic
def save_workspace_from_post(
    *,
    inception: ProjectInception,
    profile: dict,
    post,
    who: str,
    user_account=None,
    org=None,
) -> ProjectInception:
    inception.title = (post.get("title") or "").strip()[:300]

    participant = None
    if user_account and org:
        participant = ensure_participant(
            inception,
            user_account,
            org,
            InceptionParticipant.TECHNICAL,
        )

    for lane in profile.get("lanes") or []:
        lid = lane["id"]
        body = (post.get(f"lane_{lid}") or "").strip()
        contrib, created = WorkshopContribution.objects.get_or_create(
            inception=inception,
            contribution_type=lid,
            defaults={
                "content": body,
                "participant": participant,
                "updated_by_name": who,
            },
        )
        if not created and body != (contrib.content or ""):
            contrib.content = body
            contrib.updated_by_name = who
            if participant and not contrib.participant_id:
                contrib.participant = participant
            contrib.save()
            append_activity(inception, f"Updated {lane.get('label', lid)}", who)
        elif created and body:
            append_activity(inception, f"Updated {lane.get('label', lid)}", who)

    inception.custody_type_id = (post.get("custody_type") or "").strip()[:80]
    inception.custody_status = (post.get("custody_status") or "UNKNOWN").strip()[:40]
    inception.custody_owner_note = (post.get("custody_owner") or "").strip()[:500]
    inception.custody_route_note = (post.get("custody_route") or "").strip()[:500]

    inception.funding_type_id = (post.get("funding_type") or "").strip()[:80]
    inception.funding_status = (post.get("funding_status") or "UNFUNDED").strip()[:40]
    inception.funding_envelope = (post.get("funding_envelope") or "").strip()[:80]
    inception.funding_source_note = (post.get("funding_note") or "").strip()[:500]

    budget = ensure_budget(inception, profile, user_account)
    currency = (post.get("budget_currency") or "").strip()[:10]
    if currency:
        budget.currency = currency
    basis = (post.get("budget_basis") or "").strip()
    if basis or "budget_basis" in post:
        budget.basis_of_estimate = basis
    accuracy = (post.get("budget_accuracy") or "").strip()[:5]
    if accuracy:
        budget.accuracy = accuracy
    budget.save()

    for line in budget.lines.all():
        key = f"budget_line_{line.code}"
        if key in post:
            line.amount = _parse_amount(post.get(key))
            line.save(update_fields=["amount"])

    # Advance stage while collaborating
    if inception.stage == ProjectInception.STAGE_CONCEPT:
        inception.stage = ProjectInception.STAGE_WORKSHOP

    brief = inception_to_brief(inception)
    ready = readiness(brief, profile)
    if ready["concept_ready"] and inception.stage in (
        ProjectInception.STAGE_CONCEPT,
        ProjectInception.STAGE_WORKSHOP,
    ):
        inception.stage = ProjectInception.STAGE_DOCUMENTED

    append_activity(inception, "Saved living brief", who)
    inception.save()
    return inception


def reset_for_profile_switch(
    inception: ProjectInception,
    new_profile: dict,
    who: str,
) -> ProjectInception:
    """Keep same inception row; switch pack and clear lane content."""
    new_id = new_profile.get("id") or ""
    inception.profile_id = new_id
    inception.sector = PROFILE_SECTOR.get(new_id, inception.sector or "OTHER")
    inception.stage = ProjectInception.STAGE_CONCEPT
    inception.custody_type_id = ""
    inception.custody_status = "UNKNOWN"
    inception.custody_owner_note = ""
    inception.custody_route_note = ""
    inception.funding_type_id = ""
    inception.funding_status = "UNFUNDED"
    inception.funding_envelope = ""
    inception.funding_source_note = ""
    inception.contributions.all().delete()
    if hasattr(inception, "concept_budget"):
        inception.concept_budget.lines.all().delete()
        seed_budget_lines(inception.concept_budget, new_profile)
    else:
        ensure_budget(inception, new_profile)
    defaults = TENANT_INCEPTION_DEFAULTS.get(
        getattr(inception.sponsor_org, "org_code", "") or "", {}
    )
    if defaults.get("profile_id") == new_id and defaults.get("title"):
        inception.title = defaults["title"]
    append_activity(
        inception,
        f"Switched profile to {new_profile.get('title')}",
        who,
    )
    inception.save()
    return inception


def _default_country_for_org(org):
    code = (getattr(org, "org_code", "") or "").upper()
    if code.startswith("MTN"):
        return Country.objects.filter(code="SS").first()
    return Country.objects.filter(code="KE").first()


@transaction.atomic
def approve_concept(
    *,
    inception: ProjectInception,
    profile: dict,
    who: str,
    user_account=None,
    comments: str = "",
) -> tuple[InceptionApproval, InfraProject | None]:
    """
    Sponsor approval: record decision, mint InfraProject, move to DESIGN.
    """
    brief = inception_to_brief(inception)
    ready = readiness(brief, profile)
    if not ready["concept_ready"]:
        raise ValueError("Concept gate not ready")

    inception.stage = ProjectInception.STAGE_SPONSOR_REVIEW
    inception.save(update_fields=["stage", "updated_at"])

    project = mint_infra_project(inception)
    project_id = project.task_id if project else ""

    approval = InceptionApproval.objects.create(
        inception=inception,
        actioned_by=user_account,
        actioned_by_name=who,
        action=InceptionApproval.APPROVED,
        comments=comments or "",
        approved_budget=getattr(
            getattr(inception, "concept_budget", None), "total_amount", None
        ),
        currency=getattr(
            getattr(inception, "concept_budget", None), "currency", "KES"
        )
        or "KES",
        minted_project_id=project_id,
    )

    if hasattr(inception, "concept_budget") and inception.concept_budget:
        budget = inception.concept_budget
        budget.is_approved = True
        budget.approved_by = user_account
        budget.approved_at = timezone.now()
        budget.save(
            update_fields=["is_approved", "approved_by", "approved_at", "updated_at"]
        )

    inception.stage = ProjectInception.STAGE_DESIGN
    inception.infra_project = project
    append_activity(
        inception,
        f"Concept approved - BuildWatch identity {project_id}",
        who,
    )
    inception.save()

    # Unlock programme work plan (rollout + financing + BOM)
    try:
        from buildwatch.workplan.services import get_or_create_work_plan

        get_or_create_work_plan(
            infra_project=project,
            inception=inception,
            profile_id=inception.profile_id,
            who=who,
        )
        append_activity(
            inception,
            "Project work plan seeded (test -> commissioning)",
            who,
        )
        inception.save(update_fields=["activity_log", "updated_at"])
    except Exception:
        # Work plan is additive; never block concept approval
        pass

    return approval, project


@transaction.atomic
def mint_infra_project(inception: ProjectInception) -> InfraProject:
    if inception.infra_project_id:
        return inception.infra_project

    project_id = (inception.seed_project_ref or inception.inception_ref).strip()[:50]
    description = (inception.title or inception.inception_ref)[:200]
    task, _ = ProjectTask.objects.get_or_create(
        project_id=project_id,
        defaults={"description": description},
    )
    if task.description != description and not inception.seed_project_ref:
        task.description = description
        task.save(update_fields=["description"])

    project = InfraProject.objects.filter(task=task).first()
    if project is None:
        project = InfraProject.objects.create(
            task=task,
            owner_org=inception.sponsor_org,
            country=inception.country or _default_country_for_org(inception.sponsor_org),
            sector=inception.sector or "OTHER",
            project_type="PRIVATE"
            if (getattr(inception.sponsor_org, "organization_type", "") or "")
            == "PRIVATE"
            else "GOV",
            county=inception.county_region or "",
            is_active=True,
        )
    else:
        # Link existing (e.g. pre-seeded MTN project) without overwriting ownership lightly
        if project.owner_org_id is None:
            project.owner_org = inception.sponsor_org
            project.save(update_fields=["owner_org"])

    inception.infra_project = project
    inception.save(update_fields=["infra_project", "updated_at"])
    return project
