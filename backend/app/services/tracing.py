"""Optional Langfuse tracing.

Disabled by default. Enable with ``LANGFUSE_ENABLED=true`` plus ``LANGFUSE_PUBLIC_KEY`` and
``LANGFUSE_SECRET_KEY`` (install with ``pip install -e ".[langfuse]"``). Tracing is strictly
best-effort: any failure is logged and swallowed, it can never break a dispute run. Only data the
LLM already sees (PII-masked text) is sent, never raw complaints.
"""

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.core.config import Settings

logger = logging.getLogger(__name__)


class Tracer:
    """No-op tracer; also the interface of the real one."""

    enabled = False

    @contextmanager
    def span(self, name: str, **metadata: Any) -> Iterator[None]:
        yield

    def generation(
        self,
        *,
        name: str,
        model: str,
        prompt_version: str,
        input_text: str,
        output: Any,
        tokens_in: int,
        tokens_out: int,
        cost_inr: float,
        latency_ms: int,
    ) -> None:
        return None

    def flush(self) -> None:
        return None


class LangfuseTracer(Tracer):
    enabled = True

    def __init__(self, client: Any) -> None:
        self._client = client

    @contextmanager
    def span(self, name: str, **metadata: Any) -> Iterator[None]:
        try:
            cm = self._client.start_as_current_observation(
                name=name, as_type="span", metadata=metadata
            )
            cm.__enter__()
        except Exception:
            logger.warning("langfuse span start failed", exc_info=True)
            yield
            return
        try:
            yield
        finally:
            try:
                cm.__exit__(None, None, None)
            except Exception:
                logger.warning("langfuse span end failed", exc_info=True)

    def generation(
        self,
        *,
        name: str,
        model: str,
        prompt_version: str,
        input_text: str,
        output: Any,
        tokens_in: int,
        tokens_out: int,
        cost_inr: float,
        latency_ms: int,
    ) -> None:
        try:
            with self._client.start_as_current_observation(
                name=name,
                as_type="generation",
                model=model,
                input=input_text,
                output=output,
                usage_details={"input": tokens_in, "output": tokens_out},
                metadata={
                    "prompt_version": prompt_version,
                    "cost_inr": cost_inr,
                    "latency_ms": latency_ms,
                },
            ):
                pass
        except Exception:
            logger.warning("langfuse generation failed", exc_info=True)

    def flush(self) -> None:
        try:
            self._client.flush()
        except Exception:
            logger.warning("langfuse flush failed", exc_info=True)


_tracer: Tracer = Tracer()


def configure_tracing(settings: Settings) -> Tracer:
    """Install the tracer implied by settings and return it (no-op when disabled/unavailable)."""
    global _tracer
    _tracer = Tracer()
    if not settings.langfuse_enabled:
        return _tracer
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.warning("LANGFUSE_ENABLED but keys are empty; tracing disabled")
        return _tracer
    try:
        from langfuse import Langfuse

        os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        _tracer = LangfuseTracer(client)
    except Exception:
        logger.warning("langfuse unavailable; tracing disabled", exc_info=True)
    return _tracer


def get_tracer() -> Tracer:
    """The currently configured tracer."""
    return _tracer
