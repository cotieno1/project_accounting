"""Canonical BOQ shape for BuildWatch bid packages."""
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
    source_page: int | None = None
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
