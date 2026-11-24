"""Tests for core configuration, DB connectivity, and raw-layer ORM models."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.db import create_db_engine, create_session_factory
from app.ingestion.models import (
    RawServiceRecord,
    ScrapeError,
    ScrapeRun,
    ScrapeStatus,
    TriggerSource,
)


def test_settings_defaults_and_bounds() -> None:
    settings = Settings()
    assert settings.database_url.startswith("postgresql")
    assert "MedServicePriceBot" in settings.user_agent
    assert settings.default_min_delay_sec >= 1.5
    assert settings.raw_retention_days >= 90


def test_settings_rejects_unsafe_delay_and_retention() -> None:
    with pytest.raises(ValidationError):
        Settings(default_min_delay_sec=0.5)

    with pytest.raises(ValidationError):
        Settings(raw_retention_days=30)


def test_raw_layer_tables_exist_and_enforce_constraints() -> None:
    settings = Settings()
    engine = create_db_engine(settings.database_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"scrape_runs", "raw_service_records", "scrape_errors"}.issubset(tables)

    session_factory = create_session_factory(engine)
    now = datetime.now(UTC)
    run_id = uuid.uuid4()
    fp = f"fp-{uuid.uuid4().hex}"

    with session_factory() as session:
        run = ScrapeRun(
            id=run_id,
            source_id="kdlolymp",
            triggered_by=TriggerSource.MANUAL,
            status=ScrapeStatus.RUNNING,
            started_at=now,
        )
        session.add(run)
        session.flush()

        rec = RawServiceRecord(
            source_id="kdlolymp",
            source_url="https://kdlolymp.kz/pricelist",
            record_fingerprint=fp,
            clinic_name_raw="КДЛ Олимп",
            city_raw="Алматы",
            service_name_raw="Общий анализ крови (ОАК)",
            price_raw=Decimal("3200.00"),
            currency_raw="KZT",
            duration_days_raw=1,
            raw_payload={"code": "01-001", "price": "3200"},
            first_seen_at=now,
            last_seen_at=now,
            parsed_at=now,
            last_run_id=run_id,
        )
        session.add(rec)

        err = ScrapeError(
            run_id=run_id,
            source_id="kdlolymp",
            url="https://kdlolymp.kz/broken",
            error_type="parse_error",
            message="Invalid price cell",
            details={"row": 12},
            occurred_at=now,
        )
        session.add(err)
        session.commit()

    # Duplicate (source_id, record_fingerprint) must fail unique constraint
    with session_factory() as session:
        dup = RawServiceRecord(
            source_id="kdlolymp",
            source_url="https://kdlolymp.kz/pricelist",
            record_fingerprint=fp,
            clinic_name_raw="КДЛ Олимп",
            city_raw="Алматы",
            service_name_raw="Общий анализ крови (ОАК)",
            price_raw=Decimal("3200.00"),
            currency_raw="KZT",
            raw_payload={},
            first_seen_at=now,
            last_seen_at=now,
            parsed_at=now,
            last_run_id=run_id,
        )
        session.add(dup)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    # Cleanup test rows
    with session_factory() as session:
        session.query(ScrapeError).filter(ScrapeError.run_id == run_id).delete()
        session.query(RawServiceRecord).filter(RawServiceRecord.last_run_id == run_id).delete()
        session.query(ScrapeRun).filter(ScrapeRun.id == run_id).delete()
        session.commit()

    engine.dispose()
