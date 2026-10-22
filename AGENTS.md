# w0m — Workspace Root Entrypoint

**Canonical conventions live in this workspace root entrypoint and [`CLAUDE.md`](CLAUDE.md).**

This is the top-level workspace root (`@wom`) containing the 7 estate repositories:
- `wom7web`: Canonical monorepo (Astro apps, shared packages, design system, specs, SDLC tracking).
- `wom7api`: Backend capability layer (Supabase migrations, edge functions, worker).
- `wom7func`: Edge worker and cron dispatch.
- `wom7ext`: Webomage browser extensions.
- `wom7sec`: Security probes and policies.
- `wom7skills`: Canonical w0m Agent Skills source and sync tooling.
- `wom7mlx`: Apple MLX inference subsystem (in `wom7mlx/wom7mlx`).

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

- **Never `--no-verify`.** Hooks are the gate; fix the finding instead.
- **Collaborative worktree safety & zero blanket git discards.**
  The working tree is a **shared concurrent workspace** used simultaneously by human developers, Claude Code, Antigravity, and background agents (T235).
  - **NEVER execute blanket destructive git commands** (`git checkout -- .`, `git reset --hard`, `git clean -f`, or blanket restores). Any revert must be strictly surgical and file-scoped (`git checkout -- <file>`) after inspecting `git diff <file>`.
  - **NEVER run repository-wide formatters** (`pre-commit run --all-files`, full-tree `oxfmt`/`prettier`) on a dirty or shared tree. Pre-commit hooks must run only on staged files (`pre-commit run`).
  - **Orient before modifying:** At session pickup or before staging, inspect `git status` to distinguish your active ticket's changes from uncommitted work of other agents or human developers. Never overwrite, stage, or discard another contributor's in-flight files.
- **Work in your own agent tree, not the shared live tree (owner direction 2026-10-03/04, AgDR-0032, T531 AC6).** One branch (`beta`), no pull requests, no remote branches — but every agent edits and commits in **its own complete copy of the estate**.
  - **Start:** from the live root, `just agent-tree <your-name>` creates `~/.w0m/work/<your-name>/w0m`: the root repo with every member repo nested inside it, each on local branch `agent/<your-name>` cut from `origin/beta` (about 333 MB, seconds). Work and commit there with normal pathspec commits.
  - **Land:** from inside your tree, `just agent-tree-land --dry-run`, then `just agent-tree-land`: fetch, rebase onto `origin/beta`, check ticket ids, push `HEAD:beta` (members first, root last). It never forces and refuses a dirty tree, a rebase conflict, and a ticket id that collides with or leaves a gap on `origin/beta`. `just agent-tree-list` shows your sets; `just agent-tree-remove <name>` removes one that is fully pushed.
  - **The live checkout is the owner's and the deploy's.** Do not edit, stage or commit in it. After you land, the owner's checkout catches up with `git merge --ff-only origin/beta`; git refuses if that would overwrite uncommitted work.
  - **Why:** in one day in the shared tree another agent's uncommitted files blocked three pushes, tickets were swept into the wrong commits twice, and a ratchet baseline read from the live tree failed the release-shaped test tier (`LESSONS.md`, 2026-10-03).
  - **Rules that bite:** a partial layout (a root worktree without every member repo) makes derived files wrong and the hooks accept them, so never regenerate `TASKS.md`, `STATE.md` or `docs/DECISIONS.md` outside a complete tree; take a ticket id from `git ls-tree origin/beta .tasks/` right before you create it, not from your own tree.
- **"Ready to deploy" is measured on the deploy's own stages, never inferred.** The release is cut from `origin/beta` after a fetch, not from any working tree, so another agent's landing changes what ships. Before saying "ready", run on that commit: `just _deploy-preflight`, `just check-guardrails`, `just test`, `just goldens`, `just check-warp`, `just check-infisical`, then `just state-check` **last** (it goes stale whenever a ticket is created or edited). `test-prepush` is only the first slice. Say which stages only the owner's run can exercise (Touch ID confirm, `db-migrate`, ship, `smoke-live`). A failed deploy on 2026-10-06 found six blockers this way (`LESSONS.md` §3, T503).
- **Query `just lessons <topic>` before you register a suite, add a dependency, edit a skill, write a credential-shaped fixture or schedule a job.** The 2026-10-04 suite-recipe lesson existed and was repeated two days later; a lesson is a gate only once a check enforces it (T549).
  - **4-Home Knowledge Split & Canonical `@wom/LESSONS.md` (T178 AC2/AC3/AC5):** Every fact or lesson has one home:
    1. **`CLAUDE.md` / `AGENTS.md`** — standing architectural invariants and workflow gates loaded on every session.
    2. **Auto-memory (`MEMORY.md`)** — durable cross-session machine/environment/user facts (never ticket handoffs or code-review war stories).
    3. **Ticket body (`.tasks/T##.md`)** — per-ticket AC evidence, verification outputs, and session handoff notes (`## Status`).
    4. **`LESSONS.md` (`@wom/LESSONS.md`, configured via `.w0m/sdlc.json -> lessons_surface.file` / `lessons.path`)** — transferable engineering rules (`⇒` generalisation + `⭐` tell) queried via `just lessons <topic>`. Pre-root `wom7web/.agent/LESSONS.md` was migrated/seeded into `@wom/LESSONS.md` (`wom7web/.agent/` itself remains live for `deployments/`, `rules/`, `specs/`, and `workflows/` per T127 R4). Historical closed tickets (`T1`–`T176`+) are not retroactively backfilled into `LESSONS.md`; their per-ticket findings remain in `.tasks/T##.md`.
- **Never run `just db-migrate`, deployment commands (`just deploy`, `just deploy-all`, `deploy-*`), or external PR creation commands directly from an agent shell.**
  Live database migrations, production deploys, and external PR creation are **strictly gated by the human-confirmation gate** (`docs/DEPLOY-CONFIRM.md`, T161 AC3, owner direction 2026-08-10, 2026-09-26). The gate refuses any agent session outright (process ancestry + agent env markers, T435), then needs a real terminal and the device owner's Touch ID. Holding a terminal does not make an agent a human: agy answered a live `db-migrate` prompt through its own pty on 2026-09-17, which is why. **Agents must NEVER attempt to execute `just db-migrate`, `just deploy`, `just deploy-all`, or open external PRs (`gh pr create`, etc.) directly — prepare all code, migrations, tests, PR proposals, and verification checks, and explicitly request the human developer to run them.**
- **Graph before grep.** `just ask "<symbols>"` is the default first action for *where is X / who calls it / what depends on this* — not Grep.
- **When you do grep, use `just search` — never a bare grep at the estate root.** The root repo *excludes its own members*, so a root search returns **64 hits where the repos hold 5,268**. Use `just search "<pattern>"`. Always pass `LC_ALL=C` and `--no-pager` for git grep.
- **The database is managed by migrations. No exceptions.** Applied with `just db-migrate`.
- **Secrets reach a command only by process injection** — `infisical run --env=<env> --silent -- <cmd>`. Do not add a `.env` dependency.
- **No `Co-Authored-By` / attribution trailers** in commits. Conventional Commits, referencing the ticket.
- **Skills are governed via `.w0m/skills.json` (`just skills-sync`).** Never hand-place or edit skills in `.agents/skills/` or `.opencode/commands/`; generate surfaces from `wom7skills/skills-registry.json` (T152 AC5b).
- **Always fork public/open-source repositories to the `webomage` GitHub organization (`github.com/webomage/<repo>`), never personal `casualuser/<repo>` forks (owner direction 2026-10-18).** Every fork in `wom7pr/` must use `git@github.com:webomage/<repo>.git` as `origin` (`gh repo fork <upstream> --org webomage --clone=false`), while commits remain authored and GPG-signed by `casualuser` (`Aleksei Tcelishchev <casualuser@gmail.com>`).
- **`STATE.md` blocked your push? `just land` regenerates it.** Pre-push `state-check` compares STATE.md's mechanical block against reality.
- **Architectural Decisions (AgDR) — estate standard (T392).** All architectural and design decisions across every repo are recorded in [AgDR format](project/templates/decision.md) in [`docs/decisions/`](docs/decisions/) and indexed in [`docs/DECISIONS.md`](docs/DECISIONS.md) (`just decisions`). Never invent splinter registers.
- **Estate gates never depend on client workspaces; client checks live in `<client>-w0m` (T302).** An estate gate (`preflight.py` in estate mode) must never reference or depend on a client workspace (`_proj/`, `!proj/`, `_self/` outside `@wom`, or any non-`w0m` project root declared in `project/clients-policy.json`): a client directory is not w0m's health, may be absent or moved on another machine, and dilutes the signal of a green estate preflight. Conversely, client-side operational checks belong in the client's own `-w0m` workspace beside the toolchain they measure under the same `just` recipe names (e.g. `just vm-staleness` / `just vm-retention` in `bridgeroad-w0m`), so moving a check out of estate `preflight` is a relocation to its subject's workspace, never a deletion. Enforced mechanically by `check_estate_preflight_client_boundary()` in `wom7web/project/scripts/preflight.py`.
- **Zero silent fallbacks, clean cutovers over shims, zero shadow symlinks (AgDR-0025).** Fail fast and fail closed (`docs/ANTI-PATTERNS.md`). Multi-path fallback search ladders and backward-compatibility shims are strictly prohibited. 100% of callers must be updated atomically when a path or contract changes.
- **Use `@webomage/ui` Design System primitives from the very beginning (`ds-conformance`, T207 AC5/AC6).** Never write raw `<button>`, `<input>`, or `<select>` controls or hardcoded `#hex` colors in `apps/cp` (`.astro` or `.svelte`) — even when editing legacy files that still contain native HTML controls. Always import and use `@webomage/ui` primitives (`Button`, `Input`, `Select`, `Badge`, `Card`, `PageHeader`) and CSS custom property tokens (`var(--...)`) from the start, and convert touched legacy controls when editing a file.
- **Triangulated Single Source of Truth (SSOT) & Multi-Sided Verification.**
  Every fact, data schema, contract, and convention must have exactly **ONE canonical source of truth** across the estate. Dual SSOTs, parallel unsynchronized cookies/tokens, and duplicate state mechanisms are strictly prohibited.
  Before declaring or updating an SSOT, run the **Triangulated SSOT Protocol**:
  1. **Reality Grounding (`fact-checker`)**: Cross-validate claims across the 5 surfaces: *Docs vs Specs vs Code vs Tests vs Live Infra*. Code is the truth for *what is*; specs are the truth for *what should be*. Never accept ungrounded assertions.
  2. **Adversarial Interrogation (`socrates` / `/grill-me` / `torvalds`)**: Subject requirements to Socratic questioning and fresh-context adversarial review. Interrogate boundary conditions, missing edge cases, and challenge bloat or unnecessary abstractions before writing code.
  3. **Structural Single-Responsibility (`schema-critique`)**: Audit that every table, column, route, and axis answers exactly ONE real-world question with zero duplicate mechanisms answering the same question.
  4. **Weighted Decision Convergence**: Settle all contested tradeoffs or remaining architectural forks with a weighted decision matrix (cost, risk, unblocks, recommendation) rather than silent guesswork.
- **Visual & architectural reports via Artifacts (anti-terminal-overflow).** Complex architectural reports, broad system audits, and wide Mermaid (`.mmd`) diagrams must NEVER be dumped as raw multiline markdown in terminal chat (which causes terminal width overflow / ASCII diagram fallback warnings). Output them as Antigravity **artifacts** (`UserFacing: true`), preserve a permanent copy in `.agents/reports/` (mirrored to `wom7web/docs/reports/` when relevant), and present only concise summaries with clickable links in terminal responses.
- **Close a ticket's open questions with a weighted decision; split big leftovers into a dependent ticket** (owner, 2026-09-24).
  At the end of a ticket, list each remaining question with a recommended answer and its weight (cost, risk, what it
  unblocks), so the owner can settle them in one reply. Leftover scope that is a different kind of work (research
  vs shipping) or has its own dependencies becomes a **new ticket**: `Split from: [[T…]]` in its Links, `blocked_by:`
  when there is an order, and the original AC reads `[x] … split into [[T…]]` so the original can close. Example:
  T437 (arm64 WebTorrent fork) shipped; its Rust/WASM path became T438. Money, accounts and public posts stay
  owner-only; this speeds up deciding, it does not replace asking.

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
| **Decided Technical Debt** | `TECH-DEBT.md` (`just debt-check`) | Clean, non-drifting list of accepted debts |
| **Tech Stacks & Command Registry** | `project/stacks-policy.json` (`just discovery`) | Per-stack contract mapping tools to `just` commands |
| **Estate & Client Port Governance** | `project/ports-policy.json` (`just ports-check`) | Canonical port registry (`4321–4325` apps, `8787/8788` headroom, `8790` `wom7func`, `4400–4499` client projects, T402) |
| **Estate File Layout & Hygiene** | `project/layout-policy.json` (`just layout-check`) | Tracked file directory classes, stale report citations, and `.gitignore` justification across 8 repos (T446) |
| **Inbound Tray (`_in/`) Triage** | `_in/INDEX.md` (`just in-triage`, `just in-check`) | Disposition ledger (`new`/`adopted`/`declined`/`living`) and ticket/spec matcher for `_in/` drops (T447) |
| **Universal System Standards & SSOT** | `docs/standards/SYSTEM-STANDARDS-MATRIX.md` (`just standards-check`) | 10-layer RFC/Standard matrix, SSOT authority graph, meta-asset JSON Schemas, and coverage engine (T214) |
| **System Topology & Boundaries** | `docs/ECOSYSTEM.md` & `docs/ARCHITECTURE.md` | Maps cross-boundary data and service flows |
| **Backend Knowledge Base Index** | `docs/backend/KB-INDEX.md` | Curated index for backend, DB, and edge functions |

