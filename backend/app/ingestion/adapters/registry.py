"""Registry of pluggable source adapters."""

from __future__ import annotations

from collections.abc import Sequence

from app.ingestion.adapters.base import BaseSourceAdapter
from app.ingestion.schemas import SourceInfo


class UnknownSourceError(KeyError):
    """Raised when a requested source_id is not registered."""


class AdapterRegistry:
    """In-memory registry enabling new sources to plug in without editing core runner code."""

    def __init__(self) -> None:
        self._adapters: dict[str, BaseSourceAdapter] = {}

    def register(self, adapter: BaseSourceAdapter) -> None:
        if adapter.source_id in self._adapters:
            raise ValueError(f"Adapter '{adapter.source_id}' is already registered")
        self._adapters[adapter.source_id] = adapter

    def get(self, source_id: str) -> BaseSourceAdapter:
        adapter = self._adapters.get(source_id)
        if adapter is None:
            raise UnknownSourceError(f"Unknown source_id: '{source_id}'")
        return adapter

    def list_all(self, *, only_enabled: bool = False) -> list[SourceInfo]:
        adapters = list(self._adapters.values())
        if only_enabled:
            adapters = [a for a in adapters if a.enabled]
        return [a.to_source_info() for a in adapters]

    def resolve(self, source_ids: Sequence[str] | None = None) -> list[BaseSourceAdapter]:
        if source_ids is None:
            return [a for a in self._adapters.values() if a.enabled]
        return [self.get(sid) for sid in source_ids]


default_registry = AdapterRegistry()
