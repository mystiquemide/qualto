from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pytest

from qualto.engine.attest import (
    AttestationEngine,
    CancellationError,
    ExchangeOrder,
    RetryPolicy,
    Verdict,
    compare_claim_to_order,
)
from qualto.engine.claim import Claim
from qualto.engine.receipts import ReceiptLog
from qualto.engine.session import ClaimReplayError, Session


def claim_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "claimId": "qualto-claim-abcdefghijkl",
        "mandate": "buy five USDT of BNB",
        "symbol": "BNBUSDT",
        "side": "BUY",
        "orderType": "LIMIT",
        "quantity": "0.008",
        "price": "625.00",
        "status": "NEW",
        "reason": "Small bounded limit order.",
    }
    payload.update(overrides)
    return payload


def order_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "orderId": 1001,
        "symbol": "BNBUSDT",
        "side": "BUY",
        "origClientOrderId": "qualto-claim-abcdefghijkl",
        "status": "NEW",
        "origQty": "0.008",
        "executedQty": "0",
        "price": "625.00",
        "type": "LIMIT",
    }
    payload.update(overrides)
    return payload


def make_claim(**overrides: Any) -> Claim:
    return Claim.from_mapping(claim_payload(**overrides))


def make_order(**overrides: Any) -> ExchangeOrder:
    return ExchangeOrder.from_mapping(order_payload(**overrides))


def test_matching_order_is_proved() -> None:
    result = compare_claim_to_order(make_claim(), make_order())

    assert result.verdict is Verdict.PROVED
    assert all(field.matched for field in result.fields)


def test_exchange_order_accepts_binance_client_order_id_alias() -> None:
    payload = order_payload()
    payload.pop("origClientOrderId")
    payload["clientOrderId"] = "qualto-claim-abcdefghijkl"

    order = ExchangeOrder.from_mapping(payload)

    assert order.orig_client_order_id == "qualto-claim-abcdefghijkl"


@pytest.mark.parametrize(
    "field,change",
    [
        ("symbol", "ETHUSDT"),
        ("side", "SELL"),
        ("origQty", "0.009"),
        ("price", "640.00"),
        ("origClientOrderId", "qualto-claim-other1"),
    ],
)
def test_mismatched_identity_or_fields_are_unproved(field: str, change: str) -> None:
    result = compare_claim_to_order(make_claim(), make_order(**{field: change}))

    assert result.verdict is Verdict.UNPROVED
    assert any(not field_result.matched for field_result in result.fields)


def test_partial_fill_is_explicit_partial() -> None:
    result = compare_claim_to_order(
        make_claim(status="FILLED"),
        make_order(status="PARTIALLY_FILLED", executedQty="0.004"),
    )

    assert result.verdict is Verdict.PARTIAL
    assert result.executed_qty == "0.004"


def test_market_order_new_is_pending() -> None:
    result = compare_claim_to_order(
        make_claim(orderType="MARKET", price=None, status="FILLED"),
        make_order(type="MARKET", status="NEW", price="0"),
    )

    assert result.verdict is Verdict.PENDING


class FakeGateway:
    def __init__(self, order: Mapping[str, Any] | None = None, *, fail: bool = False) -> None:
        self.order = dict(order or order_payload())
        self.fail = fail
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(self, tool_name: str, arguments: Mapping[str, Any] | None = None) -> Any:
        args = dict(arguments or {})
        self.calls.append((tool_name, args))
        if self.fail:
            raise RuntimeError("provider unavailable")
        if tool_name == "spot.newOrder":
            return {"orderId": self.order["orderId"]}
        if tool_name == "spot.getOrder":
            return dict(self.order)
        if tool_name == "spot.deleteOrder":
            cancelled = dict(self.order)
            cancelled["status"] = "CANCELED"
            return cancelled
        raise AssertionError(f"unexpected tool {tool_name}")


def make_engine(tmp_path: Path, gateway: FakeGateway) -> AttestationEngine:
    session = Session("session-001", ReceiptLog(tmp_path / "receipts.jsonl"))
    session.connect()
    session.activate()
    return AttestationEngine(gateway, session, retry_policy=RetryPolicy(attempts=1, delay_seconds=0))


def test_engine_places_claim_bound_order_and_reads_by_both_ids(tmp_path: Path) -> None:
    gateway = FakeGateway()
    engine = make_engine(tmp_path, gateway)

    result = engine.place_and_attest(make_claim())

    assert result.verdict is Verdict.PROVED
    assert gateway.calls[0] == (
        "spot.newOrder",
        {
            "symbol": "BNBUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "quantity": 0.008,
            "newClientOrderId": "qualto-claim-abcdefghijkl",
            "price": 625.0,
            "timeInForce": "GTC",
        },
    )
    readbacks = gateway.calls[1:]
    assert readbacks == [
        ("spot.getOrder", {"symbol": "BNBUSDT", "orderId": 1001}),
        ("spot.getOrder", {"symbol": "BNBUSDT", "origClientOrderId": "qualto-claim-abcdefghijkl"}),
    ]

    receipt = engine.session.receipts.entries()[-1]
    assert receipt["orderResponse"] == {"orderId": 1001}
    assert receipt["readbackByOrderId"]["orderId"] == 1001
    assert receipt["readbackByOrigClientOrderId"]["origClientOrderId"] == "qualto-claim-abcdefghijkl"


def test_engine_failure_blocks_session_and_records_receipt(tmp_path: Path) -> None:
    gateway = FakeGateway(fail=True)
    engine = make_engine(tmp_path, gateway)

    result = engine.place_and_attest(make_claim())

    assert result.verdict is Verdict.UNPROVED
    entries = engine.session.receipts.entries()
    assert entries[-1]["attestation"]["verdict"] == "UNPROVED"
    with pytest.raises(Exception):
        engine.session.assert_can_write()


def test_duplicate_claim_is_rejected_and_logged(tmp_path: Path) -> None:
    gateway = FakeGateway()
    engine = make_engine(tmp_path, gateway)
    claim = make_claim()
    assert engine.place_and_attest(claim).verdict is Verdict.PROVED

    with pytest.raises(ClaimReplayError):
        engine.place_and_attest(claim)

    assert engine.session.receipts.entries()[-1]["event"] == "claim_rejected"


def test_engine_cancels_the_exact_claim_bound_order(tmp_path: Path) -> None:
    gateway = FakeGateway()
    engine = make_engine(tmp_path, gateway)
    claim = make_claim()
    placed = engine.place_and_attest(claim)

    cancelled = engine.cancel_order(claim, placed.order_id or 0)

    assert cancelled.status == "CANCELED"
    assert gateway.calls[-1] == ("spot.deleteOrder", {"symbol": "BNBUSDT", "orderId": 1001})
    assert engine.session.receipts.entries()[-1]["verdict"] == "PROVED"


def test_failed_cancellation_blocks_the_session(tmp_path: Path) -> None:
    gateway = FakeGateway()
    engine = make_engine(tmp_path, gateway)
    claim = make_claim()
    engine.place_and_attest(claim)
    gateway.fail = True

    with pytest.raises(CancellationError):
        engine.cancel_order(claim, 1001)

    assert engine.session.block_reason == "order cancellation could not be proved"
