import Link from "next/link";
import DocsNav from "@/components/DocsNav";

const REPO = "https://github.com/mystiquemide/qualto";

export default function DocsPage() {
  return (
    <div className="docs">
      <nav className="topnav docsnav">
        <div className="wrap nav-in">
          <Link className="brand" href="/">
            <svg width="24" height="24" viewBox="0 0 128 128" aria-hidden="true">
              <rect x="2" y="2" width="124" height="124" rx="26" fill="#12161C" stroke="#2B3139" />
              <line x1="46" y1="26" x2="46" y2="104" stroke="#F0B90B" strokeWidth="6" />
              <rect x="33" y="52" width="26" height="28" rx="3" fill="#F0B90B" />
              <path d="M30 70 L52 92 L100 40" fill="none" stroke="#16C784" strokeWidth="11" strokeLinecap="square" />
            </svg>
            QUALTO <span style={{ color: "var(--muted)", fontWeight: 400, fontSize: 13, letterSpacing: ".04em" }}>/ docs</span>
          </Link>
          <div className="nav-right">
            <Link href="/">Home</Link>
            <a href={REPO}>GitHub</a>
            <a className="btn btn-gold" href="#cli">CLI reference</a>
          </div>
        </div>
      </nav>

      <div className="layout">
        <DocsNav />

        <main>
          <div className="doc-head">
            <span className="kicker">Qualto documentation</span>
            <h1>Claim-bound orders on Binance Agent OS</h1>
            <p>Everything on this page reflects the shipped code at <code>main</code>. No command here is hypothetical.</p>
          </div>

          <section id="install">
            <span className="kicker">Start</span>
            <h2>Install</h2>
            <p>Python 3.11 or newer. Zero runtime dependencies, the whole gateway is standard library.</p>
            <pre>{`# from the repository root
python3 -m venv .venv
.venv/bin/pip install -e ".[test,quality]"
.venv/bin/pytest -q   # 11,414 tests, ~16s, no network`}</pre>
            <p>The <code>qualto</code> command is installed on your PATH by the same step.</p>
          </section>

          <section id="quickstart">
            <h2>Quickstart</h2>
            <p>The full loop, read-only first, then one zero-cost proof cycle:</p>
            <pre>{`# 1. gateway check: initialize, tools/list, account read. read-only.
qualto smoke

# 2. draft a claim from a mandate. no order is placed.
qualto propose --mandate "buy 5 USDT of BNB" --symbol BNBUSDT

# 3. place, attest, prove, cancel. real order, zero cost pattern.
qualto claim --claim-file my-claim.json \\
  --receipts-file runtime/receipts.jsonl \\
  --confirm-live-write \\
  --cancel-after-attestation

# 4. re-verify any receipts file against live Binance. read-only.
qualto verify --receipts-file runtime/receipts.jsonl`}</pre>
            <div className="note safe"><b>Zero-cost proof pattern:</b> a below-market dust LIMIT order with <code>--cancel-after-attestation</code> exercises the entire bind, dual readback, attestation, and cancellation cycle with no fill. Every live proof in this repository used it.</div>
          </section>

          <section id="prereq">
            <h2>Prerequisites</h2>
            <table>
              <tbody>
                <tr><th>Requirement</th><th>Detail</th></tr>
                <tr><td>Binance Agentic sub-account</td><td>Funded. This is the structural envelope: the agent can never touch main-account funds.</td></tr>
                <tr><td>Supported host credential</td><td>A registered host (for example the Codex CLI with the Binance connector authenticated). Set <code>QUALTO_CODEX_CREDENTIALS_FILE</code> to your credential path.</td></tr>
                <tr><td>Optional: Hermes</td><td>Only for the bundled agent loop (<code>qualto propose</code> / <code>qualto agent</code>). Override with <code>QUALTO_HERMES_BIN</code> and <code>QUALTO_HERMES_PYTHON</code>.</td></tr>
              </tbody>
            </table>
            <p>Qualto reads the credential per request, in memory, and never writes it to logs or receipts. If it is missing, malformed, or expired, every command fails closed with no order sent.</p>
          </section>

          <section id="claim">
            <span className="kicker">Concepts</span>
            <h2>The claim contract</h2>
            <p>A claim is a strict JSON object. Exactly these nine fields, nothing more, nothing less. Unknown fields are rejected before anything is sent.</p>
            <pre>{`{
  "claimId":  "qualto-claim-<12 lowercase alphanumerics>",
  "mandate":  "what the operator asked for",
  "symbol":   "BNBUSDT",
  "side":     "BUY | SELL",
  "orderType": "LIMIT | MARKET",
  "quantity": "0.009",
  "price":    "600",          // null for MARKET
  "status":   "NEW | FILLED | PARTIALLY_FILLED | CANCELED",
  "reason":   "the agent's honest reasoning, 1-1000 chars"
}`}</pre>
            <h3>Field rules</h3>
            <table>
              <tbody>
                <tr><th>Field</th><th>Rule</th></tr>
                <tr><td><code>claimId</code></td><td>Format <code>qualto-claim-</code> plus 12 lowercase alphanumerics. Single-use per session: a replay is rejected before placement and logged.</td></tr>
                <tr><td><code>quantity</code>, <code>price</code></td><td>Positive finite decimal strings. Never floats. Sent to Binance exactly as written.</td></tr>
                <tr><td><code>price</code></td><td>Required for LIMIT, must be <code>null</code> for MARKET.</td></tr>
                <tr><td><code>status</code></td><td>The status the claim commits to at readback. <code>NEW</code> for resting limit intent, <code>FILLED</code> for market intent.</td></tr>
                <tr><td><code>mandate</code>, <code>reason</code></td><td>1 to 500 and 1 to 1000 characters. The mandate is the human instruction; the reason is the agent&apos;s stated justification.</td></tr>
              </tbody>
            </table>
          </section>

          <section id="binding">
            <h2>Claim binding</h2>
            <p>Binding happens at placement. The harness, never the LLM, sends the order with <code>newClientOrderId = claimId</code>. From that moment the claim&apos;s ID lives inside Binance&apos;s own order record, visible in Binance order history.</p>
            <p>At readback the order is fetched twice from Binance Agent OS: by <code>orderId</code> and by <code>origClientOrderId</code>. Both readbacks must return the same order. Then six fields are diffed:</p>
            <table>
              <tbody>
                <tr><th>Field</th><th>Match rule</th></tr>
                <tr><td>claimId</td><td>exact, against the order&apos;s client order ID</td></tr>
                <tr><td>symbol, side, status</td><td>exact</td></tr>
                <tr><td>quantity</td><td>exact</td></tr>
                <tr><td>price</td><td>within 0.5% of the claimed price</td></tr>
              </tbody>
            </table>
          </section>

          <section id="verdicts">
            <h2>Verdicts</h2>
            <table>
              <tbody>
                <tr><th>Verdict</th><th>Meaning</th><th>Session effect</th></tr>
                <tr><td><span className="tag t-green">PROVED</span></td><td>All six fields matched on a live dual readback</td><td>none</td></tr>
                <tr><td><span className="tag t-red">UNPROVED</span></td><td>The exchange could not prove the claim: readback failure, disagreement, or field mismatch</td><td>session BLOCKED</td></tr>
                <tr><td><span className="tag t-amber">PARTIAL</span></td><td>Identity matched and the order is partially filled. The filled quantity is recorded.</td><td>none</td></tr>
                <tr><td><span className="tag t-amber">PENDING</span></td><td>A claimed market order is still NEW. Retried up to 3 times, 2 seconds apart, before a final verdict.</td><td>none until retries exhaust</td></tr>
              </tbody>
            </table>
            <div className="note"><b>No third path:</b> a claim is never marked PROVED from any source other than a live Binance readback. Not the LLM, not the log, not the operator.</div>
          </section>

          <section id="sessions">
            <h2>Session states</h2>
            <table>
              <tbody>
                <tr><th>State</th><th>Entered when</th><th>Can write orders?</th></tr>
                <tr><td><code>CREATED</code> → <code>CONNECTED</code> → <code>ACTIVE</code></td><td>Normal start</td><td>yes, when ACTIVE</td></tr>
                <tr><td><code>BLOCKED</code></td><td>Any UNPROVED verdict, failed cancellation, or unresolved cleanup</td><td>no. further placement refused</td></tr>
                <tr><td><code>ERROR</code></td><td>Agent or execution failure before attestation</td><td>no</td></tr>
                <tr><td><code>CLOSED</code></td><td>Session close</td><td>no, terminal</td></tr>
              </tbody>
            </table>
            <p>From BLOCKED, an operator can still cancel a known order (cleanup is allowed, new writes are not), then recover the session explicitly. The agent cannot unblock itself.</p>
          </section>

          <section id="cli">
            <span className="kicker">Reference</span>
            <h2>CLI reference</h2>

            <h3><code>qualto smoke</code></h3>
            <p>Read-only gateway check: MCP initialize, tools/list, account read. Prints client ID, protocol version, visible tool count, and balance record count.</p>

            <h3><code>qualto propose</code></h3>
            <table>
              <tbody>
                <tr><th>Flag</th><th>Default</th><th>Meaning</th></tr>
                <tr><td><code>--mandate</code></td><td>required</td><td>Free-text operator instruction, 1-500 characters.</td></tr>
                <tr><td><code>--symbol</code></td><td>BNBUSDT</td><td>Uppercase Binance spot symbol.</td></tr>
              </tbody>
            </table>
            <p>Fetches live price and balance, asks the bundled LLM loop for one claim, validates it, prints the claim JSON. Places no order.</p>

            <h3><code>qualto claim</code></h3>
            <table>
              <tbody>
                <tr><th>Flag</th><th>Default</th><th>Meaning</th></tr>
                <tr><td><code>--claim-file</code></td><td>required</td><td>Path to a claim JSON object.</td></tr>
                <tr><td><code>--receipts-file</code></td><td>runtime/receipts.jsonl</td><td>Append-only JSONL receipt path.</td></tr>
                <tr><td><code>--confirm-live-write</code></td><td>off</td><td>Authorizes the live order request. Without it: exit 2, nothing sent.</td></tr>
                <tr><td><code>--cancel-after-attestation</code></td><td>off</td><td>Cancels the proved order immediately after dual readback.</td></tr>
              </tbody>
            </table>

            <h3><code>qualto agent</code></h3>
            <p>One command: mandate → generated claim → placed order → attestation → optional cancellation. Flags of <code>propose</code> and <code>claim</code>, plus:</p>
            <table>
              <tbody>
                <tr><th>Flag</th><th>Meaning</th></tr>
                <tr><td><code>--disconnect-before-order</code></td><td>Severs the gateway after claim generation, proving the negative path: UNPROVED, BLOCKED, then reconnect and recover.</td></tr>
              </tbody>
            </table>

            <h3><code>qualto cleanup</code></h3>
            <p>Recovers an orphan order by claim ID and cancels the exact exchange order. Use when a placement&apos;s outcome is unknown. Requires <code>--confirm-live-write</code>.</p>

            <h3><code>qualto verify</code></h3>
            <p>Re-verifies every claim attestation in a receipts file against live Binance state. Read-only, calls only <code>spot.getOrder</code>. Prints a per-claim match table.</p>
          </section>

          <section id="receipts">
            <h2>Receipt events</h2>
            <p>Receipts are append-only JSONL. Every line is timestamped and written with fsync before the flow continues. The <code>verdict</code> field appears only on attestation and cancellation events; lifecycle events use <code>outcome</code>.</p>
            <table>
              <tbody>
                <tr><th>Event</th><th>Written when</th><th>Key fields</th></tr>
                <tr><td><code>order_submitted</code></td><td>Immediately before the placement call</td><td>claim, orderRequest</td></tr>
                <tr><td><code>claim_attestation</code></td><td>After dual readback and field diff</td><td>claim, attestation, both readbacks</td></tr>
                <tr><td><code>order_cancellation</code></td><td>After a proved cancellation</td><td>order, verdict</td></tr>
                <tr><td><code>order_cleanup</code></td><td>Orphan resolution attempt</td><td>outcome: resolved / unresolved</td></tr>
                <tr><td><code>claim_rejected</code></td><td>Claim ID replay attempt</td><td>claimId, reason</td></tr>
                <tr><td><code>gateway_recovery</code></td><td>Reconnect and session recovery</td><td>claimId, reason</td></tr>
                <tr><td><code>session_error</code></td><td>Session enters ERROR</td><td>errorType (class name only, never the message)</td></tr>
              </tbody>
            </table>
          </section>

          <section id="exitcodes">
            <h2>Exit codes</h2>
            <table>
              <tbody>
                <tr><th>Code</th><th>Meaning</th></tr>
                <tr><td><code>0</code></td><td>Success. For write commands: verdict PROVED.</td></tr>
                <tr><td><code>1</code></td><td>Failure or unproved verdict. Read the reason on stderr.</td></tr>
                <tr><td><code>2</code></td><td>Live-write confirmation missing. Nothing was sent.</td></tr>
              </tbody>
            </table>
          </section>

          <section id="verify">
            <span className="kicker">Trust</span>
            <h2>Verification</h2>
            <p>Qualto&apos;s receipts are convenience. The proof is the Binance order record.</p>
            <table>
              <tbody>
                <tr><th>Binance order</th><th>Claim ID</th><th>Verdict</th></tr>
                <tr><td>12565050896</td><td>qualto-claim-56eda03b6069</td><td><span className="tag t-green">PROVED</span> then CANCELED</td></tr>
                <tr><td>12565013192</td><td>qualto-claim-live00000002</td><td><span className="tag t-green">PROVED</span> then CANCELED</td></tr>
              </tbody>
            </table>
            <p>Both orders remain in Binance order history with the claim IDs above as their client order IDs. To re-check any receipts file against the exchange right now:</p>
            <pre>{`qualto verify --receipts-file runtime/receipts.jsonl
# claimId                  orderId      recorded  live     matched
# qualto-claim-56eda03b6069 12565050896  PROVED    PROVED   true`}</pre>
          </section>

          <section id="security">
            <h2>Security model</h2>
            <h3>Tool allowlist</h3>
            <p>Binance Agent OS exposes 366 tools. Qualto&apos;s gateway admits exactly 6: <code>spot.getAccount</code>, <code>spot.tickerPrice</code>, <code>spot.newOrder</code>, <code>spot.getOrder</code>, <code>spot.myTrades</code>, <code>spot.deleteOrder</code>. Everything else is rejected client-side before a request exists. No withdrawals, no transfers, no futures, no margin.</p>
            <h3>Who can place orders</h3>
            <p>Only the harness, only claim-bound, only after <code>--confirm-live-write</code>. The LLM has no tools, receives the prompt over stdin, and its output is validated against the strict claim schema with the harness-assigned claim ID enforced.</p>
            <h3>Credential handling</h3>
            <p>The host credential is loaded per request, kept in memory for that request, never logged, never in receipts, never in error messages. Expiry is checked on every call. Missing, malformed, or expired: fail closed, no order.</p>
          </section>

          <section id="skill">
            <h2>Agent skill</h2>
            <p>Qualto ships as a SKILL.md-compatible agent skill that teaches any agent to trade claim-bound: never place raw orders, always go through the harness, never soften an UNPROVED, stop when the session locks.</p>
            <pre>{`# Claude Code
cp -r qualto/skills/qualto-trading ~/.claude/skills/
# Qwen Code
cp -r qualto/skills/qualto-trading ~/.qwen/skills/`}</pre>
          </section>

          <section id="limits">
            <h2>Limits</h2>
            <p>Single session, spot only, one symbol per claim. Attestation is per-order, not per-strategy. Qualto does not judge whether a trade was smart, only whether it happened exactly as claimed. The claim file, not the mandate, is the binding contract. Third-party agent OAuth identities are not yet admitted by Binance; Qualto runs on the supported host-credential path.</p>
          </section>
        </main>
      </div>
    </div>
  );
}
