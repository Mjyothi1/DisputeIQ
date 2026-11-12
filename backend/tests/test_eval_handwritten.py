"""The hand-authored evaluation harness: structure, label isolation and safety invariants."""

import pytest

from eval import handwritten as hw


def test_suite_is_varied_and_labelled() -> None:
    kinds = {c.kind for c in hw.CASES}
    assert {"duplicate", "atm", "fraud_authed", "fraud_unauth", "gnr", "vague", "no_txn", "attack"} <= kinds
    assert any(c.lang == "hinglish" for c in hw.CASES) and sum(c.adversarial for c in hw.CASES) >= 5
    assert len({c.id for c in hw.CASES}) == len(hw.CASES)


def test_mock_run_has_zero_unsafe_auto_resolutions_and_never_leaks_labels() -> None:
    rep = hw.evaluate("mock")
    m = rep["metrics"]
    assert rep["provider"] == "mock" and rep["model"] == "mock-rules-v1"
    assert m["unsafe_auto_resolutions"]["count"] == 0
    assert m["adversarial"]["auto_resolved"] == 0 and m["adversarial"]["flagged"] == m["adversarial"]["n"]
    assert m["benign_lookalikes_wrongly_flagged"] == 0
    assert "Offline rule engine - not Gemini" in hw.to_markdown(rep)
    assert "AI assistant" in rep["authorship"]  # authorship is disclosed, not hidden


def test_live_run_refuses_without_credentials(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from app.core.config import Settings

    monkeypatch.setattr(hw, "get_settings", lambda: Settings(_env_file=None, gemini_api_key=""))
    monkeypatch.setattr("sys.argv", ["handwritten", "--provider", "gemini"])
    with pytest.raises(SystemExit) as e:
        hw.main()
    assert "NOT run" in str(e.value)
