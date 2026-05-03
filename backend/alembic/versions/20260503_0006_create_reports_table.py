"""create reports table"""

import sqlalchemy as sa
from alembic import op

revision = "202605030006"
down_revision = "202605030005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signal_id", sa.Integer(), sa.ForeignKey("radar_signals.id"), nullable=True),
        sa.Column("report_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("suggestion_label", sa.String(length=40), nullable=False),
        sa.Column("review_status", sa.String(length=40), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
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
    )
    op.create_index("ix_reports_user_id", "reports", ["user_id"])
    op.create_index("ix_reports_signal_id", "reports", ["signal_id"])
    op.create_index("ix_reports_report_type", "reports", ["report_type"])
    op.create_index("ix_reports_status", "reports", ["status"])
    op.create_index("ix_reports_review_status", "reports", ["review_status"])


def downgrade() -> None:
    op.drop_index("ix_reports_review_status", table_name="reports")
    op.drop_index("ix_reports_status", table_name="reports")
    op.drop_index("ix_reports_report_type", table_name="reports")
    op.drop_index("ix_reports_signal_id", table_name="reports")
    op.drop_index("ix_reports_user_id", table_name="reports")
    op.drop_table("reports")
