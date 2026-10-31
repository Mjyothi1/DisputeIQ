"""FastAPI dependencies. Overridable in tests (``app.dependency_overrides``)."""

import logging
from collections.abc import Callable
from functools import lru_cache

from app.agent.llm import LLMError
from app.agent.pipeline import build_pipeline
from app.core.config import get_settings
from app.db import models
from app.db.enums import AuditActor, DisputeStatus
from app.db.session import get_session_factory
from app.services.audit import AuditLogger
from app.services.embeddings import Embedder, build_embedder

logger = logging.getLogger(__name__)
Runner = Callable[[int], None]


def default_runner(dispute_id: int) -> None:
    """Run the agent for one dispute in its own session (used for background tasks).

    Provider failures (missing Gemini key, quota, network) are logged on the case and never
    silently replaced with mock analysis.
    """
    try:
        with get_session_factory()() as session:
            build_pipeline(session).run(dispute_id)
    except LLMError as exc:
        logger.error(
            "LLM provider failed (no mock fallback)",
            extra={"dispute_id": dispute_id, "error": str(exc)[:300]},
        )
        _mark_provider_failure(dispute_id, str(exc))
    except Exception:
        logger.exception("background processing failed", extra={"dispute_id": dispute_id})
        _mark_provider_failure(dispute_id, "Unexpected processing failure; see server logs.")


def _mark_provider_failure(dispute_id: int, message: str) -> None:
    """Persist a human-visible failure when the pipeline never started (e.g. missing API key)."""
    try:
        with get_session_factory()() as session:
            d = session.get(models.Dispute, dispute_id)
            if d is None:
                return
            if d.status in (DisputeStatus.NEW, DisputeStatus.PROCESSING):
                d.status = DisputeStatus.NEEDS_HUMAN
            AuditLogger(session, dispute_id).log(
                "llm_provider_error",
                AuditActor.TOOL,
                None,
                f"{message} (no fabricated AI analysis; mock was not used)",
            )
            session.commit()
    except Exception:  # noqa: BLE001 — never crash the worker on secondary logging failure
        logger.exception("could not record provider failure", extra={"dispute_id": dispute_id})


def get_runner() -> Runner:
    return default_runner


@lru_cache
def _embedder() -> Embedder:
    return build_embedder(get_settings())


def get_embedder() -> Embedder | None:
    return _embedder()
