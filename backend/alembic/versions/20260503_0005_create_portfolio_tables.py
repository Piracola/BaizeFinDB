"""create portfolio and watchlist tables"""

import sqlalchemy as sa
from alembic import op

revision = "202605030005"
down_revision = "202604300004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_key", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.UniqueConstraint("user_key"),
    )
    op.create_index("ix_users_user_key", "users", ["user_key"])

    op.create_table(
        "portfolio_holdings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("instrument_code", sa.String(length=80), nullable=False),
        sa.Column("instrument_name", sa.String(length=160), nullable=False),
        sa.Column("market", sa.String(length=40), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("cost_price", sa.Float(), nullable=True),
        sa.Column("position_ratio", sa.Float(), nullable=True),
        sa.Column("alert_enabled", sa.Boolean(), nullable=False),
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
        sa.UniqueConstraint(
            "user_id",
            "market",
            "instrument_code",
            name="uq_portfolio_holdings_user_market_code",
        ),
    )
    op.create_index("ix_portfolio_holdings_user_id", "portfolio_holdings", ["user_id"])
    op.create_index(
        "ix_portfolio_holdings_instrument_code",
        "portfolio_holdings",
        ["instrument_code"],
    )
    op.create_index(
        "ix_portfolio_holdings_instrument_name",
        "portfolio_holdings",
        ["instrument_name"],
    )
    op.create_index("ix_portfolio_holdings_market", "portfolio_holdings", ["market"])

    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("instrument_code", sa.String(length=80), nullable=False),
        sa.Column("instrument_name", sa.String(length=160), nullable=False),
        sa.Column("market", sa.String(length=40), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("alert_enabled", sa.Boolean(), nullable=False),
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
        sa.UniqueConstraint(
            "user_id",
            "market",
            "instrument_code",
            name="uq_watchlist_items_user_market_code",
        ),
    )
    op.create_index("ix_watchlist_items_user_id", "watchlist_items", ["user_id"])
    op.create_index(
        "ix_watchlist_items_instrument_code",
        "watchlist_items",
        ["instrument_code"],
    )
    op.create_index(
        "ix_watchlist_items_instrument_name",
        "watchlist_items",
        ["instrument_name"],
    )
    op.create_index("ix_watchlist_items_market", "watchlist_items", ["market"])


def downgrade() -> None:
    op.drop_index("ix_watchlist_items_market", table_name="watchlist_items")
    op.drop_index("ix_watchlist_items_instrument_name", table_name="watchlist_items")
    op.drop_index("ix_watchlist_items_instrument_code", table_name="watchlist_items")
    op.drop_index("ix_watchlist_items_user_id", table_name="watchlist_items")
    op.drop_table("watchlist_items")

    op.drop_index("ix_portfolio_holdings_market", table_name="portfolio_holdings")
    op.drop_index("ix_portfolio_holdings_instrument_name", table_name="portfolio_holdings")
    op.drop_index("ix_portfolio_holdings_instrument_code", table_name="portfolio_holdings")
    op.drop_index("ix_portfolio_holdings_user_id", table_name="portfolio_holdings")
    op.drop_table("portfolio_holdings")

    op.drop_index("ix_users_user_key", table_name="users")
    op.drop_table("users")
