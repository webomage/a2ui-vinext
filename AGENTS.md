# w0m — Workspace Root Entrypoint

**Canonical conventions live in this workspace root entrypoint and [`CLAUDE.md`](CLAUDE.md).**

Top-level workspace root (`@wom`) containing the 7 estate repositories:
- `w0m-web`: Canonical monorepo (Astro apps, shared packages, design system, specs, SDLC).
- `w0m-api`: Backend capability layer (Supabase migrations, edge functions, worker).
- `w0m-cf`: Edge worker and cron dispatch.
- `w0m-ext`: Webomage browser extensions.
- `w0m-sec`: Security probes and policies.
- `w0m-skills`: Canonical w0m Agent Skills source and sync tooling.
- `w0m-mlx`: Apple MLX inference subsystem (`w0m-mlx/w0m-mlx`).

## Session start — every agent, before any work

1. **`just preflight --fast`** (~1.5s) — MCP, graph currency, repo state, toolchain, `_in/` tray disposition (`just in-check`).
2. **`just state-brief`** — current ⭐ PICK UP HERE block of `STATE.md`: **recorded intent, not measured fact** — re-derive cited numbers (`just state-check`, `just tasks`) before acting. Do not read full `STATE.md` or archive to orient. Full pickup gate: `w0m-state-load`.
3. **`just in-triage`** — when `preflight` reports `new` drops in `_in/` (or before picking up an inbound drop), inspect `_in/INDEX.md` and related tickets/specs (T447).

Claude Code runs session-start hooks automatically (`.claude/settings.local.json`); Antigravity, Codex, opencode, and Gemini must run them explicitly.

## Non-negotiables

- **Create or claim the ticket (`T##`) BEFORE writing or committing non-trivial code — never backfill tickets retroactively (T129 AC3/AC4).**
  - **Non-trivial work** (`feat`, `fix`, `refactor`, `perf`, `test`, `security`, `build`, or >1 file of substantive code, migrations, contracts, or runtime behaviour) MUST start via `w0m-sdlc-new` or `w0m-sdlc-start` on `.tasks/T##.md` BEFORE coding, and every commit must reference `T##` (`just commit-msg-check`).
  - **Trivial work** (`chore`, `docs`, `style`, `ci`, `revert` limited to single-file doc typos, `STATE.md`/index refreshes, or comments) is exempt unless staging substantive code/migrations (`.w0m/sdlc.json → change_classification`).
- **Never `--no-verify`.** Hooks are the gate; fix the finding instead.
- **Collaborative worktree safety & zero blanket git discards (T235).**
  - **NEVER execute blanket destructive git commands** (`git checkout -- .`, `git reset --hard`, `git clean -f`). Reverts must be file-scoped (`git checkout -- <file>`) after `git diff <file>`.
  - **NEVER run repository-wide formatters** (`pre-commit run --all-files`, full-tree `oxfmt`/`prettier`) on a dirty or shared tree; run `pre-commit run` on staged files only.
  - **Orient before modifying:** Check `git status` first; never overwrite, stage, or discard another contributor's in-flight files.
- **Work in your own agent tree, not the shared live tree (AgDR-0032, T531 AC6).** Single branch (`beta`), no PRs or remote branches — every agent works in its own full copy:
  - **Start:** from live root, `just agent-tree <name>` creates `~/.w0m/work/<name>/w0m` with all member repos nested on `agent/<name>` cut from `origin/beta`.
  - **Land:** inside your tree, `just agent-tree-land --dry-run` then `just agent-tree-land` (fetch, rebase onto `origin/beta`, check ticket ids, push `HEAD:beta` members first, root last); `just agent-tree-remove <name>` cleans up once pushed.
  - **Live checkout belongs to owner & deploy.** Never edit/stage/commit in it; sync after landing via `git merge --ff-only origin/beta`.
  - **Rules that bite:** never regenerate `TASKS.md`, `STATE.md`, or `docs/DECISIONS.md` outside a complete tree; take new ticket ids from `git ls-tree origin/beta .tasks/`.
- **"Ready to deploy" is measured on deploy stages, never inferred (T503).** Run on fetched `origin/beta`: `just _deploy-preflight`, `just check-guardrails`, `just test`, `just goldens`, `just check-warp`, `just check-infisical`, and `just state-check` **last**; state owner-only stages (Touch ID confirm, `db-migrate`, ship, `smoke-live`).
- **Query `just lessons <topic>` before registering a suite, adding a dependency, editing a skill, writing credential-shaped fixtures, or scheduling a job (T549).**
  - **4-Home Knowledge Split & Canonical `@wom/LESSONS.md` (T178 AC2/AC3/AC5):**
    1. **`CLAUDE.md` / `AGENTS.md`** — standing invariants and workflow gates loaded every session.
    2. **Auto-memory (`MEMORY.md`)** — durable cross-session machine/environment/user facts.
    3. **Ticket body (`.tasks/T##.md`)** — per-ticket AC evidence, verification outputs, and `## Status` handoff notes.
    4. **`LESSONS.md` (`@wom/LESSONS.md`)** — transferable engineering rules (`⇒` generalisation + `⭐` tell) queried via `just lessons <topic>`. (`w0m-web/.agent/` stays live for `deployments/`, `rules/`, `specs/`, and `workflows/` per T127 R4.)
- **Never run `just db-migrate`, deployment commands (`just deploy`, `just deploy-all`, `deploy-*`), or external PR creation (`gh pr create`) from an agent shell (`docs/DEPLOY-CONFIRM.md`, T161 AC3, T435).** Prepare code, migrations, tests, and PR proposals, then ask the human developer to run Touch ID-gated steps.
- **Graph before grep.** Run `just ask "<symbols>"` first for symbol/caller/dependency lookups.
- **When grepping, use `just search` — never bare grep at estate root.** Root git excludes member repos; use `just search "<pattern>"` (and `LC_ALL=C git --no-pager grep` inside a repo).
- **The database is managed by migrations. No exceptions.** Applied via `just db-migrate`.
- **Secrets reach commands only via process injection** — `infisical run --env=<env> --silent -- <cmd>`. Never add `.env` dependencies.
- **No `Co-Authored-By` / attribution trailers** in commits. Use Conventional Commits referencing `T##`.
- **Skills are governed via `.w0m/skills.json` (`just skills-sync`).** Never hand-edit `.agents/skills/` or `.opencode/commands/`; generate from `w0m-skills/skills-registry.json` (T152 AC5b).
- **Fork public OSS repos to `github.com/webomage/<repo>`, never `casualuser/<repo>`, with GPG-signed commits (`-S`) and Why / What For / How PR bodies.** Keep exact upstream repo names (`w0m-*` is reserved for first-party estate repos). Every `w0m-pr/` fork uses `git@github.com:webomage/<repo>.git` as `origin`, signed by `Aleksei Tcelishchev <casualuser@gmail.com>`.
- **`STATE.md` blocked push? `just land` regenerates it.** Pre-push `state-check` verifies `STATE.md` against reality.
- **Architectural Decisions (AgDR) — estate standard (T392).** Record decisions in [AgDR format](project/templates/decision.md) under [`docs/decisions/`](docs/decisions/) and index in [`docs/DECISIONS.md`](docs/DECISIONS.md) (`just decisions`).
- **Estate gates never depend on client workspaces; client checks live in `<client>-w0m` (T302).** Estate `preflight.py` must never depend on `_proj/`, `!proj/`, `_self/` outside `@wom`, or non-`w0m` roots in `project/policies/clients-policy.json` — enforced by `check_estate_preflight_client_boundary()`.
- **Zero silent fallbacks, clean cutovers over shims, zero shadow symlinks (AgDR-0025).** Fail fast and fail closed (`docs/ANTI-PATTERNS.md`); update 100% of callers atomically.
- **Use `@webomage/ui` Design System primitives from the start (`ds-conformance`, T207 AC5/AC6).** Never write raw `<button>`, `<input>`, `<select>`, or `#hex` colors in `apps/cp`; use `@webomage/ui` (`Button`, `Input`, `Select`, `Badge`, `Card`, `PageHeader`) and `var(--...)` tokens.
- **Triangulated Single Source of Truth (SSOT) Protocol:**
  1. **Reality Grounding (`fact-checker`)**: Cross-validate Docs vs Specs vs Code vs Tests vs Live Infra (`just reality-verify`).
  2. **Adversarial Interrogation (`socrates` / `/grill-me` / `torvalds`)**: Challenge boundary conditions and bloat before coding.
  3. **Structural Single-Responsibility (`schema-critique`)**: Ensure each table, column, route, and axis answers one real-world question.
  4. **Weighted Decision Convergence**: Settle contested forks via weighted decision matrix (cost, risk, unblocks, recommendation).
- **Repo-first storage for reports & diagrams (`.agents/reports/` & `w0m-web/docs/reports/` FIRST).** Store reports, audits, plans, and `.mmd` diagrams in `.agents/reports/` (and mirror to `w0m-web/docs/reports/`) before mirroring to IDE brain artifacts; link `file://` references to workspace paths.
- **Close open questions with weighted decisions; split leftover scope into dependent tickets** (`Split from: [[T…]]`, `blocked_by:`, `[x] … split into [[T…]]`). Money, accounts, and public posts stay owner-only.
- **Zero unused / unwired parts & audited change-log/drift observability (T613, T614).** Never ship dead UI toggles, queries to missing SQL relations/columns (`w0m-web/project/scripts/supabase_surface_drift_check.py`), synthetic `200 OK` fallbacks (`AgDR-0025`), or orphan exports/config keys. Mutable security, privacy, public-visibility, and commercial settings MUST log actor, old/new payload, and timestamp via `SECURITY DEFINER` triggers into append-only `*_audit_log` tables.
- **Mandatory Session & Ticket Wrap-Up — finish tickets/sessions as `done` before ending or deploy handoff (T613, T616).** Execute full `w0m-sdlc-archive` + `.w0m/sdlc.json → session_wrapup`:
  1. Pass drift, reality, spec, and debt gates (`supabase_surface_drift_check.py`, `just reality-verify`, `just spec-drift`, `just dod-check`, `just debt-check --enforce`).
  2. Flip `.tasks/T##.md` to `status: done` + `queue: done` with AC evidence and explicit lesson disposition.
  3. Run `just lessons-harvest`, record transferable rules in `@wom/LESSONS.md`, and pass `w0m-web/project/scripts/lessons_check.py`.
  4. Mirror reports/diagrams repo-first to `.agents/reports/` (`w0m-web/docs/reports/`), passing `just reports-ticket-check` and `just mmd-validate`.
  5. Run `just state-save`, land via `just agent-tree-land`, fast-forward live checkout (`git merge --ff-only origin/beta`), remove the pushed agent tree (`just agent-tree-remove <name>`), and verify `just state-check` exits `0` last.

## Fast Project Info & Indexed Data References

| Need | Fastest Tool / Recipe | What It Queries |
|---|---|---|
| **Code Symbols & Call Paths** | `just ask "<symbols>"` | `codegraph` across all repos + `graphify` semantic graph |
| **Semantic Knowledge Search** | `just graph-query "<query>" [repo\|global]` | Graphify entity & concept network |
| **Concept Subgraph & Degrees** | `just graph-explain "<concept>" [repo\|global]` | Node community, degree, incoming/outgoing edges |
| **Shortest Path** | `just graph-path "<A>" "<B>" [repo\|global]` | Shortest relationship path traversal |
| **Blast Radius / Impact** | `just graph-affected "<symbol>" [depth]` | Reverse graph traversal of callers/dependents |
| **Visual Graphs** | `just graph-tree`, `just graph-callflow`, `just crg-open` | Interactive D3 tree, Mermaid call-flow, AST graph (`:8765`) |
| **Architectural Decisions** | `docs/DECISIONS.md` (`just decisions`) | Indexed AgDR choices across repos (T232, T392) |
| **Anti-Patterns** | `docs/ANTI-PATTERNS.md` | Banned fallback traps, shims, dual SSOT |
| **Ticket Queue & Reality Audit** | `TASKS.md` (`just tasks`, `just reality-verify`) | Ranked task queue + completed ticket/spec reality check |
| **Technical Debt** | `TECH-DEBT.md` (`just debt-check`) | Decided debts + `## Closed-Debt Ledger` |
| **Late-Learn Friction** | `just lessons-harvest` | Transcript & `agent-tree-land` friction harvester (T602) |
| **Stacks, Ports & Layout** | `project/policies/{stacks,ports,layout}-policy.json` | `just discovery`, `just ports-check`, `just layout-check` |
| **Inbound Tray (`_in/`)** | `_in/INDEX.md` (`just in-triage`, `just in-check`) | Disposition ledger & ticket/spec matcher (T447) |
| **System Standards & Topology** | `docs/standards/SYSTEM-STANDARDS-MATRIX.md`, `docs/ARCHITECTURE.md` | `just standards-check`, service flows, `docs/backend/KB-INDEX.md` |

### Canonical Script & Policy Locations (`@wom` root vs `w0m-web/project/`)

| Surface | Canonical Path | Never Guess / Stale Path |
|---|---|---|
| **Ticket Files & Queue** | `.tasks/T##.md` & `TASKS.md` | `w0m-web/TASKS.md`, `project/tickets/T##.md` |
| **Technical Debt Register** | `TECH-DEBT.md` & `scripts/debt_register_check.py` | `w0m-web/TECH-DEBT.md`, `w0m-web/project/scripts/debt_register_check.py` |
| **Lessons & Harvester** | `LESSONS.md`, `scripts/lessons_query.py`, `w0m-web/project/scripts/lessons_check.py` | `w0m-web/LESSONS.md`, `scripts/lessons_check.py` |
| **Supabase Drift Gate** | `w0m-web/project/scripts/supabase_surface_drift_check.py` | `scripts/supabase_surface_drift_check.py` |
| **`justfile` Entrypoints** | `justfile` (`@wom`), `w0m-api/justfile`, `w0m-cf/justfile`, `w0m-ext/justfile` | `w0m-web/justfile` |
| **Agent Tree & Release** | `w0m-web/project/scripts/agent_tree.py` & `scripts/release.py` | `scripts/agent_tree.py` |
| **Suite Runner & Registry** | `scripts/run_suites.py` & `w0m-web/project/test-suites.json` | `w0m-web/project/scripts/run_suites.py`, `project/test-suites.json` |
| **Graph & MCP Ratchet** | `scripts/graph_health.py`, `scripts/mcp_ratchet.py`, `w0m-web/project/mcp-exposure-baseline.json` | `w0m-web/project/scripts/graph_health.py`, `project/mcp-exposure-baseline.json` |
| **Version & Ticket Doctors** | `w0m-web/project/scripts/version_doctor.py`, `scripts/ticket_audit.py`, `scripts/ticket_schema_check.py`, `scripts/reports_ticket_check.py` | `scripts/version_doctor.py`, `w0m-web/project/scripts/ticket_audit.py`, `w0m-web/project/scripts/ticket_schema_check.py` |
