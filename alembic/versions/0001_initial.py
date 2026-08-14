"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Europe/London"),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="ru"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "auctions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("current_price", sa.Integer(), nullable=True),
        sa.Column("bid_count", sa.Integer(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("buy_now_price", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("is_store", sa.Boolean(), nullable=True),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_winner", sa.Boolean(), nullable=True),
        sa.Column("monitoring_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("consecutive_errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_auctions_external_id", "auctions", ["external_id"], unique=True)
    op.create_index("ix_auctions_monitoring_next_poll", "auctions", ["monitoring_active", "next_poll_at"])
    op.create_index("ix_auctions_closed", "auctions", ["is_closed"])

    op.create_table(
        "user_auctions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("auction_id", sa.BigInteger(), sa.ForeignKey("auctions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("notifications_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "auction_id", name="uq_user_auction"),
    )
    op.create_index("ix_user_auctions_user_id", "user_auctions", ["user_id"])
    op.create_index("ix_user_auctions_auction_id", "user_auctions", ["auction_id"])

    op.create_table(
        "auction_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("auction_id", sa.BigInteger(), sa.ForeignKey("auctions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_price", sa.Integer(), nullable=True),
        sa.Column("bid_count", sa.Integer(), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("buy_now_price", sa.Integer(), nullable=True),
        sa.Column("is_closed", sa.Boolean(), nullable=True),
        sa.Column("has_winner", sa.Boolean(), nullable=True),
        sa.Column("new_bid", sa.Boolean(), nullable=True),
        sa.Column("raw_data", JSONB(), nullable=True),
    )
    op.create_index("ix_snapshots_auction_observed", "auction_snapshots", ["auction_id", "observed_at"])

    op.create_table(
        "sent_notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_auction_id",
            sa.BigInteger(),
            sa.ForeignKey("user_auctions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("dedup_key", sa.String(length=128), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_auction_id", "kind", "dedup_key", name="uq_sent_notification"),
    )
    op.create_index("ix_sent_notifications_status", "sent_notifications", ["status"])


def downgrade() -> None:
    op.drop_table("sent_notifications")
    op.drop_table("auction_snapshots")
    op.drop_table("user_auctions")
    op.drop_table("auctions")
    op.drop_table("users")
