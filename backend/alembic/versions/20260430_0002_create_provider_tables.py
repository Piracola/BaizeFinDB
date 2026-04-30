"""create provider collection tables"""

import sqlalchemy as sa
from alembic import op

revision = "202604300002"
down_revision = "202604300001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("endpoint", sa.String(length=120), nullable=False),
        sa.Column("market", sa.String(length=40), nullable=False),
        sa.Column("snapshot_type", sa.String(length=80), nullable=False),
        sa.Column("source_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("raw_summary", sa.JSON(), nullable=False),
        sa.Column("normalized_rows", sa.JSON(), nullable=False),
        sa.Column("normalization_version", sa.String(length=80), nullable=False),
    )
    op.create_index("ix_market_snapshots_provider_name", "market_snapshots", ["provider_name"])
    op.create_index("ix_market_snapshots_endpoint", "market_snapshots", ["endpoint"])
    op.create_index("ix_market_snapshots_market", "market_snapshots", ["market"])
    op.create_index("ix_market_snapshots_snapshot_type", "market_snapshots", ["snapshot_type"])

    op.create_table(
        "provider_fetch_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("endpoint", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("fetch_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetch_finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("freshness", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("missing_fields", sa.JSON(), nullable=False),
        sa.Column("raw_snapshot_id", sa.Integer(), sa.ForeignKey("market_snapshots.id")),
        sa.Column("normalization_version", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_provider_fetch_logs_provider_name",
        "provider_fetch_logs",
        ["provider_name"],
    )
    op.create_index("ix_provider_fetch_logs_endpoint", "provider_fetch_logs", ["endpoint"])
    op.create_index("ix_provider_fetch_logs_status", "provider_fetch_logs", ["status"])

    op.create_table(
        "data_quality_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("endpoint", sa.String(length=120), nullable=False),
        sa.Column("check_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("missing_fields", sa.JSON(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("fetch_log_id", sa.Integer(), sa.ForeignKey("provider_fetch_logs.id")),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("market_snapshots.id")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_data_quality_checks_provider_name",
        "data_quality_checks",
        ["provider_name"],
    )
    op.create_index("ix_data_quality_checks_endpoint", "data_quality_checks", ["endpoint"])
    op.create_index("ix_data_quality_checks_status", "data_quality_checks", ["status"])


def downgrade() -> None:
    op.drop_index("ix_data_quality_checks_status", table_name="data_quality_checks")
    op.drop_index("ix_data_quality_checks_endpoint", table_name="data_quality_checks")
    op.drop_index("ix_data_quality_checks_provider_name", table_name="data_quality_checks")
    op.drop_table("data_quality_checks")

    op.drop_index("ix_provider_fetch_logs_status", table_name="provider_fetch_logs")
    op.drop_index("ix_provider_fetch_logs_endpoint", table_name="provider_fetch_logs")
    op.drop_index("ix_provider_fetch_logs_provider_name", table_name="provider_fetch_logs")
    op.drop_table("provider_fetch_logs")

    op.drop_index("ix_market_snapshots_snapshot_type", table_name="market_snapshots")
    op.drop_index("ix_market_snapshots_market", table_name="market_snapshots")
    op.drop_index("ix_market_snapshots_endpoint", table_name="market_snapshots")
    op.drop_index("ix_market_snapshots_provider_name", table_name="market_snapshots")
    op.drop_table("market_snapshots")
