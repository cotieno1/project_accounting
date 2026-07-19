# ============================================================================
# buildwatch/open_tender.py
#
# Open Tender - Financial Dashboard + Public Tender Internal Fin Ops.
#
# Task     = awarded public tender, tagged via PublicTenderProfile (PUBLIC_TENDER /
#            PPP / -) linked to an accounts.ProjectTask. Close Tender tasks stay
#            untagged and are never mixed into these dashboards.
# Sub-task = priced BOQ category (package) from the bid workspace
#            OR Pioneer internal item (financial + non-financial impact).
# Resources= products/resources with phased quantities (Fin Ops).
# ============================================================================
from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from .models import (
    BidWorkspace,
    PublicTenderProfile,
    SubTaskResource,
    SubTaskResourcePhase,
    TenderBoqPackage,
    TenderListing,
    WorkspaceBillPrice,
    WorkSubTask,
)

Z = Decimal("0")

# Standard Pioneer-internal sub-tasks (not priced BOQ lines) with real impact.
STANDARD_INTERNAL_SUBTASKS = [
    {
        "code": "INT-01",
        "name": "Mobilisation & award kick-off",
        "description": "Letter of award intake, team mobilisation, kick-off prerequisites.",
        "has_financial_impact": True,
        "has_non_financial_impact": True,
    },
    {
        "code": "INT-02",
        "name": "Site handover, clearing & securing",
        "description": "Take possession, clear bushes, secure perimeter. Gated on site handover.",
        "has_financial_impact": True,
        "has_non_financial_impact": True,
    },
    {
        "code": "INT-03",
        "name": "Temporary works & site facilities",
        "description": "Temp structures, storage, site offices, welfare.",
        "has_financial_impact": True,
        "has_non_financial_impact": True,
    },
    {
        "code": "INT-04",
        "name": "CCTV / site security systems",
        "description": "Surveillance and security products & resources for the site.",
        "has_financial_impact": True,
        "has_non_financial_impact": True,
    },
    {
        "code": "INT-05",
        "name": "Insurances, bonds & guarantees",
        "description": "Performance bond, all-risks, statutory covers.",
        "has_financial_impact": True,
        "has_non_financial_impact": True,
    },
    {
        "code": "INT-06",
        "name": "QA / supervision (Pioneer side)",
        "description": "Onsite Snr Site Engineer QA, coordination with MoW consultants.",
        "has_financial_impact": True,
        "has_non_financial_impact": True,
    },
]


def _q(v):
    return (v or Z).quantize(Decimal("0.01"))


def public_task_ids():
    """ProjectTask PKs tagged as public/PPP/etc. - exclude these from Close Tender."""
    return list(PublicTenderProfile.objects.values_list("task_id", flat=True))


def ensure_public_profile(tender, contractor_org, task, category=None, award_ref="", awarded_at=None):
    """Create or update the PublicTenderProfile for an awarded tender."""
    category = category or PublicTenderProfile.CATEGORY_PUBLIC_TENDER
    profile, _ = PublicTenderProfile.objects.update_or_create(
        task=task,
        defaults={
            "tender": tender,
            "category": category,
            "contractor_org": contractor_org,
            "award_letter_ref": award_ref or "",
            "awarded_at": awarded_at,
        },
    )
    return profile


def _package_value(workspace, package_code):
    if workspace is None:
        return Z
    total = (
        WorkspaceBillPrice.objects.filter(workspace=workspace, package_code=package_code)
        .aggregate(s=Sum("amount"))
        .get("s")
    )
    return _q(total)


def _best_workspace(tender, contractor_org):
    qs = BidWorkspace.objects.filter(tender=tender)
    if contractor_org:
        ws = qs.filter(organisation=contractor_org).order_by("-id").first()
        if ws:
            return ws
    return qs.order_by("-id").first()


def generate_subtasks_from_boq(profile, ua=None):
    """
    Seed Open Tender sub-tasks from priced BOQ packages + standard internal items.
    Idempotent on (profile, package_code) for BOQ and (profile, code) for internal.
    """
    tender = profile.tender
    project = getattr(getattr(tender, "event", None), "project", None)
    if project is None:
        return 0

    workspace = _best_workspace(tender, profile.contractor_org)
    packages = list(TenderBoqPackage.objects.filter(tender=tender).order_by("sort_order", "code"))

    # If packages selected in workspace, prefer those; else all packages.
    selected = set((workspace.selected_package_codes or []) if workspace else [])
    if selected:
        packages = [p for p in packages if p.code in selected] or packages

    created = 0
    seq = 1

    existing_boq = {
        st.package_code: st
        for st in profile.subtasks.filter(kind=WorkSubTask.KIND_BOQ).exclude(package_code="")
    }
    for pkg in packages:
        value = _package_value(workspace, pkg.code)
        if pkg.code in existing_boq:
            st = existing_boq[pkg.code]
            if st.planned_value != value:
                st.planned_value = value
                st.save(update_fields=["planned_value", "updated_at"])
            continue
        WorkSubTask.objects.create(
            profile=profile,
            project=project,
            tender=tender,
            kind=WorkSubTask.KIND_BOQ,
            package_code=pkg.code,
            seq=seq,
            code="BOQ-%02d" % seq,
            name=pkg.title[:200],
            description="Priced BOQ category %s" % pkg.code,
            has_financial_impact=True,
            has_non_financial_impact=False,
            planned_value=value,
        )
        seq += 1
        created += 1

    existing_int = {
        st.code: st for st in profile.subtasks.filter(kind=WorkSubTask.KIND_INTERNAL)
    }
    for item in STANDARD_INTERNAL_SUBTASKS:
        if item["code"] in existing_int:
            continue
        WorkSubTask.objects.create(
            profile=profile,
            project=project,
            tender=tender,
            kind=WorkSubTask.KIND_INTERNAL,
            seq=seq,
            code=item["code"],
            name=item["name"],
            description=item["description"],
            has_financial_impact=item["has_financial_impact"],
            has_non_financial_impact=item["has_non_financial_impact"],
            planned_value=Z,
        )
        seq += 1
        created += 1

    return created


def open_tender_overview(profile):
    """Rollup for Open Tender - Financial Dashboard."""
    subtasks = list(
        profile.subtasks.prefetch_related("resources", "resources__phases").all()
    )
    boq = [s for s in subtasks if s.kind == WorkSubTask.KIND_BOQ]
    internal = [s for s in subtasks if s.kind == WorkSubTask.KIND_INTERNAL]
    planned = sum((_q(s.planned_value) for s in subtasks), Z)
    earned = sum((_q(s.planned_value) for s in subtasks if s.is_authorized), Z)
    done = sum(1 for s in subtasks if s.is_done)
    return {
        "profile": profile,
        "tender": profile.tender,
        "task_id": profile.task_id,
        "boq_subtasks": boq,
        "internal_subtasks": internal,
        "subtasks": subtasks,
        "totals": {
            "planned": _q(planned),
            "earned": _q(earned),
            "count": len(subtasks),
            "done": done,
            "pct": int(round(done * 100 / len(subtasks))) if subtasks else 0,
        },
    }


def fin_ops_overview(profile):
    """Rollup for Public Tender Internal Fin Ops (resources + phases)."""
    resources = list(
        SubTaskResource.objects.filter(subtask__profile=profile)
        .select_related("subtask")
        .prefetch_related("phases")
    )
    rows = []
    for r in resources:
        phases = list(r.phases.all())
        phased = sum((p.qty for p in phases), Z)
        rows.append({
            "resource": r,
            "subtask": r.subtask,
            "phases": phases,
            "phased_qty": phased,
            "remaining": (r.total_qty or Z) - phased,
        })
    return {
        "profile": profile,
        "task_id": profile.task_id,
        "tender": profile.tender,
        "rows": rows,
        "resource_kinds": SubTaskResource.KIND_CHOICES,
    }


def add_resource(subtask, name, resource_kind, unit, total_qty, notes=""):
    return SubTaskResource.objects.create(
        subtask=subtask,
        name=name[:200],
        resource_kind=resource_kind or SubTaskResource.KIND_MATERIAL,
        unit=(unit or "No")[:30],
        total_qty=Decimal(str(total_qty or 0)),
        notes=(notes or "")[:300],
    )


def set_resource_phases(resource, phase_qtys):
    """
    phase_qtys: list of (phase_index, qty, phase_name?)
    Replaces existing phases with the given split (e.g. 5000, 2500, 2500).
    """
    resource.phases.all().delete()
    created = []
    for i, item in enumerate(phase_qtys, start=1):
        if isinstance(item, (list, tuple)):
            idx = int(item[0]) if len(item) > 0 else i
            qty = Decimal(str(item[1] if len(item) > 1 else 0))
            name = (item[2] if len(item) > 2 else "") or ("Phase %d" % idx)
        else:
            idx, qty, name = i, Decimal(str(item)), ("Phase %d" % i)
        created.append(
            SubTaskResourcePhase.objects.create(
                resource=resource,
                phase_index=idx,
                phase_name=name[:80],
                qty=qty,
            )
        )
    return created
