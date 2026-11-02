---
name: w0m-sdlc-start
description: >
  Start a ticket the right way. The FIRST gate of the w0m SDLC lifecycle
  (start→spec→build→review→security→verify→deploy→archive). Trigger when a developer says
  "start T37", "pick up a ticket", "begin work on <id>", or "what should I work on". Loads the
  ticket, VERIFIES its claimed state against reality (git/code/spec/tracker), gathers grounded
  context, flags gaps, produces a Start Brief, then flips status → in-progress and routes to the
  next gate. Project-agnostic: reads `.w0m/sdlc.json`. Attacks "spec-only changes actually built".
metadata:
  author: w0m
  namespace: w0m-sdlc
  gate: start
  version: "2026.11.01-1793588043"
---

# w0m-sdlc-start — the ticket kickoff gate

You are the **explore/orient** gate of the w0m SDLC lifecycle. Your job is NOT to implement. It
is to load a ticket, **prove what is actually true about it right now**, and hand the developer
(or the next gate) a grounded, gap-aware starting point. Trust *evidence*, never the `status`
field — the whole reason this gate exists is that ticket/spec status drifts from code reality
("spec-only changes that were actually built").

## Step 0 — Load the project config (always first)
Discover **`.w0m/sdlc.json`**: first walk **up** from the current working directory to the first
match (git-style). If none is found, also look **one level down** into immediate child
directories — a monorepo root holds the config in its canonical repo (e.g. `w0m-web/.w0m/`), so
`ls */.w0m/sdlc.json` catches it. Read it once; every path/command below comes from it. All paths
in the config are relative to the config's own repo, resolved through `root`/`repos`. Key fields:
`tickets` (source/board/dir/pattern/template/id_prefix), `specs` (system/dir/verify_skill),
`repos`, `vcs` (repo/default_branch/gh_account), `codegraph`, `secrets.run`, `commands`,
`tech_debt`, `conventions`, `lifecycle`. Full schema: the sibling `.w0m/README.md`.

If **no config is found**, don't guess silently: tell the user, assume conventional defaults
(`tickets.source:"files"`, `board:"TASKS.md"`, `dir:".tasks"`, `specs.system:"none"`,
single repo `.`), and offer to scaffold a `.w0m/` from the template. Everything below is written
against the config; `w0m`'s own values (in this repo's `.w0m/sdlc.json`) are the worked example.

### Step 0a — Environment preflight (T147 AC1)
Run `commands.preflight` (w0m: `just preflight --fast`, ~1.6s). It answers a **different question**
from Step 0b: not *are the interfaces conformant* but *is what this session will actually reach
reachable right now* — MCP servers, the graph index, the repos, the required binaries. **It reports,
it never blocks** (AC5), so treat every finding as context for the Start Brief rather than a stop.
Two findings change what you should do next, so read them rather than skimming the ✅s:
- a **stale/absent graph index** means *graph-before-grep* will mislead you in Step 3 — refresh it
  (`just graph-global`) or say you fell through to grep;
- a **declared-but-unreachable MCP server** means any plan that routes through it needs a fallback.
⚠️ It cannot tell you whether an MCP server is connected to the **running session** — a harness fact
no script can read. Both Obsidian servers were declared, enabled and listening for twelve days while
zero Obsidian tools existed. It labels that unverifiable rather than printing a number it cannot
measure; if the ticket depends on an MCP server, confirm the tools are actually present before
planning around them.

### Step 0b — Toolchain preflight (T119 AC7)
Run `commands.doctor` (w0m: `just sdlc-doctor`). It verifies the **two standard interfaces** the
rest of this gate depends on — commands via `toolchain.commands_via` (`just`) and secrets via
`toolchain.secrets_via` (`infisical`) — including the `tools-policy.json` version floors and
per-repo conformance. A **failure means a later gate command would break confusingly halfway**
(a missing recipe, an unparseable justfile, an unset `secrets.run`), so stop and fix it here
rather than mid-build. Warnings (e.g. an expired Infisical session) are advisory — surface them,
and note that a command in `commands.needs_secrets` WILL fail until the session is renewed.

## Step 1 — Resolve the ticket
- If the user gave an id, use it (prefix from `tickets.id_prefix`, e.g. `T37`).
- If not: **run `just tasks`** (from the estate root) and present its ranked candidates. Do **not**
  hand-read the board's NOW/NEXT sections — that was the instruction here until 2026-08-02 and it
  saw **40 of 119** open tickets (NOW 23 + NEXT 17), with the other 79 in nine sections it never
  read. The top-ranked ticket was in none of them. `just tasks` ranks across the whole queue and
  carries the score, the AC progress and the two boards' disagreement, all of which belong in this
  decision. For `tickets.source:"github"` run `gh issue list`.
  Present candidates with the **AskUserQuestion tool** — id, priority, one-line title, status
  glyph, AC progress. **Never auto-pick.**
- Load the ticket: files → `{tickets.dir}/{pattern}` (frontmatter + body); github → `gh issue
  view <n> --json`. Also load its board row. If a board row exists but the ticket file doesn't
  (or vice-versa), flag it as drift and offer to scaffold from `tickets.template`.

## Step 2 — Verify claimed state vs reality (invoke the research gate & ticket-audit)
1. **Run `just ticket-audit <id>` (T211):** Mechanically verifies the four tracking surfaces and classifies ACs (`confirmed`, `contradicted`, `stale`, `unmeasurable`). If surfaces disagree or ACs are contradicted by code reality, do NOT start the ticket until claims and scope are aligned.
2. **Invoke `w0m-sdlc-research`** on the ticket — it is the shared deep-verify step, run here *before
start* (as it was run *after creation* by `w0m-sdlc-new`). Do not re-implement its checks; consume
its **Grounding Report**. It covers, with evidence:
- **Status coherence** — tracker status vs board glyph (⚪🟡🔴✅💤) vs GH issue state.
- **"Is it secretly already (partly) done?"** — `git log --grep "<id>"` across the ticket's repos,
  codegraph/grep for the acceptance artifacts, and `openspec-verify-change` for spec↔code drift.
- **Dependencies** — blockers/overlaps from `[[T..]]` links + the board.
- **Prior art, scope, live/DB state.**

If research returns **already-done / obsolete / duplicate / revise**, stop and surface that — don't
start work on a ticket that shouldn't be started. Otherwise carry its report into the Start Brief.

## Step 3 — Gather grounding context
- **Skills the stack calls for (T127 AC5):** run **`just skill match`**. It intersects the techs
  this project actually has (`stacks-policy.json` `detect: dep:<name>`) with the skills each tech
  declares, minus what is already managed or deliberately excluded. Put any `+ recommended` lines in
  the Start Brief as a **non-blocking recommendation** — never auto-install: adding executable
  instructions to a project because a gate saw a dependency is not a decision a gate gets to make.
  ⚠️ An `undecided` count means techs whose `skills` key is **absent** (nobody chose) as opposed to
  an empty list (deliberately none) — surface it, it is a gap in the registry, not in the project.
  ⚠️ Exit **2** means no dependencies or no stacks registry — a missing input, not "nothing needed".
- **Is the area even declared? (T147 AC3)** If the ticket touches a stack, a gate or a build
  command, run `commands.coverage_scan` (w0m: `just coverage-scan`, ~0.3s) and check whether the
  paths it touches appear in the worklist. A path there is claimed by **no stack**, which means the
  registry-driven gates do not know it exists — so "the typecheck passes" may be a statement about
  files you are not changing. ⚠️ Uncovered means *undeclared*, **not** *ungated*: a workspace-wide
  recipe may still reach it. Put it in the Start Brief as a risk, never as a blocker.
- **Code map — the graph is the FIRST action, grep is the fallback (T163).** `just ask "<q>" [repo]`
  before Grep/Read. **codegraph** for *where is X / who calls it* (per-repo, re-indexed every
  commit); **graphify** for *cross-repo and architecture* (the only united graph).
  See `docs/KNOWLEDGE-GRAPH.md`.
  - ⚠️ **NAME SYMBOLS, DO NOT ASK PROSE.** The query tokenizes, so a natural-language question
    matches on its filler words: *"what does graph_fresh do and what calls it"* returned
    `callLlm` / `callGuild` / `call_llm` — matched off **"calls"** — while
    `graph_fresh probe STALE_COMMITS_FAIL` resolved exactly. Prose in, confident noise out.
  - Fall through to grep when the graph **misses**, and say so; do not silently double up. `just ask`
    refuses to answer from a stale union (`graph_fresh`), so a green answer is a current answer.
- **Spec:** if set, read the change's proposal + `## ADDED/MODIFIED Requirements`.
- **Prior art:** scan session notes / linked docs for earlier work on this area.
- **Standing debt:** read `{tech_debt.register}` (estate-root `TECH-DEBT.md`) for decided debt in the
  touched area (checking the `Tracked` column `owner: [[T##]]` / `found-at: [[T##]]` / `accepted: [[T##]]` links via `just debt-check`), and run `{tech_debt.markers}` for raw TODO/FIXME occurrences. The old
  `public.tech_debt` Supabase census was retired 2026-07-21 — do not query it.
- **Gotchas & Lessons (T232 AC10):** query earned rules via **`just lessons "<domain|symbols>"`** (or scan root `LESSONS.md`), plus traps from auto-memory (`MEMORY.md`) and `CLAUDE.md`/`AGENTS.md`. `LESSONS.md` is **READ-FIRST** — review relevant tells before starting.

## Step 4 — Produce the Start Brief (the gate's deliverable)
- **Verified state** — what is *actually* true now, each claim backed by evidence (commit hash,
  file:line, spec-verify verdict, tracker/GH state). Call out every claimed-vs-actual gap.
- **Acceptance criteria** — restate each, marked ✅ met / 🟡 partial / ⚪ not started *based on the
  evidence above*, not on the file's checkboxes.
- **Dependencies** — blockers and their real status.
- **Blast radius** — key files/symbols/specs to touch.
- **Risks & gotchas** — from debt + memory + deps.
- **Recommended next gate** — the successor of `start` in `lifecycle` (usually `w0m-sdlc-spec`
  if design is needed, else `w0m-sdlc-build`). Name it.

## Step 5 — Update tracking (only after the user confirms the brief)
- Set the ticket status → in-progress in `{tickets.dir}/{pattern}`.
  Update ticket frontmatter (`status: in-progress`) and status notes.
  Do not edit or manually render `TASKS.md` — `just land` regenerates it deterministically from `.tasks/` (T425).
  If github-mirrored, reflect it (re-run `tickets.sync`; ticket markdown is the source).
- Commit the ticket update with the id in the message per `conventions` (e.g.
  `chore(T37): start — status → in-progress`). Then hand off to the recommended next gate.

## Conventions (from config `conventions`, enforced)
Tool ladder MCP > CLI > Python > TS > bash-oneliner (no complex multiline bash). Never
`--no-verify`/skip hooks. Never add `Co-Authored-By`/attribution trailers. Update ticket + board
(+ GH) together, one commit, id referenced. Absolute dates (`YYYY-MM-DD`).

## Where this sits
First gate of the `w0m-sdlc-*` family (advances **T23**). Successors are defined by the config's
`lifecycle`. The `w0m` orchestrator routes into this gate. For projects that don't want the full
opinionated pipeline, see the curated generic set in `w0m-skills/GENERIC-SDLC-SET.md`.
