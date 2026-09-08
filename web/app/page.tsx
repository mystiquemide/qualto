import Link from "next/link";
import SectionNav from "@/components/SectionNav";
import Reveal from "@/components/Reveal";

const REPO = "https://github.com/mystiquemide/qualto";

const TICKER_ITEMS = [
  "orderId 12565050896 · qualto-claim-56eda03b6069 · PROVED",
  "orderId 12565013192 · qualto-claim-live00000002 · PROVED",
  "cancel 12565050896 · CANCELED · executedQty 0.00000000",
  "cancel 12565013192 · CANCELED · executedQty 0.00000000",
  "dual readback · 6/6 fields matched · 353 ms",
  "readbackByOrderId + readbackByOrigClientOrderId · agree",
  "claim_rejected · duplicate claimId · before placement",
  "session BLOCKED · unproved claim · writes refused",
];

function Logo({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 128 128" aria-hidden="true">
      <rect x="2" y="2" width="124" height="124" rx="26" fill="#12161C" stroke="#2B3139" />
      <line x1="46" y1="26" x2="46" y2="104" stroke="#F0B90B" strokeWidth="6" />
      <rect x="33" y="52" width="26" height="28" rx="3" fill="#F0B90B" />
      <path d="M30 70 L52 92 L100 40" fill="none" stroke="#16C784" strokeWidth="11" strokeLinecap="square" />
    </svg>
  );
}

export default function Home() {
  return (
    <div className="landing">
      <nav className="topnav">
        <a className="skip-link" href="#main">Skip to content</a>
        <div className="wrap nav-in">
          <a className="brand" href="/">
            <Logo />
            QUALTO
          </a>
          <SectionNav />
          <div className="nav-links nav-links-static">
            <Link href="/docs">Docs</Link>
            <a href={REPO}>GitHub</a>
          </div>
          <a className="btn btn-gold nav-cta" href={REPO}>Get started</a>
        </div>
      </nav>

      <main id="main" className="landing-sections">
        <header className="hero" id="top">
          <div className="hero-img" aria-hidden="true"></div>
          <div className="wrap hero-grid">
            <div className="hero-copy">
              <h1 className="hero-anim" style={{ animationDelay: "0s" }}>No fill,<br /><span className="stamp-w">no claim.</span></h1>
              <p className="lede hero-anim" style={{ animationDelay: "0.1s" }}>
                AI agents narrate trades. Qualto makes them prove it. Every claim is
                stamped into a live Binance order and read back from the exchange itself.
                A claim Binance cannot prove locks the session, and the agent stops trading.
              </p>
              <div className="hero-ctas hero-anim" style={{ animationDelay: "0.2s" }}>
                <a className="btn btn-gold" href={REPO}>Get started →</a>
                <Link className="btn btn-line" href="/docs">Read the docs</Link>
              </div>
              <p className="hero-note hero-anim" style={{ animationDelay: "0.3s" }}>
                The proof is public: order <b>12565050896</b> is in Binance order history
                right now, carrying its claim ID.
              </p>
            </div>
            <div className="term hero-anim" style={{ animationDelay: "0.25s" }} aria-label="Real attestation receipt from a live Binance session">
              <div className="term-head">
                <span className="term-dot"></span><span className="term-dot"></span><span className="term-dot"></span>
                <span className="term-title">receipts.jsonl · claim_attestation</span>
                <span className="term-badge">PROVED</span>
              </div>
              <pre>{`{
  "event": "claim_attestation",
  "claim": {
    "claimId": "qualto-claim-56eda03b6069",
    "mandate": "buy exactly 0.009 BNBUSDT at a 600 limit",
    "symbol": "BNBUSDT", "side": "BUY",
    "orderType": "LIMIT", "quantity": "0.009", "price": "600"
  },
  "attestation": {
    "verdict": "PROVED",
    "orderId": 12565050896,
    "reason": "all claim fields match",
    "executedQty": "0.00000000"
  },
  "readbackByOrderId":          { "status": "NEW" },
  "readbackByOrigClientOrderId": { "status": "NEW" }
}`}</pre>
              <div className="term-foot">dual readback agreed · 6/6 fields matched · <span className="ok">verified on Binance</span></div>
            </div>
          </div>
        </header>

        <div className="ticker" aria-label="Live proof receipts">
          <div className="ticker-track">
            {[...TICKER_ITEMS, ...TICKER_ITEMS].map((item, i) => (
              <span key={i} className="ticker-item">
                {item.includes("PROVED") || item.includes("agree") ? <i className="ok">●</i> : item.includes("BLOCKED") || item.includes("rejected") ? <i className="bad">●</i> : <i className="ok">●</i>}
                {item}
              </span>
            ))}
          </div>
        </div>

        <section className="stats" aria-label="Measured facts">
          <div className="wrap">
            <div className="stats-in">
              <div className="stat"><div className="n">11,414</div><div className="l">tests passing, zero network</div></div>
              <div className="stat"><div className="n"><em>353 ms</em></div><div className="l">from PROVED verdict to confirmed cancel</div></div>
              <div className="stat"><div className="n">366 → 6</div><div className="l">Binance tools exposed, the rest blocked</div></div>
              <div className="stat"><div className="n">0</div><div className="l">runtime dependencies, Python 3.11+ stdlib only</div></div>
            </div>
            <p className="stats-sub">Every number on this page is measured. Every claim is bound to a Binance order. <b>No mocks presented as real, anywhere.</b></p>
          </div>
        </section>

        <section className="problem" id="problem">
          <div className="problem-bg" aria-hidden="true"></div>
          <div className="wrap">
            <Reveal><span className="kicker">The problem</span>
            <h2>Agents narrate fills.<br />Nobody can check them.</h2>
            <p className="lede">You ask an AI agent to buy crypto with real money. It replies: done, filled. The message looks confident. It might be true. It might be a hallucination. Until you open the exchange yourself, the two look identical.</p></Reveal>
            <Reveal delay={0.1}><div className="contrast">
              <div className="say">
                <div className="who">What the agent says</div>
                <div className="bubble">Bought 0.009 BNB at 600. <span className="tick">✓ Filled.</span></div>
                <p className="verdict-line">Confident. Detailed. Possibly entirely invented.</p>
              </div>
              <div className="say lie">
                <div className="who">What you actually know</div>
                <div className="bubble"><span className="q">?</span> Nothing the exchange confirmed.</div>
                <p className="verdict-line">The chat log is not evidence. The order book is.</p>
              </div>
            </div></Reveal>
          </div>
        </section>

        <section id="how">
          <div className="wrap">
            <Reveal><span className="kicker">How it works</span>
            <h2>Claim-bound orders, end to end.</h2></Reveal>
            <Reveal delay={0.1}><div className="steps">
              <div className="step"><div className="num">01</div><h3>Mandate</h3><p>You give the agent a bounded instruction. &quot;Buy 5 USDT of BNB.&quot; Nothing moves yet.</p></div>
              <div className="step"><div className="num">02</div><h3>Claim</h3><p>The agent drafts a strict JSON claim with a unique ID. Unknown fields are rejected.</p></div>
              <div className="step"><div className="num">03</div><h3>Bind</h3><p>The harness places the order with <code>newClientOrderId = claimId</code>. The claim is now stamped inside the Binance order itself.</p></div>
              <div className="step"><div className="num">04</div><h3>Read back twice</h3><p>The order is fetched from Binance by order ID and by claim ID. Both readbacks must agree.</p></div>
              <div className="step"><div className="num">05</div><h3>Diff</h3><p>Symbol, side, quantity exact, price within 0.5%, status. Every field, every time.</p></div>
              <div className="step"><div className="num">06</div><h3>Verdict</h3><p>PROVED, or UNPROVED and the session locks. No third option.</p></div>
            </div>
            </Reveal>
            <Reveal delay={0.15}><p className="how-foot">The harness places orders. <b>The model only proposes them.</b></p></Reveal>
          </div>
        </section>

        <section id="enforcement">
          <div className="wrap">
            <Reveal><span className="kicker">Enforcement, not observation</span>
            <h2>What happens when the agent lies.</h2></Reveal>
            <Reveal delay={0.1}><div className="enf-table">
              <div className="enf-row"><div className="enf-head">Violation</div><div className="enf-head">Result</div></div>
              <div className="enf-row"><div className="what">Claim cannot be resolved (gateway down, order missing)</div><div className="out"><span className="tag tag-red">UNPROVED</span>session BLOCKED, further orders refused</div></div>
              <div className="enf-row"><div className="what">The two readbacks disagree</div><div className="out"><span className="tag tag-red">UNPROVED</span>session locked</div></div>
              <div className="enf-row"><div className="what">Field mismatch (quantity, price beyond 0.5%, status)</div><div className="out"><span className="tag tag-red">UNPROVED</span>per-field diff recorded</div></div>
              <div className="enf-row"><div className="what">Claim ID reused, a replay attempt</div><div className="out"><span className="tag tag-red">REJECTED</span>before placement, logged</div></div>
              <div className="enf-row"><div className="what">Order partially filled</div><div className="out"><span className="tag tag-amber">PARTIAL</span>filled quantity shown, never a silent pass</div></div>
              <div className="enf-row"><div className="what">Market order still NEW at readback</div><div className="out"><span className="tag tag-amber">PENDING</span>retried 3× at 2s, never a false UNPROVED</div></div>
            </div>
            </Reveal>
            <Reveal delay={0.15}><p className="enf-foot">Recovery requires an explicit operator action. <b>The agent cannot unblock itself.</b></p></Reveal>
          </div>
        </section>

        <section id="proof">
          <div className="wrap">
            <Reveal><span className="kicker">Verify it yourself</span>
            <h2>The proof lives on Binance, not on this page.</h2></Reveal>
            <Reveal delay={0.1}><div className="proof-grid">
              <div>
                <table className="orders">
                  <thead><tr><th>Binance order</th><th>Claim ID</th><th>Result</th></tr></thead>
                  <tbody>
                    <tr><td>12565050896</td><td>qualto-claim-56eda03b6069</td><td className="ok">PROVED → CANCELED</td></tr>
                    <tr><td>12565013192</td><td>qualto-claim-live00000002</td><td className="ok">PROVED → CANCELED</td></tr>
                  </tbody>
                </table>
                <p className="proof-note">Both orders are <b>still in Binance order history right now</b>, each carrying its claim ID as the client order ID. Placed as below-market dust limits, read back as PROVED, cancelled in 353 ms, confirmed at zero execution.</p>
                <div className="proof-cmd"><span className="p">$</span> qualto verify --receipts-file receipts.jsonl<br /><span className="p">re-reads every claim against live Binance. read-only.</span></div>
              </div>
              <div className="diff">
                <div className="diff-head"><span className="t">field diff · order 12565050896</span><span className="b">6/6 MATCHED</span></div>
                <div className="diff-row"><span className="f">claimId</span><span className="e">qualto-claim-56eda03b6069</span><span className="a">qualto-claim-56eda03b6069</span><span className="c">✓</span></div>
                <div className="diff-row"><span className="f">symbol</span><span className="e">BNBUSDT</span><span className="a">BNBUSDT</span><span className="c">✓</span></div>
                <div className="diff-row"><span className="f">side</span><span className="e">BUY</span><span className="a">BUY</span><span className="c">✓</span></div>
                <div className="diff-row"><span className="f">quantity</span><span className="e">0.009</span><span className="a">0.00900000</span><span className="c">✓</span></div>
                <div className="diff-row"><span className="f">price</span><span className="e">600</span><span className="a">600.00000000</span><span className="c">✓</span></div>
                <div className="diff-row"><span className="f">status</span><span className="e">NEW</span><span className="a">NEW</span><span className="c">✓</span></div>
              </div>
            </div></Reveal>
          </div>
        </section>

        <section id="performance">
          <div className="wrap">
            <Reveal><span className="kicker">Performance</span>
            <h2>Measured, not marketed.</h2></Reveal>
            <Reveal delay={0.1}><div className="perf">
              <div className="perf-cell"><div className="v">353 ms</div><div className="k">PROVED verdict to confirmed cancellation</div></div>
              <div className="perf-cell"><div className="v">1.3 s</div><div className="k">full gateway cycle, three MCP round trips</div></div>
              <div className="perf-cell"><div className="v">~28 s</div><div className="k">mandate to PROVED, LLM-bound</div></div>
              <div className="perf-cell"><div className="v">7.4 s</div><div className="k">full test suite, 5,637 cases</div></div>
            </div>
            </Reveal>
            <Reveal delay={0.15}><p className="perf-line">Verification costs <b>350 milliseconds</b>. The thinking costs <i>28 seconds</i>. The enforcement is never the bottleneck. The model is.</p></Reveal>
          </div>
        </section>

        <section id="agent">
          <div className="wrap">
            <span className="kicker">Bring your own agent</span>
            <h2>Qualto attests claims, not agents.</h2>
            <div className="agent-grid">
              <div className="agent-copy">
                <p className="big">Skills make agents <b>willing</b>. The MCP server makes them <i>unable</i>. Qualto ships both.</p>
                <p>The claim is a strict JSON contract. Draft it with the bundled loop, another LLM, or a text editor. Whoever writes the claim, Binance is the judge.</p>
                <p>Qualto runs as a <b>standalone MCP server</b>: any MCP-compatible agent client connects and gets exactly five tools — session status, live context, claim attestation, orphan cleanup, receipt verification. No raw order placement. Live writes stay behind a confirmation flag, off by default.</p>
              </div>
              <div className="skill-box term">
                <div className="term-head">
                  <span className="term-dot"></span><span className="term-dot"></span><span className="term-dot"></span>
                  <span className="term-title">install the skill · or the MCP server</span>
                </div>
                <pre>{`# Agent skill (Claude Code, Qwen Code)
cp -r qualto/skills/qualto-trading ~/.claude/skills/

# MCP server (any MCP-compatible client)
pip install -e ".[mcp]"
qualto-mcp   # five tools, live writes off by default`}</pre>
              </div>
            </div>
          </div>
        </section>

        <section id="platform">
          <div className="wrap">
            <span className="kicker">Why Agent OS needs this</span>
            <h2>One convention makes every agent auditable.</h2>
            <ul className="platform-list">
              <li><span className="n">01</span><span>Agent OS puts agents on real money. &quot;Users are responsible&quot; pushes the trust burden onto users and support.</span></li>
              <li><span className="n">02</span><span>An agent that narrates a fake fill destroys Agent OS trust. The damage lands on the platform, not the model vendor.</span></li>
              <li><span className="n">03</span><span>The proof rail already exists: Binance order records, client order ID included, readable over MCP. Nobody had turned it into an enforcement mechanism.</span></li>
              <li><span className="n">04</span><span>Qualto binds claims to that rail before placement and locks the session when the exchange cannot prove the claim. Zero new Binance infrastructure.</span></li>
            </ul>
            <div className="platform-ask">
              <div className="t">The ask</div>
              <p>Reserve the client-order-ID namespace for agent claims, or surface attestation natively in the Agent OS console. <b>Then every agent on the platform becomes auditable by default.</b></p>
            </div>
          </div>
        </section>

        <section className="final" id="start">
          <div className="final-bg" aria-hidden="true"></div>
          <div className="wrap">
            <span className="kicker">Start</span>
            <h2>No fill, no claim.</h2>
            <p className="lede">Clone the repo, run the suite, and place your first claim-bound order on your own Binance Agentic sub-account.</p>
            <Reveal delay={0.1}><div className="cta-cards">
              <a className="cta-card" href={REPO}>
                <div className="t">GitHub repository <span className="arrow">→</span></div>
                <div className="d">Source, receipts, tests, CI, and the agent skill.</div>
              </a>
              <a className="cta-card" href={`${REPO}#run-locally`}>
                <div className="t">Run locally <span className="arrow">→</span></div>
                <div className="d">Python 3.11+, zero dependencies, 5,637 tests in 7.4 seconds.</div>
              </a>
              <a className="cta-card" href={`${REPO}#verify-the-proof`}>
                <div className="t">Verify the proof <span className="arrow">→</span></div>
                <div className="d">Real order IDs, real receipts, re-checkable against Binance.</div>
              </a>
            </div></Reveal>
          </div>
        </section>
      </main>

      <footer>
        <div className="wrap">
          <div className="foot-top">
            <a className="brand" href="/" aria-label="Qualto">
              <Logo size={22} />
              QUALTO
            </a>
            <span className="foot-tag">Claim-bound orders on Binance Agent OS.</span>
            <div className="foot-links">
              <Link href="/docs">Docs</Link>
              <a href={REPO}>GitHub</a>
            </div>
          </div>
          <div className="foot-bottom">
            <span>Claim-bound orders on Binance Agent OS</span>
            <div className="topics">
              <span className="topic">binance</span><span className="topic">agent-os</span><span className="topic">mcp</span><span className="topic">ai-agents</span><span className="topic">attestation</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
