"""Schema tests. The DB round-trip runs only when TEST_DATABASE_URL points at Postgres."""

import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db import models
from app.db.base import Base
from app.db.enums import (
    AuditActor,
    AuthMethod,
    CardNetwork,
    DisputeChannel,
    MerchantCategory,
    TxnChannel,
)

UTC = timezone.utc  # Python 3.11+ compat

EXPECTED_TABLES = {
    "customers",
    "customer_accounts",
    "cards",
    "merchants",
    "transactions",
    "subscriptions",
    "disputes",
    "evidence",
    "decisions",
    "reviews",
    "audit_events",
    "case_embeddings",
}


def test_all_tables_registered() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_card_stores_only_masked_number() -> None:
    columns = set(Base.metadata.tables["cards"].columns.keys())
    assert {"masked_pan", "last4"} <= columns
    assert not {"pan", "card_number"} & columns


def test_money_is_numeric_not_float() -> None:
    col = Base.metadata.tables["transactions"].columns["amount"]
    assert col.type.__class__.__name__ == "Numeric"


def test_ground_truth_is_isolated_to_disputes() -> None:
    holders = [t for t, tbl in Base.metadata.tables.items() if "ground_truth" in tbl.columns]
    assert holders == ["disputes"]


TEST_DB = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")
def test_roundtrip_against_postgres() -> None:
    assert TEST_DB
    engine = create_engine(TEST_DB)
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        tables = list(Base.metadata.sorted_tables)
    except DBAPIError:
        # pgvector not installed on this server: exercise every table except the vector one.
        tables = [t for t in Base.metadata.sorted_tables if t.name != "case_embeddings"]

    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    try:
        with Session(engine) as s:
            cust = models.Customer(name="Asha Rao", phone="+919800000000")
            card = models.Card(
                customer=cust,
                masked_pan="XXXX-XXXX-XXXX-1234",
                last4="1234",
                network=CardNetwork.RUPAY,
            )
            merchant = models.Merchant(
                name="QuickKart", mcc="5311", category=MerchantCategory.ECOMMERCE
            )
            txn = models.Transaction(
                card=card,
                merchant=merchant,
                amount=Decimal("1499.50"),
                txn_time=datetime(2026, 9, 1, tzinfo=UTC),
                channel=TxnChannel.ECOM,
                auth_method=AuthMethod.OTP_3DS,
                details={"device_city": "Pune"},
            )
            dispute = models.Dispute(
                customer=cust,
                channel=DisputeChannel.FORM,
                raw_text="charged twice",
                matched_txn=txn,
            )
            dispute.audit_events.append(
                models.AuditEvent(step="intake", actor=AuditActor.AGENT, tokens_in=10)
            )
            s.add(dispute)
            s.commit()

            loaded = s.get(models.Dispute, dispute.id)
            assert loaded is not None
            assert loaded.status.value == "NEW"
            assert loaded.matched_txn is not None
            assert loaded.matched_txn.amount == Decimal("1499.50")
            assert loaded.matched_txn.details == {"device_city": "Pune"}
            assert len(loaded.audit_events) == 1
    finally:
        Base.metadata.drop_all(engine, tables=tables)
