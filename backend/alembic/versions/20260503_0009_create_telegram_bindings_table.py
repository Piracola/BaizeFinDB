"""create telegram bindings table"""

import sqlalchemy as sa
from alembic import op

revision = "202605030009"
down_revision = "202605030008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_bindings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("is_allowed", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("chat_id", name="uq_telegram_bindings_chat_id"),
    )
    op.create_index("ix_telegram_bindings_user_id", "telegram_bindings", ["user_id"])
    op.create_index("ix_telegram_bindings_chat_id", "telegram_bindings", ["chat_id"])
    op.create_index("ix_telegram_bindings_is_allowed", "telegram_bindings", ["is_allowed"])


def downgrade() -> None:
    op.drop_index("ix_telegram_bindings_is_allowed", table_name="telegram_bindings")
    op.drop_index("ix_telegram_bindings_chat_id", table_name="telegram_bindings")
    op.drop_index("ix_telegram_bindings_user_id", table_name="telegram_bindings")
    op.drop_table("telegram_bindings")
