---
name: webomage-design
description: "Use this skill to generate, audit, and refine well-branded interfaces, responsive layouts, and UI components for Webomage (@webomage/ui + w0m-web/design-system). Enforces dark-first glassmorphic tokens, per-app [data-app] brand theming, 25 canonical @webomage/ui primitives, and the AgDR-0054 Mobile-First Multi-Orientation Responsive Contract (Mobile Portrait/Landscape, Tablet Vertical 768x1024, Tablet Horizontal 1024x768, and Desktop Well-Wrapped 1200px-1440px+)."
metadata:
  version: "2026.11.09-1794266135"
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

## 4. UI Copy Hygiene — Zero Internal Ticket or AgDR Spam (`T667`)

- **Never expose internal engineering tracker IDs in user-facing UI**: Do not put `T##` ticket numbers, `AgDR-####` / `ADR-####` decision numbers, or `AC#` acceptance-criteria tags into headings, card titles, badges, buttons, form labels, placeholders, tooltips, table headers, status pills, empty states, validation messages, or UI-rendered catalog descriptions.
- **Write clear product/domain copy instead**: Describe what the capability does for the user (e.g., `"Personal Access Tokens"`, `"Dedicated Client Instance"`, `"Zero-Trust Origin Verification"`) rather than citing the ticket or decision that introduced it (`"(T53)"`, `"(AgDR-0028)"`, `"(AC4)"`).
- **Keep SDLC provenance in code comments & commits**: Place `T##` and `AgDR-####` references in HTML/JS comments (`<!-- T663 -->`, `// AgDR-0054`), `.tasks/T##.md`, specs, and commit messages — enforced mechanically by `just ui-ticket-leak-check`.

## 5. 12-Dimension UI Craftsmanship & Zero-Execution Read-Only Skill/Repo Audit Rubric

Synthesized from the estate's 4 forked UI/UX audit skills (`webomage/ui-ux-pro-max-skill`, `webomage/agent-skills`, `webomage/redesign-skill`, and `webomage/ui-ux-suite`):

1. **D1 — Token Purity & Theme Discipline (`10 pts`)**: Zero hardcoded `#hex` colors (`#38bdf8`, `#020617`, etc.) inside application components; 100% consumption of `var(--...)` CSS custom properties and `rgba(var(--rgb-*), alpha)` triplets.
2. **D2 — Perceptual Contrast & Dark-Mode Depth (`10 pts`)**: WCAG 2.2 AA (`>= 4.5:1` body, `>= 3:1` UI controls) + APCA `Lc >= 60` on dark glass surfaces; bordered elevation (`1px solid rgba(255, 255, 255, 0.10)`) instead of muddy drop shadows.
3. **D3 — Typography Hierarchy & Numeric Discipline (`8 pts`)**: Maximum 4 distinct font sizes per card/section, `60ch–72ch` prose measure, and `font-variant-numeric: tabular-nums` (`tabular-nums`) on all counters, prices, scores, and latency metrics.
4. **D4 — Equal-Height Card Grid Rhythm & Bottom-Pinned CTAs (`10 pts`)**: Every multi-column card grid MUST apply `auto-rows-fr items-stretch` on the grid container, `h-full flex flex-col justify-between` on each card, and `mt-auto pt-4` on the footer/CTA link row so bottom links align along a single horizontal baseline across mobile, tablet, and desktop.
5. **D5 — 4-Posture Responsive Contract (`10 pts`)**: Zero horizontal overflow and balanced layout across Mobile (`375×812` & `812×375`), Tablet Vertical (`768×1024`), Tablet Horizontal (`1024×768`), and Desktop Well-Wrapped (`1200px–1440px+`).
6. **D6 — 6-State Component Completeness (`8 pts`)**: Every interactive/async view explicitly implements `default`, `hover`, `focus-visible`, `loading` (skeleton/spinner without layout jump), `empty` (actionable `EmptyState`), and `error` (clear recovery banner + retry CTA).
7. **D7 — Primitive Reuse (`@webomage/ui`) (`8 pts`)**: Use canonical `@webomage/ui` primitives (`Button`, `Input`, `Select`, `Badge`, `Card`, `Dialog`, `Tabs`) instead of ad-hoc raw HTML controls.
8. **D8 — Accessibility & Keyboard Ergonomics (`10 pts`)**: `aria-label` on icon-only controls, explicit `<label>` associations, `:focus-visible` rings, semantic landmarks, and `>= 44×44px` (`min-h-11`) touch targets.
9. **D9 — Motion & Micro-Interaction Discipline (`6 pts`)**: `150ms–220ms` cubic-bezier transitions on `transform`/`opacity` only, with mandatory `@media (prefers-reduced-motion: reduce)` (`motion-reduce:`) support.
10. **D10 — Conversion Flow & Step Auto-Scroll (`8 pts`)**: Selecting any option/tier in multi-step forms smoothly scrolls (`scrollIntoView({ behavior: 'smooth', block: 'center' })`) to the next step, routes paid tiers through account registration + Free Baseline Audit before Stripe Checkout, and routes AI Agent Helper conversations to Free Audit registration.
11. **D11 — Zero Dead Controls & Copy Hygiene (`6 pts`)**: Zero `href="#"` anchors, zero no-op handlers, and zero leaked internal ticket/AgDR/AC identifiers (`just ui-ticket-leak-check`).
12. **D12 — Anti-Slop Visual Craftsmanship (`6 pts`)**: One unmistakable primary CTA per viewport, consistent `20px` outer / `12px` inner card border-radius nesting, and domain-specific microcopy (zero generic filler).

### Read-Only Zero-Execution Skill & Repository Audit Mode (`executionMode: "zero_exec_readonly_ast"`)
When auditing a shared client GitHub repository or external `SKILL.md` / `.claude/` / `.agents/` skill bundle:
- **Never execute untrusted code, `npm install`, `postinstall` hooks, or container sandboxes.**
- Perform 100% read-only static AST/source inspection over the repository tree (`runReadOnlyRepoAndSkillUiAudit` in `@webomage/lib` and `run_readonly_repo_and_skill_audit` in `scripts/fork_catalog_sync.py`) checking both **Skill/Repo Security** (prompt injection, Trojan-Source bidirectional Unicode, malicious `package.json` lifecycle scripts, `curl | sh` pipes) and the **12 UI/UX Craftsmanship Dimensions**.
