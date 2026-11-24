"""Abstract base class for pluggable clinic/laboratory source adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence

from app.ingestion.http_client import PoliteHttpClient
from app.ingestion.schemas import RawServiceInput, SourceInfo


class BaseSourceAdapter(ABC):
    """Contract implemented by every data source adapter without touching DB directly."""

    source_id: str
    display_name: str
    supported_format: str
    cities: Sequence[str] = ()
    enabled: bool = True

    def to_source_info(self) -> SourceInfo:
        """Build public metadata describing this adapter."""
        return SourceInfo(
            source_id=self.source_id,
            display_name=self.display_name,
            supported_format=self.supported_format,
            cities=list(self.cities),
            enabled=self.enabled,
        )

    @abstractmethod
    def fetch_records(
        self,
        client: PoliteHttpClient,
        limit: int | None = None,
    ) -> AsyncIterator[RawServiceInput]:
        """Async generator yielding validated RawServiceInput items."""
        ...
