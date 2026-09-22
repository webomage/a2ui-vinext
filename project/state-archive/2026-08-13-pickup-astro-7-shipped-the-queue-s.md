<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ## ⭐ PICK UP HERE — 2026-08-13 — **Astro 7 shipped; the queue's two structural blind spots are closed; RBAC is down to f -->

## ⭐ PICK UP HERE — 2026-08-13 — **Astro 7 shipped; the queue's two structural blind spots are closed; RBAC is down to four owner decisions.**

> **Written for an agent with none of my context. Every number measured 2026-08-13.**
>
> ### 🔴 A. FOUR OWNER DECISIONS — nothing below them can start
> These are not "nice to confirm". Each is load-bearing for several tickets, and no amount of
> agent work moves them.
>
> 1. **The office VOCABULARY** ([[T117]]) — the *scope* question is NOT open; it was decided in
>    writing 2026-07-16/07-22 (`resource_grants(subject, office|capability, scope_type, scope_id)`
>    + `wom_can_on`, full DDL in `openspec/changes/2026-07-16-rbac-capability-model/tasks.md` 3.2/3.3)
>    and **never built**. What is open is only **Q1 the area names** (`fin·sales·account·delivery·
>    eng·quality·talent·design·growth·gov`, **3 agency-only** ⇒ realms are NOT symmetric) and
>    **Q2 realm-as-prefix vs realm-as-column** — recommendation on file: **column**, because
>    `client.acme.fin` re-introduces the parsed-string failure the scope column removed.
> 2. **Approve (or re-scope) the capability-model change.** Its header says *"DRAFT. No live
>    migration runs until reviewed, refined, and approved"*, and Phase 1 task **1.6 is an owner
>    dashboard activation**. ⚠️ **The chain is FIVE migrations + that activation, not two** — I said
>    two on 2026-08-12 and it was wrong: `wom_can_on` needs `wom_can`, which needs
>    `role_capabilities` + `user_capabilities` + a hook stamping `wom_caps`, **and the live hook
>    does not stamp it**.
> 3. **[[T206]] AC1 — a Supabase DASHBOARD check only you can do.** Per-service Postgres roles need
>    a `role: svc_x` JWT. **No JWT secret exists in infisical and the keys are the NEW opaque format**
>    (`sb_publishable_…`/`sb_secret_…`). If the legacy JWT secret is still retrievable, or a new
>    secret key can bind to a custom role ⇒ **cheap**. If neither ⇒ **rewriting DB access in 53 edge
>    functions**. It gates the estimate, not the design. **Same check unblocks [[T202]] AC1's prod half.**
> 4. **[[T117]] AC5 — which 6 of the live 12 `user_roles` values survive.** ⚠️ **Now a three-part
>    decision:** which six · what happens to the 4 `ai-*` · whether they migrate to `system.*` roles.
>    **[[T117]] AC9 is strictly downstream of it** — its own amendment says reconciling the flow
>    diagrams first *"would make them wrong"*.
>
> ### ✅ B. What shipped 2026-08-13 (all pushed, both trees clean)
> · **Astro 6.4.8 → 7.2.1, all five apps building**, ONE major in the lockfile, **6 osv suppressions
>   deleted** (13→7). Blocker was a **0-byte patch file** pinning `@astrojs/cloudflare`; then
>   `astro-compress` (declares `astro:"*"` as a **dependency**, so it seats its own copy); then
>   wrangler `^4.123.0` **lockstep across 3 repos**; then `@astrojs/markdown-remark@7.2.2`.
> · **[[T173]] 6/6 + closed** — `blocked_by:` is a real frontmatter field, the **sdlc board has a
>   `Blocked by` column**, `just ticket-deps` (+5 offline probes) gates dangling/self/cyclic/**resolved**.
> · **[[T13]] closed** — the `w0m-sdlc-*` pipeline was already delivered; verified by **routing**, not
>   by counting skills.
> · **[[T117]] 4/10** — AC7 (D4) was already closed by [[T198]] AC5 and uncredited; **AC8** →
>   `just schema-drift` (2 ghosts: table `users`, column `ai_personas.metadata`).
> · **[[T202]] 4/7** — AC3 triage (37 importers), AC5 gate (+10 offline probes), AC6 `persistSession`
>   retired. **AC4 WITHDRAWN — the defect did not exist.**
> · **[[T199]] 7/13** — AC1 buckets, AC5 backups dropped, AC6 grant layer, AC12 orphans.
> · **[[T207]] 3/8** — AC1 one-whitelist, AC4 nav coverage, AC7 DS parity.
> · **Queue hygiene: 15 untriaged → 0**, and the "no acceptance criteria at all" class → **0**
>   (T69/T70/T72/T74/T76 written). 21 remain with the template's **honest placeholder** — that is
>   [[T185]]'s job, one at a time via `w0m-sdlc-spec`. ⚠️ **Do NOT bulk-generate ACs to move the
>   number**; a placeholder that admits nothing is there beats an invented criterion.
>
> ### ⚠️ C. The gotcha that recurred SIX times today — read this before trusting any measurement
> **A detector that cannot fire is not evidence of absence.** Six instances, all mine:
> 1. `just authz-remap` silently skipped 2 of its inputs → a **stale** office snapshot read as a live
>    separation-of-duties defect (it had been fixed 2 days earlier).
> 2. A shell sweep with nested quoting returned **"0 callers" for 5 functions**, one of which I had
>    already found a caller for.
> 3. `CHECK_RE` counted `Astro.locals.user` (a *read*) and a 404 `redirect` as authorization →
>    the meaningless **"25 files query before checking"**; the real answer is **0 of 37 authorise
>    anything themselves**.
> 4. A line-by-line scan missed **multi-line** `await supabase\n .from(...)` → all 20 pages read as
>    "no query".
> 5. Matching the bare identifier `DEEP_LINK_ONLY` hit its own **doc comment**, emptied the corpus,
>    and the gate printed ✅ while measuring **zero routes**.
> 6. Searching **one repo of a two-repo estate** → nearly recorded "no Drizzle" when it is in
>    `wom7api`.
> ⇒ **Every gate written today therefore has offline red probes, and several assert an EMPTY CORPUS
>   IS A FAILURE.** When a check is green, confirm it measured something.
>
> ### 🎯 D. Best next pickups (no owner decision needed)
> · **[[T69]]** — 3 live, **silently failing** bugs, all re-verified today: character sheet renders
>   **0 XP/0 balance as if true** (unqualified `gamification` schema), interview transcript panel
>   **permanently empty** (`interview_messages` exists in no schema), **scraped jobs never persist**
>   (`scraped_jobs` in no schema — ⚠️ **`public.aggregated_jobs` DOES exist and may be the intended
>   target; check before creating anything**). AC5 closes the whole class by extending
>   `just schema-drift` to `.from()` call sites.
> · **[[T207]] AC5/AC6** — the token gate. **777 hardcoded hex across 77 distinct values, 552 native
>   controls.** ⚠️ Advisory first — day-one `--enforce` blocks every commit. 🔑 **Measure TOKENS, not
>   imports**: `@webomage/ui` imports **tripled** (7→23) while hex **rose** 119→175 for one colour.
> · **[[T72]]** — 6 ACs now written; ⚠️ **AC5 exists to stop a "consolidation" deleting Gauge** (189
>   `.spec` files locally, 364 estate-wide — Gauge specifies TESTS, OpenSpec specifies CHANGES).
>
> ### 🔧 E. New gates this session (all `just`, all with probes)
> `authz-bucket-check(-test)` · `authz-grant-check(-test)` · `authz-admin-client(-test)` ·
> `cp-nav-check` · `ticket-deps(--test)` · `schema-drift`
>
