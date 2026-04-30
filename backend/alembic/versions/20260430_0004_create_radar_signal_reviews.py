"""create radar signal review table"""

import sqlalchemy as sa
from alembic import op

revision = "202604300004"
down_revision = "202604300003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "radar_signal_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("signal_id", sa.Integer(), sa.ForeignKey("radar_signals.id"), nullable=False),
        sa.Column("review_status", sa.String(length=40), nullable=False),
        sa.Column("reviewer", sa.String(length=80), nullable=False),
        sa.Column("rule_version", sa.String(length=80), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_radar_signal_reviews_signal_id", "radar_signal_reviews", ["signal_id"])
    op.create_index(
        "ix_radar_signal_reviews_review_status",
        "radar_signal_reviews",
        ["review_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_radar_signal_reviews_review_status", table_name="radar_signal_reviews")
    op.drop_index("ix_radar_signal_reviews_signal_id", table_name="radar_signal_reviews")
    op.drop_table("radar_signal_reviews")
