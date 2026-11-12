"""CLI: seed the database with synthetic data.

python -m data_gen.seed --seed 42 --anchor 2026-10-26 --reset
"""

import argparse
import json
from datetime import datetime, timezone

from sqlalchemy import delete, inspect

from app.db import models
from app.db.session import get_session_factory
from data_gen.generate import generate

UTC = timezone.utc  # datetime.UTC was added in Python 3.11; timezone.utc works everywhere

TABLES_CHILD_FIRST = [
    models.CaseEmbedding, models.AuditEvent, models.Review, models.Decision, models.Evidence,
    models.Dispute, models.Subscription, models.Transaction, models.Merchant, models.Card,
    models.Customer,
]  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--anchor", help="YYYY-MM-DD reference 'now' for reproducible data")
    ap.add_argument("--reset", action="store_true", help="delete all existing rows first")
    ap.add_argument(
        "--llm",
        action="store_true",
        help="write complaint texts with the configured LLM_PROVIDER (needs an API key); "
        "texts are cached in data_gen/.complaint_cache.json",
    )
    args = ap.parse_args()
    anchor = (
        datetime.strptime(args.anchor, "%Y-%m-%d").replace(hour=12, tzinfo=UTC)
        if args.anchor
        else None
    )
    with get_session_factory()() as session:
        if args.reset:
            existing = set(inspect(session.get_bind()).get_table_names())
            for model in TABLES_CHILD_FIRST:
                if model.__tablename__ in existing:  # case_embeddings is absent on SQLite
                    session.execute(delete(model))
            session.commit()
        writer = None
        if args.llm:
            from app.agent.llm import build_llm_client
            from app.core.config import get_settings
            from data_gen.complaints import LLMWriter

            settings = get_settings()
            if settings.llm_provider == "mock":
                raise SystemExit(
                    "--llm needs a real provider (LLM_PROVIDER=gemini with GEMINI_API_KEY, "
                    "or anthropic/openai with its key); mock cannot write complaint text"
                )
            writer = LLMWriter(build_llm_client(settings), "data_gen/.complaint_cache.json")
        summary = generate(session, seed=args.seed, anchor=anchor, writer=writer)
        if writer is not None:
            summary["complaint_writer"] = writer.stats
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
