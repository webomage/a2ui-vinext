# T638 — Orca Desktop & Mobile Built-In `*top` & Docker TUI Monitor Launcher (Staged on `webomage/orca`) + `HP` Monitor Tooling

- **Ticket:** `T638`
- **Date:** `2026-11-04`
- **Agent:** `agy:t638-orca-top-monitors`

## 1. Summary & GitHub Actions Build-Quota Discipline

Per the operator's GitHub Actions build-quota rule:
1. Implemented built-in **`*top` & Docker/container TUI auto-detection and one-click/one-tap launching** across Orca Desktop and Orca Mobile on pure upstream PR branch [`webomage/orca@feat/system-and-docker-monitors`](https://github.com/webomage/orca/tree/feat/system-and-docker-monitors) (`518a8c2d528190eb5001aea62d10c65c618df47f`).
2. Verified the full assembled overlay stack locally onto `stablyai/orca@v1.4.248` (`b32f6b03801`) — `feat/system-and-docker-monitors` stacked cleanly onto all `14` active overlay branches (`15` branches included, `0` conflicts, no `overlay/*` adaptation branch needed).
3. Staged the branch in `config/w0m-overlay-branches.json` on `webomage/orca:beta` (`006450d599fff67d1a25d133a08f2f7b4d93cb81`) **without dispatching `w0m-overlay-release.yml`** (`0` GitHub Actions minutes spent), ready to ride the next batched `just orca-release`.
4. Installed non-root `*top` and Docker TUI binaries on `HP` (`btop`, `lazydocker`, `ctop`, `ncdu`, `duf`) via Linuxbrew alongside existing `top`, `htop`, and `docker`.

## 2. Shipped Capabilities

### A. Shared Monitor Catalog (`src/shared/system-monitors.ts`)
- Curated **21** interactive terminal monitors across 5 categories, filtered by execution-host platform (`darwin`, `linux`, `win32`):
  - **System**: `btop`, `htop`, `bottom` (`btm`), `glances`, `atop`, `s-tui`, `gotop`, `vtop`, `top`
  - **Containers & Kubernetes**: `lazydocker`, `ctop`, `docker stats` (`docker-stats`, mapped to the `docker` binary), `oxker`, `podman stats` (`podman-stats`, mapped to `podman`), `k9s`
  - **GPU**: `nvtop`, `radeontop`, `asitop` (macOS), `macmon` (macOS)
  - **Disk**: `ncdu`, `duf`, `gdu`
  - **I/O & Network**: `iotop`, `iftop`, `nethogs`, `bandwhich`
- Provides curated fallback presets (`btop`, `htop`, `lazydocker`, `ctop`, `docker-stats`, `ncdu`, `top`) when Orca Mobile is paired to an older host runtime that predates `preflight.detectMonitors`.

### B. Zero-Subprocess Execution-Host Detection (`IPC` + `RPC`)
- **`src/main/preflight/system-monitor-detection.ts`**: Probes candidate binaries in parallel via `findFirstExecutableInPath` / `findFirstExecutableInWslPath` using Orca's cached login shell `$PATH` (zero child-process spawns on Linux/macOS/Windows local hosts; supports WSL distros when configured).
- **IPC & Preload (`preflight:detectMonitors`)**: Wired through `src/main/ipc/preflight.ts`, `src/preload/api/preflight-api.ts`, `src/preload/api/preflight-bridge.ts`, and `src/renderer/src/web/preload-api/web-host-capability-api.ts`.
- **Runtime RPC (`preflight.detectMonitors`)**: Registered in `src/main/runtime/rpc/methods/preflight.ts`, generated into `src/shared/rpc-contract/rpc-params-catalog.generated.ts`, and added to `EXECUTION_HOST_ROUTED_METHODS` in `src/main/runtime/runtime-rpc/runtime-rpc-mobile-method-routing.ts` so both paired Desktop remote environments and Orca Mobile probe the target execution host directly.

### C. Orca Desktop (`+ → Monitors` Submenu & `+` Search Omnibox)
- **`+` Dropdown (`TabBarSystemMonitorsSubmenu.tsx` + `tab-bar-static-create-menu.tsx`)**: Adds a **`Monitors`** submenu right below the terminal shell items, listing every detected monitor with its command badge and opening a named terminal tab (`launchSystemMonitorInNewTab`).
- **`+` Search Omnibox (`tab-create-menu-options.ts` + `TabBarCreateEntryRow.tsx`)**: Exposes searchable `Monitor: <Name>` entries matched by monitor name, binary command, category, keywords (`docker`, `containers`, `gpu`, `cpu`, `ram`, `disk`, `network`, `*top`), and description.

### D. Orca Mobile (`New Tab → Monitors (*top)` Sheet)
- **`MobileSystemMonitorsSheet.tsx` + `MobileSessionSheets.tsx`**: Adds a **`Monitors (*top)`** entry to the Mobile `New Tab` sheet, grouped by category (`System`, `Containers`, `GPU`, `Disk`, `I/O & Network`), launching a named terminal tab with `{ startupCommand: monitor.command, startupCommandDelivery: 'shell-ready' }` so login-shell / Linuxbrew `$PATH` initialization finishes before the TUI starts.
- **`mobile-system-monitors-loader.ts`**: Handles `preflight.detectMonitors` reads via `preflightDetectMonitorsRead` and falls back cleanly to curated presets if an older host returns `method_not_found` / `forbidden`.

### E. `HP` Workstation Monitor Tooling & Registry Sync
- Installed via Linuxbrew on `HP`: `btop` (`1.4.8`), `lazydocker` (`0.25.2`), `ctop` (`0.7.7`), `ncdu` (`2.9.2`), `duf` (`0.9.1`) alongside system `top`, `htop`, and `docker`.
- Documented root-level `apt-get` install command (`radeontop`, `iotop`, `nethogs` for the AMD Radeon HD 8650G APU and kernel I/O/network accounting).
- Registered `stablyai/orca:feat/system-and-docker-monitors` (`T638`) in `scripts/w0m_prs.py` (`27` proposals total).

## 3. Verification

- **Workstation Tooling (`HP`)**: `command -v top htop btop lazydocker ctop ncdu duf docker` (all present), `just tools-check` (`0 required-problem(s), 0 warn`).
- **Pure Branch (`518a8c2d528`)**:
  - `oxlint` across all `29` touched/created files: `0` warnings, `0` errors.
  - Typechecks: `tsrs` (`config/tsconfig.tc.web.json` `0` errors; `config/tsconfig.node.json` `0` errors in `T638` files), `mobile/tsconfig.json` (`0` errors), `config/tsconfig.build.cli.json` (`0` errors).
  - Ratchets: `generate-rpc-params-catalog.mjs --check`, `check-process-host-imports.mjs`, `check-main-sync-spawn-ratchet.mjs`, `check-compat-boundary-imports.mjs`, `verify-localization-catalogs.mjs`, `verify-mobile-localization.mjs` — all green.
  - Unit tests: Desktop/Main/Shared Vitest `9/9` files (`39/39` tests passed), Mobile Vitest `3/3` files (`8/8` tests passed).
- **Local Full-Stack Overlay Assembly (`15` included branches onto `v1.4.248` / `b32f6b03801`)**:
  - `assemble-w0m-overlay.mjs --mode assemble`: `feat/system-and-docker-monitors` merged cleanly with `0` conflicts (`2/2` `assemble-w0m-overlay.test.mjs` passed).
  - `build-mobile-web-app-bundle.mjs` + `verify-mobile-web-app-bundle.mjs`: `17` routes, `123` chunks, `184` assets, reproducible `buildId 2dc42279ab723a4f47c37a78f38125c9e796200a769f86f15d51898eea747a8b`.
  - Assembled `oxlint` (`0` warnings/errors) + Desktop/Mobile Vitest smoke (`5/5` files, `13/13` tests passed).
- **GitHub Actions Quota Check**: `gh run list -R webomage/orca --limit 3` confirmed **0** workflow runs triggered after pushing `feat/system-and-docker-monitors` (`518a8c2d528`) and `beta` (`006450d599f`).
- **PR Registry & Ticket Audit**: `python3 scripts/tests/test_w0m_prs.py` (`92/92` passed), `python3 scripts/ticket_audit.py T638 --strict --offline`.
