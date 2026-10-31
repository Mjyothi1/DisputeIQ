"""Shared fixtures: in-memory SQLite (all tables except the pgvector one) and row factories."""

from collections.abc import Iterator
from datetime import datetime, timezone

UTC = timezone.utc  # datetime.UTC was added in Python 3.11; timezone.utc works everywhere

from decimal import Decimal
from itertools import count
from typing import Any

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session

from app.db import models
from app.db.base import Base
from app.db.enums import (
    AuthMethod,
    CardNetwork,
    DisputeChannel,
    MerchantCategory,
    TxnChannel,
)

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
SQLITE_TABLES = [t for t in Base.metadata.sorted_tables if t.name != "case_embeddings"]


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine, tables=SQLITE_TABLES)
    with Session(engine) as s:
        yield s


class Factory:
    """Tiny row factory so tests read declaratively."""

    def __init__(self, session: Session) -> None:
        self.s = session
        self._n = count(1)
        self.customer = models.Customer(name="Test Customer")
        self.card = models.Card(
            customer=self.customer,
            masked_pan="XXXX-XXXX-XXXX-1111",
            last4="1111",
            network=CardNetwork.VISA,
        )
        self.merchant = models.Merchant(
            name="ShopNow", mcc="5311", category=MerchantCategory.ECOMMERCE
        )
        session.add_all([self.customer, self.card, self.merchant])
        session.flush()

    def txn(self, **kw: Any) -> models.Transaction:
        values: dict[str, Any] = {
            "card": self.card,
            "merchant": self.merchant,
            "amount": Decimal("1000.00"),
            "txn_time": NOW,
            "channel": TxnChannel.ECOM,
            "auth_method": AuthMethod.OTP_3DS,
        }
        values.update(kw)
        t = models.Transaction(**values)
        self.s.add(t)
        self.s.flush()
        return t

    def dispute(self, **kw: Any) -> models.Dispute:
        values: dict[str, Any] = {
            "customer": self.customer,
            "channel": DisputeChannel.FORM,
            "raw_text": "x",
            "created_at": NOW,
        }
        values.update(kw)
        d = models.Dispute(**values)
        self.s.add(d)
        self.s.flush()
        return d


@pytest.fixture
def factory(session: Session) -> Factory:
    return Factory(session)
