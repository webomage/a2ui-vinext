---
id: AgDR-0010
title: "Do not adopt Cloudflare Kitesurf — every browser workload here needs the two things it trades away"
timestamp: 2026-08-24T00:20:00-05:00
agent: claude-code
model: claude-opus-5
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket:
---

# AgDR-0010 — Kitesurf is not a fit for any browser workload this estate has

## Y-statement

> In the context of **five distinct browser workloads across `wom7cfworkers`, `wom7web` and
> `wom7ext`**, facing **a free beta browser that explicitly drops pixel-perfect rendering and
> persistent authenticated sessions**, we decided **not to adopt Kitesurf anywhere today**, to
> achieve **measurements and deliverables that stay trustworthy**, accepting **that we keep paying
> full Chromium cost for PDF generation and keep a local browser in the loop for layout gates,
> and that a beta product may narrow these limits later and deserve a re-read**.

## Context

Owner ask 2026-08-23: *"let's actually look if we can add this for our stack effectively —
https://developers.cloudflare.com/browser-run/kitesurf/"*.

**What the page says**, fetched 2026-08-23. Kitesurf is *"Cloudflare's stateless, highly scalable
browser that runs entirely on top of Workers and is designed for AI agents"*. It reaches sufficient
web-standards compliance for agent tasks by removing what only humans need — tabs, themes,
extensions, **pixel-perfect rendering** — and uses far less CPU and memory than Chromium. Surface:
a Quick Actions API (`browser=kitesurf`) for screenshots and HTML extraction, a CDP endpoint at
`wss://api.cloudflare.com/client/v4/accounts/<ID>/browser-run/devtools/browser?browser=kitesurf`
usable from Puppeteer/Playwright, and an MCP client config via `chrome-devtools-mcp`. **Beta, free
behind per-account limits.** Stated limitations: no video, no WebGL, no bot-challenge TLS
fingerprints, **no persistent authenticated sessions**.

**What we actually run**, measured the same day rather than recalled:

| workload | evidence |
|---|---|
| CV / client-document **PDF generation** | `wom7cfworkers/src/workflows/document-generator.ts:92` — `@cloudflare/puppeteer`, `puppeteer.launch(c.env.BROWSER)`, `page.pdf({format:"A4", printBackground:true})`, uploaded to storage. The **only** consumer of the `BROWSER` binding declared in `wom7cfworkers/wrangler.jsonc:48` |
| **layout-matrix** ([[T261]]) | `apps/web/scripts/layout-matrix.mjs` — Playwright; measures computed font sizes, text widths and Range rects across 11 viewport/orientation pairs |
| **visual goldens** | Gauge + section-scoped homepage matrix — screenshot diffing |
| **Upwork automation + e2e** | `wom7ext` — Puppeteer driving a real Chrome **extension**, against logged-in Upwork |
| **agent browsing** | `claude-in-chrome`, declared in `.w0m/sdlc.json → mcp` as *"browser automation for the verify gate (**real logged-in Chrome**)"* |

🔑 **Every one of the five depends on pixel fidelity or on session persistence** — the two things
Kitesurf removes by design. That is not bad luck; it is what this estate uses browsers *for*. We do
not scrape, and the one job Kitesurf targets — headless HTML extraction for agents — we already do
with `WebFetch`, at no cost and with no binding to maintain.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Adopt for **PDF generation** | Free vs metered Chromium; already on Workers; one binding swap | PDF is **not** in the documented surface (screenshots + HTML extraction only); a CV is a client-facing deliverable and *"eliminating pixel-perfect rendering"* is disqualifying for a document | 🔴 rejected |
| Adopt for **layout-matrix** | Would remove a local browser from a gate we want to run anywhere | 🔴 **The sharpest no.** The gate measures text metrics, and [[T261]] exists *because* an H1 silently collapsed to 16px while a lines-based check passed. A renderer that trades pixel fidelity returns numbers that are **plausible and wrong** — the exact failure mode the ticket was built to catch | 🔴 rejected |
| Adopt for **visual goldens** | Same | Screenshot diffing against a non-pixel-perfect renderer measures nothing | 🔴 rejected |
| Adopt for **`wom7ext`** | Would lift Upwork automation off this laptop | Needs extensions, logged-in sessions, and surviving bot challenges — Kitesurf explicitly lacks **all three** | 🔴 rejected |
| Adopt for **agent browsing / research** | Genuinely its use case; MCP-shaped, and this estate is MCP-first | Already served by `WebFetch` at zero cost; the declared browser MCP is `claude-in-chrome`, whose whole point is a *real logged-in* Chrome — the definitional opposite | 🟡 no need today |
| **Adopt nothing, record why** | Keeps every measurement trustworthy; costs nothing; the question stops being re-opened | We keep paying Chromium cost for PDFs and keep a local browser in the layout gate | ✅ **chosen** |

## Decision

**Do not adopt Kitesurf in any workload.** Keep `@cloudflare/puppeteer` on the standard `BROWSER`
binding for PDF generation, keep Playwright local for the layout matrix and goldens, and keep
`claude-in-chrome` as the declared agent-browsing surface.

## Consequences

**Positive.** No measurement in the estate starts depending on a renderer that is documented as not
pixel-perfect — which matters most for the one gate whose entire job is catching a wrong pixel.
Nothing new to configure, no beta dependency in a client-facing deliverable, and no second browser
path to keep in sync. The evaluation itself produced a reusable map of where browsers are used here,
which did not previously exist in one place.

**Negative, stated rather than moved elsewhere.** We keep paying full Chromium cost for every CV and
client-document PDF, and the layout matrix keeps needing a browser on whatever machine runs it —
which is a real constraint on ever running that gate in CI. We also decline a free tier we are
plausibly the target user for, and Kitesurf being **beta** means these limits may narrow: this
record is a snapshot of 2026-08-23 documentation, not a permanent judgement.

⚠️ **One inference, flagged as an inference.** PDF support was judged **absent from the documented
surface**, not tested. CDP `Page.printToPDF` might work over the Kitesurf endpoint even though it is
not advertised. If that matters later, the cheap experiment is pointing `document-generator`'s
`puppeteer.connect` at the Kitesurf CDP URL and diffing one CV PDF against current output — an
afternoon, not a project.

## What this does NOT decide

- **Not a judgement on Kitesurf.** For scraping, agent research or high-volume screenshotting it
  looks well-designed; we do not have those workloads.
- **Not a decision about Browser Run generally.** The `BROWSER` binding stays, and the default
  Chromium path is untouched.
- **Not permanent.** Re-read when Kitesurf leaves beta, or if it ever documents PDF output or
  session persistence. Either would reopen the PDF and `wom7ext` rows above.
- **Nothing about [[T269]]** (`.mcpb`/`.dxt` packaging) or the Cloudflare MCP server at
  `https://mcp.cloudflare.com/mcp` — which is separately declared and configured, and which this
  session could not use because it needs interactive auth.
