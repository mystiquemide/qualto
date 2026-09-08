<p align="center">
  <img src="assets/qualto-banner.svg" alt="Qualto — no fill, no claim" width="880">
</p>

<p align="center">
  <a href="https://github.com/mystiquemide/qualto/actions/workflows/ci.yml"><img src="https://github.com/mystiquemide/qualto/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Binance-Agent%20OS%20%C2%B7%20Track%20A-F0B90B?logo=binance&logoColor=black" alt="Binance Agent OS · Track A">
  <img src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/tests-5%2C637%20passing-16C784" alt="5,637 tests passing">
  <img src="https://img.shields.io/badge/coverage-86%25-16C784" alt="86% coverage">
  <img src="https://img.shields.io/badge/runtime%20deps-zero-848E9C" alt="zero runtime dependencies">
  <img src="https://img.shields.io/badge/ruff%20%C2%B7%20mypy-clean-261230" alt="ruff + mypy clean">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license"></a>
</p>

# Qualto

Qualto binds an agent's trading claim to a live Binance order, reads it back through Binance Agent OS, and blocks further writes when the exchange cannot prove the claim.

The rule is simple: **no fill, no claim.**

> Agent OS gives agents the ability to trade. Qualto gives the exchange the ability to hold them to their word.

**▶ Demo video (90s): [mandate → claim → claim-bound order → PROVED → "check it on Binance" → disconnect → UNPROVED → session locked](TBD-REPLACE-WITH-TWEET-LINK)**

## The problem

Agents now trade real money, and their chat logs narrate fills nobody can check. A confabulated fill looks identical to a real one until someone opens the exchange — and by then the trust is gone. The burden lands on the user; the reputational damage lands on the platform that gave the agent the keys.

## How it works

1. The operator enters a bounded mandate.
2. The agent proposes a strict claim from live price and balance context.
3. The harness validates the claim and stamps its ID into `newClientOrderId`.
4. Binance returns the order through MCP by order ID **and** claim ID — both readbacks must agree.
5. Qualto diffs symbol, side, quantity (exact), price (±0.5%), and status.
6. A proved claim is recorded. An unproved claim locks the session.

The harness places orders. The model only proposes them.

## Pair support

The claim contract accepts any uppercase Binance Spot symbol supported by the connected account. Read-only ticker checks passed for `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`, `ADAUSDT`, and `DOGEUSDT` on 2026-09-08. The live claim-bound order and cancellation proof uses `BNBUSDT`.

## What happens when the agent lies

Enforcement, not observation — every row was exercised against the real gateway:

| Violation | Result |
|---|---|
| Claim unresolvable (gateway down, order missing) | **UNPROVED** → session **BLOCKED** with reason → further order placement refused |
| Dual readbacks disagree | **UNPROVED** → session locked |
| Field mismatch (qty, price beyond ±0.5%, status) | **UNPROVED** with per-field diff → session locked |
| Claim ID reused (replay) | Rejected before placement, logged |
| Order partially filled | **PARTIAL** verdict with filled quantity — never a silent pass |
| Market order still NEW at readback | **PENDING**, retried 3× at 2s — never a false UNPROVED |

Recovery requires an explicit operator action (reconnect + recover). The agent cannot unblock itself.

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

The verifier calls only `spot.getOrder` and never places or cancels an order. To verify the engineering itself: `pip install -e ".[test]" && pytest -q` — 5,637 tests, ~8 seconds, zero network, no mocks presented as real.

## Bring your own agent

Qualto attests **claims, not agents**. The claim is a strict JSON contract — draft it with the bundled loop, another LLM, or a text editor. The attestation gate is agent-agnostic: whoever writes the claim, Binance is the judge. The bundled loop (Hermes, tools disabled, prompt over stdin, 120s budget) is one optional provider; the core — placement, dual readback, attestation, lock, receipts — runs entirely without it.

### Give your own agent the rules

Qualto ships as an **agent skill** — one file that teaches any SKILL.md-compatible agent (Claude Code, Qwen Code, and friends) to trade claim-bound and report verdicts honestly:

```bash
git clone https://github.com/mystiquemide/qualto
mkdir -p ~/.claude/skills && cp -r qualto/skills/qualto-trading ~/.claude/skills/
# Qwen Code: cp -r qualto/skills/qualto-trading ~/.qwen/skills/
```

The skill encodes the policy: never place raw orders, always go through the harness, never soften an UNPROVED, stop when the session locks. **Skills make agents willing. The harness makes them unable.**

## Why Agent OS needs this

1. Agent OS puts agents on real money; "users are responsible" pushes the trust burden onto users and support.
2. An agent that narrates a fake fill destroys Agent OS trust — the damage lands on the platform, not the model vendor.
3. The proof rail already exists: Binance order records, client-order-ID field included, readable over MCP. Nobody had turned it into an *enforcement* mechanism.
4. Qualto binds claims to that rail pre-placement and locks the session when the exchange cannot prove the claim — accountability with **zero new Binance infrastructure**.
5. Adopt **claim-bound orders** as an Agent OS convention and every agent on the platform becomes auditable by default.

The ask: reserve the client-order-ID namespace for agent claims, or surface attestation natively in the Agent OS console. Third-party verifier identities are not admitted today — opening that door turns this from one harness into platform infrastructure.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test,quality]"
.venv/bin/pytest -q
```

With the registered host credential available, `qualto smoke` checks the gateway and `qualto propose --mandate "buy 5 USDT of BNB"` produces a claim without placing an order. To run a full zero-cost proof cycle on your own funded Agentic sub-account, write a below-market dust claim and confirm the live write explicitly:

```bash
qualto claim --claim-file my-claim.json \
             --receipts-file runtime/my-receipts.jsonl \
             --confirm-live-write \
             --cancel-after-attestation
```

Every write command requires `--confirm-live-write`; without it, exit code 2 and nothing is sent.

## Authentication

Qualto uses the same Binance Agent OS endpoint and native tool surface as the sponsor integration. OAuth stays in the registered Codex host-managed connector. Qualto reads that credential at runtime and never exposes it to the model or receipts.

## Limits

Qualto does not provide trading strategy, forecasting, futures, margin, withdrawals, or multi-user accounts. It is a claim and enforcement layer for bounded spot-order workflows: single session, one symbol per claim, attestation per order. Live commands require explicit confirmation, and the included Binance proof account is private. The claim file, not the mandate, is the binding contract.

## Roadmap: from harness to platform

- **MCP tool** — expose the attestation gate as a runtime tool so any Agent OS agent *cannot bypass* claim-binding (the skill ships today; the tool makes it structural).
- **Platform standard** — claim-bound orders as an Agent OS convention, attestation surfaced in the console.
- **No proof, no payment** — attestation as the settlement gate for agentic commerce (x402).
- **Multi-venue attestation** — the same claim-diff pattern over `convert.orderStatus`.

## Submission

- **Hackathon:** Binance Agent OS Mini Hackathon — **Track A** (working agent)
- **Sponsor stack:** Binance Agent OS MCP (`agent.binance.com/mcp/agentic`) — load-bearing; delete it and nothing above survives
- **Built live** during the hackathon window — the commit history reads M1 → M7 checkpoints: gateway → claim engine → agent loop → enforcement → verification ladder → review fixes → read-only verifier
- **Demo video:** TBD-REPLACE-WITH-TWEET-LINK
- **Submission tweet:** TBD-REPLACE-WITH-TWEET-LINK
- **Author:** [MystiqueMide](https://github.com/mystiquemide)

**Topics:** `binance` · `agent-os` · `mcp` · `ai-agents` · `llm-agents` · `trading` · `attestation` · `verification` · `trust-and-safety` · `python`

## License

[MIT](LICENSE) — © 2026 MystiqueMide
