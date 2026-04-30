"""create schema health checks table"""

import sqlalchemy as sa
from alembic import op

revision = "202604300001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schema_health_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("component", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("details", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("schema_health_checks")

