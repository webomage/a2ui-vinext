---
id: AgDR-0042
title: "Dual-Track WordPress Migration Delivery Offering (Astro Default + vinext Interactive Track)"
timestamp: 2026-10-25T23:20:00Z
agent: antigravity
model: claude-opus-4-6
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T136
---

# AgDR-0042 — Dual-Track WordPress Migration Delivery Offering (Astro Default + `vinext` Interactive Track)

## Y-statement

> In the context of **productizing a repeatable B2B WordPress modernization service offering (`[[T136]]`, `[[T137]]`) where our first-party estate runs Astro (`wom7web/apps/*`) and client `1945socialclub.com` runs `vinext` (Vite + React on Cloudflare Pages/Workers)**, facing **the SEO/crawl risks of moving content sites to client-rendered SPAs, the `wp-admin`/plugin replacement boundary, and `[[T130]]` stack governance rules**, we decided **to offer a Dual-Track "WP-to-Edge Modernization" service — defaulting to Track 1 (Astro on Cloudflare Pages/Workers + Keystatic/Directus + R2) for 80% of brochure/editorial/SEO WordPress sites, and selecting Track 2 (`vinext` Vite+React SSR on Cloudflare Workers/Pages + Supabase) when interactive React application state or existing React component reuse dominates (`> 30%` stateful routes), while isolating client `vinext` repos in `<client>-w0m` workspaces (`[[T302]]`) and declining heavy WooCommerce/LMS rewrites**, to achieve **sub-50ms edge TTFB, zero PHP/plugin CVE toil, and reusable `1945`/`@wom` delivery playbooks with zero estate `stacks-policy.json` drift**, accepting **that non-technical editors must transition from `wp-admin` to Keystatic or Directus and that shortcode-heavy page builders (~30% of extraction effort) require manual template cleanup**.

## Context

1. **First-party estate measurement (`[[T136]]` AC1):**
   - Connected Hostinger API (`listWordPressInstallations`) returns `[]` (**0 WordPress installs**), and `1945socialclub.com` is already running `vinext-vite-react`.
   - Zero WordPress installations exist across the 7 `@wom` repositories. The migration target is strictly **prospect/client WordPress properties** classified into 4 archetypes (S: Brochure `5–25` pages; M: Editorial/Blog `50–500` posts + ACF/Yoast; L: Interactive/Portal/Multilingual `50–250` pages; XL: Heavy WooCommerce/LMS).
2. **Why `vinext` alone is the wrong default for all WordPress sites (`[[T136]]` AC3/AC5):**
   - ~80% of WordPress sites are brochure, marketing, or editorial content properties whose business value depends on organic search (`JSON-LD`, `sitemap.xml`, instant HTML LCP, social unfurling).
   - Rewriting a server-rendered PHP site into a client-side rendered (`CSR`) React SPA risks crawl regressions and strips `0 KB`-JS Core Web Vitals advantages that **Astro** provides out of the box.
   - Conversely, when a WordPress site is evolving into an authenticated club/member portal or stateful web app (like `1945socialclub.com`), **`vinext` (with Worker SSR enabled)** lets the client leverage the full React component ecosystem.
3. **Stack governance boundary (`[[T130]]`, `[[T302]]`, AC6):**
   - Keeping client `vinext` deliverables inside their own `<client>-w0m` workspaces (`conventions.framework: "vinext-vite-react"`) incurs **0 hours of estate `stacks-policy.json` drift** and `~1.5 hours` of client-workspace `justfile` wiring (`build`, `typecheck`, `lint`, `test`, `fmt-check`).

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Option 1: `vinext`-only migration offering** | Reuses `1945` Vite+React setup across every client | Suboptimal for content/SEO sites (`85–160 KB` React runtime vs Astro's `0 KB` default); high crawl-regression risk if deployed as CSR SPA | Rejected as sole default |
| **Option 2: Astro-only migration offering** | Matches `@wom` first-party stack (`apps/web`, `@webomage/ui`); best CWV/SEO | Friction when a client has existing React/Next.js engineers or needs heavy React-only stateful libraries across most routes | Rejected as sole option |
| **Option 3: Dual-Track Astro (Default) + `vinext` SSR (Interactive Track)** | Matches the right tool to the archetype; preserves `0 KB`-JS SEO for content sites while monetizing `1945` `vinext` expertise for interactive portals | Requires explicit track-selection gate during discovery intake | **ACCEPTED** |
| **Option 4: Headless WordPress (`wp-admin` + edge frontend)** | Zero editor retraining | Double infrastructure/security burden (still patching PHP/MySQL + maintaining edge frontend) | Exception-only (when `> 5` daily editors refuse to leave `wp-admin`) |
| **Option 5: Rewrite WooCommerce / LMS onto Astro or `vinext`** | Large project ticket size | Negative ROI rebuilding cart/tax/shipping/course state machines from scratch | **REJECTED (No-Go)** — route to Shopify or Cloudflare APO hardening |

## Decision

1. **Offer "WP-to-Edge Modernization" in 3 fixed-fee S/M/L bands** (`Band S`: `24–40 hrs` / `$3.5k–$6k`; `Band M`: `56–96 hrs` / `$8.5k–$15k`; `Band L`: `110–180 hrs` / `$18k–$30k`), backed by the playbook in `docs/reports/2026-10-25-t136-wordpress-vinext-astro-migration-offering.md`.
2. **Default to Track 1 (Astro on Cloudflare Pages/Workers + Keystatic/Directus + R2 + Turnstile)** for all brochure, marketing, and editorial WordPress migrations (Archetypes S & M).
3. **Select Track 2 (`vinext` Vite+React with Worker SSR + Supabase Auth/RLS)** when `> 30%` of target views require shared interactive React state, member portal workflows (`1945` pattern), or client React component reuse (Archetype L). Pure CSR SPA mode is prohibited on SEO-indexed routes.
4. **Enforce the Honest Migration Boundary & SEO Gate:** Every engagement requires explicit client sign-off on the CMS replacement (`Keystatic` vs `Directus`), form/auth replacement (`Turnstile` + `Supabase`), and passes a 100% pre-cutover URL `200`/`301` + `JSON-LD` parity check.
5. **Isolate client `vinext` repositories in `<client>-w0m` workspaces (`[[T302]]`)** so `@wom/project/policies/stacks-policy.json` remains purely first-party unless a shared `vinext` package is added to `@wom` (`~1.5 hrs` `T130` registration cost).

## Consequences

- **Positive:**
  - Directly monetizes both `@wom`'s Astro/Cloudflare platform primitives and `1945`'s `vinext` architecture as a high-margin productized service line alongside [[T137]].
  - Protects clients from SEO regressions and scope creep via explicit No-Go boundaries (WooCommerce >50 SKUs, LMS, unbudgeted shortcode rewrites).
- **Negative:**
  - ~30% of migration effort on legacy Elementor/Divi/WPBakery sites remains manual shortcode/template cleanup and must be priced into Band M/L statements of work.

## What this does NOT decide

- Does not register `vinext` inside `@wom/project/policies/stacks-policy.json` today, because no `@wom` estate repo runs `vinext` (`1945` lives in its own client workspace per [[T302]]).
