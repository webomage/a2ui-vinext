# T757 — OpenDesign Color, Contrast & Design-System Alignment Report

- **Ticket:** `T757`
- **Date:** 2026-11-16
- **Scope:** Align `@webomage/ui` tokens, WebGL starfield backgrounds, shared auth/navigation contrast, and `w0m-web/design-system/` (`od-design-system-project/v1`) across `apps/web`, `apps/cp`, and `apps/me`.

## Root Causes Resolved

1. **WebGL Canvas Seam (`#000000` vs `--slate-950` `#020617`):**
   - `apps/web/src/components/three/WarpScene.ts` and `apps/cp/src/components/three/WarpScene.ts` cleared the starfield with pure black `0x000000`, creating a horizontal seam directly below the `#020617` header.
   - Fixed by clearing both scenes with `0x020617` and lerping star tail vertices toward `--slate-950` RGB (`2/255, 6/255, 23/255`), plus softening the header hairline in `apps/web/src/components/Header.astro`.

2. **Portal (`[data-app="cp"]`) Action Contrast & Chat FAB Polarity:**
   - Calibrated `--brand-app` to Cobalt `#1668e3` with white `--primary-foreground` / `--text-on-brand` (`var(--white)`), `#60a5fa` `--link`, and matching `--focus-ring`.
   - Fixed `.btn-primary` in `apps/{web,cp}/src/styles/global.css` and `.chat-toggle-btn` foreground in `apps/{web,cp}/src/components/ChatApp.svelte` to consume `var(--primary-foreground)`.
   - Scoped `select-item.svelte` highlights onto neutral `muted` / `foreground` surfaces so `--accent` brand overrides no longer paint dropdown options flat blue.

3. **Talent Cloud (`[data-app="me"]`) Indigo/Purple Drift & Dimmed H1 Fade:**
   - Moved `[data-app="me"]` (`--brand-me`, `--brand-accent`) onto Sky `#38bdf8` (`--sky-400`) + Emerald `#34d399` (`--emerald-400`), aligned fallbacks (`56, 189, 248`) and `--brand-color` usage in `apps/me/src/components/JobBoard.svelte`, removed the `#fff -> #64748b` dimmed fade on the `JobBoard.svelte` hero H1, and removed legacy `indigo-*`/`purple-*`/`bg-black/*` classes across auth and `me`/`cp` pages.

4. **Auth Views & Visual Restraint (`AuthForm.astro` & `{login,forgot-password,reset-password}.astro`):**
   - Converted Google/LinkedIn/GitHub OAuth buttons in `packages/ui/src/lib/components/ui/AuthForm.astro` to dark-slate `variant="outline"` so `Sign In` remains the single high-contrast primary CTA per viewport.
   - Replaced asymmetric top-left blobs and gradient-clipped headings with centered ambient slate wash and solid crisp headings topped by a thin `var(--gradient-brand)` rule.

5. **OpenDesign `od-design-system-project/v1` Package Alignment (`w0m-web/design-system/`):**
   - Kept `w0m-web/design-system/tokens/*.css` in 100% parity with `packages/ui/src/tokens.css` (288 declarations, 193 canonical tokens).
   - Upgraded `w0m-web/design-system/` with OpenDesign-canonical `manifest.json` (`schemaVersion: "od-design-system-project/v1"`), schema-strict `tokens.css` (`TOKEN_SCHEMA`), `DESIGN.md`, `USAGE.md`, `components.html`, `components.manifest.json`, `design-tokens.json`, and `tailwind-v4.css`.

## Verified Visual Evidence (Post-Fix Chromium Captures)

Inspected all 11 refreshed captures in `verify_v2_*.png`:

| Surface | Desktop Capture | Mobile / Secondary Capture | Visual Result |
|---|---|---|---|
| `apps/web` | `verify_v2_web_home_desktop.png`, `verify_v2_web_solutions_desktop.png`, `verify_v2_web_login_desktop.png` | `verify_v2_web_audit_mobile.png` | Seamless `#020617` header-to-canvas blend, crisp Sky `#38bdf8` + dark slate ink on CTAs & Chat FAB, calm neutral OAuth stack. |
| `apps/me` | `verify_v2_me_home_desktop.png`, `verify_v2_me_board_desktop.png`, `verify_v2_me_assessments_desktop.png`, `verify_v2_me_login_desktop.png` | — | Unified Sky + Slate across sidebar, hero, Feature Voting Board, assessments empty state, and auth; crisp non-faded `"Find Your Next Remote Role"`. |
| `apps/cp` | `verify_v2_cp_login_desktop.png`, `verify_v2_cp_forgot_desktop.png` | `verify_v2_cp_login_mobile.png` | Calibrated Cobalt `#1668e3` + pure white `Sign In` / `Send Reset Link` / Chat FAB, readable `#60a5fa` links, zero horizontal overflow. |

## Verification Summary

- `validateDesignTokenOutputs`, `parseDesignSystemProjectManifest`, and `lintArtifact` against `w0m-web/design-system/`: `SELF_CHECK.ok = true` (`0` errors, `0` warnings), `56` OpenDesign token bindings, `0` undeclared refs, `0` lint findings.
- `just ds-diff` (`193` tokens synced), `just ds-bundle`, `just ds-conformance --enforce`, `just design-system-check` (`7` projects, `0` contract errors), `just ui-ticket-leak-check` (`481` files, `0` leaks).
- `pytest` design-system suite (`test_t92_t93_design_system.py`, `test_t496_job_join_ds.py`, `test_ds_conformance.py`, `test_tokens_parity.py`, `test_t183_design_system_sdlc.py`, `test_t42_ds_master_sync.py`): `23 passed`.
- `astro check`: `web` (`167` files, `0` errors/warnings/hints), `me` (`103` files, `0` errors/warnings/hints), `cp` (`271` files, `0` errors/warnings, `1` pre-existing hint on `apps/cp/src/pages/index.astro:33`).
- Vitest (`packages/ui/src apps/web/src/tests/`): `22` test files passed, `128` tests passed.
- `just mmd-validate`, `just debt-check --enforce`, `just check-guardrails`: passed.
