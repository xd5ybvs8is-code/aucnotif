"""drop users.timezone

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-16

"""
import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("users", "timezone")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'Europe/Moscow'"),
        ),
    )
