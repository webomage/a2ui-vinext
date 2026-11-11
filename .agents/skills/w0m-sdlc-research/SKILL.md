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
  version: "2026.11.10-1794361245"
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
>
> **Ticket reality audit (T211).** Run `just ticket-audit <id>` (`w0m-ticket-audit`) to mechanically
> cross-check the four tracking surfaces (`ticket.md`, `TASKS.md`, `project/tickets.json`, GitHub issue)
> and classify each AC into confirmed (✅), contradicted (🔴), stale (⚠️), or unmeasurable (❔). If surfaces
> disagree or ACs are contradicted by codebase reality, resolve or flag them before proceeding.

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
- **Vetted OSS package discovery (`awesome-repositories` MCP, T26) & Package Legitimacy Gate (`just package-legitimacy-check`, T714).** When a ticket or spec proposes
  introducing a new third-party dependency, replacing a custom module with an open-source library, or
  evaluating upstream candidates (`wom7open` / `w0m-pr`), query the read-only `awesome-repositories`
  MCP server (`search_repositories`, `search_metadata_tags`, `get_repository`, `list_curated_searches`,
  `list_repository_docs`; see `docs/PACKAGE-DISCOVERY-MCP.md`), run `just package-legitimacy-check` (`python3 scripts/package_legitimacy_check.py`) to block hallucinated/typosquatted `[SLOP]` packages and flag unpinned `[SUS]` dependencies, and verify the chosen package's license
  against `project/policies/deps-policy.json` before drafting the spec.
- **Triangulated SSOT & Multi-sided verification (`fact-checker`, `socrates` / `/grill-me`, `torvalds`).**
  Enforce adversarial rigor: cross-validate facts across the 5 surfaces (*Docs vs Specs vs Code vs Tests vs Live Infra*) using `fact-checker` to disprove stale assumptions. Apply Socratic questioning (`socrates` / `/grill-me`) to expose boundary conditions and missing edge cases. Apply ruthless pragmatism (`torvalds`) to eliminate bloat and unnecessary abstractions before any spec is drafted.
- **Epistemic Research Firewall (T717, adapted from `BMAD-METHOD` `bmad-deep-recon` & EGM Goldfish isolation).**
  1. **Never conclude from training weights alone:** Prior knowledge proposes hypotheses and queries; factual conclusions require verifiable evidence retrieved or measured in *this* run (file:line, commit SHA, live query, or dated primary upstream source).
  2. **Project-context firewall:** Internal tickets, briefs, PRDs, and prior claims shape *what questions to ask*, never *what is true*. They are inadmissible as proof of codebase or external ecosystem state. When delegating external or Goldfish research subagents, pass an isolated brief without unverified ambient assertions, and cite publisher/repo + publication/retrieval date on every external claim.
- **UI/UX surface & design system (MANDATORY for tickets with UI/UX changes).**
  Trigger condition: ticket `repos` includes `web` or `cp`, tags include `ui`/`ux`/`frontend`/`cp`/`design`, or the ticket touches `.astro`, `.svelte`, `.css`, `packages/ui`, or `apps/*`.
  **Enforce and launch UI skills:**
  - **`webomage-design`** (`w0m-web/design-system/`): Check canonical tokens (`tokens/*.css` — slate-950 canvas, `#38bdf8` primary, glassmorphic white 3–5% fill + white/10 hairline border, Inter font), guidelines, and existing component specifications (`packages/ui` and `design-system/components/`). Reusing existing tokens and components is mandatory; ad-hoc hex codes and un-mastered inline utilities are strictly prohibited.
  - **`steve-jobs`**: Critique product UX, simplicity, visual hierarchy, ergonomics, and touch targets. Challenge unnecessary forms, buttons, or navigation friction.
  - **`modern-web-guidance`**: Audit against modern browser APIs, responsive layouts, View Transitions, container queries, `:has()`, accessible dialogs/popovers, and modern frontend best practices.
  - **`a11y-debugging`**: Check semantic HTML, ARIA landmarks and attributes, keyboard focus order, contrast compliance, and touch target sizing.
  Output concrete UI findings, component reuse candidates, and token citations directly into the Grounding Report.

## Step 3 — Produce the Grounding Report (the gate's deliverable)
- **Validity** — real & needed? or **already-done / obsolete / duplicate** of T##? (cite the evidence)
- **Accuracy** — every claim in the ticket that does NOT match reality (the drift), with file:line/commit.
- **SSOT Reality & Boundary Findings** — 5-surface fact-check results (`fact-checker`), edge cases identified via Socratic questioning, and bloat/complexity warnings.
- **Prior art** — what already exists to reuse (don't rebuild it).
- **UI/UX & Design System alignment** (mandatory if UI-touching) — cited `design-system/` tokens, `@webomage/ui` components to reuse, `steve-jobs` simplicity critique, `modern-web-guidance` patterns, and `a11y-debugging` accessibility constraints.
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
