# w0m — Workspace Root Entrypoint

**Canonical conventions live in this workspace root entrypoint and [`CLAUDE.md`](CLAUDE.md).**

This is the top-level workspace root (`@wom`) containing the 7 estate repositories:
- `w0m-web`: Canonical monorepo (Astro apps, shared packages, design system, specs, SDLC tracking).
- `w0m-api`: Backend capability layer (Supabase migrations, edge functions, worker).
- `w0m-cf`: Edge worker and cron dispatch.
- `w0m-ext`: Webomage browser extensions.
- `w0m-sec`: Security probes and policies.
- `w0m-skills`: Canonical w0m Agent Skills source and sync tooling.
- `w0m-mlx`: Apple MLX inference subsystem (in `w0m-mlx/w0m-mlx`).

## Session start — every agent, before any work

1. **`just preflight --fast`** (~1.5s) — MCP, graph currency, repo state, toolchain, `_in/` tray disposition (`just in-check`).
2. **`just state-brief`** — the current ⭐ PICK UP HERE block of `STATE.md`: what the last session
   believed was next. It is **recorded intent, not measured fact** — re-derive any number it cites
   (`just state-check`, `just tasks`) before acting on it. Do not read the rest of `STATE.md` or its
   archive to orient. The full pickup gate is the `w0m-state-load` skill.
3. **`just in-triage`** — when `preflight` reports `new` drops in `_in/` (or before picking up an inbound drop), run `just in-triage` to inspect `_in/INDEX.md` and related tickets/specs (T447).

Claude Code runs both automatically (SessionStart hook in `.claude/settings.local.json`). Every other
agent — Antigravity, Codex, opencode, Gemini — has no such hook here and must run them itself.

## Non-negotiables

- **Create or claim the ticket (`T##`) BEFORE writing or committing non-trivial code — never backfill tickets retroactively (T129 AC3/AC4).**
  - **Non-trivial work** (`feat`, `fix`, `refactor`, `perf`, `test`, `security`, `build`, or >1 file of substantive code, migrations, contracts, or runtime behaviour) MUST start by creating (`w0m-sdlc-new`) or claiming (`w0m-sdlc-start`) a `.tasks/T##.md` ticket BEFORE implementation begins, and every commit must reference `T##` (`scripts/conventional_commit.py` / `just commit-msg-check`).
  - **Trivial work** (`chore`, `docs`, `style`, `ci`, `revert` limited to single-file doc typos, `STATE.md` / generated index refreshes, or comment-only edits) is exempt from ticket creation, but the commit-msg gate rejects unticketed `chore:`/`docs:` commits that stage substantive code or migrations (`.w0m/sdlc.json → change_classification`).
- **Never `--no-verify`.** Hooks are the gate; fix the finding instead.
- **Collaborative worktree safety & zero blanket git discards.**
  The working tree is a **shared concurrent workspace** used simultaneously by human developers, Claude Code, Antigravity, and background agents (T235).
  - **NEVER execute blanket destructive git commands** (`git checkout -- .`, `git reset --hard`, `git clean -f`, or blanket restores). Any revert must be strictly surgical and file-scoped (`git checkout -- <file>`) after inspecting `git diff <file>`.
  - **NEVER run repository-wide formatters** (`pre-commit run --all-files`, full-tree `oxfmt`/`prettier`) on a dirty or shared tree. Pre-commit hooks must run only on staged files (`pre-commit run`).
  - **Orient before modifying:** At session pickup or before staging, inspect `git status` to distinguish your active ticket's changes from uncommitted work of other agents or human developers. Never overwrite, stage, or discard another contributor's in-flight files.
- **Work in your own agent tree, not the shared live tree (owner direction 2026-10-03/04, AgDR-0032, T531 AC6).** One branch (`beta`), no pull requests, no remote branches — every agent edits and commits in **its own complete copy of the estate**.
  - **Start:** from the live root, `just agent-tree <your-name>` creates `~/.w0m/work/<your-name>/w0m`: the root repo with every member repo nested inside it, each on local branch `agent/<your-name>` cut from `origin/beta`. Work and commit there with normal pathspec commits.
  - **Land:** from inside your tree, `just agent-tree-land --dry-run`, then `just agent-tree-land`: fetch, rebase onto `origin/beta`, check ticket ids, push `HEAD:beta` (members first, root last). `just agent-tree-list` shows sets; `just agent-tree-remove <name>` removes one that is fully pushed.
  - **The live checkout is the owner's and the deploy's.** Do not edit, stage or commit in it. After you land, the owner's checkout catches up with `git merge --ff-only origin/beta`.
  - **Rules that bite:** never regenerate `TASKS.md`, `STATE.md` or `docs/DECISIONS.md` outside a complete tree; take a ticket id from `git ls-tree origin/beta .tasks/` right before you create it, not from your own tree.
- **"Ready to deploy" is measured on the deploy's own stages, never inferred.** Before saying "ready", run on the fetched `origin/beta` commit: `just _deploy-preflight`, `just check-guardrails`, `just test`, `just goldens`, `just check-warp`, `just check-infisical`, then `just state-check` **last**. Say which stages only the owner's run can exercise (Touch ID confirm, `db-migrate`, ship, `smoke-live`, `LESSONS.md` §3, T503).
- **Query `just lessons <topic>` before you register a suite, add a dependency, edit a skill, write a credential-shaped fixture or schedule a job (T549).**
  - **4-Home Knowledge Split & Canonical `@wom/LESSONS.md` (T178 AC2/AC3/AC5):** Every fact or lesson has one home:
    1. **`CLAUDE.md` / `AGENTS.md`** — standing architectural invariants and workflow gates loaded on every session.
    2. **Auto-memory (`MEMORY.md`)** — durable cross-session machine/environment/user facts (never ticket handoffs or code-review war stories).
    3. **Ticket body (`.tasks/T##.md`)** — per-ticket AC evidence, verification outputs, and session handoff notes (`## Status`).
    4. **`LESSONS.md` (`@wom/LESSONS.md`, `.w0m/sdlc.json -> lessons_surface.file` / `lessons.path`)** — transferable engineering rules (`⇒` generalisation + `⭐` tell) queried via `just lessons <topic>`. (`w0m-web/.agent/` remains live for `deployments/`, `rules/`, `specs/`, and `workflows/` per T127 R4.)
- **Never run `just db-migrate`, deployment commands (`just deploy`, `just deploy-all`, `deploy-*`), or external PR creation commands directly from an agent shell.**
  Live database migrations, production deploys, and external PR creation are **strictly gated by the human-confirmation gate** (`docs/DEPLOY-CONFIRM.md`, T161 AC3, T435). The gate refuses any agent session outright (process ancestry + agent env markers) and requires a real terminal + Touch ID. **Agents must NEVER attempt to execute `just db-migrate`, `just deploy`, `just deploy-all`, or open external PRs (`gh pr create`, etc.) directly — prepare all code, migrations, tests, PR proposals, and verification checks, and explicitly request the human developer to run them.**
- **Graph before grep.** `just ask "<symbols>"` is the default first action for *where is X / who calls it / what depends on this* — not Grep.
- **When you do grep, use `just search` — never a bare grep at the estate root.** The root repo *excludes its own members*, so a root search returns **64 hits where the repos hold 5,268**. Use `just search "<pattern>"`. Always pass `LC_ALL=C` and `--no-pager` for git grep.
- **The database is managed by migrations. No exceptions.** Applied with `just db-migrate`.
- **Secrets reach a command only by process injection** — `infisical run --env=<env> --silent -- <cmd>`. Do not add a `.env` dependency.
- **No `Co-Authored-By` / attribution trailers** in commits. Conventional Commits, referencing the ticket.
- **Skills are governed via `.w0m/skills.json` (`just skills-sync`).** Never hand-place or edit skills in `.agents/skills/` or `.opencode/commands/`; generate surfaces from `w0m-skills/skills-registry.json` (T152 AC5b).
- **Always fork public/open-source repositories to `github.com/webomage/<repo>`, never personal `casualuser/<repo>` forks, with GPG-signed commits and structured Why / What For / How PR descriptions (owner direction 2026-10-18, 2026-10-23, 2026-10-28).** Public open-source forks keep the **exact upstream repository name** (`github.com/webomage/<repo>`, or `github.com/webomage/<upstream-org>-<repo>` on collision), reserving the `w0m-*` prefix strictly for first-party estate repositories (`webomage/w0m`, `webomage/w0m-web`, `webomage/w0m-api`, `webomage/w0m-cf`, etc.). Every fork in `w0m-pr/` must use `git@github.com:webomage/<repo>.git` as `origin` (`gh repo fork <upstream> --org webomage --clone=false`), with every commit authored and GPG-signed (`-S`, `commit.gpgsign = true`) by `casualuser` (`Aleksei Tcelishchev <casualuser@gmail.com>`). Every PR description MUST explicitly include **Why (Rationale & Problem)**, **What For (Use Cases & Value)**, and **How (Implementation, Invariants & Verification)** alongside any upstream template sections.
- **`STATE.md` blocked your push? `just land` regenerates it.** Pre-push `state-check` compares STATE.md's mechanical block against reality.
- **Architectural Decisions (AgDR) — estate standard (T392).** All architectural and design decisions across every repo are recorded in [AgDR format](project/templates/decision.md) in [`docs/decisions/`](docs/decisions/) and indexed in [`docs/DECISIONS.md`](docs/DECISIONS.md) (`just decisions`). Never invent splinter registers.
- **Estate gates never depend on client workspaces; client checks live in `<client>-w0m` (T302).** An estate gate (`preflight.py` in estate mode) must never reference or depend on a client workspace (`_proj/`, `!proj/`, `_self/` outside `@wom`, or any non-`w0m` project root declared in `project/clients-policy.json`). Client-side operational checks belong in the client's own `-w0m` workspace beside the toolchain they measure under the same `just` recipe names (e.g. `just vm-staleness` / `just vm-retention` in `bridgeroad-w0m`). Enforced mechanically by `check_estate_preflight_client_boundary()` in `scripts/preflight.py`.
- **Zero silent fallbacks, clean cutovers over shims, zero shadow symlinks (AgDR-0025).** Fail fast and fail closed (`docs/ANTI-PATTERNS.md`). Multi-path fallback search ladders and backward-compatibility shims are strictly prohibited. 100% of callers must be updated atomically when a path or contract changes.
- **Use `@webomage/ui` Design System primitives from the very beginning (`ds-conformance`, T207 AC5/AC6).** Never write raw `<button>`, `<input>`, or `<select>` controls or hardcoded `#hex` colors in `apps/cp` (`.astro` or `.svelte`). Always import and use `@webomage/ui` primitives (`Button`, `Input`, `Select`, `Badge`, `Card`, `PageHeader`) and CSS custom property tokens (`var(--...)`) from the start, and convert touched legacy controls when editing a file.
- **Triangulated Single Source of Truth (SSOT) & Multi-Sided Verification.**
  Every fact, data schema, contract, and convention must have exactly **ONE canonical source of truth** across the estate. Before declaring or updating an SSOT, run the **Triangulated SSOT Protocol**:
  1. **Reality Grounding (`fact-checker`)**: Cross-validate claims across the 5 surfaces (*Docs vs Specs vs Code vs Tests vs Live Infra*). Code is the truth for *what is*; specs are the truth for *what should be*.
  2. **Adversarial Interrogation (`socrates` / `/grill-me` / `torvalds`)**: Interrogate boundary conditions, missing edge cases, and challenge bloat before writing code.
  3. **Structural Single-Responsibility (`schema-critique`)**: Audit that every table, column, route, and axis answers exactly ONE real-world question with zero duplicate mechanisms.
  4. **Weighted Decision Convergence**: Settle contested tradeoffs or architectural forks with a weighted decision matrix (cost, risk, unblocks, recommendation).
- **Repo-first storage for all reports & artifacts (`.agents/reports/` & `w0m-web/docs/reports/` FIRST, anti-terminal-overflow, owner direction 2026-10-28).** Always write and store architectural reports, audits, plans, and Mermaid (`.mmd`) diagrams **first inside the repository** in `.agents/reports/` (and mirror to `w0m-web/docs/reports/`), then mirror to the Antigravity artifact directory (`<appDataDir>/brain/<conversation-id>`, `UserFacing: true`) when needed for UI preview. Always link clickable `file://` references in terminal responses to the in-repo `.agents/reports/<name>.md` path (never only the external `~/.gemini/antigravity-cli/brain/` path) so Orca desktop and mobile tabs can load and edit them inside the authorized workspace root.
- **Close a ticket's open questions with a weighted decision; split big leftovers into a dependent ticket** (owner, 2026-09-24).
  At the end of a ticket, list each remaining question with a recommended answer and its weight (cost, risk, what it unblocks). Leftover scope that is a different kind of work becomes a **new ticket**: `Split from: [[T…]]` in its Links, `blocked_by:` when there is an order, and the original AC reads `[x] … split into [[T…]]` so the original can close (e.g. T437 → T438). Money, accounts and public posts stay owner-only.
- **Zero unused / unwired parts & audited change-log/drift observability (owner direction 2026-11-02, T613, T614).**
  Never ship dead UI toggles, queries/mutations referencing non-existent SQL tables/views/columns (`w0m-web/project/scripts/supabase_surface_drift_check.py`), synthetic `200 OK` placeholder fallbacks masking missing rows (`AgDR-0025`), or unreferenced exports/config keys. Mutable security, privacy, public-visibility, and commercial settings MUST record actor, old/new payload, and timestamp in append-only `*_audit_log` tables populated by `SECURITY DEFINER` triggers with `authenticated` `SELECT`-only owner/admin RLS.
- **Mandatory Session & Ticket Wrap-Up — complete tickets and sessions as `done` before ending or deploy handoff (owner direction 2026-11-02, T613).**
  Never stop half-closed after `w0m-sdlc-verify` when `just deploy-all` / `just db-migrate` is human-gated (`docs/DEPLOY-CONFIRM.md`). Every finished ticket and session MUST execute full `w0m-sdlc-archive` + Session Wrap-Up (`.w0m/sdlc.json → session_wrapup`):
  1. Prove zero unused/unwired surfaces and code↔schema drift gates (`supabase_surface_drift_check.py`, `debt-check --enforce`).
  2. Flip `.tasks/T##.md` to `status: done` + `queue: done` with full AC evidence and explicit lesson disposition (`Lesson captured in LESSONS.md: <heading>` or `Lessons: none (routine delivery)`).
  3. Run `just lessons-harvest`, record earned transferable rules in `@wom/LESSONS.md`, and pass `w0m-web/project/scripts/lessons_check.py`.
  4. Mirror all session/IDE brain reports and Mermaid diagrams repo-first into `.agents/reports/` (and `w0m-web/docs/reports/`), passing `just reports-ticket-check` and `just mmd-validate`.
  5. Run `just state-save`, land all repos via `just agent-tree-land`, fast-forward the live checkout (`git merge --ff-only origin/beta`), remove the pushed agent tree (`just agent-tree-remove <name>`), and verify `just state-check` exits `0` last.

## Fast Project Info & Indexed Data References

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
| **Architectural Anti-Patterns** | `docs/ANTI-PATTERNS.md` | Banned anti-patterns (fallback traps, lava flows, dual SSOT) & invariants |
| **Ticket Queue & Task Priorities** | `TASKS.md` (`just tasks`, `just tasks hot`) | Ranked task queue with status, priority, and ACs |
| **Decided Technical Debt** | `TECH-DEBT.md` (`just debt-check`) | Clean, non-drifting list of accepted debts + `## Closed-Debt Ledger` |
| **Worktree Late-Learn Friction** | `just lessons-harvest` (`scripts/lessons_query.py --harvest-friction`) | Harvests location misses, CLI/schema errors, and gate refusals from transcripts & `agent-tree-land` (T602) |
| **Tech Stacks & Command Registry** | `project/stacks-policy.json` (`just discovery`) | Per-stack contract mapping tools to `just` commands |
| **Estate & Client Port Governance** | `project/ports-policy.json` (`just ports-check`) | Canonical port registry (`4321–4325` apps, `8787/8788` headroom, `8790` `w0m-cf`, `4400–4499` client projects, T402) |
| **Estate File Layout & Hygiene** | `project/layout-policy.json` (`just layout-check`) | Tracked file directory classes, stale report citations, and `.gitignore` justification across 8 repos (T446) |
| **Inbound Tray (`_in/`) Triage** | `_in/INDEX.md` (`just in-triage`, `just in-check`) | Disposition ledger (`new`/`adopted`/`declined`/`living`) and ticket/spec matcher for `_in/` drops (T447) |
| **Universal System Standards & SSOT** | `docs/standards/SYSTEM-STANDARDS-MATRIX.md` (`just standards-check`) | 10-layer RFC/Standard matrix, SSOT authority graph, meta-asset JSON Schemas, and coverage engine (T214) |
| **System Topology & Boundaries** | `docs/ECOSYSTEM.md` & `docs/ARCHITECTURE.md` | Maps cross-boundary data and service flows |
| **Backend Knowledge Base Index** | `docs/backend/KB-INDEX.md` | Curated index for backend, DB, and edge functions |

### Canonical Script & Policy Locations (`@wom` root vs `w0m-web/project/`)

| Surface | Canonical Path | Never Guess / Stale Path |
|---|---|---|
| **Ticket Files & Queue** | `.tasks/T##.md` & `TASKS.md` | `w0m-web/TASKS.md`, `project/tickets/T##.md` |
| **Technical Debt Register** | `TECH-DEBT.md` & `scripts/debt_register_check.py` | `w0m-web/TECH-DEBT.md`, `w0m-web/project/scripts/debt_register_check.py` |
| **Lessons & Friction Harvester** | `LESSONS.md`, `scripts/lessons_query.py`, `w0m-web/project/scripts/lessons_check.py` | `w0m-web/LESSONS.md`, `scripts/lessons_check.py` |
| **Supabase Code↔Schema Drift Gate** | `w0m-web/project/scripts/supabase_surface_drift_check.py` | `scripts/supabase_surface_drift_check.py` |
| **Estate `justfile` Entrypoints** | `justfile` (`@wom` root), `w0m-api/justfile`, `w0m-cf/justfile`, `w0m-ext/justfile` | `w0m-web/justfile` (`w0m-web` uses root `just` or `pnpm --filter`) |
| **Agent Tree & Release Scripts** | `w0m-web/project/scripts/agent_tree.py` & `scripts/release.py` | `scripts/agent_tree.py` |
| **Suite Runner & Registry** | `scripts/run_suites.py` & `w0m-web/project/test-suites.json` | `w0m-web/project/scripts/run_suites.py`, `project/test-suites.json` |
| **Graph & MCP Ratchet** | `scripts/graph_health.py`, `scripts/mcp_ratchet.py`, `w0m-web/project/mcp-exposure-baseline.json` | `w0m-web/project/scripts/graph_health.py`, `project/mcp-exposure-baseline.json` |
| **Version & Ticket Doctors** | `w0m-web/project/scripts/version_doctor.py`, `w0m-web/project/scripts/ticket_audit.py`, `scripts/ticket_schema_check.py`, `scripts/reports_ticket_check.py` | `scripts/version_doctor.py`, `scripts/ticket_audit.py`, `w0m-web/project/scripts/ticket_schema_check.py`, `w0m-web/project/scripts/reports_ticket_check.py` |

