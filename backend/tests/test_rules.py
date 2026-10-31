from datetime import datetime, timedelta, timezone
UTC = timezone.utc  # Python 3.11+ compat
from decimal import Decimal

import pytest

from app.db.enums import Recommendation
from app.rules.config import RulesConfig, load_rules_config
from app.rules.eligibility import EligibilityResult, check_eligibility, compute_deadline
from app.rules.policy import (
    CONF_FREQUENT_DISPUTER_CAP,
    baseline_recommendation,
    enforce_consistency,
)
from app.rules.routing import route
from app.rules.types import Blocker, CheckName, EvidenceItem, Finding, RouteTarget

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def cfg() -> RulesConfig:
    return load_rules_config()


def ev(name: CheckName, finding: Finding, **details: object) -> EvidenceItem:
    return EvidenceItem(name, finding, f"{name.value}:{finding.value}", dict(details))


OK = EligibilityResult(eligible=True, deadline_at=NOW, days_remaining=30)


# ---- config -----------------------------------------------------------------------------
def test_config_has_all_eight_codes(cfg: RulesConfig) -> None:
    assert set(cfg.codes) == {
        "FRAUD_NOT_AUTHORISED", "DUPLICATE_CHARGE", "GOODS_NOT_RECEIVED", "NOT_AS_DESCRIBED",
        "CANCELLED_RECURRING", "INCORRECT_AMOUNT", "REFUND_NOT_PROCESSED",
        "ATM_CASH_NOT_DISPENSED",
    }  # fmt: skip
    assert cfg.spec("DUPLICATE_CHARGE").code == "DUPLICATE_CHARGE"


def test_bad_allow_list_rejected(tmp_path: object, cfg: RulesConfig) -> None:
    from pathlib import Path

    import yaml

    from app.rules.config import CONFIG_PATH

    raw = yaml.safe_load(CONFIG_PATH.read_text())
    raw["thresholds"]["auto_resolve_codes"] = ["NOPE"]
    p = Path(str(tmp_path)) / "bad.yaml"
    p.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="unknown codes"):
        load_rules_config(p)


# ---- deadlines --------------------------------------------------------------------------
def test_deadline_exact_window(cfg: RulesConfig) -> None:
    txn_time = NOW - timedelta(days=100)
    d = compute_deadline("DUPLICATE_CHARGE", txn_time, NOW, cfg)
    assert d.deadline_at == txn_time + timedelta(days=120)
    assert d.days_remaining == 20
    assert not d.expired


def test_deadline_boundary_is_not_expired_at_exact_instant(cfg: RulesConfig) -> None:
    txn_time = NOW - timedelta(days=120)
    d = compute_deadline("DUPLICATE_CHARGE", txn_time, NOW, cfg)
    assert d.days_remaining == 0
    assert not d.expired


def test_deadline_one_second_after_is_expired(cfg: RulesConfig) -> None:
    txn_time = NOW - timedelta(days=120, seconds=1)
    d = compute_deadline("DUPLICATE_CHARGE", txn_time, NOW, cfg)
    assert d.expired
    assert d.days_remaining == -1


def test_atm_uses_shorter_window(cfg: RulesConfig) -> None:
    d = compute_deadline("ATM_CASH_NOT_DISPENSED", NOW - timedelta(days=31), NOW, cfg)
    assert d.expired


def test_naive_datetimes_treated_as_utc(cfg: RulesConfig) -> None:
    d = compute_deadline("DUPLICATE_CHARGE", datetime(2026, 10, 1), NOW, cfg)  # noqa: DTZ001
    assert d.deadline_at.tzinfo is not None


# ---- eligibility ------------------------------------------------------------------------
def test_no_transaction_is_ineligible(cfg: RulesConfig) -> None:
    r = check_eligibility("FRAUD_NOT_AUTHORISED", None, [], NOW, cfg)
    assert not r.eligible and r.blockers == [Blocker.NO_TRANSACTION]


def test_duplicate_eligible_with_positive_evidence(cfg: RulesConfig) -> None:
    e = [ev(CheckName.DUPLICATE_CHARGE, Finding.POSITIVE)]
    r = check_eligibility("DUPLICATE_CHARGE", NOW - timedelta(days=5), e, NOW, cfg)
    assert r.eligible and r.days_remaining == 115


def test_duplicate_contradicted_when_no_duplicate(cfg: RulesConfig) -> None:
    e = [ev(CheckName.DUPLICATE_CHARGE, Finding.NEGATIVE)]
    r = check_eligibility("DUPLICATE_CHARGE", NOW - timedelta(days=5), e, NOW, cfg)
    assert not r.eligible and Blocker.EVIDENCE_CONTRADICTS in r.blockers


def test_missing_required_evidence(cfg: RulesConfig) -> None:
    r = check_eligibility("DUPLICATE_CHARGE", NOW - timedelta(days=5), [], NOW, cfg)
    assert r.blockers == [Blocker.EVIDENCE_MISSING]
    assert r.missing_evidence == ["duplicate_charge"]


def test_inconclusive_counts_as_missing(cfg: RulesConfig) -> None:
    e = [ev(CheckName.SUBSCRIPTION_CANCELLED, Finding.INCONCLUSIVE)]
    r = check_eligibility("CANCELLED_RECURRING", NOW - timedelta(days=5), e, NOW, cfg)
    assert Blocker.EVIDENCE_MISSING in r.blockers


def test_window_expired_blocks(cfg: RulesConfig) -> None:
    e = [ev(CheckName.DUPLICATE_CHARGE, Finding.POSITIVE)]
    r = check_eligibility("DUPLICATE_CHARGE", NOW - timedelta(days=200), e, NOW, cfg)
    assert r.window_expired and not r.eligible


def test_full_refund_blocks_but_partial_does_not(cfg: RulesConfig) -> None:
    full = [ev(CheckName.REFUND_ISSUED, Finding.POSITIVE, refund_status="FULL")]
    part = [ev(CheckName.REFUND_ISSUED, Finding.POSITIVE, refund_status="PARTIAL")]
    t = NOW - timedelta(days=3)
    assert (
        Blocker.ALREADY_REFUNDED
        in check_eligibility("GOODS_NOT_RECEIVED", t, full, NOW, cfg).blockers
    )
    assert check_eligibility("GOODS_NOT_RECEIVED", t, part, NOW, cfg).eligible


def test_fraud_has_no_required_evidence(cfg: RulesConfig) -> None:
    assert check_eligibility("FRAUD_NOT_AUTHORISED", NOW - timedelta(days=3), [], NOW, cfg).eligible


# ---- policy -----------------------------------------------------------------------------
def test_friendly_fraud_rejected_and_flagged(cfg: RulesConfig) -> None:
    e = [ev(CheckName.STRONG_AUTHENTICATION, Finding.POSITIVE)]
    p = baseline_recommendation("FRAUD_NOT_AUTHORISED", OK, e)
    assert p.recommendation is Recommendation.REJECT and p.friendly_fraud


def test_genuine_fraud_files_chargeback(cfg: RulesConfig) -> None:
    e = [ev(CheckName.STRONG_AUTHENTICATION, Finding.NEGATIVE)]
    p = baseline_recommendation("FRAUD_NOT_AUTHORISED", OK, e)
    assert p.recommendation is Recommendation.FILE_CHARGEBACK and not p.friendly_fraud


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("DUPLICATE_CHARGE", Recommendation.REFUND),
        ("ATM_CASH_NOT_DISPENSED", Recommendation.REFUND),
        ("CANCELLED_RECURRING", Recommendation.FILE_CHARGEBACK),
        ("INCORRECT_AMOUNT", Recommendation.FILE_CHARGEBACK),
        ("REFUND_NOT_PROCESSED", Recommendation.FILE_CHARGEBACK),
    ],
)
def test_verified_codes(cfg: RulesConfig, code: str, expected: Recommendation) -> None:
    assert baseline_recommendation(code, OK, []).recommendation is expected


def test_expired_window_rejects(cfg: RulesConfig) -> None:
    el = EligibilityResult(False, NOW, -5, [Blocker.WINDOW_EXPIRED], ["expired"])
    assert (
        baseline_recommendation("DUPLICATE_CHARGE", el, []).recommendation is Recommendation.REJECT
    )


def test_missing_evidence_requests_info(cfg: RulesConfig) -> None:
    el = EligibilityResult(False, NOW, 5, [Blocker.EVIDENCE_MISSING], ["missing"])
    p = baseline_recommendation("CANCELLED_RECURRING", el, [])
    assert p.recommendation is Recommendation.NEED_MORE_INFO


def test_no_transaction_requests_info(cfg: RulesConfig) -> None:
    el = EligibilityResult(False, None, None, [Blocker.NO_TRANSACTION], ["none"])
    p = baseline_recommendation("GOODS_NOT_RECEIVED", el, [])
    assert p.recommendation is Recommendation.NEED_MORE_INFO


def test_unverifiable_claim_strong_vs_weak_match(cfg: RulesConfig) -> None:
    strong = baseline_recommendation("GOODS_NOT_RECEIVED", OK, [], match_score=0.9)
    weak = baseline_recommendation("GOODS_NOT_RECEIVED", OK, [], match_score=0.55)
    assert strong.recommendation is Recommendation.FILE_CHARGEBACK and strong.max_confidence <= 0.6
    assert weak.recommendation is Recommendation.NEED_MORE_INFO


def test_frequent_disputer_caps_confidence(cfg: RulesConfig) -> None:
    e = [ev(CheckName.DISPUTE_HISTORY, Finding.POSITIVE)]
    p = baseline_recommendation("DUPLICATE_CHARGE", OK, e)
    assert p.frequent_disputer and p.max_confidence == CONF_FREQUENT_DISPUTER_CAP


def test_consistency_downgrades_ineligible(cfg: RulesConfig) -> None:
    expired = EligibilityResult(False, NOW, -1, [Blocker.WINDOW_EXPIRED], ["late"])
    missing = EligibilityResult(False, NOW, 5, [Blocker.EVIDENCE_MISSING], ["gap"])
    assert enforce_consistency(Recommendation.FILE_CHARGEBACK, expired)[0] is Recommendation.REJECT
    assert enforce_consistency(Recommendation.REFUND, missing)[0] is Recommendation.NEED_MORE_INFO
    assert enforce_consistency(Recommendation.REFUND, OK) == (Recommendation.REFUND, [])
    assert enforce_consistency(Recommendation.REJECT, expired) == (Recommendation.REJECT, [])


# ---- routing ----------------------------------------------------------------------------
def auto(**over: object) -> bool:
    args: dict[str, object] = {
        "recommendation": Recommendation.REFUND, "confidence": 0.95,
        "amount": Decimal("2500"), "reason_code": "DUPLICATE_CHARGE", "eligibility": OK,
    }  # fmt: skip
    args.update(over)
    return route(**args).target is RouteTarget.AUTO_RESOLVE  # type: ignore[arg-type]


def test_clean_duplicate_auto_resolves() -> None:
    assert auto()


@pytest.mark.parametrize(
    "override",
    [
        {"recommendation": Recommendation.REJECT},
        {"recommendation": Recommendation.FILE_CHARGEBACK},
        {"recommendation": Recommendation.NEED_MORE_INFO},
        {"confidence": 0.84},
        {"amount": Decimal("10000.01")},
        {"amount": None},
        {"reason_code": "FRAUD_NOT_AUTHORISED"},
        {"reason_code": "GOODS_NOT_RECEIVED"},
        {"friendly_fraud": True},
        {"frequent_disputer": True},
        {"injection_suspected": True},
        {"needs_human_flag": True},
        {"eligibility": EligibilityResult(False, NOW, -1, [Blocker.WINDOW_EXPIRED])},
    ],
)
def test_any_failed_condition_goes_to_human(override: dict[str, object]) -> None:
    assert not auto(**override)


def test_route_boundaries_are_inclusive() -> None:
    assert auto(confidence=0.85)
    assert auto(amount=Decimal("10000"))


def test_every_reject_goes_to_human_regardless_of_confidence() -> None:
    assert not auto(recommendation=Recommendation.REJECT, confidence=1.0)


def test_route_reports_reasons() -> None:
    r = route(Recommendation.REJECT, 0.5, Decimal("1"), "X", OK)
    assert r.target is RouteTarget.HUMAN_REVIEW and len(r.reasons) >= 3


# ---- evidence verdicts and match caps ---------------------------------------------------
def test_evidence_verdicts(cfg: RulesConfig) -> None:
    from app.rules.policy import confidence_cap_for_match, evidence_verdict

    dup_pos = ev(CheckName.DUPLICATE_CHARGE, Finding.POSITIVE)
    assert evidence_verdict("DUPLICATE_CHARGE", dup_pos, cfg) == "PASS"
    assert (
        evidence_verdict("DUPLICATE_CHARGE", ev(CheckName.DUPLICATE_CHARGE, Finding.NEGATIVE), cfg)
        == "FAIL"
    )
    assert (
        evidence_verdict(
            "DUPLICATE_CHARGE", ev(CheckName.DUPLICATE_CHARGE, Finding.INCONCLUSIVE), cfg
        )
        == "INCONCLUSIVE"
    )
    # weakened_by: strong auth on a fraud claim reads as FAIL; absence reads as PASS
    auth = CheckName.STRONG_AUTHENTICATION
    assert evidence_verdict("FRAUD_NOT_AUTHORISED", ev(auth, Finding.POSITIVE), cfg) == "FAIL"
    assert evidence_verdict("FRAUD_NOT_AUTHORISED", ev(auth, Finding.NEGATIVE), cfg) == "PASS"
    # frequent disputer is a concern for every code; unrelated checks are INFO
    hist = CheckName.DISPUTE_HISTORY
    assert evidence_verdict("GOODS_NOT_RECEIVED", ev(hist, Finding.POSITIVE), cfg) == "FAIL"
    assert (
        evidence_verdict("DUPLICATE_CHARGE", ev(CheckName.ATM_FAILURE, Finding.NEGATIVE), cfg)
        == "INFO"
    )
    assert (
        evidence_verdict("DUPLICATE_CHARGE", ev(CheckName.ATM_FAILURE, Finding.INCONCLUSIVE), cfg)
        == "INFO"
    )
    # match caps
    assert confidence_cap_for_match(0.95) == 1.0
    assert confidence_cap_for_match(0.79) == 0.7 and confidence_cap_for_match(None) == 0.7
    assert confidence_cap_for_match(0.99, ambiguous=True) == 0.7


def test_route_lists_friendly_fraud_first() -> None:
    r = route(
        Recommendation.REJECT,
        0.75,
        Decimal("50000"),
        "FRAUD_NOT_AUTHORISED",
        OK,
        friendly_fraud=True,
    )
    assert "friendly fraud" in r.reasons[0].lower()
    assert (
        "No matched transaction amount."
        in route(Recommendation.REFUND, 0.9, None, "DUPLICATE_CHARGE", OK).reasons
    )
