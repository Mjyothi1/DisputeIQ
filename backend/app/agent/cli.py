"""Run one dispute end to end and print the decision and audit trail.

python -m app.agent.cli --dispute-id 12
python -m app.agent.cli --customer-id 5 --text "I was charged twice by KartKing for Rs 999"
python -m app.agent.cli --ping-llm   # live Gemini connectivity check (no mock fallback)
"""

import argparse
import json
import sys

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agent.llm import LLMError, build_llm_client, resolve_model
from app.agent.pipeline import build_pipeline
from app.core.config import get_settings
from app.db import models
from app.db.enums import DisputeChannel
from app.db.session import get_session_factory


class _PingOut(BaseModel):
    ok: bool = Field(description="Must be true when the provider answered.")
    provider_echo: str = Field(description="Short confirmation that a real model responded.")


def ping_llm() -> int:
    """Make one structured call against the configured provider. Exit non-zero on failure."""
    settings = get_settings()
    model = resolve_model(settings)
    print(f"Provider={settings.llm_provider}  model={model}")
    if settings.llm_provider == "mock":
        print(
            "LLM_PROVIDER=mock — this is the offline fixture, not a live Gemini call.",
            file=sys.stderr,
        )
        return 2
    try:
        client = build_llm_client(settings)
        result = client.structured(
            task="ping",
            system=(
                "You are a connectivity probe for DisputeIQ. "
                "Return JSON matching the schema. Do not invent dispute decisions."
            ),
            user='Reply with ok=true and provider_echo="gemini-live" if you are Gemini.',
            schema=_PingOut,
            prompt_version="ping-v1",
        )
    except LLMError as exc:
        print(f"LIVE LLM CALL FAILED (no mock fallback): {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — surface unexpected SDK errors clearly
        print(f"LIVE LLM CALL FAILED (no mock fallback): {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": result.parsed.ok,
                "provider_echo": result.parsed.provider_echo,
                "model": result.model,
                "tokens_in": result.tokens_in,
                "tokens_out": result.tokens_out,
                "cost_inr": result.cost_inr,
                "latency_ms": result.latency_ms,
                "source": "live-provider",
            },
            indent=2,
        )
    )
    return 0 if result.parsed.ok else 1


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dispute-id", type=int)
    ap.add_argument("--customer-id", type=int)
    ap.add_argument("--text")
    ap.add_argument(
        "--ping-llm",
        action="store_true",
        help="Call the configured real LLM once and print telemetry (fails closed, no mock).",
    )
    args = ap.parse_args()
    if args.ping_llm:
        raise SystemExit(ping_llm())
    if not args.dispute_id and not (args.customer_id and args.text):
        ap.error("give --dispute-id, or --customer-id with --text, or --ping-llm")

    with get_session_factory()() as session:
        if args.dispute_id:
            dispute_id = args.dispute_id
        else:
            d = models.Dispute(
                customer_id=args.customer_id, channel=DisputeChannel.FORM, raw_text=args.text
            )
            session.add(d)
            session.commit()
            dispute_id = d.id
        result = build_pipeline(session).run(dispute_id)
        disputed = session.get(models.Dispute, dispute_id)
        assert disputed is not None
        decision = session.scalars(
            select(models.Decision)
            .where(models.Decision.dispute_id == dispute_id)
            .order_by(models.Decision.id.desc())
        ).first()
        print(f"\n=== Dispute {dispute_id}: {result.status.value} ===")
        print(f"Masked complaint : {disputed.masked_text}")
        print(f"Matched txn      : {result.matched_txn_id}   Reason code: {result.reason_code}")
        print(
            f"Recommendation   : {result.recommendation.value if result.recommendation else None}"
            f"  (confidence {result.confidence})  friendly_fraud={result.friendly_fraud}"
        )
        if result.route_reasons:
            print(f"Sent to human because: {' | '.join(result.route_reasons)}")
        if decision:
            print(
                f"\nModel: {decision.model} (live Gemini if name starts with gemini-; "
                f"mock-rules-v1 is the offline fixture)"
            )
            print(
                f"\nRationale:\n{decision.rationale}\n\n--- Customer letter ---\n{decision.drafted_customer_letter}"
            )
            if decision.drafted_chargeback_filing:
                print(f"\n--- Chargeback filing ---\n{decision.drafted_chargeback_filing}")
        print("\n--- Audit trail ---")
        for e in session.scalars(
            select(models.AuditEvent)
            .where(models.AuditEvent.dispute_id == dispute_id)
            .order_by(models.AuditEvent.id)
        ):
            tele = (
                f" [{e.model} {e.tokens_in}/{e.tokens_out} tok, INR {e.cost_inr}, {e.latency_ms}ms]"
                if e.model
                else ""
            )
            print(
                f"{e.timestamp:%H:%M:%S} {e.actor.value:5} {e.step:22}{tele}\n      -> {e.output_summary}"
            )
        print(
            f"\nTotal: {result.tokens_in}+{result.tokens_out} tokens, INR {result.llm_cost_inr}, {result.latency_ms} ms"
        )
        if result.error:
            print(f"Pipeline error (no fabricated analysis): {result.error}", file=sys.stderr)


if __name__ == "__main__":
    main()
