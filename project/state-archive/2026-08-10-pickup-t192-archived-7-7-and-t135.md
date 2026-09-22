<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### ⭐ (was) PICK UP HERE — 2026-08-10 — **[[T192]] ARCHIVED (7/7) and [[T135]] ARCHIVED (12/12) — the transitive depende -->

### ⭐ (was) PICK UP HERE — 2026-08-10 — **[[T192]] ARCHIVED (7/7) and [[T135]] ARCHIVED (12/12) — the transitive dependency-licence gate is live at pre-push. [[T193]] filed: CODEMAP.md maps a repo that no longer exists.**

> **Written for an agent with none of my context. Everything below is measured, 2026-08-10.**
>
> ### ✅ A. What shipped and is PUSHED
> **[[T192]] is DONE and ARCHIVED** (2026-08-10). `just ide-trace` → **14/14 declared surfaces at
> parity**, 27 → 11 findings, **nothing red in the 7 w0m repos**; `just ide-trace-test` → 13/13;
> issue #189 closed; ticket + board + GH agree. 🔑 **Its three deferrals carry rows — D43**
> (wom7ext's 9 GitHub Spec Kit workflows are ORPHANED: they reference a `.specify/` that does
> not exist — owner call, removal recommended), **D44** (wire `ide-trace --enforce` after the
> client declarations land), **D45** (`ide_surfaces` → `client-profile.json`, under T182 AC2).
> Closing a ticket is when a deferred finding evaporates; these did not.
>
> **[[T135]] is now 12/12** — AC6's transitive/copyleft half was the last one. 🔴 **Its policy
> pointed at a key that never existed:** `hygiene-policy.json` said the audit *"reads
> `deps-policy.json → licenses`"* and that key was absent — a pointer reading as coverage, the
> same shape T192 found in a `$schema`. Built `just dep-licenses-check` (1,173 prod packages,
> 0 fail / 3 review all exempted / 1,170 advisory) + 20 red probes. ⚠️ **Two gate-design facts
> worth carrying:** (a) the gate found a defect in ITSELF on its first run — an unanchored
> `GPL-3.0` pattern matched inside `LGPL-3.0-or-later`; it is now a mutation-tested regression
> probe; (b) **`license-check`'s promotion trigger had fired long ago and nobody re-read it** —
> its entry still said *"NOT YET GREEN — 234 findings"* while it exited 0. A promotion trigger
> nobody re-reads is a gate that stays `manual` forever. Both licence gates are now wired in
> `.husky/pre-push`; `hooks-check` says 21 declared / 21 wired.
>
> **Next up:** [[T182]] — 5/8, and it owns 8 of the 11 remaining `ide-trace` findings (the four
> clients declaring no IDEs) plus D45. [[T110]] is 4/5. [[T193]] is filed and unstarted.
> ✅ **T135 went through the FULL lifecycle this session** — review → security → verify →
> archive. 🔴 **The review gate caught a FAIL-OPEN the 20 AC7 probes had missed:** `_tier`
> searched the whole SPDX string for `OR` and elected the most permissive branch, so
> `(MIT OR Apache-2.0) AND GPL-3.0-only` came back *advisory* — the licence gate waving through
> exactly what it exists to block. **Every probe used a FLAT expression.** ⇒ A probe set that
> only exercises the simple shape certifies the simple shape. Security gate filed **D46**
> (wom7ext/wom7skills carry no `packageManager` pin, and this gate now runs pnpm in 5
> workspaces on every push). The archive found **18 of 19 'incomplete' tasks were done** —
> `tasks.md`, the surface this ticket designated the authority on what landed, had fallen
> behind the work.
>
> 🚢 **UNDEPLOYED APP WORK EXISTS, and it is not this session's.** Live is
> `2026.08.01-1785595598` / `13110ecf` (2026-08-01). Since then beta has **274 commits**, of
> which **25 files** touch `apps/web` + `apps/cp` — from [[T131]] (release-versioning stamper),
> [[T165]] (canonical CV source + schema gate), [[T168]] (retired Upwork collections) and
> [[T156]] (worker dispatch fix). ⛔ `just deploy*` is DENIED to the agent ([[T161]] AC3), so
> this is an OWNER action: `cd wom7api && just deploy-all`. Those tickets' own deploy gates
> have not been run — verify each before shipping rather than treating the diff as one change.
>
> ### 🔴 A0. Two corrections I made to my own work — read these before trusting the tables below
> 1. **I widened the openspec marker on a FILENAME.** Seeing wom7mlx's `.cursor/rules/openspec.md`
>    reported as a lookalike, I added an `openspec*` glob and wrote *"the earlier openspec layout"*
>    into the policy, the ticket, this file and a commit message. **They are hand-written** — a
>    feature commit, a `specs/meta/` layout, **no `openspec/` directory in that repo**, and no code
>    in the installed CLI emits a `rules/openspec.md`. That is this ticket's own trap, at the
>    fourth time of asking, committed by the gate built to catch it. Marker is `opsx*`, nothing else.
> 2. **`wom7api/.agent` and `wom7api/.claude` are SYMLINKS to wom7web's.** Same inode, set
>    2026-02-12. So the founding claim — *"byte-identical to wom7api's, one repo's rules copied
>    into the other"* — was wrong about its mechanism: **not a copy, a shared directory**, exactly
>    like the shared `justfile`. I found it by writing two "per-repo" files and watching the second
>    overwrite the first. ⇒ **Before "fixing" duplication, check whether it is one file.**
>
> `wom7web` `91f96ca8` · `wom7api` `26c46dd` · `wom7skills` `d3a6afe`. All three verified pushed.
> - **[[T192]] all 7 ACs met.** `.w0m/sdlc.json → ide_surfaces` declares the connected set —
>   a **dict keyed by repo** for the estate's 7, a **list** for a single-root project.
>   **`just ide-trace`** (+`--enforce`/`--json`) reads openspec's **31-tool registry LIVE** from
>   the installed CLI, scans every tool dir across 7 repos + 4 clients, diffs both drift
>   directions, checks rule parity, and lists what loads from `$HOME`. **`just ide-trace-test`**
>   drives parity against the **real, unmodified** `.agent/rules.md` → asserts **0/6**, and
>   `CLAUDE.md` → **6/6**.
> - **[[T192]] AC5 is why you can trust `.agent/` now.** `w0m skill check`'s retired-path warning
>   was what taught the 08-09 agent to delete Artemio's `.agent/`. It now says *"remove
>   `.agent/skills` ONLY … 🔴 Do NOT delete `.agent/` itself"*, and reads the project's
>   declaration to say **"this project DECLARES `antigravity` connected"**. Proven **live**:
>   `openspec update` regenerated `.agent/skills` (10 entries, wom7web + wom7api) and the new
>   warning fired on the real reappearance. Both retired trees removed; `.agent/` intact.
>
> ### 🔴 B. What the trace found — bigger than the ticket that asked for it
> - **Parity is broken estate-wide, not just in Antigravity.** Of **9** declared surfaces,
>   **1 passes**: `wom7web/CLAUDE.md` 6/6. **Every other repo's `CLAUDE.md` scores 1/6 or 2/6.**
>   Both `.agent/rules.md` score **0/6** and still carry the wrong repo's text.
> - **wom7mlx runs three undeclared openspec IDE surfaces** — `.cursor`, `.gemini`, `.windsurf`.
> - **A second spec framework is installed**: `wom7ext/.windsurf/workflows/speckit.*` = **GitHub
>   Spec Kit**, 9 files. ⚠️ Compare the recorded *Gauge is the w0m spec tool* decision.
> - **artemio** — a hand-built Gemini command set (`.gemini/commands/*.toml`) in a **client** repo,
>   and its Antigravity contract is the **empty set** (`.agent/workflows/` exists, no `rules.md`).
> - **8 global surfaces load into every session.** 🔴 `~/.gemini/GEMINI.md` (2,238 B) carries w0m
>   SDLC policy — `--no-verify`, the `w0m-sdlc-*` gate sequence — **machine-wide**, which is
>   exactly what [[T151]] AC9 decided the global `CLAUDE.md` must never do, done for a different
>   IDE where nobody was looking.
>
> ### ⏭️ C. Next, in priority order
> 1. **[[T192]] parity remediation** — the build is done, the content job is not. 8 of 9 surfaces
>    fail; that is 6 repos' `CLAUDE.md` plus rewriting two `.agent/rules.md` that describe the
>    wrong repo and point at the deleted `.env`. **Wire `just ide-trace` into pre-push only after
>    that** — it is red on ~25 real findings today, and a gate that blocks every commit on an
>    untriaged backlog gets bypassed in a repo where `--no-verify` is prohibited.
> 2. **Two owner decisions**, recorded in `docs/OPENSPEC-OWNERSHIP.md` — (a) generate `.opencode`
>    and declare it, or drop OpenCode from the owner's chosen three; (b) are wom7mlx's three extra
>    surfaces and wom7ext's Spec Kit workflows intended, or leftovers to remove?
> 3. **[[T103]] Astro 6→7** — unchanged, and **AC4 is still half done and uncommitted**; the
>    detail is in the previous block below. ⛔ AC5 needs deploy, which is DENIED to this agent.
> 4. **[[T193]]** (new, P2) — `docs/CODEMAP.md` says `Generated: 2026-02-16` and its tree is
>    rooted at `src/pages/`. Grepped for all **10** workspace members (`apps/web|cp|demo|job|join`,
>    `packages/ui|lib|logger|crawler|mcp-aws-fundamentals`): **0 hits for every one.** Not a
>    partial map — a map of a previous repo, filed under `docs/` and read as ground truth.
>
> ### ⚠️ D. Gotchas earned today
> - 🔑 **The identity of an IDE surface is its CONTENT, never its directory name — and I got this
>   wrong three times before the gate was right.** T192's own filing called
>   `servicios777/.kilocode` (a node package dir holding `@kilocode/plugin`) and `wom7ext/.agent`
>   (untracked scratch) "IDE surfaces found by scanning", on the name alone. Then the gate's first
>   marker was `opsx*` — the **current** openspec layout only — and it demoted wom7mlx's three
>   **genuinely openspec-managed** surfaces, written in the earlier `openspec*` layout, to
>   dismissable lookalikes. **A too-narrow marker turns real findings into noise**, which is worse
>   than no gate. Four states now: `openspec` / `foreign` / `autoload-only` / `other`.
> - **openspec keeps NO memory of `init --tools`.** Measured: `openspec/config.yaml` contains
>   `schema: spec-driven` and nothing else, in every project that has one. That is *why* the
>   declaration must be the source of truth — there is no other candidate.
> - **`openspec update` decides from the DISK, not from any declaration.** It updated exactly the
>   declared set here and created nothing new (AC7 ✅) — but that means an **undeclared** surface
>   is not merely tolerated by the generator, it is actively **kept fresh** by it. Only
>   `just ide-trace` closes that loop.
> - **`.github` is openspec's skillsDir for Copilot.** Anything scanning tool dirs by name will
>   hit nearly every repo on earth. `wom7ext/.github` and `wom7sec/.github` are empty dirs.
> - **A policy file's `$schema` must resolve.** `project/client-profile.json` records that w0m's
>   and Artemio's `.w0m/sdlc.json` both point at a `sdlc.schema.json` that does not exist, so both
>   have passed every presence check while never being validated. `ide_trace.py` hard-fails on a
>   dangling `$schema` rather than adding a third.
> - **A parallel Antigravity agent is still working in `wom7web`** — `docs/00-MOC-*.md`,
>   `VAULT-INDEX.md`, `ARCHITECTURE.md`, `business_plan.md`, `project/tickets.json` are all
>   modified by it and were deliberately left unstaged. `git add -A` would sweep them up.
