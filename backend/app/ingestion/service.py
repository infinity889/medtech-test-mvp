"""Public provider service contract for the ingestion module."""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import Engine, delete, desc, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.db import create_db_engine, create_session_factory
from app.ingestion.adapters.registry import AdapterRegistry, default_registry
from app.ingestion.models import RawServiceRecord, ScrapeError, ScrapeRun, TriggerSource
from app.ingestion.runner import IngestionRunner
from app.ingestion.schemas import (
    RawServiceRecordDTO,
    ScrapeErrorDTO,
    ScrapeRunDTO,
    SourceInfo,
)

MIN_RAW_RETENTION_DAYS = 90


class IngestionService:
    """Facade consumed by normalization, search-api, scheduler, and CLI."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        registry: AdapterRegistry | None = None,
        settings: Settings | None = None,
        engine: Engine | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry or default_registry
        self._settings = settings or Settings()
        self._engine = engine
        self._runner = IngestionRunner(
            session_factory=self._session_factory,
            registry=self._registry,
            settings=self._settings,
        )

    def close(self) -> None:
        """Dispose owned SQLAlchemy engine resources if created by factory."""
        if self._engine is not None:
            self._engine.dispose()

    def list_sources(self, *, only_enabled: bool = False) -> list[SourceInfo]:
        """Return metadata for all registered adapters."""
        return self._registry.list_all(only_enabled=only_enabled)

    async def trigger_run(
        self,
        source_ids: Sequence[str] | None = None,
        *,
        triggered_by: Literal["manual", "cron"] = "manual",
        limit: int | None = None,
    ) -> list[ScrapeRunDTO]:
        """Trigger scraping for selected or all enabled sources with fault isolation."""
        trigger_enum = TriggerSource(triggered_by)
        return await self._runner.run_sources(
            source_ids=source_ids,
            triggered_by=trigger_enum,
            limit=limit,
        )

    def list_runs(
        self,
        *,
        source_id: str | None = None,
        limit: int = 20,
    ) -> list[ScrapeRunDTO]:
        """List recent scrape runs ordered newest first."""
        stmt = select(ScrapeRun).order_by(desc(ScrapeRun.started_at)).limit(limit)
        if source_id is not None:
            stmt = stmt.where(ScrapeRun.source_id == source_id)
        with self._session_factory() as session:
            rows = list(session.scalars(stmt))
        return [ScrapeRunDTO.model_validate(row) for row in rows]

    def list_errors(
        self,
        *,
        run_id: uuid.UUID | None = None,
        source_id: str | None = None,
        limit: int = 50,
    ) -> list[ScrapeErrorDTO]:
        """List structured scrape error log entries ordered newest first."""
        stmt = select(ScrapeError).order_by(desc(ScrapeError.occurred_at)).limit(limit)
        if run_id is not None:
            stmt = stmt.where(ScrapeError.run_id == run_id)
        if source_id is not None:
            stmt = stmt.where(ScrapeError.source_id == source_id)
        with self._session_factory() as session:
            rows = list(session.scalars(stmt))
        return [ScrapeErrorDTO.model_validate(row) for row in rows]

    def iter_raw_records(
        self,
        *,
        updated_since: datetime | None = None,
        source_id: str | None = None,
        batch_size: int = 500,
    ) -> Iterator[list[RawServiceRecordDTO]]:
        """Stream raw records in deterministic order for downstream normalization."""
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")

        offset = 0
        while True:
            stmt = (
                select(RawServiceRecord)
                .order_by(RawServiceRecord.last_seen_at.asc(), RawServiceRecord.id.asc())
                .offset(offset)
                .limit(batch_size)
            )
            if updated_since is not None:
                stmt = stmt.where(RawServiceRecord.last_seen_at >= updated_since)
            if source_id is not None:
                stmt = stmt.where(RawServiceRecord.source_id == source_id)

            with self._session_factory() as session:
                rows = list(session.scalars(stmt))

            if not rows:
                break

            yield [RawServiceRecordDTO.model_validate(row) for row in rows]
            if len(rows) < batch_size:
                break
            offset += batch_size

    def purge_expired_raw_records(self, retention_days: int = MIN_RAW_RETENTION_DAYS) -> int:
        """Delete raw records older than retention_days (enforcing >= 90 days audit policy)."""
        if retention_days < MIN_RAW_RETENTION_DAYS:
            raise ValueError(
                f"retention_days must be >= {MIN_RAW_RETENTION_DAYS} per audit policy"
            )
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        stmt = (
            delete(RawServiceRecord)
            .where(RawServiceRecord.last_seen_at < cutoff)
            .returning(RawServiceRecord.id)
        )
        with self._session_factory() as session:
            deleted_ids = list(session.scalars(stmt))
            session.commit()
            return len(deleted_ids)


def create_default_ingestion_service(settings: Settings | None = None) -> IngestionService:
    """Build an IngestionService wired to the configured PostgreSQL engine and default registry."""
    resolved_settings = settings or Settings()
    engine = create_db_engine(resolved_settings.database_url)
    session_factory = create_session_factory(engine)
    return IngestionService(
        session_factory=session_factory,
        registry=default_registry,
        settings=resolved_settings,
        engine=engine,
    )
