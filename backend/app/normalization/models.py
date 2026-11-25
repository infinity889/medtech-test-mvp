"""SQLAlchemy ORM models for the normalized medical services layer."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

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


class ServiceCategory(StrEnum):
    """Canonical medical service categories matching TZ section 2.2."""

    LAB = "lab"
    DOCTOR = "doctor"
    DIAGNOSTICS = "diagnostics"
    PROCEDURE = "procedure"


class CurrencyCode(StrEnum):
    """Supported input currencies (all converted to KZT in service_offers)."""

    KZT = "KZT"
    USD = "USD"


class MatchMethod(StrEnum):
    """How a raw service string was matched to a canonical ServiceCatalog entry."""

    EXACT = "exact"
    SYNONYM = "synonym"
    FUZZY = "fuzzy"
    MANUAL = "manual"


class UnmatchedStatus(StrEnum):
    """Lifecycle status of an unmatched service queue item."""

    PENDING = "pending"
    MAPPED = "mapped"
    IGNORED = "ignored"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ServiceCatalog(Base):
    """Canonical medical service dictionary (>= 50 normalized entries)."""

    __tablename__ = "service_catalog"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    canonical_name: Mapped[str] = mapped_column(
        String(256), unique=True, index=True, nullable=False
    )
    category: Mapped[ServiceCategory] = mapped_column(
        SAEnum(
            ServiceCategory,
            name="service_category_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        index=True,
        nullable=False,
    )
    synonyms: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class Clinic(Base):
    """Deduplicated canonical clinic / laboratory branch entity."""

    __tablename__ = "clinics"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    clinic_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    clinic_name: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(128), nullable=True)
    working_hours: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    has_online_booking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    offers: Mapped[list["ServiceOffer"]] = relationship(back_populates="clinic")


class ServiceOffer(Base):
    """Normalized active/historical offer for one (clinic, canonical service) pair."""

    __tablename__ = "service_offers"
    __table_args__ = (
        UniqueConstraint("clinic_id", "service_id", name="uq_service_offers_clinic_service"),
        Index("ix_service_offers_service_active_price", "service_id", "is_active", "price_kzt"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clinics.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_catalog.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    raw_record_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("raw_service_records.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    service_name_raw: Mapped[str] = mapped_column(Text, nullable=False)
    service_name_norm: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[ServiceCategory] = mapped_column(
        SAEnum(
            ServiceCategory,
            name="service_category_enum",
            create_type=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        index=True,
        nullable=False,
    )
    price_kzt: Mapped[Decimal] = mapped_column(Numeric(12, 2), index=True, nullable=False)
    original_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[CurrencyCode] = mapped_column(
        SAEnum(
            CurrencyCode,
            name="currency_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=CurrencyCode.KZT,
    )
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_method: Mapped[MatchMethod] = mapped_column(
        SAEnum(
            MatchMethod,
            name="match_method_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    parsed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, index=True, nullable=False, default=True)

    clinic: Mapped[Clinic] = relationship(back_populates="offers")
    service: Mapped[ServiceCatalog] = relationship()


class PriceHistory(Base):
    """Append-only price snapshots recorded on initial observation and price changes."""

    __tablename__ = "price_history"
    __table_args__ = (
        Index("ix_price_history_service_clinic_recorded", "service_id", "clinic_id", "recorded_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clinics.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_catalog.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    offer_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_offers.id", ondelete="SET NULL"),
        nullable=True,
    )
    price_kzt: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False, default=_utcnow
    )


class UnmatchedService(Base):
    """Queue of raw service records awaiting manual mapping or ignoring."""

    __tablename__ = "unmatched_services"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    raw_record_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("raw_service_records.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    clinic_name_raw: Mapped[str] = mapped_column(Text, nullable=False)
    city_raw: Mapped[str] = mapped_column(String(128), nullable=False)
    service_name_raw: Mapped[str] = mapped_column(Text, nullable=False)
    category_hint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    price_kzt: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    suggested_service_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_catalog.id", ondelete="SET NULL"),
        nullable=True,
    )
    suggested_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[UnmatchedStatus] = mapped_column(
        SAEnum(
            UnmatchedStatus,
            name="unmatched_status_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        index=True,
        nullable=False,
        default=UnmatchedStatus.PENDING,
    )
    resolved_service_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_catalog.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
