"""Adapter registry and auto-detect."""
from __future__ import annotations

from pathlib import Path

from .adapters.base import BoqAdapter

_REGISTRY: dict[str, BoqAdapter] = {}
_LOADED = False


def register(adapter: BoqAdapter) -> None:
    _REGISTRY[adapter.id] = adapter


def _ensure_builtins() -> None:
    global _LOADED
    if _LOADED:
        return
    from .adapters.emurua_ahp_pdf import EmuruaAhpPdfAdapter
    from .adapters.isiolo_domestic_pdf import IsioloDomesticPdfAdapter

    register(IsioloDomesticPdfAdapter())
    register(EmuruaAhpPdfAdapter())
    _LOADED = True


def get_adapter(adapter_id: str) -> BoqAdapter:
    _ensure_builtins()
    if adapter_id not in _REGISTRY:
        raise KeyError(
            "Unknown adapter %r. Available: %s" % (adapter_id, list_adapters())
        )
    return _REGISTRY[adapter_id]


def list_adapters() -> list[str]:
    _ensure_builtins()
    return sorted(_REGISTRY)


def detect_adapter(path: Path, text_sample: str = ""):
    _ensure_builtins()
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
