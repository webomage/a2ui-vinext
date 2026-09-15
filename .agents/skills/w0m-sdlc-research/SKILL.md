---
name: w0m-sdlc-research
description: >
  Deep spec/ticket verification-and-research step of the w0m SDLC lifecycle. The reusable
  grounding pass invoked AFTER a task is created (by w0m-sdlc-new) and AGAIN BEFORE work begins
  (by w0m-sdlc-start). Trigger when you need to prove a ticket/spec is real, needed, accurate,
  feasible, and non-duplicative — "research T37 in depth", "verify this spec against reality",
  "is this already done?". Researches ALL depths: knowledge, live code state, existing tickets,
  specs, and deploy/DB reality. Project-agnostic via `.w0m/sdlc.json`.
metadata:
  author: w0m
  namespace: w0m-sdlc
  gate: research
  version: "2026.09.12-1789241242"
---

# w0m-sdlc-research — the deep grounding gate

Prove a ticket/spec against **everything we already know and everything the code already does**,
before anyone trusts it. This is the anti-drift heart of the lifecycle: run it **after task
creation** (nothing enters the queue ungrounded) and **before start** (nothing begins on stale
assumptions). Output is a verdict backed by evidence, never an opinion.

## Step 0 — Load config

> **Path-drift check first (T119 AC3).** Run `just ticket-paths <id>` before reading anything the
> ticket claims. It resolves every file path the ticket names against the git tree of each repo in
> `.w0m/sdlc.json` → `repos`, and for a miss proposes the basename match. Two outcomes matter:
> **DRIFT** (the file exists elsewhere — the ticket is stale, and grepping the stated path would
> have found nothing) and **MISSING** (no such basename anywhere — the file was deleted, renamed
> beyond recognition, or is *planned* rather than existing, which changes what this ticket is).
> Record either in the Grounding Report. The tool never rewrites a path: a confidently wrong
> auto-correction is worse than a stale one, so propose the fix and let the human confirm.

Read `.w0m/sdlc.json` (walk up from cwd; if none, check one level down into child repos). Use
`tickets`, `specs`, `repos`, `codegraph`, `secrets.run`, `tech_debt`, `vcs`.

## Step 1 — Identify the subject
The ticket id (+ its `spec` if set), or a draft ticket handed in by `w0m-sdlc-new`. Load its full
text. Extract the concrete claims and intended outcomes to test.

## Step 2 — Research the depths (gather evidence from every source)
Run all that apply; record what each *actually* shows with a citation:

- **Knowledge.** Auto-memory (`MEMORY.md` + the relevant memory files), `CLAUDE.md`/`AGENTS.md`,
  `docs/` + KB, root `LESSONS.md` via **`just lessons "<query>"`** (not `.agent/LESSONS.md` — moved 2026-08-14), prior
  `docs/sessions/*`. → What do we already know that bears on this — decisions, gotchas, prior
  attempts, constraints?
- **Code state.** For each entity/behavior the ticket claims or needs: **`just ask` FIRST** (T163 —
  the graph is the default, grep is the fallback), else Grep/Read; `git log` for prior work. →
  Does it already exist (fully/partially)? What's the *real* starting point vs. the ticket's
  assumption?
  ⚠️ **Query by SYMBOL NAME, never as prose** — the query tokenizes, so *"what calls it"* matches
  `callLlm`/`callGuild`. Name the thing you mean. `just ask` refuses to answer from a stale union,
  so a green answer is a current one.
- **Existing work.** Scan the board + `tickets/` for **duplication/overlap/dependencies**; check
  roadmap alignment; scan `specs.dir` for related or *conflicting* designs. → Should this merge
  with an existing ticket, or is it blocked by one?
- **Decided debt.** Read **`TECH-DEBT.md`** and query the **`tech_debt` store**
  (`{tech_debt.table}`, refreshed by `{tech_debt.census}`) for rows touching the same files,
  symbols or area. → Three outcomes, all of which change the ticket:
  **(a)** the thing is *already a known, decided* debt row — link it and say what the ticket does
  that the row doesn't, or drop the ticket; **(b)** the ticket **pays a row down** — name the row,
  because CLAUDE.md requires deleting it on archive and an unnamed row never gets deleted;
  **(c)** the ticket **adds** debt — say so now rather than discovering it in review.
  ⚠️ A ticket filed against area X while a debt row already describes X is the same
  duplicate-work failure this gate exists to prevent — it just hides in a different file.
- **Spec drift.** If a `spec` exists, invoke `specs.verify_skill` (`openspec-verify-change`). If
  the ticket touches entity/vocab names, run `tech_debt.lexicon_lint`. → Does design match code?
- **Live/state.** Where the ticket touches running surfaces: DB schema, `/health`, deploy state
  (Supabase MCP or `{secrets.run} psql`). Read-only. → Is the premise still true in production?
- **Stack drift (T130).** If the ticket touches a stack's tools/build, run `just discovery` and note
  any drift (used-not-declared / declared-not-used) in the Grounding Report. → Does
  `project/stacks-policy.json` still match what the stack actually uses?

## Step 3 — Produce the Grounding Report (the gate's deliverable)
- **Validity** — real & needed? or **already-done / obsolete / duplicate** of T##? (cite the evidence)
- **Accuracy** — every claim in the ticket that does NOT match reality (the drift), with file:line/commit.
- **Prior art** — what already exists to reuse (don't rebuild it).
- **Dependencies & conflicts** — blockers, overlapping tickets, contradicting specs.
- **Scope** — over/under-scoped; missing or non-observable acceptance criteria.
- **Decided debt** — `TECH-DEBT.md` / `tech_debt` rows this ticket **duplicates**, **pays down**
  (name them — they must be deleted on archive) or **adds**. "None found" is a valid answer; a
  silent omission is not, because it reads identically to not having looked.
- **Feasibility & risks** — from debt, gotchas, live state.
- **Verdict** — one of: **proceed** · **revise ticket** (list edits) · **merge with T##** · **drop/obsolete**.

## Step 4 — Apply (only with confirmation)
If the verdict is *revise/merge/drop*, propose concrete ticket edits (scope, acceptance, prior-art
+ dependency links, or a merge/close). On confirm, update the ticket + board (+ GH) together, id
referenced. This gate **never starts implementation** — it grounds the work.

## Conventions
From config `conventions`: conventional commits w/ id, never skip hooks, no coauthor trailer, tool
ladder MCP>CLI>Python>TS>bash. Cite evidence for every claim. Absolute dates.

## Where this sits
Cross-cutting verify step, not a linear stage. Invoked by **`w0m-sdlc-new`** (after drafting a
ticket) and **`w0m-sdlc-start`** (before the Start Brief). After a *proceed* verdict at creation
the ticket enters the queue; at start it feeds the Start Brief.
