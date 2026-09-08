---
name: qualto-claim-bound-trading
description: Place Binance orders only as claim-bound trades attested by Qualto — if Binance can't prove it, the agent can't claim it. Use when the user asks to buy, sell, or trade on Binance, place or check an order, or verify an agent's reported fill. Every order must carry a claim ID, read back PROVED against the exchange, or the session locks and trading stops.
---

# Qualto — Claim-Bound Trading on Binance Agent OS

You are operating a trading agent boundary that enforces one invariant: **if Binance can't prove it, the agent can't claim it.** A trade claim is only true if a live Binance order, stamped with the claim's ID, reads back matching. You never place raw orders. You never assert a fill the exchange cannot prove.

## Prerequisites

- `qualto` installed (`pip install -e .` from the repo) and on PATH
- Binance Agentic sub-account funded; supported host credential available
- Check readiness first: `qualto smoke` (read-only — must print `gateway=ready`)

## The claim contract

Every trade is a strict JSON claim. Required fields, no others:

```json
{
  "claimId": "qualto-claim-<12 lowercase alphanumerics>",
  "mandate": "what the user asked for, 1-500 chars",
  "symbol": "BNBUSDT",
  "side": "BUY",
  "orderType": "LIMIT",
  "quantity": "0.009",
  "price": "600",
  "status": "NEW",
  "reason": "1-1000 chars, your honest reasoning"
}
```

Rules you must respect:
- Quantities/prices are decimal strings, positive, finite. Market orders set `price` to `null`.
- `status` is the status you commit to at readback: NEW for resting limit orders, FILLED for market intent.
- A `claimId` is single-use. Never reuse one; if you regenerate a claim, mint a new ID.

## The workflow — never skip steps

1. **Draft the claim** from live context. If `qualto` is available, prefer letting the harness generate context: show the user the claim JSON before anything is sent.
2. **Save it** to a file, e.g. `my-claim.json`.
3. **Get explicit user confirmation** for the live write. Never run a write command on your own initiative.
4. **Place and attest, with cleanup armed**:
   ```bash
   qualto claim --claim-file my-claim.json \
                --receipts-file runtime/receipts.jsonl \
                --confirm-live-write \
                --cancel-after-attestation
   ```
5. **Report the verdict exactly as returned.** `PROVED` means every field matched the exchange readback. `UNPROVED` means it did not — say so plainly, never soften it. `PARTIAL` means report the filled quantity. `PENDING` means the readback is still retrying.
6. Exit code 0 = PROVED. Exit code 1 = anything else. Exit code 2 = confirmation missing — ask the user, do not self-confirm.

## Hard rules

- **Never call Binance order endpoints directly.** No raw `spot.newOrder`, no constructing orders outside the harness. All placement goes through `qualto claim`. The exchange, not you, is the source of truth.
- **Never fabricate, round, or predict a verdict.** If the command did not return PROVED, the claim is not proved. There is no such thing as "probably filled."
- **If the session is BLOCKED, stop trading.** Report the block reason and the recovery path (operator reconnect + recover). Do not attempt further writes or workarounds.
- **One claim, one order.** If you need to adjust a trade, cancel or let the existing claim resolve, then create a new claim with a new ID.
- **Zero-cost pattern for demos/tests:** below-market dust LIMIT (e.g. quantity 0.009, price far under market) + `--cancel-after-attestation` → proves the full bind-readback-attest-cancel cycle with no fill.

## Verifying past fills

To re-check any receipts file against live Binance state (read-only):

```bash
qualto verify --receipts-file runtime/receipts.jsonl
```

Use this whenever a user asks "did that trade actually happen?" — re-read the exchange, don't re-tell the log.

## If something breaks

- Gateway errors, credential unavailable → report the error as-is; the harness fails closed. No order is the safe outcome.
- An order may have been placed but the response was lost → `qualto cleanup --claim-file my-claim.json --confirm-live-write` resolves the order by claim ID and cancels the exact exchange order.
- Never retry a write "to be sure" — ask the user first.
