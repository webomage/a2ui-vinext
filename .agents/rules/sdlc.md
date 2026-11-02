---
trigger: always_on
description: Ticket work (T## in TASKS.md) must run through the w0m SDLC gates, not ad-hoc edits.
---

## w0m SDLC — mandatory for ticket work

**Create or claim the ticket (`T##`) BEFORE writing or committing non-trivial code — never backfill tickets retroactively (T129 AC3/AC4).**
Any non-trivial change (`feat`, `fix`, `refactor`, `perf`, `test`, `security`, `build`, or >1 file of substantive code/migrations/contracts) requires creating (`w0m-sdlc-new`) or claiming (`w0m-sdlc-start`) a `.tasks/T##.md` ticket BEFORE implementation begins, and referencing `T##` in the commit message (`just commit-msg-check`). Trivial changes (`chore`, `docs`, `style`, `ci`, `revert` touching only docs/state/typos) are exempt unless they stage substantive code or migrations (`.w0m/sdlc.json → change_classification`).

If the task maps to a ticket (`T##` in `TASKS.md`), run it through the SDLC gates.

- **Entry:** the `w0m` skill, or `w0m-sdlc-start` with the ticket id.
- **Lifecycle:** new → start → spec → build → review → security → verify → deploy → archive
  (`.w0m/sdlc.json` → `lifecycle`; each gate routes to its successor). `w0m-sdlc-research` is
  cross-cutting and runs inside `new` and `start`.
- **Config-driven:** every gate reads `.w0m/sdlc.json` — do not hardcode paths or commands.

**Consult before building, update on archive:**
`TASKS.md` (the T-row is status-of-record) · `.tasks/T##.md` · `ROADMAP.md` ·
**`TECH-DEBT.md`** (decided debt; move paid-down rows to `## Closed-Debt Ledger` and run `just debt-check --enforce`) · `openspec/` ·
`docs/KNOWLEDGE-GRAPH.md` / `just ask "<q>"` for code questions before grep.

**Triangulated SSOT mandatory for specs & research:**
Before finalizing a spec or design, enforce the Triangulated SSOT Protocol: ground claims across the 5 surfaces (`fact-checker`), interrogate boundary conditions (`socrates` / `/grill-me`), audit single-responsibility (`schema-critique`), and settle open questions with weighted decisions.

**Update the tracking surfaces in the SAME commit as the work.** A stale T-row misleads the next
agent — this has happened; T89 sat at "started, poller wired" through a session that finished it.

**Not for client/non-w0m projects.** Those gates assume `.w0m/sdlc.json` and w0m conventions —
use `w0m-skills/GENERIC-SDLC-SET.md` instead.
