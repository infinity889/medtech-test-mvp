"""Fault-isolated, deduplicating ingestion runner writing into the raw layer."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import Executable, func, literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.ingestion.adapters.base import BaseSourceAdapter
from app.ingestion.adapters.registry import AdapterRegistry
from app.ingestion.http_client import HttpFetchError, PoliteHttpClient, RobotsDisallowedError
from app.ingestion.models import (
    RawServiceRecord,
    ScrapeError,
    ScrapeRun,
    ScrapeStatus,
    TriggerSource,
)
from app.ingestion.schemas import RawServiceInput, ScrapeRunDTO, compute_record_fingerprint


def _default_http_client_factory(settings: Settings) -> PoliteHttpClient:
    return PoliteHttpClient(
        user_agent=settings.user_agent,
        min_delay_sec=settings.default_min_delay_sec,
        max_jitter_sec=settings.default_max_jitter_sec,
        timeout_sec=settings.http_timeout_sec,
        max_retries=settings.http_max_retries,
    )


def _classify_error(exc: Exception) -> tuple[str, str | None, dict[str, object]]:
    if isinstance(exc, RobotsDisallowedError):
        return "robots_disallowed", exc.url, {}
    if isinstance(exc, HttpFetchError):
        return "http_error", exc.url, {"status_code": exc.status_code}
    if isinstance(exc, ValidationError):
        return "validation_error", None, {"errors": exc.errors()}
    return "unexpected_error", None, {"exception_type": type(exc).__name__}


class IngestionRunner:
    """Executes source adapters with strict fault isolation and idempotent raw-layer upserts."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        registry: AdapterRegistry,
        settings: Settings | None = None,
        http_client_factory: Callable[[], PoliteHttpClient] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry
        self._settings = settings or Settings()
        self._http_client_factory = http_client_factory or (
            lambda: _default_http_client_factory(self._settings)
        )

    async def run_sources(
        self,
        source_ids: Sequence[str] | None = None,
        *,
        triggered_by: TriggerSource = TriggerSource.MANUAL,
        limit: int | None = None,
    ) -> list[ScrapeRunDTO]:
        """Run each requested adapter sequentially; failure in one never aborts the rest."""
        adapters = self._registry.resolve(source_ids)
        results: list[ScrapeRunDTO] = []

        async with self._http_client_factory() as client:
            for adapter in adapters:
                run_dto = await self._run_single_adapter(
                    adapter=adapter,
                    client=client,
                    triggered_by=triggered_by,
                    limit=limit,
                )
                results.append(run_dto)

        return results

    async def _run_single_adapter(
        self,
        *,
        adapter: BaseSourceAdapter,
        client: PoliteHttpClient,
        triggered_by: TriggerSource,
        limit: int | None,
    ) -> ScrapeRunDTO:
        started_at = datetime.now(UTC)
        run_id = uuid.uuid4()

        with self._session_factory() as session:
            run = ScrapeRun(
                id=run_id,
                source_id=adapter.source_id,
                triggered_by=triggered_by,
                status=ScrapeStatus.RUNNING,
                started_at=started_at,
            )
            session.add(run)
            session.commit()

        records_fetched = 0
        records_inserted = 0
        records_updated = 0
        errors_count = 0
        seen_fingerprints: set[str] = set()

        try:
            async for item in adapter.fetch_records(client, limit=limit):
                records_fetched += 1
                try:
                    validated = (
                        item
                        if isinstance(item, RawServiceInput)
                        else RawServiceInput.model_validate(item)
                    )
                except ValidationError as exc:
                    errors_count += 1
                    self._record_error(run_id, adapter.source_id, exc)
                    continue

                fingerprint = compute_record_fingerprint(adapter.source_id, validated)
                if fingerprint in seen_fingerprints:
                    continue
                seen_fingerprints.add(fingerprint)

                was_inserted = self._upsert_raw_record(
                    run_id=run_id,
                    source_id=adapter.source_id,
                    fingerprint=fingerprint,
                    item=validated,
                )
                if was_inserted:
                    records_inserted += 1
                else:
                    records_updated += 1
        except Exception as exc:  # noqa: BLE001 — isolate any adapter crash
            errors_count += 1
            self._record_error(run_id, adapter.source_id, exc)

        finished_at = datetime.now(UTC)
        processed_count = records_inserted + records_updated
        if errors_count == 0:
            final_status = ScrapeStatus.SUCCESS
        elif processed_count > 0:
            final_status = ScrapeStatus.PARTIAL
        else:
            final_status = ScrapeStatus.FAILED

        with self._session_factory() as session:
            run_row = session.get(ScrapeRun, run_id)
            assert run_row is not None
            run_row.status = final_status
            run_row.finished_at = finished_at
            run_row.records_fetched = records_fetched
            run_row.records_inserted = records_inserted
            run_row.records_updated = records_updated
            run_row.errors_count = errors_count
            session.commit()
            session.refresh(run_row)
            return ScrapeRunDTO.model_validate(run_row)

    def _upsert_raw_record(
        self,
        *,
        run_id: uuid.UUID,
        source_id: str,
        fingerprint: str,
        item: RawServiceInput,
    ) -> bool:
        now = datetime.now(UTC)
        stmt = pg_insert(RawServiceRecord).values(
            id=uuid.uuid4(),
            source_id=source_id,
            source_url=str(item.source_url),
            record_fingerprint=fingerprint,
            clinic_name_raw=item.clinic_name_raw.strip(),
            city_raw=item.city_raw.strip(),
            address_raw=item.address_raw.strip() if item.address_raw else None,
            phone_raw=item.phone_raw.strip() if item.phone_raw else None,
            working_hours_raw=item.working_hours_raw.strip() if item.working_hours_raw else None,
            latitude=item.latitude,
            longitude=item.longitude,
            clinic_rating_raw=item.clinic_rating_raw,
            has_online_booking=item.has_online_booking,
            service_name_raw=item.service_name_raw.strip(),
            category_hint=item.category_hint.strip() if item.category_hint else None,
            price_raw=item.price_raw,
            currency_raw=item.currency_raw.upper(),
            duration_days_raw=item.duration_days_raw,
            raw_payload=item.raw_payload,
            first_seen_at=now,
            last_seen_at=now,
            parsed_at=now,
            last_run_id=run_id,
        )
        excluded = stmt.excluded
        upsert_stmt: Executable = stmt.on_conflict_do_update(
            constraint="uq_raw_source_fingerprint",
            set_={
                "source_url": excluded.source_url,
                "phone_raw": func.coalesce(excluded.phone_raw, RawServiceRecord.phone_raw),
                "working_hours_raw": func.coalesce(
                    excluded.working_hours_raw, RawServiceRecord.working_hours_raw
                ),
                "latitude": func.coalesce(excluded.latitude, RawServiceRecord.latitude),
                "longitude": func.coalesce(excluded.longitude, RawServiceRecord.longitude),
                "clinic_rating_raw": func.coalesce(
                    excluded.clinic_rating_raw, RawServiceRecord.clinic_rating_raw
                ),
                "has_online_booking": func.coalesce(
                    excluded.has_online_booking, RawServiceRecord.has_online_booking
                ),
                "category_hint": func.coalesce(
                    excluded.category_hint, RawServiceRecord.category_hint
                ),
                "raw_payload": excluded.raw_payload,
                "last_seen_at": excluded.last_seen_at,
                "parsed_at": excluded.parsed_at,
                "last_run_id": excluded.last_run_id,
            },
        ).returning(literal_column("(xmax = 0)").label("inserted"))

        with self._session_factory() as session:
            inserted = bool(session.execute(upsert_stmt).scalar_one())
            session.commit()
            return inserted

    def _record_error(self, run_id: uuid.UUID, source_id: str, exc: Exception) -> None:
        error_type, url, details = _classify_error(exc)
        with self._session_factory() as session:
            session.add(
                ScrapeError(
                    run_id=run_id,
                    source_id=source_id,
                    url=url,
                    error_type=error_type,
                    message=str(exc),
                    details=details or None,
                    occurred_at=datetime.now(UTC),
                )
            )
            session.commit()
