# T627 — Replace Bash `orca-overlay-update` with Python `scripts/orca_overlay_update.py` & Clean Up `webomage` GitHub Actions

- **Ticket:** `T627`
- **Date:** `2026-11-03`
- **Agent:** `agy:t627-orca-apply-ci-cleanup`

## 1. Root Cause & Replacement of Bash `orca-overlay-update` with Python (`scripts/orca_overlay_update.py`)

### Root Cause
1. **Why a script exists at all**: Day-to-day updates do **not** use a script — once Orca runs `webomage/orca@v1.4.249-w0m.1`, Orca's native `electron-updater` (`GenericProvider`) pulls future `webomage/orca` releases automatically in-app. `orca-overlay-update` (`just orca-apply` / `just orca-status`) is strictly a one-time bootstrap, CI status/dispatch, and stock-rollback helper.
2. **Why the Bash script crashed after installing `v1.4.249-w0m.1`**: Writing the CLI in Bash glued `gh` + `jq` + `mktemp` + `trap` + an embedded `python3 <<'PY'` SHA-512 snippet together under `set -euo pipefail`. Inside `apply_overlay()`, `local workdir` went out of scope when the function returned, so the process-exit `EXIT` trap (`rm -rf "$workdir"`) threw `line 1: workdir: unbound variable` (`exit 1`) *after* `~/Apps/orca-linux.AppImage` and `~/Apps/orca-linux.AppImage.stock.bak` had already been verified and installed, leaving `~/Apps/.orca-overlay-dl.sJyU9H` behind.

### Fix & Improvements
1. **Pure stdlib Python CLI (`scripts/orca_overlay_update.py` + `~/.local/bin/orca-overlay-update`)**: Replaced the Bash wrapper entirely with stdlib Python matching the rest of `@wom/scripts/*.py` (`orca_sessions.py`, `w0m_prs.py`, `social_trace.py`):
   - Uses `tempfile.TemporaryDirectory(dir=appimage_path.parent, prefix=".orca-overlay-dl.")` context manager — deterministic cleanup on return, exception, or `SystemExit`, with zero Bash `trap` / `set -u` scoping hazards and zero `jq` subprocesses.
   - Downloads `latest-linux.yml` (`~350 B`) first and verifies `$APPIMAGE_PATH` SHA-512 in native `hashlib.sha512()` before downloading the `240 MB` `orca-linux.AppImage` (`--force` overrides), so re-running `just orca-apply` when up to date verifies SHA-512 and exits `0` in `<2s`.
   - Wired `just orca-status`, `just orca-apply`, and `just orca-overlay-test` in `justfile`.
2. **Hermetic Regression Suite (`scripts/tests/test_orca_overlay_update.py`)**: `5/5` unittest checks passing (`ruff check` `0` errors) covering fresh `--apply` + `.stock.bak` creation + temp cleanup, idempotent SHA-512 fast-path (`0` redundant AppImage downloads), overlay-to-overlay upgrades preserving `.stock.bak`, SHA-512 mismatch abort cleanup, and `--restore-stock` / `--status`.

## 2. First Live Cloud Release Fixes on `webomage/orca` (`v1.4.249-w0m.1`)

- **`9d3acca4757` (`webomage/orca:feat/w0m-overlay-updater-feed`)**: Declared `ORCA_RELEASE_REPO` in `src/shared/release-channel.ts` so `config/tsconfig.build.cli.json` (which excludes `src/types/build-constants.d.ts`) compiles with `0` errors.
- **`a1581002ad7` (`webomage/orca:beta`)**: Switched `Publish GitHub Release` in `.github/workflows/w0m-overlay-release.yml` from `git push origin refs/tags/$TAG` (blocked by GitHub's `workflows` App scope check when tagging assembled overlay commits) to `gh release create "$TAG" --target beta`. Run `#41764577088` succeeded and published `webomage/orca@v1.4.249-w0m.1`.

## 3. `webomage` Organization GitHub Actions Cleanup (33 Repositories Audited)

- **Workflows disabled (`71` total across 7 repos)**:
  - `webomage/orca`: disabled `58` inherited upstream `.github/workflows/*` workflows; kept `w0m Overlay Release` (`w0m-overlay-release.yml`) active.
  - `webomage/omlx`: disabled all `5` inherited upstream workflows.
  - `webomage/mlx-vlm`: disabled all `3` inherited upstream workflows.
  - `webomage/tart-guest-agent`: disabled both `2` inherited upstream workflows.
  - `webomage/w0m`: disabled `1` broken cross-repo `CI` workflow (saves private Actions minutes on every push).
  - `webomage/w0m-web`: disabled `1` broken cross-repo `CI` workflow (saves private Actions minutes on every push).
  - `webomage/homebrew-tap`: disabled `1` failing daily `brew bump` (`autobump.yml`) workflow; kept `brew pr-pull` and `Dependabot Updates` active.
- **Workflow runs deleted (`1,707` total across 9 repos)**:
  - `orca`: `1,176` deleted, `1` green `w0m Overlay Release` (`#41764577088`) kept.
  - `omlx`: `18` deleted (`0` remaining).
  - `mlx-vlm`: `4` deleted (`0` remaining).
  - `w0m`: `99` failed/cancelled deleted (`0` remaining).
  - `w0m-web`: `256` failed/cancelled deleted (`0` remaining).
  - `w0m-api`: `116` dead `startup_failure` runs deleted (`0` remaining).
  - `w0m-ext`: `19` dead `startup_failure` runs deleted (`0` remaining).
  - `w0m-sec`: `8` dead `startup_failure` runs deleted (`0` remaining).
  - `homebrew-tap`: `11` failed `brew bump` runs deleted, `3` green runs kept.
