---
id: AgDR-0056
title: "Personal & Talent Cloud unification on me.webomage.com (apps/me) and Organization/Crew single-responsibility realignment on cp.webomage.com (apps/cp)"
timestamp: 2026-11-04T19:40:00-05:00
agent: antigravity
model: gemini-2.5-pro
trigger: user-prompt
status: accepted
superseded_by:
supersedes: AgDR-0033
ticket: T646
---

# AgDR-0056 — Personal & Talent Cloud unification on `me.webomage.com` (`apps/me`) and Organization/Crew single-responsibility realignment on `cp.webomage.com` (`apps/cp`)

## Y-statement

> In the context of **personal, candidate, freelancer, public-profile, and organization workflows being fragmented across four web portals (`job.webomage.com`, `join.webomage.com`, `cp.webomage.com`, and `webomage.com/u/*`) after `AgDR-0033` split org-level contracts, proposals, outreach, and recruiting away from `apps/cp` while leaving `apps/join` as a separate 6-page assessment portal and personal `/me/*` utilities split between `apps/cp` and `apps/job`**, facing **cross-subdomain context switching inside `/o/[org]/*` org management, confusion over whether non-crew registered individuals belong in a "member" vs "candidate" vs "job" portal, duplicate profile/resume widgets + an unguarded `adminClient()` / `system_prompt` exposure in `apps/join`, and extra Cloudflare Worker / Pages custom-domain overhead (`AgDR-0055`)**, we decided **to unify `apps/job`, `apps/join`, universal personal `/me/*` workspaces, and canonical public personal profiles (`/u/[slug]/*`) into a single Personal & Talent Cloud portal at `me.webomage.com` (`w0m-web/apps/me`, Worker `webomage-me`), repatriate all `/o/[org]/*` commercial, outreach, and recruiting routes back into `cp.webomage.com` / `cp.w0m.xyz` (`w0m-web/apps/cp`) while keeping only minimal Crew delivery/account `/me` routes (`/me`, `/me/work`, `/me/account`) in `apps/cp`, retire `apps/job` and `apps/join` with zero backward-compatibility shims (`AgDR-0025`), and serve deterministic `301` redirects from `job.webomage.com/*`, `join.webomage.com/*`, `webomage.com/u/*`, `w0m.xyz/u/*`, and moved `cp.webomage.com/me/*` paths to `https://me.webomage.com`** to achieve **strict single-responsibility portal boundaries (`me.` = any registered person + public personal identity + Talent Cloud; `cp.` = Organization + Project + Crew Delivery + Platform Admin; `webomage.com` = B2B corporate showcase), `5 -> 4` Cloudflare SSR Workers, and zero duplicate surfaces**, accepting **an estate-wide atomic cutover across 6 repositories (`@wom`, `w0m-web`, `w0m-api`, `w0m-cf`, `w0m-ext`, `w0m-sec`) and updating external bookmarks/links via `301` redirects**.

## Context

Measured on `2026-11-04` across `@wom`, `w0m-web`, `w0m-api`, `w0m-cf`, `w0m-ext`, and `w0m-sec`:

- **`w0m-web/apps/` ships 5 Astro SSR Workers (`cp`, `demo`, `job`, `join`, `web`):**
  - `apps/join` (`join.webomage.com`, Worker `webomage-join`) has only 7 routes (`/`, `/login`, `/dashboard`, `/assessments`, `/assessments/[id]`, `/interview/[id]`, `/404`). Its `/dashboard` duplicates Resume/Profile widgets already built more completely in `ResumeStudio.svelte` and falls back to `demoCandidateFixture` due to an unauthenticated `anon` Supabase client (`T283` class bug). Its `/interview/[id]` omits `route-policy.ts` registration, invokes `adminClient()` (`service_role`) without session/candidate ownership checks, and serializes `templateData.system_prompt` into client HTML props.
  - `apps/job` (`job.webomage.com`, Worker `webomage-job`) mixes **personal career/freelancer surfaces** (`/me/{resume,work,contracts,proposals,messages,connectors,outreach,todos}`) with **organization commercial & recruiting surfaces** (`/o/[org]/money/{contracts,proposals}/*`, `/o/[org]/outreach`, `/o/[org]/people/recruiting/*`), forcing org managers and crew inside `cp.webomage.com` to bounce across subdomains mid-org-navigation.
  - `apps/cp` (`cp.webomage.com` & `cp.w0m.xyz`, Worker `webomage-cp`) still hosts personal non-org surfaces (`/me/{todos,insights,profile,oss,skills,opportunities,accounting}`) that apply to any registered person (candidates, indie makers, external talent, crew alike), while `apps/web` (`webomage.com`) hosts `/u/[slug]`, `/u/[slug]/cv`, and `/u/[slug]/wishlist` separate from the portal where users actually edit their profile, CV, and wishlists.
- **Session Cookie & Domain Architecture (`packages/lib/src/auth/server-client.ts:15-21`):**
  - `cookieDomainFor()` scopes `HttpOnly` Supabase SSR cookies to `.webomage.com` for every `*.webomage.com` host (`me.webomage.com`, `cp.webomage.com`, `webomage.com`), providing zero-friction SSO across `me.webomage.com` and `cp.webomage.com`.
  - Admin access on `cp.w0m.xyz` uses `.w0m.xyz` cookies; retaining `/me/account` inside `apps/cp` ensures `.w0m.xyz` MFA/PAT/security ceremonies never cross registrable domains.
- **Cloudflare & DNS Hygiene (`w0m-api/cloudflare/records.tf`, `TECH-DEBT.md` `D23`):**
  - Retiring `webomage-join` and consolidating `webomage-job` into `webomage-me` shrinks active SSR Workers from `5` to `4` (`AgDR-0055`) and allows removing legacy `cloudflare_pages_domain.{join_webomage,job_webomage}` resources in favor of clean Cloudflare Ruleset `301` redirects.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Option 1: Keep 4 separate portals (`cp.`, `job.`, `join.`, `webomage.com/u/*`) and patch `apps/join` bugs in place** | Smallest immediate diff | Preserves 4-portal fragmentation, org-level bouncing between `cp.` and `job.`, duplicate candidate/profile views, and an unnecessary 5th SSR Worker (`webomage-join`) | **Rejected** |
| **Option 2: Merge `job.` + `join.` as `member.webomage.com` while renaming `cp.` to `home.` or `i.`** | Consolidates `job.` + `join.` | `"member."` mislabels non-crew registered users (applicants, talent cloud, indie users); renaming `cp.` (`cp.webomage.com` + `cp.w0m.xyz`) churns every client/admin/crew route and test suite without structural gain (`home.`/`i.` read as personal rather than multi-tenant org/ops) | **Rejected by owner (2026-11-04)** |
| **Option 3: Unify `job.` + `join.` + personal `/me/*` + public `/u/*` into `me.webomage.com` (`apps/me`) and keep `cp.webomage.com` / `cp.w0m.xyz` (`apps/cp`) strictly for Organization, Project, Crew Delivery & Admin — with zero backward-compatibility shims (`AgDR-0025`)** | Every portal answers **one real-world question**: `me.` = *"Who am I, my personal tools, my public profile `/u/<slug>`, and my talent/freelance career?"*; `cp.` = *"How does my Organization, Client Engagement, Project, or Crew operate?"*; `webomage.com` = *"What does Webomage offer B2B clients?"*; cuts Workers `5 -> 4` | Requires atomic 6-repo cutover (`@wom`, `w0m-web`, `w0m-api`, `w0m-cf`, `w0m-ext`, `w0m-sec`) and Cloudflare edge `301` rules for retired `job.` / `join.` / `/u/*` URLs | **Chosen (Owner decision 2026-11-04)** |

## Decision

1. **Canonical 3-Surface Portal Architecture (`me.` + `cp.` + `webomage.com`, plus `demo.` sandbox)**:
   - **`me.webomage.com` (`w0m-web/apps/me`, Worker `webomage-me`, dev port `4323`)** is the single **Personal, Public Profile & Talent Cloud Portal** for *any* registered person or public visitor:
     - **Public Identity & Talent Cloud:** `/` (Personal & Talent Cloud home + open roles/bounties), `/jobs` & `/jobs/[id]`, `/assessments` & `/assessments/[id]`, `/u/[slug]`, `/u/[slug]/cv`, `/u/[slug]/wishlist`, `/login`, `/mfa/challenge`.
     - **Universal Personal `/me/*` (`capability: "self"` unless hat-specific):** `/me` (Personal home), `/me/todos` (Lists, Checklists & Shared Wishlists), `/me/insights` (Social Signals & Insights), `/me/profile` (Identity, Privacy & Public Profile controls), `/me/resume` (Resume Studio), `/me/history` (Work History; `/me/work` -> `301 /me/history`), `/me/oss` (OSS & PRs), `/me/skills` (Certifications & Skill Challenges), `/me/applications` (Candidate onboarding & `job_applications`), `/me/interviews/[id]` (Authenticated Hume EVI AI interview), `/me/bounties` (Guild & security bounty board), `/me/contracts`, `/me/proposals`, `/me/messages`, `/me/connectors`, `/me/outreach`, `/me/wallet`, `/me/account`, and `/me/accounting` (Self-accounting & MX RESICO/SAT tax).
     - **Zero `/o/[org]/*` or `/admin/*` routes** exist in `apps/me`.
   - **`cp.webomage.com` & `cp.w0m.xyz` (`w0m-web/apps/cp`, Worker `webomage-cp`, dev port `4324`)** is strictly the **Organization, Client Engagement, Crew Delivery & Platform Admin Control Panel**:
     - Owns **100% of `/o/[org]/*` and `/o/[org]/p/[project]/*` routes**, repatriating `/o/[org]/money/{contracts,proposals}[/[id]]`, `/o/[org]/outreach`, and `/o/[org]/people/recruiting/{index,candidates,templates,pipeline,ats,cv}` from retired `apps/job`.
     - Owns **100% of `/admin/*` platform administration**.
     - Retains **minimal Crew `/me` routes**: `/me` (Crew context landing + link to `me.webomage.com`), `/me/work` (`hat.delivery` assigned project delivery queue), and `/me/account` (local security/MFA/PAT settings so `cp.w0m.xyz` never redirects across registrable domains). All personal/career `/me/*` paths on `apps/cp` return deterministic `301` redirects to `https://me.webomage.com/me/...` preserving query strings.
   - **`webomage.com` (`w0m-web/apps/web`, Worker `webomage`, dev port `4321`)** is strictly the **B2B Corporate Showcase**:
     - Owns `/`, `/audit`, `/co/[slug]` (company public profiles), `/careers` (`200 OK` marketing careers showcase linking open roles/applications to `https://me.webomage.com/jobs`), `/team` (crew showcase linking profile/CV actions to `https://me.webomage.com/u/<slug>`), and legal/service pages.
     - `/u/[slug]`, `/u/[slug]/cv`, and `/u/[slug]/wishlist` on `apps/web` return `301` redirects to `https://me.webomage.com/u/[slug]...`.
2. **Strict Zero-Shim Clean Cutover (`AgDR-0025`)**:
   - Delete `w0m-web/apps/job` and `w0m-web/apps/join` completely; never keep dual Workers, wrapper packages, or deprecated alias builds.
   - Configure edge `301` redirects in `w0m-api/cloudflare/redirects.tf` (`job.webomage.com/* -> https://me.webomage.com/*`, `join.webomage.com/* -> https://me.webomage.com/*`, `webomage.com/u/* -> https://me.webomage.com/u/*`, `w0m.xyz/u/* -> https://me.webomage.com/u/*`) and remove stale `cloudflare_pages_domain.{join_webomage,job_webomage}` declarations from `records.tf`.
3. **Preserved Clauses of `AgDR-0033`**:
   - Decisions **1 and 2** of `AgDR-0033` (`job.webomage.com` portal boundary and `cp -> job` org commercial split) are **superseded** by this decision.
   - Decisions **3 and 4** of `AgDR-0033` (Provider-Agnostic Outreach & Clipping Vault `outreach_{clips,threads,messages}` under `AgDR-0029`, and `w0m-ext` declarative + DOM-to-Markdown clipper via `outreach-clip-ingest`) **remain in full force**, targeting `https://me.webomage.com/me/outreach` for personal outreach and `https://cp.webomage.com/o/[org]/outreach` for org outreach.

## Consequences

**Positive:**
- Every portal has an unambiguous audience and single structural responsibility: **`me.`** for individuals & public personal profiles, **`cp.`** for organizations, client projects, crew delivery & admin, and **`webomage.com`** for B2B marketing.
- Organization managers and crew never leave `cp.webomage.com` when moving between contracts, proposals, recruiting/ATS, projects, sprints, vaults, and invoices.
- Shrinks first-party Cloudflare SSR Workers from `5` to `4` (`AgDR-0055`), eliminates duplicate candidate/profile views, and closes the `adminClient()` + `system_prompt` exposure in `/me/interviews/[id]`.
- Canonical public personal URLs (`me.webomage.com/u/<slug>` with short vanity redirect `w0m.xyz/u/<slug>`) live on the exact same origin where individuals manage their profile, CV, and wishlists.

**Negative:**
- Requires an atomic multi-repo update across `@wom`, `w0m-web`, `w0m-api`, `w0m-cf`, `w0m-ext`, and `w0m-sec` plus visual golden regeneration (`specs/me/goldens.spec`).
- Existing bookmarks to `job.webomage.com`, `join.webomage.com`, or `webomage.com/u/<slug>` rely on HTTP `301` redirects; Cloudflare DNS/Ruleset Terraform changes and orphaned Worker cleanup (`webomage-job`, `webomage-join`) require owner Touch ID confirmation at rollout time.

## What this does NOT decide

- Renaming `cp.webomage.com` / `cp.w0m.xyz` (explicitly retained for Organization, Crew & Admin per owner decision `2026-11-04`).
- Modifying the `upwork.*` mirror schema (`AgDR-0029`) or `outreach_{clips,threads,messages}` RLS tables (`AgDR-0033` §3–4).
- Moving `/co/[slug]` B2B company profiles off `webomage.com` (`/co/[slug]` remains on `apps/web`; only personal `/u/[slug]/*` profiles move to `me.webomage.com`).
