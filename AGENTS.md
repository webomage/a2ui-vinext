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

## Non-negotiables

- **Never `--no-verify`.** Hooks are the gate; fix the finding instead.
- **Never run `just db-migrate` or deployment commands (`just deploy`, `just deploy-all`, `deploy-*`) directly from an agent shell.**
  Live database migrations and production deploys are **strictly gated by the interactive TTY confirmation gate** (`docs/DEPLOY-CONFIRM.md`, T161 AC3, owner direction 2026-08-10). The gate deliberately requires an interactive human terminal (`/dev/tty` or `stdin.isatty()`). Agent subprocesses run without a TTY, causing these commands to block or fail closed. **Agents must NEVER attempt to execute `just db-migrate`, `just deploy`, or `just deploy-all` directly — prepare all code, migrations, tests, and verification checks, and explicitly request the human developer to run them.**
- **Graph before grep.** `just ask "<symbols>"` is the default first action for *where is X / who calls it / what depends on this* — not Grep.
- **When you do grep, use `just search` — never a bare grep at the estate root.** The root repo *excludes its own members*, so a root search returns **64 hits where the repos hold 5,268**. Use `just search "<pattern>"`. Always pass `LC_ALL=C` and `--no-pager` for git grep.
- **The database is managed by migrations. No exceptions.** Applied with `just db-migrate`.
- **Secrets reach a command only by process injection** — `infisical run --env=<env> --silent -- <cmd>`. Do not add a `.env` dependency.
- **No `Co-Authored-By` / attribution trailers** in commits. Conventional Commits, referencing the ticket.
- **`STATE.md` blocked your push? Run `just state-save`, commit, push.** Pre-push `state-check` compares STATE.md's mechanical block against reality.
- **Zero silent fallbacks, clean cutovers over shims, zero shadow symlinks (AgDR-0025).** Fail fast and fail closed (`docs/ANTI-PATTERNS.md`). Multi-path fallback search ladders and backward-compatibility shims are strictly prohibited. 100% of callers must be updated atomically when a path or contract changes.
- **Visual & architectural reports via Artifacts (anti-terminal-overflow).** Complex architectural reports, broad system audits, and wide Mermaid (`.mmd`) diagrams must NEVER be dumped as raw multiline markdown in terminal chat (which causes terminal width overflow / ASCII diagram fallback warnings). Output them as Antigravity **artifacts** (`UserFacing: true`), preserve a permanent copy in `.agents/reports/` (mirrored to `wom7web/docs/reports/` when relevant), and present only concise summaries with clickable links in terminal responses.

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
| **System Topology & Boundaries** | `docs/ECOSYSTEM.md` & `docs/ARCHITECTURE.md` | Maps cross-boundary data and service flows |
| **Backend Knowledge Base Index** | `docs/backend/KB-INDEX.md` | Curated index for backend, DB, and edge functions |

