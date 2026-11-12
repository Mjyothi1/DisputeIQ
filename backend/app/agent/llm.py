
"""Provider-agnostic LLM client.

Every call returns a validated Pydantic object plus telemetry.
Transient API errors are retried with exponential backoff.
Invalid structured output is retried once with a corrective note.

Providers: Gemini, Anthropic, OpenAI, and explicitly selected Mock.
Real providers never silently fall back to Mock.
"""

import logging
import random
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar

try:
    from anthropic.types import ToolUseBlock as _ToolUseBlock
except ImportError:
    _ToolUseBlock = None  # type: ignore[assignment,misc]

from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.services.tracing import get_tracer

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


PRICING: dict[str, tuple[float, float]] = {
    "gemini-": (0.0, 0.0),
    "claude-sonnet": (3.0, 15.0),
    "claude-haiku": (1.0, 5.0),
    "claude-opus": (15.0, 75.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.5, 10.0),
}

DEFAULT_PRICE = (3.0, 15.0)

DEFAULT_MODELS = {
    "gemini": Settings.model_fields["gemini_model"].default,  # one source of truth: config.py
    "anthropic": "claude-sonnet-5-5",
    "openai": "gpt-4o-mini",
    "mock": "mock-rules-v1",
}


class LLMError(RuntimeError):
    """The model could not produce a valid structured answer."""


@dataclass
class LLMResult(Generic[T]):
    parsed: T
    model: str
    prompt_version: str
    tokens_in: int
    tokens_out: int
    cost_inr: float
    latency_ms: int


class LLMClient(Protocol):
    model: str

    def structured(
        self,
        *,
        task: str,
        system: str,
        user: str,
        schema: type[T],
        prompt_version: str,
        payload: dict[str, Any] | None = None,
    ) -> LLMResult[T]:
        ...


def cost_inr(
    model: str,
    tokens_in: int,
    tokens_out: int,
    usd_inr: float,
) -> float:
    """Calculate estimated INR cost."""
    price = next(
        (
            price
            for prefix, price in PRICING.items()
            if model.startswith(prefix)
        ),
        DEFAULT_PRICE,
    )

    usd = (
        tokens_in / 1e6 * price[0]
        + tokens_out / 1e6 * price[1]
    )

    return round(usd * usd_inr, 6)


@dataclass
class RawResponse:
    data: dict[str, Any] | BaseModel
    tokens_in: int
    tokens_out: int


class _Backend(Protocol):
    def call(
        self,
        system: str,
        user: str,
        schema: type[BaseModel],
    ) -> RawResponse:
        ...


class RetryingClient:
    """Wraps a backend with retries, validation and telemetry."""

    def __init__(
        self,
        backend: _Backend,
        model: str,
        usd_inr: float,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self.retry_events: list[str] = []
        self._jitter = jitter
        self.backend = backend
        self.model = model
        self.usd_inr = usd_inr
        self.max_retries = max_retries
        self._sleep = sleep

    def structured(
        self,
        *,
        task: str,
        system: str,
        user: str,
        schema: type[T],
        prompt_version: str,
        payload: dict[str, Any] | None = None,
    ) -> LLMResult[T]:
        start = time.perf_counter()

        tokens_in = 0
        tokens_out = 0
        correction_note = ""

        # Original request plus one corrective output retry.
        for _ in range(2):
            raw = self._call_with_backoff(
                system,
                user + correction_note,
                schema,
                task,
            )

            tokens_in += raw.tokens_in
            tokens_out += raw.tokens_out

            try:
                if isinstance(raw.data, schema):
                    parsed = raw.data
                else:
                    parsed = schema.model_validate(raw.data)

            except ValidationError as exc:
                logger.warning(
                    "Invalid structured output",
                    extra={
                        "task": task,
                        "error": str(exc)[:300],
                    },
                )

                correction_note = (
                    "\n\nYour previous reply failed schema validation. "
                    "Return valid output only."
                )
                continue

            result = LLMResult(
                parsed=parsed,
                model=self.model,
                prompt_version=prompt_version,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_inr=cost_inr(
                    self.model,
                    tokens_in,
                    tokens_out,
                    self.usd_inr,
                ),
                latency_ms=int(
                    (time.perf_counter() - start) * 1000
                ),
            )

            get_tracer().generation(
                name=task,
                model=self.model,
                prompt_version=prompt_version,
                input_text=user,
                output=parsed.model_dump(mode="json"),
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_inr=result.cost_inr,
                latency_ms=result.latency_ms,
            )

            return result

        raise LLMError(
            f"{task}: model output failed schema validation twice"
        )

    def _call_with_backoff(
        self,
        system: str,
        user: str,
        schema: type[BaseModel],
        task: str,
    ) -> RawResponse:
        last: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return self.backend.call(system, user, schema)
            except LLMError:
                raise
            except Exception as exc:
                last = exc
                kind, retry_after, code = classify_failure(exc)
                message = str(exc)

                if kind == "auth":
                    raise LLMError(
                        f"{task}: LLM credentials rejected (HTTP {code}): {message[:200]}"
                    ) from exc
                if kind == "hard_quota":
                    raise LLMError(
                        f"{task}: API quota exhausted (not retried): {message[:200]}"
                    ) from exc
                if kind == "permanent":
                    raise LLMError(
                        f"{task}: permanent API error (HTTP {code}): {message[:200]}"
                    ) from exc

                if attempt >= self.max_retries:
                    break

                delay = self._delay(attempt, retry_after)
                if delay is None:
                    raise LLMError(
                        f"{task}: rate limited; provider asked to wait {retry_after:.0f}s "
                        f"(> {MAX_RETRY_WAIT_S:.0f}s cap), not waiting: {message[:200]}"
                    ) from exc

                self.retry_events.append(
                    f"{task}: transient error (HTTP {code}); retry {attempt + 1}/"
                    f"{self.max_retries} in {delay:.1f}s"
                    + (f" (provider retry-after {retry_after:.0f}s)" if retry_after else "")
                )
                logger.warning(
                    "Transient LLM error; retrying",
                    extra={"task": task, "attempt": attempt + 1, "delay_s": delay,
                           "http_code": code, "error": message[:300]},
                )
                self._sleep(delay)

        raise LLMError(
            f"{task}: LLM call failed after {self.max_retries + 1} attempts "
            f"(transient errors persisted): {str(last)[:300]}"
        ) from last

    def _delay(self, attempt: int, retry_after: float | None) -> float | None:
        """Backoff seconds (exponential + jitter, honouring retry-after); None = too long."""
        base = min(2.0**attempt, 20.0)
        if retry_after is not None:
            if retry_after > MAX_RETRY_WAIT_S:
                return None
            base = max(base, retry_after)
        return base * (1.0 + self._jitter() * 0.25)

    def drain_events(self) -> list[str]:
        """Retry notes since the last call (the pipeline writes them to the audit trail)."""
        events, self.retry_events = self.retry_events, []
        return events


def _gemini_usage(resp: Any) -> tuple[int, int]:
    """Extract Gemini token usage."""
    metadata = getattr(resp, "usage_metadata", None)

    if metadata is None:
        return 0, 0

    tokens_in = int(
        getattr(metadata, "prompt_token_count", None) or 0
    )

    tokens_out = int(
        getattr(metadata, "candidates_token_count", None)
        or getattr(metadata, "response_token_count", None)
        or 0
    )

    return tokens_in, tokens_out


MAX_RETRY_WAIT_S = 30.0
_HARD_QUOTA_MARKERS = ("perday", "per day", "daily", "limit: 0", "limit:0", "billing")
_AUTH_MARKERS = ("api key", "api_key_invalid", "permission_denied", "unauthenticated")


def _error_blob(exc: BaseException) -> str:
    parts = [
        str(getattr(exc, "status", "") or ""),
        str(getattr(exc, "message", "") or ""),
        str(exc),
        str(getattr(exc, "details", "") or ""),
    ]
    return " ".join(parts).lower()


def _error_code(exc: BaseException) -> int | None:
    for attr in ("code", "status_code"):
        v = getattr(exc, attr, None)
        if isinstance(v, int):
            return v
    return None


def _retry_after_seconds(exc: BaseException, blob: str) -> float | None:
    """Provider hint: ``retryDelay: 34s`` / "retry in 34.5s" / a Retry-After header."""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers:
        try:
            v = headers.get("retry-after")
            if v is not None:
                return float(v)
        except (TypeError, ValueError):
            pass
    m = re.search(r"retry(?:delay)?\W{1,6}(?:in\s+)?(\d+(?:\.\d+)?)\s*s", blob)
    return float(m.group(1)) if m else None


def classify_failure(exc: BaseException) -> tuple[str, float | None, int | None]:
    """Return ``(kind, retry_after_s, http_code)``.

    kind: ``transient`` (retry, bounded) | ``hard_quota`` | ``auth`` | ``permanent``.
    A 429 / RESOURCE_EXHAUSTED is transient unless it names a daily/billing quota.
    """
    code = _error_code(exc)
    blob = _error_blob(exc)
    if code in (401, 403) or any(k in blob for k in _AUTH_MARKERS):
        return "auth", None, code
    if code == 429 or "resource_exhausted" in blob:
        if any(k in blob for k in _HARD_QUOTA_MARKERS):
            return "hard_quota", None, code
        return "transient", _retry_after_seconds(exc, blob), code
    if isinstance(code, int) and code >= 500:
        return "transient", _retry_after_seconds(exc, blob), code
    if code is None and ("unavailable" in blob or "deadline_exceeded" in blob):
        return "transient", None, code
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return "transient", None, code
    if isinstance(code, int) and 400 <= code < 500:
        return "permanent", None, code
    return "permanent", None, code


def classify_gemini_api_error(exc: BaseException) -> Exception:
    """Map a Gemini SDK error: hard failures become :class:`LLMError`; transient ones pass
    through unchanged so :class:`RetryingClient` can retry them."""
    kind, _, code = classify_failure(exc)
    if kind == "auth":
        return LLMError(
            "Gemini API key is missing, invalid, or not authorised. "
            "Check GEMINI_API_KEY in the backend environment."
        )
    if kind == "hard_quota":
        return LLMError(
            "Gemini daily/billing quota exhausted. Check your Google AI Studio quota. "
            "No mock fallback was used."
        )
    if kind == "permanent":
        return LLMError(f"Gemini API error {code}: {str(exc)[:300]}")
    return exc  # type: ignore[return-value]


class GeminiBackend:
    """Structured JSON generation using the official google-genai SDK."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_s: float,
        max_output_tokens: int = 2048,
    ) -> None:
        from google import genai
        from google.genai import types

        self._types = types

        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(timeout_s * 1000)
            ),
        )

        self.model = model
        self.max_output_tokens = max_output_tokens

    def call(
        self,
        system: str,
        user: str,
        schema: type[BaseModel],
    ) -> RawResponse:
        from google.genai import errors as genai_errors

        # Gemini 3 models use thinking_level rather than
        # the older thinking_budget configuration.
        thinking = self._types.ThinkingConfig(
            thinking_level="low"
        )

        config = self._types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            max_output_tokens=self.max_output_tokens,
            response_mime_type="application/json",
            response_schema=schema,
            thinking_config=thinking,
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=user,
                config=config,
            )

        except genai_errors.APIError as exc:
            mapped = classify_gemini_api_error(exc)

            logger.warning(
                "Gemini API request failed: HTTP %s, status=%s, error=%s",
                getattr(exc, "code", None),
                getattr(exc, "status", None),
                str(exc)[:300],
            )

            if mapped is exc:
                raise
            raise mapped from exc

        except TimeoutError as exc:
            raise TimeoutError(
                "Gemini request timed out"
            ) from exc

        except OSError as exc:
            raise ConnectionError(
                f"Gemini network error: {exc}"
            ) from exc

        tokens_in, tokens_out = _gemini_usage(response)

        parsed = getattr(response, "parsed", None)

        if parsed is not None:
            if isinstance(parsed, schema):
                return RawResponse(
                    parsed,
                    tokens_in,
                    tokens_out,
                )

            if isinstance(parsed, BaseModel):
                return RawResponse(
                    parsed.model_dump(),
                    tokens_in,
                    tokens_out,
                )

            if isinstance(parsed, dict):
                return RawResponse(
                    parsed,
                    tokens_in,
                    tokens_out,
                )

        response_text = (
            getattr(response, "text", None) or ""
        ).strip()

        if not response_text:
            raise LLMError(
                "Gemini returned empty content "
                "(no structured JSON)"
            )

        try:
            return RawResponse(
                schema.model_validate_json(response_text),
                tokens_in,
                tokens_out,
            )

        except ValidationError:
            import json

            try:
                return RawResponse(
                    json.loads(response_text),
                    tokens_in,
                    tokens_out,
                )

            except json.JSONDecodeError as exc:
                raise LLMError(
                    "Gemini returned non-JSON content"
                ) from exc


class AnthropicBackend:
    """Structured output using an Anthropic tool call."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float,
        max_tokens: int = 2048,
    ) -> None:
        import anthropic

        self.client = anthropic.Anthropic(
            api_key=api_key,
            timeout=timeout,
            max_retries=0,
        )

        self.model = model
        self.max_tokens = max_tokens

    def call(
        self,
        system: str,
        user: str,
        schema: type[BaseModel],
    ) -> RawResponse:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": user,
                }
            ],
            tools=[
                {
                    "name": "emit",
                    "description": "Return the structured result.",
                    "input_schema": schema.model_json_schema(),
                }
            ],
            tool_choice={
                "type": "tool",
                "name": "emit",
            },
        )

        data: dict[str, Any] = {}

        for block in response.content:
            if (
                _ToolUseBlock is not None
                and isinstance(block, _ToolUseBlock)
            ):
                data = (
                    dict(block.input)
                    if isinstance(block.input, dict)
                    else {}
                )
                break

        return RawResponse(
            data,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )


class OpenAIBackend:
    """Structured output using OpenAI's Pydantic response format."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float,
    ) -> None:
        import openai

        self.client = openai.OpenAI(
            api_key=api_key,
            timeout=timeout,
            max_retries=0,
        )

        self.model = model

    def call(
        self,
        system: str,
        user: str,
        schema: type[BaseModel],
    ) -> RawResponse:
        response = self.client.beta.chat.completions.parse(
            model=self.model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": system,
                },
                {
                    "role": "user",
                    "content": user,
                },
            ],
            response_format=schema,
        )

        parsed = response.choices[0].message.parsed

        if parsed is None:
            raise LLMError(
                "Model refused or returned no parsable output"
            )

        usage = response.usage

        return RawResponse(
            parsed,
            usage.prompt_tokens if usage else 0,
            usage.completion_tokens if usage else 0,
        )


def resolve_model(settings: Settings) -> str:
    """Resolve the configured model."""

    if settings.llm_model.strip():
        return settings.llm_model.strip()

    if settings.llm_provider == "gemini":
        return (
            settings.gemini_model
            or DEFAULT_MODELS["gemini"]
        ).strip()

    return DEFAULT_MODELS[settings.llm_provider]


def build_llm_client(
    settings: Settings,
    merchant_names: Sequence[str] = (),
    sleep: Callable[[float], None] = time.sleep,
) -> LLMClient:
    """Build the configured LLM client.

    Real providers never silently fall back to Mock.
    """

    provider = settings.llm_provider
    model = resolve_model(settings)

    if provider == "mock":
        from app.agent.mock_llm import MockLLM

        return MockLLM(merchant_names)

    if provider == "gemini":
        if not settings.gemini_api_key.strip():
            raise LLMError(
                "LLM_PROVIDER=gemini but GEMINI_API_KEY is empty. "
                "Set the key in the backend environment."
            )

        backend: _Backend = GeminiBackend(
            settings.gemini_api_key.strip(),
            model,
            settings.llm_timeout_s,
        )

    elif provider == "anthropic":
        if not settings.anthropic_api_key:
            raise LLMError(
                "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is empty"
            )

        backend = AnthropicBackend(
            settings.anthropic_api_key,
            model,
            settings.llm_timeout_s,
        )

    elif provider == "openai":
        if not settings.openai_api_key:
            raise LLMError(
                "LLM_PROVIDER=openai but OPENAI_API_KEY is empty"
            )

        backend = OpenAIBackend(
            settings.openai_api_key,
            model,
            settings.llm_timeout_s,
        )

    else:
        raise LLMError(
            f"Unsupported LLM_PROVIDER={provider!r}"
        )

    return RetryingClient(
        backend,
        model,
        settings.usd_inr,
        settings.llm_max_retries,
        sleep,
    )
