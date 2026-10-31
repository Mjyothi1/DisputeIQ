"""Index DEV-split disputes into ``case_embeddings`` as historical resolved cases.

This is an OFFLINE bootstrap that stands in for "past cases already resolved by analysts": it
reads the synthetic ground-truth labels of the DEV split only (never TEST). The agent itself never
reads ground_truth; it only reads the resulting case_embeddings rows.

    python -m data_gen.build_memory
"""

from sqlalchemy import select

from app.core.config import get_settings
from app.db import models
from app.db.enums import DataSplit
from app.db.session import get_session_factory
from app.services.embeddings import Embedder, build_embedder
from app.services.pii import mask_pii
from app.services.retrieval import index_case


def build_memory(session, embedder: Embedder) -> int:  # type: ignore[no-untyped-def]
    n = 0
    for d in session.scalars(select(models.Dispute).where(models.Dispute.split == DataSplit.DEV)):
        gt = d.ground_truth or {}
        if not gt.get("reason_code") or gt.get("prompt_injection"):
            continue  # never memorise injection attempts
        index_case(
            session,
            embedder,
            d.id,
            mask_pii(d.raw_text).text,
            gt["reason_code"],
            gt["recommendation"],
        )
        n += 1
    session.commit()
    return n


if __name__ == "__main__":
    with get_session_factory()() as s:
        if s.get_bind().dialect.name != "postgresql":
            raise SystemExit(
                "Case memory needs PostgreSQL + pgvector; skipping (not needed on SQLite)."
            )
        emb = build_embedder(get_settings())
        print(f"Indexed {build_memory(s, emb)} historical cases using the '{emb.name}' embedder.")
