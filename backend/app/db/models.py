"""SQLAlchemy 2.0 ORM models for DisputeIQ.

Money is stored as ``Numeric(12, 2)`` (INR) and handled as ``Decimal`` in Python, never float.
Only masked card numbers and the last four digits are ever stored.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

try:
    from pgvector.sqlalchemy import Vector as _Vector

    def Vector(dim: int) -> Any:  # type: ignore[misc]
        return _Vector(dim)
except ImportError:
    # pgvector not installed (SQLite mode) - use a plain JSON column; the table is skipped anyway
    def Vector(dim: int) -> Any:  # type: ignore[misc]
        from sqlalchemy import JSON
        return JSON()
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db.base import Base, JSONType
from app.db.enums import (
    AuditActor,
    AuthMethod,
    CardNetwork,
    CardStatus,
    DataSplit,
    DisputeChannel,
    DisputeStatus,
    MerchantCategory,
    Recommendation,
    RefundStatus,
    ReviewAction,
    SubscriptionStatus,
    TxnChannel,
    TxnStatus,
)

EMBEDDING_DIM = get_settings().embedding_dim


def _enum(enum_cls: type) -> Enum:
    """Store enums as validated VARCHAR (portable, easy to migrate) rather than native PG enums."""
    return Enum(enum_cls, native_enum=False, length=32, validate_strings=True)


def _now() -> Any:
    return func.now()


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(160))
    segment: Mapped[str] = mapped_column(String(32), default="RETAIL")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())

    cards: Mapped[list["Card"]] = relationship(back_populates="customer")
    disputes: Mapped[list["Dispute"]] = relationship(back_populates="customer")


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    masked_pan: Mapped[str] = mapped_column(String(19))  # e.g. XXXX-XXXX-XXXX-1234
    last4: Mapped[str] = mapped_column(String(4))
    network: Mapped[CardNetwork] = mapped_column(_enum(CardNetwork))
    status: Mapped[CardStatus] = mapped_column(_enum(CardStatus), default=CardStatus.ACTIVE)

    customer: Mapped[Customer] = relationship(back_populates="cards")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="card")


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    mcc: Mapped[str] = mapped_column(String(4))
    category: Mapped[MerchantCategory] = mapped_column(_enum(MerchantCategory))
    city: Mapped[str | None] = mapped_column(String(80))
    is_recurring_biller: Mapped[bool] = mapped_column(Boolean, default=False)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), index=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    txn_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    channel: Mapped[TxnChannel] = mapped_column(_enum(TxnChannel))
    auth_method: Mapped[AuthMethod] = mapped_column(_enum(AuthMethod))
    status: Mapped[TxnStatus] = mapped_column(_enum(TxnStatus), default=TxnStatus.SETTLED)
    refund_status: Mapped[RefundStatus] = mapped_column(
        _enum(RefundStatus), default=RefundStatus.NONE
    )
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    # True when the customer's account was debited (relevant for FAILED / ATM cases).
    account_debited: Mapped[bool] = mapped_column(Boolean, default=True)
    # Free-form details, e.g. ATM cash-dispense result, device city.
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONType)

    card: Mapped[Card] = relationship(back_populates="transactions")
    merchant: Mapped[Merchant] = relationship()


class Subscription(Base):
    """Needed by the recurring-cancellation check (CANCELLED_RECURRING)."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), index=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id"), index=True)
    status: Mapped[SubscriptionStatus] = mapped_column(
        _enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Dispute(Base):
    __tablename__ = "disputes"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    channel: Mapped[DisputeChannel] = mapped_column(_enum(DisputeChannel))
    raw_text: Mapped[str] = mapped_column(Text)
    masked_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[DisputeStatus] = mapped_column(
        _enum(DisputeStatus), default=DisputeStatus.NEW, index=True
    )
    extracted_fields: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    matched_txn_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"))
    reason_code: Mapped[str | None] = mapped_column(String(40), index=True)
    confidence: Mapped[float | None] = mapped_column(Float)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())
    # Customer-portal submissions only: the category the customer picked and the transaction they
    # selected (ownership verified server-side). Both NULL for staff-entered and seeded disputes.
    customer_category: Mapped[str | None] = mapped_column(String(40))
    customer_txn_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"))
    customer_merchant: Mapped[str | None] = mapped_column(String(160))
    customer_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    customer_txn_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    customer_card_last4: Mapped[str | None] = mapped_column(String(4))

    # Synthetic data only. The agent must never read these two columns.
    ground_truth: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    split: Mapped[DataSplit | None] = mapped_column(_enum(DataSplit), index=True)

    customer: Mapped[Customer] = relationship(back_populates="disputes")
    matched_txn: Mapped[Transaction | None] = relationship(foreign_keys=[matched_txn_id])
    customer_txn: Mapped[Transaction | None] = relationship(foreign_keys=[customer_txn_id])
    evidence: Mapped[list["Evidence"]] = relationship(
        back_populates="dispute", cascade="all, delete-orphan"
    )
    decisions: Mapped[list["Decision"]] = relationship(
        back_populates="dispute", cascade="all, delete-orphan"
    )
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="dispute", cascade="all, delete-orphan"
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(
        back_populates="dispute", cascade="all, delete-orphan"
    )


class CustomerAccount(Base):
    """Customer-portal login. Always role CUSTOMER; reviewers never live in this table."""

    __tablename__ = "customer_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), unique=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # Existing and seeded accounts remain verified; registrations explicitly set this to False.
    email_verified: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    email_verification_code_hash: Mapped[str | None] = mapped_column(String(64))
    email_verification_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_verification_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())

    customer: Mapped[Customer] = relationship()


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    dispute_id: Mapped[int] = mapped_column(ForeignKey("disputes.id"), index=True)
    check_name: Mapped[str] = mapped_column(String(60))
    result: Mapped[str] = mapped_column(String(20))  # PASS | FAIL | INCONCLUSIVE | INFO
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())

    dispute: Mapped[Dispute] = relationship(back_populates="evidence")


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    dispute_id: Mapped[int] = mapped_column(ForeignKey("disputes.id"), index=True)
    recommendation: Mapped[Recommendation] = mapped_column(_enum(Recommendation))
    rationale: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    friendly_fraud_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    drafted_customer_letter: Mapped[str | None] = mapped_column(Text)
    drafted_chargeback_filing: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(80))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())

    dispute: Mapped[Dispute] = relationship(back_populates="decisions")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    dispute_id: Mapped[int] = mapped_column(ForeignKey("disputes.id"), index=True)
    analyst: Mapped[str] = mapped_column(String(120))
    action: Mapped[ReviewAction] = mapped_column(_enum(ReviewAction))
    final_decision: Mapped[Recommendation] = mapped_column(_enum(Recommendation))
    notes: Mapped[str | None] = mapped_column(Text)
    edited_letter: Mapped[str | None] = mapped_column(Text)
    edited_filing: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())

    dispute: Mapped[Dispute] = relationship(back_populates="reviews")


class AuditEvent(Base):
    """Append-only log of every pipeline step, tool call, model output and human action."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    dispute_id: Mapped[int] = mapped_column(ForeignKey("disputes.id"), index=True)
    step: Mapped[str] = mapped_column(String(60))
    actor: Mapped[AuditActor] = mapped_column(_enum(AuditActor))
    input_summary: Mapped[str | None] = mapped_column(Text)
    output_summary: Mapped[str | None] = mapped_column(Text)
    # LLM call telemetry (null for non-LLM steps).
    model: Mapped[str | None] = mapped_column(String(80))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    cost_inr: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=_now(), index=True
    )

    dispute: Mapped[Dispute] = relationship(back_populates="audit_events")


class CaseEmbedding(Base):
    """Embedding of a resolved case's summary, for pgvector similar-case retrieval."""

    __tablename__ = "case_embeddings"

    dispute_id: Mapped[int] = mapped_column(ForeignKey("disputes.id"), primary_key=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    summary: Mapped[str] = mapped_column(Text)
    reason_code: Mapped[str | None] = mapped_column(String(40), index=True)
    outcome: Mapped[str | None] = mapped_column(String(32))  # final recommendation
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())
