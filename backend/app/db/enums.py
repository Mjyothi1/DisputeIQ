"""Enumerations shared by the DB models, rules engine and API schemas."""

import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        """Backport of StrEnum for Python 3.10."""

        def __str__(self) -> str:
            return self.value


class CardNetwork(StrEnum):
    VISA = "VISA"
    MASTERCARD = "MASTERCARD"
    RUPAY = "RUPAY"


class CardStatus(StrEnum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    CLOSED = "CLOSED"


class MerchantCategory(StrEnum):
    ECOMMERCE = "ECOMMERCE"
    FOOD_DELIVERY = "FOOD_DELIVERY"
    TRAVEL = "TRAVEL"
    SUBSCRIPTION = "SUBSCRIPTION"
    RETAIL = "RETAIL"
    ATM = "ATM"


class TxnChannel(StrEnum):
    POS = "POS"
    ECOM = "ECOM"
    ATM = "ATM"
    RECURRING = "RECURRING"


class AuthMethod(StrEnum):
    OTP_3DS = "OTP_3DS"
    PIN = "PIN"
    NONE = "NONE"


class TxnStatus(StrEnum):
    SETTLED = "SETTLED"
    REVERSED = "REVERSED"
    FAILED = "FAILED"


class RefundStatus(StrEnum):
    NONE = "NONE"
    PARTIAL = "PARTIAL"
    FULL = "FULL"


class SubscriptionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"


class DisputeChannel(StrEnum):
    FORM = "FORM"
    EMAIL = "EMAIL"
    CHAT = "CHAT"


class DisputeStatus(StrEnum):
    NEW = "NEW"
    PROCESSING = "PROCESSING"
    AUTO_RESOLVED = "AUTO_RESOLVED"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    OVERRIDDEN = "OVERRIDDEN"


class DataSplit(StrEnum):
    """Synthetic-data split. The agent never reads ground_truth; eval uses TEST only."""

    DEV = "DEV"
    TEST = "TEST"


class Recommendation(StrEnum):
    REFUND = "REFUND"
    FILE_CHARGEBACK = "FILE_CHARGEBACK"
    REJECT = "REJECT"
    NEED_MORE_INFO = "NEED_MORE_INFO"


class ReviewAction(StrEnum):
    APPROVE = "APPROVE"
    EDIT = "EDIT"
    OVERRIDE = "OVERRIDE"
    REJECT = "REJECT"


class AuditActor(StrEnum):
    AGENT = "AGENT"
    TOOL = "TOOL"
    HUMAN = "HUMAN"
