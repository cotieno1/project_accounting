# ============================================================================
# buildwatch/milestones.py
#
# Delivery + payment milestones derived from the BOQ programme (phases/trades)
# and tied to the PM Gantt chart. Delivery of a milestone (compliance sign-off)
# is a pre-requisite for raising its payment.
# ============================================================================
from __future__ import annotations

from decimal import Decimal

from .models import ComplianceCheckpoint, PaymentCertificate, ProjectMilestone

Z = Decimal("0")


def _q(v):
    return (v or Z).quantize(Decimal("0.01"))


def generate_milestones_for_tender(tender):
    """Create milestones from the tender's BOQ programme phases. Idempotent."""
    from .views_compliance import PHASE_LABELS, _draft_programme

    project = getattr(getattr(tender, "event", None), "project", None)
    if project is None:
        return 0

    checkpoints = list(tender.checkpoints.all())
    prog = _draft_programme(checkpoints)
    phases = prog["phases"]
    if not phases:
        return 0

    existing = {m.phase_index: m for m in project.milestones.all()}
    created = 0
    for seq, p in enumerate(phases, start=1):
        if p["idx"] in existing:
            continue
        ProjectMilestone.objects.create(
            project=project,
            tender=tender,
            phase_index=p["idx"],
            seq=seq,
            name=p.get("label") or PHASE_LABELS.get(p["idx"], "Phase %d" % p["idx"]),
            planned_start_week=p["start"],
            duration_weeks=p["duration"],
        )
        created += 1

    autodistribute_value(project, only_if_empty=True)
    return created


def autodistribute_value(project, only_if_empty=False):
    """Split the contract sum across milestones (even split) as a starting point."""
    milestones = list(project.milestones.all())
    if not milestones:
        return
    if only_if_empty and any((m.value_amount or Z) > 0 for m in milestones):
        return
    contract = project.contract_value or Z
    n = len(milestones)
    if contract <= 0:
        return
    share = (contract / n).quantize(Decimal("0.01"))
    running = Z
    for i, m in enumerate(milestones):
        amt = contract - running if i == n - 1 else share
        m.value_amount = amt
        m.value_pct = (amt / contract * Decimal("100")).quantize(Decimal("0.001")) if contract else Z
        m.save(update_fields=["value_amount", "value_pct", "updated_at"])
        running += amt


def _phase_compliance(checkpoints, phase_index):
    from .views_compliance import _phase_of

    phase_cps = [c for c in checkpoints if _phase_of(c) == phase_index]
    total = len(phase_cps)
    approved = sum(1 for c in phase_cps if c.status == ComplianceCheckpoint.STATUS_APPROVED)
    open_mandatory = [
        c for c in phase_cps
        if c.is_mandatory and c.status not in (
            ComplianceCheckpoint.STATUS_APPROVED, ComplianceCheckpoint.STATUS_NA,
        )
    ]
    return {
        "total": total,
        "approved": approved,
        "open_mandatory": len(open_mandatory),
        "pct": int(round(approved * 100 / total)) if total else 0,
        # ready to deliver when nothing mandatory is still open
        "ready": len(open_mandatory) == 0,
    }


def milestone_schedule(project):
    """Return milestones enriched with Gantt geometry, delivery readiness and payment."""
    milestones = list(project.milestones.all())
    if not milestones:
        return {"milestones": [], "total_weeks": 0, "totals": None}

    checkpoints = []
    for m in milestones:
        if m.tender_id:
            checkpoints = list(m.tender.checkpoints.all())
            break
    if not checkpoints:
        # fall back to any tender on the project's event
        ev = getattr(project, "task", None)
        try:
            checkpoints = list(
                ComplianceCheckpoint.objects.filter(tender__event__project=project)
            )
        except Exception:
            checkpoints = []

    total_weeks = max((m.end_week for m in milestones), default=0)

    certs = list(
        PaymentCertificate.objects
        .filter(project=project)
        .exclude(status=PaymentCertificate.STATUS_DRAFT)
    )
    by_ms = {}
    for c in certs:
        by_ms.setdefault(c.milestone_id, []).append(c)

    rows = []
    tot_value = tot_certified = tot_paid = Z
    for m in milestones:
        comp = _phase_compliance(checkpoints, m.phase_index)
        ms_certs = by_ms.get(m.pk, [])
        certified = sum((c.net_payable or Z for c in ms_certs), Z)
        paid = sum((c.net_payable or Z for c in ms_certs if c.status == PaymentCertificate.STATUS_PAID), Z)

        left = round((m.planned_start_week - 1) * 100.0 / total_weeks, 2) if total_weeks else 0
        width = round(max(1, m.duration_weeks) * 100.0 / total_weeks, 2) if total_weeks else 0

        rows.append({
            "m": m,
            "compliance": comp,
            "delivered": m.status == ProjectMilestone.STATUS_DELIVERED,
            "can_deliver": comp["ready"] and m.status != ProjectMilestone.STATUS_DELIVERED,
            "can_pay": m.status == ProjectMilestone.STATUS_DELIVERED,
            "value": _q(m.value_amount),
            "certified": _q(certified),
            "paid": _q(paid),
            "cert_count": len(ms_certs),
            "left_pct": left,
            "width_pct": width,
        })
        tot_value += m.value_amount or Z
        tot_certified += certified
        tot_paid += paid

    return {
        "milestones": rows,
        "total_weeks": total_weeks,
        "totals": {
            "value": _q(tot_value),
            "certified": _q(tot_certified),
            "paid": _q(tot_paid),
            "delivered": sum(1 for r in rows if r["delivered"]),
            "count": len(rows),
        },
    }
