from pathlib import Path
root = Path("buildwatch/boq_ingest")
(root / "adapters").mkdir(parents=True, exist_ok=True)

def w(rel, text):
    p = root / rel if not str(rel).startswith("buildwatch") else Path(rel)
    if not str(rel).startswith("buildwatch"):
        p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.replace("\r\n", "\n"), encoding="utf-8")
    print("wrote", p)

w("__init__.py", '''"""Parallel RFQ to Standard BOQ ingest library.

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
''')

w("schema.py", '''"""Canonical BOQ shape for BuildWatch bid packages."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class StandardBoqLine:
    bill_ref: str
    description: str
    unit: str
    quantity: Decimal
    sort_order: int = 0
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["quantity"] = str(self.quantity)
        return d


@dataclass
class StandardBoqCategory:
    code: str
    title: str
    sort_order: int = 0
    lines: list[StandardBoqLine] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "title": self.title,
            "sort_order": self.sort_order,
            "lines": [ln.to_dict() for ln in self.lines],
        }


@dataclass
class StandardBoq:
    """Normalized BOQ ready to map onto TenderBoqPackage / TenderBoqLine."""
    source_name: str
    adapter_id: str
    categories: list[StandardBoqCategory] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def line_count(self) -> int:
        return sum(len(c.lines) for c in self.categories)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "adapter_id": self.adapter_id,
            "warnings": list(self.warnings),
            "meta": dict(self.meta),
            "line_count": self.line_count,
            "packages": [c.to_dict() for c in self.categories],
        }
''')

w("normalize.py", '''"""Shared unit / quantity / description normalization."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


def normalize_unit(raw: str) -> str:
    u = (raw or "").rstrip(".").strip()
    ul = u.lower()
    if ul.startswith("no"):
        return "No"
    if ul.startswith("lm") or ul == "m":
        return "Lm"
    if ul == "sum":
        return "Sum"
    if ul == "item":
        return "Item"
    if ul == "lot":
        return "Lot"
    if ul == "set":
        return "Set"
    return (u or "No")[:30]


def parse_qty(raw) -> Decimal:
    if isinstance(raw, Decimal):
        return raw
    s = str(raw).replace(",", "").strip()
    try:
        q = Decimal(s)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid quantity: %r" % (raw,)) from exc
    if q <= 0:
        raise ValueError("quantity must be > 0: %r" % (raw,))
    return q


def clean_description(text: str, max_len: int = 255) -> str:
    desc = re.sub(r"\s+", " ", (text or "").strip(" -.,"))
    return desc[:max_len]
''')

w("adapters/base.py", '''"""Adapter contract for RFQ/BOQ formats."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..schema import StandardBoq


class BoqAdapter(ABC):
    """One adapter per known RFQ/BOQ layout family."""

    id: str = "base"
    label: str = "Base"

    @abstractmethod
    def can_handle(self, path: Path, text_sample: str = "") -> float:
        """Return confidence 0.0-1.0 that this adapter matches the file."""

    @abstractmethod
    def parse(self, path: Path) -> StandardBoq:
        """Parse source file into StandardBoq (no DB side effects)."""
''')

w("registry.py", '''"""Adapter registry and auto-detect."""
from __future__ import annotations

from pathlib import Path

from .adapters.base import BoqAdapter

_REGISTRY: dict[str, BoqAdapter] = {}


def register(adapter: BoqAdapter) -> None:
    _REGISTRY[adapter.id] = adapter


def get_adapter(adapter_id: str) -> BoqAdapter:
    from . import adapters as _adapters  # noqa: F401

    if adapter_id not in _REGISTRY:
        raise KeyError(
            "Unknown adapter %r. Available: %s" % (adapter_id, list_adapters())
        )
    return _REGISTRY[adapter_id]


def list_adapters() -> list[str]:
    from . import adapters as _adapters  # noqa: F401

    return sorted(_REGISTRY)


def detect_adapter(path: Path, text_sample: str = ""):
    from . import adapters as _adapters  # noqa: F401

    best = None
    best_score = 0.0
    for adapter in _REGISTRY.values():
        score = adapter.can_handle(path, text_sample=text_sample)
        if score > best_score:
            best = adapter
            best_score = score
    if best is None or best_score <= 0:
        raise ValueError(
            "No adapter matched %s. Try --adapter %s"
            % (path.name, list_adapters())
        )
    return best, best_score
''')

print("core files written")