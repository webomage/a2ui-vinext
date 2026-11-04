# T621 — Orca Mobile & Desktop UX Enhancements (`webomage/orca`)

**Date:** 2026-11-03  
**Ticket:** [[T621]]  
**Agent:** `agy:t621-orca-mobile-desktop-ux`  
**Target Fork & Integration Branch:** `webomage/orca` (`beta` @ `c5e23497666`)

---

## 1. Deliverables Summary

| Branch (`webomage/orca`) | Commit SHA | Target Role | Verification |
| :--- | :--- | :--- | :--- |
| `feat/mobile-terminal-triple-tap-enter` | `85f3b0133b4` | Standalone upstream PR candidate to `stablyai/orca` (`T435` human-gated) + `beta` overlay | `79/79` mobile Vitest tests, `0` i18n drift, `0` `oxlint` warnings/errors |
| `fix/mobile-live-input-prompt-backload` | `f329761390a` | `webomage/orca:beta` overlay | `77/77` mobile Vitest tests, `0` `oxlint` warnings/errors |
| `feat/subagent-display-and-floating-category` | `a9861b32736` | `webomage/orca:beta` overlay | `100/100` desktop/runtime + `98/98` mobile Vitest tests, `17/17` CI ratchets, `0` i18n drift |
| `beta` | `c5e23497666` | Unified self-healing overlay branch (`17` registered branches in `config/w0m-overlay-branches.json`) | `28/28` post-merge desktop + mobile integration tests, GPG-signed (`G`) |

---

## 2. Architecture & Key Invariants

### 2.1 Mobile Terminal Triple-Tap Enter (`feat/mobile-terminal-triple-tap-enter`)
- **WebView Gesture State Machine (`mobile/src/terminal/document/touch-tap-selection.ts`)**: Extends `TouchTapSelection` to detect 3 consecutive taps within `300ms` and `24px` drift without delaying single-tap focus or double-tap word selection, cancelling word selection and posting `{ type: 'triple-tap' }` when `tripleTapEnter` is enabled.
- **Ordered Flush + Enter (`mobile/src/session/use-mobile-session-terminal-triple-tap.ts`)**: Calls `flushLiveInputBeforeSpecialKey(activeHandle)` before sending `\r` via `sendAccessoryTerminalBytes` so uncommitted Live Input prompt edits reach the PTY ahead of `Enter`, accompanied by `triggerLightImpact()`.
- **Settings Toggle (`mobile/src/settings/terminal-triple-tap-enter-preference.ts`)**: Default-enabled (`true`) SecureStore preference surfaced in `MobileTerminalSettingsSection.tsx`.

### 2.2 Mobile Live Input Active Prompt Backload (`fix/mobile-live-input-prompt-backload`)
- **Cursor-Line Prompt Extraction (`mobile/src/terminal/document/prompt-line-backload.ts`)**: Reads the wrapped xterm buffer line around `buffer.active.cursorY`, strips standard shell/TUI prompt prefixes (`$ `, `% `, `# `, `❯ `, `› `, `> `), and returns `{ text, cursorOffset }` while skipping alternate-screen TUIs (`buffer.active.type === 'alternate'`) and password/secret prompts.
- **Session Retention (`mobile/src/terminal/use-terminal-live-session-retention.ts`)**: Preserves per-handle Live Input buffer and cursor anchor across session tab switches and clears saved state cleanly on submit, mode toggle, or terminal clear; skips backload when password masking (`inputMasked`) is active on `beta`.

### 2.3 Subagent Display (`flat` Default + `tree`) & Floating Agents Category (`feat/subagent-display-and-floating-category`)
- **Subagent Display Preferences (`src/shared/constants.ts`, `ui-chrome-types.ts`)**: `showSubagents` defaults to `true` and `subagentDisplayMode` defaults to `'flat'` (`Alongside agents`) with `'tree'` (`Tree under parent`) selectable in both desktop (`worktree-card-option-items.tsx`) and mobile (`workspace-subagent-option-controls.tsx`) workspace view menus.
- **Subagent Indicator & Lineage Handling (`worktree-card-subagent-mode.ts`, `DashboardAgentRow.tsx`, `WorktreeAgentRow.tsx`)**: Renders `CornerDownRight` icon badge on subagent rows across compact/full desktop cards and mobile rows, and strips `entry.orchestration` on `rowSource === 'subagent'` in `'flat'` mode so `buildAgentRowLineageTree` promotes subagents alongside top-level agents.
- **Antigravity Subagent Roster (`src/shared/antigravity-subagent-roster.ts`, `antigravity-events.ts`)**: Tracks `invoke_subagent`, `manage_subagents`, and `send_message` lifecycle events into `subagents[]` on the parent Antigravity hook listener state.
- **Collapsible Floating Category (`floating-worktree-ps-summary.ts`, `FloatingWorkspaceSidebarSection.tsx`, `floating-workspace-section.ts`)**: Synthesizes a `workspaceKind: 'floating'` `RuntimeWorktreePsSummary` whenever `FLOATING_WORKTREE_ID` (`__floating__`) hosts live agents or terminals, rendering a collapsible **Floating** section on both desktop and mobile sidebars with direct pane navigation (`floatingWorkspaceSessionPath(hostId)`).

---

## 3. Upstream PR Submission (`T435` Human Confirmation Gate)

Per `T435`, external PR creation against `stablyai/orca` requires human confirmation:
- **Compare URL**: `https://github.com/stablyai/orca/compare/main...webomage:orca:feat/mobile-terminal-triple-tap-enter?expand=1`
- **CLI Submission Command**: `just prs-submit --branch feat/mobile-terminal-triple-tap-enter --no-dry-run`
