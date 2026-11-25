"""Create normalization layer tables.

Revision ID: 0002_normalization_layer
Revises: 0001_ingestion_raw_layer
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_normalization_layer"
down_revision: str | None = "0001_ingestion_raw_layer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

service_category_enum = postgresql.ENUM(
    "lab", "doctor", "diagnostics", "procedure", name="service_category_enum", create_type=False
)
currency_enum = postgresql.ENUM("KZT", "USD", name="currency_enum", create_type=False)
match_method_enum = postgresql.ENUM(
    "exact", "synonym", "fuzzy", "manual", name="match_method_enum", create_type=False
)
unmatched_status_enum = postgresql.ENUM(
    "pending", "mapped", "ignored", name="unmatched_status_enum", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    service_category_enum.create(bind, checkfirst=True)
    currency_enum.create(bind, checkfirst=True)
    match_method_enum.create(bind, checkfirst=True)
    unmatched_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "service_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("canonical_name", sa.String(length=256), nullable=False),
        sa.Column("category", service_category_enum, nullable=False),
        sa.Column("synonyms", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_service_catalog_code"),
        sa.UniqueConstraint("canonical_name", name="uq_service_catalog_canonical_name"),
    )
    op.create_index("ix_service_catalog_code", "service_catalog", ["code"])
    op.create_index("ix_service_catalog_canonical_name", "service_catalog", ["canonical_name"])
    op.create_index("ix_service_catalog_category", "service_catalog", ["category"])

    op.create_table(
        "clinics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("clinic_key", sa.String(length=64), nullable=False),
        sa.Column("clinic_name", sa.Text(), nullable=False),
        sa.Column("city", sa.String(length=128), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(length=128), nullable=True),
        sa.Column("working_hours", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column(
            "has_online_booking", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("website_url", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("clinic_key", name="uq_clinics_clinic_key"),
    )
    op.create_index("ix_clinics_source_id", "clinics", ["source_id"])
    op.create_index("ix_clinics_clinic_key", "clinics", ["clinic_key"])
    op.create_index("ix_clinics_city", "clinics", ["city"])

    op.create_table(
        "service_offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "clinic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clinics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "service_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("service_catalog.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "raw_record_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_service_records.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("service_name_raw", sa.Text(), nullable=False),
        sa.Column("service_name_norm", sa.String(length=256), nullable=False),
        sa.Column("category", service_category_enum, nullable=False),
        sa.Column("price_kzt", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("original_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", currency_enum, nullable=False, server_default="KZT"),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("match_method", match_method_enum, nullable=False),
        sa.Column("match_score", sa.Float(), nullable=False),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("clinic_id", "service_id", name="uq_service_offers_clinic_service"),
    )
    op.create_index("ix_service_offers_clinic_id", "service_offers", ["clinic_id"])
    op.create_index("ix_service_offers_service_id", "service_offers", ["service_id"])
    op.create_index("ix_service_offers_raw_record_id", "service_offers", ["raw_record_id"])
    op.create_index("ix_service_offers_source_id", "service_offers", ["source_id"])
    op.create_index("ix_service_offers_category", "service_offers", ["category"])
    op.create_index("ix_service_offers_price_kzt", "service_offers", ["price_kzt"])
    op.create_index("ix_service_offers_parsed_at", "service_offers", ["parsed_at"])
    op.create_index("ix_service_offers_is_active", "service_offers", ["is_active"])
    op.create_index(
        "ix_service_offers_service_active_price",
        "service_offers",
        ["service_id", "is_active", "price_kzt"],
    )

    op.create_table(
        "price_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "clinic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clinics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "service_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("service_catalog.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "offer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("service_offers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("price_kzt", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_price_history_clinic_id", "price_history", ["clinic_id"])
    op.create_index("ix_price_history_service_id", "price_history", ["service_id"])
    op.create_index("ix_price_history_recorded_at", "price_history", ["recorded_at"])
    op.create_index(
        "ix_price_history_service_clinic_recorded",
        "price_history",
        ["service_id", "clinic_id", "recorded_at"],
    )

    op.create_table(
        "unmatched_services",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "raw_record_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_service_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("clinic_name_raw", sa.Text(), nullable=False),
        sa.Column("city_raw", sa.String(length=128), nullable=False),
        sa.Column("service_name_raw", sa.Text(), nullable=False),
        sa.Column("category_hint", sa.String(length=128), nullable=True),
        sa.Column("price_kzt", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "suggested_service_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("service_catalog.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("suggested_score", sa.Float(), nullable=True),
        sa.Column("status", unmatched_status_enum, nullable=False, server_default="pending"),
        sa.Column(
            "resolved_service_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("service_catalog.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("raw_record_id", name="uq_unmatched_services_raw_record_id"),
    )
    op.create_index("ix_unmatched_services_raw_record_id", "unmatched_services", ["raw_record_id"])
    op.create_index("ix_unmatched_services_source_id", "unmatched_services", ["source_id"])
    op.create_index("ix_unmatched_services_status", "unmatched_services", ["status"])


def downgrade() -> None:
    op.drop_index("ix_unmatched_services_status", table_name="unmatched_services")
    op.drop_index("ix_unmatched_services_source_id", table_name="unmatched_services")
    op.drop_index("ix_unmatched_services_raw_record_id", table_name="unmatched_services")
    op.drop_table("unmatched_services")

    op.drop_index("ix_price_history_service_clinic_recorded", table_name="price_history")
    op.drop_index("ix_price_history_recorded_at", table_name="price_history")
    op.drop_index("ix_price_history_service_id", table_name="price_history")
    op.drop_index("ix_price_history_clinic_id", table_name="price_history")
    op.drop_table("price_history")

    op.drop_index("ix_service_offers_service_active_price", table_name="service_offers")
    op.drop_index("ix_service_offers_is_active", table_name="service_offers")
    op.drop_index("ix_service_offers_parsed_at", table_name="service_offers")
    op.drop_index("ix_service_offers_price_kzt", table_name="service_offers")
    op.drop_index("ix_service_offers_category", table_name="service_offers")
    op.drop_index("ix_service_offers_source_id", table_name="service_offers")
    op.drop_index("ix_service_offers_raw_record_id", table_name="service_offers")
    op.drop_index("ix_service_offers_service_id", table_name="service_offers")
    op.drop_index("ix_service_offers_clinic_id", table_name="service_offers")
    op.drop_table("service_offers")

    op.drop_index("ix_clinics_city", table_name="clinics")
    op.drop_index("ix_clinics_clinic_key", table_name="clinics")
    op.drop_index("ix_clinics_source_id", table_name="clinics")
    op.drop_table("clinics")

    op.drop_index("ix_service_catalog_category", table_name="service_catalog")
    op.drop_index("ix_service_catalog_canonical_name", table_name="service_catalog")
    op.drop_index("ix_service_catalog_code", table_name="service_catalog")
    op.drop_table("service_catalog")

    bind = op.get_bind()
    unmatched_status_enum.drop(bind, checkfirst=True)
    match_method_enum.drop(bind, checkfirst=True)
    currency_enum.drop(bind, checkfirst=True)
    service_category_enum.drop(bind, checkfirst=True)
