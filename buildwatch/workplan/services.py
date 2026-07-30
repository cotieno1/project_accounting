# -*- coding: utf-8 -*-
"""Seed and update Project Work Plan from programme profiles."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from buildwatch.inception.loader import get_profile
from buildwatch.models_inception import ProjectInception
from buildwatch.models_workplan import (
    ProjectWorkPlan,
    WorkPlanActivity,
    WorkPlanBomLine,
    WorkPlanPhase,
)


def _dec(raw, default="0") -> Decimal:
    try:
        return Decimal(str(raw).replace(",", "").strip() or default)
    except (InvalidOperation, ValueError, AttributeError):
        return Decimal(default)


def _log(plan: ProjectWorkPlan, who: str, text: str) -> None:
    WorkPlanActivity.objects.create(
        plan=plan,
        who=who or "",
        text=text[:400],
        at=timezone.now(),
    )


def work_plan_pack(profile_id: str) -> dict:
    profile = get_profile(profile_id) or {}
    return profile.get("work_plan") or {}


@transaction.atomic
def get_or_create_work_plan(
    *,
    infra_project,
    inception: ProjectInception | None = None,
    profile_id: str = "",
    who: str = "system",
) -> ProjectWorkPlan:
    profile_id = (
        profile_id
        or (inception.profile_id if inception else "")
        or getattr(infra_project, "sector", "")
        or ""
    )
    # Prefer inception profile when linked
    if inception and inception.profile_id:
        profile_id = inception.profile_id

    pack = work_plan_pack(profile_id)
    title_default = pack.get("title") or f"Work plan - {infra_project}"

    plan, created = ProjectWorkPlan.objects.get_or_create(
        infra_project=infra_project,
        defaults={
            "inception": inception,
            "profile_id": profile_id,
            "title": title_default,
            "currency": pack.get("currency")
            or (
                getattr(getattr(inception, "concept_budget", None), "currency", None)
                if inception
                else None
            )
            or "KES",
            "total_envelope": _dec(pack.get("default_envelope"), "0"),
            "strategy_note": pack.get("strategy_note") or "",
        },
    )
    if not created:
        if inception and not plan.inception_id:
            plan.inception = inception
        if profile_id and not plan.profile_id:
            plan.profile_id = profile_id
        if not plan.title:
            plan.title = title_default
        plan.save()
    else:
        _log(plan, who, "Work plan created")

    seed_phases_and_bom(plan, pack, who=who)

    if inception and hasattr(inception, "concept_budget") and inception.concept_budget:
        if plan.total_envelope == 0 and inception.concept_budget.total_amount:
            plan.total_envelope = inception.concept_budget.total_amount
            plan.save(update_fields=["total_envelope", "updated_at"])
            for phase in plan.phases.all():
                if phase.financing_pct:
                    phase.financing_amount = (
                        plan.total_envelope * phase.financing_pct / Decimal("100")
                    ).quantize(Decimal("0.01"))
                    phase.save(update_fields=["financing_amount"])

    return plan


def seed_phases_and_bom(plan: ProjectWorkPlan, pack: dict, who: str = "system") -> None:
    """Idempotent seed of rollout phases + BOM templates from profile pack."""
    phases = pack.get("phases") or []
    existing_phases = {p.code: p for p in plan.phases.all()}
    created_any = False
    for i, row in enumerate(phases):
        code = (row.get("id") or row.get("code") or "").strip()
        if not code:
            continue
        label = (row.get("label") or code).strip()
        kind = (row.get("kind") or WorkPlanPhase.KIND_WAVE).strip()
        sort_order = int(row.get("sort_order", i * 10))
        pct = _dec(row.get("financing_pct"), "0")
        amount = (plan.total_envelope * pct / Decimal("100")).quantize(Decimal("0.01"))
        if code in existing_phases:
            phase = existing_phases[code]
            phase.label = label
            phase.kind = kind
            phase.sort_order = sort_order
            phase.objective = row.get("objective") or phase.objective
            phase.exit_criteria = row.get("exit_criteria") or phase.exit_criteria
            phase.site_or_scope = row.get("scope") or phase.site_or_scope
            phase.financing_trigger = (
                row.get("financing_trigger") or phase.financing_trigger
            )
            if phase.financing_pct == 0 and pct:
                phase.financing_pct = pct
                phase.financing_amount = amount
            phase.save()
        else:
            WorkPlanPhase.objects.create(
                plan=plan,
                code=code,
                label=label,
                kind=kind,
                sort_order=sort_order,
                objective=row.get("objective") or "",
                exit_criteria=row.get("exit_criteria") or "",
                site_or_scope=row.get("scope") or "",
                financing_pct=pct,
                financing_amount=amount,
                financing_trigger=row.get("financing_trigger") or "",
            )
            created_any = True

    bom_rows = pack.get("bom_lines") or []
    if bom_rows and not plan.bom_lines.exists():
        phase_by_code = {p.code: p for p in plan.phases.all()}
        for i, row in enumerate(bom_rows):
            phase_code = (row.get("phase") or "").strip()
            WorkPlanBomLine.objects.create(
                plan=plan,
                phase=phase_by_code.get(phase_code),
                item_code=(row.get("item_code") or "").strip()[:50],
                description=(row.get("description") or row.get("label") or "Item")[:300],
                unit=(row.get("unit") or "Nr")[:20],
                quantity=_dec(row.get("quantity"), "0"),
                unit_cost=_dec(row.get("unit_cost"), "0"),
                sort_order=int(row.get("sort_order", i * 10)),
                notes=(row.get("notes") or "")[:300],
            )
        created_any = True

    if created_any:
        _log(plan, who, "Seeded rollout phases / BOM from profile pack")


@transaction.atomic
def save_work_plan_from_post(plan: ProjectWorkPlan, post, who: str) -> ProjectWorkPlan:
    plan.title = (post.get("title") or plan.title or "")[:300]
    plan.strategy_note = (post.get("strategy_note") or "").strip()
    currency = (post.get("currency") or "").strip()[:10]
    if currency:
        plan.currency = currency
    if "total_envelope" in post:
        plan.total_envelope = _dec(post.get("total_envelope"), "0")
    status = (post.get("status") or "").strip()
    if status in dict(ProjectWorkPlan.STATUS_CHOICES):
        plan.status = status
    plan.save()

    # Recompute phase amounts from % if envelope changed
    for phase in plan.phases.all():
        key_pct = f"phase_pct_{phase.code}"
        key_amt = f"phase_amt_{phase.code}"
        key_scope = f"phase_scope_{phase.code}"
        key_obj = f"phase_objective_{phase.code}"
        key_exit = f"phase_exit_{phase.code}"
        key_trig = f"phase_trigger_{phase.code}"
        key_done = f"phase_done_{phase.code}"
        changed = False
        if key_pct in post:
            phase.financing_pct = _dec(post.get(key_pct), "0")
            changed = True
        if key_amt in post and (post.get(key_amt) or "").strip():
            phase.financing_amount = _dec(post.get(key_amt), "0")
            changed = True
        elif key_pct in post or "total_envelope" in post:
            phase.financing_amount = (
                plan.total_envelope * phase.financing_pct / Decimal("100")
            ).quantize(Decimal("0.01"))
            changed = True
        if key_scope in post:
            phase.site_or_scope = (post.get(key_scope) or "")[:300]
            changed = True
        if key_obj in post:
            phase.objective = (post.get(key_obj) or "").strip()
            changed = True
        if key_exit in post:
            phase.exit_criteria = (post.get(key_exit) or "").strip()
            changed = True
        if key_trig in post:
            phase.financing_trigger = (post.get(key_trig) or "")[:200]
            changed = True
        if key_done in post:
            phase.is_complete = post.get(key_done) in ("on", "1", "true", "True")
            changed = True
        if changed:
            phase.save()

    for line in plan.bom_lines.all():
        qkey = f"bom_qty_{line.id}"
        ckey = f"bom_cost_{line.id}"
        dkey = f"bom_desc_{line.id}"
        if qkey in post:
            line.quantity = _dec(post.get(qkey), "0")
        if ckey in post:
            line.unit_cost = _dec(post.get(ckey), "0")
        if dkey in post:
            line.description = (post.get(dkey) or line.description)[:300]
        line.save()

    # Optional new BOM row
    new_desc = (post.get("bom_new_description") or "").strip()
    if new_desc:
        WorkPlanBomLine.objects.create(
            plan=plan,
            description=new_desc[:300],
            item_code=(post.get("bom_new_code") or "")[:50],
            unit=(post.get("bom_new_unit") or "Nr")[:20],
            quantity=_dec(post.get("bom_new_qty"), "0"),
            unit_cost=_dec(post.get("bom_new_cost"), "0"),
            sort_order=(plan.bom_lines.count() + 1) * 10,
        )

    _log(plan, who, "Saved work plan (rollout + financing + BOM)")
    return plan
