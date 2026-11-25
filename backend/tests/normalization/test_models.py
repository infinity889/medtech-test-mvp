"""Tests for normalization settings, ORM models, and PostgreSQL constraints."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, inspect
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.db import create_db_engine, create_session_factory
from app.ingestion.models import RawServiceRecord, ScrapeRun, ScrapeStatus, TriggerSource
from app.normalization.models import (
    Clinic,
    CurrencyCode,
    MatchMethod,
    PriceHistory,
    ServiceCatalog,
    ServiceCategory,
    ServiceOffer,
    UnmatchedService,
    UnmatchedStatus,
)


def test_normalization_settings_validation() -> None:
    settings = Settings()
    assert settings.usd_to_kzt_rate == Decimal("495.00")
    assert settings.fuzzy_match_threshold == 86.0
    assert settings.fuzzy_suggestion_threshold == 60.0
    assert settings.offer_max_age_days == 30

    with pytest.raises(ValidationError):
        Settings(fuzzy_match_threshold=70.0, fuzzy_suggestion_threshold=80.0)

    with pytest.raises(ValidationError):
        Settings(usd_to_kzt_rate=Decimal("0"))


def test_normalization_tables_and_unique_constraints() -> None:
    engine = create_db_engine(Settings().database_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "service_catalog",
        "clinics",
        "service_offers",
        "price_history",
        "unmatched_services",
    }.issubset(tables)

    session_factory = create_session_factory(engine)
    now = datetime.now(UTC)
    tag = uuid.uuid4().hex[:8]
    run_id = uuid.uuid4()
    raw_id = uuid.uuid4()
    service_id = uuid.uuid4()
    clinic_id = uuid.uuid4()

    try:
        with session_factory() as session:
            session.add(
                ScrapeRun(
                    id=run_id,
                    source_id=f"norm_test_{tag}",
                    triggered_by=TriggerSource.MANUAL,
                    status=ScrapeStatus.SUCCESS,
                    started_at=now,
                )
            )
            session.flush()
            session.add(
                RawServiceRecord(
                    id=raw_id,
                    source_id=f"norm_test_{tag}",
                    source_url="https://example.kz/p",
                    record_fingerprint=f"fp_{tag}",
                    clinic_name_raw="Клиника Тест",
                    city_raw="Алматы",
                    service_name_raw="ОАК",
                    price_raw=Decimal("3000.00"),
                    currency_raw="KZT",
                    raw_payload={},
                    first_seen_at=now,
                    last_seen_at=now,
                    parsed_at=now,
                    last_run_id=run_id,
                )
            )
            session.add(
                ServiceCatalog(
                    id=service_id,
                    code=f"lab_oak_{tag}",
                    canonical_name=f"Общий анализ крови {tag}",
                    category=ServiceCategory.LAB,
                    synonyms=["ОАК", "CBC"],
                )
            )
            session.add(
                Clinic(
                    id=clinic_id,
                    source_id=f"norm_test_{tag}",
                    clinic_key=f"ck_{tag}",
                    clinic_name="Клиника Тест",
                    city="Алматы",
                    has_online_booking=True,
                )
            )
            session.flush()

            offer = ServiceOffer(
                clinic_id=clinic_id,
                service_id=service_id,
                raw_record_id=raw_id,
                source_id=f"norm_test_{tag}",
                source_url="https://example.kz/p",
                service_name_raw="ОАК",
                service_name_norm=f"Общий анализ крови {tag}",
                category=ServiceCategory.LAB,
                price_kzt=Decimal("3000.00"),
                original_price=Decimal("3000.00"),
                currency=CurrencyCode.KZT,
                duration_days=1,
                match_method=MatchMethod.SYNONYM,
                match_score=100.0,
                parsed_at=now,
                is_active=True,
            )
            session.add(offer)
            session.flush()

            session.add(
                PriceHistory(
                    clinic_id=clinic_id,
                    service_id=service_id,
                    offer_id=offer.id,
                    price_kzt=Decimal("3000.00"),
                    recorded_at=now,
                )
            )
            session.add(
                UnmatchedService(
                    raw_record_id=raw_id,
                    source_id=f"norm_test_{tag}",
                    clinic_name_raw="Клиника Тест",
                    city_raw="Алматы",
                    service_name_raw="Неизвестная услуга",
                    price_kzt=Decimal("3000.00"),
                    status=UnmatchedStatus.PENDING,
                    created_at=now,
                )
            )
            session.commit()

        # Duplicate (clinic_id, service_id) in service_offers must raise IntegrityError
        with session_factory() as session:
            session.add(
                ServiceOffer(
                    clinic_id=clinic_id,
                    service_id=service_id,
                    raw_record_id=raw_id,
                    source_id=f"norm_test_{tag}",
                    source_url="https://example.kz/p",
                    service_name_raw="ОАК 2",
                    service_name_norm=f"Общий анализ крови {tag}",
                    category=ServiceCategory.LAB,
                    price_kzt=Decimal("3100.00"),
                    original_price=Decimal("3100.00"),
                    currency=CurrencyCode.KZT,
                    match_method=MatchMethod.EXACT,
                    match_score=100.0,
                    parsed_at=now,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        # Duplicate raw_record_id in unmatched_services must raise IntegrityError
        with session_factory() as session:
            session.add(
                UnmatchedService(
                    raw_record_id=raw_id,
                    source_id=f"norm_test_{tag}",
                    clinic_name_raw="Клиника Тест",
                    city_raw="Алматы",
                    service_name_raw="Дубль",
                    price_kzt=Decimal("3000.00"),
                    status=UnmatchedStatus.PENDING,
                    created_at=now,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        with session_factory() as session:
            session.execute(delete(PriceHistory).where(PriceHistory.clinic_id == clinic_id))
            session.execute(
                delete(UnmatchedService).where(UnmatchedService.raw_record_id == raw_id)
            )
            session.execute(delete(ServiceOffer).where(ServiceOffer.clinic_id == clinic_id))
            session.execute(delete(Clinic).where(Clinic.id == clinic_id))
            session.execute(delete(ServiceCatalog).where(ServiceCatalog.id == service_id))
            session.execute(delete(RawServiceRecord).where(RawServiceRecord.id == raw_id))
            session.execute(delete(ScrapeRun).where(ScrapeRun.id == run_id))
            session.commit()
        engine.dispose()
