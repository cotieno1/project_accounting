# -*- coding: utf-8 -*-
"""Helpers for the three-column inception collaboration workspace."""
from __future__ import annotations

from django.utils import timezone

from buildwatch.inception.loader import get_profile
from buildwatch.models_inception import (
    InceptionParticipant,
    WorkshopContribution,
)

# Full classic pack (buildings). Profiles may override via contribution_types.
DEFAULT_CONTRIB_TYPES = [
    ("SPONSOR_WHY", "Why: Strategic rationale", "SPONSOR"),
    ("SPONSOR_FUNDING", "Funding: Source and structure", "SPONSOR"),
    ("SPONSOR_OUTCOME", "Outcome: Definition of success", "SPONSOR"),
    ("BUSINESS_NEED", "Need: Problem being solved", "BUSINESS"),
    ("BUSINESS_USERS", "Users: Who and how many", "BUSINESS"),
    ("BUSINESS_WISHLIST", "Wish list: Requirements", "BUSINESS"),
    ("BUSINESS_PRIORITY", "Priority: Must-have vs nice-to-have", "BUSINESS"),
    ("TECH_SITE", "Site: Analysis and constraints", "TECHNICAL"),
    ("TECH_CONCEPT", "Concept: Design approach", "TECHNICAL"),
    ("TECH_STRUCTURE", "Structure: Systems and materials", "TECHNICAL"),
    ("TECH_STANDARDS", "Standards: Applicable codes", "TECHNICAL"),
    ("TECH_RISKS", "Risks: Technical risks", "TECHNICAL"),
    ("TECH_BUDGET", "Budget: High-level estimate (QS)", "TECHNICAL"),
    ("TECH_PROGRAMME", "Programme: Time estimate", "TECHNICAL"),
]

LANE_FROM_PREFIX = {
    "SPONSOR": WorkshopContribution.LANE_MANDATE,
    "BUSINESS": WorkshopContribution.LANE_REQUIREMENTS,
    "TECH": WorkshopContribution.LANE_FEASIBILITY,
}


def contribution_type_rows(profile_id: str) -> list[dict]:
    profile = get_profile(profile_id) or {}
    rows = profile.get("contribution_types") or []
    if rows:
        out = []
        for row in rows:
            code = (row.get("id") or "").strip()
            if not code:
                continue
            role = (row.get("role") or "").strip().upper()
            if not role:
                if code.startswith("SPONSOR"):
                    role = "SPONSOR"
                elif code.startswith("BUSINESS"):
                    role = "BUSINESS"
                else:
                    role = "TECHNICAL"
            out.append(
                {
                    "key": code,
                    "label": row.get("label") or code,
                    "role": role,
                }
            )
        return out
    return [
        {"key": k, "label": lab, "role": role}
        for k, lab, role in DEFAULT_CONTRIB_TYPES
    ]


def contributions_map(inception) -> dict:
    return {
        c.contribution_type: c
        for c in inception.contributions.all()
    }


def column_blocks(inception, profile_id: str) -> dict:
    """Split contribution types into sponsor / business / technical columns."""
    cmap = contributions_map(inception)
    sponsor, business, technical = [], [], []
    for row in contribution_type_rows(profile_id):
        item = {
            **row,
            "contrib": cmap.get(row["key"]),
            "is_budget": row["key"] == WorkshopContribution.TECH_BUDGET,
        }
        if row["role"] == "SPONSOR":
            sponsor.append(item)
        elif row["role"] == "BUSINESS":
            business.append(item)
        else:
            technical.append(item)
    return {
        "sponsor_blocks": sponsor,
        "business_blocks": business,
        "technical_blocks": technical,
        "sponsor_done": bool(sponsor) and all(
            b["contrib"] and (b["contrib"].content or "").strip() for b in sponsor
        ),
        "business_done": bool(business) and all(
            b["contrib"] and (b["contrib"].content or "").strip() for b in business
        ),
        "technical_done": bool(technical)
        and all(
            (
                b["is_budget"]
                and hasattr(inception, "concept_budget")
                and inception.concept_budget
            )
            or (b["contrib"] and (b["contrib"].content or "").strip())
            for b in technical
        ),
    }


def sync_lanes_from_typed_contributions(inception, who: str = "") -> None:
    """Keep living-brief lanes in sync so concept readiness still works."""
    by_type = contributions_map(inception)
    buckets = {
        WorkshopContribution.LANE_MANDATE: [],
        WorkshopContribution.LANE_REQUIREMENTS: [],
        WorkshopContribution.LANE_FEASIBILITY: [],
    }
    for code, contrib in by_type.items():
        body = (contrib.content or "").strip()
        if not body:
            continue
        if code.startswith("SPONSOR") or code == WorkshopContribution.LANE_MANDATE:
            buckets[WorkshopContribution.LANE_MANDATE].append(body)
        elif code.startswith("BUSINESS") or code == WorkshopContribution.LANE_REQUIREMENTS:
            buckets[WorkshopContribution.LANE_REQUIREMENTS].append(body)
        elif code.startswith("TECH") or code == WorkshopContribution.LANE_FEASIBILITY:
            buckets[WorkshopContribution.LANE_FEASIBILITY].append(body)

    for lane_id, parts in buckets.items():
        text = "\n\n".join(parts)
        WorkshopContribution.objects.update_or_create(
            inception=inception,
            contribution_type=lane_id,
            defaults={
                "content": text,
                "updated_by_name": who,
            },
        )


def save_typed_contribution(
    *,
    inception,
    contribution_type: str,
    content: str,
    participant: InceptionParticipant | None,
    who: str,
) -> WorkshopContribution:
    contrib, _ = WorkshopContribution.objects.update_or_create(
        inception=inception,
        contribution_type=contribution_type,
        defaults={
            "content": content,
            "participant": participant,
            "updated_by_name": who,
        },
    )
    sync_lanes_from_typed_contributions(inception, who=who)
    if inception.stage == inception.STAGE_CONCEPT:
        inception.stage = inception.STAGE_WORKSHOP
        inception.save(update_fields=["stage", "updated_at"])
    return contrib


def sections_complete(inception, profile_id: str) -> bool:
    cols = column_blocks(inception, profile_id)
    return bool(
        cols["sponsor_done"] and cols["business_done"] and cols["technical_done"]
    )


def mark_documented_if_ready(inception, profile_id: str) -> None:
    if sections_complete(inception, profile_id) and inception.stage in (
        inception.STAGE_CONCEPT,
        inception.STAGE_WORKSHOP,
    ):
        inception.stage = inception.STAGE_DOCUMENTED
        inception.save(update_fields=["stage", "updated_at"])
