---
id: AgDR-0049
title: "Group training across personal orgs uses a Training Cohort container over two-party engagements, never multi-client engagements"
timestamp: 2026-10-25T23:10:00-05:00
agent: antigravity
model: claude-opus-4-6
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T460
---

# AgDR-0049 — Group training across personal orgs uses a Training Cohort container over two-party engagements

## Y-statement

> In the context of **[[AgDR-0028]] §3 and [[T460]] (split from [[T458]] Q30), where every engagement joins exactly two organisations (`contractor_org_id` and `client_org_id`, addressed `<contractor>.<engagement>.<client>`), training runs through engagements of `kind = 'training'` with minimum hats `trainer` and `trainee`, and the owner asked how to model group training where one trainer teaches several trainees from several personal orgs**, facing **seven live engagement-scoped RLS policies (`contracts_client_select_own`, `Client select own milestones`, `Client view own invoices`, `projects_client_select_own`, `project_repos_client_select_own`, `Client users select own project_vaults`, `Client users select own vault_notes`) that grant read access to any holder of an active hat on `engagement_id`, alongside `@backstage/catalog-model`'s requirement that an engagement `Group` has one `spec.parent` and a singular `w0m.dev/client` annotation (`AgDR-0026`, `AgDR-0028`)**, we decided **to permanently reject multi-client engagements (`engagement_client_orgs` M:N, Model B), keep the strict two-party `public.engagements` row per trainee (Model A) as the canonical legal, billing, grading, and RLS primitive, and specify a Training Cohort container (`public.training_cohorts` + `engagements.cohort_id`, Model C) that groups $N$ two-party training engagements under one shared syllabus vault and instructor view (`Group` with `spec.type: cohort` in Backstage)** to achieve **complete trainee privacy for grades, tuition contracts, invoices, dropouts, and submission repositories while giving instructors a unified cohort classroom and 100% Backstage catalog compliance**, accepting **that a cohort of $N$ solo trainees creates $N$ two-party `engagements` rows linked by `cohort_id` and that the `training_cohorts` migration is deferred until the first multi-personal-org cohort is scheduled (`AgDR-0025`)**.

## Context

Measured on 2026-10-25 across `wom7api/supabase/migrations/` and `wom7web/project/scripts/catalog_models.py` (`.agents/reports/2026-10-25-t460-group-training-engagement-models-research.md`, [[T460]]):

1. **Same-Company Corporate Training Already Works in a Single Engagement (`AgDR-0028` §4)**:
   - When a single company org (e.g. `acme`) contracts `webomage` to train 5 of `acme`'s employees, all 5 trainees belong to the same client org (`acme`). Under [[AgDR-0028]] §4 ("a role may have several holders"), all 5 employees hold `trainee` hats on the single two-party engagement `webomage.<id>.acme`.
   - The architectural fork in [[T460]] arises specifically when **trainees come from $N$ separate personal orgs** (`orgs.kind = 'personal'`, `AgDR-0027` §4).
2. **Why Multi-Client Engagements (Model B) Break RLS Isolation and Backstage (`AC1`, `AC2`)**:
   - **Cross-Trainee Privacy Leak:** In `20261007120000_t529_retire_clients_and_client_users.sql` and `20261021180000_t284_t344_client_vaults_and_telegram_enforcement.sql`, RLS policies grant `SELECT` on `contracts`, `projects`, `project_repos`, and `project_vaults` to any authenticated user holding an active hat on `engagement_id`. If $N$ trainees from $N$ unrelated personal orgs share one `engagement_id`, every trainee can read every other trainee's tuition contract, scholarship terms, graded submission repository, and private evaluation notes.
   - **Coupled Dropout / Lifecycle State:** `public.engagements.status` (`draft | active | paused | completed | archived`) is a single scalar per engagement. If 1 of 10 trainees pauses or drops out, a single engagement row cannot represent per-trainee lifecycle states.
   - **Backstage Entity Schema Violation:** In `wom7web/project/scripts/catalog_models.py` (`AgDR-0026`, `AgDR-0028`), an engagement `Group` has `spec.parent = group:default/<contractor>` and `metadata.annotations["w0m.dev/client"] = group:default/<client>`. A multi-client engagement has no singular `<client>` for either `w0m.dev/client` or the `<contractor>.<engagement>.<client>` address.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Model A — One Standalone Two-Party Engagement per Trainee (Current Base Model)** | Zero schema changes; 100% RLS isolation of grades, contracts, invoices, and repos; independent `engagements.status` per trainee; valid Backstage entities. Weighted score: **4.25 / 5.00**. | Instructor teaching $N$ solo trainees must attach the shared curriculum vault and post syllabus updates across $N$ ungrouped engagements. | **Kept as Base Legal/RLS Primitive (`AC1`, `AC3`)** |
| **Model B — One Multi-Client Engagement (`engagement_client_orgs` M:N join)** | Single `engagements` row per batch. | Breaks `<contractor>.<engagement>.<client>` address (`AgDR-0028` §2); leaks private contracts, invoices, grades, and submission repos across all trainees under live RLS; couples dropout `status`; breaks singular `w0m.dev/client` in Backstage. Weighted score: **1.60 / 5.00**. | **Permanently Rejected (`AC1`–`AC3`)** |
| **Model C — Training Cohort Container Grouping $N$ Two-Party Engagements (`training_cohorts` + `engagements.cohort_id`, Recommended)** | Preserves 100% of two-party contract, billing, grading, repo, and dropout isolation on each trainee's `engagements` row while sharing one cohort curriculum vault, one announcement feed, and a native Backstage `Group` (`spec.type: cohort`) parent node. Weighted score: **4.80 / 5.00**. | Adds one `training_cohorts` table and a nullable `engagements.cohort_id` FK when group cohorts launch. | **Accepted Target Architecture (`AC1`–`AC3`)** |

## Decision

### 1. Invariant: `public.engagements` Remains Strictly Two-Party (`AC1`)

1. **No Multi-Client Engagements:** `public.engagements` permanently joins exactly one `contractor_org_id` and one `client_org_id` (`AgDR-0028` §1). `engagement_client_orgs` M:N join tables are prohibited.
2. **Isolation Boundaries in Group Training (Model C):**
   - **Private per Trainee (on the two-party `engagements` row):** Tuition `contracts`, `invoices`, 1:1 mentoring `client_message_threads`, individual capstone `projects` and `project_repos`, grades/assessments, and enrollment `status` (`active`, `paused`, `completed`, `archived`).
   - **Shared across the Cohort (on `training_cohorts`):** Cohort syllabus & lecture notes (`cohort_vault_id REFERENCES public.project_vaults(id)`), curriculum `blueprint_id`, cohort schedule (`start_date`, `end_date`), and opt-in cohort Q&A feed, readable by any user holding an active `trainer` or `trainee` hat on an engagement where `engagements.cohort_id = training_cohorts.id`.

### 2. Backstage Catalog Alignment (`AC2`)

In `wom7web/project/scripts/catalog_models.py` (`@backstage/catalog-model`):
- A **Training Cohort** maps to `kind: Group`, `spec.type: cohort`, `spec.parent: group:default/<trainer-org>`, `spec.children: ["group:default/<eg-1>", "group:default/<eg-2>", ...]`, with annotation `w0m.dev/engagement-kind: training`.
- Each trainee's **Training Engagement** remains `kind: Group`, `spec.type: engagement`, `spec.parent: group:default/<cohort-slug>` (or `group:default/<trainer-org>` when ungrouped), `spec.children: ["group:default/<eg-i>.trainer", "group:default/<eg-i>.trainee"]`, with singular `w0m.dev/client: group:default/<trainee-personal-org>` and `w0m.dev/cohort: group:default/<cohort-slug>`.

### 3. Build Trigger (`AC3`)

- Because `public.engagements` currently has `0` rows with `kind = 'training'` in production, we do not add dead `training_cohorts` tables ahead of a live cohort (`AgDR-0025`).
- Model A handles any 1:1 or single-employer training immediately today; when the first multi-personal-org training batch is scheduled by `w0m.talent.trainer`, its implementation ticket will add `public.training_cohorts` and `engagements.cohort_id` strictly following Model C (`AgDR-0049`).

## Consequences

- **Positive**:
  - Zero changes or exceptions to `AgDR-0028`'s two-party engagement model, `<contractor>.<engagement>.<client>` addressing, or the 7 engagement-scoped RLS policies.
  - Complete FERPA/GDPR-grade privacy between solo trainees in the same cohort (no leaked grades, code submissions, tuition rates, or private mentoring messages).
  - Clean 3-level Backstage `Group` hierarchy (`trainer-org → cohort → engagement → hat`) validated by existing `catalog_models.py` rules.
- **Negative**:
  - Enrolling $N$ solo trainees into a cohort inserts $N$ rows into `public.engagements` (automated in a single batch enrollment RPC when `training_cohorts` is built).

## What this does NOT decide

- Pricing, tuition amounts, or income-share agreement terms for talent training cohorts.
- Peer code-review mechanics (if two trainees in a cohort are paired for peer review, that is granted via an explicit repo/project hat or `resource_grants` row on the target project, never by merging their engagements).
