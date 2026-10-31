"""pgvector similar-case retrieval. Runs only when TEST_DATABASE_URL points at Postgres+pgvector."""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db import models
from app.db.base import Base
from app.db.enums import DisputeChannel
from app.services.embeddings import HashEmbedder
from app.services.retrieval import PgVectorRetriever, index_case

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def pg() -> Iterator[Session]:
    assert URL
    engine = create_engine(URL)
    with engine.begin() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    Base.metadata.drop_all(engine)


def make_dispute(s: Session, text_: str) -> int:
    cust = s.query(models.Customer).first() or models.Customer(name="C")
    s.add(cust)
    s.flush()
    d = models.Dispute(customer_id=cust.id, channel=DisputeChannel.FORM, raw_text=text_)
    s.add(d)
    s.flush()
    return d.id


def test_index_and_nearest_neighbours(pg: Session) -> None:
    emb = HashEmbedder(384)
    rows = {
        "I was charged twice by KartKing for one order": ("DUPLICATE_CHARGE", "REFUND"),
        "Double charge on my card at ShopSetu same order": ("DUPLICATE_CHARGE", "REFUND"),
        "ATM did not dispense cash but account debited": ("ATM_CASH_NOT_DISPENSED", "REFUND"),
        "I did not make this transaction at all": ("FRAUD_NOT_AUTHORISED", "FILE_CHARGEBACK"),
    }
    ids = {}
    for txt, (code, outcome) in rows.items():
        ids[txt] = make_dispute(pg, txt)
        index_case(pg, emb, ids[txt], txt, code, outcome)
    r = PgVectorRetriever(pg, emb)
    top = r.top_k("charged twice for the same order by KartKing", k=2)
    assert [c.reason_code for c in top] == ["DUPLICATE_CHARGE", "DUPLICATE_CHARGE"]
    assert top[0].similarity >= top[1].similarity and 0 < top[0].similarity <= 1.0
    assert top[0].outcome == "REFUND"


def test_exclude_self_and_upsert(pg: Session) -> None:
    emb = HashEmbedder(384)
    d1 = make_dispute(pg, "charged twice")
    d2 = make_dispute(pg, "charged twice again")
    index_case(pg, emb, d1, "charged twice", "DUPLICATE_CHARGE", "REFUND")
    index_case(pg, emb, d2, "charged twice again", "DUPLICATE_CHARGE", "REFUND")
    index_case(pg, emb, d1, "charged twice", "DUPLICATE_CHARGE", "REJECT")  # upsert
    got = PgVectorRetriever(pg, emb).top_k("charged twice", k=5, exclude_dispute_id=d1)
    assert [c.dispute_id for c in got] == [d2]
    assert pg.get(models.CaseEmbedding, d1).outcome == "REJECT"  # type: ignore[union-attr]
