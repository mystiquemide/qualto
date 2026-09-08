# Qualto

Qualto binds an agent's trading claim to a live Binance order, reads it back through Binance Agent OS, and blocks further writes when the exchange cannot prove the claim.

The rule is simple: no fill, no claim.

> Agent OS gives agents the ability to trade. Qualto gives the exchange the ability to hold them to their word.

## How it works

1. The operator enters a bounded mandate.
2. The agent proposes a strict claim from live price and balance context.
3. The harness validates the claim and stamps its ID into `newClientOrderId`.
4. Binance returns the order through MCP by order ID and claim ID.
5. Qualto diffs symbol, side, quantity, price, and status.
6. A proved claim is recorded. An unproved claim locks the session.

The harness places orders. The model only proposes them.

## Pair support

The claim contract accepts any uppercase Binance Spot symbol supported by the connected account. Read-only ticker checks passed for `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`, `ADAUSDT`, and `DOGEUSDT` on 2026-09-08. The live claim-bound order and cancellation proof uses `BNBUSDT`.

## Verify the proof

The proof lives in Binance's order record, not only in Qualto's log. These claim-bound limit orders were placed in the Binance Agentic sub-account, read back as `PROVED`, cancelled immediately, and confirmed with zero execution:

| Order ID | Claim ID | Result |
| --- | --- | --- |
| `12565013192` | `qualto-claim-live00000002` | PROVED, then CANCELED |
| `12565050896` | `qualto-claim-56eda03b6069` | PROVED, then CANCELED |

The masked receipt sample is in [`examples/proof-receipts.jsonl`](examples/proof-receipts.jsonl). To re-check a receipt file against current Binance state, use the read-only verifier:

```bash
qualto verify --receipts-file runtime/receipts.jsonl
```

The verifier calls only `spot.getOrder` and never places or cancels an order.

## Authentication

Qualto uses the same Binance Agent OS endpoint and native tool surface as the sponsor integration. OAuth stays in the registered Codex host-managed connector. Qualto reads that credential at runtime and never exposes it to the model or receipts.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test,quality]"
.venv/bin/pytest -q
```

With the registered host credential available, `qualto smoke` checks the gateway and `qualto propose --mandate "buy 5 USDT of BNB"` produces a claim without placing an order.

## Limits

Qualto does not provide trading strategy, forecasting, futures, margin, withdrawals, or multi-user accounts. It is a claim and enforcement layer for bounded spot-order workflows. Live commands require explicit confirmation, and the included Binance proof account is private.
