---
id: AgDR-0054
title: "Mobile-first multi-orientation responsive UI architecture (Mobile Portrait/Landscape, Tablet Vertical/Horizontal, and Well-Wrapped Desktop)"
timestamp: 2026-11-01T22:18:00-05:00
agent: antigravity
model: gemini-4-argon
trigger: owner-direction
status: accepted
superseded_by:
supersedes:
ticket: T603
---

# AgDR-0054 — Mobile-first multi-orientation responsive UI architecture (Mobile Portrait/Landscape, Tablet Vertical/Horizontal, and Well-Wrapped Desktop)

## Y-statement

> In the context of **authoring and maintaining UI surfaces across `@webomage/ui` (`w0m-web/packages/ui`), `w0m-web/design-system/`, and all four monorepo applications (`apps/web`, `apps/cp`, `apps/join`, `apps/job`) under [[T603]]**, facing **(1) desktop-first CSS rules in layout shells (`AppShell.svelte`) and marketing sections that required brittle `max-width` overrides, (2) tablet users rotating between vertical (`768×1024`) and horizontal (`1024×768`) orientations experiencing unexpected sidebar collapses or cramped vertical viewports, and (3) wide desktop screens (`1440px+`) stretching control-panel cards edge-to-edge without a well-wrapped container**, we decided **to declare `w0m` UI canonically Mobile-First (`0px–767px` base styles covering both portrait `375×812` and landscape `812×375`), with progressive `min-width` + `orientation` breakpoints for Tablet Vertical (`768×1024`, `min-width: 768px` portrait), Tablet Horizontal (`1024×768`, `min-width: 768px` landscape / `min-width: 1024px`), and Well-Wrapped Desktop (`1200px–1440px+`, centered `--wrapper-max-width: 1200px` on marketing surfaces and `max-w-[1440px]` / `minmax(0, 1fr)` well-wrapped panels in CP)**, to achieve **zero horizontal overflow at any viewport, smooth orientation transitions on mobile and tablet (portrait & landscape), persistent sidebar state across hat/context switches, and clean visual wrapping on desktop monitors**, accepting **that new components and layouts must author base rules for mobile viewports first and layer tablet/desktop enhancements via progressive `@media` / Tailwind breakpoint modifiers (`sm:`, `md:`, `lg:`, `xl:`)**.

## Context

1. **Owner Direction (`2026-11-01`)**:
   - *"It's time to declare w0m UI to be declared mobile first but still support also tablet sizes with vertical and horizontal orientation and desktop well wrapped as well."*
2. **Observed Friction Across Viewports**:
   - `AppShell.svelte` (`packages/ui/src/lib/components/layout/AppShell.svelte`) previously ignored `localStorage.getItem("w0m-sidebar-collapsed")` whenever `matchMedia("(max-width: 1023px)")` matched, causing the sidebar to snap shut on tablet portrait (`768×1024`) and split-screen viewports whenever a navigation or hat switch occurred.
   - Tablet horizontal (`1024×768`) and mobile landscape (`812×375`) have ample horizontal width relative to their vertical height, requiring orientation-aware header/footer compaction (`@media (max-height: 600px) and (orientation: landscape)`) and side-by-side workspace rails without modal backdrop obstruction on tablet widths (`>=768px`).
   - On large desktop displays (`1440×900` and `1920×1080`), unwrapped `1fr` grid children in `apps/cp` could stretch data cards excessively or overflow horizontally when nested tables/preformatted blocks lacked `min-width: 0`.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **O1 — Keep desktop-first CSS with ad-hoc `max-width` overrides** | No change to legacy habits. | Perpetuates horizontal overflow bugs on mobile, ignores tablet portrait vs landscape ergonomics, and leaves desktop CP panels unwrapped. | **Rejected** |
| **O2 — Separate mobile and desktop layout trees** | Tailored DOM per device class. | Doubles component maintenance, breaks SSR hydration parity (before `matchMedia` runs), and violates single-shell architecture (`T439`). | **Rejected** |
| **O3 — Canonical Mobile-First Single-Shell Architecture with Tablet Vertical/Horizontal & Well-Wrapped Desktop Postures** | One SSR-safe DOM tree (`AppShell`); base rules guarantee mobile usability (`44px` `--tap-target`, fluid `minmax(0, 1fr)`); explicit rules for Tablet Portrait (`768×1024`), Tablet Landscape (`1024×768`), and Well-Wrapped Desktop (`1200px` marketing / `1440px` CP). | Requires discipline to write mobile base rules first and test across portrait + landscape tablet viewports. | **Accepted ([[T603]])** |

## Decision

All `@webomage/ui` primitives, `w0m-web/design-system/` specifications, and `apps/{web,cp,join,job}` pages follow the **4-Posture Mobile-First Responsive Contract**:

| Posture | Canonical Viewport(s) | Media / Breakpoint Contract | Layout & Ergonomic Rules |
|---|---|---|---|
| **1. Mobile First (Base)** | Portrait `375×812` · Landscape `812×375` (`0px–767px`) | Base unprefixed CSS (`< 768px`); landscape short-viewport `@media (max-height: 600px) and (orientation: landscape)` | Single-column flow (`grid-cols-1`); `--tap-target: 44px` minimum interactive hit area; `16px` (`var(--space-4)`) horizontal gutters; CP `AppShell` uses `60px` icon rail + fixed slide-over drawer (`min(264px, 82vw)`) when expanded; compact header/footer on short landscape viewports. |
| **2. Tablet Vertical (Portrait)** | `768×1024` (`768px–1023px`, `orientation: portrait`) | `md:` (`min-width: 768px`) + `@media (min-width: 768px) and (max-width: 1023px) and (orientation: portrait)` | 2-column adaptive card grids (`md:grid-cols-2`); `24px` (`var(--space-6)`) gutters; CP `AppShell` defaults to `60px` icon rail and expands inline (`240px minmax(0, 1fr)`) without blocking the workspace when toggled open; honors `localStorage` sidebar preference across navigations. |
| **3. Tablet Horizontal (Landscape)** | `1024×768` (`768px–1199px`, `orientation: landscape`) | `lg:` (`min-width: 1024px`) + `@media (min-width: 768px) and (max-width: 1199px) and (orientation: landscape)` | 2-to-3 column grids (`lg:grid-cols-3`); side-by-side split panels for height-constrained (`768px`) landscape screens; CP `AppShell` supports full inline sidebar (`248px–264px minmax(0, 1fr)`) with independent vertical scroll (`100dvh`) in both sidebar and main column. |
| **4. Desktop Well-Wrapped** | `1440×900` (`>= 1200px` / `xl:`) | `xl:` (`min-width: 1280px`) / `--wrapper-max-width: 1200px` | Marketing pages wrap inside `max-width: var(--wrapper-max-width, 1200px)` with `margin-inline: auto` and `padding-inline: var(--page-gutter, 24px)`. Control Panel (`apps/cp`) wraps `.w0m-main > *` cleanly with `min-width: 0`, `max-width: 1440px`, and `overflow-x: hidden` on `.col` so wide tables/cards wrap or scroll locally without viewport overflow. |

## Consequences

- **Positive**:
  - Zero horizontal overflow across mobile (`375px`), tablet portrait (`768px`), tablet landscape (`1024px`), and desktop (`1440px`).
  - Sidebar state in `AppShell.svelte` never unexpectedly collapses during hat selection or tablet interaction.
  - All design/UI skills (`webomage-design`, `w0m-pixel-clone`, `figma-designer`, `landing-page-design`) enforce the same 4-posture responsive contract.
- **Negative / Trade-offs**:
  - Layout and visual audits must check both tablet orientations (`768×1024` portrait and `1024×768` landscape) alongside mobile (`375×812`) and desktop (`1440×900`).

## Compliance / Verification

- Enforced in `packages/ui/src/lib/components/layout/AppShell.svelte`, `w0m-web/design-system/readme.md`, and `packages/ui/src/lib/components/layout/__tests__/AppShell.test.ts`.
