"""add is_active and unsubscribe_token with backfill

Revision ID: a1b2c3d4e5f6
Revises: 7e701ae4ed98
Create Date: 2026-06-05

"""

from __future__ import annotations

import secrets
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "7e701ae4ed98"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "subscriptions",
        sa.Column("unsubscribe_token", sa.String(length=128), nullable=True),
    )
    op.create_index(
        op.f("ix_subscriptions_unsubscribe_token"),
        "subscriptions",
        ["unsubscribe_token"],
        unique=True,
    )

    conn = op.get_bind()
    metadata = sa.MetaData()
    subscriptions = sa.Table("subscriptions", metadata, autoload_with=conn)
    rows = conn.execute(sa.select(subscriptions.c.id)).fetchall()
    for (row_id,) in rows:
        token = secrets.token_urlsafe(32)
        conn.execute(
            subscriptions.update()
            .where(subscriptions.c.id == row_id)
            .values(is_active=True, unsubscribe_token=token)
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_subscriptions_unsubscribe_token"), table_name="subscriptions")
    op.drop_column("subscriptions", "unsubscribe_token")
    op.drop_column("subscriptions", "is_active")
