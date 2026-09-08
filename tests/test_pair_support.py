from __future__ import annotations

import pytest

from qualto.engine.claim import Claim

BINANCE_SPOT_PAIRS = (
    "BNBUSDT",
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
)


@pytest.mark.parametrize("symbol", BINANCE_SPOT_PAIRS)
def test_claim_contract_supports_binance_spot_pair_matrix(symbol: str) -> None:
    claim = Claim.from_mapping(
        {
            "claimId": "qualto-claim-paircheck001",
            "mandate": f"check a bounded {symbol} limit claim",
            "symbol": symbol,
            "side": "BUY",
            "orderType": "LIMIT",
            "quantity": "0.001",
            "price": "1",
            "status": "NEW",
            "reason": "Pair support contract test.",
        }
    )

    assert claim.symbol == symbol
    assert claim.to_order_arguments()["symbol"] == symbol
