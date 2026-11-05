---
id: AgDR-0033
title: "Jobs portal boundary: move Resume Studio, freelancer marketplace sync, multi-platform outreach, proposals, messages, recruiting, and contract management to job.webomage.com while keeping technical project delivery in cp.webomage.com"
timestamp: 2026-10-19T16:00:00-05:00
agent: antigravity
model: gemini-2.5-pro
trigger: user-prompt
status: superseded
superseded_by: AgDR-0056
supersedes:
ticket: T560
---

# AgDR-0033 — Jobs portal boundary: commercial, career, and multi-platform outreach in `apps/job`; technical project delivery in `apps/cp`

> **Status note (2026-11-04, `AgDR-0056` / `T646`):** Portal-boundary clauses **1 and 2** below (`job.webomage.com` vs `cp.webomage.com` split) are **superseded by [`AgDR-0056`](./AgDR-0056-me-personal-portal-unification-and-cp-org-realignment.md)**, which unifies `apps/job` + `apps/join` + personal `/me/*` + public `/u/*` into `me.webomage.com` (`apps/me`) and repatriates all `/o/[org]/*` commercial/recruiting routes back to `cp.webomage.com` (`apps/cp`). Clauses **3 and 4** (Provider-Agnostic Outreach & Clipping Vault and `w0m-ext` Clipper) remain active.

## Y-statement

> In the context of **`cp.webomage.com` (`wom7web/apps/cp`) accumulating member career tools, Resume Studio, Upwork marketplace sync, proposals, messages, recruiting, and commercial contract management alongside technical engineering project delivery, while `job.webomage.com` (`wom7web/apps/job`) serves only public vacancy listings**, facing **cognitive overload in the main Control Panel and the need to manage multi-platform freelancer and professional outreach (Upwork, LinkedIn, Contra, Toptal, Freelancer.com, Fiverr Pro, Wellfound, X-Team, Indeed) with browser-clipped context via `wom7ext`**, we decided **to make `job.webomage.com` (`apps/job`) the single canonical portal for member career & Resume Studio, marketplace sync, multi-platform outreach & communications, proposals, messages, recruiting, and contract management (both member `/me/*` and org-level commercial `/o/[org]/money/{contracts,proposals}` + `/o/[org]/people/recruiting/*`), cut over the moved `apps/cp` routes to 301 redirects, keep `cp.webomage.com` (`apps/cp`) focused strictly on technical project management (`/o/[org]/projects/*`, `/o/[org]/p/[project]/*`), member delivery/identity core, and platform administration, and extend `wom7ext` with a universal and spec-driven page/selection clipper feeding an owner-scoped Outreach & Messages Vault** to achieve **a sharp single-responsibility boundary between commercial/talent acquisition (`job.webomage.com`) and technical project execution (`cp.webomage.com`) with zero duplicate surfaces (`AgDR-0025`)**, accepting **that cross-app UI primitives must be extracted to `@webomage/ui` / `@webomage/lib` and that org users navigate between `job.webomage.com` (contracts, proposals, recruiting) and `cp.webomage.com` (projects, sprints, repositories, invoices) over shared `.webomage.com` SSO cookies**.

## Context

Measured on 2026-10-19 across `wom7web`, `wom7api`, and `wom7ext`:

- `wom7web/apps/job` (`job.webomage.com`) contains only 4 pages (`index.astro`, `jobs/[id].astro`, `404.astro`, `api/health.ts`) and an empty `routes: RouteRule[] = []` in `apps/job/src/lib/route-policy.ts`, even though `apps/job/src/middleware.ts` already mounts `createAuthMiddleware({ app: "job", routes, roleHome: () => "/" })` and `apps/cp/src/lib/supabase-ssr.ts` already scopes `HttpOnly` session cookies to `.webomage.com` with `"job.webomage.com"` whitelisted in `apps/cp/src/pages/sso.ts`.
- `wom7web/apps/cp` (`cp.webomage.com`) currently hosts both **technical engineering delivery** (`/o/[org]/projects/*`, `/o/[org]/p/[project]/*`, `/me/work`, `/me/oss`, `/me/todos`) and **career / commercial talent & contract acquisition** (`/me/profile/resume`, `/me/profile/work`, `/me/upwork/{contracts,proposals,messages}`, `/o/[org]/money/{contracts,proposals}`, `/o/[org]/people/recruiting/*`).
- Upwork sync (`upwork.*` mirror schema, `T468`/`T533`/`T559`: 95 contracts, 1,784 proposals, 162 rooms, 2,614 messages) covers Upwork, while outreach across LinkedIn, Contra, Toptal, Freelancer.com, Fiverr Pro, Wellfound, X-Team, and Indeed has no unified ingestion or thread-tracking surface, and many platforms block server-side scraping behind authenticated browser sessions or Cloudflare challenges.
- `wom7ext` already ships a manifest v3 Chrome extension with `specEngine.ts`, declarative `specs/*.json` extractors (`upwork.*`, `linkedin.*`), and authenticated Supabase session storage (`supabaseService.ts`).

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Option 1: Keep all member career, Upwork, and contract views in `apps/cp` and mirror a subset in `apps/job`** | No route moves in `apps/cp` | Violates `AgDR-0025` (dual SSOT / duplicate pages across apps) and leaves `apps/cp` overloaded with commercial + career workflows | **Rejected** |
| **Option 2: Move only member-level `/me/upwork/*` and Resume Studio to `apps/job`, leaving org `/o/[org]/money/{contracts,proposals}` in `apps/cp`** | Smaller initial route move | Splits contract and proposal management across two portals (`job` for member contracts/proposals, `cp` for org contracts/proposals) | **Rejected by owner (2026-10-19, D2b)** |
| **Option 3: Move all career, Resume Studio, marketplace sync, outreach, proposals, messages, recruiting, and contract management (member `/me/*` AND org `/o/[org]/*`) to `apps/job` (`job.webomage.com`) with 301 cutovers in `apps/cp`, while keeping technical project management (`w0m` internal & client engineering projects) in `apps/cp`** | Clean single-responsibility split: **Commercial, Talent & Career (`job.webomage.com`)** vs **Technical Project Delivery & Ops (`cp.webomage.com`)**; zero duplicate views (`AgDR-0025`) | Requires extracting shared components (`ResumeStudio`, `WorkHistory`, `ContractManager`, `ProposalManager`, `ATSKanban`) to `@webomage/ui` / `@webomage/lib` and updating `cp-view-dispositions.json` | **Chosen (Owner decision 2026-10-19, D1–D5)** |

## Decision

1. **Canonical Portal Boundary (`apps/job` vs `apps/cp`)**:
   - **`job.webomage.com` (`wom7web/apps/job`)** owns:
     - Public job board & vacancy detail (`/`, `/jobs/[id]`).
     - Member Career & Resume Studio (`/me`, `/me/resume`, `/me/work`, `/api/profile/resume`).
     - Member Marketplace Sync & Contract Execution (`/me/contracts`, `/me/proposals`, `/me/messages`, `/me/connectors`).
     - Multi-Platform Outreach & Communications Vault (`/me/outreach`, `/me/outreach/[threadId]`, `/me/clips`).
     - Organization Commercial Contract, Proposal & Recruiting Management (`/o/[org]/money/contracts`, `/o/[org]/money/proposals`, `/o/[org]/people/recruiting/*`, `/o/[org]/outreach`).
   - **`cp.webomage.com` (`wom7web/apps/cp`)** owns:
     - Technical Project Management & Engineering Delivery (`/o/[org]`, `/o/[org]/projects/*`, `/o/[org]/p/[project]/*` for both `w0m` internal projects and client tech projects).
     - Organization Billing & Invoices (`/o/[org]/money/invoices`), Team & Directory (`/o/[org]/people/{team,clients,contacts}`), and Knowledge/Docs.
     - Member Delivery & Identity Core (`/me`, `/me/work`, `/me/oss`, `/me/todos`, `/me/profile`, `/me/account`).
     - Platform Administration (`/admin/*`).
2. **Atomic Cutover (`AgDR-0025`)**:
   - Every route moved from `apps/cp` to `apps/job` is replaced in `apps/cp` with a deterministic 301 redirect to its canonical `https://job.webomage.com/...` URL (preserving query strings such as `?room=` and `?q=`), with `apps/cp/src/lib/context/nav.ts` and `project/cp-view-dispositions.json` updated in the same commit.
3. **Provider-Agnostic Outreach & Clipping Vault (`AgDR-0029`)**:
   - `upwork.*` remains strictly untouched for Upwork mirror fidelity (`T468`/`T533`).
   - Three new owner-scoped tables in `public` (`outreach_clips`, `outreach_threads`, `outreach_messages`) enforce `profile_id = public.current_profile_id()` RLS (`authz_probe_suite.py`), link to `public.contracts` and `public.proposals` via `public.source_links`, and index vetted passages into `public.upwork_evidence_passages` for `w0m-personnel` AI drafting.
4. **Browser Extension Page & Selection Clipper (`wom7ext`)**:
   - `wom7ext` provides declarative `specs/*.json` extractors for Upwork, LinkedIn, Contra, Toptal, Freelancer.com, Fiverr Pro, Wellfound, X-Team, and Indeed, plus a universal DOM-to-Markdown page/selection clipper fallback, ingesting via `POST /functions/v1/outreach-clip-ingest`.

## Consequences

**Positive:**
- Every commercial, recruiting, career, proposal, message, and contract workflow lives in one dedicated portal (`job.webomage.com`), while `cp.webomage.com` stays focused on engineering execution and technical project delivery.
- Zero duplicate pages or unsynchronized parallel UIs across `apps/cp` and `apps/job` (`AgDR-0025`).
- Browser-authenticated page clipping via `wom7ext` works immediately across all freelancer and professional platforms without waiting on third-party OAuth approvals or fragile server-side scrapers.

**Negative:**
- Shared Svelte components (`ResumeStudio`, `WorkHistory`, `ContractManager`, `ProposalManager`, `ATSKanban`) and helper modules (`upwork-view.ts`, `unified-registry.ts`) must live in shared workspace packages (`@webomage/ui` / `@webomage/lib`) rather than app-private folders.
- Users switching between commercial contract negotiation (`job.webomage.com`) and sprint/project execution (`cp.webomage.com`) cross subdomains, relying on shared `.webomage.com` session cookies and cross-portal header switcher links.

## What this does NOT decide

- Replacing `upwork.*` mirror tables or `upwork_mcp_sync.py` (those remain governed by `AgDR-0029` and `T539`/`T559`).
- Automating headless browser outreach sending on third-party platforms (all outbound messages remain human-reviewed and user-sent in the browser; the platform drafts and tracks them).
