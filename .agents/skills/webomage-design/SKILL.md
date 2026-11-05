---
name: webomage-design
description: "Use this skill to generate, audit, and refine well-branded interfaces, responsive layouts, and UI components for Webomage (@webomage/ui + w0m-web/design-system). Enforces dark-first glassmorphic tokens, per-app [data-app] brand theming, 25 canonical @webomage/ui primitives, and the AgDR-0054 Mobile-First Multi-Orientation Responsive Contract (Mobile Portrait/Landscape, Tablet Vertical 768x1024, Tablet Horizontal 1024x768, and Desktop Well-Wrapped 1200px-1440px+)."
metadata:
  version: "2026.11.04-1793849799"
---

# Webomage Design System (`webomage-design`)

Canonical design system skill for the **Webomage (`@wom`)** estate (`w0m-web/design-system/` SSOT → `w0m-web/packages/ui` `@webomage/ui` Svelte 5 / Astro 6 runtime).

## 1. Visual Foundations & Per-App Brand Tokens

- **Dark-First Canvas**: Deep slate-950 (`#020617`) background, translucent white glass surfaces (`rgba(255, 255, 255, 0.03)` to `0.05` fill, `1px solid rgba(255, 255, 255, 0.10)` hairline border, `12px` backdrop blur, `16px–20px` radius).
- **Per-App Brand Rebinding (`[data-app]`)**:
  - `data-app="web"` (default marketing): sky-blue `--brand-web` (`#38bdf8`) with indigo accent (`#818cf8`).
  - `data-app="cp"` / `data-app="admin"` (Control Panel): app-blue `--brand-app` (`#0a84ff`).
  - Never hardcode `#hex` colors in `apps/cp` or `apps/web` components — always consume CSS custom properties (`var(--brand-color)`, `var(--wom-brand)`, `var(--surface-*)`, `var(--text-*)`, `var(--border-*)`).
- **Typography**: Inter (`400–900`), fluid `--text-hero` (`clamp(1.875rem, 7.5vw, 4.25rem)`) and `--text-section` (`clamp(1.75rem, 4.5vw, 3.5rem)`), monospace emerald for cost/metric figures.

## 2. 4-Posture Mobile-First Multi-Orientation Responsive Contract (`AgDR-0054`, `T603`)

All `w0m` UI surfaces (`apps/web`, `apps/cp`, `apps/me`, `apps/demo`, `@webomage/ui`) are **mobile-first** while explicitly supporting tablet vertical, tablet horizontal, and well-wrapped desktop postures:

1. **Mobile First (`0px–767px`, Portrait `375×812` & Landscape `812×375`)**:
   - Base CSS rules target mobile without `@media` wrappers (`grid-template-columns: minmax(0, 1fr)`, `16px` gutter, `>= 44px` tap targets, zero horizontal page overflow).
   - Mobile landscape (`@media (max-width: 900px) and (orientation: landscape) and (max-height: 600px)`) compacts top/bottom bars so vertical reading canvas is preserved.
2. **Tablet Vertical / Portrait (`768px–1023px`, `orientation: portrait`, `768×1024`)**:
   - 2-column fluid card grids (`24px` gutter) + collapsible `60px` icon rail or `240px` drawer preserving at least `480px` main canvas width.
3. **Tablet Horizontal / Landscape (`768px–1199px`, `orientation: landscape`, `1024×768`)**:
   - Persistent `220px–240px` left navigation + fluid `minmax(0, 1fr)` main panel, 2–3 column grids, and real-time panel re-rendering on project/hat switches without collapsing the sidebar.
4. **Desktop Well-Wrapped (`1200px+` / `1440px+`)**:
   - Persistent `240px` sidebar + well-wrapped main container (`max-width: var(--wrapper-max-width, 1440px); min-width: 0; margin-inline: auto; width: 100%`) so wide monitors never stretch prose, forms, or tables edge-to-edge.

## 3. Canonical Primitives (`@webomage/ui`)

Always import from `@webomage/ui` rather than writing raw `<button>`, `<input>`, or `<select>` controls:
- **Core**: `Badge`, `Button`, `Card`, `Checkbox`, `Input`, `Label`, `Separator`
- **Overlay & Data**: `Dialog`, `Select`, `Table`
- **Brand & Domain**: `BlueprintCard`, `ComplexityBadge`, `GlassCard`, `SegmentBadge`, `StatusDot`, `TechIcon`, `BugReportWidget`, `QuickViewModal`
- **Layout**: `AppShell`, `Breadcrumb`, `ContextSwitcher`, `EmptyState`, `PageHeader`, `SideNav`, `Tabs`
