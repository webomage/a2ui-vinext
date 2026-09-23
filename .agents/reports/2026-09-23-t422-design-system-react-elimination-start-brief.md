# w0m SDLC Start Brief: T422 — Design System React Spec Elimination & Token SSOT Consolidation (Post-T420 Phase 2)

> **Ticket:** [T422](.tasks/T422.md)  
> **Title:** Design System React Spec Elimination & Token SSOT Consolidation (Post-T420 Phase 2)  
> **Gate:** `w0m-sdlc-start` (Orient / Explore / Ground)  
> **Author:** Antigravity / w0m Engineering  
> **Date:** 2026-09-23  
> **Status:** in-progress  

---

## 1. Verified State & Audit Summary

Mechanically verified via `just ticket-audit T422`, AST search, and token inspection across the estate:

- **Tracking Surface Coherence:** ✅ 4/4 agree (ticket file, board row, sync index, GitHub issue #422).
- **Post-T420 Foundation (Confirmed Shipped):**
  - Shipped `@webomage/ui/tokens.css` with 213 declarations, active in `apps/web` and `apps/cp`.
  - Tailwind v4 `@theme` includes 17 semantic colours + radii + fonts; shadcn utilities emit CSS in production bundles.
  - Zero hardcoded fallbacks remain (32 → 0).
  - All React implementation files (`.jsx`, `.dc.html`, templates) deleted (24 MB → 4.9 MB).
- **Surviving Gaps to Deliver in T422 (Phase 2 / Ticket A: P1–P3):**
  - **P1 (React in Spec Layer):** 53 occurrences across 38 files (21 `.prompt.md` files with ` ```jsx ` / `className`, and 17 `.d.ts` files with `ReactNode` / `JSX.Element`). Svelte authors are currently handed React specs.
  - **P2 (Token Divergence & SSOT):** `packages/ui/src/tokens.css` (203 tokens) and `design-system/tokens/*.css` (188 tokens) are hand-maintained. 16 legacy/segment tokens are in PKG only, and `--tracking-widest` (`.2em`) was dropped from PKG.
  - **P3 (T92 Unblocking):** `TARGET-COMPONENT-REGISTRY-2026-09-10.md` §2 points T92 to deleted `.jsx` files.

---

## 2. Acceptance Criteria Grounding & Implementation Plan

| AC | Requirement | Measured State | Implementation Plan |
|---|---|---|---|
| **AC1** | Purge React/JSX from 21 `.prompt.md` files | 21 files have ` ```jsx ` / `className` | Rewrite code fences to `svelte` / `astro`, use `@webomage/ui` imports, replace `className` with `class` |
| **AC2** | Purge React types from 17 `.d.ts` files | 17 files type `ReactNode` / `JSX.Element` | Replace with native TypeScript types matching Svelte 5 `$props()` interfaces (`Snippet`, `string`, `Record<string, unknown>`) |
| **AC3** | Consolidate Token SSOT & Restore Lost Tokens | `--tracking-widest` missing in PKG | Add `--tracking-widest: 0.2em` to `packages/ui/src/tokens.css`; ensure single SSOT alignment with `design-system/tokens/` |
| **AC4** | Token Parity & Drift Test Gate | No automated parity test today | Create `packages/ui/tests/tokens_parity.test.ts` or `scripts/tests/test_tokens_ssot.py` + `just tokens-parity-test` |
| **AC5** | Re-point T92 Target Component Registry | 7 target components point to deleted `.jsx` | Update `TARGET-COMPONENT-REGISTRY-2026-09-10.md` to reference `.prompt.md`, `.d.ts`, and live `.astro` implementations |
| **AC6** | Automated Regression Proof | No test suite | Implement `scripts/tests/test_design_system_react_free.py` verifying 0 React matches, valid registry paths, and token parity |

---

## 3. Dependencies & Blast Radius

- **Blocks:** [[T92]] (Port 7 brand/domain components into `@webomage/ui` as Svelte).
- **Precedents:** [[T420]] (Design system reconciliation, token wiring, React cleanup).
- **Subsystems Touched:**
  - `wom7web/design-system/components/` (spec layer only)
  - `wom7web/packages/ui/src/tokens.css` (token restoration)
  - `wom7web/design-system/TARGET-COMPONENT-REGISTRY-2026-09-10.md`
  - Workspace test scripts (`scripts/tests/`) and `justfile`

---

## 4. Routing to Next Gate

- Transition T422 status: `queued` → `in-progress`.
- Route to **`w0m-sdlc-spec`**: author OpenSpec change `2026-09-23-design-system-react-elimination-and-tokens-ssot`.
