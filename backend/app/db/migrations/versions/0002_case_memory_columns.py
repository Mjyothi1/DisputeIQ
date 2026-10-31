"""case_embeddings: add reason_code and outcome

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("case_embeddings", sa.Column("reason_code", sa.String(length=40), nullable=True))
    op.add_column("case_embeddings", sa.Column("outcome", sa.String(length=32), nullable=True))
    op.create_index(
        op.f("ix_case_embeddings_reason_code"), "case_embeddings", ["reason_code"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_case_embeddings_reason_code"), table_name="case_embeddings")
    op.drop_column("case_embeddings", "outcome")
    op.drop_column("case_embeddings", "reason_code")
