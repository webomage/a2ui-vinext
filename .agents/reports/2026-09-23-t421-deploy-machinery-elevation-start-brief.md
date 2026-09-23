# T421 Start Brief: Elevate Deployment Machinery, Scripts, Recipes, and Logs to Workspace Root (Phase 4)

**Ticket:** [T421](file:///Users/proto/Projects/@self/@wom/.tasks/T421.md) (`status: queued` → transitioning to `in-progress`)  
**GitHub Issue:** [#421](https://github.com/webomage/wom7board/issues/421)  
**Epic:** [[ROADMAP]] §13.6 — `platform-operations`  
**Date:** 2026-09-23  

---

## 1. Verified Current State vs Claims

Mechanically verified via `just ticket-audit T421`, `just preflight --fast`, and estate-wide code inspection:
- **Git & Remotes:** All 8 repos (`@wom`, `wom7web`, `wom7api`, `wom7func`, `wom7skills`, `wom7ext`, `wom7sec`, `wom7mlx`) are 100% clean and up-to-date with `origin/beta`.
- **Preflight:** Fast preflight passes clean (12/12 tools on PATH, graph current, 7 repos clean, 0 uncommitted).
- **Tracking Parity:** 4/4 tracking surfaces agree (`.tasks/T421.md`, `TASKS.md`, `project/tickets/T421.md`, GitHub #421).
- **Current Deployment Machinery Location:**
  - Deployment helper scripts (`log_deploy.sh`, `dump_deploy_log.sh`, `check_cf_deployment.py`) are located in `wom7api/scripts/`.
  - Deployment execution logs are stored in `wom7api/deploy-logs/` (with active logs from Sept 2026 and rotated monthly archive `2026-08/`).
  - Deployment recipes (`deploy`, `deploy-all`, `deploy-web`, `deploy-cp`, `deploy-join`, `deploy-job`, `deploy-demo`, `deploy-workers`, `deploy-functions`, `_deploy-chain`, `_log-deploy`, `_confirm`, `changelog`) are defined in `wom7api/justfile`.
  - `wom7web/justfile` is a symlink pointing to `../wom7api/justfile`.
  - `@wom/justfile` contains only a delegation stub `sdlc-deploy: @just --justfile wom7web/justfile sdlc-deploy {{ args }}`; calling `just deploy` or `just deploy-web` at root fails with `error: justfile does not contain recipe deploy`.
  - `.w0m/sdlc.json` points `deploy_logs.dir` to `"wom7api/deploy-logs"` and `versioning.producer.declared_at` to `"wom7api/justfile"`.

---

## 2. Acceptance Criteria Status

| AC | Description | Status | Evidence / Gap |
|---|---|---|---|
| **AC1** | Elevate Deployment Scripts to `@wom/scripts/` | ⚪ Not started | `log_deploy.sh`, `dump_deploy_log.sh`, `check_cf_deployment.py` still in `wom7api/scripts/`. |
| **AC2** | Centralize Deployment Logs to `@wom/deploy-logs/` | ⚪ Not started | Logs still in `wom7api/deploy-logs/`. `.w0m/sdlc.json` points to `wom7api/deploy-logs`. |
| **AC3** | Elevate Core Deploy Recipes to Root `justfile` | ⚪ Not started | Root `justfile` lacks `deploy`, `deploy-web`, etc. Recipes still reside in `wom7api/justfile`. |
| **AC4** | Update Deployment Confirmation Gate & Documentation | ⚪ Not started | `_confirm` gate needs to run at estate root; `docs/DEPLOY-CONFIRM.md` references `wom7api/justfile`. |
| **AC5** | Clean Cutover in `wom7api` and `wom7web` | ⚪ Not started | Zero-shim clean cutover required. `wom7api/justfile` must forward cleanly or defer to root without cycles. |
| **AC6** | Automated Verification and Regression Proof | ⚪ Not started | `scripts/tests/test_deploy_elevation.py` and `just deploy-elevation-test` to be created. |

---

## 3. Dependencies & Architectural Invariants

1. **AgDR-0025 (Clean Cutover & Zero Fallbacks):**
   - No backward-compatibility shims or shadow symlinks left in `wom7api/scripts/`.
   - All callers across the entire estate must be updated atomically to reference `@wom/scripts/` and `@wom/deploy-logs/`.
2. **Interactive TTY Confirmation Gate (T161 AC3, `docs/DEPLOY-CONFIRM.md`):**
   - Live deploy commands require an interactive human terminal (`/dev/tty`).
   - Agents must never execute live deployment commands directly (`just deploy`, `just deploy-all`).
   - The elevation to `@wom/justfile` must preserve the `_confirm` recipe and its TTY enforcement.
3. **Deploy In-Flight Protection (T267):**
   - `deploy_in_flight_check.py` monitors deploys relative to declared estate root (`.w0m/sdlc.json -> root`). Elevating to `@wom` remains fully protected.
4. **Release Version Standard (T131):**
   - Canonical format `YYYY.MM.DD-<unixtimestamp>` produced by `just version`.
   - `version_doctor.py` consumer verification must assert that all declared consumers in `.w0m/sdlc.json` exist and interpolate `deploy_version`.

---

## 4. Blast Radius Analysis

- **Files to Move / Centralize:**
  - `wom7api/scripts/log_deploy.sh` → `scripts/log_deploy.sh`
  - `wom7api/scripts/dump_deploy_log.sh` → `scripts/dump_deploy_log.sh`
  - `wom7api/scripts/check_cf_deployment.py` → `scripts/check_cf_deployment.py`
  - `wom7api/scripts/gen_changelog.py` → `scripts/gen_changelog.py` (referenced by `dump_deploy_log.sh`)
  - `wom7api/deploy-logs/` → `deploy-logs/` (at estate root)
- **Files to Update:**
  - `justfile` (root `@wom/justfile`): add `deploy`, `deploy-all`, `deploy-web`, `deploy-cp`, `deploy-join`, `deploy-job`, `deploy-demo`, `deploy-workers`, `deploy-functions`, `_deploy-chain`, `_log-deploy`, `_confirm`, `changelog`, `deploy-elevation-test`.
  - `wom7api/justfile`: update or forward recipes to root `justfile` cleanly.
  - `wom7web/project/scripts/deploy_logged.py`: update default `LOGS` directory and execution cwd to estate root.
  - `wom7web/project/scripts/deploy_logs_rotate.py`: ensure root directory resolution via `.w0m/sdlc.json`.
  - `wom7web/project/scripts/version_doctor.py`: update consumer recipe lookup to check `@wom/justfile`.
  - `wom7web/project/scripts/changelog_drift.py`: update `LOGDIR = ROOT / "deploy-logs"`.
  - `.w0m/sdlc.json`: update `deploy_logs.dir` to `"deploy-logs"`, update `versioning.producer.declared_at` to root `justfile`.
  - `.gitignore` (in `@wom` and `wom7api`): ensure root ignores `deploy-logs/*.log` (keeping bucket structure and `.gitkeep`).
  - `docs/DEPLOY-CONFIRM.md`: update references from `wom7api/justfile` to `@wom/justfile`.
- **New Files:**
  - `scripts/tests/test_deploy_elevation.py`

---

## 5. Risks & Mitigations

- **Risk 1: `version_doctor.py` checking `wom7api/justfile`:**
  - *Mitigation:* Update `version_doctor.py` to inspect root `justfile` for declared consumers (`deploy-web`, `deploy-workers`, etc.), and run `test_version_doctor.py` to confirm 24/24 pass.
- **Risk 2: `deploy_logged.py` subprocess execution context:**
  - *Mitigation:* In root elevation, recipes run with root working directory. Update `deploy_logged.py` cwd default from `API` to `ROOT`. Run `test_deploy_logged.py` to verify full probe suite passes.
- **Risk 3: `deploy-in-flight` hook breaking:**
  - *Mitigation:* `deploy_in_flight_check.py` checks `is_relative_to(root)`. Since root contains `@wom`, runs from `@wom` are inside the estate. Verify with `test_deploy_in_flight.py`.

---

## 6. Recommended Next Gate

- **Next Gate:** `w0m-sdlc-spec`  
- Author OpenSpec proposal, tasks, and delta spec at `openspec/changes/2026-09-23-deploy-machinery-root-elevation/`.
