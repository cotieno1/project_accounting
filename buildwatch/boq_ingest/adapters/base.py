"""Adapter contract for RFQ/BOQ formats."""
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
