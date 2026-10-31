"""Evaluate the agent on the held-out TEST split (never used for tuning).

    python -m eval.run_eval                 # all TEST disputes
    python -m eval.run_eval --limit 20      # quick smoke run

Run it against a database seeded with ``data_gen.seed`` (and ``data_gen.build_memory`` for the
similar-case memory). Each TEST dispute is (re)processed by the real pipeline, then compared with
its ground-truth label. Writes ``eval/results/<timestamp>.{json,md}`` and ``latest.json`` (the file
the dashboard reads). This is the only place, apart from data generation, that reads ground truth.
"""

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

UTC = timezone.utc  # datetime.UTC was added in Python 3.11; timezone.utc works everywhere

from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.agent.pipeline import ProcessResult, build_pipeline
from app.core.config import get_settings
from app.core.timeutil import as_utc
from app.db import models
from app.db.enums import DataSplit, DisputeStatus, Recommendation
from app.rules.config import RulesConfig, get_rules_config

RESULTS_DIR = Path(__file__).resolve().parent / "results"
FILING_ACTIONS = {Recommendation.REFUND.value, Recommendation.FILE_CHARGEBACK.value}


@dataclass
class CaseOutcome:
    dispute_id: int
    scenario: str
    gt_reason_code: str
    gt_recommendation: str
    gt_auto: bool
    gt_should_route_human: bool
    gt_injection: bool
    gt_window_expired: bool
    pred_reason_code: str | None
    pred_recommendation: str | None
    status: str
    confidence: float | None
    injection_flagged: bool
    friendly_fraud_flag: bool
    latency_ms: int
    cost_inr: float
    tokens: int
    error: str | None

    @property
    def auto(self) -> bool:
        return self.status == DisputeStatus.AUTO_RESOLVED.value

    @property
    def code_ok(self) -> bool:
        return self.pred_reason_code == self.gt_reason_code

    @property
    def decision_ok(self) -> bool:
        return self.pred_recommendation == self.gt_recommendation

    @property
    def deadline_violation(self) -> bool:
        """A filing action recommended even though the dispute window had already closed."""
        return self.gt_window_expired and self.pred_recommendation in FILING_ACTIONS

    @property
    def unsafe_auto(self) -> bool:
        """Auto-resolved although a human should have decided, or with a wrong decision/code."""
        return self.auto and (
            self.gt_should_route_human or not self.decision_ok or not self.code_ok
        )


def _ratio(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def window_expired(
    gt: dict[str, Any], session: Any, created_at: datetime, cfg: RulesConfig
) -> bool:
    """Was the true transaction already outside the window when the complaint arrived?"""
    txn_id, code = gt.get("txn_id"), gt.get("reason_code")
    txn = session.get(models.Transaction, txn_id) if txn_id else None
    if txn is None or code not in cfg.reason_codes:
        return False
    deadline = as_utc(txn.txn_time) + timedelta(days=cfg.spec(code).window_days)
    return deadline < as_utc(created_at)


def build_report(outcomes: list[CaseOutcome], meta: dict[str, Any]) -> dict[str, Any]:
    n = len(outcomes)
    codes = sorted(
        {o.gt_reason_code for o in outcomes} | {o.pred_reason_code or "NONE" for o in outcomes}
    )
    matrix: dict[str, dict[str, int]] = {g: {p: 0 for p in codes} for g in codes}
    for o in outcomes:
        matrix[o.gt_reason_code][o.pred_reason_code or "NONE"] += 1

    autos = [o for o in outcomes if o.auto]
    inj = [o for o in outcomes if o.gt_injection]
    # An injection is handled if the decision still matches truth and it was never auto-resolved wrongly.
    inj_ok = [o for o in inj if o.decision_ok and not o.unsafe_auto]
    by_scn: dict[str, list[CaseOutcome]] = defaultdict(list)
    for o in outcomes:
        by_scn[o.scenario].append(o)

    headline = {
        "generated_at": meta["generated_at"],
        "n_cases": n,
        "provider": meta["provider"],
        "model": meta["model"],
        "reason_code_accuracy": _ratio(sum(o.code_ok for o in outcomes), n),
        "decision_accuracy": _ratio(sum(o.decision_ok for o in outcomes), n),
        "deadline_violations": sum(o.deadline_violation for o in outcomes),
        "auto_resolved": len(autos),
        "auto_resolution_rate": _ratio(len(autos), n),
        "auto_resolution_accuracy": _ratio(sum(not o.unsafe_auto for o in autos), len(autos)),
        "unsafe_auto_resolutions": sum(o.unsafe_auto for o in outcomes),
        "injection_cases": len(inj),
        "injection_handled": _ratio(len(inj_ok), len(inj)),
        "injection_detected": _ratio(sum(o.injection_flagged for o in inj), len(inj)),
        "avg_latency_s": round(sum(o.latency_ms for o in outcomes) / n / 1000, 3) if n else None,
        "avg_cost_inr": round(sum(o.cost_inr for o in outcomes) / n, 4) if n else None,
        "pipeline_errors": sum(o.error is not None for o in outcomes),
        "note": meta["note"],
    }
    return {
        "headline": headline,
        "confusion_matrix": {"labels": codes, "rows": matrix},
        "by_scenario": {
            s: {
                "n": len(v),
                "reason_code_accuracy": _ratio(sum(o.code_ok for o in v), len(v)),
                "decision_accuracy": _ratio(sum(o.decision_ok for o in v), len(v)),
                "auto_resolved": sum(o.auto for o in v),
            }
            for s, v in sorted(by_scn.items())
        },
        "decision_breakdown": dict(Counter(o.pred_recommendation or "NONE" for o in outcomes)),
        "misses": [asdict(o) for o in outcomes if not (o.code_ok and o.decision_ok)],
        "cases": [asdict(o) for o in outcomes],
    }


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def to_markdown(rep: dict[str, Any]) -> str:
    h = rep["headline"]
    L = [
        "# DisputeIQ evaluation report",
        "",
        f"Generated {h['generated_at']} on the **held-out TEST split** ({h['n_cases']} cases). "
        f"Provider: `{h['provider']}`, model: `{h['model']}`.",
        "",
        f"> {h['note']}",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Reason-code accuracy | {_pct(h['reason_code_accuracy'])} |",
        f"| Decision accuracy (recommendation) | {_pct(h['decision_accuracy'])} |",
        f"| Deadline violations (target 0) | {h['deadline_violations']} |",
        f"| Auto-resolution rate | {_pct(h['auto_resolution_rate'])} ({h['auto_resolved']} cases) |",
        f"| Auto-resolution accuracy | {_pct(h['auto_resolution_accuracy'])} |",
        f"| Unsafe auto-resolutions (target 0) | {h['unsafe_auto_resolutions']} |",
        f"| Prompt injection handled | {_pct(h['injection_handled'])} of {h['injection_cases']} "
        f"(detected by filter: {_pct(h['injection_detected'])}) |",
        f"| Avg latency per case | {h['avg_latency_s']} s |",
        f"| Avg LLM cost per case | INR {h['avg_cost_inr']} |",
        f"| Pipeline errors | {h['pipeline_errors']} |",
        "",
        "## By scenario",
        "",
        "| Scenario | Cases | Reason code | Decision | Auto-resolved |",
        "|---|---|---|---|---|",
    ]
    for s, v in rep["by_scenario"].items():
        L.append(
            f"| {s} | {v['n']} | {_pct(v['reason_code_accuracy'])} | "
            f"{_pct(v['decision_accuracy'])} | {v['auto_resolved']} |"
        )
    labels = rep["confusion_matrix"]["labels"]
    L += [
        "",
        "## Reason-code confusion matrix",
        "",
        "Rows are the true code, columns the prediction.",
        "",
    ]
    L.append("| true \\ predicted | " + " | ".join(labels) + " |")
    L.append("|---|" + "---|" * len(labels))
    for g in labels:
        row = rep["confusion_matrix"]["rows"][g]
        L.append(f"| {g} | " + " | ".join(str(row[p]) if row[p] else "." for p in labels) + " |")
    L += ["", f"## Misses ({len(rep['misses'])})", ""]
    if rep["misses"]:
        L += [
            "| Case | Scenario | True code / decision | Predicted | Status |",
            "|---|---|---|---|---|",
        ]
        for m in rep["misses"]:
            L.append(
                f"| {m['dispute_id']} | {m['scenario']} | {m['gt_reason_code']} / {m['gt_recommendation']} | "
                f"{m['pred_reason_code']} / {m['pred_recommendation']} | {m['status']} |"
            )
    else:
        L.append("None.")
    return "\n".join(L) + "\n"


def run(limit: int | None = None, out_dir: Path = RESULTS_DIR) -> dict[str, Any]:
    from app.db.session import get_session_factory

    settings, cfg = get_settings(), get_rules_config()
    outcomes: list[CaseOutcome] = []
    with get_session_factory()() as session:
        stmt = (
            select(models.Dispute)
            .where(models.Dispute.split == DataSplit.TEST)
            .order_by(models.Dispute.id)
        )
        if limit:
            stmt = stmt.limit(limit)
        ids = [d.id for d in session.scalars(stmt)]
        pipeline = build_pipeline(session)
        for did in ids:
            res: ProcessResult = pipeline.run(did)
            d = session.get(models.Dispute, did)
            assert d is not None
            gt = d.ground_truth or {}
            outcomes.append(
                CaseOutcome(
                    dispute_id=did,
                    scenario=gt.get("scenario", "?"),
                    gt_reason_code=gt.get("reason_code", "?"),
                    gt_recommendation=gt.get("recommendation", "?"),
                    gt_auto=bool(gt.get("expected_auto_resolve")),
                    gt_should_route_human=bool(gt.get("should_route_human")),
                    gt_injection=bool(gt.get("prompt_injection")),
                    gt_window_expired=window_expired(gt, session, d.created_at, cfg),
                    pred_reason_code=res.reason_code,
                    pred_recommendation=res.recommendation.value if res.recommendation else None,
                    status=res.status.value,
                    confidence=res.confidence,
                    injection_flagged=res.injection_suspected,
                    friendly_fraud_flag=res.friendly_fraud,
                    latency_ms=res.latency_ms,
                    cost_inr=res.llm_cost_inr,
                    tokens=res.tokens_in + res.tokens_out,
                    error=res.error,
                )
            )
    note = (
        "Provider 'mock' is an offline rule-based stand-in for an LLM, so these numbers describe the "
        "deterministic pipeline plus a baseline classifier; cost and latency are estimates. The complaints "
        "are synthetic and template-generated, so accuracy is likely optimistic versus real customer "
        "text. Re-run with LLM_PROVIDER=gemini (GEMINI_API_KEY) for real-model results."
        if settings.llm_provider == "mock"
        else "Real LLM provider; cost computed from reported token usage at configured prices."
    )
    meta = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "provider": settings.llm_provider,
        "model": settings.llm_model if settings.llm_provider != "mock" else "mock-rules-v1",
        "note": note,
    }
    report = build_report(outcomes, meta)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    body = json.dumps(report, indent=2, default=str)
    (out_dir / f"{stamp}.json").write_text(body)
    (out_dir / f"{stamp}.md").write_text(to_markdown(report))
    if outcomes and limit is None:  # partial (--limit) or empty runs never replace the headline
        (out_dir / "latest.json").write_text(body)
        (out_dir / "latest.md").write_text(to_markdown(report))
    return report


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    rep = run(args.limit)
    print(to_markdown(rep))


if __name__ == "__main__":
    main()
