"""add label to user_auctions

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-16

"""
import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_auctions", sa.Column("label", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("user_auctions", "label")
