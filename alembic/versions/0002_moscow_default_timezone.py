"""default timezone to Europe/Moscow

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-14

"""
import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE users SET timezone = 'Europe/Moscow' WHERE timezone = 'Europe/London'")
    op.alter_column("users", "timezone", server_default=sa.text("'Europe/Moscow'"))


def downgrade() -> None:
    op.alter_column("users", "timezone", server_default=sa.text("'Europe/London'"))
