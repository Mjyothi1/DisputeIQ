"""Langfuse tracing is optional and must never break a run."""

from contextlib import contextmanager
from typing import Any

import pytest
from pydantic import BaseModel

from app.agent.llm import RawResponse, RetryingClient
from app.core.config import Settings
from app.services import tracing
from app.services.tracing import LangfuseTracer, Tracer, configure_tracing, get_tracer


class _Out(BaseModel):
    x: int


class _Backend:
    def call(self, system: str, user: str, schema: type[BaseModel]) -> RawResponse:
        return RawResponse({"x": 1}, 10, 5)


class FakeLangfuse:
    def __init__(self, boom: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.flushed = False
        self.boom = boom

    @contextmanager
    def start_as_current_observation(self, **kw: Any):  # type: ignore[no-untyped-def]
        if self.boom:
            raise RuntimeError("langfuse down")
        self.calls.append(kw)
        yield

    def flush(self) -> None:
        self.flushed = True


@pytest.fixture(autouse=True)
def _reset() -> Any:
    yield
    configure_tracing(Settings(langfuse_enabled=False))


def test_disabled_by_default_is_noop() -> None:
    t = configure_tracing(Settings())
    assert isinstance(t, Tracer) and not t.enabled
    with t.span("x"):
        pass


def test_enabled_without_keys_falls_back_to_noop() -> None:
    assert not configure_tracing(Settings(langfuse_enabled=True)).enabled


def test_generation_is_recorded_with_usage_and_cost() -> None:
    fake = FakeLangfuse()
    tracing._tracer = LangfuseTracer(fake)
    res = RetryingClient(_Backend(), "claude-sonnet-5-5", 88.0).structured(
        task="intake", system="s", user="masked text", schema=_Out, prompt_version="v1"
    )
    assert res.parsed.x == 1
    (call,) = fake.calls
    assert call["as_type"] == "generation" and call["name"] == "intake"
    assert call["usage_details"] == {"input": 10, "output": 5}
    assert call["input"] == "masked text" and call["model"] == "claude-sonnet-5-5"


def test_span_and_flush() -> None:
    fake = FakeLangfuse()
    tracing._tracer = LangfuseTracer(fake)
    with get_tracer().span("dispute_pipeline", dispute_id=3):
        pass
    get_tracer().flush()
    assert fake.calls[0]["name"] == "dispute_pipeline" and fake.flushed


def test_tracer_failures_never_break_the_llm_call() -> None:
    tracing._tracer = LangfuseTracer(FakeLangfuse(boom=True))
    res = RetryingClient(_Backend(), "m", 88.0).structured(
        task="t", system="s", user="u", schema=_Out, prompt_version="v1"
    )
    assert res.parsed.x == 1
    with get_tracer().span("p"):
        pass
