"""Claim-bound order placement, readback, field diffing, and enforcement."""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Callable, Mapping, Protocol

from .claim import Claim, ClaimStatus, OrderType
from .session import ClaimReplayError, Session


class Verdict(StrEnum):
    PROVED = "PROVED"
    UNPROVED = "UNPROVED"
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"


class Gateway(Protocol):
    def execute(self, tool_name: str, arguments: Mapping[str, Any] | None = None) -> Any:
        """Execute one allowlisted Binance operation."""


_ORDER_RECEIPT_FIELDS = frozenset(
    {
        "orderId",
        "symbol",
        "side",
        "origClientOrderId",
        "status",
        "origQty",
        "executedQty",
        "price",
        "type",
        "time",
        "updateTime",
    }
)


def _safe_order_receipt(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return {key: value[key] for key in _ORDER_RECEIPT_FIELDS if key in value}


def _decimal(value: Any, field_name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"exchange field {field_name} is invalid") from exc
    if not result.is_finite():
        raise ValueError(f"exchange field {field_name} is invalid")
    return result


@dataclass(frozen=True, slots=True)
class ExchangeOrder:
    order_id: int
    symbol: str
    side: str
    orig_client_order_id: str
    status: str
    orig_qty: Decimal
    executed_qty: Decimal
    price: Decimal
    order_type: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExchangeOrder":
        if not isinstance(payload, Mapping):
            raise ValueError("exchange order is not an object")
        order_id = payload.get("orderId")
        if isinstance(order_id, bool):
            raise ValueError("exchange order ID is invalid")
        try:
            order_id_int = int(order_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("exchange order ID is invalid") from exc
        if order_id_int <= 0:
            raise ValueError("exchange order ID is invalid")
        required_text = ("symbol", "side", "origClientOrderId", "status", "type")
        if any(not isinstance(payload.get(key), str) or not payload[key] for key in required_text):
            raise ValueError("exchange order text fields are invalid")
        orig_qty = _decimal(payload.get("origQty"), "origQty")
        executed_qty = _decimal(payload.get("executedQty"), "executedQty")
        price = _decimal(payload.get("price", "0"), "price")
        if orig_qty < 0 or executed_qty < 0 or price < 0 or executed_qty > orig_qty:
            raise ValueError("exchange order numeric fields are invalid")
        return cls(
            order_id=order_id_int,
            symbol=payload["symbol"],
            side=payload["side"],
            orig_client_order_id=payload["origClientOrderId"],
            status=payload["status"],
            orig_qty=orig_qty,
            executed_qty=executed_qty,
            price=price,
            order_type=payload["type"],
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "orderId": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "origClientOrderId": self.orig_client_order_id,
            "status": self.status,
            "origQty": format(self.orig_qty, "f"),
            "executedQty": format(self.executed_qty, "f"),
            "price": format(self.price, "f"),
            "type": self.order_type,
        }


@dataclass(frozen=True, slots=True)
class DiffField:
    name: str
    expected: str | None
    actual: str | None
    matched: bool

    def to_mapping(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "expected": self.expected,
            "actual": self.actual,
            "matched": self.matched,
        }


@dataclass(frozen=True, slots=True)
class Attestation:
    claim_id: str
    verdict: Verdict
    order_id: int | None
    reason: str
    fields: tuple[DiffField, ...]
    executed_qty: str | None = None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "claimId": self.claim_id,
            "verdict": self.verdict.value,
            "orderId": self.order_id,
            "reason": self.reason,
            "fields": [field.to_mapping() for field in self.fields],
            "executedQty": self.executed_qty,
        }


def _price_matches(expected: Decimal | None, actual: Decimal) -> bool:
    if expected is None:
        return True
    if expected <= 0:
        return False
    tolerance = expected * Decimal("0.005")
    return abs(actual - expected) <= tolerance


def compare_claim_to_order(claim: Claim, order: ExchangeOrder) -> Attestation:
    """Compare only exchange fields required by the claim contract."""

    quantity_match = order.orig_qty == claim.quantity
    price_match = _price_matches(claim.price, order.price)
    fields = (
        DiffField("claimId", claim.claim_id, order.orig_client_order_id, claim.claim_id == order.orig_client_order_id),
        DiffField("symbol", claim.symbol, order.symbol, claim.symbol == order.symbol),
        DiffField("side", claim.side.value, order.side, claim.side.value == order.side),
        DiffField("quantity", format(claim.quantity, "f"), format(order.orig_qty, "f"), quantity_match),
        DiffField(
            "price",
            None if claim.price is None else format(claim.price, "f"),
            format(order.price, "f"),
            price_match,
        ),
        DiffField("status", claim.status.value, order.status, claim.status.value == order.status),
    )
    identity_matches = all(field.matched for field in fields[:5])
    executed_qty = format(order.executed_qty, "f")
    if not identity_matches:
        return Attestation(claim.claim_id, Verdict.UNPROVED, order.order_id, "exchange fields do not match", fields, executed_qty)
    if order.status == "PARTIALLY_FILLED":
        return Attestation(claim.claim_id, Verdict.PARTIAL, order.order_id, "order is partially filled", fields, executed_qty)
    if (
        order.status == "NEW"
        and claim.status is ClaimStatus.FILLED
        and claim.order_type is OrderType.MARKET
    ):
        return Attestation(claim.claim_id, Verdict.PENDING, order.order_id, "market order is still pending", fields, executed_qty)
    if not fields[-1].matched:
        return Attestation(claim.claim_id, Verdict.UNPROVED, order.order_id, "exchange status does not match", fields, executed_qty)
    if claim.status is ClaimStatus.FILLED and order.executed_qty != claim.quantity:
        return Attestation(claim.claim_id, Verdict.UNPROVED, order.order_id, "filled quantity does not match", fields, executed_qty)
    return Attestation(claim.claim_id, Verdict.PROVED, order.order_id, "all claim fields match", fields, executed_qty)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 3
    delay_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts must be positive")
        if self.delay_seconds < 0:
            raise ValueError("delay_seconds cannot be negative")


class AttestationEngine:
    """Make claim-bound writes and enforce session-wide failure behavior."""

    def __init__(
        self,
        gateway: Gateway,
        session: Session,
        *,
        retry_policy: RetryPolicy | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.gateway = gateway
        self.session = session
        self.retry_policy = retry_policy or RetryPolicy()
        self.sleeper = sleeper

    def place_and_attest(self, claim: Claim) -> Attestation:
        self.session.assert_can_write()
        try:
            self.session.reserve_claim_id(claim.claim_id)
        except ClaimReplayError:
            self.session.record(
                {
                    "event": "claim_rejected",
                    "claimId": claim.claim_id,
                    "verdict": Verdict.UNPROVED.value,
                    "reason": "claim ID was already used in this session",
                }
            )
            raise

        try:
            placement = self.gateway.execute("spot.newOrder", claim.to_order_arguments())
            order_id = int(placement["orderId"])
        except Exception as exc:
            return self._fail_closed(claim, "order placement failed", exc)

        last_by_order_id: dict[str, Any] | None = None
        last_by_client_id: dict[str, Any] | None = None
        for attempt in range(self.retry_policy.attempts):
            try:
                by_order_id = self.gateway.execute(
                    "spot.getOrder", {"symbol": claim.symbol, "orderId": order_id}
                )
                by_client_id = self.gateway.execute(
                    "spot.getOrder",
                    {"symbol": claim.symbol, "origClientOrderId": claim.claim_id},
                )
                first = ExchangeOrder.from_mapping(by_order_id)
                second = ExchangeOrder.from_mapping(by_client_id)
                last_by_order_id = first.to_mapping()
                last_by_client_id = second.to_mapping()
                if first.order_id != second.order_id:
                    return self._fail_closed(
                        claim,
                        "order readbacks disagree",
                        None,
                        placement=placement,
                        order_id=order_id,
                    )
                attestation = compare_claim_to_order(claim, first)
                if attestation.verdict is not Verdict.PENDING:
                    return self._record_attestation(
                        claim,
                        placement,
                        last_by_order_id,
                        last_by_client_id,
                        attestation,
                    )
            except Exception as exc:
                if attempt == self.retry_policy.attempts - 1:
                    return self._fail_closed(
                        claim,
                        "order readback failed",
                        exc,
                        placement=placement,
                        order_id=order_id,
                    )
            if attempt < self.retry_policy.attempts - 1:
                self.sleeper(self.retry_policy.delay_seconds)

        return self._fail_closed(
            claim,
            "order readback remained pending",
            None,
            placement=placement,
            order_id=order_id,
        )

    def _record_attestation(
        self,
        claim: Claim,
        placement: Any,
        readback_by_order_id: Mapping[str, Any] | None,
        readback_by_client_id: Mapping[str, Any] | None,
        attestation: Attestation,
    ) -> Attestation:
        self.session.record(
            {
                "event": "claim_attestation",
                "claim": claim.to_mapping(),
                "orderResponse": _safe_order_receipt(placement),
                "readbackByOrderId": _safe_order_receipt(readback_by_order_id),
                "readbackByOrigClientOrderId": _safe_order_receipt(readback_by_client_id),
                "attestation": attestation.to_mapping(),
            }
        )
        if attestation.verdict is Verdict.UNPROVED:
            self.session.block("claim could not be proved")
        return attestation

    def _fail_closed(
        self,
        claim: Claim,
        reason: str,
        cause: Exception | None,
        *,
        placement: Any = None,
        order_id: int | None = None,
    ) -> Attestation:
        del cause
        attestation = Attestation(claim.claim_id, Verdict.UNPROVED, order_id, reason, ())
        self.session.block(
            reason,
            receipt={
                "event": "claim_attestation",
                "claim": claim.to_mapping(),
                "orderResponse": _safe_order_receipt(placement),
                "attestation": attestation.to_mapping(),
            },
        )
        return attestation
