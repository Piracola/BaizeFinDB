"""create push logs table"""

import sqlalchemy as sa
from alembic import op

revision = "202605030007"
down_revision = "202605030006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("target_ref", sa.String(length=120), nullable=False),
        sa.Column("source_kind", sa.String(length=80), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("included_signal_ids", sa.JSON(), nullable=False),
        sa.Column("blocked_signal_ids", sa.JSON(), nullable=False),
        sa.Column("needs_human_review_signal_ids", sa.JSON(), nullable=False),
        sa.Column("delivery_details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_push_logs_user_id", "push_logs", ["user_id"])
    op.create_index("ix_push_logs_channel", "push_logs", ["channel"])
    op.create_index("ix_push_logs_target_ref", "push_logs", ["target_ref"])
    op.create_index("ix_push_logs_source_kind", "push_logs", ["source_kind"])
    op.create_index("ix_push_logs_source_id", "push_logs", ["source_id"])
    op.create_index("ix_push_logs_status", "push_logs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_push_logs_status", table_name="push_logs")
    op.drop_index("ix_push_logs_source_id", table_name="push_logs")
    op.drop_index("ix_push_logs_source_kind", table_name="push_logs")
    op.drop_index("ix_push_logs_target_ref", table_name="push_logs")
    op.drop_index("ix_push_logs_channel", table_name="push_logs")
    op.drop_index("ix_push_logs_user_id", table_name="push_logs")
    op.drop_table("push_logs")
