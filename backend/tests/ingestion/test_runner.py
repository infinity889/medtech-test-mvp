"""Integration tests for AdapterRegistry and IngestionRunner against PostgreSQL."""

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

from sqlalchemy import delete, func, select

from app.core.config import Settings
from app.core.db import create_db_engine, create_session_factory
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
from app.ingestion.runner import IngestionRunner
from app.ingestion.schemas import RawServiceInput


class StaticAdapter(BaseSourceAdapter):
    """Test adapter returning predefined records."""

    def __init__(
        self,
        source_id: str,
        records: list[RawServiceInput],
        *,
        fail_after: Exception | None = None,
    ) -> None:
        self.source_id = source_id
        self.display_name = f"Static {source_id}"
        self.supported_format = "html"
        self.cities = ("Алматы",)
        self._records = records
        self._fail_after = fail_after

    async def fetch_records(
        self,
        client: PoliteHttpClient,
        limit: int | None = None,
    ) -> AsyncIterator[RawServiceInput]:
        for count, rec in enumerate(self._records):
            if limit is not None and count >= limit:
                break
            yield rec
        if self._fail_after is not None:
            raise self._fail_after


def _make_record(service: str, price: str, *, city: str = "Алматы") -> RawServiceInput:
    return RawServiceInput(
        clinic_name_raw="Тест Лаб",
        city_raw=city,
        address_raw="ул. Абая 10",
        service_name_raw=service,
        price_raw=Decimal(price),
        currency_raw="KZT",
        duration_days_raw=1,
        source_url="https://example.kz/prices",
        raw_payload={"service": service, "price": price},
    )


def _cleanup_source(session_factory: object, source_ids: list[str]) -> None:
    from sqlalchemy.orm import Session, sessionmaker

    assert isinstance(session_factory, sessionmaker)
    with session_factory() as session:
        assert isinstance(session, Session)
        session.execute(delete(ScrapeError).where(ScrapeError.source_id.in_(source_ids)))
        session.execute(delete(RawServiceRecord).where(RawServiceRecord.source_id.in_(source_ids)))
        session.execute(delete(ScrapeRun).where(ScrapeRun.source_id.in_(source_ids)))
        session.commit()


async def test_runner_deduplicates_on_rerun_and_versions_on_price_change() -> None:
    engine = create_db_engine(Settings().database_url)
    session_factory = create_session_factory(engine)
    src = f"test_dedup_{uuid.uuid4().hex[:8]}"

    try:
        rec_a = _make_record("ОАК", "3000")
        rec_b = _make_record("Биохимия", "5500")

        registry = AdapterRegistry()
        # Include an intra-run duplicate of rec_a to test within-run deduplication too
        registry.register(StaticAdapter(src, [rec_a, rec_a, rec_b]))

        runner = IngestionRunner(session_factory=session_factory, registry=registry)
        first_runs = await runner.run_sources([src], triggered_by=TriggerSource.MANUAL)

        assert len(first_runs) == 1
        assert first_runs[0].status == ScrapeStatus.SUCCESS
        assert first_runs[0].records_inserted == 2
        assert first_runs[0].records_updated == 0

        # Re-run with identical data -> 0 inserted, 2 updated
        second_runs = await runner.run_sources([src], triggered_by=TriggerSource.CRON)
        assert second_runs[0].status == ScrapeStatus.SUCCESS
        assert second_runs[0].records_inserted == 0
        assert second_runs[0].records_updated == 2

        # Price change on ОАК -> 1 new row inserted, 1 unchanged row updated, total 3 rows in DB
        rec_a_new_price = _make_record("ОАК", "3200")
        registry_v2 = AdapterRegistry()
        registry_v2.register(StaticAdapter(src, [rec_a_new_price, rec_b]))
        runner_v2 = IngestionRunner(session_factory=session_factory, registry=registry_v2)

        third_runs = await runner_v2.run_sources([src], triggered_by=TriggerSource.MANUAL)
        assert third_runs[0].status == ScrapeStatus.SUCCESS
        assert third_runs[0].records_inserted == 1
        assert third_runs[0].records_updated == 1

        with session_factory() as session:
            total = session.scalar(
                select(func.count()).select_from(RawServiceRecord).where(
                    RawServiceRecord.source_id == src
                )
            )
            assert total == 3
    finally:
        _cleanup_source(session_factory, [src])
        engine.dispose()


async def test_runner_isolates_failures_and_logs_scrape_errors() -> None:
    engine = create_db_engine(Settings().database_url)
    session_factory = create_session_factory(engine)
    bad_src = f"test_bad_{uuid.uuid4().hex[:8]}"
    partial_src = f"test_part_{uuid.uuid4().hex[:8]}"
    good_src = f"test_good_{uuid.uuid4().hex[:8]}"

    try:
        registry = AdapterRegistry()
        registry.register(
            StaticAdapter(
                bad_src,
                [],
                fail_after=RobotsDisallowedError("https://blocked.kz/prices"),
            )
        )
        registry.register(
            StaticAdapter(
                partial_src,
                [_make_record("УЗИ", "9000")],
                fail_after=HttpFetchError("https://partial.kz/page2", "HTTP 503", status_code=503),
            )
        )
        registry.register(StaticAdapter(good_src, [_make_record("Ферритин", "4800")]))

        runner = IngestionRunner(session_factory=session_factory, registry=registry)
        runs = await runner.run_sources(
            [bad_src, partial_src, good_src], triggered_by=TriggerSource.MANUAL
        )

        by_src = {r.source_id: r for r in runs}
        assert by_src[bad_src].status == ScrapeStatus.FAILED
        assert by_src[bad_src].errors_count == 1
        assert by_src[bad_src].records_inserted == 0

        assert by_src[partial_src].status == ScrapeStatus.PARTIAL
        assert by_src[partial_src].errors_count == 1
        assert by_src[partial_src].records_inserted == 1

        assert by_src[good_src].status == ScrapeStatus.SUCCESS
        assert by_src[good_src].errors_count == 0
        assert by_src[good_src].records_inserted == 1

        with session_factory() as session:
            errors = list(
                session.scalars(
                    select(ScrapeError).where(ScrapeError.source_id.in_([bad_src, partial_src]))
                )
            )
            error_types = {e.source_id: e.error_type for e in errors}
            assert error_types[bad_src] == "robots_disallowed"
            assert error_types[partial_src] == "http_error"
    finally:
        _cleanup_source(session_factory, [bad_src, partial_src, good_src])
        engine.dispose()
