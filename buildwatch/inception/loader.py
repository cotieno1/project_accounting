"""Load sector-agnostic Inception programme profiles from JSON."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PROFILES_DIR = Path(__file__).resolve().parent / "profiles"


@lru_cache(maxsize=1)
def list_profiles() -> list[dict]:
    rows = []
    for path in sorted(PROFILES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        rows.append(
            {
                "id": data["id"],
                "title": data.get("title", data["id"]),
                "summary": data.get("summary", ""),
            }
        )
    return rows


@lru_cache(maxsize=32)
def get_profile(profile_id: str) -> dict | None:
    safe = (profile_id or "").strip()
    if not safe or ".." in safe or "/" in safe or "\\" in safe:
        return None
    path = PROFILES_DIR / f"{safe}.json"
    # Also allow id with dots matching filename
    if not path.exists():
        matches = list(PROFILES_DIR.glob(f"{safe}.json"))
        if not matches:
            # try exact filename from id (infrastructure.dam.json)
            candidate = PROFILES_DIR / f"{safe}.json"
            if not candidate.exists():
                for p in PROFILES_DIR.glob("*.json"):
                    data = json.loads(p.read_text(encoding="utf-8"))
                    if data.get("id") == safe:
                        return data
                return None
            path = candidate
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def default_profile_id() -> str:
    rows = list_profiles()
    return rows[0]["id"] if rows else ""


def empty_brief(profile: dict) -> dict:
    """Blank living-brief draft for session storage (no Django model yet)."""
    lanes = {}
    for lane in profile.get("lanes") or []:
        lanes[lane["id"]] = {"body": "", "updated_by": "", "updated_at": ""}
    return {
        "title": "",
        "profile_id": profile.get("id", ""),
        "lanes": lanes,
        "custody": {
            "type_id": "",
            "status": "UNKNOWN",
            "owner_note": "",
            "route_note": "",
        },
        "funding": {
            "type_id": "",
            "status": "UNFUNDED",
            "envelope": "",
            "source_note": "",
        },
        "activity": [],
        "decisions": [],
        "project_id": "",
    }


def readiness(brief: dict, profile: dict) -> dict:
    """Simple readiness flags for concept gate (UI only; not a full rules engine)."""
    lanes = brief.get("lanes") or {}
    mandate_ok = bool((lanes.get("mandate") or {}).get("body", "").strip())
    req_ok = bool((lanes.get("requirements") or {}).get("body", "").strip())
    feas_ok = bool((lanes.get("feasibility") or {}).get("body", "").strip())
    custody = brief.get("custody") or {}
    funding = brief.get("funding") or {}
    custody_ok = bool(custody.get("type_id") and custody.get("status") not in ("", "UNKNOWN"))
    funding_ok = bool(
        funding.get("type_id")
        and (funding.get("envelope") or "").strip()
        and funding.get("status") not in ("", "UNFUNDED")
    )
    checks = [
        {"id": "mandate.minimal", "label": "Mandate lane has content", "ok": mandate_ok},
        {"id": "requirements.minimal", "label": "Requirements lane has content", "ok": req_ok},
        {"id": "feasibility.minimal", "label": "Feasibility lane has content", "ok": feas_ok},
        {"id": "custody.route", "label": "Asset custody type + status set", "ok": custody_ok},
        {"id": "funding.envelope", "label": "Funding type + envelope set", "ok": funding_ok},
    ]
    concept_ready = all(c["ok"] for c in checks)
    return {
        "checks": checks,
        "concept_ready": concept_ready,
        "gates": profile.get("gates") or [],
    }
