"""Audit trail: every pipeline step, tool call, model output (with telemetry) and human action."""

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from app.db.enums import AuditActor
from app.db.models import AuditEvent

MAX_SUMMARY = 2000


class _HasTelemetry(Protocol):
    @property
    def model(self) -> str: ...
    @property
    def prompt_version(self) -> str: ...
    @property
    def tokens_in(self) -> int: ...
    @property
    def tokens_out(self) -> int: ...
    @property
    def cost_inr(self) -> float: ...
    @property
    def latency_ms(self) -> int: ...


@dataclass(frozen=True)
class Telemetry:
    """Aggregate telemetry for a whole pipeline run."""

    model: str
    prompt_version: str
    tokens_in: int
    tokens_out: int
    cost_inr: float
    latency_ms: int


def _clip(text: str | None) -> str | None:
    if text is None:
        return None
    return text if len(text) <= MAX_SUMMARY else text[: MAX_SUMMARY - 1] + "…"


class AuditLogger:
    """Appends :class:`AuditEvent` rows for one dispute. Summaries must contain masked data only."""

    def __init__(self, session: Session, dispute_id: int) -> None:
        self.session, self.dispute_id = session, dispute_id

    def log(
        self,
        step: str,
        actor: AuditActor,
        input_summary: str | None = None,
        output_summary: str | None = None,
        llm: _HasTelemetry | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            dispute_id=self.dispute_id,
            step=step,
            actor=actor,
            input_summary=_clip(input_summary),
            output_summary=_clip(output_summary),
        )
        if llm is not None:
            event.model, event.prompt_version = llm.model, llm.prompt_version
            event.tokens_in, event.tokens_out = llm.tokens_in, llm.tokens_out
            event.cost_inr, event.latency_ms = llm.cost_inr, llm.latency_ms  # type: ignore[assignment]
        self.session.add(event)
        self.session.flush()
        return event
