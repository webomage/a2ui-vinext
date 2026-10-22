# Antigravity rules — `wom7web` **and** `wom7api`

> 📍 **Moved 2026-08-30 from `.agent/rules.md` to `.agents/rules/w0m.md`.** Antigravity now
> defaults to the `.agents/` root and keeps `.agent/` only for backward compatibility, and
> openspec 1.11.0 made the same move. `just ide-trace` refused to run (exit 2, UNMEASURABLE)
> rather than scan the old path — *"the registry moved; fix the policy rather than scan a
> path that no longer exists"*.

> ⚠️ **GOVERNED ACROSS REPOS.** `.agents/rules/w0m.md` is synchronized across `@wom`, `wom7web`, and
> `wom7api` as real tracked files (cross-repo `.agent` symlinks were removed in T427 / AgDR-0025).
> Keep all copies aligned with the canonical rules in `@wom/AGENTS.md` and `CLAUDE.md`.

**Canonical conventions live in [`../CLAUDE.md`](../CLAUDE.md)** (i.e. `wom7web/CLAUDE.md`).
Read it first. This file exists because Antigravity does **not** autoload `CLAUDE.md` — it loads
*this* file — so the rules that must never be missed are restated here in full, and everything
else is a pointer.

> 🔴 **Rewritten 2026-08-10 ([[T192]]).** The previous version carried **0 of 6** non-negotiables,
> described only `wom7api` while governing both repos, and instructed agents to read `ADMIN_EMAIL`
> / `ADMIN_PASSWORD` from **`wom7web/.env`** — a file **T119 AC2b deleted**, whose absence is
> itself a standing rule. ⚠️ T192's filing recorded this file as *"byte-identical to wom7api's —
> one repo's rules copied into the other"*. That was wrong about the mechanism: it is **not a
> copy, it is a symlink**. Identical bytes had a structural cause, not a careless one, and the fix
> is a file written to serve **both** repos — not two files. `just ide-trace` now checks it against
> `CLAUDE.md` on every run; `just ide-trace-test` proves the check fails on the version it replaced.

## The two repos this governs

- **`wom7web`** — the **canonical** repo: the Astro workspace (5 apps, 5 packages), SDLC config
  (`.w0m/sdlc.json`), the ticket queue (`TASKS.md`), specs (`openspec/`), the design system, and
  this `.agent/` surface.
- **`wom7api`** — the **backend capability layer**: the Supabase project (migrations, edge
  functions, RLS), the Cloudflare Worker (`src/`), and **the `justfile` every other repo symlinks**.

Say which one you are in before you act. Tickets, specs and SDLC config are always read from
`wom7web`; deploy always runs from `wom7api`.

## Non-negotiables

These are not style preferences. Each exists because breaking it has already cost this estate.

- **Never `--no-verify`.** Hooks are the gate; fix the finding instead. There are no exceptions.
- **Never run `just db-migrate` or deployment commands (`just deploy`, `just deploy-all`, `deploy-*`) directly from an agent shell.**
  Live database migrations and production deploys are **strictly gated by the human-confirmation gate** (`docs/DEPLOY-CONFIRM.md`, T161 AC3, owner direction 2026-08-10). The gate refuses any agent session outright (process ancestry + agent env markers, T435), then needs a real terminal and the device owner's Touch ID. Holding a terminal does not make an agent a human: agy answered a live `db-migrate` prompt through its own pty on 2026-09-17, which is why. **Agents must NEVER attempt to execute `just db-migrate`, `just deploy`, or `just deploy-all` directly — prepare all code, migrations, tests, and verification checks, and explicitly request the human developer to run them.**
- **Graph before grep.** `just ask "<symbols>"` is the default first action for *where is X / who
  calls it / what depends on this* — not Grep. Name symbols; the query tokenizes, so prose
  returns confident noise.
- **The database is managed by migrations. No exceptions.** Every DDL, RLS policy, grant, bucket
  flag, trigger and function reaches the DB as a committed file in `wom7api/supabase/migrations/`,
  applied with `just db-migrate`. Never `psql`, the Supabase SQL editor, the dashboard, or an MCP
  write — those are for **reading**. `wom_ddl_guard` is a Postgres event trigger that *refuses*
  out-of-band DDL.
  ⚠️ **Never `supabase migration repair --status reverted` to unblock a push** — that is how six
  orphan migrations were created.
- **Secrets reach a command only by process injection** — `infisical run --env=<env> --silent --
  <cmd>`. **Do not add a `.env` or `.dev.vars` dependency.** `wom7web/.env` is gone; re-introducing
  one is a regression, not a migration.
- **No `Co-Authored-By` / attribution trailers** in commits. Conventional Commits, referencing the
  ticket.
- **`STATE.md` blocked your push? Run `just state-save`, commit, push.** The pre-push `state-check`
  compares STATE.md's mechanical block against reality. Reaching for `--no-verify` here is
  prohibited *and* pointless — the drift stays.
- **Zero silent fallbacks, clean cutovers over shims, zero shadow symlinks (AgDR-0025).** Fail fast and fail closed (`docs/ANTI-PATTERNS.md`). Multi-path fallback search ladders and backward-compatibility shims are strictly prohibited. 100% of callers must be updated atomically when a path or contract changes.
- **Use `@webomage/ui` Design System primitives from the very beginning (`ds-conformance`, T207 AC5/AC6).** Never write raw `<button>`, `<input>`, or `<select>` controls or hardcoded `#hex` colors in `apps/cp` (`.astro` or `.svelte`) — even when editing legacy files that still contain native HTML controls. Always import and use `@webomage/ui` primitives (`Button`, `Input`, `Select`, `Badge`, `Card`, `PageHeader`) and CSS custom property tokens (`var(--...)`) from the start, and convert touched legacy controls when editing a file.
- **Upstream PR & issue pre-flight discovery.** Before opening any new PR or filing an issue in an external/upstream repository (`wom7pr/*` or open-source dependencies), search open AND closed PRs and issues (`gh pr list --state all --search "<q>"`, `gh issue list --state all --search "<q>"`). If an active PR exists, do not duplicate it — contribute QA, verification proof, or targeted patches to that PR. If stalled/closed PRs exist, inspect why they stalled and cite them in the PR body, explaining why they are superseded and contrasting architectural trade-offs upfront.
- **Visual & architectural reports via Artifacts (anti-terminal-overflow).** Complex architectural reports, broad system audits, and wide Mermaid (`.mmd`) diagrams must NEVER be dumped as raw multiline markdown in terminal chat (which causes terminal width overflow / ASCII diagram fallback warnings). Output them as Antigravity **artifacts** (`UserFacing: true`), preserve a permanent copy in `.agents/reports/` (mirrored to `wom7web/docs/reports/` when relevant), and present only concise summaries with clickable links in terminal responses.

## Working here

- **Ticket work (`T##`) runs through the w0m SDLC gates** — entry `w0m-sdlc-start <id>`; every path
  is read from `wom7web/.w0m/sdlc.json`, never hardcoded.
- **Commands go through `just`**, not raw `pnpm`/`npx`/`tsc`/`deno`/`wrangler`/`supabase`.
  `just discovery` gates it.
- **Deploy runs from `wom7api/`** (`cd wom7api && just deploy`) — recipes use bare `supabase/` paths.
- **Local dev**: `just redev`, then test on `http://localhost:4321`.
- ⚠️ **wom7api is a hybrid runtime**: pnpm for the Worker, Deno for edge functions. `deno install`
  at its root clobbers the pnpm `node_modules`.
- Ecosystem map: `wom7web/docs/ECOSYSTEM.md`. Long-form reference: `wom7web/AGENTS.md`.

## Fast Project Info & Indexed Data References

Never scan the whole tree or blind-grep when pre-built, verified indexes are available:

| Need | Fastest Tool / Recipe | What It Queries |
|---|---|---|
| **Code Symbols & Call Paths** | `just ask "<symbols>"` | Queries `codegraph` across all repos + `graphify` semantic graph |
| **Semantic Knowledge Search** | `just graph-query "<query>" [repo\|global]` | Graphify entity & concept network |
| **Concept Subgraph & Degrees** | `just graph-explain "<concept>" [repo\|global]` | Node community, degree, incoming/outgoing edges |
| **Shortest Path Between Concepts** | `just graph-path "<A>" "<B>" [repo\|global]` | Shortest relationship path traversal |
| **Blast Radius / Impact Analysis** | `just graph-affected "<symbol>" [depth]` | Reverse graph traversal of affected callers/dependents |
| **Interactive D3 Code Tree** | `just graph-tree [repo\|global]` | Opens D3 collapsible tree visualization in browser |
| **Mermaid Call-flow Dashboard** | `just graph-callflow [repo]` | Generates interactive zoomable call-flow diagrams |
| **Full AST Code Review Graph** | `just crg-open [repo]` / `just crg-serve [repo]` | Opens / serves Code-Review-Graph AST visualizer (`:8765`) |
| **Architectural & Design Decisions** | `docs/DECISIONS.md` (`just decisions`) | Indexed record of all decided architectural choices (T232) |
| **Ticket Queue & Task Priorities** | `TASKS.md` (`just tasks`, `just tasks hot`) | Ranked task queue with status, priority, and ACs |
| **Decided Technical Debt** | `TECH-DEBT.md` (`just debt-check`) | Clean, non-drifting list of accepted debts |
| **Tech Stacks & Command Registry** | `project/stacks-policy.json` (`just discovery`) | Per-stack contract mapping tools to `just` commands |
| **System Topology & Boundaries** | `docs/ECOSYSTEM.md` & `docs/ARCHITECTURE.md` | Maps cross-boundary data and service flows |
| **Backend Knowledge Base Index** | `docs/backend/KB-INDEX.md` | Curated index for backend, DB, and edge functions |

## This directory

`.agent/` is **Antigravity's live IDE surface** — `rules.md`, `rules/`, `workflows/` — declared in
`.w0m/sdlc.json → ide_surfaces.connected`. **Do not delete it.** Only `.agent/skills/` is retired
(T127 R4), and `openspec update` regenerates that one; remove *that subdirectory* alone. An agent
deleted a client's whole `.agent/` on a warning about `.agent/skills`, committed and pushed it —
that incident is why this paragraph exists.
