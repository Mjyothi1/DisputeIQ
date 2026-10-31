"""No-Docker mode: tables are created on SQLite and the pipeline runs without pgvector."""

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.agent.pipeline import build_pipeline
from app.core.config import Settings
from app.db.init_db import init_db
from app.services.retrieval import NullRetriever


def test_init_db_skips_vector_table_on_sqlite() -> None:
    engine = create_engine("sqlite://")
    names = init_db(engine)
    assert "case_embeddings" not in names and "disputes" in names
    assert "disputes" in inspect(engine).get_table_names()
    init_db(engine)  # idempotent


def test_pipeline_uses_null_retriever_on_sqlite() -> None:
    engine = create_engine("sqlite://")
    init_db(engine)
    with Session(engine) as s:
        p = build_pipeline(s, Settings(llm_provider="mock"))
    assert isinstance(p.retriever, NullRetriever)
