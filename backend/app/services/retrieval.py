"""Similar-case retrieval over resolved cases (pgvector cosine distance)."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CaseEmbedding
from app.services.embeddings import Embedder


@dataclass(frozen=True)
class SimilarCase:
    dispute_id: int
    summary: str
    reason_code: str | None
    outcome: str | None
    similarity: float  # cosine similarity, 1.0 = identical

    def as_prompt_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.dispute_id,
            "similarity": round(self.similarity, 3),
            "reason_code": self.reason_code,
            "outcome": self.outcome,
            "summary": self.summary,
        }


class Retriever(Protocol):
    def top_k(
        self, text: str, k: int, exclude_dispute_id: int | None = None
    ) -> list[SimilarCase]: ...


class PgVectorRetriever:
    """Nearest resolved cases by cosine distance, using the ``case_embeddings`` table."""

    def __init__(self, session: Session, embedder: Embedder) -> None:
        self.session, self.embedder = session, embedder

    def top_k(
        self, text: str, k: int = 3, exclude_dispute_id: int | None = None
    ) -> list[SimilarCase]:
        vec = self.embedder.embed([text])[0]
        dist = CaseEmbedding.embedding.cosine_distance(vec).label("dist")
        stmt = select(CaseEmbedding, dist).order_by(dist).limit(k)
        if exclude_dispute_id is not None:
            stmt = stmt.where(CaseEmbedding.dispute_id != exclude_dispute_id)
        return [
            SimilarCase(c.dispute_id, c.summary, c.reason_code, c.outcome, 1.0 - float(d))
            for c, d in self.session.execute(stmt).all()
        ]


class InMemoryRetriever:
    """Same interface without a database (tests, and SQLite-backed unit tests)."""

    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder
        self._cases: list[tuple[SimilarCase, list[float]]] = []

    def add(self, dispute_id: int, summary: str, reason_code: str, outcome: str) -> None:
        vec = self.embedder.embed([summary])[0]
        self._cases.append((SimilarCase(dispute_id, summary, reason_code, outcome, 0.0), vec))

    def top_k(
        self, text: str, k: int = 3, exclude_dispute_id: int | None = None
    ) -> list[SimilarCase]:
        q = self.embedder.embed([text])[0]
        scored = [
            (sum(a * b for a, b in zip(q, v, strict=True)), c)
            for c, v in self._cases
            if c.dispute_id != exclude_dispute_id
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            SimilarCase(c.dispute_id, c.summary, c.reason_code, c.outcome, s) for s, c in scored[:k]
        ]


class NullRetriever:
    def top_k(
        self, text: str, k: int = 3, exclude_dispute_id: int | None = None
    ) -> list[SimilarCase]:
        return []


def index_case(
    session: Session,
    embedder: Embedder,
    dispute_id: int,
    masked_text: str,
    reason_code: str,
    outcome: str,
) -> None:
    """Insert or update the embedding for a resolved case. ``masked_text`` must already be masked."""
    summary = masked_text[:300]
    vec = embedder.embed([masked_text])[0]
    row = session.get(CaseEmbedding, dispute_id)
    if row is None:
        session.add(
            CaseEmbedding(
                dispute_id=dispute_id,
                embedding=vec,
                summary=summary,
                reason_code=reason_code,
                outcome=outcome,
            )
        )
    else:
        row.embedding, row.summary, row.reason_code, row.outcome = (
            vec,
            summary,
            reason_code,
            outcome,
        )
    session.flush()


def index_many(
    session: Session, embedder: Embedder, rows: Sequence[tuple[int, str, str, str]]
) -> int:
    """Index many ``(dispute_id, masked_text, reason_code, outcome)`` rows."""
    for r in rows:
        index_case(session, embedder, *r)
    return len(rows)
