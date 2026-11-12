"""Fill an EMPTY database with the demo dataset, and finish any half-done fill. Safe to rerun.

    python -m data_gen.bootstrap

What it does, in order:
1. If the database has no customers yet, it seeds the synthetic dataset anchored to *today*,
   so deadlines look realistic on the day you demo.
2. It runs the agent over any seeded case still in NEW (the historical backlog), using the
   offline rule-based engine. This is free, takes seconds and keeps the Gemini free-tier quota
   for live submissions. Each case's audit trail records the model it was processed with.
3. On PostgreSQL it builds the similar-case memory (pgvector) if it is empty.

It never deletes or overwrites anything. If customers already exist, step 1 is skipped, so your
data (live submissions, analyst reviews) is kept across restarts and redeploys.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.agent.pipeline import build_pipeline
from app.core.config import Settings, get_settings
from app.db import models
from app.db.enums import DisputeStatus
from app.db.init_db import init_db
from app.db.session import get_engine, get_session_factory

logger = logging.getLogger(__name__)


def ensure_demo_data(
    factory: sessionmaker[Session] | None = None, settings: Settings | None = None
) -> dict[str, int | bool]:
    """Seed if empty, then process the unprocessed seeded backlog. Returns what was done."""
    factory = factory or get_session_factory()
    settings = settings or get_settings()
    out: dict[str, int | bool] = {"seeded": False, "processed": 0, "memory": 0}

    with factory() as s:
        if s.get_bind().dialect.name == "sqlite":
            init_db(s.get_bind())  # type: ignore[arg-type]
        core_tables = (
            models.Customer, models.Card, models.Merchant, models.Transaction,
            models.Subscription, models.Dispute, models.Evidence, models.Decision,
            models.Review, models.AuditEvent,
        )
        database_is_empty = all(
            (s.scalar(select(func.count()).select_from(table)) or 0) == 0
            for table in core_tables
        )
        if database_is_empty:
            from data_gen.generate import generate

            generate(s, seed=42)
            out["seeded"] = True
            logger.info("demo data seeded")
        elif (s.scalar(select(func.count()).select_from(models.Customer)) or 0) == 0:
            logger.warning("demo seeding skipped: database has existing business records")

    with factory() as s:
        backlog = list(
            s.scalars(
                select(models.Dispute.id)
                .where(models.Dispute.split.is_not(None))
                .where(models.Dispute.ground_truth.is_not(None))
                .where(models.Dispute.status == DisputeStatus.NEW)
                .order_by(models.Dispute.id)
            )
        )
    offline = settings.model_copy(update={"llm_provider": "mock"})
    for dispute_id in backlog:
        try:
            with factory() as s:
                build_pipeline(s, offline).run(dispute_id)
            out["processed"] = int(out["processed"]) + 1
        except Exception:  # one bad case must not stop the rest
            logger.exception("backlog case failed", extra={"dispute_id": dispute_id})

    with factory() as s:
        if s.get_bind().dialect.name == "postgresql":
            try:
                has_memory = s.scalar(select(func.count()).select_from(models.CaseEmbedding))
                if not has_memory:
                    from app.services.embeddings import build_embedder
                    from data_gen.build_memory import build_memory

                    out["memory"] = build_memory(s, build_embedder(settings))
            except Exception:
                logger.exception("similar-case memory build failed; continuing without it")
    logger.info("demo data ready", extra=out)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    get_engine()
    print(ensure_demo_data())
