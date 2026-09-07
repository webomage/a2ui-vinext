---
trigger: always_on
description: Ticket work (T## in TASKS.md) must run through the w0m SDLC gates, not ad-hoc edits.
---

## w0m SDLC — mandatory for ticket work

If the task maps to a ticket (`T##` in `wom7web/TASKS.md`), run it through the SDLC gates.

- **Entry:** the `w0m` skill, or `w0m-sdlc-start` with the ticket id.
- **Lifecycle:** new → start → spec → build → review → security → verify → deploy → archive
  (`.w0m/sdlc.json` → `lifecycle`; each gate routes to its successor). `w0m-sdlc-research` is
  cross-cutting and runs inside `new` and `start`.
- **Config-driven:** every gate reads `.w0m/sdlc.json` — do not hardcode paths or commands.

**Consult before building, update on archive:**
`TASKS.md` (the T-row is status-of-record) · `project/tickets/T##.md` · `ROADMAP.md` ·
**`TECH-DEBT.md`** (decided debt; delete rows the ticket pays down) · `openspec/` ·
`docs/KNOWLEDGE-GRAPH.md` / `just ask "<q>"` for code questions before grep.

**Update the tracking surfaces in the SAME commit as the work.** A stale T-row misleads the next
agent — this has happened; T89 sat at "started, poller wired" through a session that finished it.

**Not for client/non-w0m projects.** Those gates assume `.w0m/sdlc.json` and w0m conventions —
use `wom7skills/GENERIC-SDLC-SET.md` instead.
