"""Add email verification state to customer accounts.

Revision ID: 0005
Revises: 0004
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "customer_accounts",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("customer_accounts", sa.Column("email_verification_code_hash", sa.String(64), nullable=True))
    op.add_column("customer_accounts", sa.Column("email_verification_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "customer_accounts",
        sa.Column("email_verification_attempts", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("customer_accounts", "email_verification_attempts")
    op.drop_column("customer_accounts", "email_verification_expires_at")
    op.drop_column("customer_accounts", "email_verification_code_hash")
    op.drop_column("customer_accounts", "email_verified")
