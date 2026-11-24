"""SQLAlchemy ORM models for the ingestion raw layer."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class TriggerSource(StrEnum):
    """How a scrape run was initiated."""

    MANUAL = "manual"
    CRON = "cron"


class ScrapeStatus(StrEnum):
    """Lifecycle status of a scrape run."""

    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ScrapeRun(Base):
    """Execution audit record for one source adapter run."""

    __tablename__ = "scrape_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    triggered_by: Mapped[TriggerSource] = mapped_column(
        SAEnum(
            TriggerSource,
            name="trigger_source_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[ScrapeStatus] = mapped_column(
        SAEnum(
            ScrapeStatus,
            name="scrape_status_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ScrapeStatus.RUNNING,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    errors: Mapped[list["ScrapeError"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class RawServiceRecord(Base):
    """Raw scraped service offer stored separately from normalized tables (retention >= 90d)."""

    __tablename__ = "raw_service_records"
    __table_args__ = (
        UniqueConstraint("source_id", "record_fingerprint", name="uq_raw_source_fingerprint"),
        Index("ix_raw_service_records_source_last_seen", "source_id", "last_seen_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    record_fingerprint: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    clinic_name_raw: Mapped[str] = mapped_column(Text, nullable=False)
    city_raw: Mapped[str] = mapped_column(String(128), nullable=False)
    address_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    working_hours_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    clinic_rating_raw: Mapped[float | None] = mapped_column(Float, nullable=True)
    has_online_booking: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    service_name_raw: Mapped[str] = mapped_column(Text, nullable=False)
    category_hint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    price_raw: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency_raw: Mapped[str] = mapped_column(String(8), nullable=False, default="KZT")
    duration_days_raw: Mapped[int | None] = mapped_column(Integer, nullable=True)

    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False, default=_utcnow
    )
    parsed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False, default=_utcnow
    )
    last_run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("scrape_runs.id", ondelete="RESTRICT"), nullable=False
    )


class ScrapeError(Base):
    """Structured error log entry for ingestion failures."""

    __tablename__ = "scrape_errors"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("scrape_runs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    run: Mapped[ScrapeRun] = relationship(back_populates="errors")
