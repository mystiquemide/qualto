<p align="center">
  <img src="assets/qualto-banner.svg" alt="Qualto — no fill, no claim" width="880">
</p>

<p align="center">
  <a href="https://github.com/mystiquemide/qualto/actions/workflows/ci.yml"><img src="https://github.com/mystiquemide/qualto/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Binance-Agent%20OS%20%C2%B7%20Track%20A-F0B90B?logo=binance&logoColor=black" alt="Binance Agent OS · Track A">
  <a href="https://qualto.vercel.app"><img src="https://img.shields.io/badge/live_site-qualto.vercel.app-EAECEF" alt="Live site"></a>
  <img src="https://img.shields.io/badge/tests-11%2C433%20passing-16C784" alt="11,433 tests passing">
  <img src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license">
</p>

## Built For

- **Principals** — people who hand an AI agent real money on a Binance Agentic sub-account and want fills they can verify in seconds instead of trusting the agent's chat log.
- **Agent developers** — teams building trading agents on Binance Agent OS who need their agent's reported fills to be credible to end users.
- **The Agent OS platform** — the claim-bound order pattern is a convention Binance can adopt so every agent on the platform becomes auditable by default.

## One-Liner

Qualto binds every AI trading claim to a live Binance order before the claim is trusted: the claim's ID is stamped inside the order, read back from the exchange, and diffed field by field — a claim Binance cannot prove locks the session and the agent stops trading.

## The Product

AI agents now trade real money, and their outputs narrate fills nobody can check. A confabulated fill looks identical to a real one until someone opens the exchange. Qualto closes that gap with **claim-bound orders**:

- Before any order is placed, the agent's intent is captured as a strict JSON claim.
- The harness — never the LLM — places the order with `newClientOrderId = claimId`, stamping the claim's identity into Binance's own order record.
- The order is read back twice (by order ID and by claim ID), six fields are diffed, and only a full match earns a **PROVED** verdict.
- Any failure produces **UNPROVED**, blocks the session, and refuses further writes until an operator recovers it.

It matters because the trust burden of agentic trading currently falls on users. Qualto moves the source of truth to the one party who already has it: the exchange.

## Our Vision

Verification for AI agents should not live in the agent's own dashboard. Long term, Qualto is a candidate platform primitive: **claim-bound orders as an Agent OS convention**. If Binance reserves the client-order-ID namespace for agent claims — or surfaces attestation natively in the Agent OS console — every agent on the platform becomes auditable by default, with zero new Binance infrastructure. The same claim-diff pattern generalizes to settlement ("no proof, no payment" for agentic commerce) and to multi-venue attestation.

## Track

**Binance Agent OS Mini Hackathon — Track A (working agent).**

Qualto is built on, and load-bearing on, the sponsor stack: it authenticates through a registered Agent OS host connector and executes through the Agent OS MCP endpoint (`agent.binance.com/mcp/agentic`). Remove Binance Agent OS and nothing above survives — no placement, no readback, no verdicts, no proof. The product's core artifact, the proof, *lives inside Binance's order history*.

## Core Idea

**The exchange is the judge.** Existing "agent accountability" approaches log agent behavior in their own databases — the operator must trust the logger. Qualto's verdict comes exclusively from live Binance readbacks through Agent OS. Two properties make this hard to fake:

1. **Pre-placement binding** — the claim ID is committed into the order before execution, so a post-hoc story cannot claim credit for an arbitrary fill.
2. **Fail-closed enforcement** — an unproved claim does not produce a warning badge; it locks the session so the agent cannot trade again until a human intervenes.

## How It Works

End to end, from a mandate to a verifiable receipt:

1. **Mandate** — the operator gives a bounded instruction ("buy 5 USDT of BNB").
2. **Context** — the harness fetches live price (`spot.tickerPrice`) and sub-account balance (`spot.getAccount`) and passes them, with the mandate, to the LLM.
3. **Claim** — the LLM drafts a strict nine-field JSON claim (schema-validated; unknown fields rejected). The LLM has zero tools — it only proposes.
4. **Intent receipt** — the claim is written to the append-only receipt log *before* placement, so an interrupted placement is always visible.
5. **Bind** — the harness places the order with `newClientOrderId = claimId` and immediately requests cancellation if configured (zero-cost proof pattern).
6. **Dual readback** — the order is fetched from Binance by `orderId` and by `origClientOrderId`; both readbacks must agree.
7. **Diff** — claimId, symbol, side, quantity (exact), price (±0.5%), status.
8. **Verdict** — PROVED / UNPROVED / PARTIAL / PENDING, written as a timestamped receipt. UNPROVED blocks the session; recovery requires an explicit operator action.

The same flow is exposed three ways: the `qualto` CLI, a standalone **MCP server** (`qualto-mcp`) for any MCP-compatible agent client, and an optional **SKILL.md agent skill** that teaches coding agents the policy.

## Architecture

```text
┌───────────────────────── operator ─────────────────────────┐
│  CLI (qualto claim / agent / verify / cleanup / smoke)     │
│  Web console (Next.js — qualto.vercel.app)                 │
└──────────┬────────────────────────────────────────────────┘
           │ mandates, claims (strict JSON)
┌──────────▼────────────────────────────────────────────────┐
│ Qualto harness (Python 3.11+, zero core deps)             │
│  engine/claim.py    strict claim schema, decimal-exact     │
│  engine/attest.py   bind, dual readback, field diff        │
│  engine/session.py  ACTIVE/BLOCKED/ERROR/CLOSED, replay    │
│                     protection, write gates                │
│  engine/receipts.py append-only JSONL, fsync, 0600         │
│  engine/verify.py   read-only re-verification              │
│  agent/loop.py      bounded LLM drafting (stdin prompt,    │
│                     120 s wall clock, zero tools)          │
│  mcp/server.py      FastMCP policy server (qualto-mcp)     │
│  mcp/client.py      Agent OS client, request-ID matching,  │
│                     two-layer tool allowlist               │
└──────────┬────────────────────────────────────────────────┘
           │ JSON-RPC over streamable HTTP, OAuth 2.1
┌──────────▼────────────────────────────────────────────────┐
│ Binance Agent OS MCP (agent.binance.com/mcp/agentic)       │
│  366 tools exposed → 6 allowlisted by Qualto               │
└──────────┬────────────────────────────────────────────────┘
           │ spot sub-account
┌──────────▼────────────────────────────────────────────────┐
│ Binance — the order record IS the proof                    │
└───────────────────────────────────────────────────────────┘
```

**Agent layer** — the LLM (bundled provider: Hermes) receives the mandate plus live context and returns one claim. It has no tools, its prompt travels over stdin, and every call is bounded by a wall-clock budget. **Skill/tool layer** — the SKILL.md skill (policy) and the `qualto-mcp` server (five tools, structural boundary). **Backend** — the Python package plus the Next.js console. **Auth** — host-managed OAuth. **Data flow** — claims and verdicts land in append-only receipts; the exchange remains the source of truth.

## What We Built

All of the following is implemented and tested today (11,433 tests, ~19 s, no network):

| Capability | Status |
|---|---|
| Claim schema validation (strict, decimal-exact, replay-proof) | Shipped |
| Claim-bound placement + dual readback + 6-field diff | Shipped, proven live |
| Verdicts PROVED / UNPROVED / PARTIAL / PENDING | Shipped |
| Session states ACTIVE / BLOCKED / ERROR / CLOSED with write gates | Shipped |
| Append-only receipts (fsync, 0600, intent-before-placement) | Shipped |
| Orphan-order cleanup by claim ID | Shipped |
| `qualto verify` — read-only re-verification against live Binance | Shipped |
| Standalone MCP server (`qualto-mcp`, 5 tools) | Shipped |
| Agent skill (`qualto-claim-bound-trading`) | Shipped |
| Web console (landing + docs) — [qualto.vercel.app](https://qualto.vercel.app) | Shipped |
| CI (pytest / ruff / mypy) + GitHub Pages + Vercel deploys | Shipped |

## Agent Integrations

| Agent | How it interacts | Status |
|---|---|---|
| **OpenAI Codex** | The OAuth credential rides Codex's registered Binance Agent OS connector (`QUALTO_CODEX_CREDENTIALS_FILE`). All live proofs in this repo ran on this path. | Tested, live-proven |
| **Claude Code / Claude Desktop** | Install the agent skill (`~/.claude/skills/`) for policy, and/or connect `qualto-mcp` as a stdio MCP server (config in [`examples/mcp/mcp-client.json`](examples/mcp/mcp-client.json)). | Supported |
| **Qwen Code** | Same SKILL.md skill installs to `~/.qwen/skills/`. | Supported |
| **Any MCP-compatible client** | `pip install -e ".[mcp]"` then run `qualto-mcp`. The client config is client-neutral. | Supported |

In every case the agent never places raw orders — it proposes claims, and the Qualto boundary (CLI or MCP server) is the only path to the exchange.

## Binance Integration

- **Endpoint:** Binance Agent OS MCP (`agent.binance.com/mcp/agentic`), JSON-RPC over streamable HTTP, protocol `2025-03-26`, OAuth 2.1 via the registered host connector.
- **Tool funnel:** 366 tools exposed by the server → **6 allowlisted** in Qualto: `spot.getAccount`, `spot.tickerPrice`, `spot.newOrder`, `spot.getOrder`, `spot.myTrades` (reserved for fills-at-close), `spot.deleteOrder`. Anything else is rejected client-side before a request exists.
- **Order identity:** every order is placed with `newClientOrderId = claimId`, making the attestation visible in Binance's own order history UI.
- **Envelope:** all activity is confined to a funded Agentic sub-account; main-account funds are structurally out of reach.

## Skill Integrations

- **`qualto-claim-bound-trading`** (in [`skills/`](skills/qualto-trading/SKILL.md)) — teaches any SKILL.md-compatible coding agent the policy: never call Binance order endpoints directly, always go through the harness, report verdicts verbatim, never soften an UNPROVED, stop when the session locks, and use the zero-cost dust-order pattern for demos.
- **MCP tools exposed by `qualto-mcp`:** `qualto_session_status`, `qualto_read_context` (live price + balance), `qualto_attest_claim` (place, read back, verdict), `qualto_cleanup_claim` (orphan recovery), `qualto_verify_receipts` (read-only re-check). Live writes additionally require `QUALTO_ENABLE_LIVE_WRITE=1` **and** a per-call `confirm_live_write` flag.

Discovery is by standard skill-directory convention and MCP client config; the two layers compose — an agent can run the skill for policy and the MCP server for execution.

## Other Integrations

- **Web console** — Next.js 15 app (this repo, `web/`), deployed to [qualto.vercel.app](https://qualto.vercel.app) and GitHub Pages.
- **Hermes** — optional LLM provider for the bundled drafting loop (stdin prompt transport, 90 s per call, 120 s total budget).
- **CI/CD** — GitHub Actions: test/lint/type workflow on every push; Pages and Vercel deploy from `main`.

## Authentication

- Users do not give Qualto any Binance API keys. Authentication rides a **registered host connector's OAuth credential** (Codex) via `QUALTO_CODEX_CREDENTIALS_FILE`.
- The credential is loaded per request, kept in memory for that request, never logged, never written to receipts, with expiry checked on every call.
- Missing, malformed, or expired credential ⇒ fail closed, no order.
- Sessions are local, explicit, and recoverable; MCP-server sessions additionally gate writes behind the environment flag plus the per-call confirmation.

## Security

- **Permission model:** the harness is the only component that places orders; the LLM has zero tools; the MCP surface is five fixed tools; the underlying Binance operations are a 6-entry allowlist enforced before any request is built.
- **Secret handling:** per-request in-memory credential loads; a dedicated test asserts no-leak into logs, receipts, or error strings.
- **Input validation:** claims are validated against a closed schema at the boundary — unknown fields, floats for quantities, reused claim IDs, and out-of-range prices are rejected before placement.
- **Access control:** write commands require `--confirm-live-write` (CLI) or the double gate (MCP); exit code 2 and nothing is sent without it.
- **Transport:** JSON-RPC responses are matched to request IDs; mismatches are rejected.

## Safety

- **Agents are allowed to:** read live context, draft claims, and — through the Qualto boundary — place claim-bound orders and cancel the exact order bound to a claim.
- **Agents are not allowed to:** touch withdrawal, transfer, futures, or margin paths (not in the allowlist); place any order that is not claim-bound; unblock a session they got blocked.
- **Requires explicit human approval:** every live write (confirmation flag), every session recovery, every cleanup.
- **High-risk handling:** an order whose placement outcome is unknown produces an `order_submitted` intent receipt and a `qualto cleanup` path that resolves the order by claim ID and cancels the exact exchange order. Everything fails closed: the safe state is "no order."

## Prompt Examples

With the skill installed (Claude Code / Qwen Code):

```text
Simple:    "Buy 5 USDT of BNB on my sub-account and prove it."
Advanced:  "Propose a below-market dust limit for BNBUSDT that proves the
            claim-bind loop at zero cost, then cancel it."
Multi-step:"Check the session status, read live BNB price and balance,
            propose a claim that spends under 5 USDT, attest it, cancel it,
            then re-verify all receipts against Binance."
```

With any MCP client connected to `qualto-mcp`, the same intents map to tool calls:

```json
{"tool": "qualto_read_context", "arguments": {"symbol": "BNBUSDT"}}
{"tool": "qualto_attest_claim", "arguments": {"claim": {...}, "confirm_live_write": true}}
{"tool": "qualto_verify_receipts", "arguments": {}}
```

CLI equivalents: `qualto propose --mandate "buy 5 USDT of BNB"`, `qualto claim --claim-file c.json --confirm-live-write --cancel-after-attestation`, `qualto verify`.

## Run It Yourself

**Requirements:** Python 3.11+; a Binance account with a funded **Agentic sub-account**; a registered host credential (Codex CLI authenticated with the Binance connector) exported as `QUALTO_CODEX_CREDENTIALS_FILE`. Optional: Hermes for the drafting loop (`QUALTO_HERMES_BIN` / `QUALTO_HERMES_PYTHON`); Node 22+ for the web console only.

No database, no API keys of your own, no main-account access — ever.

## Quickstart

```bash
git clone https://github.com/mystiquemide/qualto && cd qualto
python3 -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/pytest -q                                  # 11,433 tests, ~19 s

export QUALTO_CODEX_CREDENTIALS_FILE=/path/to/host-credentials.json
.venv/bin/qualto smoke                               # read-only gateway check

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

To serve the web console locally: `cd web && npm install && npm run dev`.

## Benchmarks

Measured on the live Agent OS gateway and the repo's own test suite, September 2026, single VPS session, BNBUSDT:

| Task | Method | Result |
|---|---|---|
| PROVED verdict → confirmed cancellation | Wall clock between receipt timestamps on live order `12565050896` | **353 ms** |
| Full gateway cycle (initialize + tools/list + account read) | 3 timed `qualto smoke` runs | **1.2–1.4 s** |
| Mandate → PROVED (LLM-bound) | Live `qualto agent` run | **~28 s** |
| Test suite | `pytest -q`, no network | **11,433 tests in ~19 s** |

Success criterion for attestation is not statistical: it is per-order and binary — all six fields match on a live dual readback, or the verdict is not PROVED.

## Benchmark Scores

The 11,433-test matrix is the reliability benchmark, and it is fully reproducible with one command:

| Suite | Cases | Result |
|---|---|---|
| Claim round-trip contract matrix (parameterized: side × order type × status × quantities, price tolerance, envelope shapes, forbidden operations) | 10,665 | Pass |
| MCP server tools and write gates | 12 | Pass |
| Focused behavioral tests (dual readback, replay, block, cleanup, error states, CLI, pair support, receipts) | 756 | Pass |
| **Total** | **11,433** | **Pass** |

No comparative claims against other tools are made — no baseline exists, and Qualto's own rule is: no unproved claims.

## Limitations

- Single session, spot only, one symbol per claim; attestation is per-order, not per-strategy.
- The claim file — not the mandate — is the binding contract.
- Third-party agent OAuth identities are not admitted by Binance yet; Qualto runs on the registered host-credential path and fails closed when unavailable.
- The MCP server is stdio-only; remote-HTTP clients (ChatGPT, Devin) cannot connect today.
- Qualto proves that a trade happened exactly as claimed — it does not judge whether the trade was a good idea.
- Human supervision is required for: every live write, every session recovery, and any state after an UNPROVED verdict.

## Future Vision

- **Native console attestation** — claim-bound orders surfaced inside the Binance Agent OS console.
- **No proof, no payment** — attestation as the settlement gate for agentic commerce (x402).
- **Remote MCP** — HTTP transport so any hosted agent can connect.
- **Multi-venue attestation** — the same claim-diff pattern over `convert.orderStatus`.
- **Multi-session persistence** — receipt-derived session rebuilds across runs.

## Contributing

```bash
git clone https://github.com/mystiquemide/qualto && cd qualto
python3 -m venv .venv && .venv/bin/pip install -e ".[test,quality]"
.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/mypy
```

PR expectations: tests for every behavioral change, all quality gates green, no credential or receipt data committed. New Binance operations go into the allowlist in `qualto/mcp/client.py` with negative tests; new agent surfaces (skills, MCP tools) belong in `skills/` and `qualto/mcp/server.py` respectively, with the same fail-closed gates. MIT license; keep the invariant intact — **no fill, no claim**.
