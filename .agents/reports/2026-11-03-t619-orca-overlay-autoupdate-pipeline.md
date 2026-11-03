# T619 — Self-Healing Fork Overlay Auto-Update Feed (`webomage/orca`)

- **Ticket:** `T619`
- **Date:** `2026-11-03`
- **Agent:** `agy:t619-orca-overlay-autoupdate`
- **Fork Repository:** <https://github.com/webomage/orca> (`default_branch: beta`)

## 1. Problem & Architectural Choice (Option A)

Running custom `w0m` branches on desktop AppImage apps like `stablyai/orca` (`~/Apps/orca-linux.AppImage`) normally creates a binary choice:
1. Keep stock auto-updates from `stablyai/orca` and lose unmerged `w0m` fixes (`fix/linux-cli-stale-appimage-and-dispatcher`, `fix/webgl-atlas-version-desync-recovery`, etc.) on every update; or
2. Freeze onto a local custom build and lose upstream releases (nor can this `HP` `AMD A10-5745M` / `5.0 GiB` RAM host comfortably compile Electron AppImages locally).

**Option A (`Self-Healing Fork Overlay Auto-Update Feed`)** solves both without local compilation:
- GitHub Actions on `webomage/orca` (`w0m-overlay-release.yml`) checks `stablyai/orca/releases/latest` every 6 hours (`17 */6 * * *`) and on `workflow_dispatch`.
- `assemble-w0m-overlay.mjs` starts from the latest upstream stable release (advancing to `upstream/main` when active overlay branches have already rebased onto newer `upstream/main` lineage), auto-retires any `w0m` branch already merged upstream (via both `git cherry` patch-ID equivalence and `stablyai/orca` merged PR metadata), cherry-picks all cleanly applying `w0m` branches, and skips/reports any conflicting branch without failing the release.
- Packaging runs on GitHub-hosted Linux runners with `ORCA_RELEASE_REPO=webomage/orca` baked in, emitting `orca-linux.AppImage` + `latest-linux.yml` under tag `vX.Y.(Z+1)-w0m.N` (`prerelease: false`, `--latest`).
- After a one-time local cutover via `~/.local/bin/orca-overlay-update --apply --wait`, Orca's native `electron-updater` `GenericProvider` automatically downloads and applies every subsequent `webomage/orca` overlay release in-app.

## 2. Monotonic SemVer & Channel Invariants

Because `semver.gt('1.4.247-w0m.1', '1.4.247') === false`, stamping `-w0m.N` on `Z` would fail to upgrade an existing `1.4.247` install. Instead, `assemble-w0m-overlay.mjs` stamps **`X.Y.(Z+1)-w0m.N`** on top of upstream `vX.Y.Z`:

| Current Version | Next Candidate | `semver.gt(next, current)` | Outcome |
| :--- | :--- | :--- | :--- |
| `1.4.247` (stock) | `1.4.248-w0m.1` | `true` | Upgrades cleanly onto overlay track |
| `1.4.248-w0m.1` | `1.4.248-w0m.2` | `true` | Same upstream tag + updated `w0m` branch SHA |
| `1.4.248-w0m.2` | `1.4.248` | `true` | Clean exit back to stock `1.4.248` once all `w0m` PRs merge |
| `1.4.248-w0m.2` | `1.4.249-w0m.1` | `true` | Next upstream `v1.4.248` + remaining `w0m` branches |
| `1.4.248-w0m.1` | `1.4.248-rc.1` | Ignored | `isOverlayVersion()` classifies `-w0m.N` on `'stable'`, never `'rc'` |

## 3. Delivered Components & Verification

### A. Runtime Configurable Release Feed (`webomage/orca:feat/w0m-overlay-updater-feed` @ `761f4ee6cdc`)
- Declared build-time `ORCA_RELEASE_REPO` in `src/types/build-constants.d.ts` and `electron.vite.config.ts` (`main` + `renderer`).
- Added `getMainReleaseRepo()` and `isOverlayVersion()` in `src/shared/release-channel.ts`, routing `stable`/`rc` feed URLs across `updater-release-readiness.ts`, `updater-prerelease-feed.ts`, `updater-release-feed.ts`, `updater-setup.ts`, and `config/electron-builder.config.cjs`.
- **Verification:** `93/93` Vitest assertions passing (`updater-overlay-feed.test.ts`, `release-channel.test.ts`, `updater-prerelease-feed.test.ts`, `updater-release-builds.test.ts`) and `oxlint` `0 warnings, 0 errors`.

### B. Self-Healing Overlay Controller & CI Workflow (`webomage/orca:beta` @ `2a5127ef32c`)
- Added `config/w0m-overlay-branches.json` (14 `w0m` branches + `updaterBranch`), `config/scripts/assemble-w0m-overlay.mjs`, `config/scripts/assemble-w0m-overlay.test.mjs`, and `.github/workflows/w0m-overlay-release.yml`.
- **Verification:**
  - `node --test config/scripts/assemble-w0m-overlay.test.mjs`: `2/2` tests passing (including multi-commit hotfix tag lineage advancement and `git cherry` squash-merge retirement).
  - Live dry-run against `stablyai/orca@v1.4.247`: computed `version=1.4.248-w0m.1`, `shouldBuild=true`, cleanly included **8** `w0m` branches (`feat/w0m-overlay-updater-feed` + 8 feature/fix branches including both `T618` Linux CLI and WebGL atlas fixes), and cleanly skipped/reported 6 older branches awaiting rebase.
- Set `webomage/orca` `default_branch` to `beta` while keeping `main` 100% pure upstream, and disabled all 16 inherited `stablyai/orca` `schedule:` workflows so only `w0m-overlay-release.yml` runs on schedule.
- Excluded `feat/w0m-overlay-updater-feed` via `INTERNAL_OR_SUPERSEDED_BRANCHES` in `scripts/w0m_prs.py` (`89/89` checks passing in `scripts/tests/test_w0m_prs.py`).

### C. Local Bootstrap & Rollback Helper (`~/.local/bin/orca-overlay-update`)
- `--status`: Displays local AppImage size/CLI version, stock backup state, latest `stablyai/orca` tag, latest `webomage/orca` overlay release, and recent CI runs.
- `--trigger`: Dispatches `w0m-overlay-release.yml` on `webomage/orca` (`beta`).
- `--apply [--wait]`: Triggers/watches CI if needed, downloads `latest-linux.yml` + `orca-linux.AppImage`, verifies SHA-512 in Python against `latest-linux.yml`, backs up stock `~/Apps/orca-linux.AppImage.stock.bak`, and atomically swaps `~/Apps/orca-linux.AppImage`.
- `--restore-stock`: Restores `~/Apps/orca-linux.AppImage.stock.bak` to return to upstream `stablyai/orca` updates.

## 4. One-Time GitHub Org Activation Note

On `2026-10-24`, after inherited `stablyai/orca` cron workflows fired on the newly created `webomage/orca` fork, GitHub Actions was disabled for `webomage/orca` at the organization/repository policy level (`HTTP 422: Actions has been disabled for this repository`, which requires org-admin UI or `admin:org` token scope to re-enable). Now that all 16 inherited `stablyai/orca` cron workflows have been disabled on `webomage/orca`:
1. Allow `webomage/orca` once at <https://github.com/organizations/webomage/settings/actions> (or <https://github.com/webomage/orca/actions>).
2. Run `orca-overlay-update --apply --wait` to dispatch `v1.4.248-w0m.1`, wait for the Linux AppImage build, SHA-512 verify, and cut over `~/Apps/orca-linux.AppImage`.
