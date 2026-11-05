---
id: AgDR-0057
title: "Content-addressed estate tree-set certification in session-complete and SHA-cached deploy gates"
timestamp: 2026-11-05T16:35:00-05:00
agent: antigravity
model: gemini-2.5-pro
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T650
---

# AgDR-0057 — Content-addressed estate tree-set certification in `session-complete` and SHA-cached deploy gates

## Y-statement

> In the context of **`just deploy` and `just deploy-all` (`T503`) executing `97` offline suite invocations (`2,105` checks across `_deploy-preflight`, `check-guardrails`, and `just test`, taking `~8.5 min` per deploy) while `just session-complete` (`T640`) only ran `10` lightweight governance gates before pushing to `origin/beta`**, facing **both slow operator deploy turnaround (including running all `16` `prepush` suites and `check-infisical` twice per deploy) and late discovery of `vitest` / `py-typecheck` regressions only after Touch ID confirmation**, we decided **to certify the complete 10-repo estate commit set (`release.estate_repos`) inside `just session-complete` (and `just certify`) via `scripts/deploy_cert.py`, store a content-addressed SHA-256 certificate in `~/.cache/w0m/deploy-cert/<tree_set_digest>.json` keyed over every repo `HEAD` SHA plus `w0m-web/project/test-suites.json`, skip redundant offline `prepush` / `check-guardrails` / `test` re-execution in `<0.2s` during `deploy` / `deploy-all` when the clean tree-set matches its certificate while keeping `state-check`, `check-warp`, `check-infisical`, `_assert-provisioned`, and `smoke-live` live on every deploy, and deduplicate `--prepush` via `--skip-prepush` on uncached runs** to achieve **shift-left runtime verification before `origin/beta` landing and `~8.5 min -> ~5s` pre-ship gate latency on certified commits**, accepting **that `session-complete` runs the full `offline/medium` + `check-guardrails` suite once per landed commit set (and re-certifies if `land` rebases onto a concurrent push)**.

## Context

Measured on `2026-11-05` from `deploy-logs/run-2026.11.05-1793910586.log`, `justfile`, `scripts/run_suites.py`, and `scripts/session_complete.py`:

- **Duplicate and heavy pre-deploy execution (`~8.5 min` before `db-migrate` or Worker builds start)**:
  1. `_deploy-preflight` ran `scripts/run_suites.py --prepush` (`16` suites, `432` checks) before `_confirm`, and `just test` (`scripts/run_suites.py --tier offline --level medium`, `81` suites, `1,673` checks) immediately re-ran all `16` `prepush` suites a second time inside `_deploy-gates`.
  2. `_deploy-all-chain` invoked `check-infisical` directly and a second time via `_deploy-gates: check-infisical check-guardrails test`.
  3. `~55` of the `81` `offline/medium` suites are static markdown, ticket-schema, and policy ratchets that cannot change behavior on an immutable git commit set once certified, while `vitest` (`380+` test files) competed with 80 concurrent subprocesses during the operator's interactive Touch ID session.
- **Late regression discovery (`T649`)**: Because `session_complete.py` (`T640`) ran only `10` governance gates (`session_wrapup.verification_gates`), a stale app name in `lighthouse-funnel-hygiene.test.ts` (`vitest`) and an un-narrowed dict in `tool_usage_probe.py` (`py-typecheck`) landed on `origin/beta` undetected and only failed when the owner ran `just deploy-all`.
- **Existing estate precedent (`T375`)**: `scripts/prepush_runner.py` already proved commit-bound SHA checkpointing under `~/.cache/w0m/prepush/` for single-repo `pre-push` hooks, cutting repeat pushes to `<1s`. Extending that pattern to the **10-repo estate tree-set** (`release.estate_repos`) covers detached `~/.w0m/releases/<version>/w0m` worktrees cut by `scripts/release.py`.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Option A: Tree-set SHA certification in `session-complete` + cached deploy verification (`scripts/deploy_cert.py`) + `--skip-prepush` on uncached runs** | Catches `vitest` / `py-typecheck` / `deno` failures *before* code lands on `origin/beta`; cuts certified `deploy-all` pre-ship gate time from `~8.5 min` to `~5s`; preserves `T503` order (`test_deploy_chain_order.py`) and full uncached fallback on manual commits or `W0M_DEPLOY_CERT_RESET=1` | `session-complete` runs `check-guardrails` + `offline/medium` once before landing (in the agent background rather than blocking the human at Touch ID) | **Chosen (Owner decision 2026-11-05)** |
| **Option B: Uncached runtime-only `_deploy-gates` (drop governance lints from deploy)** | Cuts deploy gates to `~2.5 min` without a cache | Still blocks the human operator for `~2.5 min` on every deploy and leaves `vitest` / `py-typecheck` out of `session-complete` unless duplicated | **Rejected** |
| **Option C: Deduplicate `--prepush` and `check-infisical` only** | Minimal diff | Still takes `~6.5 min` of operator wait time on every `deploy-all` | **Rejected** |

## Decision

1. **Multi-repo content-addressed tree-set digest (`scripts/deploy_cert.py`)**:
   - A certification key (`tree_set_digest`, SHA-256) is computed over:
     1. Every estate repository returned by `release.estate_repos(root)` (`.`, `w0m-api`, `w0m-ava`, `w0m-cf`, `w0m-clips`, `w0m-ext`, `w0m-mlx/w0m-mlx`, `w0m-sec`, `w0m-skills`, `w0m-web`) mapped to its exact `HEAD` commit SHA.
     2. `policy_digest` (SHA-256 over `w0m-web/project/test-suites.json` + certified stage schema version).
   - **Fail-closed cleanliness invariant (`AgDR-0025`)**: If *any* repo in `estate_repos(root)` has modified or staged tracked files (`git status --porcelain --untracked-files=no`), certification write is refused and cache lookup always returns `MISS (dirty_tree)`.
2. **Shift-left certification in `session-complete` (`scripts/session_complete.py`) & `just certify`**:
   - After `commit_dirty_repos` and before `agent_tree.py land`, `session_complete.py` runs `deploy_cert.py certify` (`check-guardrails` + `run_suites.py --tier offline --level medium`). Any failure aborts `session-complete` before pushing to `origin/beta`.
   - After `land_and_cleanup_tree` fast-forwards `canonical_root` to `origin/beta`, if a concurrent push caused `agent_tree.py land` to rebase (changing the landed `tree_set_digest`) and `canonical_root` is clean, `session_complete.py` certifies the rebased `canonical_root` commit set automatically.
3. **Deploy chain integration (`justfile`, `scripts/run_suites.py`)**:
   - Inside a deploy (`W0M_DEPLOY_LOGGED=1`, `W0M_RELEASE_WORKTREE=1`, or `W0M_USE_DEPLOY_CERT=1`), `_deploy-preflight`, `check-guardrails`, and `test` check `deploy_cert.py`:
     - On a verified `HIT`, offline gates return `0` in `<0.2s` while `just state-check`, `just check-warp`, `just check-infisical`, `_assert-provisioned`, and `just smoke-live` always execute live.
     - On a `MISS` (manual commit outside `session-complete`, `deploy-local` with dirty files, or `W0M_DEPLOY_CERT_RESET=1`), `_deploy-preflight` runs `run_suites.py --prepush`, `check-guardrails` runs full secret/credential scans, `test` runs `run_suites.py --tier offline --level medium --skip-prepush` (avoiding re-running the `16` `prepush` suites), and a clean passing run writes `~/.cache/w0m/deploy-cert/<tree_set_digest>.json`.
   - Standalone `just test` and `just check-guardrails` invoked directly outside a deploy always run uncached so interactive test invocations never surprise a developer.

## Consequences

- **Positive**:
  - Certified `just deploy` / `just deploy-all` runs reach Touch ID in `~2s` (`state-check`) and begin `db-migrate` / Worker builds `~3s` after confirmation (`check-warp` + single `check-infisical`), eliminating `~8.5 min` of redundant waiting.
  - Broken `vitest`, `py-typecheck`, `deno-check`, or `cf-typecheck` suites are caught inside `just session-complete` before landing on `origin/beta`.
  - Uncached deploys never execute `--prepush` or `check-infisical` twice.
- **Negative / Trade-offs**:
  - `just session-complete` takes longer (~3–5 min when uncached) because it executes `check-guardrails` + `offline/medium` before landing; this runs unattended in the agent's background turn rather than during the human's interactive Touch ID session.
  - Certificates live in host-local `~/.cache/w0m/deploy-cert/`; deploying from a second machine that did not run `session-complete` (or `just certify`) falls back safely to one uncached gate run and caches the certificate locally.

## What this does NOT decide

- Does not weaken or reorder `T503`: every gate still precedes `db-migrate` and `_deploy-ship` in `just --dump` (`scripts/tests/test_deploy_chain_order.py`).
- Does not cache live environment checks (`check-warp`, `check-infisical`, `state-check`, `_assert-provisioned`, `db-migrate`, `smoke-live`), which always measure live state at deploy time.
