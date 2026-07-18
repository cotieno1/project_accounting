# ============================================================================
# buildwatch/kickoff.py
#
# Pre-commencement SOP / project kick-off: after award the QS, PM, Contractor
# and Employer agree the work plan, confirm the pre-requisites and sign off.
# This drafts the SOP (standard prerequisites + party signatories).
# ============================================================================
from __future__ import annotations

from .models import (
    BidderRegistration,
    ProjectKickoffSOP,
    SOPPartySignoff,
    SOPPrerequisite,
    Submission,
    TenderConsultant,
)

# Standard pre-commencement checklist (draft SOP). (text, responsible party)
STANDARD_PREREQUISITES = [
    ("Signed contract agreement executed by the Employer and the Contractor.", "Employer & Contractor"),
    ("Performance security / bond lodged (per the contract percentage of the contract sum).", "Contractor"),
    ("Insurances in force: Contractor's All-Risk, WIBA / workmen's compensation, and third-party / public liability.", "Contractor"),
    ("Advance payment guarantee in place (where a mobilisation advance is to be paid).", "Contractor"),
    ("Site possession / handover to the Contractor recorded and dated.", "Employer / PM"),
    ("Programme of works (Gantt) agreed and signed by the QS, PM and Contractor.", "QS, PM & Contractor"),
    ("Setting-out, benchmarks and site survey verified by the PM / Engineer.", "PM / Engineer"),
    ("Site establishment: secure materials storage, CCTV, site security, sanitation and site office.", "Contractor"),
    ("Key personnel appointed; NCA / EBK and site-agent registrations submitted.", "Contractor"),
    ("Health & Safety plan and site risk assessment submitted and approved.", "Contractor / PM"),
    ("Environmental compliance (NEMA / EIA) confirmed where applicable.", "Contractor / Employer"),
    ("Materials approval and sample submission procedure agreed.", "QS / PM"),
    ("Anti-termite soil sterilization chemical and 5-year written guarantee procedure agreed.", "Contractor / PM"),
    ("Quality assurance, inspection and hold-point procedure agreed (compliance register).", "PM / QS"),
    ("Payment procedure agreed: milestone delivery -> certificate -> Requisition Order -> Payment Order.", "QS / Employer"),
]

# TenderConsultant.role -> SOP party role
_CONSULTANT_TO_PARTY = {
    TenderConsultant.PM_ENGINEER: SOPPartySignoff.PM_ENGINEER,
    TenderConsultant.QS: SOPPartySignoff.QS,
    TenderConsultant.ARCHITECT: SOPPartySignoff.ARCHITECT,
}


def _awarded_or_bidder_org(tender):
    sub = (
        Submission.objects
        .filter(event=tender.event, is_awarded=True)
        .select_related("submitter_org")
        .first()
    )
    if sub:
        return sub.submitter_org
    reg = (
        BidderRegistration.objects
        .filter(tender=tender)
        .select_related("organisation")
        .order_by("-registered_at")
        .first()
    )
    return reg.organisation if reg else None


def generate_sop_for_tender(tender, ua=None):
    """Create the draft kick-off SOP with prerequisites and party signatories.

    Idempotent: returns the existing SOP if one already exists for the tender.
    """
    project = getattr(getattr(tender, "event", None), "project", None)
    if project is None:
        return None, False

    existing = ProjectKickoffSOP.objects.filter(project=project, tender=tender).first()
    if existing:
        return existing, False

    sop = ProjectKickoffSOP.objects.create(
        project=project, tender=tender, created_by=ua,
    )

    for i, (text, resp) in enumerate(STANDARD_PREREQUISITES, start=1):
        SOPPrerequisite.objects.create(sop=sop, seq=i, text=text, responsible=resp)

    # Party signatories: Employer + consultant team + Contractor.
    owner = getattr(project, "owner_org", None)
    consultants = {c.role: c for c in tender.consultants.all()}

    parties = []
    parties.append((SOPPartySignoff.EMPLOYER, getattr(owner, "name", ""), True, 10))

    pm = consultants.get(TenderConsultant.PM_ENGINEER)
    parties.append((SOPPartySignoff.PM_ENGINEER,
                    pm.display_name if pm else "To be confirmed", True, 20))

    qs = consultants.get(TenderConsultant.QS)
    parties.append((SOPPartySignoff.QS,
                    qs.display_name if qs else "To be confirmed", True, 30))

    arch = consultants.get(TenderConsultant.ARCHITECT)
    if arch:
        parties.append((SOPPartySignoff.ARCHITECT, arch.display_name, False, 40))

    contractor = _awarded_or_bidder_org(tender)
    parties.append((SOPPartySignoff.CONTRACTOR,
                    getattr(contractor, "name", "") or "Awarded contractor", True, 50))

    for role, name, required, order in parties:
        SOPPartySignoff.objects.create(
            sop=sop, role=role, party_name=(name or "")[:200],
            is_required=required, sort_order=order,
        )

    return sop, True


def sop_progress(sop):
    """Return prerequisite + signature progress for display."""
    prereqs = list(sop.prerequisites.all())
    signoffs = list(sop.signoffs.all())
    done = sum(1 for p in prereqs if p.is_done)
    required = [s for s in signoffs if s.is_required]
    signed_required = [s for s in required if s.signed]
    return {
        "prereq_total": len(prereqs),
        "prereq_done": done,
        "prereq_pct": int(round(done * 100 / len(prereqs))) if prereqs else 0,
        "sign_total": len(required),
        "sign_done": len(signed_required),
        "all_signed": bool(required) and len(signed_required) == len(required),
    }
