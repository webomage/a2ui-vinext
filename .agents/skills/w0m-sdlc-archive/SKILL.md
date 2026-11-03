---
name: w0m-sdlc-archive
description: >
  Close/lessons gate of the w0m SDLC lifecycle (start→spec→build→review→security→verify→deploy→
  archive). Trigger after w0m-sdlc-deploy, or "close out T37", "archive this change". Marks the
  ticket done across all tracking surfaces, archives the spec, refreshes tech-debt, and captures
  lessons so the ecosystem learns. Project-agnostic via `.w0m/sdlc.json`.
metadata:
  author: w0m
  namespace: w0m-sdlc
  gate: archive
  version: "2026.11.02-1793667351"
---

# w0m-sdlc-archive — the close + lessons gate

Close the loop so the work is durable and the next task starts smarter. A ticket isn't done until
every truth surface agrees and the lessons are captured.

## Step 0 — Load config
Read `.w0m/sdlc.json`. Use `tickets` (board/dir/sync), `specs`, `tech_debt`, `lessons` / `lessons_surface` (`lessons.path` or `lessons_surface.file`, defaulting to `LESSONS.md`), `session_wrapup`, `vcs`, `conventions`.

## Steps
1. **Confirm done-ness, zero unused/unwired parts, and drift/audit observability.** Every acceptance criterion ✅ with evidence (from the verify gate), zero unused or unwired surfaces remain (no uncreated DB columns/views, no dead UI toggles, no synthetic `200 OK` placeholder fallbacks masking missing rows, no orphan exports or dead config keys), mutable security/privacy/commercial settings emit append-only `*_audit_log` records via database triggers, and code-to-schema drift gates pass (`supabase_surface_drift_check.py` where configured). If `commands.deploy` is human-gated (`docs/DEPLOY-CONFIRM.md`), agents complete full `w0m-sdlc-archive` + Session Wrap-Up **before** handing `just deploy-all` / `just db-migrate` to the human operator so `origin/beta` is 100% archived and deploy-ready.
2. **Flip surfaces to done, together.** Update ticket frontmatter `status: done` and `queue: done` in
   `{tickets.dir}/{pattern}`. Do not edit `TASKS.md` — `just land` / `just state-save` regenerates it deterministically
   from `.tasks/` (T425), and — if github-mirrored — close the GH issue
   (re-run `tickets.sync`; ticket markdown is the source).
3. **Archive the spec.** If `specs.system:"openspec"`, invoke `openspec-archive-change` to move the
   change into the archive and sync deltas into the main specs. (`specs.system:"none"` → skip.)
4. **Refresh tech-debt.** Update `{tech_debt.register}` (estate-root `TECH-DEBT.md`): add rows for debt this change introduced (using the explicit `Tracked` grammar: `owner: [[T##]]`, `found-at: [[T##]]`, `accepted: [[T##]]`, or `— (needs a T-row)`), and move any `D##` rows this ticket paid down from the open tables into `## Closed-Debt Ledger` with resolution evidence. Run `just debt-check --enforce` to verify zero stale `owner:` links or open paid rows remain.
5. **Harvest friction & capture lessons — into the RIGHT register (`{lessons.path}` / `LESSONS.md`), governed by the 4-Home Knowledge Split (T178 AC3–AC5, T613).**
   Run `just lessons-harvest` (when configured in `session_wrapup`) to inspect repeated path/CLI/gate friction from the session, then resolve the target register from `.w0m/sdlc.json -> lessons.path` (or `lessons_surface.file`, defaulting to repo-root `LESSONS.md`).
   **One fact, one home (4-Home Knowledge Split):**
   - **`LESSONS.md`** (`{lessons.path}`) — the durable, transferable **RULE** that changes how the next ticket is
     written. Theme sections, not chronology; the format is in `w0m-lessons`. ⚠️ It earns its place
     by being **earned**: a gate caught something, or a fix was wrong twice. Not a bug log.
   - **ticket `## Status` notes (`.tasks/T##.md`)** — the **per-incident** record: what happened and what was verified in this ticket.
   - **auto-memory** (`MEMORY.md` + one file per fact) — what a **future session** needs to know
     *before* it opens any file. Correct any existing memory this work falsified.
   - **`CLAUDE.md`/`AGENTS.md`** — only for a standing rule that must reach an agent on every single task.
   - **Advisory prompt/report over mandatory filler & explicit ticket lesson disposition (T178 AC4, T613):** Not every ticket produces a transferable lesson, so at archive time explicitly record either `Lesson captured in LESSONS.md: <heading>` or `Lessons: none (routine delivery)` in `.tasks/T##.md` `## Status notes` and run `lessons_check.py`. Never claim `"captured lesson in LESSONS.md"` in `.tasks/T##.md` unless a corresponding entry was actually written to `{lessons.path}` (`LESSONS.md`) — `lessons_check.py` fails on unbacked claims.
   - **Non-backfill decision (T178 AC5):** Do not retroactively backfill closed historical tickets (`T1`–`T176`+) into `LESSONS.md`; their evidence lives in `.tasks/T##.md`.
6. **Land all session reports & artifacts repo-first (`.agents/reports/`, T613).**
   Verify every architectural report, audit, plan, or Mermaid diagram generated during the session (including IDE brain artifacts) is written repo-first to `.agents/reports/` (and mirrored to `session_wrapup.reports_mirror_dir` such as `w0m-web/docs/reports/` when configured), cites `T##` (`just reports-ticket-check`), and passes headless Mermaid validation (`just mmd-validate`). Never leave deliverables stranded exclusively in external IDE scratch/brain directories.
7. **Refresh the handoff surface (`STATE.md` & `TASKS.md`).** Closing a ticket changes the
   very facts STATE.md records — the hot list, the SDLC ranking, open/measurable counts.
   Run `just state-save` (or `just land`) to regenerate `TASKS.md` and the **mechanical** block of `STATE.md` deterministically (T425), updating permanent editorial sections (gotchas, owner actions) only when needed, and verify `just state-check` exits `0`.
8. **Final commit & atomic session wrap-up (`agent-tree-land`, T613).** Commit the tracking/spec/debt/lesson/report updates together, id referenced (`chore(T37): archive — done`), per `conventions`. When working in an isolated agent tree (`just agent-tree <name>`), run `just agent-tree-land --dry-run` then `just agent-tree-land`, fast-forward the live checkout (`git merge --ff-only origin/beta`), remove the fully pushed agent tree (`just agent-tree-remove <name>`), and run `just state-check` last so zero orphaned worktrees or uncommitted wrap-up state remain.

## Conventions
From config `conventions`: conventional commits w/ id, never skip hooks, no coauthor trailer, tool
ladder. Convert relative dates to absolute. Don't hard-delete anything — archive.

## Next gate
End of the lifecycle. Point the developer back to `w0m-sdlc-start` for the next ticket (or the
`w0m` orchestrator).
