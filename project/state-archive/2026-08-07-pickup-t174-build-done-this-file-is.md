<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### ⭐ (was) PICK UP HERE — 2026-08-07 — **T174 BUILD DONE: this file is now BOUNDED. 339,508 B → 48,268 B, and the combi -->

### ⭐ (was) PICK UP HERE — 2026-08-07 — **T174 BUILD DONE: this file is now BOUNDED. 339,508 B → 48,268 B, and the combined cost of BOTH memory surfaces fell 102,387 → 19,636 tok (−80.8%) — because the triage promoted NOTHING into the always-on one. Next gate: `w0m-sdlc-review` on T174.**

> **Written for an agent with none of my context. Measured live 2026-08-07.**
>
> ### 📍 STATE — `wom7web` + `wom7skills` carry this work; `wom7mlx` is **another agent's** (10 dirty / no upstream — not yours)
> All six gates green: `state-check` · `state-doctor-test` (**28 checks**) · `sdlc-doctor` ·
> `discovery --enforce` · `skill check` (0 unmanaged) · `docs-check`.
>
> ### 🔑 What changed, and the one sentence that matters
> **`STATE.md` — the file you are reading — was 4,140 lines / ~98k tokens, 93.9% of it dated
> history.** It is now **449 lines**, budgeted at **900 lines / 80 KiB** in
> `.w0m/sdlc.json → state_surface.retention` and gated at pre-push. 56 superseded sections moved
> **verbatim** (proven: each archive body matched as an exact substring of the pre-change file,
> 56/56) into `project/state-archive/`, indexed by the 🗄️ table at the bottom of this file.
>
> 🔑 **Do not read that archive to orient.** The index exists so you can see history *exists*.
> Open **one** file, on purpose, when you need to know *why* a past decision was taken — and say
> which and why. `§0t`-style references still resolve: ids survive in the archive filenames and in
> `project/state-archive/DISPOSITION.md`.
>
> ### 🔴 The finding worth carrying, if you carry only one
> **The saving is real rather than *relocated* only because `MEMORY.md` did not move.**
> Auto-memory loads on **every** session (~4,399 tok, unconditional); this file is read **once**,
> and only when an agent chooses to. Draining history into auto-memory would have cut `STATE.md`
> just as hard while making the estate pay forever. The triage promoted **zero** sections there —
> every durable fact was already homed or better placed in the live §4. **A halved cost that moved
> somewhere permanent is not a saving, and only measuring both surfaces can tell you which you did.**
>
> ### ⚠️ Three traps this session recorded
> 1. **A gate that only speaks when it blocks you is one you learn to resent.** The budget was
>    invisible until it rejected a push. `state-check` now prints usage on **every** pass
>    (`ℹ STATE.md 450/900 lines (50%) · 48,268/81,920 bytes (59%)`) and warns at ≥80%.
> 2. **The measurement tool commits the defect it hunts** — again. `tasks.md` §0.4 greps for
>    `### 0`/`0y` to prove nothing parses section ids. It now returns **6, all `state_doctor.py`**,
>    because this change added the estate's only id-parser *by design*. Outside that tool it is
>    still 0. The claim holds; the probe went self-fulfilling and has been re-scoped.
> 3. **Use the governed `openspec` (1.6.0, `pnpm exec openspec`), not `npx …@latest`.** 1.8.0
>    reports **58/5** where the pinned one reports **63/0** — five *unrelated* changes. Flagged for
>    separate triage; do not read it as a regression from T174.
>
> ### ▶️ What to do next
> - **T174 → `w0m-sdlc-review`.** Build gate is closed (38/38 tasks, 9/9 ACs, **zero blank evidence
>   slots**); review/security/verify have **not** run. Nine ticked ACs are not the gates that follow.
> - **[[T175]] exists because of this work** and is the reason AC2's hard-failure rule earned its
>   keep: archiving a gotcha block surfaced the only standing record of a **live security gap**
>   (`get-admin-metrics` compares a service key with `!==`; `_shared/auth.ts` already exports
>   `constantTimeEqual`). Noted twice, owned by nobody, nearly buried. ⚠️ Its AC5 needs the owner —
>   `deploy*` is denied to the agent (T161 AC3).
> - **D36 filed** — auto-memory is a third, and worse, occupant of the [[D32]]/[[D15]]
>   unversioned-location class: per-**user**, not per-workspace, so two machines can hold different
>   estate knowledge with nothing able to detect it.
> - **When you write the next ⭐ block, run `just state-rotate`** — writing one is what kills the
>   previous one. It is idempotent and it will tell you if the candidate set was empty.
