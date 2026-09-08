<p align="center">
  <img src="assets/qualto-banner.svg" alt="Qualto — the verification-first AI trading agent" width="880">
</p>

<p align="center">
  <a href="https://github.com/mystiquemide/qualto/actions/workflows/ci.yml"><img src="https://github.com/mystiquemide/qualto/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Binance-Agent%20OS%20%C2%B7%20Track%20A-F0B90B?logo=binance&logoColor=black" alt="Binance Agent OS · Track A">
  <a href="https://qualto.vercel.app"><img src="https://img.shields.io/badge/live_site-qualto.vercel.app-EAECEF" alt="Live site"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license">
</p>

# Qualto

**Qualto is a bounded, verification-first AI trading agent built on Binance Agent OS.**

It can reason about a trading mandate and execute on Binance — but it isn't allowed to claim an order succeeded until Binance itself proves it.

The LLM decides what claim to propose. Qualto's deterministic boundary decides whether it may execute. Binance decides whether the resulting claim is true.

> **If Binance can't prove it, the agent can't claim it.**

*Binance Agent OS Mini Hackathon · Track A*

- **Demo video:** TBD-REPLACE-WITH-TWEET-LINK
- **Live site:** [qualto.vercel.app](https://qualto.vercel.app)
- **Repository:** [github.com/mystiquemide/qualto](https://github.com/mystiquemide/qualto)

## The Problem

An AI agent can say *"I bought BNB"* whether the trade happened or not. Those reports are self-reported — the user has to independently open the exchange and check. Until then, a hallucinated fill and a real one look identical.

Qualto makes Binance verify the agent's claim automatically.

## How Qualto Solves It

```text
user → AI agent → claim → Qualto boundary → Agent OS → Binance → verification → agent response
```

1. **The agent reasons.** Given a mandate plus live Binance price and balance, the LLM drafts a strict trading claim — symbol, side, quantity, price, status — as validated JSON.
2. **The claim gets an identity.** Before execution, the claim receives a unique ID, and Qualto stamps that ID into the Binance order itself using `newClientOrderId`.
3. **Execution through Agent OS.** Qualto executes the order through the Binance Agent OS MCP endpoint — the agent never places raw orders.
4. **Binance becomes the judge.** Qualto reads the order back from Binance through two lookup paths (by `orderId` and by the claim ID) and requires both readbacks to agree. Claim fields are checked against the exchange record: symbol, side, quantity, price, status.
5. **The verdict is enforced, not advisory.** Match → `PROVED`. No match, unreadable, or unprovable → `UNPROVED` and the trading session locks — the agent cannot trade again until an operator intervenes.

When the agent claims a fill, Qualto additionally verifies the executed quantity before returning `PROVED`. Resting orders, cancellations, and partial fills are each attested against their actual exchange state.

## Why Binance Agent OS Is Essential

Qualto is load-bearing on Agent OS — remove it and nothing above survives:

- **Execution:** all orders go through the official Agent OS MCP endpoint (`agent.binance.com/mcp/agentic`).
- **Authentication:** OAuth 2.1 via the registered Agent OS host connector.
- **Market data:** live prices and balances from `spot.tickerPrice` and `spot.getAccount`.
- **The proof itself:** Binance's order record — with the claim ID inside it — is the source of truth for every verdict. The proof lives on Binance's ledger, not in Qualto's log.

Of the 366 tools Agent OS exposes, Qualto admits exactly 6 (spot account, ticker, place, get, trades, cancel). Everything else is rejected before a request exists.

## What We Built

**An AI trading agent whose execution claims must be proven by Binance, plus the verification layer that enforces it.**

| Capability | Status |
|---|---|
| LLM agent loop: mandate → live context → reasoned claim (tools disabled, stdin prompt, 120 s budget) | Shipped, proven live |
| Claim-bound placement + dual readback + field diff via Agent OS | Shipped, proven live |
| Verdicts PROVED / UNPROVED / PARTIAL / PENDING with session lock | Shipped, proven live |
| Session states ACTIVE / BLOCKED / ERROR / CLOSED, replay protection, write gates | Shipped |
| Standalone MCP server (`qualto-mcp`, 5 tools) for any MCP-compatible client | Shipped |
| Agent skill (`qualto-claim-bound-trading`) for Claude Code / Qwen Code | Shipped |
| `qualto verify` — read-only re-verification of receipts against live Binance | Shipped |
| Web console (landing + docs) — [qualto.vercel.app](https://qualto.vercel.app) | Shipped |
| CI (pytest / ruff / mypy), GitHub Pages, Vercel auto-deploy | Shipped |

Planned but **not** built: native attestation in the Agent OS console, x402 payment gating, multi-venue attestation, remote-HTTP MCP, multi-session persistence.

## Architecture

```text
┌───────────────────────── operator ─────────────────────────┐
│  CLI (qualto propose / claim / agent / verify / cleanup)   │
│  Web console (Next.js — qualto.vercel.app)                 │
└──────────┬────────────────────────────────────────────────┘
           │ mandates, claims (strict JSON)
┌──────────▼────────────────────────────────────────────────┐
│ AI agent layer                                             │
│  LLM (Hermes): mandate + live context → one claim.         │
│  Zero tools. Prompt over stdin. 120 s wall clock.          │
├───────────────────────────────────────────────────────────┤
│ Qualto boundary (Python 3.11+, zero core deps)            │
│  claim schema      strict, decimal-exact, replay-proof     │
│  attestation       bind → dual readback → field diff       │
│  session           ACTIVE / BLOCKED / ERROR / CLOSED       │
│  receipts          append-only JSONL, fsync, 0600          │
│  MCP server        5 tools, double write gate              │
├───────────────────────────────────────────────────────────┤
│ Agent OS client                                            │
│  JSON-RPC over streamable HTTP · request-ID matching ·     │
│  two-layer tool allowlist (366 → 6)                        │
└──────────┬────────────────────────────────────────────────┘
           │ OAuth 2.1 (registered host connector)
┌──────────▼────────────────────────────────────────────────┐
│ Binance Agent OS MCP → Binance spot sub-account            │
│  The order record IS the proof                             │
└───────────────────────────────────────────────────────────┘
```

## Live Proof

Real orders, placed by the agent, still visible in Binance order history — each carrying its claim ID as the client order ID:

| Binance order | Claim ID | Verdict |
|---|---|---|
| `12565050896` | `qualto-claim-56eda03b6069` | PROVED, then CANCELED at zero execution |
| `12565013192` | `qualto-claim-live00000002` | PROVED, then CANCELED at zero execution |
| `12565577634` | string-transport proof | PROVED, then CANCELED at zero execution |

Every live proof used the zero-cost pattern: below-market dust limit → PROVED → immediate cancel → post-cancel readback confirming zero execution. The negative path was also proven live, twice: gateway severed before placement → `UNPROVED` → session `BLOCKED` → writes refused → operator recovery.

Re-verify any receipts file against live Binance at any time:

```bash
qualto verify --receipts-file receipts.jsonl   # read-only
```

**Benchmarks** (measured, not marketed): PROVED verdict → confirmed cancellation **353 ms** · full Agent OS gateway cycle **1.2–1.4 s** · mandate → PROVED **~28 s** (LLM-bound) — *verification is never the bottleneck; the thinking is.*

**Reliability:** the behavior above is backed by 11,433 passing tests (~19 s, no network) — 10,665 parameterized claim-contract cases (sides × order types × statuses × quantities × price tolerances × envelope shapes), 12 MCP server tool/gate tests, and 756 focused behavioral tests (dual readback, replay rejection, session locking, orphan cleanup, CLI). Reproduce with `pytest -q`.

## Run It Yourself

**Requirements:** Python 3.11+ · a Binance account with a funded **Agentic sub-account** · a registered Agent OS host credential (Codex CLI authenticated with the Binance connector) as `QUALTO_CODEX_CREDENTIALS_FILE`. No database, no personal API keys, no main-account access — ever.

## Quickstart

```bash
git clone https://github.com/mystiquemide/qualto && cd qualto
python3 -m venv .venv && .venv/bin/pip install -e ".[test]"

export QUALTO_CODEX_CREDENTIALS_FILE=/path/to/host-credentials.json
.venv/bin/qualto smoke          # read-only gateway check
.venv/bin/qualto propose --mandate "buy 5 USDT of BNB"   # agent drafts, nothing placed

# first zero-cost proof cycle on your own sub-account
cat > my-claim.json <<'EOF'
{
  "claimId": "qualto-claim-yourownid001",
  "mandate": "buy a small below-market BNB limit order, then cancel",
  "symbol": "BNBUSDT", "side": "BUY", "orderType": "LIMIT",
  "quantity": "0.009", "price": "600", "status": "NEW",
  "reason": "Dust proof order bound to this claim ID."
}
EOF
.venv/bin/qualto claim --claim-file my-claim.json \
  --receipts-file runtime/my-receipts.jsonl \
  --confirm-live-write --cancel-after-attestation
```

Web console: `cd web && npm install && npm run dev`.

## Security

- **Permission model:** only Qualto's boundary places orders; the LLM has zero tools; the MCP surface is five fixed tools; the underlying Binance operations are a 6-entry allowlist enforced before any request is built.
- **Secret handling:** the host credential is loaded per request, in memory, never logged, never in receipts; a dedicated test asserts no leakage. Missing or expired ⇒ fail closed, no order.
- **Input validation:** closed claim schema at the boundary — unknown fields, float quantities, reused claim IDs, out-of-range prices rejected before placement.
- **Access control:** every live write requires `--confirm-live-write` (CLI) or the env flag plus per-call confirmation (MCP); exit code 2 and nothing is sent without it.
- **Transport:** JSON-RPC responses matched to request IDs; mismatches rejected.

## Safety

- **The agent may:** read live context, draft claims, and — through the Qualto boundary — place claim-bound orders and cancel the exact order bound to a claim.
- **The agent may not:** reach withdrawal, transfer, futures, or margin paths; place any order that isn't claim-bound; unblock a session it got blocked.
- **Requires explicit human approval:** every live write, every session recovery, every cleanup.
- **Unknown outcomes fail closed:** an order whose placement result is unknown produces an intent receipt and a `qualto cleanup` path that resolves it by claim ID. The safe state is always "no order."

## Agent Integrations

| Agent | How it interacts | Status |
|---|---|---|
| **OpenAI Codex** | The OAuth credential rides Codex's registered Binance Agent OS connector. All live proofs in this repo ran on this path. | Tested, live-proven |
| **Claude Code / Claude Desktop** | Install the agent skill (`~/.claude/skills/`) and/or connect `qualto-mcp` as a stdio MCP server ([config](examples/mcp/mcp-client.json)). | Supported |
| **Qwen Code** | Same skill installs to `~/.qwen/skills/`. | Supported |
| **Any MCP-compatible client** | `pip install -e ".[mcp]"` then `qualto-mcp`. | Supported |

## Binance Integration

- **Endpoint:** Binance Agent OS MCP (`agent.binance.com/mcp/agentic`), JSON-RPC over streamable HTTP, protocol `2025-03-26`, OAuth 2.1 via the registered host connector.
- **Tools:** 366 exposed → 6 allowlisted: `spot.getAccount`, `spot.tickerPrice`, `spot.newOrder`, `spot.getOrder`, `spot.myTrades`, `spot.deleteOrder`.
- **Order identity:** every order placed with `newClientOrderId = claimId` — the attestation is visible in Binance's own order history UI.
- **Envelope:** all activity confined to a funded Agentic sub-account; main-account funds are structurally out of reach.

## Skill Integrations

- **`qualto-claim-bound-trading`** ([skills/](skills/qualto-trading/SKILL.md)) — teaches SKILL.md-compatible agents the policy: never call Binance order endpoints directly, report verdicts verbatim, never soften an UNPROVED, stop when the session locks.
- **MCP tools (`qualto-mcp`):** `qualto_session_status`, `qualto_read_context`, `qualto_attest_claim`, `qualto_cleanup_claim`, `qualto_verify_receipts`. Live writes require `QUALTO_ENABLE_LIVE_WRITE=1` **and** a per-call `confirm_live_write` flag.

## Other Integrations

- **Web console** — Next.js 15 (`web/`), deployed to [qualto.vercel.app](https://qualto.vercel.app) and GitHub Pages.
- **Hermes** — LLM provider for the drafting loop.
- **CI/CD** — GitHub Actions on every push; Pages and Vercel deploy from `main`.

## Authentication

Users never hand Qualto a Binance API key. Authentication rides a registered Agent OS host connector's OAuth credential (`QUALTO_CODEX_CREDENTIALS_FILE`), loaded per request, expiry-checked every call, never persisted. Sessions are local and explicit; MCP sessions add the double write gate.

## Limitations

- Single session, spot only, one symbol per claim; attestation is per-order, not per-strategy.
- The claim file — not the mandate — is the binding contract.
- Third-party agent OAuth identities are not yet admitted by Binance; Qualto runs on the registered host-credential path and fails closed when unavailable.
- The MCP server is stdio-only; remote-HTTP clients (ChatGPT, Devin) cannot connect today.
- Qualto proves a trade happened exactly as claimed — it does not judge whether the trade was a good idea.
- Human supervision required for: every live write, every session recovery, any state after an UNPROVED verdict.

## Vision

Everyone is building agents that decide *what* to trade. Qualto tackles whether you can trust *what the agent says it did*. That wedge generalizes: claim-bound orders as an Agent OS convention (reserved client-order-ID namespace, native console attestation), "no proof, no payment" settlement gating for agentic commerce (x402), multi-venue attestation, and remote MCP so any hosted agent can connect.

## Contributing

```bash
git clone https://github.com/mystiquemide/qualto && cd qualto
python3 -m venv .venv && .venv/bin/pip install -e ".[test,quality]"
.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/mypy
```

PR expectations: tests for every behavioral change, all quality gates green, no credentials or receipt data committed. New Binance operations go into the allowlist in `qualto/mcp/client.py` with negative tests; new agent surfaces belong in `skills/` and `qualto/mcp/server.py` with the same fail-closed gates. MIT license. Keep the invariant intact — **if Binance can't prove it, the agent can't claim it.**