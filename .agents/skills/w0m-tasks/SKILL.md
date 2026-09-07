---
name: w0m-tasks
description: Show and triage the ranked w0m ticket queue — HOT (what can be started) and SDLC (closest to done). Use when the user asks about the ticket queue, what to work on next, project tasks, or triage. Passes arguments through to `just tasks`.
metadata:
  version: "2026.09.07-1788817891"
---

# /w0m:tasks — the w0m ticket queue

Show the w0m ticket queue, ranked.

**Run this, from `wom7api/` — that is where the justfile lives** (wom7web's is a symlink to it):

```bash
cd /Users/proto/Projects/@self/@wom/wom7api && just tasks $ARGUMENTS
```

`$ARGUMENTS` passes straight through. With none, you get both boards, which is the default and the
common case. Other slices: `hot --parts`, `list --priority P2 -n 10`, `blocked`, `stats`.

**`plan`** tracks the ONE thing the estate decided to ship — the stages declared in
`.w0m/sdlc.json → current_plan`, which points at `ROADMAP.md §33` rather than restating it.
The default board renders it as a **table, LAST — after `sdlc`** (the owner reads the report
bottom-up, so the plan sits where scrolling stops); `plan` is the standalone view with
each stage's tickets and its `exit` criterion. ⚠️ **Report the AC percentages as progress, never
as stage completion** — every stage carries a written `exit`, and the blocking stage's is a
probe result. Ticking a checkbox is a claim; running the probe is evidence. A stage showing
100% with an unmet `exit` is not done, and saying otherwise is the failure this estate keeps
shipping. It exits **1** when the plan names a ticket that does not exist — that is plan↔queue
drift, not a rounding note, and it must be surfaced rather than skipped.

**`overview`** answers what the two rankings structurally cannot — not *which ticket next* but
**what this queue is about**. Groups the open set by **area/theme**, by **ROADMAP §** (rolled up:
`§13`, `§13.2` and `§13 — … (child of T149)` are one section written three ways), by **tag**, and
into **bundles** — same area *and* same section, i.e. work worth doing together because the context
is paid for once. Reach for it when triaging or planning, not when picking the next ticket.
⚠️ Every block prints its own denominator, and the gaps are the point: **39 of 119 tickets carry no
epic**, 27 have no acceptance criteria, and 113 of 153 tags appear exactly once. Read those numbers
before trusting any grouping — a roll-up over 80 of 119 tickets is not the roadmap.

## Presenting the result

**Print both tables in full.** Every row, with its links intact — the ticket `.md` and the GitHub
issue are both in there deliberately, and they are how the user opens the ticket. Do not collapse
rows into ranges, do not summarise "5–10 are all P1", and do not drop the Issue column to save
width. The owner has already had to correct exactly that once.

🔴 **Keep the ticket path ABSOLUTE, exactly as the tool prints it** —
`/Users/…/@wom/wom7web/project/tickets/T2.md`. Do not "tidy" it into a relative link.

The session's working directory is the **`@wom` umbrella**, not `wom7web`, so the tempting
shortening to `project/tickets/T2.md` resolves to nothing and every ticket link in the answer is
dead. That happened on 2026-08-16 and the owner had to report it. If a relative form is wanted, the
only correct one is **`wom7web/project/tickets/T2.md`** — verify it resolves from the cwd before
using it, rather than assuming which repo is the root.

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
