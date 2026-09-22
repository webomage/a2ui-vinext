<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0g. 🆕 FILED 2026-07-25 — T132: `w0m-pixel-clone` (lightweight pixel-perfect parse & copy) -->

### 0g. 🆕 FILED 2026-07-25 — T132: `w0m-pixel-clone` (lightweight pixel-perfect parse & copy)

`project/tickets/T132.md` (P2, queued, no GH issue yet — ticket-sync runs on push). Owner ask: find
the skills that do lightweight pixel-perfect parsing/copying (visual source → faithful UI in code) and
**build a combined, enhanced w0m skill**. A research subagent surveyed installed + upstream skills; the
**full findings are in the ticket** (do not re-derive). Bottom line: **no installed or upstream skill
covers the whole pipeline for w0m's Svelte/Astro stack** — Figma skills build *into* Figma;
`corlab-tech@pixel-perfect-ui`/`onewave-ai@screenshot-to-code` are React; `firecrawl@…design-clone`
needs a hosted service; `webapp-testing`/`playwright-best-practices` capture+verify but don't emit.
**Proposal:** an orchestrator skill reusing w0m's existing capture/verify tooling (Playwright via
`webapp-testing` + Chrome MCP + browser preview + playwright visual-regression) that adds the two
missing pieces — **computed-style → `@webomage/ui` token extraction** and a **Svelte/Astro emitter with
a closed visual-diff refinement loop**. "Lightweight" = DOM + `getComputedStyle` + screenshot-diff, no
hosted scraper, no image-gen model. 7 ACs + a legal/ToS guardrail; 6 owner questions to resolve at
start. Lands under [[T127]] management. Build not started. GH #92.
