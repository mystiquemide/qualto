from __future__ import annotations

from decimal import Decimal

import pytest

from qualto.engine.claim import (
    Claim,
    ClaimStatus,
    ClaimValidationError,
    OrderSide,
    OrderType,
    mint_claim_id,
)


def valid_payload() -> dict[str, object]:
    return {
        "claimId": "qualto-claim-abcdefghijkl",
        "mandate": "buy five USDT of BNB",
        "symbol": "BNBUSDT",
        "side": "BUY",
        "orderType": "LIMIT",
        "quantity": "0.008",
        "price": "625.00",
        "status": "NEW",
        "reason": "The bounded mandate permits a small limit order.",
    }


def test_claim_parses_and_normalizes_order_arguments() -> None:
    claim = Claim.from_mapping(valid_payload())

    assert claim.side is OrderSide.BUY
    assert claim.order_type is OrderType.LIMIT
    assert claim.quantity == Decimal("0.008")
    assert claim.to_order_arguments() == {
        "symbol": "BNBUSDT",
        "side": "BUY",
        "type": "LIMIT",
        "quantity": "0.008",
        "newClientOrderId": "qualto-claim-abcdefghijkl",
        "price": "625.00",
        "timeInForce": "GTC",
    }


def test_market_claim_omits_price() -> None:
    payload = valid_payload()
    payload.update({"orderType": "MARKET", "price": None, "status": "FILLED"})

    claim = Claim.from_mapping(payload)

    assert claim.price is None
    assert "price" not in claim.to_order_arguments()


@pytest.mark.parametrize("field", ["claimId", "mandate", "symbol", "side", "orderType", "quantity", "price", "status", "reason"])
def test_claim_rejects_missing_required_field(field: str) -> None:
    payload = valid_payload()
    del payload[field]

    with pytest.raises(ClaimValidationError):
        Claim.from_mapping(payload)


def test_claim_rejects_unknown_field() -> None:
    payload = valid_payload()
    payload["unexpected"] = "no"

    with pytest.raises(ClaimValidationError, match="unknown"):
        Claim.from_mapping(payload)


@pytest.mark.parametrize("field,value", [("quantity", "0"), ("quantity", "-1"), ("price", "0"), ("price", "-1")])
def test_claim_rejects_nonpositive_numbers(field: str, value: str) -> None:
    payload = valid_payload()
    payload[field] = value

    with pytest.raises(ClaimValidationError):
        Claim.from_mapping(payload)


def test_claim_rejects_market_price() -> None:
    payload = valid_payload()
    payload.update({"orderType": "MARKET", "status": "FILLED"})

    with pytest.raises(ClaimValidationError, match="market"):
        Claim.from_mapping(payload)


@pytest.mark.parametrize("suffix", ["short", "UPPERCASE!!!!!", "abcdefghijklx", ""])
def test_claim_id_suffix_is_strict(suffix: str) -> None:
    with pytest.raises(ClaimValidationError):
        mint_claim_id(suffix)


def test_mint_claim_id_uses_safe_format() -> None:
    assert mint_claim_id("abcdefghijkl") == "qualto-claim-abcdefghijkl"
