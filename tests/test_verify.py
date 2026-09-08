from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from qualto.engine.verify import VerificationError, verify_receipts


def claim_payload(
    claim_id: str = "qualto-claim-abcdefghijkl", **overrides: Any
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "claimId": claim_id,
        "mandate": "buy a bounded BNB limit order",
        "symbol": "BNBUSDT",
        "side": "BUY",
        "orderType": "LIMIT",
        "quantity": "0.006",
        "price": "700",
        "status": "NEW",
        "reason": "Read-only receipt verification fixture.",
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
        "origQty": "0.006",
        "executedQty": "0",
        "price": "700",
        "type": "LIMIT",
    }
    payload.update(overrides)
    return payload


def receipt(
    *,
    claim: Mapping[str, Any] | None = None,
    order_id: int | None = 1001,
    verdict: str = "PROVED",
) -> dict[str, Any]:
    return {
        "event": "claim_attestation",
        "claim": dict(claim or claim_payload()),
        "attestation": {"orderId": order_id, "verdict": verdict},
    }


class ReadOnlyGateway:
    def __init__(self, order: Mapping[str, Any] | None = None, *, fail: bool = False):
        self.order = dict(order or order_payload())
        self.fail = fail
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(
        self, tool_name: str, arguments: Mapping[str, Any] | None = None
    ) -> Any:
        self.calls.append((tool_name, dict(arguments or {})))
        if self.fail:
            raise RuntimeError("readback unavailable")
        assert tool_name == "spot.getOrder"
        return dict(self.order)


def write_receipts(path: Path, *entries: Mapping[str, Any]) -> None:
    path.write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8"
    )


def test_verify_replays_proved_claim_against_order_id(tmp_path: Path) -> None:
    path = tmp_path / "receipts.jsonl"
    gateway = ReadOnlyGateway()
    write_receipts(path, receipt())

    results = verify_receipts(path, gateway)

    assert len(results) == 1
    assert results[0].matched
    assert results[0].live_verdict is not None
    assert results[0].live_verdict.value == "PROVED"
    assert gateway.calls == [("spot.getOrder", {"symbol": "BNBUSDT", "orderId": 1001})]


def test_verify_detects_an_edited_claim_payload(tmp_path: Path) -> None:
    path = tmp_path / "receipts.jsonl"
    edited_claim = claim_payload(quantity="0.007")
    write_receipts(path, receipt(claim=edited_claim))

    result = verify_receipts(path, ReadOnlyGateway())[0]

    assert result.live_verdict is not None
    assert result.live_verdict.value == "UNPROVED"
    assert not result.matched
    assert "differs" in result.reason


def test_verify_accepts_a_recorded_unproved_live_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "receipts.jsonl"
    write_receipts(
        path,
        receipt(
            verdict="UNPROVED",
        ),
    )
    gateway = ReadOnlyGateway(order=order_payload(status="CANCELED"))

    result = verify_receipts(path, gateway)[0]

    assert result.live_verdict is not None
    assert result.live_verdict.value == "UNPROVED"
    assert result.matched


def test_verify_does_not_call_gateway_when_receipt_has_no_order_id(
    tmp_path: Path,
) -> None:
    path = tmp_path / "receipts.jsonl"
    gateway = ReadOnlyGateway()
    write_receipts(path, receipt(order_id=None, verdict="UNPROVED"))

    result = verify_receipts(path, gateway)[0]

    assert not result.matched
    assert result.live_verdict is None
    assert gateway.calls == []
    assert "no order ID" in result.reason


def test_verify_marks_gateway_failure_without_exposing_provider_error(
    tmp_path: Path,
) -> None:
    path = tmp_path / "receipts.jsonl"
    write_receipts(path, receipt())

    result = verify_receipts(path, ReadOnlyGateway(fail=True))[0]

    assert not result.matched
    assert result.live_verdict is None
    assert result.reason == "live order readback could not be verified"


def test_verify_ignores_non_attestation_events_and_replays_each_attestation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "receipts.jsonl"
    second_claim = claim_payload("qualto-claim-mnopqrstuvwx")
    second_order = order_payload(
        orderId=1002, origClientOrderId="qualto-claim-mnopqrstuvwx"
    )
    write_receipts(
        path,
        {"event": "order_submitted", "outcome": "requested"},
        receipt(),
        receipt(claim=second_claim, order_id=1002),
    )

    class TwoOrderGateway(ReadOnlyGateway):
        def execute(
            self, tool_name: str, arguments: Mapping[str, Any] | None = None
        ) -> Any:
            super().execute(tool_name, arguments)
            return dict(
                order_payload(
                    **(
                        second_order
                        if arguments and arguments.get("orderId") == 1002
                        else {}
                    )
                )
            )

    gateway = TwoOrderGateway()
    results = verify_receipts(path, gateway)

    assert [result.order_id for result in results] == [1001, 1002]
    assert all(result.matched for result in results)
    assert len(gateway.calls) == 2


def test_verify_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "receipts.jsonl"
    path.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(VerificationError, match="invalid JSON"):
        verify_receipts(path, ReadOnlyGateway())


def test_verify_requires_at_least_one_attestation(tmp_path: Path) -> None:
    path = tmp_path / "receipts.jsonl"
    write_receipts(path, {"event": "order_submitted"})

    with pytest.raises(VerificationError, match="no claim attestations"):
        verify_receipts(path, ReadOnlyGateway())
