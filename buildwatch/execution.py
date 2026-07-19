# ============================================================================
# buildwatch/execution.py
#
# Contractor-side Work Breakdown Structure (WBS) for delivering a tender.
#
#   Task A .. n   = a ProjectMilestone (trade / phase from the BOQ preambles)
#   Sub-task A-1..= a WorkSubTask under that milestone, seeded from the phase's
#                   compliance checkpoints (which are themselves derived from the
#                   BOQ preambles) so each slice of work carries its inspection /
#                   approval gate and an earned value.
#
# Also rolls up earned value vs actual cost (from the linked Pioneer ops task)
# so the contractor can see whether each Task A is being delivered profitably.
# ============================================================================
from __future__ import annotations

from decimal import Decimal

from .models import ProjectMilestone, WorkSubTask

Z = Decimal("0")


def _q(v):
    return (v or Z).quantize(Decimal("0.01"))


def task_letter(seq):
    """1 -> A, 2 -> B ... 26 -> Z, then T27, T28 ..."""
    n = int(seq or 0)
    if 1 <= n <= 26:
        return chr(ord("A") + n - 1)
    return "T%d" % n


def _phase_checkpoints(checkpoints, phase_index):
    from .views_compliance import _phase_of

    rows = [c for c in checkpoints if _phase_of(c) == phase_index]
    rows.sort(key=lambda c: (c.sort_order, c.code))
    return rows


def _distribute_value(milestone, subtasks):
    """Split the milestone's BOQ value evenly across its sub-tasks (earned value)."""
    n = len(subtasks)
    if not n:
        return
    total = milestone.value_amount or Z
    if total <= 0:
        for st in subtasks:
            if st.planned_value != Z:
                st.planned_value = Z
                st.save(update_fields=["planned_value", "updated_at"])
        return
    share = (total / n).quantize(Decimal("0.01"))
    running = Z
    for i, st in enumerate(subtasks):
        amt = total - running if i == n - 1 else share
        if st.planned_value != amt:
            st.planned_value = amt
            st.save(update_fields=["planned_value", "updated_at"])
        running += amt


def generate_wbs_for_tender(tender, ua=None):
    """
    Create the Task A -> sub-task A-1..n breakdown from the BOQ. Idempotent:
    only adds sub-tasks that do not yet exist. Returns number of sub-tasks made.
    """
    from .milestones import generate_milestones_for_tender

    project = getattr(getattr(tender, "event", None), "project", None)
    if project is None:
        return 0

    if not project.milestones.exists():
        generate_milestones_for_tender(tender)

    milestones = list(project.milestones.all())
    if not milestones:
        return 0

    checkpoints = list(tender.checkpoints.all())
    created = 0

    for milestone in milestones:
        existing = list(milestone.subtasks.all())
        existing_cp_ids = {st.checkpoint_id for st in existing if st.checkpoint_id}
        phase_cps = _phase_checkpoints(checkpoints, milestone.phase_index)

        next_seq = (max([st.seq for st in existing], default=0)) + 1

        if phase_cps:
            for cp in phase_cps:
                if cp.pk in existing_cp_ids:
                    continue
                WorkSubTask.objects.create(
                    milestone=milestone,
                    project=project,
                    tender=tender,
                    checkpoint=cp,
                    preamble=cp.preamble,
                    seq=next_seq,
                    name=cp.title[:200],
                    description=(cp.requirement or "")[:2000],
                )
                next_seq += 1
                created += 1
        elif not existing:
            # A phase with no preamble checkpoints still needs one delivery step.
            WorkSubTask.objects.create(
                milestone=milestone,
                project=project,
                tender=tender,
                seq=next_seq,
                name="Execute & complete %s" % milestone.name,
            )
            next_seq += 1
            created += 1

        # (Re)number codes A-1.. and split the milestone value across sub-tasks.
        letter = task_letter(milestone.seq or (milestones.index(milestone) + 1))
        subtasks = list(milestone.subtasks.all())
        for i, st in enumerate(subtasks, start=1):
            code = "%s-%d" % (letter, i)
            if st.code != code:
                st.code = code
                st.save(update_fields=["code", "updated_at"])
        _distribute_value(milestone, subtasks)

    return created


def _consultant(tender, *roles):
    if tender is None:
        return None
    cons = {c.role: c for c in tender.consultants.all()}
    for r in roles:
        if r in cons:
            return cons[r]
    return None


def _consultants(tender, *roles):
    if tender is None:
        return []
    cons = {c.role: c for c in tender.consultants.all()}
    return [cons[r] for r in roles if r in cons]


def governance(project, tender):
    """
    Who oversees an Open Public Tender Project Task. External government/employer
    parties (QA supervising, PM managing, Government Accountant processing
    payment) plus the internal contractor who executes and sources at best price.
    """
    from .kickoff import _awarded_or_bidder_org
    from .models import TenderConsultant

    owner = getattr(project, "owner_org", None)
    owner_name = getattr(owner, "name", "") or "The Employer (Government)"

    pm = _consultant(tender, TenderConsultant.PM_ENGINEER)
    qa = _consultant(tender, TenderConsultant.SUPERVISION, TenderConsultant.QS)
    engineers = _consultants(
        tender,
        TenderConsultant.STRUCTURAL_CIVIL,
        TenderConsultant.ELECTRICAL_MECHANICAL,
        TenderConsultant.ARCHITECT,
    )
    contractor = _awarded_or_bidder_org(tender) if tender else None

    external = [
        {
            "role": "QA - Quality Assurance / Supervision",
            "name": (qa.display_name if qa else owner_name),
            "responsibility": "Supervises workmanship & materials on site; inspects and signs off each sub-task before it is certified.",
        },
        {
            "role": "PM - Project Manager",
            "name": (pm.display_name if pm else owner_name),
            "responsibility": "Manages the programme, issues instructions and oversees overall delivery of the works.",
        },
    ]

    # Government consulting engineers who authorize / give the nod to proceed.
    if engineers:
        for c in engineers:
            external.append({
                "role": "Consulting Engineer (Government) - " + c.get_role_display(),
                "name": c.display_name,
                "responsibility": "Authorizes the works within their discipline and gives the nod (approval) before a sub-task proceeds or is paid.",
            })
    else:
        external.append({
            "role": "Consulting Engineer (Government)",
            "name": owner_name,
            "responsibility": "Authorizes the works and gives the nod (approval) before a sub-task proceeds or is paid.",
        })

    external.append({
        "role": "Government Accountant",
        "name": owner_name,
        "responsibility": "Processes payment on the delivery hub: certificate -> Requisition Order (RO) -> Payment Order (PV).",
    })
    internal = [
        {
            "role": "Contractor (Pioneer)",
            "name": (getattr(contractor, "name", "") or "Awarded contractor"),
            "responsibility": "Executes the works, and sources outsourced materials & services competitively to secure the best price.",
        },
    ]
    return {"external": external, "internal": internal}


def _subtask_row(st):
    return {
        "st": st,
        "value": _q(st.planned_value),
        "earned": _q(st.planned_value) if st.is_approved else Z,
        "cp": st.checkpoint,
    }


def wbs_overview(project, tender=None):
    """Task A groups + sub-tasks, with earned-value and profitability rollup."""
    milestones = list(project.milestones.prefetch_related("subtasks", "subtasks__checkpoint").all())

    tasks = []
    tot_planned = tot_earned = Z
    tot_sub = tot_done = 0

    for m in milestones:
        subtasks = list(m.subtasks.all())
        rows = [_subtask_row(st) for st in subtasks]
        planned = sum((r["value"] for r in rows), Z)
        earned = sum((r["earned"] for r in rows), Z)
        done = sum(1 for st in subtasks if st.is_done)
        approved = sum(1 for st in subtasks if st.is_approved)
        count = len(subtasks)

        tasks.append({
            "m": m,
            "letter": task_letter(m.seq or (milestones.index(m) + 1)),
            "subtasks": rows,
            "planned": _q(planned),
            "earned": _q(earned),
            "count": count,
            "approved": approved,
            "done": done,
            "pct": int(round(approved * 100 / count)) if count else 0,
        })
        tot_planned += planned
        tot_earned += earned
        tot_sub += count
        tot_done += done

    finance = _finance_control(project, _q(tot_earned), _q(tot_planned))

    return {
        "tasks": tasks,
        "has_wbs": tot_sub > 0,
        "governance": governance(project, tender),
        "totals": {
            "planned": _q(tot_planned),
            "earned": _q(tot_earned),
            "subtasks": tot_sub,
            "done": tot_done,
            "pct": int(round(tot_earned * 100 / tot_planned)) if tot_planned > 0 else 0,
        },
        "finance": finance,
    }


def _finance_control(project, earned, planned):
    """
    Back-office internal control: earned value vs actual cost drawn from the
    linked Pioneer ops task (the 'Close Tender - Financial Dashboard'). Best
    effort - degrades gracefully when the project is not wired to an ops task.
    """
    contract = _q(project.contract_value)
    task = getattr(project, "task", None)
    out = {
        "linked": bool(task),
        "task_id": getattr(task, "project_id", "") if task else "",
        "contract": contract,
        "planned": planned,
        "earned": earned,
        "authorized_budget": None,
        "spent": None,
        "margin": None,
        "margin_pct": None,
    }
    if not task:
        return out

    try:
        budget = getattr(task, "budget", None)
        if budget is not None:
            out["authorized_budget"] = _q(budget.total_authorized_budget)
    except Exception:
        pass

    try:
        from accounts.ledger import task_fund_summary

        summ = task_fund_summary(task)
        if summ:
            spent = _q(summ.get("spent"))
            out["spent"] = spent
            out["margin"] = _q(earned - spent)
            out["margin_pct"] = (
                int(round((earned - spent) * 100 / earned)) if earned > 0 else None
            )
    except Exception:
        pass

    return out
