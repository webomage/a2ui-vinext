---
name: w0m-tasks
description: Show and triage the ranked w0m ticket queue, active epics, and plan progress — HOT (what can be started), SDLC (closest to done), and PLAN (current progressing scope with linked Mermaid diagrams). Trigger when the user asks "how about current plan progress?", "plan progress", "what to work on next", "project tasks", "ticket queue", or "triage". Passes arguments through to `just tasks`.
metadata:
  version: "2026.10.26-1793009642"
---

# /w0m:tasks — the w0m ticket queue

Show the w0m ticket queue, ranked.

**Run this directly from the workspace root `@wom` or from `w0m-web`:**

```bash
just tasks $ARGUMENTS
```

`$ARGUMENTS` passes straight through. With none, you get both boards (`hot` and `sdlc`), which is the default and common case. Other core slices: `hot --parts`, `list --priority P2 -n 10`, `blocked`, `stats`.

### Triage Commands

- **`next`**: Shows the single most actionable next ticket and prints the exact pickup command (`just sdlc-start <id>`).
- **`wip`**: Lists all currently active `in-progress` tickets with AC progress bars, priority, and blocker links, sorted by completion.
- **`tree [--ticket <id>]`**: Visualises the dependency tree for a ticket (defaults to current context / active branch), showing what blocks it and what it unblocks.
- **`area [--area <name>]`**: Renders the task registry grouped by functional **Area** (theme). Includes an overall Area Breakdown Summary table (Open, WIP, Done, Total, % Complete) and formatted markdown tables for each area (`product`, `sdlc`, `tools`, `infra`, `security`, `ai`, `knowledge`, `schemas`, `data`, `skills`, `mcp`, `sec`) with ticket links, GitHub issue links, priority, status, queue, AC progress, and epic. **Do NOT post this by default** — the default invocation (`just tasks`) outputs only the `hot` and `sdlc` boards. Only render the area tables when the `area` option or subcommand is explicitly requested.

### Epic & Milestone Boards

The third board in `tasks` output is **`EPIC`** (callable standalone via `just tasks epic`, `just tasks current`, or `just tasks plan`):
- **`epic`**: By default, dynamically projects the active Epic from your working ticket / git branch (e.g. `ROADMAP §13`).
- **`epic --epic <section|name>`**: Projects the board for any specified Epic (e.g. `just tasks epic --epic 13.8`). Groups epic tickets into `wip`, `queued`, `blocked`, and `done` stages with AC progress bars.
- **`current`**: Shows the estate's canonical active program/milestone declared in `.w0m/sdlc.json → current_plan` (pointing at `ROADMAP.md §33`).
- **`plan`**: Backwards-compatible alias. Supports `--tickets <T1,T2,...>`, `--tag <tag>`, and `--plan <name>`.

⚠️ **Report the AC percentages as progress, never as stage completion** — every stage carries a written `exit`, and the blocking stage's is a probe result. Ticking a checkbox is a claim; running the probe is evidence. A stage showing 100% with an unmet `exit` is not done, and saying otherwise is the failure this estate keeps shipping. It exits **1** when the plan names a ticket that does not exist — that is plan↔queue drift, not a rounding note, and it must be surfaced rather than skipped.

⚠️ Every block prints its own denominator, and the gaps are the point: **39 of 119 tickets carry no epic**, 27 have no acceptance criteria, and 113 of 153 tags appear exactly once. Read those numbers before trusting any grouping — a roll-up over 80 of 119 tickets is not the roadmap.

### Plan Progress Reporting ("plan progress" / "how about current plan progress?")

When the user asks "how about current plan progress?", "plan progress", or requests a strategic progress review:
1. **Triangulate the 3 Progress Planes**:
   - **Recently Shipped**: What landed in the latest release deployment (e.g. `releases/*.json`, deploy log, verified live health endpoints).
   - **Canonical Strategic Plan**: The active milestone declared in `.w0m/sdlc.json -> current_plan` (queried via `just tasks current` or `just tasks plan`), showing stage completion and exit verdicts.
   - **Current In-Flight Engineering Scope**: Active `in-progress` tickets (queried via `just tasks wip`) and immediate cross-ticket unblockers.
2. **Generate the Artifact & Linked `.mmd` Diagram**:
   - Write a permanent report to `.agents/reports/YYYY-MM-DD-t{id}-plan-progress.md` (citing the active primary ticket like `T478`).
   - Write the companion diagram to `.agents/reports/YYYY-MM-DD-t{id}-plan-progress.mmd` with full topology across the three planes.
   - Validate the Mermaid diagram with `node w0m-skills/skills/mmd-validate/validate.mjs <file.mmd>` to ensure clean parsing.
   - In Antigravity sessions, emit a user-facing Artifact (`UserFacing: true`) containing the Markdown report with interactive SVG Mermaid graphics.
3. **Anti-Terminal-Overflow Presentation**:
   - Render a structured, concise summary in terminal/chat (Shipped, Canonical Plan, In-Flight Critical Path, Dependencies).
   - Link directly to the generated `.md` report and companion `.mmd` diagram.
   - Provide the zero-width browser viewer command: `just diagram <path.mmd>`.
   - Never paste raw multiline Mermaid fences directly into terminal chat.

## Presenting the result

**Print both tables in full.** Every row, with its links intact — the ticket `.md` and the GitHub
issue are both in there deliberately, and they are how the user opens the ticket. Do not collapse
rows into ranges, do not summarise "5–10 are all P1", and do not drop the Issue column to save
width. The owner has already had to correct exactly that once.

🔴 **Keep the ticket path ABSOLUTE, exactly as the tool prints it** —
`/Users/…/@wom/.tasks/T2.md`. Do not "tidy" it into an outdated relative link.

The session's working directory is the **`@wom` umbrella**, so tickets resolve canonically at
`.tasks/T2.md`. Verify it resolves from the cwd before using it.

**Then say what the boards mean**, briefly. Useful things to look for:

- **The disagreement between the two boards is the signal** — the footer says so and it is right.
  `hot` is blind to how finished something is; `sdlc` is blind to whether a ticket can be worked at
  all. A ticket topping both (as T99 does) is genuinely the strongest candidate. A ticket high on
  `sdlc` but absent from `hot` is usually blocked — worth naming, not worth starting.
- **A ticket at 100% that still shows `in-progress`** is a finished ticket squatting a ranked slot;
  its `status:` field was never moved. Say so — that is a bug in the record, not a ranking.
- **A `—` in the Prio column** is an untriaged ticket. The ranking cannot place it honestly.
- **The excluded count in the SDLC header** ("N of M open tickets have NO acceptance criteria") is
  the queue's blind spot, not a rounding note. Those tickets are invisible to the completeness
  board entirely — not scored zero.

Report the counts as the tool prints them. Do not recompute a total by hand from the visible rows;
each board shows the top 10 of a much larger set.
