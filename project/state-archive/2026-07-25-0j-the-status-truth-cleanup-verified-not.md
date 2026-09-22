<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0j. ✅ DONE 2026-07-25 (later) — the status-truth cleanup. Verified, not assumed. -->

### 0j. ✅ DONE 2026-07-25 (later) — the status-truth cleanup. Verified, not assumed.

Each row was checked against live reality before flipping — the point of the exercise was that the
board had drifted from the truth, so trusting either the board *or* the previous handoff would have
reproduced the bug. **No code changed; docs/tracking only.**

- **T123** → ✅. Its row claimed *"migration written, **not yet applied to prod**"*. **False.** Both
  stamps (`20260723100000` t123_ac3, `20260723101000` t49) are present in
  `supabase_migrations.schema_migrations`, and `has_function_privilege` on the live DB confirms the
  effect: `get_top_clicks` / `get_user_daily_tokens` / `trigger_vectorize_vault` / `hard_delete_user`
  are **not executable by anon *or* authenticated**; `get_provider_quotas` is authenticated-only by
  design (CP admin, guarded in-body); all 5 still `SECURITY DEFINER` with `search_path=""` pinned.
- **T124** → ✅. All 5 ACs were already `[x]`; only the row lagged. Re-verified `git grep eyJ` finds
  **no key literal** repo-wide. AC3's Cloudflare half is partial **by design** (worker secret values
  are write-only), not an omission.
- **T121** → ✅, and it was the *only* one needing real work. Its last open AC (test-file fallbacks)
  had been closed by **T124's** sweep — a ticket closed by another ticket is exactly how a row goes
  stale. AC2/AC3/AC4 verified from the live tree + the standing gates; **AC5 newly verified** under
  `infisical run --env=dev` (all three vars injected; anon key is the live 46-char
  `sb_publishable_…`, not a JWT).
  - 🔎 Its **separate hipeople.io token finding is resolved**: token **expired 2026-07-06**, and the
    content is unrendered — **but the ticket's stated reason was wrong.** It said `content.config.ts`
    reads `src/content` not `src/data`; in fact `apps/{web,cp}/src/lib/vault.ts:29,55` **does**
    eagerly glob `/src/data/upwork_vault/proposals/*.md`. It is harmless only because `lib/vault.ts`
    has **zero importers** — a dead module. Right conclusion, wrong reasoning; don't reuse the
    reasoning. (The dead `lib/vault.ts` is cleanup, overlapping T90 — not filed.)
- **T122 / T126** → already ✅ in both row and frontmatter. The ⭐ caveat listing them was stale.
- **T79** → row corrected. Stale on **both** halves: the OpenSpec change was archived 2026-07-22
  (`archive/2026-07-22-2026-07-18-demo-showcase-and-walkthroughs`, `spec:` already points there), and
  the endpoint **was** security-reviewed — T120's live matrix drove `/api/demo/enter` and found it
  clean (hostile `persona` → error, **no token minted**; smuggled `?next=` dropped).
- 🔴 **One genuinely open item surfaced, and it is UNTICKETED:** **rate-limit/CAPTCHA on
  `/api/demo/enter`** — a public endpoint that mints login tokens, with no throttle. It is recorded
  in `T79.md` notes as an explicit out-of-scope follow-up and never got its own ticket. ⚠️ When
  ticketing it, do **not** copy the existing per-IP quota pattern: T126 found that one keyed off the
  client-controllable `X-Forwarded-For` **and failing open**. Sibling untracked items to consider
  folding in: `get-upwork-status` (ungated read) + `get-admin-metrics` (non-constant-time compare).
- **`TASKS.md` NOW section got a header note** rather than a restructure: 9 of its 11 rows are ✅
  done, only **T120** (blocked) + **T125** (queued) are open. The rows stay in place — their Status
  cells hold live-verification detail the bullet-style DONE section cannot carry — so the note tells
  the reader to trust the Status column over the section heading.
