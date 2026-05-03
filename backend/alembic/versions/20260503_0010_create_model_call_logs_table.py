"""create model call logs table"""

import sqlalchemy as sa
from alembic import op

revision = "202605030010"
down_revision = "202605030009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_call_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("call_site", sa.String(length=120), nullable=False),
        sa.Column("primary_model", sa.String(length=120), nullable=False),
        sa.Column("fallback_model", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("error_type", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_length", sa.Integer(), nullable=False),
        sa.Column("raw_prompt", sa.Text(), nullable=True),
        sa.Column("response_excerpt", sa.Text(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_model_call_logs_call_site", "model_call_logs", ["call_site"])
    op.create_index("ix_model_call_logs_status", "model_call_logs", ["status"])
    op.create_index("ix_model_call_logs_prompt_hash", "model_call_logs", ["prompt_hash"])


def downgrade() -> None:
    op.drop_index("ix_model_call_logs_prompt_hash", table_name="model_call_logs")
    op.drop_index("ix_model_call_logs_status", table_name="model_call_logs")
    op.drop_index("ix_model_call_logs_call_site", table_name="model_call_logs")
    op.drop_table("model_call_logs")
