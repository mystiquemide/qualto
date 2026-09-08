"""Adversarial matrices for the exchange-proof and transport boundaries."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from qualto.engine.attest import ExchangeOrder, Verdict, compare_claim_to_order
from qualto.engine.claim import Claim
from qualto.engine.verify import verify_receipts
from qualto.mcp.client import BinanceMCPClient, MCPProtocolError


def claim_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "claimId": "qualto-claim-abcdefghijkl",
        "mandate": "buy a bounded BNB limit order",
        "symbol": "BNBUSDT",
        "side": "BUY",
        "orderType": "LIMIT",
        "quantity": "0.006",
        "price": "700",
        "status": "NEW",
        "reason": "Adversarial contract fixture.",
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


READBACK_MUTATIONS: tuple[tuple[str, Any], ...] = (
    ("symbol", "ETHUSDT"),
    ("symbol", "BNBBTC"),
    ("side", "SELL"),
    ("origClientOrderId", "qualto-claim-zzzzzzzzzzzz"),
    ("origQty", "0.007"),
    ("origQty", "0.00000001"),
    ("price", "704"),
    ("price", "800"),
    ("status", "CANCELED"),
    ("status", "FILLED"),
)


@pytest.mark.parametrize("field,value", READBACK_MUTATIONS)
def test_exchange_proof_rejects_readback_mutation_matrix(
    field: str, value: Any
) -> None:
    claim = Claim.from_mapping(claim_payload())
    order = ExchangeOrder.from_mapping(order_payload(**{field: value}))

    result = compare_claim_to_order(claim, order)

    assert result.verdict is Verdict.UNPROVED
    assert any(not field_result.matched for field_result in result.fields)


TAMPER_CASES: tuple[tuple[str, Any], ...] = (
    *(("claimId", f"qualto-claim-{index:012x}") for index in range(1, 21)),
    ("symbol", "ETHUSDT"),
    ("symbol", "BNBBTC"),
    ("side", "SELL"),
    ("quantity", "0.007"),
    ("quantity", "0.00000001"),
    ("price", "704"),
    ("price", "800"),
    ("status", "CANCELED"),
    ("status", "FILLED"),
    ("orderType", "MARKET"),
    ("unexpected", "edited"),
    ("attestation.verdict", "UNPROVED"),
    ("attestation.verdict", "PENDING"),
    ("attestation.orderId", 1002),
    ("attestation.orderId", "not-an-order-id"),
)


class ReadOnlyGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(
        self, tool_name: str, arguments: Mapping[str, Any] | None = None
    ) -> Any:
        self.calls.append((tool_name, dict(arguments or {})))
        assert tool_name == "spot.getOrder"
        return order_payload()


@pytest.mark.parametrize("field,value", TAMPER_CASES)
def test_receipt_reverification_rejects_tampered_claim_matrix(
    field: str, value: Any, tmp_path: Path
) -> None:
    entry: dict[str, Any] = {
        "event": "claim_attestation",
        "claim": claim_payload(),
        "attestation": {"orderId": 1001, "verdict": "PROVED"},
    }
    target, key = field.split(".", 1) if "." in field else ("claim", field)
    entry[target][key] = value
    path = tmp_path / "receipts.jsonl"
    path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    result = verify_receipts(path, ReadOnlyGateway())[0]

    assert not result.matched


JSONRPC_ID_PAIRS: tuple[tuple[int, int], ...] = tuple(
    (expected, wrong)
    for expected in range(1, 201)
    for wrong in (expected + 1000, expected + 2000)
)


@pytest.mark.parametrize("expected,wrong", JSONRPC_ID_PAIRS)
def test_jsonrpc_mismatched_id_matrix(expected: int, wrong: int) -> None:
    raw = json.dumps(
        {"jsonrpc": "2.0", "id": wrong, "result": {"case": expected}}
    ).encode()

    with pytest.raises(MCPProtocolError, match="ID"):
        BinanceMCPClient._decode_jsonrpc(raw, expected_id=expected)


@pytest.mark.parametrize("expected", range(1, 201))
def test_sse_matching_id_matrix(expected: int) -> None:
    raw = (
        f'event: message\ndata: {{"jsonrpc":"2.0","id":{expected + 1000},"result":{{}}}}\n\n'
        f'event: message\ndata: {{"jsonrpc":"2.0","id":{expected},"result":{{"case":{expected}}}}}\n\n'
    ).encode()

    response = BinanceMCPClient._decode_jsonrpc(raw, expected_id=expected)

    assert response["id"] == expected
    assert response["result"]["case"] == expected
