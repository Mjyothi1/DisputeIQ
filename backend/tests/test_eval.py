"""The evaluation harness's scoring logic (pure functions, no database)."""

from eval.run_eval import CaseOutcome, build_report, to_markdown


def outcome(**kw: object) -> CaseOutcome:
    base: dict[str, object] = dict(
        dispute_id=1, scenario="duplicate", gt_reason_code="DUPLICATE_CHARGE",
        gt_recommendation="REFUND", gt_auto=True, gt_should_route_human=False, gt_injection=False,
        gt_window_expired=False, pred_reason_code="DUPLICATE_CHARGE", pred_recommendation="REFUND",
        status="AUTO_RESOLVED", confidence=0.9, injection_flagged=False, friendly_fraud_flag=False,
        latency_ms=100, cost_inr=1.0, tokens=500, error=None,
    )  # fmt: skip
    base.update(kw)
    return CaseOutcome(**base)  # type: ignore[arg-type]


META = {"generated_at": "t", "provider": "mock", "model": "m", "note": "n"}


def test_perfect_run() -> None:
    h = build_report([outcome(), outcome(dispute_id=2)], META)["headline"]
    assert h["reason_code_accuracy"] == h["decision_accuracy"] == 1.0
    assert h["auto_resolution_accuracy"] == 1.0 and h["unsafe_auto_resolutions"] == 0


def test_unsafe_auto_resolution_is_counted() -> None:
    bad = outcome(gt_should_route_human=True)
    wrong = outcome(dispute_id=2, pred_recommendation="REJECT")
    h = build_report([bad, wrong, outcome(dispute_id=3)], META)["headline"]
    assert h["unsafe_auto_resolutions"] == 2
    assert h["auto_resolution_accuracy"] == round(1 / 3, 4)


def test_deadline_violation_only_for_filing_actions_on_expired_cases() -> None:
    expired_filed = outcome(gt_window_expired=True, status="NEEDS_HUMAN")
    expired_rejected = outcome(
        dispute_id=2, gt_window_expired=True, pred_recommendation="REJECT", status="NEEDS_HUMAN"
    )
    h = build_report([expired_filed, expired_rejected, outcome(dispute_id=3)], META)["headline"]
    assert h["deadline_violations"] == 1


def test_injection_handling_and_confusion_matrix() -> None:
    inj_ok = outcome(gt_injection=True, injection_flagged=True, status="NEEDS_HUMAN", gt_auto=False)
    inj_bad = outcome(
        dispute_id=2, gt_injection=True, pred_recommendation="REJECT", status="NEEDS_HUMAN"
    )
    wrong_code = outcome(dispute_id=3, pred_reason_code="GOODS_NOT_RECEIVED", status="NEEDS_HUMAN")
    rep = build_report([inj_ok, inj_bad, wrong_code], META)
    assert rep["headline"]["injection_handled"] == 0.5
    assert rep["headline"]["injection_detected"] == 0.5
    assert rep["confusion_matrix"]["rows"]["DUPLICATE_CHARGE"]["GOODS_NOT_RECEIVED"] == 1
    assert len(rep["misses"]) == 2
    assert "Reason-code accuracy" in to_markdown(rep)
