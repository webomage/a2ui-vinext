# Orca Performance, Theme Enforcement, 22-Branch Overlay (`v1.4.251-w0m.2`), CLI Repair & Obsidian Survivability Audit

**Date:** 2026-11-05  
**Ticket:** `T653`  
**Fork / Overlay Feed:** `webomage/orca` (`beta`, release `v1.4.251-w0m.2` tracking `stablyai/orca@v1.4.251`)

---

## 1. Executive Summary

1. **Terminal & Native Chat Scroll/Redraw Churn Fixed + Bounded Warm Tab Caching Added:**
   - **Desktop (`perf/terminal-chat-redraw-and-tab-caching`, `fix/terminal-smooth-resize-and-replay`):** Suspended hidden/chat-covered xterm WebGL contexts and background PTY delivery when `NativeChatPaneCover` obscures a terminal; enabled cross-platform DEC `?2026` synchronized-output frame holding without stripping POSIX `?25h` cursor restores; coalesced non-echo foreground PTY writes per `requestAnimationFrame` and skipped redundant non-ConPTY DOM viewport double-refreshes under WebGL; paused hidden `useNativeChatPacedText` 60fps `rAF` loops; cold-parked inactive `StructuredAgentSessionPaneOverlayLayer` tabs; bounded warm terminal tab retention (`maxHotPanes = 4`); gated `createReattachGridPush` `SIGWINCH` on real grid deltas; stopped settled `foreground-grid-drift-probe` polling; floated `SessionRestoredBanner` without layout row shifts; scoped `RetainedPaneHost` fit events; and dynamically extended `pty-resize-repaint-hold` (`+80 ms` up to `450 ms`) across streaming rewrite bursts.
   - **Mobile (`perf/terminal-chat-redraw-and-tab-caching`, `fix/mobile-live-input-prompt-backload`, `feat/mobile-four-side-edge-arrows`):** Replaced unmount-on-tab-switch `512 KB` scrollback replay with a `3`-slot warm `TerminalWebView` LRU (`preserveScroll: true`), debounced transient height-only `SIGWINCH` refits (`180 ms`), prevented `readPromptBackload` from calling `flushNow()` mid-`?2026` synchronized frame, memoized `TerminalPaneView`, and `rAF`-throttled `useZoomStableViewport` scroll syncs.
2. **Light/Dark Theme Enforced End-to-End Across Agent Sessions (`fix/mobile-terminal-theme-enforcement`):**
   - Replaced hardcoded dark `#0a0a0a` WebView and pre-hydration HTML backgrounds with theme-aware surfaces (`#ffffff` light / `#0a0a0a` dark), propagated resolved light/dark theme tokens to Desktop `TerminalPane`, `StructuredAgentSessionPaneOverlayLayer`, and Mobile `TerminalWebView` (`setTheme`), and implemented PTY `OSC 10` / `OSC 11` foreground/background responses plus `CSI ? 996 n` / DEC mode `2031` notifications so TUI coding agents (`claude`, `codex`, `gemini`, `opencode`) render in light or dark mode dynamically.
3. **100% Overlay Inclusion (`22/22` Active Branches, `0` Skipped) in `v1.4.251-w0m.2`:**
   - Reconciled all previously skipped/drifted branches (`feat/agent-collaboration-board`, `feat/mobile-camera-capture-chat`, `feat/mobile-live-input-password-mask`, `feat/macos-deep-link-worktree`, `feat/macos-deep-link-shortcuts`, `feat/zeroclaw-agent-connector`, `fix/mobile-landscape-safe-area-insets`, `feat/nested-subfolder-git-and-sdlc-repo`, `feat/mobile-session-tab-reorder`, `feat/cross-worktree-tab-move`, `feat/subagent-display-and-floating-category`) so `assemble-w0m-overlay.mjs` builds `22` active branches with `0` skipped and passes all 6 Orca gates (`tsrs` desktop & mobile, desktop & mobile i18n catalogs, `max-lines` ratchet, and mobile-web bundle verification).
4. **Durable Linux `orca` CLI Repair (`scripts/orca_overlay_update.py`):**
   - Root-caused `orca runtime mount not found under /tmp/.mount_orca-*`: a manual unmarked `/home/aleksei/.local/bin/orca` wrapper caused `installLinuxBareOrcaDispatcher` to bail out with `skipped-foreign` before extracting `~/.cache/orca/appimage/launcher/installed`, which in turn forced `~/.config/orca/linux-orca-cli-shim/orca` onto an ephemeral `/tmp/.mount_orca-*` FUSE fence. `orca_overlay_update.py` now extracts the AppImage runtime into Orca's native `generation-lease-v1` cache layout and repairs both `~/.local/bin/orca` (`# orca-serve-bare-orca-dispatcher`) and `~/.config/orca/linux-orca-cli-shim/orca`.
5. **Intelligent Obsidian Vault Survivability (`scripts/obsidian_vault_guard.py`):**
   - Live note-taking and `.obsidian/*.json` plugin/UI state inside `w0m-web` (`projects/w0m/vault/` and `docs/`) now coexist safely with `just deploy` and `just session-complete`: read-only AST comparison avoids `inotify` reload loops while Obsidian is open, `deploy_cert.py` isolates unstaged vault edits from committed `HEAD` certificates while failing closed on staged or non-vault dirty files, and `session_complete.py` 3-way merges `.obsidian/*.json` and Markdown notes across canonical fast-forwards.

---

## 2. Active `webomage/orca` Overlay Stack (`22` Branches + Updater)

| # | Branch (`webomage/orca`) | Stack Ref | Upstream PR Status | Ticket |
|---|---|---|---|---|
| 0 | `feat/w0m-overlay-updater-feed` | direct | Fork-only updater feed | `T619` |
| 1 | `feat/cross-worktree-tab-move` | direct (`6015e6edb4`) | Ready (`just pr-open`) | `T597` |
| 2 | `feat/agent-collaboration-board` | direct (`ef6a0db8c5`) | Ready (`just pr-open`) | `T593` |
| 3 | `feat/mobile-camera-capture-chat` | direct (`4350eec894`) | Ready (`just pr-open`) | `T557` |
| 4 | `feat/mobile-live-input-password-mask` | direct (`6188b444f3`) | Ready (`just pr-open`) | `T593` |
| 5 | `feat/obsidian-ofm-engine` | direct (`dafc52c461`) | Ready (`just pr-open`) | `T464` |
| 6 | `feat/macos-deep-link-worktree` | direct (`85b55c87ee`) | Open `stablyai/orca#422` | `T425` |
| 7 | `feat/macos-deep-link-shortcuts` | `overlay/*` (`c68122f93d`) | Open `stablyai/orca#423` | `T426` |
| 8 | `feat/zeroclaw-agent-connector` | `overlay/*` | Open `stablyai/orca#550` | `T502` |
| 9 | `fix/mobile-landscape-safe-area-insets` | direct (`471b47030c`) | Ready (`just pr-open`) | `T433` |
| 10 | `fix/mobile-markdown-external-tab-read` | direct (`d07c01a91b`) | Ready (`just pr-open`) | `T593` |
| 11 | `feat/nested-subfolder-git-and-sdlc-repo` | direct (`1bdee70e5b`) | Ready (`just pr-open`) | `T608` |
| 12 | `feat/mobile-session-tab-reorder` | direct (`c999076109`) | Ready (`just pr-open`) | `T608` |
| 13 | `fix/linux-cli-stale-appimage-and-dispatcher` | direct (`7efd78152a`) | Ready (`just pr-open`) | `T618` |
| 14 | `feat/mobile-terminal-double-tap-ctrl-c` | direct | Ready (`just pr-open`) | `T621` |
| 15 | `feat/mobile-terminal-triple-tap-enter` | `overlay/*` | Ready (`just pr-open`) | `T621` |
| 16 | `feat/mobile-terminal-4-tap-alt-m` | `overlay/*` | Ready (`just pr-open`) | `T635` |
| 17 | `feat/mobile-four-side-edge-arrows` | `overlay/*` | Ready (`just pr-open`) | `T635` / `T646` |
| 18 | `fix/terminal-smooth-resize-and-replay` | direct (`67b51345e9`) | Ready (`just pr-open`) | `T635` / `T653` |
| 19 | `fix/mobile-terminal-theme-enforcement` | direct (`fca701fafc`) | Ready (`just pr-open`) | `T641` / `T653` |
| 20 | `perf/terminal-chat-redraw-and-tab-caching` | `overlay/*` | Ready (`just pr-open`) | `T653` |
| 21 | `fix/mobile-live-input-prompt-backload` | direct (`9f8a46b1aa`) | Ready (`just pr-open`) | `T621` / `T653` |
| 22 | `feat/subagent-display-and-floating-category` | direct (`01a571be9d`) | Ready (`just pr-open`) | `T621` / `T653` |
| 23 | `feat/system-and-docker-monitors` | direct (`de4ddf07e9`) | Ready (`just pr-open`) | `T638` |

> **Note on retired `fix/mobile-landscape-horizontal-safe-area` (`PR #37034`):** Intentionally excluded from the overlay and marked obsolete because upstream `SideSafeArea` already applies horizontal insets on session/files tabs; stacking `#37034` double-padded landscape terminals, whereas `fix/mobile-landscape-safe-area-insets` (`471b47030c`) targets `MobileHomeScreen` cleanly.

---

## 3. Operator Commands

Apply or check the Orca overlay build and repaired local CLI:

```bash
cd ~/Projects/'!self'/w0m
just orca-apply
just orca-status
```

Inspect or heal Obsidian vault state at any time:

```bash
cd ~/Projects/'!self'/w0m
just vault-guard status
```

Open prepared upstream PRs to `stablyai/orca` selectively when desired:

```bash
cd ~/Projects/'!self'/w0m
just pr-open terminal-chat-redraw
just pr-open smooth-resize
just pr-open terminal-theme-enforcement
just pr-open prompt-backload
```
