# T635 — Orca Mobile 4-Side Edge Arrows, 4-Tap `Alt+M`, Smooth `SIGWINCH`/`?2026` Resize Repaint Hold, and `overlay/*` Stacking (`v1.4.249-w0m.2`)

- **Ticket:** `T635`
- **Date:** `2026-11-04`
- **Agent:** `agy:t633-orca-edge-arrows-quad-tap`

## 1. Summary & Build-Quota Batching

To conserve GitHub Actions build minutes on `webomage/orca`:
1. Removed the `cron: '17 */6 * * *'` recurring schedule from `.github/workflows/w0m-overlay-release.yml` so `w0m Overlay Release` runs strictly on explicit `workflow_dispatch` (`just orca-release`).
2. Batched **all four** requested mobile & desktop UX branches into a **single** locally-assembled, locally-verified release **`webomage/orca@v1.4.249-w0m.2`** (`14` branches included onto `stablyai/orca@v1.4.248` / `b32f6b03801`):
   - `feat/mobile-four-side-edge-arrows` (`c5e4cc07d4a`, adapted via `overlay/feat/mobile-four-side-edge-arrows` @ `30fae197b0b`)
   - `feat/mobile-terminal-4-tap-alt-m` (`6be57d417c2`, adapted via `overlay/feat/mobile-terminal-4-tap-alt-m` @ `b6c64bf0430`)
   - `fix/terminal-smooth-resize-and-replay` (`e1b4ebca0a3`)
   - `fix/mobile-live-input-prompt-backload` (`f329761390a`, adapted via `overlay/fix/mobile-live-input-prompt-backload` @ `a5f55152aa6`)

## 2. Shipped Capabilities

### A. 4-Side Screen-Edge Arrow Navigation (`feat/mobile-four-side-edge-arrows`)
- Restores sticky 4-side screen-edge navigation controls (`Edge Pills`, `Edge Strips`, `Floating Orbs`, and `Off`) across mobile terminal, markdown, file-browser, diff, and chat panes (`ScreenEdgeNavigationOverlay.tsx`).
- Exposed in both **Settings → Terminal → Edge Navigation** (`EdgeNavigationSettingsSection.tsx` inside `TerminalShortcutSettings.tsx`) and the in-session **`•••` → Edge Navigation** quick sheet (`EdgeNavigationModeSheet.tsx`).

### B. Separate 4-Tap Terminal Gesture for `Alt+M` (`feat/mobile-terminal-4-tap-alt-m`)
- Adds independently persisted `quadTapAltMEnabled` (default `true`) and a dedicated **`4-tap for Alt+M`** toggle under **Settings → Terminal → Gestures** alongside **`Triple-tap for Enter`**.
- Detects 4 single-finger non-link terminal taps (`<= 400ms`, `<= 45px`) in `mobile/src/terminal/document/surface-tap.ts` and dispatches `Alt+M` (`\x1bm`) via `handleAccessoryKey({ bytes: '\u001bm' }, handle)` (`use-mobile-session-terminal-quad-tap.ts`).
- **Stacked 3-tap vs 4-tap disambiguation (`overlay/feat/mobile-terminal-4-tap-alt-m`)**: When *both* `tripleTapEnterEnabled` and `quadTapAltMEnabled` are enabled, tap `#3` settles for `280ms` (`QUAD_TAP_SETTLE_MS`) before emitting `terminal-triple-tap` (`Enter`); if tap `#4` lands within that window, `cancelPendingTripleTap()` cancels the pending `Enter` timer and emits `terminal-quad-tap` (`Alt+M`) immediately.

### C. Smooth Terminal Resize & `?2026` Repaint Hold (`fix/terminal-smooth-resize-and-replay`)
- **Root cause**: CLI agents (`claude`, `codex`, `agy`) run inside xterm's **normal scrollback buffer** (`!alternate`). When a desktop split-pane/window resize or mobile orientation/keyboard reflow triggers `SIGWINCH`, or when a TUI emits a multi-chunk DEC mode `2026` synchronized frame (`\x1b[?2026h...\x1b[?2026l`), chunk-by-chunk xterm writes cause a visible top-to-bottom long-scrolling waterfall.
- **Desktop fix (`src/renderer/src/components/terminal-pane/pty-connection/pty-resize-repaint-hold.ts`)**: Holds `.xterm-screen` opacity during post-`SIGWINCH` (`160ms` initial / `90ms` quiet settle, `420ms` max) and `\x1b[?2026h...\x1b[?2026l` (`180ms` max) normal-buffer bursts, releasing cleanly on xterm's parsed write callback.
- **Mobile fix (`mobile/src/terminal/terminal-write-coalescer.ts` + `mobile/src/terminal/document/resize-repaint-hold.ts`)**: Extends `TerminalWriteCoalescer` with `noteResize()` (`48ms` batching across a `260ms` window) and `?2026` frame holding (`160ms` safety cap with monotonic `performance.now()` deadlines and `syncFrameOpen` reset on flush) plus matching WebView surface hold (`resize-repaint-hold.ts`).

### D. `origin/overlay/<branch>` Inter-Branch Adaptation (`assemble-w0m-overlay.mjs`)
- Keeps every upstream PR branch (`feat/mobile-terminal-triple-tap-enter`, `feat/mobile-terminal-4-tap-alt-m`, `feat/mobile-four-side-edge-arrows`, `fix/terminal-smooth-resize-and-replay`, `fix/mobile-live-input-prompt-backload`) pure and single-concern off `upstream/main` (`b32f6b03801`).
- When cherry-picking a pure branch onto earlier stacked overlay branches conflicts, `assemble-w0m-overlay.mjs` automatically falls back to `origin/overlay/<branch>` and records `overlaySha` in `<!-- w0m-overlay-manifest: ... -->`.
- Registered all 3 new `T635` proposals in `scripts/w0m_prs.py` (`26` total contribution proposals) while ignoring internal `overlay/*` refs during fork branch discovery.

## 3. Verification

- **Local Overlay Assembly (`14` branches onto `v1.4.248` / `b32f6b03801`)**: `assemble-w0m-overlay.mjs --mode plan` & `--mode assemble` succeeded cleanly (`14` included, `0` `T635` skips), `node --test config/scripts/assemble-w0m-overlay.test.mjs` (`2/2` pass).
- **Mobile Localization & OTA Web Bundle**: `verify-mobile-localization.mjs` (`4,041` call sites, `3,648` English entries), `build-mobile-web-app-bundle.mjs` + `verify-mobile-web-app-bundle.mjs` (`17` routes, `184` assets, reproducible `buildId`).
- **Typecheck, Lint & Unit Suites**: `tsconfig.build.cli.json` (`0` errors), targeted Desktop `tsconfig.web.json` (`0` errors), `oxlint` (`24` touched files, `0` warnings/errors), Desktop Vitest (`8/8` tests passed), Mobile Vitest (`150/150` tests across `13` stacked files passed), `test_w0m_prs.py` (`91/91` passed), `test_orca_overlay_update.py` (`5/5` passed).
- **Single GitHub Actions Release Build (`#41789733171`)**: Dispatched once after full local verification; `plan` (`1m20s`) + `build-linux` (`5m44s`) succeeded on the first shot and published [`webomage/orca@v1.4.249-w0m.2`](https://github.com/webomage/orca/releases/tag/v1.4.249-w0m.2).
