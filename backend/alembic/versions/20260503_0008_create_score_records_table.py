"""create score records table"""

import sqlalchemy as sa
from alembic import op

revision = "202605030008"
down_revision = "202605030007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "score_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("signal_id", sa.Integer(), sa.ForeignKey("radar_signals.id"), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("score_status", sa.String(length=40), nullable=False),
        sa.Column("composite_score", sa.Float(), nullable=False),
        sa.Column("components", sa.JSON(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "signal_id",
            "window_days",
            name="uq_score_records_signal_window",
        ),
    )
    op.create_index("ix_score_records_signal_id", "score_records", ["signal_id"])
    op.create_index("ix_score_records_window_days", "score_records", ["window_days"])
    op.create_index("ix_score_records_score_status", "score_records", ["score_status"])


def downgrade() -> None:
    op.drop_index("ix_score_records_score_status", table_name="score_records")
    op.drop_index("ix_score_records_window_days", table_name="score_records")
    op.drop_index("ix_score_records_signal_id", table_name="score_records")
    op.drop_table("score_records")
