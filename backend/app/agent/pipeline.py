"""LangGraph dispute pipeline.

Nodes (in order): mask_pii -> intake_extract -> match_transaction -> run_evidence_checks ->
classify_reason_code -> eligibility_engine -> recommend -> draft_documents -> route.

The LLM is used for extraction, classification, explanation and prose only. Matching, evidence,
eligibility, deadlines, the recommendation itself and routing are deterministic code. The agent
never reads ``disputes.ground_truth`` (enforced by a test).
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.agent import documents as docs
from app.agent import prompts
from app.agent.llm import LLMClient, LLMError, LLMResult, build_llm_client
from app.agent.schemas import (
    ClaimExtraction,
    DraftedText,
    RationaleOutput,
    ReasonClassification,
)
from app.core.config import Settings, get_settings
from app.core.timeutil import as_utc
from app.db import models
from app.db.enums import AuditActor, DisputeStatus, Recommendation
from app.rules.config import RulesConfig, get_rules_config
from app.rules.eligibility import EligibilityResult, check_eligibility
from app.rules.policy import (
    CONF_NEED_INFO,
    PolicyDecision,
    baseline_recommendation,
    confidence_cap_for_match,
    enforce_consistency,
    evidence_verdict,
)
from app.rules.routing import RouteDecision, route
from app.rules.types import Blocker, EvidenceItem, RouteTarget
from app.services.audit import AuditLogger, Telemetry
from app.services.embeddings import build_embedder
from app.services.injection import detect_injection
from app.services.pii import mask_pii
from app.services.retrieval import NullRetriever, PgVectorRetriever, Retriever
from app.services.tracing import configure_tracing, get_tracer
from app.tools.evidence import run_all_checks
from app.tools.matching import ClaimFacts, match_transaction

logger = logging.getLogger(__name__)
TOP_K_SIMILAR = 3


_MONTHS = {
    name.lower(): number
    for number, names in enumerate(
        [
            ("January", "Jan"), ("February", "Feb"), ("March", "Mar"),
            ("April", "Apr"), ("May",), ("June", "Jun"),
            ("July", "Jul"), ("August", "Aug"), ("September", "Sep"),
            ("October", "Oct"), ("November", "Nov"), ("December", "Dec"),
        ],
        start=1,
    )
    for name in names
}




def _recover_extraction_facts(text: str, extraction: ClaimExtraction) -> ClaimExtraction:
    """Recover explicit facts omitted by the LLM without overwriting valid values."""
    recovered: dict[str, Any] = {}

    if extraction.claimed_amount is None:
        for match in re.finditer(r"(\d[\d,]*(?:\.\d{1,2})?)", text):
            prefix = text[max(0, match.start() - 12):match.start()]
            has_currency = (
                chr(8377) in prefix
                or re.search(r"\bINR\b|\bRs\.?\s*$", prefix, re.IGNORECASE) is not None
            )
            if has_currency:
                recovered["claimed_amount"] = float(match.group(1).replace(",", ""))
                break

    if extraction.approx_day is None or extraction.approx_month is None:
        months = {
            "jan": 1, "january": 1, "feb": 2, "february": 2,
            "mar": 3, "march": 3, "apr": 4, "april": 4,
            "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
            "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
            "oct": 10, "october": 10, "nov": 11, "november": 11,
            "dec": 12, "december": 12,
        }
        word_date = re.search(
            r"\b(?P<day>\d{1,2})\s+"
            r"(?P<month>January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
            r"(?:,?\s+(?P<year>\d{4}))?\b",
            text, re.IGNORECASE,
        )
        numeric_date = re.search(
            r"\b(?P<day>\d{1,2})[/-](?P<month>\d{1,2})(?:[/-](?P<year>\d{4}))?\b",
            text,
        )

        day = month = year = None
        if word_date:
            day = int(word_date.group("day"))
            month = months[word_date.group("month").lower()]
            year = word_date.group("year")
        elif numeric_date:
            day = int(numeric_date.group("day"))
            month = int(numeric_date.group("month"))
            year = numeric_date.group("year")

        if day is not None and month is not None and 1 <= day <= 31 and 1 <= month <= 12:
            if extraction.approx_day is None:
                recovered["approx_day"] = day
            if extraction.approx_month is None:
                recovered["approx_month"] = month
            if extraction.approx_year is None and year:
                recovered["approx_year"] = int(year)

    if extraction.merchant_hint is None:
        merchant = re.search(
            r"\bat\s+([A-Za-z0-9][A-Za-z0-9 &'()/.-]{1,79}?)"
            r"(?=\s+on\b|[,.;\n]|$)",
            text, re.IGNORECASE,
        )
        if merchant:
            recovered["merchant_hint"] = merchant.group(1).strip()

    return extraction.model_copy(update=recovered) if recovered else extraction


class AgentState(TypedDict, total=False):
    dispute_id: int
    as_of: datetime
    masked_text: str
    extraction: ClaimExtraction
    injection_flags: list[str]
    txn_id: int | None
    match_score: float | None
    match_ambiguous: bool
    evidence: list[EvidenceItem]
    similar: list[dict[str, Any]]
    classification: ReasonClassification | None
    reason_code: str | None
    eligibility: EligibilityResult
    policy: PolicyDecision | None
    recommendation: Recommendation
    confidence: float
    rationale: str
    cited_evidence: list[str]
    friendly_fraud: bool
    letter: str
    filing: str | None
    route_decision: RouteDecision
    needs_human_reasons: list[str]
    model_names: list[str]


@dataclass
class ProcessResult:
    dispute_id: int
    status: DisputeStatus
    recommendation: Recommendation | None = None
    confidence: float | None = None
    reason_code: str | None = None
    friendly_fraud: bool = False
    injection_suspected: bool = False
    matched_txn_id: int | None = None
    route_reasons: list[str] = field(default_factory=list)
    llm_cost_inr: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    error: str | None = None


def evidence_dicts(
    evidence: list[EvidenceItem], code: str | None = None, cfg: RulesConfig | None = None
) -> list[dict[str, Any]]:
    """Evidence as prompt/audit dicts; with a reason code each item also carries its verdict."""
    out = []
    for e in evidence:
        d: dict[str, Any] = {
            "check_name": e.check_name.value,
            "finding": e.finding.value,
            "summary": e.summary,
            "details": e.details,
        }
        if code:
            d["verdict"] = evidence_verdict(code, e, cfg)
        out.append(d)
    return out


class Pipeline:
    """Holds dependencies and exposes the compiled LangGraph."""

    def __init__(
        self,
        session: Session,
        llm: LLMClient,
        retriever: Retriever | None = None,
        config: RulesConfig | None = None,
    ) -> None:
        self.session, self.llm = session, llm
        self.retriever = retriever or NullRetriever()
        self.cfg = config or get_rules_config()
        self.graph = self._build_graph()
        self._cost = 0.0
        self._tin = self._tout = self._latency = 0

    # ---- plumbing -------------------------------------------------------------------------
    def _build_graph(self) -> Any:
        g = StateGraph(AgentState)
        order = [
            ("mask_pii", self.mask_pii),
            ("intake_extract", self.intake_extract),
            ("match_transaction", self.match_transaction),
            ("run_evidence_checks", self.run_evidence_checks),
            ("classify_reason_code", self.classify_reason_code),
            ("eligibility_engine", self.eligibility_engine),
            ("recommend", self.recommend),
            ("draft_documents", self.draft_documents),
            ("route", self.route_case),
        ]
        for name, fn in order:
            g.add_node(name, fn)
        g.add_edge(START, order[0][0])
        for (a, _), (b, _) in zip(order, order[1:], strict=False):
            g.add_edge(a, b)
        g.add_edge(order[-1][0], END)
        return g.compile()

    def _audit(self, state: AgentState) -> AuditLogger:
        return AuditLogger(self.session, state["dispute_id"])

    def _track(self, res: LLMResult[Any]) -> None:
        self._cost += res.cost_inr
        self._tin += res.tokens_in
        self._tout += res.tokens_out
        self._latency += res.latency_ms

    def _dispute(self, state: AgentState) -> models.Dispute:
        d = self.session.get(models.Dispute, state["dispute_id"])
        assert d is not None
        return d

    def _flag(self, state: AgentState, reason: str) -> list[str]:
        return [*state.get("needs_human_reasons", []), reason]

    # ---- 1. mask_pii ----------------------------------------------------------------------
    def mask_pii(self, state: AgentState) -> dict[str, Any]:
        d = self._dispute(state)
        res = mask_pii(d.raw_text)
        d.masked_text = res.text
        self._audit(state).log(
            "mask_pii", AuditActor.TOOL, f"{len(d.raw_text)} characters of raw complaint",
            f"Masked {res.total} item(s): {res.counts or 'none'}",
        )  # fmt: skip
        return {"masked_text": res.text}

    # ---- 2. intake_extract ----------------------------------------------------------------
    def intake_extract(self, state: AgentState) -> dict[str, Any]:
        d, text = self._dispute(state), state["masked_text"]
        flags = detect_injection(text)
        update: dict[str, Any] = {}
        try:
            res = self.llm.structured(
                task="extract_claim",
                system=prompts.EXTRACT_SYSTEM,
                user=prompts.extract_user(text, d.channel.value),
                schema=ClaimExtraction,
                prompt_version=prompts.PROMPT_VERSION,
                payload={"masked_text": text, "channel": d.channel.value},
            )
            self._track(res)
            extraction, telemetry = res.parsed, res
        except LLMError as exc:
            logger.error("extraction failed: %s", exc)
            extraction = ClaimExtraction(claim_type="OTHER", summary="Extraction failed")
            telemetry = None
            update["needs_human_reasons"] = self._flag(state, "Claim extraction failed.")
        extraction = _recover_extraction_facts(text, extraction)
        if flags and not extraction.injection_suspected:
            extraction = extraction.model_copy(update={"injection_suspected": True})
        d.extracted_fields = {**extraction.model_dump(), "injection_patterns": flags}
        self._audit(state).log(
            "intake_extract", AuditActor.AGENT, "Masked complaint (treated as data)",
            json.dumps(d.extracted_fields, default=str), llm=telemetry,
        )  # fmt: skip
        return {**update, "extraction": extraction, "injection_flags": flags}

    # ---- 3. match_transaction -------------------------------------------------------------
    def match_transaction(self, state: AgentState) -> dict[str, Any]:
        d, x = self._dispute(state), state["extraction"]
        facts = ClaimFacts(
            x.claimed_amount,
            x.merchant_hint,
            x.approx_day,
            x.approx_month,
            x.approx_year,
            x.card_last4,
        )
        m = match_transaction(self.session, d.customer_id, facts, state["as_of"], self.cfg)
        d.matched_txn_id = m.txn.id if m.txn else None
        self._audit(state).log(
            "match_transaction", AuditActor.TOOL,
            f"claimed={x.claimed_amount}, merchant={x.merchant_hint}, date={x.approx_day}/{x.approx_month}, card={x.card_last4}",
            f"{'Matched txn ' + str(m.txn.id) if m.txn else 'No match'} "
            f"(score {m.score}, ambiguous={m.ambiguous}); top candidates: {json.dumps(m.candidates)}",
        )  # fmt: skip
        return {"txn_id": m.txn.id if m.txn else None, "match_score": m.score if m.txn else None,
                "match_ambiguous": m.ambiguous}  # fmt: skip

    # ---- 4. run_evidence_checks -----------------------------------------------------------
    def run_evidence_checks(self, state: AgentState) -> dict[str, Any]:
        d, x = self._dispute(state), state["extraction"]
        if state.get("txn_id") is None:
            self._audit(state).log(
                "run_evidence_checks", AuditActor.TOOL, "No matched transaction", "Skipped"
            )
            return {"evidence": []}
        txn = self.session.get(models.Transaction, state["txn_id"])
        assert txn is not None
        expected = Decimal(str(x.expected_amount)) if x.expected_amount is not None else None
        items = run_all_checks(self.session, d, txn, state["as_of"], expected, self.cfg)
        self._audit(state).log(
            "run_evidence_checks", AuditActor.TOOL, f"Transaction {txn.id}",
            "; ".join(f"{i.check_name.value}={i.finding.value}" for i in items),
        )  # fmt: skip
        return {"evidence": items}

    # ---- 5. classify_reason_code ----------------------------------------------------------
    def classify_reason_code(self, state: AgentState) -> dict[str, Any]:
        d, x, ev = self._dispute(state), state["extraction"], state.get("evidence", [])
        similar = [
            c.as_prompt_dict()
            for c in self.retriever.top_k(
                state["masked_text"], TOP_K_SIMILAR, exclude_dispute_id=d.id
            )
        ]
        ev_d = evidence_dicts(ev)
        update: dict[str, Any] = {"similar": similar}
        try:
            res = self.llm.structured(
                task="classify_reason",
                system=prompts.CLASSIFY_SYSTEM,
                user=prompts.classify_user(
                    self.cfg, state["masked_text"], x.model_dump(), ev_d, similar
                ),
                schema=ReasonClassification,
                prompt_version=prompts.PROMPT_VERSION,
                payload={"extraction": x.model_dump(), "evidence": ev_d, "similar": similar},
            )
            self._track(res)
            cls = res.parsed
            if cls.code not in self.cfg.reason_codes:  # defensive: schema already restricts this
                raise LLMError(f"unknown reason code {cls.code}")
            d.reason_code, d.confidence = cls.code, cls.confidence
            out = f"{cls.code} (confidence {cls.confidence:.2f}): {cls.justification}"
            update |= {"classification": cls, "reason_code": cls.code}
        except LLMError as exc:
            logger.error("classification failed: %s", exc)
            res, out = None, f"Classification failed: {exc}"
            update |= {"classification": None, "reason_code": None,
                       "needs_human_reasons": self._flag(state, "Reason-code classification failed.")}  # fmt: skip
        self._audit(state).log(
            "classify_reason_code", AuditActor.AGENT,
            f"Claim type {x.claim_type}; {len(ev)} evidence items; similar cases {[s['case_id'] for s in similar]}",
            out, llm=res,
        )  # fmt: skip
        return update

    # ---- 6. eligibility_engine ------------------------------------------------------------
    def eligibility_engine(self, state: AgentState) -> dict[str, Any]:
        d, code, ev = self._dispute(state), state.get("reason_code"), state.get("evidence", [])
        txn = self.session.get(models.Transaction, state["txn_id"]) if state.get("txn_id") else None
        if code is None:
            el = EligibilityResult(
                False,
                None,
                None,
                [Blocker.EVIDENCE_MISSING],
                ["Reason code could not be determined."],
            )
        else:
            el = check_eligibility(
                code, txn.txn_time if txn else None, ev, state["as_of"], self.cfg
            )
        d.deadline_at = el.deadline_at
        for item in ev:  # persist evidence with a verdict relative to the reason code
            verdict = evidence_verdict(code, item, self.cfg) if code else "INFO"
            self.session.add(
                models.Evidence(
                    dispute_id=d.id,
                    check_name=item.check_name.value,
                    result=verdict,
                    details={
                        "finding": item.finding.value,
                        "summary": item.summary,
                        **item.details,
                    },
                )  # fmt: skip
            )
        self._audit(state).log(
            "eligibility_engine", AuditActor.TOOL, f"Reason code {code}",
            f"eligible={el.eligible}; days_remaining={el.days_remaining}; blockers={[b.value for b in el.blockers]}; "
            f"{'; '.join(el.reasons)}",
        )  # fmt: skip
        return {"eligibility": el}

    # ---- 7. recommend ---------------------------------------------------------------------
    def recommend(self, state: AgentState) -> dict[str, Any]:
        d, code, el = self._dispute(state), state.get("reason_code"), state["eligibility"]
        ev, cls = state.get("evidence", []), state.get("classification")
        flags = state.get("needs_human_reasons", [])
        notes: list[str]
        if code is None:
            rec, policy, notes = Recommendation.NEED_MORE_INFO, None, ["Reason code undetermined."]
            conf, friendly = 0.3, False
        else:
            policy = baseline_recommendation(code, el, ev, state.get("match_score"))
            rec, extra = enforce_consistency(policy.recommendation, el)
            notes = [*policy.reasons, *extra]
            if state.get("match_ambiguous"):
                notes.append("Transaction match is ambiguous.")
            conf = min(
                policy.max_confidence,
                cls.confidence if cls else 1.0,
                confidence_cap_for_match(
                    state.get("match_score"), state.get("match_ambiguous", False)
                ),
            )
            if rec is Recommendation.NEED_MORE_INFO:
                conf = min(conf, CONF_NEED_INFO)
            friendly = policy.friendly_fraud and rec is Recommendation.REJECT

        decision = {
            "recommendation": rec.value, "reason_code": code, "friendly_fraud": friendly,
            "policy_notes": notes, "evidence": evidence_dicts(ev, code, self.cfg),
            "classification_confidence": cls.confidence if cls else None,
            "eligibility": {"eligible": el.eligible, "days_remaining": el.days_remaining,
                            "reasons": el.reasons},
        }  # fmt: skip
        rationale, cited, telemetry = self._explain(state, decision, notes, flags)
        if telemetry is not None:
            conf = min(conf, telemetry.parsed.confidence)
        d.confidence = round(conf, 3)
        self._audit(state).log(
            "recommend", AuditActor.AGENT, f"Policy decision {rec.value}; cap inputs: match={state.get('match_score')}",
            f"{rec.value} @ {conf:.2f}; friendly_fraud={friendly}. {rationale}", llm=telemetry,
        )  # fmt: skip
        return {"recommendation": rec, "confidence": round(conf, 3), "rationale": rationale,
                "cited_evidence": cited, "friendly_fraud": friendly, "policy": policy,
                "needs_human_reasons": flags}  # fmt: skip

    def _explain(
        self, state: AgentState, decision: dict[str, Any], notes: list[str], flags: list[str]
    ) -> tuple[str, list[str], LLMResult[RationaleOutput] | None]:
        known = {e["check_name"] for e in decision["evidence"]}
        try:
            res = self.llm.structured(
                task="write_rationale",
                system=prompts.RATIONALE_SYSTEM,
                user=prompts.rationale_user(decision),
                schema=RationaleOutput,
                prompt_version=prompts.PROMPT_VERSION,
                payload=decision,
            )
            self._track(res)
            cited = [c for c in res.parsed.cited_evidence if c in known]
            return res.parsed.rationale, cited, res
        except LLMError as exc:
            logger.error("rationale generation failed: %s", exc)
            flags.append("Rationale generation failed; deterministic explanation used.")
            text = f"{decision['recommendation']} for {decision['reason_code']}. " + " ".join(notes)
            return text, [], None

    # ---- 8. draft_documents ---------------------------------------------------------------
    def _facts(self, state: AgentState) -> docs.DocFacts:
        d = self._dispute(state)
        txn = self.session.get(models.Transaction, state["txn_id"]) if state.get("txn_id") else None
        el = state["eligibility"]
        tbc = "(to be confirmed)"
        return docs.DocFacts(
            case_id=docs.case_ref(d.id), customer_name=d.customer.name,
            merchant=txn.merchant.name if txn else tbc,
            amount=docs.format_inr(txn.amount) if txn else tbc,
            txn_date=docs.format_date(txn.txn_time) if txn else tbc,
            deadline=docs.format_date(el.deadline_at) if el.deadline_at else "N/A",
            received=docs.format_date(state["as_of"]),
            card_last4=txn.card.last4 if txn else "----",
            network=txn.card.network.value if txn else "-",
            txn_ref=f"TXN-{txn.id}" if txn else "-",
            channel=txn.channel.value if txn else "-",
            auth_method=txn.auth_method.value if txn else "-",
            mcc=txn.merchant.mcc if txn else "-",
            has_txn=txn is not None,
        )  # fmt: skip

    def draft_documents(self, state: AgentState) -> dict[str, Any]:
        rec, code, ev = state["recommendation"], state.get("reason_code"), state.get("evidence", [])
        facts = self._facts(state)
        want_filing = rec is Recommendation.FILE_CHARGEBACK
        payload = {"recommendation": rec.value, "reason_code": code, "want_filing": want_filing,
                   "evidence_lines": docs.evidence_lines(ev)}  # fmt: skip
        problems: list[str] = []
        telemetry = None
        llm_body: str | None
        llm_narr: str | None
        try:
            res = self.llm.structured(
                task="draft_documents",
                system=prompts.DRAFT_SYSTEM,
                user=prompts.draft_user(payload, want_filing),
                schema=DraftedText,
                prompt_version=prompts.PROMPT_VERSION,
                payload=payload,
            )
            self._track(res)
            telemetry, llm_body, llm_narr = res, res.parsed.letter_body, res.parsed.filing_narrative
        except LLMError as exc:
            logger.error("drafting failed: %s", exc)
            llm_body = llm_narr = None
            problems.append("LLM drafting failed")
        body, p1 = docs.safe_body(llm_body, docs.FALLBACK_BODY[rec], facts)
        letter = docs.build_letter(facts, body)
        filing = None
        if want_filing and code:
            narrative, p2 = docs.safe_body(llm_narr, docs.FALLBACK_NARRATIVE, facts)
            filing = docs.build_filing(facts, code, ev, narrative)
            problems += [f"narrative: {p}" for p in p2 if p != "empty"]
        problems += [f"letter: {p}" for p in p1 if p != "empty"]
        out = "Letter drafted" + (" and chargeback filing drafted" if filing else "")
        if problems:
            out += f". Model text rejected ({', '.join(problems)}); deterministic template used."
        self._audit(state).log(
            "draft_documents", AuditActor.AGENT, f"Recommendation {rec.value}", out, llm=telemetry
        )
        return {"letter": letter, "filing": filing}

    # ---- 9. route -------------------------------------------------------------------------
    def route_case(self, state: AgentState) -> dict[str, Any]:
        d, el, rec = self._dispute(state), state["eligibility"], state["recommendation"]
        txn = self.session.get(models.Transaction, state["txn_id"]) if state.get("txn_id") else None
        policy = state.get("policy")
        rd = route(
            rec, state["confidence"], txn.amount if txn else None, state.get("reason_code"), el,
            friendly_fraud=state.get("friendly_fraud", False),
            frequent_disputer=bool(policy and policy.frequent_disputer),
            injection_suspected=state["extraction"].injection_suspected,
            needs_human_flag=bool(state.get("needs_human_reasons")),
            config=self.cfg,
        )  # fmt: skip
        auto = rd.target is RouteTarget.AUTO_RESOLVE
        d.status = DisputeStatus.AUTO_RESOLVED if auto else DisputeStatus.NEEDS_HUMAN
        self.session.add(
            models.Decision(
                dispute_id=d.id, recommendation=rec, rationale=state["rationale"],
                confidence=state["confidence"], friendly_fraud_flag=state.get("friendly_fraud", False),
                drafted_customer_letter=state["letter"], drafted_chargeback_filing=state.get("filing"),
                model=self.llm.model, prompt_version=prompts.PROMPT_VERSION,
            )
        )  # fmt: skip
        reasons = rd.reasons + list(state.get("needs_human_reasons", []))
        self._audit(state).log(
            "route", AuditActor.TOOL, f"{rec.value} @ {state['confidence']:.2f}",
            f"{d.status.value}" + (f" because: {' | '.join(reasons)}" if reasons else ": all auto-resolve conditions met"),
        )  # fmt: skip
        return {"route_decision": rd}

    # ---- entry point ----------------------------------------------------------------------
    def run(self, dispute_id: int) -> ProcessResult:
        """Process (or re-process) one dispute and commit. Never raises for pipeline faults."""
        start = time.perf_counter()
        self._cost, self._tin, self._tout, self._latency = 0.0, 0, 0, 0
        d = self.session.get(models.Dispute, dispute_id)
        if d is None:
            raise LookupError(f"dispute {dispute_id} not found")
        self.session.execute(
            delete(models.Evidence).where(models.Evidence.dispute_id == dispute_id)
        )
        d.status = DisputeStatus.PROCESSING
        self.session.flush()
        init: AgentState = {
            "dispute_id": dispute_id,
            "as_of": as_utc(d.created_at),
            "needs_human_reasons": [],
        }
        try:
            with get_tracer().span("dispute_pipeline", dispute_id=dispute_id):
                final: AgentState = self.graph.invoke(init)
        except Exception as exc:
            logger.exception("pipeline crashed", extra={"dispute_id": dispute_id})
            self.session.rollback()
            d = self.session.get(models.Dispute, dispute_id)
            assert d is not None
            d.status = DisputeStatus.NEEDS_HUMAN
            AuditLogger(self.session, dispute_id).log(
                "pipeline_error", AuditActor.TOOL, None, f"{type(exc).__name__}: {exc}"
            )
            self.session.commit()
            return ProcessResult(dispute_id, DisputeStatus.NEEDS_HUMAN, error=str(exc))
        latency = int((time.perf_counter() - start) * 1000)
        AuditLogger(self.session, dispute_id).log(
            "pipeline_complete", AuditActor.TOOL, None,
            f"{d.status.value}: {self._tin}+{self._tout} tokens, INR {self._cost:.4f}, {latency} ms",
            llm=Telemetry(self.llm.model, prompts.PROMPT_VERSION, self._tin, self._tout, round(self._cost, 4), latency),
        )  # fmt: skip
        self.session.commit()
        get_tracer().flush()
        return ProcessResult(
            dispute_id=dispute_id, status=d.status, recommendation=final["recommendation"],
            confidence=final["confidence"], reason_code=final.get("reason_code"),
            friendly_fraud=final.get("friendly_fraud", False),
            injection_suspected=final["extraction"].injection_suspected,
            matched_txn_id=final.get("txn_id"),
            route_reasons=final["route_decision"].reasons + final.get("needs_human_reasons", []),
            llm_cost_inr=round(self._cost, 4), tokens_in=self._tin, tokens_out=self._tout,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )  # fmt: skip


def build_pipeline(
    session: Session,
    settings: Settings | None = None,
    llm: LLMClient | None = None,
    retriever: Retriever | None = None,
    use_vector_memory: bool = True,
) -> Pipeline:
    """Assemble a pipeline from settings (provider, embeddings) unless parts are injected."""
    settings = settings or get_settings()
    configure_tracing(settings)
    if llm is None:
        names = list(session.scalars(select(models.Merchant.name)).all())
        llm = build_llm_client(settings, names)
    if retriever is None and use_vector_memory and session.get_bind().dialect.name == "postgresql":
        retriever = PgVectorRetriever(session, build_embedder(settings))
    return Pipeline(session, llm, retriever)
