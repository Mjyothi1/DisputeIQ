"""Customer portal API. Every route derives the customer from the signed token, never the request.

Ownership is checked on every transaction and dispute lookup; records that belong to someone else
return 404 (not 403) so their existence is not revealed.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.auth import RateLimiter, submit_limiter
from app.api.deps import Runner, get_runner
from app.core.config import Settings, get_settings
from app.core.security import (
    hash_password,
    issue_customer_token,
    read_customer_token,
    token_secret,
    verify_password,
)
from app.db import models as m
from app.db.enums import DisputeChannel
from app.db.session import get_db
from app.services.customer_view import CATEGORIES, customer_status, timeline

router = APIRouter(prefix="/portal", tags=["customer portal"])
DB = Annotated[Session, Depends(get_db)]
login_limiter = RateLimiter(limit=10, window_s=60)


# ---- auth -----------------------------------------------------------------------------------
class Principal(BaseModel):
    account_id: int
    customer_id: int


def _secret(settings: Settings) -> bytes:
    s = token_secret(settings)
    if s is None:
        raise HTTPException(
            503, "Customer portal is not configured on the server (set AUTH_SECRET)."
        )
    return s


def current_customer(
    db: DB,
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    token = (
        authorization[7:].strip()
        if authorization and authorization.lower().startswith("bearer ")
        else ""
    )
    payload = read_customer_token(_secret(settings), token)
    if payload is None:
        raise HTTPException(
            401, "Please sign in to the customer portal.", headers={"WWW-Authenticate": "Bearer"}
        )
    acct = db.get(m.CustomerAccount, payload["sub"])
    if acct is None or acct.customer_id != payload["cid"]:
        raise HTTPException(401, "Session is no longer valid. Please sign in again.")
    return Principal(account_id=acct.id, customer_id=acct.customer_id)


Me = Annotated[Principal, Depends(current_customer)]


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or v.startswith("@") or v.endswith("@") or " " in v:
            raise ValueError("Enter a valid email address.")
        return v


class Registration(Credentials):
    name: str = Field(min_length=2, max_length=120)
    # NOTE: no role field. Anything extra (e.g. "role": "REVIEWER") is ignored by pydantic.


class TokenOut(BaseModel):
    token: str
    name: str
    role: str = "customer"


@router.post("/login", response_model=TokenOut, summary="Customer sign-in")
def login(
    body: Credentials, db: DB, settings: Annotated[Settings, Depends(get_settings)]
) -> TokenOut:
    secret = _secret(settings)
    login_limiter.check(f"login:{body.email}")
    acct = db.scalars(
        select(m.CustomerAccount)
        .options(joinedload(m.CustomerAccount.customer))
        .where(m.CustomerAccount.email == body.email)
    ).first()
    # Same message and similar work whether the email exists or not.
    if acct is None:
        verify_password(body.password, hash_password("timing-equaliser"))
        raise HTTPException(401, "Email or password is incorrect.")
    if not verify_password(body.password, acct.password_hash):
        raise HTTPException(401, "Email or password is incorrect.")
    return TokenOut(
        token=issue_customer_token(secret, acct.id, acct.customer_id), name=acct.customer.name
    )


# ---- profile & transactions -----------------------------------------------------------------
class CardOut(BaseModel):
    network: str
    last4: str
    masked: str


class ProfileOut(BaseModel):
    name: str
    email: str
    cards: list[CardOut]


class TxnOut(BaseModel):
    id: int
    merchant_name: str
    amount: Decimal
    currency: str
    txn_time: datetime
    card_last4: str
    channel: str
    has_open_dispute: bool


@router.get("/me", response_model=ProfileOut)
def me(p: Me, db: DB) -> ProfileOut:
    cust = db.scalars(
        select(m.Customer)
        .options(selectinload(m.Customer.cards))
        .where(m.Customer.id == p.customer_id)
    ).one()
    acct = db.get(m.CustomerAccount, p.account_id)
    return ProfileOut(
        name=cust.name, email=acct.email if acct else "",
        cards=[CardOut(network=c.network.value, last4=c.last4, masked=f"{c.network.value} •••• {c.last4}") for c in cust.cards],
    )  # fmt: skip


def _own_txn_query(customer_id: int):  # type: ignore[no-untyped-def]
    return (
        select(m.Transaction)
        .join(m.Card, m.Transaction.card_id == m.Card.id)
        .where(m.Card.customer_id == customer_id)
        .options(joinedload(m.Transaction.merchant), joinedload(m.Transaction.card))
    )


@router.get("/transactions", response_model=list[TxnOut])
def transactions(p: Me, db: DB) -> list[TxnOut]:
    rows = db.scalars(
        _own_txn_query(p.customer_id)
        .order_by(m.Transaction.txn_time.desc(), m.Transaction.id.desc())
        .limit(50)
    ).all()
    disputed = set(
        db.scalars(select(m.Dispute.customer_txn_id).where(m.Dispute.customer_id == p.customer_id))
    )
    return [
        TxnOut(id=t.id, merchant_name=t.merchant.name, amount=t.amount, currency=t.currency, txn_time=t.txn_time,
               card_last4=t.card.last4, channel=t.channel.value, has_open_dispute=t.id in disputed)
        for t in rows
    ]  # fmt: skip


# ---- disputes -------------------------------------------------------------------------------
class ComplaintIn(BaseModel):
    transaction_id: int | None = None
    merchant_name: str | None = Field(default=None, min_length=2, max_length=160)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    transaction_date: datetime | None = None
    card_last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    category: str
    description: str = Field(min_length=5, max_length=3000)

    @field_validator("category")
    @classmethod
    def _cat(cls, v: str) -> str:
        if v not in CATEGORIES:
            raise ValueError("Unknown category.")
        return v

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 5 or not any(ch.isalnum() for ch in v):
            raise ValueError("Please describe the problem.")
        return v


class ComplaintSummary(BaseModel):
    id: int
    reference: str
    merchant: str | None
    amount: Decimal | None
    category: str | None
    status: str
    status_label: str
    message: str
    created_at: datetime


class TimelineItem(BaseModel):
    label: str
    at: datetime | None


class ComplaintDetail(ComplaintSummary):
    description: str
    transaction_date: datetime | None
    letter: str | None
    timeline: list[TimelineItem]


def _ref(i: int) -> str:
    return f"DIQ-{i:06d}"


def _summary(d: m.Dispute) -> ComplaintSummary:
    st, t = customer_status(d), d.customer_txn
    return ComplaintSummary(
        id=d.id, reference=_ref(d.id), merchant=t.merchant.name if t else d.customer_merchant, amount=t.amount if t else d.customer_amount,
        category=CATEGORIES.get(d.customer_category or ""), status=st.code, status_label=st.label,
        message=st.message, created_at=d.created_at,
    )  # fmt: skip


def _load(db: Session, customer_id: int):  # type: ignore[no-untyped-def]
    return (
        select(m.Dispute)
        .where(m.Dispute.customer_id == customer_id)
        .options(
            selectinload(m.Dispute.decisions),
            selectinload(m.Dispute.reviews),
            selectinload(m.Dispute.audit_events),
            joinedload(m.Dispute.customer_txn).joinedload(m.Transaction.merchant),
        )  # fmt: skip
    )


@router.post("/disputes", response_model=ComplaintSummary, status_code=202, summary="Report a problem")
def submit(body: ComplaintIn, p: Me, db: DB, background: BackgroundTasks, runner: Annotated[Runner, Depends(get_runner)]) -> ComplaintSummary:
    submit_limiter.check(f"cust:{p.customer_id}")
    txn = None
    if body.transaction_id is not None:
        txn = db.scalars(_own_txn_query(p.customer_id).where(m.Transaction.id == body.transaction_id)).first()
        if txn is None:
            raise HTTPException(404, "Transaction not found.")
        merchant, amount, txn_date, last4 = txn.merchant.name, txn.amount, txn.txn_time, txn.card.last4
        facts = f"[Customer portal] Category: {CATEGORIES[body.category]}. Selected transaction: {merchant}, Rs {amount:,.2f} on {txn_date:%d %b %Y}, card ending {last4}.\n"
    else:
        if not body.merchant_name or body.amount is None or body.transaction_date is None:
            raise HTTPException(422, "Enter merchant, amount and transaction date, or select a listed transaction.")
        merchant, amount, txn_date, last4 = body.merchant_name.strip(), body.amount, body.transaction_date, body.card_last4
        card_text = f", card ending {last4}" if last4 else ""
        facts = f"[Customer portal] Category: {CATEGORIES[body.category]}. Customer-provided transaction details (NOT BANK-VERIFIED): {merchant}, Rs {amount:,.2f} on {txn_date:%d %b %Y}{card_text}. Verify against issuer records before deciding.\n"
    d = m.Dispute(customer_id=p.customer_id, channel=DisputeChannel.FORM, raw_text=facts + body.description, customer_category=body.category, customer_txn_id=txn.id if txn else None, customer_merchant=None if txn else merchant, customer_amount=None if txn else amount, customer_txn_date=None if txn else txn_date, customer_card_last4=None if txn else last4)
    db.add(d)
    db.commit()
    background.add_task(runner, d.id)
    d = db.scalars(_load(db, p.customer_id).where(m.Dispute.id == d.id)).one()
    return _summary(d)

@router.get("/disputes", response_model=list[ComplaintSummary])
def my_disputes(p: Me, db: DB) -> list[ComplaintSummary]:
    rows = db.scalars(
        _load(db, p.customer_id).order_by(m.Dispute.created_at.desc(), m.Dispute.id.desc())
    ).all()
    return [_summary(d) for d in rows]


@router.get("/disputes/{dispute_id}", response_model=ComplaintDetail)
def my_dispute(dispute_id: int, p: Me, db: DB) -> ComplaintDetail:
    d = db.scalars(_load(db, p.customer_id).where(m.Dispute.id == dispute_id)).first()
    if d is None:
        raise HTTPException(404, "Complaint not found.")
    s, st, t = _summary(d), customer_status(d), d.customer_txn
    text = (
        d.raw_text.split("\n", 1)[1]
        if d.raw_text.startswith("[Customer portal]") and "\n" in d.raw_text
        else d.raw_text
    )
    return ComplaintDetail(
        **s.model_dump(),
        description=text,
        transaction_date=t.txn_time if t else d.customer_txn_date,
        letter=st.letter,
        timeline=[TimelineItem(label=str(i["label"]), at=i["at"]) for i in timeline(d)],
    )


@router.get("/categories", response_model=dict[str, str])
def categories() -> dict[str, str]:
    return CATEGORIES
