"""Integration tests for IngestionService public contract, scheduler, and CLI."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, update

from app.core.config import Settings
from app.core.db import create_db_engine, create_session_factory
from app.ingestion.adapters.base import BaseSourceAdapter
from app.ingestion.adapters.registry import AdapterRegistry
from app.ingestion.cli import run_cli
from app.ingestion.http_client import PoliteHttpClient, RobotsDisallowedError
from app.ingestion.models import RawServiceRecord, ScrapeError, ScrapeRun
from app.ingestion.scheduler import create_ingestion_scheduler
from app.ingestion.schemas import RawServiceInput
from app.ingestion.service import IngestionService


class DummyServiceAdapter(BaseSourceAdapter):
    """Deterministic adapter for testing IngestionService."""

    def __init__(
        self,
        source_id: str,
        records: list[RawServiceInput],
        *,
        fail: Exception | None = None,
    ) -> None:
        self.source_id = source_id
        self.display_name = f"Dummy {source_id}"
        self.supported_format = "json"
        self.cities = ("Алматы", "Астана")
        self._records = records
        self._fail = fail

    async def fetch_records(
        self,
        client: PoliteHttpClient,
        limit: int | None = None,
    ) -> AsyncIterator[RawServiceInput]:
        for idx, rec in enumerate(self._records):
            if limit is not None and idx >= limit:
                break
            yield rec
        if self._fail is not None:
            raise self._fail


def _sample(service: str, price: str) -> RawServiceInput:
    return RawServiceInput(
        clinic_name_raw="Клиника Альфа",
        city_raw="Алматы",
        service_name_raw=service,
        price_raw=Decimal(price),
        currency_raw="KZT",
        source_url="https://alpha.kz/prices",
    )


async def test_service_contract_runs_errors_and_streaming() -> None:
    engine = create_db_engine(Settings().database_url)
    session_factory = create_session_factory(engine)
    src_ok = f"svc_ok_{uuid.uuid4().hex[:8]}"
    src_err = f"svc_err_{uuid.uuid4().hex[:8]}"

    try:
        registry = AdapterRegistry()
        registry.register(
            DummyServiceAdapter(src_ok, [_sample("ОАК", "2500"), _sample("ТТГ", "3900")])
        )
        registry.register(
            DummyServiceAdapter(
                src_err,
                [],
                fail=RobotsDisallowedError("https://blocked.kz/catalog"),
            )
        )

        service = IngestionService(session_factory=session_factory, registry=registry)
        sources = service.list_sources()
        assert {s.source_id for s in sources} == {src_ok, src_err}

        runs = await service.trigger_run(triggered_by="manual")
        assert len(runs) == 2

        listed_runs = service.list_runs(source_id=src_ok, limit=5)
        assert len(listed_runs) == 1
        assert listed_runs[0].records_inserted == 2

        listed_errors = service.list_errors(source_id=src_err, limit=10)
        assert len(listed_errors) == 1
        assert listed_errors[0].error_type == "robots_disallowed"

        batches = list(service.iter_raw_records(source_id=src_ok, batch_size=1))
        assert len(batches) == 2
        assert {batches[0][0].service_name_raw, batches[1][0].service_name_raw} == {"ОАК", "ТТГ"}

        future = datetime.now(UTC) + timedelta(minutes=5)
        assert list(service.iter_raw_records(source_id=src_ok, updated_since=future)) == []
    finally:
        with session_factory() as session:
            session.execute(delete(ScrapeError).where(ScrapeError.source_id.in_([src_ok, src_err])))
            session.execute(
                delete(RawServiceRecord).where(RawServiceRecord.source_id.in_([src_ok, src_err]))
            )
            session.execute(delete(ScrapeRun).where(ScrapeRun.source_id.in_([src_ok, src_err])))
            session.commit()
        engine.dispose()


async def test_purge_enforces_90_day_minimum_and_deletes_only_expired() -> None:
    engine = create_db_engine(Settings().database_url)
    session_factory = create_session_factory(engine)
    src = f"svc_purge_{uuid.uuid4().hex[:8]}"

    try:
        registry = AdapterRegistry()
        registry.register(
            DummyServiceAdapter(src, [_sample("Старая услуга", "1000"), _sample("Свежая", "2000")])
        )
        service = IngestionService(session_factory=session_factory, registry=registry)
        await service.trigger_run([src], triggered_by="manual")

        with pytest.raises(ValueError, match="90"):
            service.purge_expired_raw_records(retention_days=89)

        now = datetime.now(UTC)
        with session_factory() as session:
            session.execute(
                update(RawServiceRecord)
                .where(
                    RawServiceRecord.source_id == src,
                    RawServiceRecord.service_name_raw == "Старая услуга",
                )
                .values(last_seen_at=now - timedelta(days=95))
            )
            session.execute(
                update(RawServiceRecord)
                .where(
                    RawServiceRecord.source_id == src,
                    RawServiceRecord.service_name_raw == "Свежая",
                )
                .values(last_seen_at=now - timedelta(days=89))
            )
            session.commit()

        deleted_count = service.purge_expired_raw_records(retention_days=90)
        assert deleted_count >= 1

        remaining = [r for batch in service.iter_raw_records(source_id=src) for r in batch]
        assert len(remaining) == 1
        assert remaining[0].service_name_raw == "Свежая"
    finally:
        with session_factory() as session:
            session.execute(delete(ScrapeError).where(ScrapeError.source_id == src))
            session.execute(delete(RawServiceRecord).where(RawServiceRecord.source_id == src))
            session.execute(delete(ScrapeRun).where(ScrapeRun.source_id == src))
            session.commit()
        engine.dispose()


def test_scheduler_and_cli_commands(capsys: pytest.CaptureFixture[str]) -> None:
    engine = create_db_engine(Settings().database_url)
    session_factory = create_session_factory(engine)
    try:
        registry = AdapterRegistry()
        registry.register(DummyServiceAdapter("demo_lab", [_sample("ОАК", "3000")]))
        service = IngestionService(session_factory=session_factory, registry=registry)

        scheduler = create_ingestion_scheduler(service, interval_hours=24)
        jobs = scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == "daily_ingestion_run"

        exit_code = run_cli(["list-sources"], service=service)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "demo_lab" in captured.out
    finally:
        engine.dispose()
