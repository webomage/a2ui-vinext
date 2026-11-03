---
name: w0m-state-save
description: >
  Write the session handoff into the active ticket's Status notes (`.tasks/T{id}.md`), then regenerate
  the estate-root STATE.md via `just state-save` (or let `just land root --ticket T{id}` do it).
  The ⭐ PICK UP HERE block is generated mechanically from in-flight tickets. Manual edits in STATE.md
  are reserved for permanent gotchas and owner actions. Trigger on "save state", "write the handoff",
  "end of session", or from w0m-sdlc-archive step 6.
metadata:
  author: w0m
  namespace: w0m
  version: "2026.11.02-1793666924"
---

# w0m-state-save — write the handoff

`STATE.md` is the first thing the next session reads. Under [[T428]], **ticket Status notes are the
single source of truth for session handoffs**:

| Half | Bounded by | Who writes it | How it goes wrong |
|---|---|---|---|
| **ticket handoff** | `## Status notes` in `.tasks/T{id}.md` | you, at end of session | omitted, leaving no record of where this session stopped |
| **mechanical & generated** | `W0M-STATE:BEGIN` … `W0M-STATE:END` & `## ⭐ PICK UP HERE` | `just state-save` (synthesized from active tickets) | hand-edited directly in STATE.md instead of ticket notes |
| **permanent gotchas & actions** | `## 4. Gotchas ...` & `## 3. Other open threads` | you, with the user | left describing a thread that finished two sessions ago |

## Step 1 — record your session handoff in your active ticket

Every in-flight ticket carries a `## Status notes` section (`.tasks/T{id}.md`). Append a dated note
recording what was just finished, what is currently in flight, and what the next session must pick up:

```markdown
## Status notes

- YYYY-MM-DD — What this session did; where work stopped; exact next step for the next agent.
```

If multiple tickets were touched, update each ticket's own file.

## Step 2 — regenerate the mechanical block & synthesized pickup

```bash
just state-save
```

`just state-save` (and `just land`, T425) does two things:
1. Refreshes the mechanical facts payload between `W0M-STATE:BEGIN` and `W0M-STATE:END`.
2. **Synthesizes the `## ⭐ PICK UP HERE` block** directly from `.tasks/T*.md` (T428 AC2):
   - Lists every `in-progress` ticket with its ID, title, and newest dated status note.
   - Explicitly flags any in-progress ticket with no notes (`⚠️ NO status note recorded where this stopped`).
   - Lists tickets completed today to show what finished this cycle.

**Do not hand-edit anything between the mechanical markers or under the generated PICK UP block** —
it will be overwritten on the next save or land.

### Step 2b — rotate superseded history if needed

```bash
just state-rotate
```

Moves superseded sections into `project/state-archive/` and keeps `STATE.md` under its budget
(900 lines / 80 KiB).

## Step 3 — reconcile permanent gotchas and owner actions

Check if anything from your session belongs in the permanent editorial sections of `STATE.md`:
- **Gotchas the next agent MUST know** — expensive traps or environmental constraints that cost you time.
  A gotcha that was paid down (the code now prevents it) gets **deleted**.
- **Owner actions** — things only the human can do (rotate a credential, click a dashboard).

Do NOT write session narrative paragraphs in `STATE.md` — they live in ticket Status notes.

## Step 4 — verify, then commit

```bash
just state-check
```

Must exit 0. If it fails it prints the exact drift; re-run `just state-save`.

Commit `STATE.md` and `.tasks/T{id}.md` **in the same commit as the work it describes** (or land
atomically via `just land root --ticket T{id}`).

> ⚠️ **`--no-verify` is prohibited here and pointless.** The pre-push `state-check` is the gate;
> skipping it leaves the drift in place for the next session to trip over.

## Step 5 — Session Wrap-Up Gate (Completed vs Mid-Flight Tickets, T613)

Before ending any session, verify which of the two legal end-states applies:
- **Completed ticket (`status: done`, `queue: done`)**: You MUST have executed full `w0m-sdlc-archive` — zero unused/unwired surfaces (`supabase_surface_drift_check.py`), audited change logs (`*_audit_log` where applicable), `just lessons-harvest` + `LESSONS.md` + explicit disposition in `.tasks/T{id}.md` (`lessons_check.py`), all session/IDE reports & Mermaid diagrams mirrored repo-first to `.agents/reports/` (`just reports-ticket-check`, `just mmd-validate`), `just debt-check --enforce`, `just state-save`, `just agent-tree-land`, `git merge --ff-only origin/beta` in the live checkout, `just agent-tree-remove <name>`, and `just state-check` last.
- **Genuinely paused mid-flight ticket (`status: in-progress`)**: Checkpointed in `.tasks/T{id}.md` `## Status notes` with exact remaining ACs and next action so `just state-brief` surfaces it cleanly.

## Related

- [[w0m-state-load]] — the other end of this handshake; it re-measures rather than trusting what
  you wrote here.
- [[w0m-sdlc-archive]] — runs this as step 6.
