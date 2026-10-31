"""LLM complaint writer: fact validation, fallback, caching, RNG-stream stability."""

import random
from types import SimpleNamespace
from typing import Any

from data_gen.complaints import ComplaintContext, LLMWriter, TemplateWriter


class FakeLLM:
    model = "fake"

    def __init__(self, replies: list[str] | Exception) -> None:
        self.replies, self.calls = replies, 0

    def structured(self, **kw: Any) -> Any:
        self.calls += 1
        if isinstance(self.replies, Exception):
            raise self.replies
        text = self.replies[min(self.calls - 1, len(self.replies) - 1)]
        return SimpleNamespace(parsed=kw["schema"](text=text))


def ctx(**kw: Any) -> ComplaintContext:
    base: dict[str, Any] = dict(
        reason_code="DUPLICATE_CHARGE",
        merchant="Swiggy",
        amount="Rs 499",
        date="12 Oct",
        last4="1234",
    )
    return ComplaintContext(**{**base, **kw})


GOOD = "Swiggy ne mere card 1234 se Rs 499 do baar kaat liye, please check karo yaar."


def test_accepts_text_with_all_facts_and_appends_pii() -> None:
    w = LLMWriter(FakeLLM([GOOD]))
    out = w.write(random.Random(1), ctx(phone="+91 98765 43210"), "hinglish")
    assert out.startswith(GOOD) and "98765" in out
    assert w.stats == {"llm": 1, "cached": 0, "fallback": 0}


def test_missing_fact_retries_then_falls_back_to_template() -> None:
    llm = FakeLLM(["Charged twice, fix it please now."])
    w = LLMWriter(llm)
    out = w.write(random.Random(1), ctx(), "formal")
    assert llm.calls == 2 and w.stats["fallback"] == 1
    assert out == TemplateWriter().write(random.Random(1), ctx(), "formal")


def test_second_attempt_can_succeed() -> None:
    w = LLMWriter(FakeLLM(["no facts here at all, sorry", GOOD]))
    assert w.write(random.Random(1), ctx(), "formal").startswith(GOOD)


def test_llm_exception_falls_back_without_raising() -> None:
    w = LLMWriter(FakeLLM(RuntimeError("api down")))
    assert w.write(random.Random(1), ctx(), "formal")
    assert w.stats["fallback"] == 1


def test_vague_text_must_not_leak_amount() -> None:
    c = ctx(reason_code="GOODS_NOT_RECEIVED", vague=True)
    leak = "I paid Rs 499 to Swiggy and nothing arrived."
    w = LLMWriter(FakeLLM([leak]))
    assert w.write(random.Random(1), c, "formal") != leak


def test_wrong_spelling_style_does_not_require_exact_merchant() -> None:
    w = LLMWriter(FakeLLM(["Swigy charged me Rs 499 twice on card 1234, sort it out."]))
    assert "Swigy" in w.write(random.Random(1), ctx(), "wrong_spelling")
    assert w.stats["llm"] == 1


def test_cache_roundtrip_avoids_second_call(tmp_path: Any) -> None:
    path = str(tmp_path / "c.json")
    LLMWriter(FakeLLM([GOOD]), path).write(random.Random(1), ctx(), "formal")
    llm2 = FakeLLM(["should not be called"])
    w2 = LLMWriter(llm2, path)
    assert w2.write(random.Random(1), ctx(), "formal").startswith(GOOD)
    assert llm2.calls == 0 and w2.stats["cached"] == 1


def test_rng_stream_matches_template_writer() -> None:
    a, b = random.Random(5), random.Random(5)
    LLMWriter(FakeLLM([GOOD])).write(a, ctx(), "typos")
    TemplateWriter().write(b, ctx(), "typos")
    assert a.random() == b.random()
