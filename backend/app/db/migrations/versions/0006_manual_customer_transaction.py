"""Persist customer-entered transaction details for portal complaints.

Revision ID: 0006
Revises: 0005
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("disputes", sa.Column("customer_merchant", sa.String(160), nullable=True))
    op.add_column("disputes", sa.Column("customer_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column("disputes", sa.Column("customer_txn_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("disputes", sa.Column("customer_card_last4", sa.String(4), nullable=True))


def downgrade() -> None:
    op.drop_column("disputes", "customer_card_last4")
    op.drop_column("disputes", "customer_txn_date")
    op.drop_column("disputes", "customer_amount")
    op.drop_column("disputes", "customer_merchant")