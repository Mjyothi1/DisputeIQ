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
