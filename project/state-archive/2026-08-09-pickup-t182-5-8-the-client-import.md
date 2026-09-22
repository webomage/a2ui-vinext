<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### ⭐ (was) PICK UP HERE — 2026-08-09 — **[[T182]] 5/8 — the client import path EXISTS, is enforceable at a client (8/8  -->

### ⭐ (was) PICK UP HERE — 2026-08-09 — **[[T182]] 5/8 — the client import path EXISTS, is enforceable at a client (8/8 keys), and has been run COLD on a project it was not derived from. 🔴 Read §"what the cold run cost" before you trust a green gate: four defects surfaced only because the third project declared nothing.**

> **Written for an agent with none of my context. Everything below is measured, 2026-08-09.**
>
> ### ✅ What shipped
> - **Six new gates, each with a red-probed proof**: `just client-inventory` (25/25),
>   `client-profile-check` (31/31), `skills-catalogue` (18/18), `state-bounds` (13/13),
>   `client-check` (the one-command runner), plus the **written path** at
>   `docs/CLIENT-IMPORT-PATH.md`.
> - **The `client` profile** — `project/client-profile.json`: **8 required · 2 optional · 14
>   excluded**, every key naming a gate that **provably reads it** *and* **can be pointed at a
>   client**. `.w0m/sdlc.json` gained a **`skills`** key (contract 23 → 24).
> - **All five remaining gates made project-scoped** — `preflight --project`,
>   `sdlc-doctor --project`, `discovery --project`. Enforcement at a client went **2/8 → 8/8**.
> - **Two clients now CONFORM**: **Artemio** (skills refreshed to upstream HEAD, migrated to the
>   two-layer layout, 8/8 keys) and **servicios777** (imported cold, 8/8). Both **pushed**.
>
> ### 🔴 The four defects the cold run cost — read these before trusting a gate
> A project that declares **nothing** is the only subject that finds them:
> 1. **Advisory gates printed `3/6 clean` over a repo with no `.w0m/` at all.** A green tick for a
>    key the project never declared. Gates whose keys are all undeclared now report **`n/a`**.
> 2. **`state-bounds` called an EMPTY set `✓ within`.** "Within" must mean *measured and inside*,
>    never *nothing was measured*.
> 3. **Onboarding broke four test suites at once** — each hardcoded the project set. Corpus
>    assertions now derive from the registry.
> 4. **The drift check caught MY OWN incomplete measurement** — I declared 4 of 6 techs.
>
> ### 🔴 Traps this session paid for, in one line each
> - **A quoted word is not a read.** Grep said `project` was the best-gated key in the contract;
>   every hit was the `project/` **directory path**. It has **no** reader.
> - **A probe that does not fire is not evidence.** `find -newermt '-3 hours'` is *rejected* by this
>   host's `find`; with stderr to `/dev/null` the error printed `0` and `0` read as clean — and
>   reached a commit message before being retracted.
> - **A red probe that stops being red is worse than none.** Scoping `sdlc_doctor.py` silently
>   disarmed the AC2 probe that used it as its "unscoped" example.
> - **Building a gate proves it is enforceable; PASSING it proves it is right.** Three profile
>   flaws surfaced only when trying to satisfy it (`mcp` was unsatisfiable for a project with no
>   MCP servers; a vendored schema could drift; `repos` conflated working-tree hygiene with
>   conformance).
>
> ### ⏭️ Next
> - **AC3 + AC5's 1945 half** — both need **coordination with 1945's parallel actor**, which commits
>   into that repo concurrently. 🔴 Its `STATE.md` hit **411,216 B** (612,963 B across three files)
>   and is still **UNDECLARED**; it grew ~**56 KB in two days** while this session watched.
> - **`personaje0`** — a **fourth** project, partly imported, in no ticket until now. **1 of 8
>   required keys, 7 of 14 excluded ones.** Registered read-only.
> - AC8 (design systems) is [[T183]], **paused by the owner**.
