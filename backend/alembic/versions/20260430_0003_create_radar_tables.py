"""create radar core tables"""

import sqlalchemy as sa
from alembic import op

revision = "202604300003"
down_revision = "202604300002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "radar_scan_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_snapshot_ids", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_radar_scan_batches_status", "radar_scan_batches", ["status"])

    op.create_table(
        "radar_signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey("radar_scan_batches.id"),
            nullable=False,
        ),
        sa.Column("signal_key", sa.String(length=200), nullable=False),
        sa.Column("subject_type", sa.String(length=80), nullable=False),
        sa.Column("subject_code", sa.String(length=80), nullable=True),
        sa.Column("subject_name", sa.String(length=160), nullable=False),
        sa.Column("priority", sa.String(length=10), nullable=False),
        sa.Column("lifecycle_stage", sa.String(length=40), nullable=False),
        sa.Column("review_status", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_radar_signals_batch_id", "radar_signals", ["batch_id"])
    op.create_index("ix_radar_signals_signal_key", "radar_signals", ["signal_key"])
    op.create_index("ix_radar_signals_subject_type", "radar_signals", ["subject_type"])
    op.create_index("ix_radar_signals_subject_code", "radar_signals", ["subject_code"])
    op.create_index("ix_radar_signals_subject_name", "radar_signals", ["subject_name"])
    op.create_index("ix_radar_signals_priority", "radar_signals", ["priority"])
    op.create_index("ix_radar_signals_lifecycle_stage", "radar_signals", ["lifecycle_stage"])
    op.create_index("ix_radar_signals_review_status", "radar_signals", ["review_status"])

    op.create_table(
        "signal_evidences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("signal_id", sa.Integer(), sa.ForeignKey("radar_signals.id"), nullable=False),
        sa.Column("evidence_type", sa.String(length=80), nullable=False),
        sa.Column("source_name", sa.String(length=80), nullable=False),
        sa.Column("source_ref", sa.String(length=200), nullable=True),
        sa.Column("source_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_excerpt", sa.Text(), nullable=False),
        sa.Column("normalized_summary", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("freshness", sa.String(length=40), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("public_share_policy", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_signal_evidences_signal_id", "signal_evidences", ["signal_id"])
    op.create_index("ix_signal_evidences_evidence_type", "signal_evidences", ["evidence_type"])


def downgrade() -> None:
    op.drop_index("ix_signal_evidences_evidence_type", table_name="signal_evidences")
    op.drop_index("ix_signal_evidences_signal_id", table_name="signal_evidences")
    op.drop_table("signal_evidences")

    op.drop_index("ix_radar_signals_review_status", table_name="radar_signals")
    op.drop_index("ix_radar_signals_lifecycle_stage", table_name="radar_signals")
    op.drop_index("ix_radar_signals_priority", table_name="radar_signals")
    op.drop_index("ix_radar_signals_subject_name", table_name="radar_signals")
    op.drop_index("ix_radar_signals_subject_code", table_name="radar_signals")
    op.drop_index("ix_radar_signals_subject_type", table_name="radar_signals")
    op.drop_index("ix_radar_signals_signal_key", table_name="radar_signals")
    op.drop_index("ix_radar_signals_batch_id", table_name="radar_signals")
    op.drop_table("radar_signals")

    op.drop_index("ix_radar_scan_batches_status", table_name="radar_scan_batches")
    op.drop_table("radar_scan_batches")
