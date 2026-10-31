"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-26 10:08:11.466867
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=160), nullable=True),
        sa.Column("segment", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
    )
    op.create_table(
        "merchants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("mcc", sa.String(length=4), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "ECOMMERCE",
                "FOOD_DELIVERY",
                "TRAVEL",
                "SUBSCRIPTION",
                "RETAIL",
                "ATM",
                name="merchantcategory",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("city", sa.String(length=80), nullable=True),
        sa.Column("is_recurring_biller", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_merchants")),
    )
    op.create_index(op.f("ix_merchants_name"), "merchants", ["name"], unique=False)
    op.create_table(
        "cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("masked_pan", sa.String(length=19), nullable=False),
        sa.Column("last4", sa.String(length=4), nullable=False),
        sa.Column(
            "network",
            sa.Enum(
                "VISA", "MASTERCARD", "RUPAY", name="cardnetwork", native_enum=False, length=32
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "BLOCKED", "CLOSED", name="cardstatus", native_enum=False, length=32),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], name=op.f("fk_cards_customer_id_customers")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cards")),
    )
    op.create_index(op.f("ix_cards_customer_id"), "cards", ["customer_id"], unique=False)
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("merchant_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "CANCELLED", name="subscriptionstatus", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["card_id"], ["cards.id"], name=op.f("fk_subscriptions_card_id_cards")
        ),
        sa.ForeignKeyConstraint(
            ["merchant_id"], ["merchants.id"], name=op.f("fk_subscriptions_merchant_id_merchants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriptions")),
    )
    op.create_index(op.f("ix_subscriptions_card_id"), "subscriptions", ["card_id"], unique=False)
    op.create_index(
        op.f("ix_subscriptions_merchant_id"), "subscriptions", ["merchant_id"], unique=False
    )
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("merchant_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("txn_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "channel",
            sa.Enum(
                "POS", "ECOM", "ATM", "RECURRING", name="txnchannel", native_enum=False, length=32
            ),
            nullable=False,
        ),
        sa.Column(
            "auth_method",
            sa.Enum("OTP_3DS", "PIN", "NONE", name="authmethod", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "SETTLED", "REVERSED", "FAILED", name="txnstatus", native_enum=False, length=32
            ),
            nullable=False,
        ),
        sa.Column(
            "refund_status",
            sa.Enum("NONE", "PARTIAL", "FULL", name="refundstatus", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("is_recurring", sa.Boolean(), nullable=False),
        sa.Column("account_debited", sa.Boolean(), nullable=False),
        sa.Column(
            "details",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["card_id"], ["cards.id"], name=op.f("fk_transactions_card_id_cards")
        ),
        sa.ForeignKeyConstraint(
            ["merchant_id"], ["merchants.id"], name=op.f("fk_transactions_merchant_id_merchants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transactions")),
    )
    op.create_index(op.f("ix_transactions_card_id"), "transactions", ["card_id"], unique=False)
    op.create_index(
        op.f("ix_transactions_merchant_id"), "transactions", ["merchant_id"], unique=False
    )
    op.create_index(op.f("ix_transactions_txn_time"), "transactions", ["txn_time"], unique=False)
    op.create_table(
        "disputes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column(
            "channel",
            sa.Enum("FORM", "EMAIL", "CHAT", name="disputechannel", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("masked_text", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "NEW",
                "PROCESSING",
                "AUTO_RESOLVED",
                "NEEDS_HUMAN",
                "APPROVED",
                "REJECTED",
                "OVERRIDDEN",
                name="disputestatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "extracted_fields",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("matched_txn_id", sa.Integer(), nullable=True),
        sa.Column("reason_code", sa.String(length=40), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "ground_truth",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "split",
            sa.Enum("DEV", "TEST", name="datasplit", native_enum=False, length=32),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], name=op.f("fk_disputes_customer_id_customers")
        ),
        sa.ForeignKeyConstraint(
            ["matched_txn_id"],
            ["transactions.id"],
            name=op.f("fk_disputes_matched_txn_id_transactions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_disputes")),
    )
    op.create_index(op.f("ix_disputes_customer_id"), "disputes", ["customer_id"], unique=False)
    op.create_index(op.f("ix_disputes_deadline_at"), "disputes", ["deadline_at"], unique=False)
    op.create_index(op.f("ix_disputes_reason_code"), "disputes", ["reason_code"], unique=False)
    op.create_index(op.f("ix_disputes_split"), "disputes", ["split"], unique=False)
    op.create_index(op.f("ix_disputes_status"), "disputes", ["status"], unique=False)
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dispute_id", sa.Integer(), nullable=False),
        sa.Column("step", sa.String(length=60), nullable=False),
        sa.Column(
            "actor",
            sa.Enum("AGENT", "TOOL", "HUMAN", name="auditactor", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("input_summary", sa.Text(), nullable=True),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("prompt_version", sa.String(length=40), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("cost_inr", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["dispute_id"], ["disputes.id"], name=op.f("fk_audit_events_dispute_id_disputes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        op.f("ix_audit_events_dispute_id"), "audit_events", ["dispute_id"], unique=False
    )
    op.create_index(op.f("ix_audit_events_timestamp"), "audit_events", ["timestamp"], unique=False)
    op.create_table(
        "case_embeddings",
        sa.Column("dispute_id", sa.Integer(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dispute_id"], ["disputes.id"], name=op.f("fk_case_embeddings_dispute_id_disputes")
        ),
        sa.PrimaryKeyConstraint("dispute_id", name=op.f("pk_case_embeddings")),
    )
    op.create_table(
        "decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dispute_id", sa.Integer(), nullable=False),
        sa.Column(
            "recommendation",
            sa.Enum(
                "REFUND",
                "FILE_CHARGEBACK",
                "REJECT",
                "NEED_MORE_INFO",
                name="recommendation",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("friendly_fraud_flag", sa.Boolean(), nullable=False),
        sa.Column("drafted_customer_letter", sa.Text(), nullable=True),
        sa.Column("drafted_chargeback_filing", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("prompt_version", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dispute_id"], ["disputes.id"], name=op.f("fk_decisions_dispute_id_disputes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decisions")),
    )
    op.create_index(op.f("ix_decisions_dispute_id"), "decisions", ["dispute_id"], unique=False)
    op.create_table(
        "evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dispute_id", sa.Integer(), nullable=False),
        sa.Column("check_name", sa.String(length=60), nullable=False),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column(
            "details",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dispute_id"], ["disputes.id"], name=op.f("fk_evidence_dispute_id_disputes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence")),
    )
    op.create_index(op.f("ix_evidence_dispute_id"), "evidence", ["dispute_id"], unique=False)
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dispute_id", sa.Integer(), nullable=False),
        sa.Column("analyst", sa.String(length=120), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                "APPROVE",
                "EDIT",
                "OVERRIDE",
                "REJECT",
                name="reviewaction",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "final_decision",
            sa.Enum(
                "REFUND",
                "FILE_CHARGEBACK",
                "REJECT",
                "NEED_MORE_INFO",
                name="recommendation",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("edited_letter", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dispute_id"], ["disputes.id"], name=op.f("fk_reviews_dispute_id_disputes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reviews")),
    )
    op.create_index(op.f("ix_reviews_dispute_id"), "reviews", ["dispute_id"], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_reviews_dispute_id"), table_name="reviews")
    op.drop_table("reviews")
    op.drop_index(op.f("ix_evidence_dispute_id"), table_name="evidence")
    op.drop_table("evidence")
    op.drop_index(op.f("ix_decisions_dispute_id"), table_name="decisions")
    op.drop_table("decisions")
    op.drop_table("case_embeddings")
    op.drop_index(op.f("ix_audit_events_timestamp"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_dispute_id"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index(op.f("ix_disputes_status"), table_name="disputes")
    op.drop_index(op.f("ix_disputes_split"), table_name="disputes")
    op.drop_index(op.f("ix_disputes_reason_code"), table_name="disputes")
    op.drop_index(op.f("ix_disputes_deadline_at"), table_name="disputes")
    op.drop_index(op.f("ix_disputes_customer_id"), table_name="disputes")
    op.drop_table("disputes")
    op.drop_index(op.f("ix_transactions_txn_time"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_merchant_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_card_id"), table_name="transactions")
    op.drop_table("transactions")
    op.drop_index(op.f("ix_subscriptions_merchant_id"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_card_id"), table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_index(op.f("ix_cards_customer_id"), table_name="cards")
    op.drop_table("cards")
    op.drop_index(op.f("ix_merchants_name"), table_name="merchants")
    op.drop_table("merchants")
    op.drop_table("customers")
    # ### end Alembic commands ###
