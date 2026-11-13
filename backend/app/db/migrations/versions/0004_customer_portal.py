"""customer portal: customer_accounts table + two nullable dispute columns

Additive and backward compatible: existing rows are untouched (new columns are NULL).

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, unique=True),
        sa.Column("email", sa.String(160), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_customer_accounts_email", "customer_accounts", ["email"], unique=True)
    op.add_column("disputes", sa.Column("customer_category", sa.String(40), nullable=True))
    op.add_column(
        "disputes",
        sa.Column("customer_txn_id", sa.Integer(), sa.ForeignKey("transactions.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("disputes", "customer_txn_id")
    op.drop_column("disputes", "customer_category")
    op.drop_index("ix_customer_accounts_email", table_name="customer_accounts")
    op.drop_table("customer_accounts")
