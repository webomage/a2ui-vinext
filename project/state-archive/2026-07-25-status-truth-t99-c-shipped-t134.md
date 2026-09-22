<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### Session log — 2026-07-25 (EVENING session — status-truth, T99(c) shipped, T134 filed; all pushed) -->

### Session log — 2026-07-25 (EVENING session — status-truth, T99(c) shipped, T134 filed; all pushed)

Commits — **wom7web**: `5d642d3c` (status-truth pass) · `c32845e1` (T99 start + ticket file
reconstructed) · `04a1a440` (T99 spec) · `026c5cb1` (T134 filed) · `e748614c` (T99 (c) applied).
**wom7api**: `61e6b1b` (T99 (c) drop migration + drizzle cleanup).

- **Status-truth cleanup DONE** (§0j) — T121/T123/T124 flipped to ✅, each verified against live
  reality. T123's row was actively **false** ("migration not yet applied to prod" — both stamps are
  in `schema_migrations`). T122/T126 already read ✅ and T79 was stale on both halves, so the
  previous handoff's caveat was itself partly stale.
- **T99 ticket file RECONSTRUCTED** — it had a board row but **no file** (the [[T109]] gap), so it
  could not enter the SDLC at all.
- **T99 spec written** — `2026-07-25-connector-credential-hardening`, strict-valid, 56/56.
- **T99 (c) BUILT + APPLIED LIVE** (§0k) — 7 orphan tables dropped from production, guard proven,
  D2 cleared.
- **T134 filed** (§0l) and right-sized against T94/T64/T90.
- **Two new owner asks arrived at the end** (§0m Infisical enforcement, §0n per-repo SDLC check
  gaps) — grounding recorded, **neither ticketed**, both unstarted.
- **Two self-corrections worth remembering** (both now in the ticket): auditing T99(a) via
  `pg_policy` shows the unfixed shape and is misleading; and `linkedin-sync.ts` is **not** a token
  consumer, so the token surface is 3 call sites, as the board originally said.
