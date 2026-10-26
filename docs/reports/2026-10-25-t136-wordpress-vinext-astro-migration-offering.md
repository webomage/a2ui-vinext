# T136 — WordPress to Astro & `vinext` (Vite+React) Edge Migration Offering: Research, Boundary Matrix, Effort Model & Go/No-Go Playbook

**Date:** 2026-10-25
**Ticket:** [[T136]]
**Decision Record:** [[AgDR-0042]] (`docs/decisions/AgDR-0042-wordpress-migration-astro-vinext-delivery-offering.md`)
**Epic:** [[ROADMAP]] §21 (Market Research & Business Strategy Continuation)
**Related:** [[T130]] (Stack Governance Contract), [[T137]] (Productized Audit & Modernization Line), [[T302]] (Estate vs Client Workspace Boundary)

---

## Executive Summary

Owner direction (resolved 2026-10-25): position WordPress modernization as a **repeatable B2B client delivery offering ("WP-to-Edge Modernization")** using a **dual-track target architecture**:

1. **Track 1 — Default Target (80% of WordPress sites): Astro on Cloudflare Pages/Workers + Keystatic/Directus + R2.**
   Astro is `w0m`'s canonical first-party web stack (`wom7web/apps/*`, governed in `project/policies/stacks-policy.json`), ships zero client-side JavaScript by default, and delivers superior SEO, Core Web Vitals (`TTFB 20–50 ms`, `LCP < 1.2 s`), and Content Collection ergonomics for brochure, marketing, and editorial WordPress sites.
2. **Track 2 — Interactive/Portal Target (20% of WordPress sites): `vinext` (Vite + React / Next-compatible SSR on Cloudflare Pages/Workers) + Supabase.**
   Proven in production on client `1945socialclub.com` (`conventions.framework: "vinext-vite-react"`), `vinext` is selected when a WordPress site is evolving into a stateful web application, member portal, interactive configurator, or when the client team already maintains React/Next.js components.

---

## 1. Estate Measurement & Prospect Archetype Inventory (AC1)

### 1.1 Measured First-Party & Connected Hosting Inventory

Before modeling client offerings, the connected infrastructure and tracked repositories were measured directly:

| Surface | Measurement Command / Source | Result | Implication |
|---|---|---|---|
| **Hostinger WordPress installs** | Hostinger API `listWordPressInstallations` (`ownership: all`) | `[]` (**0 installations**) | Zero WordPress sites exist on connected Hostinger hosting. |
| **Hostinger websites** | Hostinger API website inventory | `1` site: **`1945socialclub.com`** | Already migrated/operating on `vinext-vite-react` in its dedicated `<client>-w0m` workspace (`1945`). |
| **`@wom` 7-repo estate** | `just search "wordpress"` across `wom7web`, `wom7api`, `wom7func`, `wom7ext`, `wom7sec`, `wom7skills`, `wom7mlx` | **0 WordPress runtimes or themes** | WordPress migration is strictly an **outbound B2B client/prospect delivery line**, never an internal estate rewrite. |

### 1.2 Prospect WordPress Archetypes for Repeatable Delivery

Because the target is prospect/client acquisition rather than a single internal site, candidate engagements are classified into **4 concrete WordPress archetypes** during intake discovery:

| Archetype | Size & Traffic Profile | Typical Theme & Plugin Footprint | Commerce / Forms / Auth Dependencies | SEO Exposure & Target Track |
|---|---|---|---|---|
| **Archetype S — Brochure / Service Marketing WP** | `5–25` pages, `< 20` blog posts, `< 10k` monthly sessions | Elementor, Divi, Astra, or Flavor theme; Contact Form 7 / WPForms; Yoast SEO; WP Super Cache / Wordfence | 1–3 contact/quote forms; Calendly embed; zero login/commerce | Local/brand SEO (`10–50` indexed URLs) → **Track 1: Astro SSG + Cloudflare Pages** |
| **Archetype M — Editorial / Content / B2B Resource Hub WP** | `50–500` posts/pages, `2–5` Custom Post Types (CPTs), `10k–100k` monthly organic sessions | Custom PHP theme or Flavor/GeneratePress + **Advanced Custom Fields (ACF Pro)**, Yoast/RankMath Pro, Redirection, TablePress | Newsletter capture, gated PDF whitepapers, site search, multi-author editorial workflow | High organic search dependency (`100–1,000+` indexed URLs, JSON-LD rich snippets) → **Track 1: Astro SSG/SSR + Keystatic/Directus + Pagefind + R2** |
| **Archetype L — Lead-Gen / Member Portal / Multilingual WP** | `50–250` pages, `2–4` locales or authenticated member area, `10k–250k` monthly sessions | GravityForms (conditional logic + webhooks), WPML / Polylang, MemberPress-lite / Ultimate Member, custom `functions.php` REST endpoints | Authenticated user dashboard, club/event booking (`1945`-shaped), CRM sync (HubSpot/Salesforce), Stripe Checkout links | Combined SEO + authenticated app routes → **Track 2: `vinext` (Vite+React SSR) or Astro + Svelte/React Islands + Supabase Auth/RLS** |
| **Archetype XL — Heavy WooCommerce / LMS / Community (NO-GO)** | `> 50` physical/variable SKUs, LearnDash courses, or BuddyPress forums | WooCommerce + 15–30 payment/tax/shipping/subscription add-ons, LearnDash, WooSubscriptions | Full cart, inventory ledger, tax calculation, shipping labels, SCORM quizzes | **NO-GO for Astro/`vinext` rewrite** (keep on hardened WooCommerce or migrate commerce to Shopify). |

---

## 2. Honest Migration Boundary Matrix (AC2)

A WordPress migration that silently drops `wp-admin` editing or plugin behavior is an unannounced rewrite. Every engagement intake must walk the client through the following **Migration Boundary Matrix** before signing a statement of work:

| WordPress Capability | Legacy WP Mechanism | Astro / `vinext` Target Disposition | Boundary Classification & Product Decision Required |
|---|---|---|---|
| **CMS Authoring for Non-Technical Editors** | `wp-admin` Gutenberg / Classic Editor with live preview and media library | • **Git-backed CMS (`Keystatic` or `Decap CMS`)** mounted at `/keystatic` committing MDX/JSON + uploading media to Cloudflare R2 (`$0/mo` runtime cost), **OR**<br>• **Managed Headless CMS (`Directus` / `Payload` / `Sanity`)** with webhook rebuilds for high-volume daily publishing teams | **Replaces with a product decision.** Must confirm during discovery whether client editors accept Git-backed Keystatic (`1–3` editors, weekly updates) or require a database-backed headless CMS (`5+` editors, role workflows). |
| **Plugin Ecosystem (Security, Backup, Caching, SEO)** | Wordfence, UpdraftPlus, WP Rocket, W3 Total Cache, Yoast SEO (`20–40` active plugins) | • **Security/Cache/Backup plugins:** Deleted outright; replaced by immutable Cloudflare Pages/Workers edge bundles, Git version history, and R2 backups.<br>• **SEO plugins:** Replaced by typed frontmatter schemas + deterministic `<SEOHead />` component + `@astrojs/sitemap`. | **Replaces natively (architectural elimination).** Eliminates 100% of PHP plugin CVE patching and database cache-bloat toil. |
| **Forms & Lead Capture** | Contact Form 7, WPForms, GravityForms + WP Mail SMTP | **Cloudflare Turnstile** (bot verification) + **Cloudflare Worker / Astro API route** + **Supabase Postgres storage** + **3-channel outbound mail (`AgDR-0040`: Workspace SMTP / Resend)**. Multi-step calculators rebuilt as typed React/Svelte components. | **Replaces natively.** Superior deliverability (`SPF`/`DKIM`/`DMARC` enforced) and zero spam-bot database bloat. |
| **Membership & Gated Content** | MemberPress, Restrict Content Pro, `wp_users` cookie sessions | **Supabase Auth (SSR JWT cookies + Row-Level Security)** + **Cloudflare KV session cache (`SESSION`)** + **Stripe Billing / Checkout webhooks** (proven in `wom7web/apps/cp` and `1945`). | **Replaces with a product decision.** Ideal for B2B client portals and club memberships (`1945`-class); do not rebuild complex multi-tier affiliate/drip engines from scratch. |
| **Multilingual Content** | WPML, Polylang, TranslatePress | Astro built-in `i18n` routing (`src/content/[locale]/...`) or `vinext` locale route prefixes + automated `hreflang` sitemap tags. | **Replaces natively.** Removes WPML database join slowdowns (`wp_icl_translations`). |
| **Site Search** | Relevanssi, SearchWP, or default `/?s=` SQL `LIKE` queries | **Pagefind** (static WASM index built at deploy time, `0` server cost) for `< 2,000` pages, or **Supabase FTS / Cloudflare Vectorize** for dynamic/semantic search. | **Replaces natively.** Sub-50ms instant search vs `800ms+` WordPress SQL search. |
| **WooCommerce (Full E-Commerce)** | WooCommerce core + tax, shipping, inventory, gateway plugins | **Should NOT be replaced by custom Astro/`vinext` code.** For `<= 5` fixed-price digital products or memberships, use **Stripe Checkout / Payment Links**. For full catalogs (`> 50` SKUs), either keep WooCommerce or migrate to **Shopify** (with headless Storefront API if needed). | **Cannot / Should NOT replace natively.** Custom-coding cart, tax, and fulfillment logic in React/Astro has negative ROI. |
| **`wp-admin` Dashboard & User Roles** | Built-in PHP admin panel, plugin settings pages | Replaced by Keystatic UI (content), Cloudflare/Plausible/Tinybird analytics, and (when contracted) a scoped client portal (`apps/cp` / `1945` admin surface). | **Replaces with a product decision.** Client must sign off on retiring `wp-admin`. |

---

## 3. Quantified SEO & Continuity Risk Protocol (AC3)

Migrating a live revenue-generating site changes its HTML generator and edge routing. To guarantee zero organic traffic collapse, every migration follows a **5-gate quantified SEO protocol**:

### 3.1 URL & Permalink Preservation vs Deterministic `301` Map

1. **Pre-Migration URL Crawl:** Export 100% of URLs from `sitemap_index.xml`, `wp_posts` (`post_status = 'publish'`), and Google Search Console's top 1,000 landing pages (by clicks/impressions over 16 months).
2. **Route Matching Strategy:**
   - **Preferred:** Preserve exact permalink structures (`/:slug/` or `/blog/:slug/` or `/:year/:month/:slug/`) directly in Astro/`vinext` dynamic routes, including trailing-slash policy (`trailingSlash: "always"` or `"never"` matching legacy canonicals).
   - **When restructuring URLs:** Generate a static Cloudflare `_redirects` file (up to 2,000 static + 100 dynamic rules on Pages) or **Cloudflare Bulk Redirects list** mapping 100% of changed legacy paths (`/:year/:month/:day/:slug/` → `/blog/:slug/`, `/category/:cat/` → `/topics/:cat/`, `/wp-content/uploads/:path*` → `https://media.<domain>/:path*`) with **single-hop HTTP `301` status**.
3. **Zero-404 Cutover Gate:** Automated pre-cutover probe checks every URL in the pre-migration inventory against the staging Cloudflare deployment; any `404`, `5xx`, or multi-hop redirect chain (`301 → 301`) blocks DNS cutover.

### 3.2 Structured Data (`JSON-LD`), Meta Tags & Sitemap Parity

- **JSON-LD Extraction:** Scrape all `<script type="application/ld+json">` payloads emitted by Yoast SEO or RankMath on the live WordPress site (`Organization`, `WebSite`, `Article`, `BreadcrumbList`, `FAQPage`, `LocalBusiness`, `Product`) and snapshot them as golden fixtures.
- **Meta & OpenGraph Parity:** Verify `<title>`, `<meta name="description">`, `<link rel="canonical">`, `og:title`, `og:description`, `og:image`, and `twitter:card` across all page templates.
- **Feeds & Sitemaps:** Emit `/sitemap-index.xml` (or `/sitemap.xml` via rewrite) and `/feed/` (or `301` `/feed/` → `/rss.xml`) so RSS subscribers and Google Search Console sitemap submissions continue without interruption.

### 3.3 Quantified Core Web Vitals (CWV) Before / After Benchmark

| Metric | Legacy WordPress Baseline (Shared PHP Hosting + 25 Plugins) | WordPress + Cloudflare APO (Cached HTML) | Target Track 1: **Astro on Cloudflare Pages/Workers** | Target Track 2: **`vinext` SSR on Cloudflare Workers** |
|---|---|---|---|---|
| **TTFB (Time to First Byte, p75)** | `600 – 1,800 ms` | `60 – 180 ms` (cache hit) / `900 ms` (miss) | **`20 – 50 ms`** | **`35 – 90 ms`** |
| **LCP (Largest Contentful Paint, p75 mobile)** | `2.8 – 4.5 s` | `1.8 – 2.9 s` | **`0.8 – 1.2 s`** | **`1.1 – 1.6 s`** |
| **INP (Interaction to Next Paint, p75)** | `220 – 450 ms` (jQuery + 3rd-party scripts) | `200 – 400 ms` | **`< 50 ms`** (0 KB framework JS on static routes) | **`60 – 110 ms`** (React hydration) |
| **CLS (Cumulative Layout Shift)** | `0.08 – 0.25` | `0.08 – 0.25` | **`< 0.02`** (explicit image dimensions) | **`< 0.02`** |
| **Shipped JS Bundle (Content Page)** | `350 – 900 KB` | `350 – 900 KB` | **`0 – 15 KB`** (islands only) | **`85 – 160 KB`** (React runtime) |

### 3.4 Crawl-Regression Risk of Rendering Model Changes

- 🔴 **Hard Rule — Never migrate an SEO-bearing WordPress site to a Client-Side Rendered (`CSR`) SPA.**
  Replacing server-rendered WordPress PHP HTML with an empty `<div id="root"></div>` Vite+React SPA breaks non-JS social/AI crawlers (`Slackbot`, `LinkedInBot`, `Twitterbot`, `GPTBot`, `ClaudeBot`) and forces Googlebot into deferred second-wave JS rendering, which routinely triggers a `15–40%` temporary indexing drop.
- **Mitigation:**
  - **Track 1 (Astro)** pre-renders static HTML at build time (`SSG`) or streams edge-rendered HTML (`SSR`) with zero client hydration unless an interactive island (`client:load` / `client:visible`) is explicitly declared.
  - **Track 2 (`vinext`)** MUST run with **SSR / pre-rendering enabled on Cloudflare Workers/Pages** for all public indexable routes; client-only rendering is permitted strictly behind authenticated portal routes (`/portal/*`, `/dashboard/*`).

---

## 4. Reference-Grounded Effort & Pricing Model (AC4)

Effort estimates are calibrated against our production `1945socialclub.com` (`vinext-vite-react`) delivery baseline and broken across the 4 engineering workstreams:

### 4.1 Effort Breakdown by Band (S / M / L)

| Workstream | Band S: Brochure WP (`5–25` pages, 0 CPTs) | Band M: Editorial / Content WP (`50–500` posts, ACF, Keystatic) | Band L: Interactive / Portal / Multilingual WP (`50–250` pages + Auth/App state) |
|---|---|---|---|
| **1. Content & Media Extraction** (`WP-CLI` / REST API → MDX + R2 media rewrite) | `4 – 6 hrs` | `12 – 20 hrs` | `16 – 28 hrs` |
| **2. Template & Design System Rebuild** (Astro or `vinext` + Tailwind + responsive layouts) | `12 – 20 hrs` | `24 – 40 hrs` | `40 – 64 hrs` |
| **3. CMS, Forms & Integration Rework** (Keystatic/Directus, Turnstile + Worker mail, Supabase Auth/RLS) | `4 – 8 hrs` | `12 – 20 hrs` | `36 – 60 hrs` |
| **4. SEO, Redirect Map & Cutover QA** (100% URL probe, JSON-LD diff, CWV audit, DNS cutover) | `4 – 6 hrs` | `8 – 16 hrs` | `18 – 28 hrs` |
| **Total Engineering Hours** | **`24 – 40 hrs`** | **`56 – 96 hrs`** | **`110 – 180 hrs`** |
| **Calendar Duration** | **`1 – 2 weeks`** | **`3 – 4 weeks`** | **`5 – 8 weeks`** |
| **Recommended Fixed-Fee Price Band** | **`$3,500 – $6,000`** | **`$8,500 – $15,000`** | **`$18,000 – $30,000`** |
| **Post-Launch Care / Retainer Option** | `$150/mo` (hosting + dependency/content support) | `$350/mo` (hosting + SEO/editorial support) | `$750+/mo` (managed portal, Supabase/Worker SLA) |

### 4.2 What Is Automated vs What Stays Manual

- **Automated (~70% of content extraction & QA):**
  - Fetching `wp_posts`, `wp_terms`, ACF JSON metadata, and Yoast meta via `/wp-json/wp/v2/` or `wp export`.
  - Downloading `/wp-content/uploads/*`, uploading to Cloudflare R2, converting images to WebP/AVIF, and rewriting image URLs in Markdown/MDX.
  - Generating `_redirects` from legacy permalink structures and running the automated HTTP status + canonical/JSON-LD parity verifier.
- **Stays Manual (~30% — must be scoped explicitly in SOW):**
  - **Page-builder shortcode untangling:** Nested `[vc_row][vc_column]`, Elementor JSON widget trees, or Divi layout shortcodes embedded inside post bodies cannot be 100% regex-converted without human visual review on top traffic pages.
  - **Custom `functions.php` business logic:** Bespoke PHP hooks, custom pricing calculators, or undocumented CRM payloads must be read and re-implemented in TypeScript.
  - **Third-party DNS / API credential handoff:** Client domain registrar access, SMTP/Resend DKIM verification, Stripe/CRM webhook secret rotation, and editor onboarding to Keystatic/Directus.

---

## 5. Honest Alternatives Comparison (AC5)

Migrating off WordPress is **not** always the right recommendation. Every discovery audit evaluates 5 options honestly:

| Option | Upfront Effort & Cost | Ongoing Monthly Infra Cost | Pros | Cons | When to Recommend |
|---|---|---|---|---|---|
| **1. Keep WordPress + Harden & Cache** (Cloudflare WAF + APO / Super Page Cache + plugin pruning) | `4 – 8 hrs` (`$600 – $1,200`) | `$25 – $100/mo` (WP hosting + APO) | Lowest upfront cost; zero editor retraining; keeps all PHP plugins and WooCommerce intact. | Still carries PHP/MySQL attack surface, plugin update toil, and slow uncached/admin performance. | Client has `< $2,500` budget, heavy WooCommerce/LMS dependencies, or needs an immediate 48-hour emergency speed/security fix. |
| **2. Headless WordPress** (WP REST/GraphQL backend + Astro/`vinext` frontend) | `40 – 90 hrs` (`$6,500 – $14,000`) | `$25 – $100/mo` (WP origin) + `$0–$5/mo` (CF Edge) | Editors keep `wp-admin` and Gutenberg; frontend gets modern edge speed and design control. | **Worst operational TCO for small teams:** you still patch and host WordPress/MySQL *plus* maintain a separate frontend build/webhook pipeline. | Large editorial teams (`10+` writers) deeply entrenched in `wp-admin` workflows or existing WP custom post plugins. |
| **3. Full Migration to Astro on Cloudflare Pages/Workers** *(Track 1 — Default)* | `24 – 96 hrs` (`$3,500 – $15,000`) | **`$0/mo`** (CF Pages + R2 free tier + Keystatic) | Best CWV/SEO (`0 KB` JS default); eliminates PHP/DB hosting & CVE toil; first-party `@wom` stack skill/tooling reuse (`wom7web`). | Non-technical editors must move from `wp-admin` to Keystatic or Directus; no native PHP plugin drop-ins. | **Default recommendation for ~80% of brochure, B2B marketing, and content/SEO WordPress sites.** |
| **4. Full Migration to `vinext` (Vite+React SSR) on Cloudflare** *(Track 2 — Interactive)* | `56 – 180 hrs` (`$8,500 – $30,000`) | **`$0 – $5/mo`** (CF Workers/Pages + Supabase Free/Pro) | Full React component ecosystem; ideal for rich client state, member portals (`1945`), and teams with existing React/Next.js code. | Higher JS bundle weight (`85–160 KB`) than Astro; requires SSR configuration to protect SEO; separate stack from `@wom` core (`apps/*` is Astro). | **Recommended for ~20% of sites** where the WP site is becoming an interactive portal, booking engine, or React web app (`1945` pattern). |
| **5. Managed Visual Builders** (Webflow / Framer) | `20 – 60 hrs` (`$3,000 – $9,000`) | `$29 – $79+/mo` per site (vendor lock-in) | Best visual canvas for non-technical marketing designers to tweak layouts without Git. | High recurring SaaS fees; CMS item limits (`10k` cap); weak custom backend/auth extensibility; no code ownership. | Design-led startups whose in-house marketing designer wants to own layout tweaks directly in a visual GUI. |

---

## 6. `T130` Stack Governance & Registration Cost (AC6)

Under [[T130]] (`project/policies/stacks-policy.json`) and [[T302]] (Estate vs Client Workspace Boundary), adopting `vinext` has two distinct governance modes with quantified setup cost:

1. **Mode A — Client-Workspace Isolation (`<client>-w0m`, Recommended Default: `0 hrs` estate cost, `~1.5 hrs` per client repo):**
   - Per `AGENTS.md` and [[T302]], client engagements (`1945`, `bridgeroad`, `artemio`, and any future WP migration client) live in their own `<client>-w0m` workspace outside the 7 `@wom` estate repositories.
   - `just discovery` in `@wom` scans only the 7 first-party estate repositories (`wom7web`, `wom7api`, `wom7func`, `wom7ext`, `wom7sec`, `wom7skills`, `wom7mlx`). Therefore, running `vinext` in `<client>-w0m` introduces **zero drift** in `@wom/project/policies/stacks-policy.json`.
   - Inside `<client>-w0m`, `.w0m/sdlc.json` declares `"framework": "vinext-vite-react"` and wires its local `justfile` recipes (`build`, `dev`, `typecheck`, `lint`, `test`, `fmt-check`) in **`~1.5 hours`** of initial scaffolding, reusing the `1945` reference template.
2. **Mode B — First-Party Estate Registration (`~1.5 hrs` one-time cost if a `vinext` package is ever committed inside `@wom`):**
   - If a shared `vinext` template or app is ever added inside a tracked `@wom` estate repo, `just discovery --enforce` will flag `vite`/`react` as undeclared drift until a stack entry is added to `project/policies/stacks-policy.json`:
     - **`techs`**: `vite` (`dep:vite`), `react` (`dep:react`), `typescript` (`dep:typescript`), `wrangler` (`dep:wrangler`).
     - **Canonical `commands` → `just` recipes**: `build` → `vinext-build`, `typecheck` → `vinext-typecheck`, `lint` → `vinext-lint`, `test` → `vinext-test`, `fmt-check` → `vinext-fmt-check`.
     - **`gates`**: `typecheck`, `lint`, `fmt-check` wired to `pre-commit` / `pre-push` and verified by `just hooks-check` and `just discovery --enforce`.

---

## 7. Go / No-Go Decision & Flip Conditions (AC7)

### 7.1 Final Verdict: **GO — Dual-Track "WP-to-Edge Modernization" Offering**

We adopt **WordPress-to-Edge Modernization** as a repeatable B2B service offering (paired with [[T137]]'s technical audit intake), governed by [[AgDR-0042]]:

- **Default Delivery Stack (Track 1): Astro on Cloudflare Pages/Workers + Keystatic/Directus + R2 + Turnstile** for Archetypes **S** and **M** (brochure, marketing, content, and SEO-critical WordPress sites).
- **Interactive Portal Delivery Stack (Track 2): `vinext` (Vite + React SSR on Cloudflare Workers/Pages) + Supabase Auth/RLS** for Archetype **L** when interactive React state, member portals (`1945`-class), or client React component reuse is a primary requirement.
- **Decline / Re-route (Archetype XL):** Decline custom Astro/`vinext` rewrites for heavy WooCommerce (`> 50` SKUs), LMS, or low-budget (`< $2,500`) maintenance inquiries; offer either a `$750–$1,200` Cloudflare WAF/APO Hardening Sprint or a Shopify commerce migration.

### 7.2 Quantitative Conditions That Flip Track Selection

| Condition Observed During Discovery | Resulting Track Flip |
|---|---|
| `> 30%` of target views are stateful interactive workflows (dashboards, live booking/configurators, React component libraries) OR client engineering team is React-only | Flip **Track 1 (Astro) → Track 2 (`vinext` Vite+React SSR)** |
| `> 5` non-technical editors publishing daily with role-based draft approvals who refuse Git-backed PR/commit workflows | Flip **Keystatic (Git-backed) → Directus / Headless WP API** |
| Site has `> 50` WooCommerce SKUs with dynamic tax/shipping/inventory plugins | Flip **Full Migration → NO-GO** (recommend Shopify or Hardened WP + Cloudflare APO) |
| Prospect budget is `< $3,500` and goal is solely "make our existing WP site faster and stop brute-force logins" | Flip **Full Migration → Option 1 (Cloudflare WAF + APO Hardening Sprint)** |
