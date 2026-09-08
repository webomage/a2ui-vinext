# w0m — Workspace Root Entrypoint

**Canonical conventions live in [`wom7web/AGENTS.md`](wom7web/AGENTS.md)** — read it first.

This is the top-level workspace root (`@wom`) containing the 7 estate repositories:
- `wom7web`: Canonical monorepo (Astro apps, shared packages, design system, specs, SDLC tracking).
- `wom7api`: Backend capability layer (Supabase migrations, edge functions, worker).
- `wom7cfworkers`: Edge worker and cron dispatch.
- `wom7ext`: Webomage browser extensions.
- `wom7sec`: Security probes and policies.
- `wom7skills`: Canonical w0m Agent Skills source and sync tooling.
- `wom7mlx`: Apple MLX inference subsystem (in `wom7mlx/wom7mlx`).

## Non-negotiables (full text in `wom7web/AGENTS.md`)

- **Never `--no-verify`.** Hooks are the gate; fix the finding instead.
- **Graph before grep.** `just ask "<symbols>"` is the default first action for *where is X / who calls it / what depends on this* — not Grep.
- **The database is managed by migrations. No exceptions.** Applied with `just db-migrate`.
- **Secrets reach a command only by process injection** — `infisical run --env=<env> --silent -- <cmd>`. Do not add a `.env` dependency.
- **No `Co-Authored-By` / attribution trailers** in commits. Conventional Commits, referencing the ticket.
- **`STATE.md` blocked your push? Run `just state-save`, commit, push.** Pre-push `state-check` compares STATE.md's mechanical block against reality.
