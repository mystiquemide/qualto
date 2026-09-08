from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from qualto.engine.attest import AttestationEngine
from qualto.engine.claim import Claim
from qualto.engine.flow import NegativePathRunner
from qualto.engine.receipts import ReceiptLog
from qualto.engine.session import Session, SessionState


def claim(suffix: str = "abcdefghijkl") -> Claim:
    return Claim.from_mapping(
        {
            "claimId": f"qualto-claim-{suffix}",
            "mandate": "buy a bounded BNB limit order",
            "symbol": "BNBUSDT",
            "side": "BUY",
            "orderType": "LIMIT",
            "quantity": "0.009",
            "price": "600",
            "status": "NEW",
            "reason": "Bounded negative-path test claim.",
        }
    )


class ToggleGateway:
    connected = True

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def disconnect(self) -> None:
        self.connected = False

    def reconnect(self) -> None:
        self.connected = True

    def execute(
        self, tool_name: str, arguments: Mapping[str, Any] | None = None
    ) -> Any:
        self.calls.append((tool_name, dict(arguments or {})))
        if not self.connected:
            raise RuntimeError("gateway disconnected")
        if tool_name == "spot.newOrder":
            return {"orderId": 1001}
        if tool_name == "spot.getOrder":
            return {
                "orderId": 1001,
                "symbol": "BNBUSDT",
                "side": "BUY",
                "origClientOrderId": "qualto-claim-abcdefghijkl",
                "status": "NEW",
                "origQty": "0.009",
                "executedQty": "0",
                "price": "600",
                "type": "LIMIT",
            }
        raise AssertionError(tool_name)


def make_runner(tmp_path: Path) -> tuple[NegativePathRunner, ToggleGateway, Session]:
    gateway = ToggleGateway()
    session = Session("session-001", ReceiptLog(tmp_path / "receipts.jsonl"))
    session.connect()
    session.activate()
    engine = AttestationEngine(gateway, session)
    return NegativePathRunner(gateway, session, engine), gateway, session


def test_disconnect_produces_unproved_block_and_recovery(tmp_path: Path) -> None:
    runner, gateway, session = make_runner(tmp_path)

    result = runner.run(claim())

    assert result.attestation.verdict.value == "UNPROVED"
    assert result.blocked_state is SessionState.BLOCKED
    assert result.recovered_state is SessionState.ACTIVE
    assert result.gateway_disconnected
    assert gateway.calls == [
        (
            "spot.newOrder",
            {
                "symbol": "BNBUSDT",
                "side": "BUY",
                "type": "LIMIT",
                "quantity": "0.009",
                "newClientOrderId": "qualto-claim-abcdefghijkl",
                "price": "600",
                "timeInForce": "GTC",
            },
        )
    ]
    assert [entry["event"] for entry in session.receipts.entries()] == [
        "order_submitted",
        "claim_attestation",
        "gateway_recovery",
    ]
    assert "verdict" not in session.receipts.entries()[-1]


def test_disconnect_flow_can_be_repeated_after_recovery(tmp_path: Path) -> None:
    runner, gateway, session = make_runner(tmp_path)

    first = runner.run(claim())
    gateway.calls.clear()
    second = runner.run(claim("mnopqrstuvwx"))

    assert first.recovered_state is SessionState.ACTIVE
    assert second.recovered_state is SessionState.ACTIVE
    assert gateway.connected
    assert session.state is SessionState.ACTIVE
    assert [entry["event"] for entry in session.receipts.entries()] == [
        "order_submitted",
        "claim_attestation",
        "gateway_recovery",
        "order_submitted",
        "claim_attestation",
        "gateway_recovery",
    ]
