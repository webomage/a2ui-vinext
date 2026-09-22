<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### ⭐ (was) PICK UP HERE — 2026-08-08 — **T96 SHIPPED *and ARCHIVED* (5/5). Six tickets filed T179–T185. 🔴 The archive g -->

### ⭐ (was) PICK UP HERE — 2026-08-08 — **T96 SHIPPED *and ARCHIVED* (5/5). Six tickets filed T179–T185. 🔴 The archive gate found that NO RULE REQUIRES A SPEC — 144 of 180 tickets have none, and every DoD claims otherwise. Owner ordered the full backfill: [[T185]], 1 of 144 done.**

> **Written for an agent with none of my context. Everything below is measured, 2026-08-07/08.**
>
> ### 🆕 LATEST — the archive gate was the most productive thing in the session
> Closing [[T96]] properly surfaced three things that reading it never would have:
> 1. 🔴 **AC5's deferred finding had NO OWNER.** The note said *"it is its own ticket"*; no such
>    ticket existed, and [[T160]] — which built `suites-drift` — is already `done`. **A deferral is
>    the moment a finding is most likely to evaporate.** Filed **D37**.
> 2. 🔴 **No rule anywhere states WHEN a ticket needs a spec** — absent from `.w0m/sdlc.json`, from
>    `SPEC-AUTHORING-STANDARD.md` (a how-to-*write* guide) and from the `w0m-sdlc-spec` skill —
>    while the ticket **template** asserts *"spec verified"* in **every** DoD. ⇒ **144 of 180
>    tickets carry a criterion they have never met; 37 were archived anyway.** Filed **D38**.
> 3. 🧹 **D25 was false and is deleted** — `commands.test` now runs `run_suites.py --tier offline`;
>    [[T160]] paid it, verified before removal.
>
> ### ▶️ [[T185]] — the owner chose the FULL backfill, 1 of 144 done
> Owner was shown the scale (*144, of which 37 are `done`*) and chose all of it anyway — **that
> decision is recorded so it is not re-litigated, and so 143-remaining is never read as slippage.**
> 🔑 **Do AC1 (the rule) EARLY, not last** — without it the backlog grows from the front while being
> drained from the back. ⚠️ **Refuse bulk generation:** a retroactive spec *records* a contract and
> did not govern one, so each proposal states its real provenance dates and no scenario may restate
> its AC. Pattern to copy: `openspec/changes/archive/2026-08-08-2026-08-08-audit-sweep-coverage-honesty`
> (T96's — 5 requirements / 11 scenarios, validates strict, and its first paragraph admits it is
> retroactive).
>
> ### 📍 STATE — 8 of 9 repos clean, 0 ahead. One deliberate exception.
> `wom7mlx/mlx-rs` is **10 dirty on purpose** — the vendored fork mid-surgery that [[T135]] AC2a and
> [[T184]] both cite as evidence. **Committing it would invalidate two tickets.** Do not tidy it.
> `wom7mlx/wom7mlx` was committed WIP (`2f0675f`) and now tracks `origin/beta`.
>
> ### 🔨 The one thing actually BUILT — [[T96]], 5/5 ACs
> `just audit` gained its missing 4th family and stopped lying about coverage.
> 🔑 **AC3 was the real defect and it was worse than the record said.** A `SKIP` level already
> existed and fired at 7 sites — but was **counted then DROPPED from both summary lines**. With
> `openspec` or `infisical` off PATH, 4+ checks skipped and the audit still printed
> **`✅ 0 fail · 0 warn`**. Now `NOT RUN` appears in the terminal, the report headline and an
> explicit list. **Proven RED** by removing `openspec` from PATH. Exit code deliberately unchanged —
> `FAIL` still gates and pre-push depends on it.
> New family `check_knowledge()` composes the existing `graph_health.py`; on first run it found
> **4 repos behind HEAD** and `wom7md` outside the union.
> ⚠️ `just audit` still exits 1 on a **pre-existing** `[exposure] sharingd:8770` FAIL (a macOS
> system service) — verified identical against the pre-change script. Not from this build.
>
> ### 🔑 The lesson this session earned four times over
> **A term-grep proves the absence of terms, not the absence of the subject — and an audit of an
> audit needs the same scepticism as the thing it audits.**
> (a) grepping `devpod|tart|multipass` read as greenfield; the live decision is filed as *"sandbox
> substrate"* in [[T153]]/[[T171]]. (b) grepping `design_system` missed **[[T93]]**, which owns DS
> adherence enforcement. (c) counting the string `JSX` produced a **wrong** claim that the DS lint
> config was React-only. (d) **three of five** findings in T96's own 2026-08-07 AC-truth pass were
> wrong — each *looked in the wrong place*: `docs/reports/` vs `docs/audit_and_research/`;
> `not_run`/`skipped` vs a `SKIP` constant; `tier` vs `--quick`.
> 🔴 **Direction matters:** those corrections made two ACs smaller and one BIGGER. **A missing
> feature is visible; a discarded one is not.**
>
> ### 🧭 Next, in order
> 1. **[[T180]] AC1 / [[T153]] / [[T171]]** — the sandbox substrate must be decided **once**. Three
>    tickets now share one Tart substrate with different requirements ([[T179]] devcontainers ·
>    [[T180]] sandbox · [[T181]] GUI workstation). ⚠️ **[[T179]] also overlaps [[T65]]** (Gitpod).
> 2. **[[T182]]** — the client import path. 🔴 [[T177]] recurred *because* this path does not exist.
> 3. **[[T183]]** is ⏸️ **PAUSED** — resume with **Artemio**, and settle **Tailwind vs CSS-var
>    tokens first**; it blocks the `tokens` field design.
> 4. **[[T110]]** is 4/5 and blocked by **permission, not effort** — AC5 needs the generic set
>    installed into a real client repo (1945 or Artemio), both owner-write-only.
>
> ### 🔴 Owner-only actions
> 1. **`softnet` sudoers entry** ([[T180]] AC3a) — until then every egress claim in T180 is a
>    `--help` reading, not a control.
> 2. **Does the DS hold cover [[T42]] and [[T93]]?** [[T183]] is paused; those two were deliberately
>    left alone because nobody said to pause them. ([[T42]] was demoted to P2.)
> 3. **Approve a client-repo write** to unblock [[T110]] AC5.
>
> ### ⚠️ Perishable — the DevPod Tart provider is in a SESSION SCRATCHPAD
> `tart` is registered in `~/.devpod` and shows in the DevPod app (initialized via
> `devpod provider set-options`, which does **not** steal multipass's default), but its
> `provider.yaml` exists **only** under a session scratchpad. `just ticket-paths T179` reports it
> **MISSING in every repo**. 🔑 The registration surviving is what makes this easy to miss.
> That is [[T179]] AC6 — version it or lose it.
>
> ### 🟢 Hardware facts worth not re-deriving
> `tart run --nested` → *"Nested virtualization is available for Mac with the M3 chip, and later."*
> This host is an **M1 Max**; confirmed inside a booted macOS guest: **`kern.hv_support = 0`**
> (host = 1), kernel `RELEASE_ARM64_VMAPPLE`. ⇒ no Tart guest here runs Docker/colima/podman.
> 🟢 **A CoW clone of a 50 GB macOS VM cost 0 MB in 0.05 s** — clean-slate-per-run is free.
> 💾 **~30 GB free** on a 926 GB volume that began the session at 94% full; `~/.tart/cache` holds
> **~31 GB** reclaimable via `tart prune` (cost: a re-pull). `macos-test` is stopped.
