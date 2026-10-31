"""Request/response models for the HTTP API. ``ground_truth`` and raw PII are never exposed."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.enums import (
    DisputeChannel,
    DisputeStatus,
    Recommendation,
    ReviewAction,
)
from app.rules.config import get_rules_config


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- requests -------------------------------------------------------------------------------
class DisputeCreate(BaseModel):
    customer_id: int
    channel: DisputeChannel = DisputeChannel.FORM
    raw_text: str = Field(min_length=5, max_length=5000, description="The customer's complaint.")


class ReviewIn(BaseModel):
    """An analyst action on a case.

    APPROVE  - accept the agent's recommendation as is.
    EDIT     - accept the recommendation but with edited letter and/or filing (one required).
    OVERRIDE - choose a different final decision (``final_decision`` and ``notes`` required).
    REJECT   - deny the customer's dispute (final decision REJECT).
    """

    analyst: str = Field(min_length=1, max_length=120)
    action: ReviewAction
    final_decision: Recommendation | None = None
    reason_code: str | None = Field(
        None, description="Corrected reason code, if the agent was wrong."
    )
    notes: str | None = Field(None, max_length=2000)
    edited_letter: str | None = Field(None, max_length=10000)
    edited_filing: str | None = Field(None, max_length=10000)

    @model_validator(mode="after")
    def _check(self) -> "ReviewIn":
        if self.action is ReviewAction.EDIT and not (self.edited_letter or self.edited_filing):
            raise ValueError("EDIT requires edited_letter and/or edited_filing")
        if self.action is ReviewAction.OVERRIDE and (not self.final_decision or not self.notes):
            raise ValueError("OVERRIDE requires final_decision and notes explaining why")
        if self.reason_code is not None and self.reason_code not in get_rules_config().reason_codes:
            raise ValueError(f"unknown reason_code {self.reason_code!r}")
        return self


# ---- responses ------------------------------------------------------------------------------
class DisputeSummary(BaseModel):
    id: int
    customer_name: str
    channel: DisputeChannel
    status: DisputeStatus
    reason_code: str | None
    confidence: float | None
    recommendation: Recommendation | None
    friendly_fraud: bool
    merchant: str | None
    amount: Decimal | None
    deadline_at: datetime | None
    days_to_deadline: int | None
    created_at: datetime


class DisputePage(BaseModel):
    items: list[DisputeSummary]
    total: int
    page: int
    page_size: int


class TransactionOut(ORM):
    id: int
    amount: Decimal
    currency: str
    txn_time: datetime
    channel: str
    auth_method: str
    status: str
    refund_status: str
    is_recurring: bool
    merchant_name: str
    merchant_category: str
    merchant_city: str | None
    card_last4: str
    card_network: str


class EvidenceOut(ORM):
    id: int
    check_name: str
    result: Literal["PASS", "FAIL", "INCONCLUSIVE", "INFO"]
    details: dict[str, Any] | None


class DecisionOut(ORM):
    id: int
    recommendation: Recommendation
    rationale: str
    confidence: float
    friendly_fraud_flag: bool
    drafted_customer_letter: str | None
    drafted_chargeback_filing: str | None
    model: str | None
    prompt_version: str | None
    created_at: datetime


class ReviewOut(ORM):
    id: int
    analyst: str
    action: ReviewAction
    final_decision: Recommendation
    notes: str | None
    edited_letter: str | None
    edited_filing: str | None
    created_at: datetime


class AuditEventOut(ORM):
    id: int
    step: str
    actor: str
    input_summary: str | None
    output_summary: str | None
    model: str | None
    prompt_version: str | None
    tokens_in: int | None
    tokens_out: int | None
    cost_inr: Decimal | None
    latency_ms: int | None
    timestamp: datetime


class CaseDetail(BaseModel):
    id: int
    status: DisputeStatus
    channel: DisputeChannel
    customer_name: str
    customer_segment: str
    complaint_masked: str | None
    extracted_fields: dict[str, Any] | None
    reason_code: str | None
    confidence: float | None
    deadline_at: datetime | None
    days_to_deadline: int | None
    created_at: datetime
    transaction: TransactionOut | None
    evidence: list[EvidenceOut]
    decision: DecisionOut | None
    reviews: list[ReviewOut]
    route_reasons: list[str]
    can_review: bool
    audit: list[AuditEventOut]


class ProcessAccepted(BaseModel):
    dispute_id: int
    status: DisputeStatus
    message: str


class CustomerOut(BaseModel):
    id: int
    name: str
    segment: str
    cards: list[str]  # e.g. "VISA ending 1234"


class RecentTxnOut(BaseModel):
    id: int
    merchant_name: str
    amount: Decimal
    txn_time: datetime
    card_last4: str


class ReasonCodeOut(BaseModel):
    code: str
    description: str
    window_days: int
    required_evidence: list[str]


class Metrics(BaseModel):
    cases_total: int
    cases_processed: int
    by_status: dict[str, int]
    auto_resolved: int
    auto_resolution_rate: float | None
    needs_human: int
    reviewed: int
    override_rate: float | None
    avg_processing_time_s: float | None
    avg_cost_inr: float | None
    total_cost_inr: float
    deadline_violations: int
    deadline_at_risk: int
    friendly_fraud_flagged: int
    injection_flagged: int
    by_reason_code: dict[str, int]
    by_recommendation: dict[str, int]
    llm_provider_note: str | None = None
    evaluation: dict[str, Any] | None = None


class PublicConfig(BaseModel):
    """Routing thresholds the UI shows next to confidence (single source: reason_codes.yaml)."""

    auto_confidence: float
    auto_max_amount_inr: float
    auto_resolve_codes: list[str]
    at_risk_days: int
    llm_provider: str
    llm_model: str
