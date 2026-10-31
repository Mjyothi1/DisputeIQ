"""Create all tables directly from the models (no-Docker / SQLite mode).

    python -m app.db.init_db

With PostgreSQL use ``alembic upgrade head`` instead (it also enables the pgvector extension).
On SQLite the pgvector ``case_embeddings`` table is skipped: similar-case retrieval is then
disabled and the agent classifies without it. Everything else behaves the same.
"""

from sqlalchemy import Engine

from app.db import models  # noqa: F401  (registers tables)
from app.db.base import Base
from app.db.session import get_engine


def init_db(engine: Engine | None = None) -> list[str]:
    """Create missing tables; returns the table names it manages."""
    engine = engine or get_engine()
    tables = [
        t
        for t in Base.metadata.sorted_tables
        if not (engine.dialect.name == "sqlite" and t.name == "case_embeddings")
    ]
    Base.metadata.create_all(engine, tables=tables)
    return [t.name for t in tables]


if __name__ == "__main__":
    names = init_db()
    print(f"ready: {len(names)} tables on {get_engine().dialect.name}")
