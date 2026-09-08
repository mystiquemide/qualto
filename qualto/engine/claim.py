"""Strict claim schema and order-request normalization."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any


class ClaimValidationError(ValueError):
    """Raised when a model or operator claim is invalid."""


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class ClaimStatus(StrEnum):
    NEW = "NEW"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELED = "CANCELED"


_CLAIM_ID_PATTERN = re.compile(r"^qualto-claim-[a-z0-9]{12}$")
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{5,20}$")


def _decimal(value: Any, field_name: str) -> Decimal:
    if isinstance(value, (bool, float)):
        raise ClaimValidationError(f"{field_name} must be a decimal string or integer")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ClaimValidationError(f"{field_name} must be a valid decimal") from exc
    if not result.is_finite():
        raise ClaimValidationError(f"{field_name} must be finite")
    return result


def _positive_decimal(value: Any, field_name: str) -> Decimal:
    result = _decimal(value, field_name)
    if result <= 0:
        raise ClaimValidationError(f"{field_name} must be greater than zero")
    return result


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def mint_claim_id(suffix: str | None = None) -> str:
    """Mint a claim ID with a stable, exchange-safe alphabet."""

    token = suffix if suffix is not None else uuid.uuid4().hex[:12]
    if not isinstance(token, str) or not re.fullmatch(r"[a-z0-9]{12}", token):
        raise ClaimValidationError(
            "claim ID suffix must contain exactly 12 lowercase alphanumerics"
        )
    return f"qualto-claim-{token}"


@dataclass(frozen=True, slots=True)
class Claim:
    """A schema-validated, exchange-bound trading claim."""

    claim_id: str
    mandate: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Decimal | None
    status: ClaimStatus
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.claim_id, str) or not _CLAIM_ID_PATTERN.fullmatch(
            self.claim_id
        ):
            raise ClaimValidationError("claim_id has an invalid format")
        if (
            not isinstance(self.mandate, str)
            or not 1 <= len(self.mandate.strip()) <= 500
        ):
            raise ClaimValidationError("mandate must contain 1 to 500 characters")
        if not isinstance(self.symbol, str) or not _SYMBOL_PATTERN.fullmatch(
            self.symbol
        ):
            raise ClaimValidationError("symbol must be uppercase alphanumeric text")
        if not isinstance(self.side, OrderSide):
            raise ClaimValidationError("side is invalid")
        if not isinstance(self.order_type, OrderType):
            raise ClaimValidationError("order_type is invalid")
        if (
            not isinstance(self.quantity, Decimal)
            or self.quantity <= 0
            or not self.quantity.is_finite()
        ):
            raise ClaimValidationError("quantity must be a finite positive decimal")
        if self.order_type is OrderType.LIMIT:
            if self.price is None or self.price <= 0 or not self.price.is_finite():
                raise ClaimValidationError(
                    "limit claims require a finite positive price"
                )
        elif self.price is not None:
            raise ClaimValidationError("market claims cannot include a limit price")
        if not isinstance(self.status, ClaimStatus):
            raise ClaimValidationError("status is invalid")
        if (
            not isinstance(self.reason, str)
            or not 1 <= len(self.reason.strip()) <= 1000
        ):
            raise ClaimValidationError("reason must contain 1 to 1000 characters")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> Claim:
        """Parse strict external claim JSON and reject unknown fields."""

        if not isinstance(payload, Mapping):
            raise ClaimValidationError("claim must be an object")
        expected = {
            "claimId",
            "mandate",
            "symbol",
            "side",
            "orderType",
            "quantity",
            "price",
            "status",
            "reason",
        }
        actual = set(payload)
        unknown = actual - expected
        missing = expected - actual
        if unknown:
            raise ClaimValidationError("claim contains unknown fields")
        if missing:
            raise ClaimValidationError("claim is missing required fields")
        try:
            side = OrderSide(str(payload["side"]).upper())
            order_type = OrderType(str(payload["orderType"]).upper())
            status = ClaimStatus(str(payload["status"]).upper())
        except ValueError as exc:
            raise ClaimValidationError("claim enum value is invalid") from exc
        price_value = payload["price"]
        price = None if price_value is None else _positive_decimal(price_value, "price")
        quantity = _positive_decimal(payload["quantity"], "quantity")
        return cls(
            claim_id=payload["claimId"],
            mandate=payload["mandate"],
            symbol=payload["symbol"].upper()
            if isinstance(payload["symbol"], str)
            else payload["symbol"],
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status=status,
            reason=payload["reason"],
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "claimId": self.claim_id,
            "mandate": self.mandate,
            "symbol": self.symbol,
            "side": self.side.value,
            "orderType": self.order_type.value,
            "quantity": _decimal_text(self.quantity),
            "price": None if self.price is None else _decimal_text(self.price),
            "status": self.status.value,
            "reason": self.reason,
        }

    def to_order_arguments(self) -> dict[str, Any]:
        """Create the only order payload the gateway is allowed to send.

        Binance accepts decimal strings for these fields. Keeping the canonical
        text avoids converting user-approved quantities or prices through float.
        """

        arguments: dict[str, Any] = {
            "symbol": self.symbol,
            "side": self.side.value,
            "type": self.order_type.value,
            "quantity": _decimal_text(self.quantity),
            "newClientOrderId": self.claim_id,
        }
        if self.order_type is OrderType.LIMIT:
            if self.price is None:
                raise ClaimValidationError("limit claims require a price")
            arguments["price"] = _decimal_text(self.price)
            arguments["timeInForce"] = "GTC"
        return arguments
