"""Create ingestion raw-layer tables.

Revision ID: 0001_ingestion_raw_layer
Revises:
Create Date: 2026-11-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_ingestion_raw_layer"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

trigger_source_enum = postgresql.ENUM("manual", "cron", name="trigger_source_enum", create_type=False)
scrape_status_enum = postgresql.ENUM(
    "running", "success", "partial", "failed", name="scrape_status_enum", create_type=False
)


def upgrade() -> None:
    trigger_source_enum.create(op.get_bind(), checkfirst=True)
    scrape_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "scrape_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("triggered_by", trigger_source_enum, nullable=False),
        sa.Column("status", scrape_status_enum, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_scrape_runs_source_id", "scrape_runs", ["source_id"])

    op.create_table(
        "raw_service_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("record_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("clinic_name_raw", sa.Text(), nullable=False),
        sa.Column("city_raw", sa.String(length=128), nullable=False),
        sa.Column("address_raw", sa.Text(), nullable=True),
        sa.Column("phone_raw", sa.String(length=128), nullable=True),
        sa.Column("working_hours_raw", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("clinic_rating_raw", sa.Float(), nullable=True),
        sa.Column("has_online_booking", sa.Boolean(), nullable=True),
        sa.Column("service_name_raw", sa.Text(), nullable=False),
        sa.Column("category_hint", sa.String(length=128), nullable=True),
        sa.Column("price_raw", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency_raw", sa.String(length=8), nullable=False, server_default="KZT"),
        sa.Column("duration_days_raw", sa.Integer(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scrape_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.UniqueConstraint("source_id", "record_fingerprint", name="uq_raw_source_fingerprint"),
    )
    op.create_index("ix_raw_service_records_source_id", "raw_service_records", ["source_id"])
    op.create_index(
        "ix_raw_service_records_record_fingerprint", "raw_service_records", ["record_fingerprint"]
    )
    op.create_index("ix_raw_service_records_last_seen_at", "raw_service_records", ["last_seen_at"])
    op.create_index("ix_raw_service_records_parsed_at", "raw_service_records", ["parsed_at"])
    op.create_index(
        "ix_raw_service_records_source_last_seen",
        "raw_service_records",
        ["source_id", "last_seen_at"],
    )

    op.create_table(
        "scrape_errors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scrape_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("error_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_scrape_errors_run_id", "scrape_errors", ["run_id"])
    op.create_index("ix_scrape_errors_source_id", "scrape_errors", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_scrape_errors_source_id", table_name="scrape_errors")
    op.drop_index("ix_scrape_errors_run_id", table_name="scrape_errors")
    op.drop_table("scrape_errors")

    op.drop_index("ix_raw_service_records_source_last_seen", table_name="raw_service_records")
    op.drop_index("ix_raw_service_records_parsed_at", table_name="raw_service_records")
    op.drop_index("ix_raw_service_records_last_seen_at", table_name="raw_service_records")
    op.drop_index("ix_raw_service_records_record_fingerprint", table_name="raw_service_records")
    op.drop_index("ix_raw_service_records_source_id", table_name="raw_service_records")
    op.drop_table("raw_service_records")

    op.drop_index("ix_scrape_runs_source_id", table_name="scrape_runs")
    op.drop_table("scrape_runs")

    scrape_status_enum.drop(op.get_bind(), checkfirst=True)
    trigger_source_enum.drop(op.get_bind(), checkfirst=True)
