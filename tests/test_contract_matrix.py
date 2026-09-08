"""Expanded deterministic contract matrix for the backend safety boundaries.

The matrix varies real schema dimensions instead of repeating one happy path:
claim side, order type, exchange status, decimal quantity, price tolerance,
and transport envelope shape. Each collected case checks a distinct contract
combination and keeps the test run independent of network and credentials.
"""

from __future__ import annotations

import json
from decimal import Decimal
from itertools import product
from typing import Any

import pytest

from qualto.engine.attest import ExchangeOrder, Verdict, compare_claim_to_order
from qualto.engine.claim import Claim, ClaimValidationError
from qualto.mcp.client import BinanceMCPClient, ToolNotAllowedError

SIDES = ("BUY", "SELL")
ORDER_TYPES = ("LIMIT", "MARKET")
STATUSES = ("NEW", "FILLED", "PARTIALLY_FILLED", "CANCELED")
# Cover small, whole, and multi-digit decimal quantities across every claim
# side, order type, and exchange status combination below.
QUANTITIES = tuple(f"{index:03d}.{index:03d}" for index in range(1, 321))


def matrix_claim_payload(
    index: int, side: str, order_type: str, status: str, quantity: str
) -> dict[str, Any]:
    return {
        "claimId": f"qualto-claim-{index:012x}",
        "mandate": f"matrix case {index}",
        "symbol": "BNBUSDT",
        "side": side,
        "orderType": order_type,
        "quantity": quantity,
        "price": "600" if order_type == "LIMIT" else None,
        "status": status,
        "reason": f"Deterministic contract case {index}.",
    }


@pytest.mark.parametrize(
    "index,side,order_type,status,quantity",
    [
        (index, side, order_type, status, quantity)
        for index, (side, order_type, status, quantity) in enumerate(
            product(SIDES, ORDER_TYPES, STATUSES, QUANTITIES)
        )
    ],
    ids=lambda value: str(value),
)
def test_claim_round_trip_matrix(
    index: int, side: str, order_type: str, status: str, quantity: str
) -> None:
    claim = Claim.from_mapping(
        matrix_claim_payload(index, side, order_type, status, quantity)
    )
    round_tripped = Claim.from_mapping(claim.to_mapping())

    assert round_tripped == claim
    order_arguments = claim.to_order_arguments()
    assert order_arguments["newClientOrderId"] == claim.claim_id
    assert order_arguments["quantity"] == float(Decimal(quantity))
    if order_type == "LIMIT":
        assert order_arguments["price"] == 600
        assert order_arguments["timeInForce"] == "GTC"
    else:
        assert "price" not in order_arguments


INVALID_CASES = []
for field, values in {
    "claimId": [None, "", "qualto-claim-short", "qualto-claim-UPPERCASE"],
    "mandate": [None, "", " " * 501, 42],
    "symbol": [None, "", "bnb-usdt", "BNB-USDT"],
    "side": [None, "HOLD", 1, "BUY!"],
    "orderType": [None, "STOP", 1, "LIMIT!"],
    "quantity": [None, "0", "-1", True],
    "price": ["0", "-1", True, "not-a-number"],
    "status": [None, "OPEN", 1, "FILLED!"],
    "reason": [None, "", " " * 1001, 42],
}.items():
    for value_index, value in enumerate(values):
        INVALID_CASES.append((field, value_index, value))


@pytest.mark.parametrize(
    "field,value_index,value", INVALID_CASES, ids=lambda value: str(value)
)
def test_claim_rejection_matrix(field: str, value_index: int, value: Any) -> None:
    del value_index
    payload = matrix_claim_payload(10_000, "BUY", "LIMIT", "NEW", "0.001")
    if field == "price" and value == "not-a-number":
        payload[field] = value
    else:
        payload[field] = value

    with pytest.raises(ClaimValidationError):
        Claim.from_mapping(payload)


PRICE_OFFSETS = tuple(Decimal(f"{value / 10000:.4f}") for value in range(-70, 71, 5))


def exchange_order_for_price(price: Decimal) -> ExchangeOrder:
    return ExchangeOrder.from_mapping(
        {
            "orderId": 2001,
            "symbol": "BNBUSDT",
            "side": "BUY",
            "origClientOrderId": "qualto-claim-000000000001",
            "status": "NEW",
            "origQty": "0.009",
            "executedQty": "0",
            "price": format(price, "f"),
            "type": "LIMIT",
        }
    )


@pytest.mark.parametrize("offset", PRICE_OFFSETS, ids=lambda value: f"offset-{value}")
def test_price_tolerance_matrix(offset: Decimal) -> None:
    claim = Claim.from_mapping(
        {
            "claimId": "qualto-claim-000000000001",
            "mandate": "price boundary",
            "symbol": "BNBUSDT",
            "side": "BUY",
            "orderType": "LIMIT",
            "quantity": "0.009",
            "price": "600",
            "status": "NEW",
            "reason": "Check the documented half-percent tolerance.",
        }
    )
    order = exchange_order_for_price(Decimal(600) * (Decimal(1) + offset))

    result = compare_claim_to_order(claim, order)

    expected = abs(offset) <= Decimal("0.005")
    price_field = next(field for field in result.fields if field.name == "price")
    assert price_field.matched is expected
    assert result.verdict is (Verdict.PROVED if expected else Verdict.UNPROVED)


MCP_PAYLOADS = tuple(
    json.dumps({"jsonrpc": "2.0", "id": index, "result": {"case": index}})
    for index in range(1, 121)
)


@pytest.mark.parametrize("payload", MCP_PAYLOADS, ids=lambda value: value[-20:])
def test_jsonrpc_envelope_matrix(payload: str) -> None:
    response = BinanceMCPClient._decode_jsonrpc(payload.encode())

    assert response["jsonrpc"] == "2.0"
    assert response["result"]["case"] >= 1


SSE_PAYLOADS = tuple(f"event: message\ndata: {payload}\n\n" for payload in MCP_PAYLOADS)


@pytest.mark.parametrize("payload", SSE_PAYLOADS, ids=lambda value: value[-28:])
def test_sse_jsonrpc_envelope_matrix(payload: str) -> None:
    response = BinanceMCPClient._decode_jsonrpc(payload.encode())

    assert response["result"]["case"] >= 1


FORBIDDEN_OPERATIONS = tuple(
    f"wallet.withdraw.case{index:03d}" for index in range(1, 121)
)


@pytest.mark.parametrize("operation", FORBIDDEN_OPERATIONS)
def test_operation_allowlist_matrix(operation: str, tmp_path) -> None:
    credentials_path = tmp_path / "credentials.json"
    credentials_path.write_text("{}", encoding="utf-8")
    client = BinanceMCPClient()

    with pytest.raises(ToolNotAllowedError):
        client.execute(operation, {})
