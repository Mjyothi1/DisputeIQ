import pytest

from app.services.pii import mask_card_number, mask_pii


@pytest.mark.parametrize(
    "raw",
    [
        "4111 1111 1111 1234",
        "4111-1111-1111-1234",
        "4111111111111234",
        "5500 0000 0000 0004 1234"[:19],
    ],
)
def test_card_numbers_keep_only_last4(raw: str) -> None:
    out = mask_pii(f"my card {raw} was used").text
    assert "XXXX-XXXX-XXXX-" in out
    assert raw.replace(" ", "")[:8] not in out.replace(" ", "").replace("-", "")


def test_card_last4_preserved() -> None:
    assert mask_card_number("4111 1111 1111 9876") == "XXXX-XXXX-XXXX-9876"
    assert mask_pii("card 4111 1111 1111 9876.").text.endswith("XXXX-XXXX-XXXX-9876.")


@pytest.mark.parametrize(
    "phone", ["+919876543210", "9876543210", "98765 43210", "+91 98765 43210", "09876543210"]
)
def test_phone_formats(phone: str) -> None:
    res = mask_pii(f"call me on {phone} please")
    assert res.text == "call me on [PHONE] please" and res.counts == {"phone": 1}


def test_email() -> None:
    res = mask_pii("write to asha.rao@example.co.in now")
    assert res.text == "write to [EMAIL] now" and res.counts == {"email": 1}


def test_account_number_keyword_anchored() -> None:
    res = mask_pii("debited from account number 123456789012 yesterday")
    assert "123456789012" not in res.text and "[ACCOUNT]" in res.text
    assert mask_pii("a/c no: 50100234567890").counts.get("account") == 1


@pytest.mark.parametrize(
    "text",
    [
        "I paid Rs 12,345.50 on 21 Oct",
        "order 123456789012 not delivered",
        "INR 1,00,000 charged",
        "card ending 1234",
    ],
)
def test_no_false_positives(text: str) -> None:
    assert mask_pii(text).text == text


def test_idempotent_and_counts() -> None:
    raw = "Card 4111 1111 1111 1234, ph 9876543210, mail a@b.com"
    once = mask_pii(raw)
    assert once.counts == {"email": 1, "card": 1, "phone": 1} and once.total == 3
    assert mask_pii(once.text).text == once.text


def test_multiple_in_one_text() -> None:
    res = mask_pii("9876543210 and 9123456780")
    assert res.counts == {"phone": 2}


# ---- P1.2: extended identifier coverage (all values are synthetic) ---------------------------
@pytest.mark.parametrize(
    "text,gone,tag",
    [
        ("my aadhaar is 2345 6789 0123", "2345 6789 0123", "[AADHAAR]"),
        ("Aadhaar number 234567890123 shared", "234567890123", "[AADHAAR]"),
        ("id 2345-6789-0123 given", "2345-6789-0123", "[AADHAAR]"),
        ("PAN is ABCDE1234F ok", "ABCDE1234F", "[PAN_ID]"),
        ("pan abcde1234f", "abcde1234f", "[PAN_ID]"),
        ("cvv 123 was entered", "123", "[CVV]"),
        ("CVV is 4567", "4567", "[CVV]"),
        ("otp is 482913 shared", "482913", "[OTP]"),
        ("OTP: 123456", "123456", "[OTP]"),
        ("654321 is my OTP", "654321", "[OTP]"),
        ("card expiry 12/27", "12/27", "[EXPIRY]"),
        ("valid thru 08/2028", "08/2028", "[EXPIRY]"),
        ("paid via ravi.kumar@okhdfcbank today", "ravi.kumar@okhdfcbank", "[UPI_ID]"),
        ("upi 9876543210@ybl", "9876543210@ybl", "[UPI_ID]"),
    ],
)
def test_extended_identifiers_are_masked(text: str, gone: str, tag: str) -> None:
    res = mask_pii(text)
    assert gone not in res.text and tag in res.text, res.text


@pytest.mark.parametrize(
    "text",
    [
        "order number 123456789012 was delayed",
        "reference 4455667 for my complaint",
        "I paid Rs 20,000 on 22/10/2026",
        "I received no OTP and no message",
        "the transaction id is TXN20261022",
        "I tried 2-3 times at 10 pm",
    ],
)
def test_harmless_numbers_are_left_alone(text: str) -> None:
    assert mask_pii(text).text == text


def test_email_still_masked_and_not_confused_with_upi() -> None:
    res = mask_pii("write to a.b@example.com")
    assert res.text == "write to [EMAIL]" and res.counts == {"email": 1}
