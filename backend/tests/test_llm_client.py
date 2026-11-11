from typing import Any

import pytest
from pydantic import BaseModel

from app.agent.llm import (
    LLMError,
    RawResponse,
    RetryingClient,
    build_llm_client,
    classify_gemini_api_error,
    cost_inr,
    resolve_model,
)
from app.agent.mock_llm import MockLLM
from app.core.config import Settings


class Out(BaseModel):
    answer: int


class Scripted:
    """Backend whose calls follow a script of responses/exceptions."""

    def __init__(self, *script: Any) -> None:
        self.script, self.calls = list(script), 0

    def call(self, system: str, user: str, schema: type[BaseModel]) -> RawResponse:
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        assert isinstance(item, RawResponse)
        return item


def client(backend: Scripted, sleeps: list[float], retries: int = 3) -> RetryingClient:
    return RetryingClient(backend, "claude-sonnet-5-5", 88.0, retries, sleep=sleeps.append)


def call(c: RetryingClient) -> Any:
    return c.structured(task="t", system="s", user="u", schema=Out, prompt_version="v1")


def test_success_tracks_tokens_and_cost() -> None:
    res = call(client(Scripted(RawResponse({"answer": 1}, 1_000_000, 0)), []))
    assert res.parsed.answer == 1 and res.tokens_in == 1_000_000
    assert res.cost_inr == pytest.approx(3.0 * 88.0)
    assert res.prompt_version == "v1" and res.model == "claude-sonnet-5-5"


def test_transient_errors_retried_with_exponential_backoff() -> None:
    sleeps: list[float] = []
    b = Scripted(TimeoutError("x"), ConnectionError("y"), RawResponse({"answer": 2}, 10, 5))
    assert call(client(b, sleeps)).parsed.answer == 2
    assert sleeps == [1.0, 2.0] and b.calls == 3


def test_gives_up_after_max_retries() -> None:
    sleeps: list[float] = []
    b = Scripted(*[TimeoutError("down")] * 3)
    with pytest.raises(LLMError, match="after 3 attempts"):
        call(client(b, sleeps, retries=2))
    assert b.calls == 3 and len(sleeps) == 2


def test_invalid_output_gets_one_corrective_retry() -> None:
    b = Scripted(RawResponse({"answer": "nope"}, 10, 1), RawResponse({"answer": 3}, 12, 2))
    res = call(client(b, []))
    assert res.parsed.answer == 3 and res.tokens_in == 22 and res.tokens_out == 3


def test_invalid_output_twice_raises() -> None:
    b = Scripted(RawResponse({}, 1, 1), RawResponse({"answer": "x"}, 1, 1))
    with pytest.raises(LLMError, match="schema validation twice"):
        call(client(b, []))


def test_cost_table_and_unknown_model_default() -> None:
    assert cost_inr("gpt-4o-mini", 1_000_000, 1_000_000, 100.0) == pytest.approx((0.15 + 0.6) * 100)
    assert cost_inr("mystery", 1_000_000, 0, 1.0) == pytest.approx(3.0)
    assert cost_inr("gemini-3.8-flash", 1_000_000, 1_000_000, 88.0) == 0.0


def test_resolve_model_prefers_gemini_model_then_llm_model() -> None:
    assert resolve_model(Settings(_env_file=None, llm_provider="gemini")) == "gemini-3.8-flash"
    assert (
        resolve_model(
            Settings(_env_file=None, llm_provider="gemini", gemini_model="gemini-3.5-flash-lite")
        )
        == "gemini-3.5-flash-lite"
    )
    assert (
        resolve_model(
            Settings(
                _env_file=None,
                llm_provider="gemini",
                gemini_model="gemini-3.8-flash",
                llm_model="gemini-x",
            )
        )
        == "gemini-x"
    )


def test_classify_gemini_errors_are_explicit() -> None:
    class Fake:
        def __init__(self, code: int, status: str, message: str) -> None:
            self.code, self.status, self.message = code, status, message

        def __str__(self) -> str:
            return self.message

    assert "API key" in str(classify_gemini_api_error(Fake(401, "UNAUTHENTICATED", "bad key")))
    assert "quota" in str(
        classify_gemini_api_error(Fake(429, "RESOURCE_EXHAUSTED", "quota exceeded"))
    ).lower()
    soft = Fake(429, "TOO_MANY_REQUESTS", "rate limit please retry")
    assert classify_gemini_api_error(soft) is soft


def test_factory_mock_and_missing_keys() -> None:
    assert isinstance(build_llm_client(Settings(llm_provider="mock")), MockLLM)
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        build_llm_client(Settings(llm_provider="gemini", gemini_api_key=""))
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        build_llm_client(Settings(llm_provider="anthropic", anthropic_api_key=""))
    with pytest.raises(LLMError, match="OPENAI_API_KEY"):
        build_llm_client(Settings(llm_provider="openai", openai_api_key=""))
    # Missing Gemini key must NOT silently return MockLLM
    with pytest.raises(LLMError):
        client = build_llm_client(Settings(llm_provider="gemini", gemini_api_key=""))
        assert not isinstance(client, MockLLM)
