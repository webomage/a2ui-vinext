---
name: w0m-pixel-clone
description: Lightweight pixel-perfect web page parse-and-copy workflow that captures live URLs, reference screenshots, or DOM+CSS dumps across 3 breakpoints (375, 768, 1440), extracts design tokens into @webomage/ui CSS variables (enforcing RGB triplets inside rgba()), emits clean Astro + Svelte 5 runes components, and verifies fidelity via a closed visual-diff loop (<= 2% mismatch).
trigger: Cloning, migrating, or reconstructing a web page or UI section with pixel-level visual fidelity into Astro + Svelte 5 and @webomage/ui tokens.
license: MIT
provenance:
  origin: w0m
metadata:
  version: "2026.10.26-1793055094"
---

# w0m-pixel-clone — Lightweight Pixel-Perfect Parse-and-Copy Skill

Reconstruct any authorized reference page or UI section into clean **Astro + Svelte 5 runes** and **`@webomage/ui` design tokens** without shipping raw scraped HTML dumps, inline `style="..."` attributes, or third-party class soup.

---

## 0. Legal, Copyright & ToS Guardrail (Mandatory Gate)

Before capturing or emitting any code, verify target authorization:

1. **Authorized targets (allowlisted automatically):**
   - Localhost / loopback / preview environments (`localhost`, `127.0.0.1`, `*.pages.dev`, `*.workers.dev`)
   - First-party & explicit client migration domains (`webomage.com`, `*.webomage.com`, or domains passed via `--allow-domain <domain>`)
2. **Third-party structural study (`--confirm-authorized` required):**
   - Cloning a third-party URL without `--confirm-authorized` is **refused (exit code `2`)**.
   - When `--confirm-authorized` is supplied for structural/layout study, the pipeline enforces **brand/copy/asset sanitization**: third-party logos, proprietary copy, and brand names are replaced with structural placeholders and `@webomage/ui` tokens. Never copy third-party trademarks or copyrighted media verbatim.

---

## 1. Multi-Source Capture Contract (Stage 1)

`w0m-pixel-clone` accepts any combination of three input sources (and refuses with exit code `2` if none are provided):

1. **`--url <https://...>`** — Live URL rendered via Playwright / Chrome DevTools MCP at the 3 canonical breakpoints:
   - **Mobile:** `375x812`
   - **Tablet:** `768x1024`
   - **Desktop:** `1440x900`
2. **`--screenshots <dir-or-csv>`** — Reference screenshots (`mobile.png`, `tablet.png`, `desktop.png` or explicit paths).
3. **`--dom <path.html>` / `--css <path.css>`** — Saved DOM/HTML + computed style or stylesheet dump.

```bash
node .agents/skills/w0m-pixel-clone/scripts/pixel_clone.mjs \
  --url https://localhost:4321/pricing \
  --dom fixtures/pricing.html \
  --css fixtures/pricing.css \
  --out-dir ./clone-out
```

---

## 2. Structural & Section Parser (Stage 2)

Before emitting any component code, `pixel_clone.mjs` parses the DOM into a normalized semantic section tree:

- **Canonical section kinds:** `header`, `hero`, `features`, `cards`, `cta`, `footer`
- **Interactive state map per control:** `default`, `hover`, `focus`, `active`
- **Auditable artifact:** Writes `docs/research/<hostname>/outline.md` containing:
  - Target metadata, breakpoints (`375x812`, `768x1024`, `1440x900`), and authorization mode
  - Ordered section hierarchy (`header` → `hero` → `features` / `cards` → `cta` → `footer`)
  - Landmark selectors, child counts, headings, interactive controls, and state transitions

Review `docs/research/<hostname>/outline.md` before or alongside component generation so layout structure is auditable.

---

## 3. Design Token & CSS Variable Extractor (Stage 3)

Computed styles (`color`, `background-color`, `font-family`, `font-size`, `font-weight`, `line-height`, `letter-spacing`, `border-radius`, `box-shadow`, spacing scale, grid/flex gaps) are extracted and mapped onto `@webomage/ui` CSS custom properties:

- **Color & Surface Tokens:** `--brand`, `--bg`, `--surface`, `--text`, `--text-muted`, `--border`
- **RGB Triplets for Alpha Composition (Mandatory Rule):**
  - Every color token used inside `rgba(...)` is emitted as a comma-separated RGB triplet variable (`--brand-rgb: R, G, B;`, `--bg-rgb: R, G, B;`, `--text-rgb: R, G, B;`).
  - **Never** emit `rgba(var(--brand), 0.2)` when `--brand` holds a `#hex` value — `rgba(#hex, alpha)` is invalid CSS and fails silently in browsers. Always emit `rgba(var(--brand-rgb), 0.2)`.
- **Typography, Radius & Spacing Scale:** `--font-sans`, `--font-display`, `--radius-sm`, `--radius-md`, `--radius-lg`, `--space-1` … `--space-8`, `--shadow-card`.

---

## 4. Svelte 5 + Astro Component Emitter (Stage 4)

Generates clean, maintainable source files using `@webomage/ui` primitives:

1. **`CloneSection.svelte` (Svelte 5 Runes):**
   - Uses `$props()`, `$state()`, and `$derived()` runes.
   - Imports `@webomage/ui` primitives (`Button`, `Card`, `Badge`, `Input`, `Select`, `PageHeader`).
   - Zero raw `<button>`, `<input>`, or `<select>` elements; zero hardcoded `#hex` colors; zero inline `style="..."` dumps.
2. **`index.astro` (Astro Page/Layout):**
   - Imports the extracted `tokens.css` and mounts `CloneSection.svelte` inside the page layout across responsive grid breakpoints (`375px`, `768px`, `1440px`).

---

## 5. Closed Visual-Diff Verification Loop (Stage 5)

To guarantee visual fidelity rather than one-shot guesswork:

1. Render the generated route at `375x812`, `768x1024`, and `1440x900`.
2. Compare reference vs candidate bitmaps/metrics via `compareVisualFidelity` (or `--verify-diff <metrics.json>`).
3. **Pass threshold:** Mismatch ratio `<= 0.02` (`2.0%`) across all 3 breakpoints.
4. **Iterative refinement (`maxPasses = 3`):** When mismatch exceeds `0.02`, report the exact failing breakpoint and bounding region (`header`, `hero`, `cards`, `footer`), adjust token/grid deltas, and re-run up to `N = 3` passes. Exit `1` if mismatch remains `> 0.02` after pass 3.
