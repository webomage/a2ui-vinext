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
- **Work in your own agent tree, not the shared live tree (AgDR-0032, T531 AC6).** Single branch (`beta`), no PRs/remote branches:
  - **Start:** `just agent-tree <name>` creates `~/.w0m/work/<name>/w0m` (`agent/<name>` cut from `origin/beta`).
  - **Land:** inside your tree, `just agent-tree-land --dry-run` then `just agent-tree-land` (members first, root last); `just agent-tree-remove <name>` cleans up. Live root is owner/deploy only (`git merge --ff-only origin/beta` after landing); never regen `TASKS.md`/`STATE.md`/`DECISIONS.md` outside a complete tree; allocate new ticket IDs via `just ticket-new "<title>"` (or inspect via `just ticket-next`), never guess or manually assign IDs.
- **"Ready to deploy" is measured, never inferred (T503).** Run on fetched `origin/beta`: `just _deploy-preflight`, `just check-guardrails`, `just test`, `just goldens`, `just check-warp`, `just check-infisical`, `just state-check` **last**; state owner-only stages (Touch ID, `db-migrate`, ship, `smoke-live`).
- **Query `just lessons <topic>` before registering a suite, adding a dependency, editing a skill, writing credential fixtures, or scheduling a job (T549).** 4-Home Split (T178): `AGENTS.md` (invariants), `MEMORY.md` (machine facts), `.tasks/T##.md` (AC evidence + `## Status`), `@wom/LESSONS.md` (transferable rules; `w0m-web/.agent/` holds `deployments/`, `rules/`, `specs/`, `workflows/` per T127 R4).
- **Never run `just db-migrate`, `just deploy*`, or raw `gh pr create` from an agent shell (`docs/DEPLOY-CONFIRM.md`, T161 AC3, T435, `AgDR-0058`).** Migrations, deploys, and `AgDR-0047` disclosures stay Touch ID-gated; upstream OSS fork PRs go through `just pr-auto` / `just pr-open` (`scripts/w0m_prs.py`, enforcing `CONTRIBUTING.md`, template, duplicate, `Fixes #`, `merge-tree`, and anti-automation denylist e.g. `ml-explore/mlx-lm`).
- **Operator copy-paste `bash` snippets MUST be `<= 58` chars/line and `histexpand`-safe (`.agents/rules/copy-paste-commands.md`, T621).** Wrap with ` \`, single-quote `!` paths (`cd ~/Projects/'!self'/w0m`), emit pure runnable lines (zero `#`/`$`), and prefer short `just` aliases.
- **Graph before grep:** `just ask "<symbols>"` first; use `just search "<pattern>"` at root (`LC_ALL=C git --no-pager grep` inside a repo).
- **Database:** managed by migrations (`just db-migrate`). **Secrets:** process injection only (`infisical run --env=<env> --silent -- <cmd>`, zero `.env`).
- **Commits & Skills:** Conventional Commits referencing `T##`, zero `Co-Authored-By` trailers; skills synced from `w0m-skills/skills-registry.json` via `just skills-sync` (T152 AC5b).
- **OSS Forks:** fork to `github.com/webomage/<repo>` (never `casualuser` or `w0m-*`), GPG-signed (`-S`, `Aleksei Tcelishchev <casualuser@gmail.com>`), Why / What For / How PR body.
- **`STATE.md` / Decisions:** `just land` regenerates `STATE.md` (`state-check` verifies it); record AgDRs in [`docs/decisions/`](docs/decisions/) ([template](project/templates/decision.md), indexed in [`docs/DECISIONS.md`](docs/DECISIONS.md) via `just decisions`).
- **Free-Tier-First Resource Rule (`AgDR-0055`, `AgDR-0003`, `AgDR-0043`, T623):** Compress/hash client-side first; put edge compute, R2 (`$0` egress), KV, Turnstile + `@webomage/fingerprint`, and Workers AI on **Cloudflare Free Tier first**; reserve **Supabase Free Tier second** strictly for GoTrue Auth, RLS metadata, and compact `*_audit_log` rows.
- **Estate boundary & no shims (T302, `AgDR-0025`):** Estate `preflight.py` never depends on client workspaces (`check_estate_preflight_client_boundary()`); fail closed (`docs/ANTI-PATTERNS.md`), update 100% of callers atomically, zero shadow symlinks.
- **UI DS & copy gates (`T207`, `T667`):** Use `@webomage/ui` primitives and `var(--...)` tokens in `apps/cp` (`ds-conformance`); never leak `T##`, `AgDR-####`, `ADR-####`, or `AC#` into user-facing UI strings (`just ui-ticket-leak-check`).
- **Triangulated SSOT Protocol:** Reality Grounding (`fact-checker`, `just reality-verify`) → Adversarial Interrogation (`socrates`/`/grill-me`/`torvalds`) → Structural Single-Responsibility (`schema-critique`) → Weighted Decision Matrix.
- **Reports, scoping & drift hygiene (`.agents/reports/`, `T613`, `T614`):** Store reports/diagrams in `.agents/reports/` & `w0m-web/docs/reports/` first; split leftover scope into dependent tickets (`blocked_by:`); keep money/accounts/public posts owner-only. Zero dead UI controls, missing SQL refs (`w0m-web/project/scripts/supabase_surface_drift_check.py`), or synthetic `200 OK` fallbacks; mutable sensitive settings must log via `SECURITY DEFINER` triggers to `*_audit_log`.
- **Mandatory Session & Ticket Wrap-Up (`T613`, `T616`, `T640`):** Run **`just session-complete [T## ...]`** inside the active session to pass drift/reality/spec/DoD/debt gates, flip `.tasks/T##.md` to `status: done` + `queue: done` + `closed_as: completed`, run `just lessons-harvest` + `lessons_check.py`, pass `just reports-ticket-check` + `just mmd-validate`, `just state-save`, `just agent-tree-land`, fast-forward live checkout, `just agent-tree-remove`, archive transcript, and verify `just state-check` last.

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
| **Stacks, Ports & Layout** | `project/policies/stacks-policy.json`, `w0m-web/project/{ports,layout}-policy.json` | `just discovery`, `just ports-check`, `just layout-check` |
| **Inbound Tray (`_in/`)** | `_in/INDEX.md` (`just in-triage`, `just in-check`) | Disposition ledger & ticket/spec matcher (T447) |
| **System Standards & Topology** | `docs/standards/SYSTEM-STANDARDS-MATRIX.md`, `docs/ARCHITECTURE.md` | `just standards-check`, service flows, `docs/backend/KB-INDEX.md` |

### Canonical Script & Policy Locations (`@wom` root vs `w0m-web/project/`)

| Surface | Canonical Path | Never Guess / Stale Path |
|---|---|---|
| **Ticket Files & Queue** | `.tasks/T##.md`, `TASKS.md`, `scripts/tasks_render.py`, `scripts/sync_github.py` | `w0m-web/TASKS.md`, `scripts/tickets_render.py`, `scripts/gh_tasks_sync.py` |
| **Technical Debt Register** | `TECH-DEBT.md` & `scripts/debt_register_check.py` | `w0m-web/TECH-DEBT.md`, `w0m-web/project/scripts/debt_register_check.py` |
| **Lessons & Harvester** | `LESSONS.md`, `scripts/lessons_query.py`, `w0m-web/project/scripts/lessons_check.py` | `w0m-web/LESSONS.md`, `scripts/lessons_check.py` |
| **Emoji & Mermaid Gates** | `scripts/emoji_policy_check.py` & `just mmd-validate` | `w0m-web/project/scripts/emoji_policy_check.py`, `w0m-web/project/scripts/mmd_validate.py` |
| **Ports, Layout & Standards** | `w0m-web/project/{ports,layout,standards,hooks-llm}-policy.json` | `project/policies/ports-policy.json`, `project/policies/layout-policy.json` |
| **Supabase Drift Gate** | `w0m-web/project/scripts/supabase_surface_drift_check.py` | `scripts/supabase_surface_drift_check.py` |
| **`justfile` Entrypoints** | `justfile` (`@wom`), `w0m-api/justfile`, `w0m-cf/justfile`, `w0m-ext/justfile` | `w0m-web/justfile` |
| **Agent Tree & Release** | `w0m-web/project/scripts/agent_tree.py` & `scripts/release.py` | `scripts/agent_tree.py` |
| **Suite Runner & Registry** | `scripts/run_suites.py` & `w0m-web/project/test-suites.json` | `w0m-web/project/scripts/run_suites.py`, `project/test-suites.json` |
| **Graph & MCP Ratchet** | `scripts/graph_health.py`, `scripts/mcp_ratchet.py`, `w0m-web/project/mcp-exposure-baseline.json` | `w0m-web/project/scripts/graph_health.py`, `project/mcp-exposure-baseline.json` |
| **Version & Ticket Doctors** | `w0m-web/project/scripts/version_doctor.py`, `scripts/ticket_audit.py`, `scripts/ticket_schema_check.py`, `scripts/reports_ticket_check.py` | `scripts/version_doctor.py`, `w0m-web/project/scripts/ticket_audit.py`, `w0m-web/project/scripts/ticket_schema_check.py` |
