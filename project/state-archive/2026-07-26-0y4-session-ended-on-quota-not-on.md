<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0y4. superseded pickup block — 2026-07-26 (EARLY HOURS) — **Session ended on QUOTA, not on a problem. All 3 tracking -->

### 0y4. superseded pickup block — 2026-07-26 (EARLY HOURS) — **Session ended on QUOTA, not on a problem. All 3 tracking fixes APPLIED. T135's spec is WRITTEN and strict-valid. Next action: `w0m-sdlc-build` for T135, starting at its `tasks.md` §0 preflight.** ✅ **§0 IS NOW DONE — see the ⭐ block above.**

> **Handoff state, verified at write time** (`git status` + `git log @{u}..` per repo):
>
> | Repo | branch | dirty | unpushed | HEAD |
> |---|---|---|---|---|
> | `wom7web` | `beta` | **0** | **0** | `5c9c2a01` (+ the commit carrying this file) |
> | `wom7api` | `beta` | **0** | **0** | `18f09c4` |
> | `wom7cfworkers` | `beta` | **0** | **0** | `adce18a` |
> | `wom7md` | `beta` | **0** | **0** | `38fbbf7` |
> | `wom7skills` | `beta` | **0** | **0** | `3e968b7` |
> | `wom7ext` | `beta` | **0** | **0** | `b1b0310` |
>
> `git pull` first — a parallel Antigravity agent also commits to `beta`.
>
> **Two trees are dirty and NEITHER is mine** (another agent's in-flight logits-mismatch work):
> `wom7mlx/wom7mlx` **10 dirty** (`beta`) and the vendored `wom7mlx/mlx-rs` **10 dirty** (`main`).
> **Do not touch, do not reformat, do not "fix" them.** They block `cargo check` (T135 AC2a) but
> **not** the `cargo fmt --check` gate that actually ships.
>
> ### ▶ START HERE — in this order
> 1. `git pull` everywhere.
> 2. **`w0m-sdlc-build` for T135.** The spec gate is **done** and the change is strict-valid. Start at
>    **`openspec/changes/2026-07-25-repo-hygiene-gates/tasks.md` § 0 (preflight)** — it exists because
>    three recorded groundings have already turned out wrong, and §0 re-measures them cheaply before
>    anything depends on them.
> 3. **Do NOT re-derive §0w / §0z / §0m / §0n / §0p / §0u.** Each is a real command run. Where one was
>    found wrong this session it is **corrected in place and marked**, not deleted — read the
>    correction, not the struck line.
>
> ### ✅ WHAT LANDED THIS SESSION — 3 commits, all pushed
>
> | Commit | What |
> |---|---|
> | `761cac20` | The 3 tracking fixes (T49 / T32 / T131) **+ filed T140** |
> | `9aaf8e86` | **T135 spec** — `openspec/changes/2026-07-25-repo-hygiene-gates` |
> | `5c9c2a01` | Corrected 2 wrong groundings found *while writing* that spec |
>
> **The three tracking fixes are APPLIED — the fix table in §0z is now struck through.**
> - **T49 → `done`.** Verified live: stamp `20260723101000` present, **0** unpinned definer functions,
>   **32** pinned. AC4 ticked only after actually running the suites (`deno-test` 18/18, `vitest` 1/1).
> - **T32 → P0 ➜ P2, `blocked` ➜ `paused`. Deliberately NOT closed.** 3 of 4 ACs verified satisfied;
>   the remainder (git-history purge) is **[[T17]]'s** scope. AC2 left unticked on purpose — it is the
>   pointer that keeps T17 attached to its origin.
> - **T131 claim corrected** — and **the previous correction was corrected too** (§0z item 2).
>
> **T135 spec gate ✅ DONE.** `openspec validate --all --strict` → **57 passed, 0 failed**.
> **11 requirements** against `sdlc_toolchain` (1 modified, 10 added), with a **bidirectional**
> AC↔requirement trace (12 ACs → 11 reqs, no orphans either way). Three design decisions, recorded in
> the ticket: the registry gains a **`gates`** map (unphased role = schema failure) so AC4's per-stack
> subset is mechanically checkable; **AC7 + AC9 were promoted to first-class requirements** rather than
> checklist items; and `tasks.md` carries **paired red/green evidence slots with blank exit-code
> fields**, so AC7's proof obligation is unskippable at build time.
>
> ### 🆕 T140 FILED (GH #101) — a live breakage found by *running* a test, not by auditing
> **`just test` in `wom7web` was collecting ZERO test files** and dying on `MODULE_NOT_FOUND`. Cause:
> the security floor `floors.undici = ">=7.28.0"` is a **lower bound only**, so pnpm resolved
> **undici 8.7.0** — but `jsdom@29` (vitest's DOM env) needs undici's internal
> `lib/handler/wrap-handler.js`, **removed in 8.x**. A security control had silently disabled the web
> test suite, which was **reporting nothing while running nothing**.
> - ✅ **Immediate fix shipped:** `wom7web` pinned `">=7.28.0 <8"` → resolves **7.29.0**, still above
>   the floor, **no patch level given up**; recorded as `exceptions.undici` so nobody "aligns"
>   `wom7api`/`wom7cfworkers` (fine on 8.x, no jsdom) back to 7. `just test` now **1 passed / 0 failed**.
> - 🔴 **T140 is the generalisable half:** `deps_sync.py`'s `semver()` reads only the **first** `x.y.z`,
>   so it can neither enforce nor propagate an upper bound — and **all 9 floors share the unbounded
>   shape**. ⚠️ Run **`w0m-sdlc-research`** before starting it (filed by hand from direct evidence;
>   confirm it isn't already inside [[T112]]'s scope).
>
> ### 🔴 THREE GROUNDINGS WERE FOUND WRONG THIS SESSION — read the corrections, not the originals
> All three are corrected **in place and marked**, because deleting them would erase the lesson.
>
> | Where | Was | Actually |
> |---|---|---|
> | §0z item 2 | *"0 of 40 skills declare a version — wrong in both directions"* | **11 of 40** declare an *indented* `metadata.version`. So *"16 of 27"* was **right per top-level dir**, and **29 of 40** per the real corpus. `.w0m/skills.json` has **two** fields: `version` = provenance label, `observed_version` = the real one (58/70). Use the denominator-free statement: **zero canonical skills carry a *conforming* version.** |
> | §0n gap 3 | *"`wom7ext` has no lint/format/typecheck at all"* | **False.** `wom7ext/extension/` has 9 devDeps, 7 scripts **incl. `type-check`**, and a `tsconfig.json`. ⇒ **T135 AC3 SHRINKS** to "wire up what exists". |
> | §0u | *"`wom7api` and `wom7ext` are not `private: true`"* | `wom7ext/extension` **does** have it. Gaps are `wom7api` + the **repo-root** `wom7ext/package.json`. And `license` is absent on **all 7** manifests ⇒ **AC11 GROWS** from 4 to 7. |
>
> ⚠️ **The meta-lesson matters more than any of the three.** Two of them are the **same
> wrong-directory-level error** that §0n *already documents* for `wom7mlx` — *"it measured the outer
> `wom7mlx/`, which is not a git repo"* — repeated in the same estate on the same day, **by the pass
> that was citing that very warning**. A written lesson did not prevent its own recurrence. Hence
> `tasks.md` task 0.1 now requires **locating every `package.json`** (excluding `node_modules`) before
> scoping, not merely resolving the git boundary.
> **"No config at this path" is not "no config in this repo."**
> And the §0z case adds the companion rule: **a correction pass is not self-validating** — that one
> over-corrected by silently narrowing "declares a version" to a top-level key, which is the same
> *"my measurement is the truth"* error it was written to fix.
>
> ### 🔴 OWNER ACTIONS OUTSTANDING — still THREE, unchanged this session
> 1. **Revoke the `casualuser` GitHub token** — GitHub → Settings → Applications / PATs. Dropping the
>    DB row did **not** revoke it (ciphertext, no recoverable key ⇒ not validatable or revocable
>    programmatically). Identity `casualuser`, GitHub id `1243074`.
> 2. **T99(d) task 3.1 — provision `CONNECTOR_TOKEN_KEY_V1`.** `openssl rand -base64 32` → Infisical,
>    version `1`, exposed to the edge runtime as Supabase secrets. **Do not let an agent invent key
>    material.**
> 3. **T99(d) task 3.5 — apply migration `20260725180000`.** Deliberately held: it is outward-facing
>    and pointless before 3.1.
>
> ### ❓ OPEN OWNER QUESTIONS (asked, unanswered — do not guess these)
> 1. **T136:** which WordPress sites? (zero WP anywhere in the estate; Hostinger has zero installs —
>    AC1 cannot start)
> 2. **T137:** what does *"register"* mean — signup surface · external marketplace listing · legally
>    registering an entity? AC5 assumes the first two.
> 3. **T137:** first paying customer profile, and whether the full tier is sold before deep mode exists.
>
> ### ⚠️ TWO THINGS T135's BUILD GATE MUST SETTLE (recorded as unresolved, not guessed)
> - **`wom7sec`'s gate-matrix row is UNCONFIRMED, not fact** — it was not present as a working tree
>   when the matrix was measured. `tasks.md` **task 0.3** re-measures it before anything depends on it.
> - **AC10's denominator is wrong.** The "2 of 27 canonical skills mention `infisical`" baseline counts
>   **top-level directories**; the corpus is **40 `SKILL.md` files**. `tasks.md` **task 6.2** requires
>   picking a denominator and writing it down *before* setting a target.
>
> ### 🔥 THE HOT LIST — what changed since the previous ⭐ block
> The validated hot-10 in §0y3 below still stands **except** for these movements:
> - **T135** was #1 and is now **spec-complete** → its next step is `build`, not `spec`.
> - **T49** and **T32** are off the board as open items (closed / re-prioritised).
> - **T140** is new and P1, but **not yet researched** — do not rank it above T135 on freshness alone.
> - **T120** (Safe Browsing, P0) is **still unverifiable from here** and still worth a 5-minute owner
>   check that could close a P0. Nobody has looked since 2026-07-22.
> - **Fileless tickets remain SIX** — T111, T87, T90, T94, T96, T112 — and **T112 still has no board
>   row at all**. Unchanged this session. Still blocks [[T137]]'s AC0.
