---
id: AgDR-0050
title: "Root-first estate layout (L2): single flat justfile namespace via import, @wom/scripts elevation, and zero shadow symlinks"
timestamp: 2026-10-26T01:45:00-05:00
agent: antigravity
model: claude-opus-4-6
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T509
---

# AgDR-0050 — Root-first estate layout (L2): single flat justfile namespace via import, @wom/scripts elevation, and zero shadow symlinks

## Y-statement

> In the context of **[[T509]] (completing the [[T414]] root elevation across the `@wom` estate workspace), where 68 Class-A estate scripts and 85 root-script test modules still sat in `wom7web/project/scripts/` and `wom7api/scripts/`, `wom7web/justfile` was an escaping symlink to `wom7api/justfile`, 19 estate policy/schema shadow symlinks remained in `wom7web/project/`, and recipe definitions were duplicated across `@wom/justfile` and `wom7api/justfile` with 63 forwarders and 33 reverse forwarders**, facing **silent path drift across recipes, JSON policies, git hooks, test runners, and launchd schedules whenever files moved, plus the anti-shim / zero-shadow-symlink mandate of [[AgDR-0025]]**, we decided **to adopt Layout L2: a single flat root `justfile` namespace split via `import 'just/estate.just'` with `set fallback := true` on sub-repo justfiles (`wom7web/justfile` symlink deleted), elevate all Class-A estate scripts to `@wom/scripts/` (122 scripts) and their tests to `@wom/scripts/tests/` (85 modules), remove all 19 estate shadow symlinks from `wom7web`, and enforce path and recipe integrity via `scripts/stale_path_check.py` and `scripts/justfile_calls_check.py`** to achieve **one canonical source of truth for estate commands, scripts, policies, and tests runnable from `@wom` or any sub-repo directory with zero duplicate recipe names, zero reverse forwarders, zero shadow symlinks, and conserved `run_suites.py` check counts**, accepting **that repo-specific DB/authz probes (U9) remain in `wom7web/project/scripts/` and `wom7api/scripts/` until their dedicated follow-up unit**.

## Context

- [[T414]] (2026-09-21) lifted the first batch of estate scripts and policies to `@wom`, but left the estate half-moved:
  1. `wom7web/justfile` remained a symlink to `../wom7api/justfile`, while `@wom/justfile` duplicated 361 recipes from `wom7api/justfile` (63 as `--justfile` forwarders) and `wom7api/justfile` carried 33 `--justfile ../justfile` reverse forwarders.
  2. 68 Class-A estate scripts (3 in `wom7api/scripts/`, 65 in `wom7web/project/scripts/`) and 85 test modules testing `@wom/scripts/` still lived inside sub-repos.
  3. 19 shadow symlinks in `wom7web/project/` pointed upward to `../../project/policies/*.json`, violating [[AgDR-0025]].
  4. No mechanical gate verified that script paths referenced inside `justfile` recipes, JSON/JSONC policies, git hooks, or launchd schedules existed on disk.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **O1 — Per-repo `just` modules (`mod api`, `mod web`)** | Separates sub-repo namespaces syntactically. | Renames every estate recipe invocation (`just api::db-migrate`), breaking 200+ docs, hooks, skills, and operator muscle memory. | **Rejected** |
| **O2 — Forwarding facade (`@wom/justfile` forwards to `wom7api/justfile`)** | Minimal recipe movement. | Violates [[AgDR-0025]] (shims over cutovers), preserves dual SSOT across two justfiles, and caused 8 dangling `sdlc-*` forwarders. | **Rejected** |
| **O3 — Layout L2: Single flat root `justfile` + `import 'just/estate.just'`, `set fallback := true`, `@wom/scripts/` elevation, and `stale-path-check` gate** | Preserves flat `just <recipe>` ergonomics from `@wom` and from inside every sub-repo (`cd wom7web && just tasks`), eliminates all duplicate recipes, reverse forwarders, and shadow symlinks, and enforces 5-carrier path existence at pre-push. | Requires atomic caller updates across recipes, policies, hooks, tests, and docs. | **Accepted ([[T509]])** |

## Decision

1. **Five-Carrier Stale-Path Gate (`scripts/stale_path_check.py`, `AC1`, `AC2`, `AC4`, `AC11`, `AC15`)**:
   - `just stale-path-check` inspects recipe bodies (via `just --dump --dump-format json`), JSON/JSONC policies and keys, git hooks (`.husky/`, `.githooks/`, `.pre-commit-config.yaml`), test-runner configs, and launchd plists/schedules (`schedules.jsonc`), failing closed (exit 1 on stale path or dangling `--justfile` target, exit 2 if unmeasurable).
2. **Single Root Recipe Namespace (`justfile` + `just/estate.just`, `AC3`, `AC7`, `AC9`, `AC13`)**:
   - `@wom/justfile` imports `just/estate.just` and defines all 862 estate and cross-repo recipes with root-relative paths and explicit `--projectId={{ infisical_project_id }}` on `infisical run` calls.
   - `wom7web/justfile` (escaping symlink) is deleted; `wom7api/justfile` retains only `set fallback := true` and the 4 `wom7api`-local recipes (`db-local-up`, `db-local-down`, `backup-daily`, `backup-weekly`).
   - `scripts/justfile_calls_check.py` enforces zero unresolved bare `just` calls, zero `--justfile ../justfile` reverse forwarders, and zero duplicate recipe names between `justfile` and `wom7api/justfile`.
   - `scripts/run_suites.py` resolves and executes all 355 declared suites from `@wom` (`API = ROOT`), conserving suite and check counts (`AC7`).
3. **Class-A Script & Test Elevation (`@wom/scripts/` & `@wom/scripts/tests/`, `AC5`, `AC6`, `AC8`, `AC16`)**:
   - All 68 remaining Class-A estate scripts moved to `@wom/scripts/` (122 top-level scripts total) and all 85 root-script test modules moved to `@wom/scripts/tests/`, covered by root `mypy.ini` (`just py-typecheck-root`, 157 source files, 0 issues) and `py-typing-check` (326 scripts).
   - Every `@wom/scripts/*.py` module carries a `Usage:` docstring naming `scripts/<name>.py` or `just <recipe>` (`AC16`).
4. **Zero Shadow Symlinks (`AC10`)**:
   - All 19 estate policy/schema shadow symlinks in `wom7web/project/` are removed in accordance with [[AgDR-0025]]; all callers resolve canonical paths under `@wom/project/policies/`.

## Consequences

- Running `just <recipe>` from `@wom` or any sub-repo (`wom7web`, `wom7api`, `wom7func`, `wom7ext`, `wom7sec`, `wom7skills`, `wom7mlx/wom7mlx`) resolves deterministically to the root namespace.
- Any future script move or recipe rename is gated at pre-push by `stale-path-check`, `justfile-calls-check`, `suites-drift`, `layout-check`, and `py-typecheck`.
- Deferred scope (`U9`: moving the 58 DB/authz probe scripts from `wom7web/project/scripts/` to `wom7api/scripts/`) remains tracked separately and in `TECH-DEBT.md`.
