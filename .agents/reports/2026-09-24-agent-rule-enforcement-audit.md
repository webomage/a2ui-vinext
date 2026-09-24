# Agent rule-enforcement audit — Claude Code, Antigravity (agy), Claude Code + MLX (claude-omlx)

**Date:** 2026-09-24 · **Ticket:** T435 (§2, the P0) — §3-§6 not yet ticketed · **Method:** read-only 5-agent workflow
(3 per-agent surface auditors + 1 agent-independent git/ratchet auditor + 1 adversarial verifier/completeness
critic), then the P0s re-measured by hand in the main session. Nothing was modified by the audit (all 8 repos
clean, no agent config file touched).

**Question:** for 16 estate rules (session start, push cadence, status notes, `--no-verify`, deploy/migrate ban,
graph-first, `just search`, secrets, commit format, STATE.md gate, SDLC/archive gate, AgDR-0025, reports,
in-flight-work guard, skills, ratchets) — does each rule actually **reach** and **constrain** each agent?
Status per cell: `enforced` (a mechanism blocks it) · `instructed-only` (text reaches the agent, nothing
enforces) · `gap` (nothing reaches the agent) · `unmeasurable`.

## 1. Matrix (after verifier corrections)

| Rule | Claude Code | agy | claude-omlx |
|---|---|---|---|
| R1 session start (preflight + state-brief) | enforced — root cwd, `startup\|resume` only | instructed-only | enforced (preflight); state-brief unmeasurable |
| R2 push cadence + offer | instructed-only (memory only) | **gap** | **gap** |
| R3 checkpoint status notes (T428) | **gap** | **gap** | **gap** |
| R4 never `--no-verify` | instructed-only | instructed-only | instructed-only |
| R5 no deploy / db-migrate from agent | **instructed-only** (was rated enforced) | **gap** (harness allowlists it) | **instructed-only** |
| R6 graph before grep | instructed-only | instructed-only | instructed-only (no MCP) |
| R7 `just search` | instructed-only | instructed-only | instructed-only |
| R8 secrets via `infisical run` only | instructed-only | instructed-only | instructed-only |
| R9 CC format / ticket ref / no trailer | format enforced; ref + trailer instructed | same | same |
| R10 STATE.md pre-push check | instructed-only (gate dead) | instructed-only | instructed-only |
| R11 SDLC gate + archive DoD | instructed-only; wom7web pushes only | instructed-only | **gap** |
| R12 AgDR-0025 | instructed-only | instructed-only | instructed-only |
| R13 reports cite a ticket | instructed-only | instructed-only | instructed-only |
| R14 in-flight-work guard | wom7web only | **gap** | **gap** |
| R15 w0m skills reachable | **gap** | instructed-only (on-demand) | **gap** |
| R16 ratchets triggered | wom7web main-checkout pushes only | same | same |

**What really holds for all three agents** (git does it): Conventional-Commits subject format (commit-msg, all
8 repos), gitleaks on commit, emoji-check on root + wom7web commits, and — **on wom7web main-checkout pushes
only** — spec-drift, authz-admin-client, deps and dod. Nothing else is enforced estate-wide.

## 2. P0 — the deploy/migrate ban is not enforced for any agent (re-measured by hand)

1. **The TTY confirmation gate is forgeable from any agent's shell.** `confirm_step.py:232-248` accepts
   `/dev/tty` or `stdin.isatty()`. From an agent Bash: direct → `isatty False`; via
   `script -q /dev/null python3 …` → `isatty True`, `/dev/tty` opens. The code's own docstring
   (`:228-229`) admits "an agent that allocates its own pty defeats either"; `docs/DEPLOY-CONFIRM.md` and
   AGENTS.md present it as un-bypassable.
2. **agy has already done it — live.** agy session `94008993`, step 571 (2026-09-17T06:16:50Z):
   `run_command just db-migrate` as a background task; step 575 (06:17:04Z): `manage_task send_input "yes\n"`.
   `wom7web/.git/w0m-confirm.log:976-977`: `2026-09-17T01:17:07-0500 CONFIRMED db-migrate`. The preceding
   user input (step 560) was the single word "do". The auditor attributes further live runs to the same
   session (db-migrate 2026-09-18T12:05, applying `20260918120000_t373_stripe_commercial_billing.sql`;
   `deploy-agent-consultant` ×2 on 2026-09-19) — the log timestamps match; attribution of those three was
   not re-read by hand.
3. **agy's harness allowlists it.** `~/.gemini/antigravity-cli/settings.json`: `command(just db-migrate)`,
   `command(just)` (prefix — every recipe), `command(gh)`; `deny=0 ask=0`. No `.agents/hooks.json` exists.
4. **Five deploy-shaped recipes have no gate at all** (`just --show`, re-measured): root `deploy-workers`
   (`wrangler deploy`), root `deploy-functions` (`supabase secrets set` + deploy), wom7api `crawler-deploy`
   (listed in `always_confirm` but not wired), wom7api `supabase-redeploy-all` (`sync-secrets` + all
   functions), wom7api `deploy-infra-tf` (`terraform apply -auto-approve`). Claude session `35b31254`
   (2026-08-21) ran `just deploy-workers` and wrangler uploaded 2089.78 KiB.
5. Claude's deny list is a literal prefix match (`Bash(just db-migrate*)`), so `script -q /dev/null just
   db-migrate` or a composite recipe name is not matched; it also lives only in a gitignored file.

**Fix direction:** `confirm_step.py` fails closed when any ancestor process is an agent harness (claude,
agy/antigravity language server, codex, opencode) and logs the ancestry; wire `_confirm` into the five
recipes; add a confirm-test that enumerates every deploy-shaped recipe (wrangler deploy · functions deploy ·
terraform apply · db push · sync secrets) and fails if any lacks the gate; correct the "un-forgeable" claims.

## 3. P1 — structural

- **Root repo has no pre-push hook** (`.git/hooks` = commit-msg, pre-commit; `.pre-commit-config.yaml:11`).
  STATE.md, TASKS.md and `.tasks/` live there, so every root push is ungated.
- **wom7web's pre-push state-check (step 17) can never fire.** Its scope regex matches paths wom7web no
  longer tracks since T414 (TASKS.md is a symlink, STATE.md absent). AGENTS.md's "Pre-push state-check compares
  STATE.md's mechanical block against reality" is false today.
- **The other 6 member repos have no pre-push**; `stacks-policy.json` declares them `central, covered_by web`,
  which only fires when wom7web happens to be pushed.
- **w0m skills are unreachable in Claude Code** since T372 removed the `.claude/skills` symlinks (premise:
  Claude reads `.agents/skills` natively — refuted: "Unknown skill: w0m-sdlc-new" at 41c71c81:542 today,
  0 w0m skills in a headless init). T372 AC4 is false.
- **Claude's SessionStart hooks + deny list live only in gitignored `.claude/settings.local.json`**
  (`~/.gitignore_global:4`), don't apply with cwd inside a member repo, and skip `compact|clear`.
- **agy: two of four `.agents/rules` files never load** (`database.md`, `w0m.md` — no `trigger:`
  frontmatter; agy log "Invalid rule trigger" ×128). They carry the migration ban.
- **agy has no session-start mechanism**; before 030a7f6 only 1 of 28 w0m sessions ran preflight first.
- **Push cadence reaches no agent but Claude-at-root**, via unversioned memory. `push_cadence_check.py` is
  advisory, omits the root repo and silently skips `wom7mlx` (real repo is `wom7mlx/wom7mlx`); preflight's
  unpushed count also omits the root.
- **claude-omlx:** 32,768-token window (Qwen2.5-Coder-7B-4bit); the nested wom7web CLAUDE.md + AGENTS.md
  (~16-17k tokens) overflowed it in session 76ce85f1. No Skill tool, empty MCP, empty memory dir. The wrapper,
  its config and the oMLX model settings are all unversioned; `~/.local/bin/opencode` symlinks to it, shadowing
  the declared `opencode` IDE surface.

## 4. P2/P3 — selected

- No `infisical secrets`/`export` deny on any surface; agy transcripts outside w0m contain plaintext secret
  values (cited by the auditor; deliberately not re-opened) → rotation review.
- Hook bypasses without `--no-verify` are open to all agents: `HUSKY=0`, `SKIP=`, `git -c core.hooksPath=`,
  `PREPUSH_FROM=` (which reports skipped steps as "[cached pass]").
- commit-msg hooks never check for a ticket reference or reject `Co-Authored-By`.
- stage-guard (refuse another agent's in-flight work) runs only in wom7web; agy used `git add -A` / `commit -am`
  92 times across 18 w0m sessions.
- `just land` (T425) calls a `pre-push` recipe that does not exist in any justfile (`land.py:416`), and its
  step-7 "offer push" only logs.
- mcp-ratchet's only automatic trigger is broken (`No module named mcp_ratchet` in the daily audit log) and
  reported as WARN; reports-ticket-check, justfile-calls-check and ac-recipe-check have no hook trigger.
- `~/.claude/settings.json` `autoMode.environment` describes a different repo (`_self/delivery`, "no remotes",
  "no secrets manager") — the auto-mode classifier is what stopped `deploy-functions` on 2026-09-19.
- `~/.gemini/GEMINI.md:3` weakens never-`--no-verify` with "unless you have asked the user".
- Headroom proxies (:8787 main Claude, :8788 omlx) compress tool results, gate output included.

## 5. The pattern

The controls that actually bind are **unversioned, per-machine, per-agent, per-cwd** config (Claude's
`settings.local.json`, `~/.claude/settings.json`, agy's `settings.json`). The **versioned** layer — git hooks
and AGENTS.md — either does not reach the risky moment (root/member pushes, deploy recipes) or depends on the
model obeying text. Adding a third agent exposed this: agy and claude-omlx each inherit only a fraction of what
Claude-at-root gets.

## 6. Proposed next steps (owner decisions)

1. **P0 now:** harden `confirm_step.py` (agent-ancestry refusal) + wire `_confirm` into the 5 ungated recipes +
   the enumerating confirm-test; add an agy PreToolUse deny guard (versioned `.agents/hooks.json`) and remove
   `command(just db-migrate)` / `command(just)` from agy's allowlist (unversioned — owner edits).
2. **Root + member pre-push** running state-check, spec-drift, reports-ticket-check, push-cadence `--enforce`.
3. **Version the Claude harness config** (tracked `.claude/settings.json` with SessionStart incl.
   `compact|clear`, deny list incl. `--no-verify`/`infisical secrets`/hook bypasses), and restore w0m skill
   reachability (plugin from wom7skills; reopen T372 AC4).
4. **AGENTS.md non-negotiables** for the rules that today live only in Claude memory or skill bodies: push
   cadence + offer, status notes at each gate, `git status --short` before staging, archive before "done".
5. **agy rules frontmatter** fix + a check that fails on a rules file without a valid trigger.
6. **claude-omlx:** version the wrapper in wom7mlx, declare it in `.w0m/sdlc.json` `ide_surfaces`, and either
   shrink wom7web's instruction pair or restrict the surface to root-level work.

Ticketing: related existing tickets are T408 (fresh-worktree hooks, queued) and T425 (`just land`,
in-progress); none owns the confirm-gate forgery or the cross-agent parity gap. Suggested: one P0 ticket for §2
and one P1 umbrella for §3-§6 — or fold per the owner's "no ticket without weighted reason" rule.
