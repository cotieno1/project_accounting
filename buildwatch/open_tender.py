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
    ActivityBudgetLine,
    BidWorkspace,
    OpenTenderActivity,
    PublicTenderProfile,
    SubTaskResource,
    SubTaskResourcePhase,
    TenderBoqLine,
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


# Pilot packages for activity + activity-based budget demos (Block A).
PILOT_ACTIVITY_PACKAGES = ("BA-B04-E02", "BA-B04-E07")  # R.C Frame, Internal Finishes

_UNIT_MAP = {
    "SM": "m2",
    "CM": "m3",
    "LM": "m",
    "KG": "kg",
    "NO": "No",
    "ITEM": "Item",
    "SUM": "Sum",
}


def _measure_unit(boq_unit):
    u = (boq_unit or "").strip().upper()
    return _UNIT_MAP.get(u, (boq_unit or "").strip() or "No")


def _location_hint(description, package_title=""):
    text = ("%s %s" % (description or "", package_title or "")).lower()
    if "lift lobby" in text or "lift" in text and "lobby" in text:
        return "Lift lobby"
    if "landing" in text:
        return "Stair landings"
    if "tread" in text or "riser" in text:
        return "Staircases"
    if "tank" in text:
        return "Tank / roof"
    if "non slip" in text or "non-slip" in text:
        return "Wet areas (kitchen / bathroom / balcony)"
    if "ceramic wall" in text or "wall tile" in text:
        return "Walls (wet areas / kitchens)"
    if "floor tile" in text or "ceramic tile" in text and "wall" not in text:
        return "Floors (rooms / corridors)"
    if "skirting" in text:
        return "Room perimeters"
    if "column" in text:
        return "Columns"
    if "beam" in text:
        return "Beams"
    if "slab" in text:
        return "Suspended slabs"
    if "staircase" in text or "stair" in text:
        return "Staircases"
    if "reinforcement" in text or "brc" in text:
        return "Structural members"
    if "formwork" in text or "soffit" in text or "sides of" in text:
        return "Formwork contact surfaces"
    return ""


def _activity_name(description, location_hint=""):
    name = (description or "BOQ activity").strip()
    if len(name) > 180:
        name = name[:177] + "..."
    if location_hint and location_hint.lower() not in name.lower():
        return ("%s [%s]" % (name, location_hint))[:255]
    return name[:255]


def _draft_budget_lines(activity):
    """
    Seed a draft activity-based budget from the BOQ amount.
    Splits by activity type (tiling / concrete / formwork / rebar / default).
    Rates are draft placeholders for Pioneer to refine in Fin Ops.
    """
    if activity.budget_lines.exists():
        return 0
    amt = activity.amount
    provisional = False
    if amt <= 0 and (activity.quantity or Z) > 0:
        # Provisional envelope until the bid line is priced.
        amt = _q(activity.quantity * Decimal("1000"))
        provisional = True
    elif amt <= 0:
        return 0
    qty = activity.quantity or Decimal("1")
    mu = activity.measure_unit or activity.unit or "No"
    text = (activity.name or "").lower()
    created = 0
    note_suffix = (
        "Provisional draft - replace with priced BOQ / best-price RFQ"
        if provisional else
        "Draft activity budget - refine with best-price RFQ"
    )

    def add(kind, name, share, unit=None, notes=""):
        nonlocal created
        share_amt = _q(amt * Decimal(str(share)))
        if share_amt <= 0:
            return
        rate = _q(share_amt / qty) if qty else share_amt
        ActivityBudgetLine.objects.create(
            activity=activity,
            kind=kind,
            name=name[:200],
            unit=(unit or mu)[:30],
            quantity=qty,
            rate=rate,
            notes=((notes + " - " if notes else "") + note_suffix)[:300],
            seq=created + 1,
        )
        created += 1

    if any(k in text for k in ("tile", "ceramic", "porcelain", "skirting")):
        add(ActivityBudgetLine.KIND_MATERIAL, "Tiles / adhesives / grout / screed make-up", 0.55,
            notes="Certified products per finishes preamble")
        add(ActivityBudgetLine.KIND_LABOUR, "Tilers + helpers", 0.30)
        add(ActivityBudgetLine.KIND_EQUIPMENT, "Tile cutter / mixer hire", 0.08)
        add(ActivityBudgetLine.KIND_INTERNAL, "Protection, cleaning, QA samples", 0.07)
    elif any(k in text for k in ("reinforcement", "brc", "steel bar")):
        add(ActivityBudgetLine.KIND_MATERIAL, "Reinforcement steel + tying wire + chairs", 0.70,
            notes="Per Concrete Work preamble / bending schedules")
        add(ActivityBudgetLine.KIND_LABOUR, "Steel fixers", 0.22)
        add(ActivityBudgetLine.KIND_EQUIPMENT, "Bar bender / cutter", 0.05)
        add(ActivityBudgetLine.KIND_INTERNAL, "Inspection hold for Engineer check", 0.03)
    elif any(k in text for k in ("formwork", "soffit", "sides of", "shutter")):
        add(ActivityBudgetLine.KIND_MATERIAL, "Formwork timber / plywood / oil", 0.45)
        add(ActivityBudgetLine.KIND_LABOUR, "Carpenters + striking gang", 0.40)
        add(ActivityBudgetLine.KIND_EQUIPMENT, "Props / scaffolding", 0.10)
        add(ActivityBudgetLine.KIND_INTERNAL, "Striking-time compliance (preamble)", 0.05)
    elif any(k in text for k in ("column", "beam", "slab", "concrete", "blinding", "staircase")) \
            or (activity.unit or "").upper() == "CM":
        add(ActivityBudgetLine.KIND_MATERIAL, "Cement + fine/coarse aggregate + water", 0.50,
            notes="OPC per BS; samples + mill certs (Concrete Work preamble)")
        add(ActivityBudgetLine.KIND_LABOUR, "Concreting gang + curing", 0.28)
        add(ActivityBudgetLine.KIND_EQUIPMENT, "Batch mixer + vibrator", 0.15)
        add(ActivityBudgetLine.KIND_INTERNAL, "Cube tests / Clerk of Works attendance", 0.07)
    else:
        add(ActivityBudgetLine.KIND_MATERIAL, "Materials / products", 0.50)
        add(ActivityBudgetLine.KIND_LABOUR, "Labour / resources", 0.35)
        add(ActivityBudgetLine.KIND_EQUIPMENT, "Equipment", 0.10)
        add(ActivityBudgetLine.KIND_INTERNAL, "Internal / QA", 0.05)
    return created


def generate_activities_from_boq_lines(profile, package_codes=None, with_draft_budget=True):
    """
    Expand BOQ category sub-tasks into measurable activities (one per BOQ line).
    Default pilot: Block A R.C Frame + Internal Finishes (concrete + tiling).
    """
    package_codes = list(package_codes) if package_codes else list(PILOT_ACTIVITY_PACKAGES)
    tender = profile.tender
    project = getattr(getattr(tender, "event", None), "project", None)
    workspace = _best_workspace(tender, profile.contractor_org)
    created = 0
    budgeted = 0

    # Ensure pilot package sub-tasks exist (even if not in selected_package_codes).
    if project is not None:
        existing_boq = {
            st.package_code: st
            for st in profile.subtasks.filter(kind=WorkSubTask.KIND_BOQ).exclude(package_code="")
        }
        next_seq = (max([st.seq for st in profile.subtasks.all()], default=0)) + 1
        for code in package_codes:
            if code in existing_boq:
                continue
            pkg = TenderBoqPackage.objects.filter(tender=tender, code=code).first()
            if not pkg:
                continue
            WorkSubTask.objects.create(
                profile=profile,
                project=project,
                tender=tender,
                kind=WorkSubTask.KIND_BOQ,
                package_code=code,
                seq=next_seq,
                code="BOQ-%02d" % next_seq,
                name=pkg.title[:200],
                description="Priced BOQ category %s" % code,
                has_financial_impact=True,
                planned_value=_package_value(workspace, code),
            )
            next_seq += 1

    for st in profile.subtasks.filter(kind=WorkSubTask.KIND_BOQ, package_code__in=package_codes):
        pkg = TenderBoqPackage.objects.filter(tender=tender, code=st.package_code).first()
        if not pkg:
            continue
        existing = {
            a.code: a for a in st.activities.exclude(code="")
        }
        seq = 1
        for line in pkg.lines.order_by("sort_order", "bill_ref"):
            code = (line.bill_ref or ("L%s" % line.pk))[:30]
            # Prefer contractor priced rate if present.
            price = None
            if workspace:
                price = WorkspaceBillPrice.objects.filter(
                    workspace=workspace, package_code=st.package_code, bill_ref=line.bill_ref,
                ).first()
            qty = (price.quantity if price and price.quantity else line.quantity) or Z
            rate = (price.unit_rate if price else Z) or Z
            amount = _q(price.amount) if price else _q(qty * rate)
            hint = _location_hint(line.description, pkg.title)
            name = _activity_name(line.description, hint)

            if code in existing:
                act = existing[code]
                act.quantity = qty
                act.unit_rate = rate
                act.amount = amount
                act.unit = (line.unit or "")[:30]
                act.measure_unit = _measure_unit(line.unit)
                act.location_hint = hint[:120]
                act.name = name
                act.save()
            else:
                act = OpenTenderActivity.objects.create(
                    subtask=st,
                    boq_line=line,
                    seq=seq,
                    code=code,
                    name=name,
                    description=(line.description or "")[:2000],
                    unit=(line.unit or "")[:30],
                    measure_unit=_measure_unit(line.unit),
                    quantity=qty,
                    unit_rate=rate,
                    amount=amount,
                    location_hint=hint[:120],
                )
                created += 1
            seq += 1
            if with_draft_budget:
                budgeted += _draft_budget_lines(act)

    return {"activities": created, "budget_lines": budgeted}


def open_tender_overview(profile):
    """Rollup for Open Tender - Financial Dashboard."""
    subtasks = list(
        profile.subtasks.prefetch_related(
            "resources", "resources__phases",
            "activities", "activities__budget_lines",
        ).all()
    )
    boq = [s for s in subtasks if s.kind == WorkSubTask.KIND_BOQ]
    internal = [s for s in subtasks if s.kind == WorkSubTask.KIND_INTERNAL]
    planned = sum((_q(s.planned_value) for s in subtasks), Z)
    earned = sum((_q(s.planned_value) for s in subtasks if s.is_authorized), Z)
    done = sum(1 for s in subtasks if s.is_done)

    # Activity + activity-budget rollup (pilot packages first).
    activity_rows = []
    for st in boq:
        acts = list(st.activities.all())
        if not acts:
            continue
        budget_sum = sum((_q(a.budget_total) for a in acts), Z)
        activity_rows.append({
            "subtask": st,
            "activities": acts,
            "count": len(acts),
            "boq_amount": sum((_q(a.amount) for a in acts), Z),
            "budget_total": budget_sum,
        })

    return {
        "profile": profile,
        "tender": profile.tender,
        "task_id": profile.task_id,
        "boq_subtasks": boq,
        "internal_subtasks": internal,
        "subtasks": subtasks,
        "activity_groups": activity_rows,
        "pilot_packages": list(PILOT_ACTIVITY_PACKAGES),
        "gate_chain": WorkSubTask.GATE_CHAIN,
        "dependencies": list(
            profile.activity_dependencies.select_related(
                "predecessor_subtask", "successor_subtask",
            )
        ),
        "totals": {
            "planned": _q(planned),
            "earned": _q(earned),
            "count": len(subtasks),
            "done": done,
            "pct": int(round(done * 100 / len(subtasks))) if subtasks else 0,
            "activities": sum(g["count"] for g in activity_rows),
            "activity_budget": _q(sum((g["budget_total"] for g in activity_rows), Z)),
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

def _wbs_group_key(package):
    """Group packages by building / works area from code prefix (BA, SH, CV...)."""
    code = (package.code or "").strip()
    prefix = code.split("-")[0] if code else "OTHER"
    title = package.title or ""
    label = title.split("/")[0].strip() if title else prefix
    return prefix, (label or prefix)


def build_project_wbs(listing):
    """
    Complete Project WBS from the employer BOQ packages + lines.

      Level 0 = Project (tender)
      Level 1 = Building / works area (BA Block A, SH Social Hall, CV Civil...)
      Level 2 = Element / category (R.C Frame, Internal Finishes...)  = Task
      Level 3 = BOQ line activity (Columns, ceramic wall tiles...)     = Activity
    """
    packages = list(
        TenderBoqPackage.objects.filter(tender=listing)
        .prefetch_related("lines")
        .order_by("sort_order", "code")
    )
    groups_map = {}
    tot_packages = 0
    tot_activities = 0

    for pkg in packages:
        prefix, label = _wbs_group_key(pkg)
        if prefix not in groups_map:
            groups_map[prefix] = {
                "code": prefix,
                "name": label,
                "tasks": [],
                "activity_count": 0,
            }
        activities = []
        for i, line in enumerate(pkg.lines.all(), start=1):
            hint = _location_hint(line.description, pkg.title)
            activities.append({
                "seq": i,
                "code": line.bill_ref or ("L%s" % line.pk),
                "name": _activity_name(line.description, hint),
                "description": line.description or "",
                "unit": line.unit or "",
                "measure_unit": _measure_unit(line.unit),
                "quantity": line.quantity,
                "location_hint": hint,
            })
            tot_activities += 1
        groups_map[prefix]["tasks"].append({
            "code": pkg.code,
            "name": pkg.title,
            "sort_order": pkg.sort_order,
            "activities": activities,
            "activity_count": len(activities),
        })
        groups_map[prefix]["activity_count"] += len(activities)
        tot_packages += 1

    groups = sorted(groups_map.values(), key=lambda g: g["code"])
    for g in groups:
        g["tasks"].sort(key=lambda t: (t["sort_order"], t["code"]))

    return {
        "listing": listing,
        "ref": listing.event.ref,
        "title": listing.event.description,
        "groups": groups,
        "totals": {
            "groups": len(groups),
            "tasks": tot_packages,
            "activities": tot_activities,
        },
    }

