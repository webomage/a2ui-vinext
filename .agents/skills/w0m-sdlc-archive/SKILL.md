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
  version: "2026.09.24-1790250554"
---

# w0m-sdlc-archive — the close + lessons gate

Close the loop so the work is durable and the next task starts smarter. A ticket isn't done until
every truth surface agrees and the lessons are captured.

## Step 0 — Load config
Read `.w0m/sdlc.json`. Use `tickets` (board/dir/sync), `specs`, `tech_debt`, `vcs`, `conventions`.

## Steps
1. **Confirm done-ness.** Every acceptance criterion ✅ with evidence (from the verify gate) and
   the change is live (from the deploy gate). If not, stop — it's not archivable.
2. **Flip surfaces to done, together.** Update ticket frontmatter `status: done` in
   `{tickets.dir}/{pattern}`. Do not edit `TASKS.md` — `just land` regenerates it deterministically
   from `.tasks/` (T425), and — if github-mirrored — close the GH issue
   (re-run `tickets.sync`; ticket markdown is the source).
3. **Archive the spec.** If `specs.system:"openspec"`, invoke `openspec-archive-change` to move the
   change into the archive and sync deltas into the main specs. (`specs.system:"none"` → skip.)
4. **Refresh tech-debt.** Update `{tech_debt.register}` (TECH-DEBT.md): add rows for debt this change introduced, DELETE rows it paid down (git history is the audit trail). Anything introduced/paid-down should be reflected
   in `{tech_debt.register}`; DELETE rows this ticket resolved (git history is the record).
5. **Capture lessons — into the RIGHT register, and `LESSONS.md` is the one this step kept
   missing.** 🔴 Corrected 2026-08-18 (T229): this list named `MEMORY.md`/`CLAUDE.md` and **not
   `LESSONS.md`**, while the `w0m-lessons` skill it folds in says the target is the repo-root
   **`LESSONS.md`**. Two instructions for one register, and *this* list is what an agent reads at
   close time — so the lessons went everywhere except the register built for them.
   **One fact, one home:**
   - **`LESSONS.md`** (repo root) — the durable **RULE** that changes how the next ticket is
     written. Theme sections, not chronology; the format is in `w0m-lessons`. ⚠️ It earns its place
     by being **earned**: a gate caught something, or a fix was wrong twice. Not a bug log.
   - **ticket `## Status notes`** — the **per-incident** record: what happened, in this ticket.
   - **auto-memory** (`MEMORY.md` + one file per fact) — what a **future session** needs to know
     *before* it opens any file. Correct any existing memory this work falsified.
   - **`CLAUDE.md`/`AGENTS.md`** — only for a rule that must reach an agent on every single task.
6. **Refresh the handoff surface.** Closing a ticket changes the
   very facts STATE.md records — the hot list, the SDLC ranking, open/measurable counts.
   `just land` regenerates the **mechanical** block deterministically (T425). Update
   editorial sections (pickup block, gotchas) only when needed.
7. **Final commit.** Commit the tracking/spec/debt updates together, id referenced
   (`chore(T37): archive — done`), per `conventions`.

## Conventions
From config `conventions`: conventional commits w/ id, never skip hooks, no coauthor trailer, tool
ladder. Convert relative dates to absolute. Don't hard-delete anything — archive.

## Next gate
End of the lifecycle. Point the developer back to `w0m-sdlc-start` for the next ticket (or the
`w0m` orchestrator).
