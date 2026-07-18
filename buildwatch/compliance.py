"""Generate compliance / certification / sign-off checkpoints for a tender.

Anchors checkpoints to BOQ preamble clauses (hold points that need approval,
certificates / written guarantees, inspections) and adds a curated set of
site-readiness items (storage, CCTV, equipment, security, insurances).
"""
from __future__ import annotations

import re

# ── Clause classification keywords ───────────────────────────────────────────
_CERT_RE = re.compile(r"(?i)certif|guarantee|warrant")
_HOLD_RE = re.compile(
    r"(?i)\bapprov|to the approval of|shall report to the (architect|engineer)|"
    r"shall not be (filled|covered)|before .*(laid|placed|filled|covered up)|"
    r"notification to the (architect|engineer)|shall be inspected|\binspect\b"
)

_CLAUSE_RE = re.compile(r"^\(?[A-Za-z]\)?[.\)]?\s+\S")


def _is_subheading(s: str) -> bool:
    if len(s) > 45:
        return False
    words = s.split()
    if not words:
        return False
    caps = sum(1 for w in words if w[:1].isupper())
    return caps >= max(1, len(words) - 1) and not s.endswith(".")


def _groups(body: str):
    """Split a preamble body into (sub-heading, [clause texts]) groups."""
    groups: list[tuple[str, list[str]]] = []
    cur_head = "General"
    cur: list[str] = []
    for raw in body.splitlines():
        s = raw.strip()
        if not s:
            continue
        if _CLAUSE_RE.match(s):
            cur.append(s)
        elif _is_subheading(s):
            if cur:
                groups.append((cur_head, cur))
                cur = []
            cur_head = s
        else:
            if cur:
                cur[-1] = (cur[-1] + " " + s).strip()
    if cur:
        groups.append((cur_head, cur))
    return groups


def _roles_for(trade_code: str, category: str):
    """(responsible_role, approver_role) defaults by trade + category."""
    from buildwatch.models import ComplianceCheckpoint as C

    structural = trade_code in {"STEELWORK", "CONCRETE"}
    services = trade_code in {"PLUMBING", "METALWORK"}
    approver = C.ROLE_ENGINEER if (structural or services) else C.ROLE_ARCHITECT
    return C.ROLE_CONTRACTOR, approver


def _checkpoints_from_preamble(preamble, max_per_trade: int = 5):
    from buildwatch.models import ComplianceCheckpoint as C

    picks = []
    seen_titles = set()
    for head, clauses in _groups(preamble.body):
        joined = " ".join(clauses)
        is_cert = bool(_CERT_RE.search(joined))
        is_hold = bool(_HOLD_RE.search(joined))
        if not (is_cert or is_hold):
            continue
        title = head.strip() or preamble.title
        key = title.lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        category = C.CERTIFICATE if is_cert else C.HOLD_POINT
        resp, appr = _roles_for(preamble.trade_code, category)
        requirement = "\n".join(clauses)[:2000]
        picks.append({
            "title": "%s: %s" % (preamble.title, title),
            "requirement": requirement,
            "category": category,
            "responsible": resp,
            "approver": appr,
            "is_cert": is_cert,
        })
    # Certificates first, then hold points; cap per trade.
    picks.sort(key=lambda p: 0 if p["is_cert"] else 1)
    return picks[:max_per_trade]


def _site_readiness_defaults():
    from buildwatch.models import ComplianceCheckpoint as C

    return [
        ("SITE-STORAGE", "Secure materials store established",
         "A lockable, weatherproof materials store is set up on site with inventory "
         "control for cement, steel, fittings and finishes.",
         C.ROLE_CONTRACTOR, C.ROLE_CLIENT),
        ("SITE-CCTV", "CCTV / site surveillance operational",
         "CCTV cameras and recording are installed and operational covering stores, "
         "plant yard and the active works.",
         C.ROLE_CONTRACTOR, C.ROLE_CLIENT),
        ("SITE-SECURITY", "Site security and perimeter hoarding in place",
         "Perimeter hoarding / fencing and 24-hour security are in place before works begin.",
         C.ROLE_CONTRACTOR, C.ROLE_CLIENT),
        ("SITE-PLANT", "Major plant and equipment mobilised",
         "Key plant and equipment are mobilised to site and certified fit for use.",
         C.ROLE_CONTRACTOR, C.ROLE_ENGINEER),
        ("SITE-OFFICE", "Site office and welfare facilities set up",
         "Site office, sanitation and welfare facilities are established.",
         C.ROLE_CONTRACTOR, C.ROLE_CLIENT),
        ("SITE-SAFETY", "Safety, PPE and first-aid provisions in place",
         "OSH plan, PPE issue, signage and first-aid provisions are in place.",
         C.ROLE_CONTRACTOR, C.ROLE_ENGINEER),
        ("SITE-INSURANCE", "Insurances and performance security lodged",
         "Contractor all-risk insurance, WIBA and performance security are lodged and current.",
         C.ROLE_CONTRACTOR, C.ROLE_CLIENT),
        ("SITE-SETOUT", "Site set-out approved by the Engineer",
         "Setting-out and benchmarks are checked and approved before excavation begins.",
         C.ROLE_CONTRACTOR, C.ROLE_ENGINEER),
    ]


def _slug_code(prefix: str, title: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "-", title.upper()).strip("-")[:28]
    return ("%s-%s" % (prefix[:8], base))[:40] or prefix[:40]


def generate_checkpoints_for_tender(listing, *, replace: bool = False) -> int:
    """Create ComplianceCheckpoint rows for a tender. Returns count created.

    Idempotent: never duplicates a code, and never deletes checkpoints that
    already have sign-off progress.
    """
    from buildwatch.models import ComplianceCheckpoint as C

    if replace:
        listing.checkpoints.filter(
            status=C.STATUS_PENDING,
            responsible_user__isnull=True,
            evidence="",
        ).delete()

    # Codes already in the DB (idempotency) vs codes allocated in this run
    # (within-run disambiguation only). Generation is deterministic, so a
    # re-run maps each checkpoint to the same code and is skipped.
    db_existing = set(listing.checkpoints.values_list("code", flat=True))
    run_codes: set[str] = set()
    created = 0
    order = 0

    for code, title, req, resp, appr in _site_readiness_defaults():
        if code in run_codes or code in db_existing:
            run_codes.add(code)
            continue
        order += 10
        C.objects.create(
            tender=listing, code=code, title=title, requirement=req,
            category=C.SITE_READINESS, responsible_role=resp, approver_role=appr,
            sort_order=order,
        )
        run_codes.add(code)
        created += 1

    for pre in listing.preambles.all():
        for cp in _checkpoints_from_preamble(pre):
            base = _slug_code(pre.trade_code, cp["title"].split(":")[-1])
            code = base
            n = 2
            while code in run_codes:  # disambiguate within this run only
                code = ("%s%d" % (base[:38], n))[:40]
                n += 1
            run_codes.add(code)
            if code in db_existing:  # already created on a previous run
                continue
            order += 10
            C.objects.create(
                tender=listing, preamble=pre, code=code,
                title=cp["title"][:160], requirement=cp["requirement"],
                category=cp["category"], responsible_role=cp["responsible"],
                approver_role=cp["approver"], sort_order=order,
                source_page=pre.source_page,
            )
            created += 1

    return created
