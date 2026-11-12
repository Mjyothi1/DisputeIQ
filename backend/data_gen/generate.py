"""Seeded, reproducible synthetic data generator.

Creates customers, cards, merchants, ~5,000 transactions over 12 months, and ~300 disputes with
ground-truth labels. Ground truth lives only in ``disputes.ground_truth`` and is never read by the
agent; the evaluation harness uses it on the TEST split only.
"""

import random
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.db import models
from app.db.enums import (
    AuthMethod,
    CardNetwork,
    DataSplit,
    DisputeChannel,
    DisputeStatus,
    MerchantCategory,
    RefundStatus,
    SubscriptionStatus,
    TxnChannel,
)
from app.rules.config import get_rules_config
from data_gen.catalog import (
    CITIES,
    FIRST_NAMES,
    FRAUD_MERCHANTS,
    INJECTIONS,
    LAST_NAMES,
    MERCHANTS,
)
from data_gen.complaints import STYLES, ComplaintContext, ComplaintWriter, TemplateWriter, misspell

UTC = timezone.utc  # datetime.UTC was added in Python 3.11; timezone.utc works everywhere

C = MerchantCategory
ONLINE = (C.ECOMMERCE, C.FOOD_DELIVERY, C.TRAVEL)

# scenario -> number of disputes (sums to 300)
PLAN: dict[str, int] = {
    "duplicate": 45,
    "friendly_fraud": 35,
    "genuine_fraud": 30,
    "gnr_clear": 15,
    "gnr_vague": 15,
    "not_as_described": 15,
    "cancelled_recurring": 25,
    "cancelled_but_active": 5,
    "atm_failure": 22,
    "atm_cash_was_dispensed": 3,
    "refunded_then_disputed": 20,
    "out_of_window": 20,
    "incorrect_amount": 15,
    "refund_not_processed": 15,
    "serial_duplicate": 10,
    "prompt_injection": 10,
}
N_SERIAL_CUSTOMERS = 2
SUB_PRICES = [149, 199, 299, 399, 499, 649, 799, 999, 1499]


def money(rng: random.Random, low: float, high: float, whole: float = 0.6) -> Decimal:
    """Random INR amount in [low, high]; mostly whole rupees."""
    v = rng.uniform(low, high)
    if rng.random() < whole:
        v = round(v / 10) * 10 or 10
    return Decimal(str(round(v, 2))).quantize(Decimal("0.01"), ROUND_HALF_UP)


@dataclass
class Planted:
    """What a scenario builder returns."""

    txn: models.Transaction
    ctx: ComplaintContext
    truth: dict[str, Any]
    customer: models.Customer
    match_checkable: bool = True


@dataclass
class Generator:
    session: Session
    rng: random.Random
    anchor: datetime
    writer: ComplaintWriter
    customers: list[models.Customer] = field(default_factory=list)
    cards_by_customer: dict[int, list[models.Card]] = field(default_factory=dict)
    merchants: list[models.Merchant] = field(default_factory=list)
    fraud_merchants: list[models.Merchant] = field(default_factory=list)
    serial: list[models.Customer] = field(default_factory=list)
    pool: list[models.Customer] = field(default_factory=list)
    _pool_i: int = 0

    # ---- base world ---------------------------------------------------------------------
    def build_world(self, n_customers: int = 200, n_cards: int = 300) -> None:
        r = self.rng
        for i in range(n_customers):
            first, last = r.choice(FIRST_NAMES), r.choice(LAST_NAMES)
            self.customers.append(
                models.Customer(
                    name=f"{first} {last}",
                    phone=f"+91{r.choice('6789')}{r.randrange(10**9):09d}",
                    email=f"{first}.{last}{i}@example.com".lower(),
                    segment=r.choice(["RETAIL", "RETAIL", "PREMIUM", "STUDENT"]),
                    created_at=self.anchor - timedelta(days=r.randint(400, 2000)),
                )
            )
        self.session.add_all(self.customers)
        self.session.flush()

        owners = [c for c in self.customers] + [
            r.choice(self.customers) for _ in range(n_cards - n_customers)
        ]
        for c in owners:
            last4 = f"{r.randrange(10**4):04d}"
            card = models.Card(
                customer_id=c.id,
                masked_pan=f"XXXX-XXXX-XXXX-{last4}",
                last4=last4,
                network=r.choice(list(CardNetwork)),
            )
            self.session.add(card)
            self.cards_by_customer.setdefault(c.id, []).append(card)
        self.session.flush()

        for name, cat, mcc, recurring in MERCHANTS:
            self.merchants.append(
                models.Merchant(
                    name=name, mcc=mcc, category=cat, is_recurring_biller=recurring,
                    city=r.choice(CITIES),
                )
            )  # fmt: skip
        for name, cat, mcc, city in FRAUD_MERCHANTS:
            m = models.Merchant(name=name, mcc=mcc, category=cat, city=city)
            self.fraud_merchants.append(m)
        self.session.add_all([*self.merchants, *self.fraud_merchants])
        self.session.flush()

        shuffled = self.customers[:]
        r.shuffle(shuffled)
        self.serial = shuffled[:N_SERIAL_CUSTOMERS]
        self.pool = shuffled[N_SERIAL_CUSTOMERS:]

    def by_cat(self, *cats: MerchantCategory) -> list[models.Merchant]:
        return [m for m in self.merchants if m.category in cats]

    def next_customer(self) -> models.Customer:
        c = self.pool[self._pool_i % len(self.pool)]
        self._pool_i += 1
        return c

    def card_of(self, customer: models.Customer) -> models.Card:
        return self.rng.choice(self.cards_by_customer[customer.id])

    def add_txn(self, **kw: Any) -> models.Transaction:
        t = models.Transaction(**kw)
        self.session.add(t)
        self.session.flush()
        return t

    # ---- background traffic -------------------------------------------------------------
    def background(self, n: int) -> None:
        r = self.rng
        all_cards = [c for cards in self.cards_by_customer.values() for c in cards]
        # Active subscriptions with monthly charges.
        subs = self.by_cat(C.SUBSCRIPTION)
        made = 0
        for card in r.sample(all_cards, 140):
            m = r.choice(subs)
            price = Decimal(r.choice(SUB_PRICES))
            self.session.add(
                models.Subscription(
                    card_id=card.id, merchant_id=m.id, status=SubscriptionStatus.ACTIVE
                )
            )
            start = self.anchor - timedelta(days=r.randint(60, 340))
            t = start
            while t < self.anchor - timedelta(days=1):
                self.add_txn(
                    card_id=card.id, merchant_id=m.id, amount=price, txn_time=t,
                    channel=TxnChannel.RECURRING, auth_method=AuthMethod.NONE, is_recurring=True,
                )  # fmt: skip
                made += 1
                t += timedelta(days=30)
        for _ in range(n - made):
            card = r.choice(all_cards)
            m = r.choice([x for x in self.merchants if x.category is not C.SUBSCRIPTION])
            when = self.anchor - timedelta(seconds=r.randint(3600, 365 * 86400))
            if m.category is C.ATM:
                self.add_txn(
                    card_id=card.id, merchant_id=m.id, amount=Decimal(r.choice([500, 1000, 2000, 3000, 5000, 10000])),
                    txn_time=when, channel=TxnChannel.ATM, auth_method=AuthMethod.PIN,
                    details={"cash_dispensed": True},
                )  # fmt: skip
            elif m.category is C.RETAIL:
                amt = money(r, 80, 9000, 0.3)
                self.add_txn(
                    card_id=card.id, merchant_id=m.id, amount=amt, txn_time=when,
                    channel=TxnChannel.POS,
                    auth_method=AuthMethod.PIN if amt > 2000 else r.choice([AuthMethod.PIN, AuthMethod.NONE]),
                )  # fmt: skip
            else:
                hi = {C.TRAVEL: 25000, C.ECOMMERCE: 12000, C.FOOD_DELIVERY: 1500}[m.category]
                self.add_txn(
                    card_id=card.id, merchant_id=m.id, amount=money(r, 90, hi, 0.4), txn_time=when,
                    channel=TxnChannel.ECOM,
                    auth_method=AuthMethod.OTP_3DS if r.random() < 0.92 else AuthMethod.NONE,
                )  # fmt: skip

    # ---- scenario builders --------------------------------------------------------------
    def _ctx(
        self, code: str, txn: models.Transaction, customer: models.Customer, **kw: Any
    ) -> ComplaintContext:
        r = self.rng
        style = kw.pop("style", None) or r.choice(STYLES)
        merchant = kw.pop("merchant_name", None) or txn.merchant.name
        if style == "wrong_spelling":
            merchant = misspell(r, merchant)
        when = txn.txn_time
        if style == "wrong_date":
            when = when + timedelta(days=r.choice([-6, -4, -3, 3, 4, 7]))
        amount = kw.pop("amount", txn.amount)
        fmt = r.choice(["Rs {:,.0f}", "Rs {:,.2f}", "INR {:,.2f}", "₹{:,.0f}"])
        ctx = ComplaintContext(
            style=style,
            reason_code=code,
            merchant=merchant,
            amount=fmt.format(amount) if amount is not None else None,
            date=when.strftime("%d %b"),
            last4=txn.card.last4 if r.random() < 0.8 else None,
            full_pan=None,
            phone=customer.phone if r.random() < 0.12 else None,
            email=customer.email if r.random() < 0.10 else None,
        )
        if r.random() < 0.15:
            d = "".join(r.choice("0123456789") for _ in range(12))
            ctx.full_pan = f"{r.choice('45')}{d[:3]} {d[3:7]} {d[7:11]} {txn.card.last4}"
        for k, v in kw.items():
            setattr(ctx, k, v)
        return ctx

    def b_duplicate(
        self, created: datetime, customer: models.Customer | None = None, serial: bool = False
    ) -> Planted:
        r = self.rng
        customer = customer or self.next_customer()
        card, m = self.card_of(customer), r.choice(self.by_cat(*ONLINE))
        amt = money(r, 150, 9500) if r.random() < 0.8 else money(r, 10500, 45000)
        t1 = created - timedelta(days=r.uniform(2, 100))
        kw: dict[str, Any] = {
            "card_id": card.id,
            "merchant_id": m.id,
            "amount": amt,
            "channel": TxnChannel.ECOM,
            "auth_method": AuthMethod.OTP_3DS,
        }
        self.add_txn(txn_time=t1, **kw)
        dup = self.add_txn(txn_time=t1 + timedelta(minutes=r.randint(1, 25)), **kw)
        limit = get_rules_config().thresholds.auto_max_amount_inr
        human = serial or amt > Decimal(str(limit))
        truth = {
            "reason_code": "DUPLICATE_CHARGE",
            "recommendation": "REFUND",
            "should_route_human": human,
        }
        return Planted(dup, self._ctx("DUPLICATE_CHARGE", dup, customer), truth, customer)

    def b_serial_duplicate(self, created: datetime) -> Planted:
        c = self.serial[self._serial_i % len(self.serial)]
        self._serial_i += 1
        return self.b_duplicate(created, customer=c, serial=True)

    _serial_i = 0

    def b_friendly_fraud(
        self, created: datetime, customer: models.Customer | None = None
    ) -> Planted:
        r = self.rng
        customer = customer or self.next_customer()
        card = self.card_of(customer)
        if r.random() < 0.7:
            m, ch, auth = r.choice(self.by_cat(*ONLINE)), TxnChannel.ECOM, AuthMethod.OTP_3DS
        else:
            m, ch, auth = r.choice(self.by_cat(C.RETAIL)), TxnChannel.POS, AuthMethod.PIN
        t = self.add_txn(card_id=card.id, merchant_id=m.id, amount=money(r, 500, 30000), txn_time=created - timedelta(days=r.uniform(5, 90)), channel=ch, auth_method=auth)  # fmt: skip
        truth = {
            "reason_code": "FRAUD_NOT_AUTHORISED",
            "recommendation": "REJECT",
            "should_route_human": True,
            "friendly_fraud": True,
        }
        return Planted(t, self._ctx("FRAUD_NOT_AUTHORISED", t, customer), truth, customer)

    def b_genuine_fraud(self, created: datetime) -> Planted:
        r = self.rng
        customer = self.next_customer()
        m = r.choice(self.fraud_merchants)
        t = self.add_txn(
            card_id=self.card_of(customer).id, merchant_id=m.id, amount=money(r, 3000, 60000),
            txn_time=created - timedelta(days=r.uniform(1, 40)), channel=TxnChannel.ECOM,
            auth_method=AuthMethod.NONE, details={"merchant_city": m.city, "unusual_merchant": True},
        )  # fmt: skip
        truth = {
            "reason_code": "FRAUD_NOT_AUTHORISED",
            "recommendation": "FILE_CHARGEBACK",
            "should_route_human": True,
        }
        return Planted(t, self._ctx("FRAUD_NOT_AUTHORISED", t, customer), truth, customer)

    def _online_txn(
        self, customer: models.Customer, created: datetime, days: tuple[float, float], **kw: Any
    ) -> models.Transaction:
        r = self.rng
        m = r.choice(self.by_cat(C.ECOMMERCE, C.TRAVEL))
        vals: dict[str, Any] = {
            "card_id": self.card_of(customer).id, "merchant_id": m.id, "amount": money(r, 400, 12000),
            "txn_time": created - timedelta(days=r.uniform(*days)), "channel": TxnChannel.ECOM,
            "auth_method": AuthMethod.OTP_3DS,
        }  # fmt: skip
        vals.update(kw)
        return self.add_txn(**vals)

    def b_gnr_clear(self, created: datetime) -> Planted:
        c = self.next_customer()
        t = self._online_txn(c, created, (10, 100))
        truth = {
            "reason_code": "GOODS_NOT_RECEIVED",
            "recommendation": "FILE_CHARGEBACK",
            "should_route_human": True,
        }
        return Planted(
            t,
            self._ctx(
                "GOODS_NOT_RECEIVED",
                t,
                c,
                style=self.rng.choice(["formal", "angry", "hinglish", "typos"]),
            ),
            truth,
            c,
        )

    def b_gnr_vague(self, created: datetime) -> Planted:
        c = self.next_customer()
        t = self._online_txn(c, created, (10, 80))
        with_merchant = self.rng.random() < 0.5
        ctx = self._ctx("GOODS_NOT_RECEIVED", t, c, vague=True, amount=None, date=None, last4=None)
        if not with_merchant:
            ctx.merchant = None
        truth = {
            "reason_code": "GOODS_NOT_RECEIVED",
            "recommendation": "NEED_MORE_INFO",
            "should_route_human": True,
        }
        return Planted(t, ctx, truth, c, match_checkable=False)

    def b_not_as_described(self, created: datetime) -> Planted:
        c = self.next_customer()
        t = self._online_txn(c, created, (10, 90))
        truth = {
            "reason_code": "NOT_AS_DESCRIBED",
            "recommendation": "FILE_CHARGEBACK",
            "should_route_human": True,
        }
        return Planted(t, self._ctx("NOT_AS_DESCRIBED", t, c), truth, c)

    def _sub_txn(
        self, c: models.Customer, created: datetime, cancelled: bool
    ) -> models.Transaction:
        r = self.rng
        card, m = self.card_of(c), r.choice(self.by_cat(C.SUBSCRIPTION))
        t_time = created - timedelta(days=r.uniform(3, 60))
        t = self.add_txn(card_id=card.id, merchant_id=m.id, amount=Decimal(r.choice(SUB_PRICES)), txn_time=t_time, channel=TxnChannel.RECURRING, auth_method=AuthMethod.NONE, is_recurring=True)  # fmt: skip
        self.session.add(
            models.Subscription(
                card_id=card.id, merchant_id=m.id,
                status=SubscriptionStatus.CANCELLED if cancelled else SubscriptionStatus.ACTIVE,
                cancelled_at=t_time - timedelta(days=r.uniform(3, 40)) if cancelled else None,
            )
        )  # fmt: skip
        return t

    def b_cancelled(self, created: datetime) -> Planted:
        c = self.next_customer()
        t = self._sub_txn(c, created, cancelled=True)
        truth = {
            "reason_code": "CANCELLED_RECURRING",
            "recommendation": "FILE_CHARGEBACK",
            "should_route_human": True,
        }
        return Planted(t, self._ctx("CANCELLED_RECURRING", t, c), truth, c)

    def b_cancelled_but_active(self, created: datetime) -> Planted:
        c = self.next_customer()
        t = self._sub_txn(c, created, cancelled=False)
        truth = {
            "reason_code": "CANCELLED_RECURRING",
            "recommendation": "REJECT",
            "should_route_human": True,
        }
        return Planted(t, self._ctx("CANCELLED_RECURRING", t, c), truth, c)

    def _atm_txn(
        self, c: models.Customer, created: datetime, days: tuple[float, float], dispensed: bool
    ) -> models.Transaction:
        r = self.rng
        amt = (
            Decimal(r.choice([500, 1000, 2000, 5000, 10000]))
            if r.random() < 0.85
            else Decimal(20000)
        )
        return self.add_txn(
            card_id=self.card_of(c).id, merchant_id=r.choice(self.by_cat(C.ATM)).id, amount=amt,
            txn_time=created - timedelta(days=r.uniform(*days)), channel=TxnChannel.ATM,
            auth_method=AuthMethod.PIN, account_debited=True, details={"cash_dispensed": dispensed},
        )  # fmt: skip

    def b_atm_failure(self, created: datetime) -> Planted:
        c = self.next_customer()
        t = self._atm_txn(c, created, (1, 25), dispensed=False)
        human = t.amount > Decimal(str(get_rules_config().thresholds.auto_max_amount_inr))
        truth = {
            "reason_code": "ATM_CASH_NOT_DISPENSED",
            "recommendation": "REFUND",
            "should_route_human": human,
        }
        return Planted(t, self._ctx("ATM_CASH_NOT_DISPENSED", t, c), truth, c)

    def b_atm_dispensed(self, created: datetime) -> Planted:
        c = self.next_customer()
        t = self._atm_txn(c, created, (1, 25), dispensed=True)
        truth = {
            "reason_code": "ATM_CASH_NOT_DISPENSED",
            "recommendation": "REJECT",
            "should_route_human": True,
        }
        return Planted(t, self._ctx("ATM_CASH_NOT_DISPENSED", t, c), truth, c)

    def b_refunded(self, created: datetime) -> Planted:
        c = self.next_customer()
        t = self._online_txn(c, created, (10, 90), refund_status=RefundStatus.FULL)
        self.add_txn(card_id=t.card_id, merchant_id=t.merchant_id, amount=-t.amount, txn_time=t.txn_time + timedelta(days=self.rng.randint(2, 9)), channel=TxnChannel.ECOM, auth_method=AuthMethod.NONE)  # fmt: skip
        truth = {
            "reason_code": "GOODS_NOT_RECEIVED",
            "recommendation": "REJECT",
            "should_route_human": True,
        }
        return Planted(t, self._ctx("GOODS_NOT_RECEIVED", t, c), truth, c)

    def b_out_of_window(self, created: datetime, kind: str | None = None) -> Planted:
        r = self.rng
        c = self.next_customer()
        kind = kind or r.choice(["gnr"] * 8 + ["fraud"] * 5 + ["dup"] * 4 + ["atm"] * 3)
        if kind == "atm":
            t = self._atm_txn(c, created, (35, 60), dispensed=False)
            code = "ATM_CASH_NOT_DISPENSED"
        elif kind == "dup":
            kw: dict[str, Any] = {"card_id": self.card_of(c).id, "merchant_id": r.choice(self.by_cat(*ONLINE)).id, "amount": money(r, 300, 8000), "channel": TxnChannel.ECOM, "auth_method": AuthMethod.OTP_3DS}  # fmt: skip
            base = created - timedelta(days=r.uniform(130, 250))
            self.add_txn(txn_time=base, **kw)
            t = self.add_txn(txn_time=base + timedelta(minutes=9), **kw)
            code = "DUPLICATE_CHARGE"
        elif kind == "fraud":
            t = self._online_txn(c, created, (125, 250), auth_method=AuthMethod.NONE)
            code = "FRAUD_NOT_AUTHORISED"
        else:
            t = self._online_txn(c, created, (125, 250))
            code = "GOODS_NOT_RECEIVED"
        truth = {
            "reason_code": code,
            "recommendation": "REJECT",
            "should_route_human": True,
            "out_of_window": True,
        }
        return Planted(t, self._ctx(code, t, c), truth, c)

    def b_incorrect_amount(self, created: datetime) -> Planted:
        r = self.rng
        c = self.next_customer()
        expected = money(r, 200, 6000)
        charged = (expected * Decimal(str(round(r.uniform(1.15, 2.0), 2)))).quantize(
            Decimal("0.01")
        )
        t = self._online_txn(c, created, (5, 90), amount=charged)
        ctx = self._ctx("INCORRECT_AMOUNT", t, c, expected_amount=f"Rs {expected:,.2f}")
        truth = {
            "reason_code": "INCORRECT_AMOUNT",
            "recommendation": "FILE_CHARGEBACK",
            "should_route_human": True,
            "expected_amount": str(expected),
        }
        return Planted(t, ctx, truth, c)

    def b_refund_not_processed(self, created: datetime) -> Planted:
        c = self.next_customer()
        t = self._online_txn(c, created, (15, 100))
        truth = {
            "reason_code": "REFUND_NOT_PROCESSED",
            "recommendation": "FILE_CHARGEBACK",
            "should_route_human": True,
        }
        return Planted(t, self._ctx("REFUND_NOT_PROCESSED", t, c), truth, c)

    def b_injection(self, created: datetime) -> Planted:
        kind = self.rng.choice(["ff", "ff", "ff", "ff", "oow", "oow", "oow", "ref", "ref", "ref"])
        p = (
            self.b_friendly_fraud(created) if kind == "ff"
            else self.b_out_of_window(created, "gnr") if kind == "oow"
            else self.b_refunded(created)
        )  # fmt: skip
        p.truth["prompt_injection"] = True
        p.ctx.injection = self.rng.choice(INJECTIONS)
        return p

    # ---- disputes -----------------------------------------------------------------------
    def history_disputes(self) -> None:
        """Past disputes that make the serial customers 'frequent disputers'."""
        r = self.rng
        for c in self.serial:
            for _ in range(3):
                t = self._online_txn(c, self.anchor, (30, 300))
                self.session.add(
                    models.Dispute(
                        customer_id=c.id, channel=DisputeChannel.FORM, raw_text="Earlier dispute (history).",
                        masked_text="Earlier dispute (history).", status=DisputeStatus.APPROVED,
                        matched_txn_id=t.id, created_at=self.anchor - timedelta(days=r.randint(15, 300)),
                    )
                )  # fmt: skip
        self.session.flush()

    def file_dispute(self, p: Planted, scenario: str, created: datetime) -> models.Dispute:
        r = self.rng
        style, inject = p.ctx.style, p.ctx.injection
        text = self.writer.write(r, p.ctx, style)
        if inject:
            text = f"{text} {inject}" if r.random() < 0.6 else f"{inject} {text}"
        truth = {
            **p.truth, "scenario": scenario, "txn_id": p.txn.id, "match_checkable": p.match_checkable,
            "style": style, "prompt_injection": p.truth.get("prompt_injection", False),
            "expected_auto_resolve": p.truth["recommendation"] == "REFUND" and not p.truth["should_route_human"],
        }  # fmt: skip
        d = models.Dispute(
            customer_id=p.customer.id, channel=r.choice(list(DisputeChannel)), raw_text=text,
            status=DisputeStatus.NEW, created_at=created, ground_truth=truth,
        )  # fmt: skip
        self.session.add(d)
        self.session.flush()
        return d


def assign_splits(
    disputes: list[tuple[str, models.Dispute]], rng: random.Random, n_test: int = 100
) -> None:
    """Stratified DEV/TEST split by scenario, using largest remainders to hit ``n_test`` exactly."""
    groups: dict[str, list[models.Dispute]] = defaultdict(list)
    for scenario, d in disputes:
        groups[scenario].append(d)
    total = len(disputes)
    quotas = {s: len(g) * n_test / total for s, g in groups.items()}
    take = {s: int(q) for s, q in quotas.items()}
    leftovers = sorted(quotas, key=lambda s: quotas[s] - take[s], reverse=True)
    for s in leftovers[: n_test - sum(take.values())]:
        take[s] += 1
    for s, g in groups.items():
        rng.shuffle(g)
        for i, d in enumerate(g):
            d.split = DataSplit.TEST if i < take[s] else DataSplit.DEV


def generate(
    session: Session,
    seed: int = 42,
    anchor: datetime | None = None,
    writer: ComplaintWriter | None = None,
    n_background: int = 5000,
) -> dict[str, Any]:
    """Populate the database. Returns a summary of what was created."""
    rng = random.Random(seed)
    anchor = (anchor or datetime.now(UTC).replace(minute=0, second=0, microsecond=0)).astimezone(
        UTC
    )
    g = Generator(session, rng, anchor, writer or TemplateWriter())
    g.build_world()
    g.background(n_background)
    g.history_disputes()

    builders: dict[str, Callable[[datetime], Planted]] = {
        "duplicate": g.b_duplicate,
        "serial_duplicate": g.b_serial_duplicate,
        "friendly_fraud": g.b_friendly_fraud,
        "genuine_fraud": g.b_genuine_fraud,
        "gnr_clear": g.b_gnr_clear,
        "gnr_vague": g.b_gnr_vague,
        "not_as_described": g.b_not_as_described,
        "cancelled_recurring": g.b_cancelled,
        "cancelled_but_active": g.b_cancelled_but_active,
        "atm_failure": g.b_atm_failure,
        "atm_cash_was_dispensed": g.b_atm_dispensed,
        "refunded_then_disputed": g.b_refunded,
        "out_of_window": g.b_out_of_window,
        "incorrect_amount": g.b_incorrect_amount,
        "refund_not_processed": g.b_refund_not_processed,
        "prompt_injection": g.b_injection,
    }
    jobs = [s for s, n in PLAN.items() for _ in range(n)]
    rng.shuffle(jobs)
    made: list[tuple[str, models.Dispute]] = []
    for scenario in jobs:
        created = anchor - timedelta(hours=rng.uniform(1, 7 * 24))
        planted = builders[scenario](created)
        made.append((scenario, g.file_dispute(planted, scenario, created)))
    assign_splits(made, rng)
    session.commit()

    split_counts = Counter(d.split.value for _, d in made if d.split)
    return {
        "seed": seed,
        "anchor": anchor.isoformat(),
        "customers": len(g.customers),
        "cards": sum(len(v) for v in g.cards_by_customer.values()),
        "merchants": len(g.merchants) + len(g.fraud_merchants),
        "disputes": len(made),
        "splits": dict(split_counts),
        "scenarios": dict(Counter(s for s, _ in made)),
    }
