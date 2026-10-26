---
id: AgDR-0048
title: "Decline destructive personal-to-company org merge; adopt non-destructive portfolio attribution and cutoff novation for engagements"
timestamp: 2026-10-25T23:00:00-05:00
agent: antigravity
model: claude-opus-4-6
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T459
---

# AgDR-0048 — Decline destructive personal-to-company org merge; adopt non-destructive portfolio attribution and cutoff novation

## Y-statement

> In the context of **[[AgDR-0027]] §4 and [[AgDR-0028]] §1, where every registered person without a company receives a silent personal org (`orgs.kind = 'personal'`), a personal org that is a party to any engagement is kept when the person joins or claims a company org (`public.brand_slug_claims`, [[T495]]), and [[T459]] (split from [[T458]] Q32) evaluates whether to allow merging a person's personal org into their company org by transferring its engagements**, facing **12 relational surfaces tied to `orgs` and `engagements` — including freelancer-scoped `upwork.contracts` and `public.source_links` (`AgDR-0029`), issued fiscal `public.invoices` with Stripe/Mercado Pago/Banxico SPEI audit trails (`T351`), append-only `public.hat_assignment_log` records (`T461`), and uniqueness constraints on `public.projects` (`projects_host_name_lower_uq`) and `public.client_message_threads` (`idx_client_message_threads_client_org`)**, we decided **to permanently reject destructive in-place `org_id` merging across historical engagements, contracts, and invoices, and instead adopt a Non-Destructive Attribution & Cutoff Novation Policy: completed engagements, contracts, invoices, and Upwork links remain immutable on the personal org; company orgs showcase a founder's prior personal engagements via Dual Portfolio Attribution; and active/in-flight engagements transition to a company org only via an explicit Cutoff Novation (closing the personal engagement at the cutoff date and opening a linked successor engagement on the company org for active projects and future billing)** to achieve **100% legal counterparty, tax/CFDI/1099, and Upwork source-mirror integrity while giving newly formed or claimed companies full commercial credit for their founders' verified track record**, accepting **that a person with prior solo engagements retains their historical personal org in `public.orgs` alongside their company org (`AgDR-0027` §4)**.

## Context

Measured on 2026-10-25 across `wom7api/supabase/migrations/` and `wom7web` (`.agents/reports/2026-10-25-t459-personal-to-company-org-merge-research.md`, [[T459]]):

1. **In-Place Conversion Already Covers Solo Incorporation (`AgDR-0027` §4)**:
   - When a solo person incorporates their own business and no separate target company row exists, `public.orgs.kind` converts in place from `'personal'` to `'company'`. Nothing needs to be copied or merged because the org UUID does not change.
   - The merge question (`T459`) arises only when **two distinct `public.orgs` rows exist**: a person's `personal` org (which already has historical or active engagements) and a separate `company` org that the person claims (`T495`) or joins.
2. **Why Rewriting Historical `org_id` References Violates Legal, Tax, and Mirror Invariants (`AC1`)**:
   - **External Marketplace Provenance (`AgDR-0029`, `T468`):** `upwork.contracts` connects to `upwork.connections(profile_id, scope)`. Contracts executed under `scope = 'freelancer'` legally name the individual person and their personal tax profile on Upwork. Rewriting `engagements.contractor_org_id` on historical engagements to a company org falsifies who contracted the work.
   - **Fiscal & Payment Rail Immutability (`T373`, `T351`):** `public.invoices` rows carry `client_id`, `contract_id`, Stripe payment intents (`orgs.stripe_customer_id`), Mercado Pago IDs, and Banxico SPEI 7-digit references / 18-digit CLABEs (`20261021201000_t351_mexican_payment_rails_invoices.sql`). Tax law (SAT CFDI in Mexico, IRS 1099/W-8BEN in the US) forbids retroactively altering the legal issuer or recipient on settled invoices.
   - **Relational & Uniqueness Collisions (`T204`, `T285`, `T442`):**
     - `public.projects` enforces `projects_host_name_lower_uq` on `(host_org_id, lower(btrim(name)))`.
     - `public.client_message_threads` enforces `idx_client_message_threads_client_org` (at most one thread per `client_org_id`).
     - `public.connections` enforces `connections_org_provider_urn_uq` on `(org_id, provider, provider_urn)`.
     - `public.engagements` enforces `ON DELETE RESTRICT` on both `contractor_org_id` and `client_org_id`.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Option 1 — Destructive In-Place `org_id` Merge** (Rewrite `contractor_org_id` / `client_org_id` / `org_id` from personal org to company org across all tables and delete personal org) | Single remaining `orgs` row for the user. | Falsifies legal counterparties on closed contracts and paid invoices; contradicts `upwork.connections.scope = 'freelancer'`; collides on unique indexes (`projects_host_name_lower_uq`, `idx_client_message_threads_client_org`, `connections_org_provider_urn_uq`). Weighted score: **2.05 / 5.00**. | **Rejected (`AC1`, `AC3`)** |
| **Option 2 — Non-Destructive Attribution & Cutoff Novation Model (Recommended)** (Keep personal org + historical engagements/invoices immutable; cross-link founder case studies to company portfolio; transition active engagements via cutoff novation) | Preserves 100% of tax, invoice, Upwork mirror, and RBAC audit trails; solves the commercial showcase need for the company org; provides a legally sound cutoff novation path for active projects. Weighted score: **4.85 / 5.00**. | A person who had solo engagements prior to joining a company retains their historical personal org in `public.orgs`. | **Accepted (`AC1`–`AC3`)** |
| **Option 3 — Status Quo (No Portfolio Attribution & Manual Project Recreation)** | Zero schema or UI additions. | Newly claimed/formed company orgs cannot showcase founder case studies (`T288`) delivered under a personal org; active projects must be recreated by hand. Weighted score: **3.20 / 5.00**. | **Rejected (`AC3`)** |

## Decision

### 1. Per-Item Disposition Policy (`AC2`)

1. **Never Move (Permanently Immutable on Personal Org / Profile)**:
   - **`public.orgs` (`kind = 'personal'`)**: Kept permanently whenever referenced by $\ge 1$ `public.engagements` row (`ON DELETE RESTRICT`, `AgDR-0027` §4).
   - **Completed `public.engagements` & Closed `public.contracts` / `client_milestones` / `engagement_closures`**: Keep original `contractor_org_id` and `client_org_id`.
   - **External Marketplace Mirrors (`upwork.*` & `public.source_links`)**: Governed by `AgDR-0029`; bound to `profile_id` and never re-attributed to a different org.
   - **Issued Financial Records (`public.invoices`, Stripe `stripe_customer_id`, SPEI/Mercado Pago settlements)**: Immutable fiscal ledger; never re-parented across legal entities.
   - **Security Audit Logs (`public.hat_assignment_log`) & Personal Career Records (`profile_experience`, `profile_cv_facts`, `profile_resumes`)**: Remain permanently attached to their original engagement and `profile_id`.
2. **Copy / Cross-Link (Dual Portfolio Attribution)**:
   - **Public Case Studies & Portfolio Items (`public.projects.published_case_slug`, `T288`)**: Keep `projects.engagement_id` pointing to the true historical engagement on the personal org, and expose a cross-org attribution link (`engagement_attributions` / `attributed_org_id`) so a company org where the person holds `<company>.owner` can display the case study on `/co/<company>` with explicit provenance (`"Delivered by <Person> (Founder at <Company>)"`).
   - **Outreach Clips & RAG Evidence (`public.outreach_clips`, `public.upwork_evidence_passages`, `T561`)**: Retain `profile_id = current_profile_id()` ownership while setting `outreach_clips.org_id = company_org_id` so the company's commercial team and `w0m-personnel` AI drafting can cite the evidence.
3. **Transferable (Active / Unbilled / Prospective Only, via Cutoff Novation or Pipeline Reassignment)**:
   - **Prospective Pipeline (`public.outreach_threads`, `public.leads`, `DRAFT` `public.contracts` with 0 invoices)**: May reassign `org_id` / `client_id` directly to the company org before contract execution.
   - **In-Flight Commercial Engagements (`status = 'active'` with prior invoices)**: Must use **Cutoff Novation**, never in-place mutation:
     1. Close the personal-org engagement (`status = 'completed'`) and settle/freeze all pre-cutoff milestones and invoices on the personal org.
     2. Create a successor `public.engagements` row on the company org (`supersedes_engagement_id` pointing to the closed personal engagement).
     3. Re-point active `public.projects`, `public.project_repos`, and `public.project_vaults` to the successor engagement (verifying `projects_host_name_lower_uq` before re-pointing `host_org_id`), allowing `wom_hats_fill()` (`T458 S7`) to provision fresh engagement hats on the company org.
   - **Org Connections (`public.connections` where `owner_kind = 'org'`)**: Never bulk-copied; require either fresh corporate OAuth authorization or explicit single-connection reassignment by a principal holding `grant.manage` on both orgs.

### 2. Build Ticket Disposition (`AC3`)

- **Destructive org merge is closed and declined** with the rationale above (`T459` Definition of Done).
- Because `webomage` is currently the sole active delivery contractor org on the platform (`AgDR-0028` §1) and all 95 historical Upwork contracts are already linked under `T468`/`T529`, no immediate database migration is needed today. Any future agency onboarding surface in the public directory (`AgDR-0027` §9) must implement the non-destructive Attribution & Cutoff Novation pattern defined here.

## Consequences

- **Positive**:
  - Preserves 100% legal, fiscal (SAT CFDI, IRS 1099, Banxico SPEI `T351`, Stripe), and marketplace (`AgDR-0029` Upwork mirror) integrity with zero retroactive counterparty falsification.
  - Eliminates multi-table unique index collisions (`projects_host_name_lower_uq`, `idx_client_message_threads_client_org`, `connections_org_provider_urn_uq`).
  - Enables newly formed or claimed companies to display their founders' verified track record with honest provenance.
- **Negative**:
  - Founders who completed engagements on a personal org before joining an existing company org will continue to see their historical personal org in their archived context list alongside their active company org.

## What this does NOT decide

- The UI layout of the public company directory (`/co/<slug>`, `AgDR-0027` §9), which is tracked under its own directory tickets.
- Bilateral legal novation templates (PDF/DocuSign addendum text) between a client org, a personal org, and a successor company org.
