"""Parallel RFQ to Standard BOQ ingest library.

Additive only: not wired into tender publish, bid workspace, or seed_isiolo_boq.
Use dry_run_boq_ingest to parse a file to StandardBoq JSON without DB writes.
"""
from .registry import detect_adapter, get_adapter, list_adapters
from .schema import StandardBoq, StandardBoqCategory, StandardBoqLine

__all__ = [
    "StandardBoq",
    "StandardBoqCategory",
    "StandardBoqLine",
    "detect_adapter",
    "get_adapter",
    "list_adapters",
]
