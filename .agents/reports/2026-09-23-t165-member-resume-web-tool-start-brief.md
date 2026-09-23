# w0m SDLC Start Brief: T165 — Member Resume/CV Engine & Web Tool

> **Ticket:** [T165](.tasks/T165.md)  
> **Title:** Member Resume/CV Engine & Web Tool — import/export, role/tech targeted generation, visual template PDF printing  
> **Gate:** `w0m-sdlc-start` (Orient / Explore / Ground)  
> **Author:** Antigravity / w0m Engineering  
> **Date:** 2026-09-23  
> **Status:** in-progress  

---

## 1. Verified State & Audit Summary

Mechanically verified via `just ticket-audit T165`, code search, and schema checks across all 7 estate repositories:

- **Tracking Surface Coherence:** ✅ 4/4 agree (ticket file, board row, sync index, issue reference).
- **Existing Foundations (Confirmed Done):**
  - **AC1 (Canonical Schema & Fact Store):** ✅ **CONFIRMED**. Canonical JSON Resume schemas (`project/schemas/cv/jsonresume.schema.json`, `project/schemas/cv/w0m-cv.schema.json`) enforced via `just cv-validate` and `just cv-validate-test` (10 files, 64 experiences, schema valid).
  - **AC2 (Multi-Source Ingestion & Evidence Normalization):** ✅ **CONFIRMED**. `project/scripts/cv_import.py`, `company-aliases.json`, and conflict detection in `conflicts.json` handle normalization, entity aliasing, and multi-source merging.
  - **AC3 (Anti-Hallucination Overclaim Gate):** ✅ **CONFIRMED**. `project/scripts/cv_overclaim_check.py` and `just cv-overclaim-check` strictly enforce that prose assertions trace directly to verified data entries.
- **Pending Foundations to be Delivered (AC4–AC8):**
  - **AC4 (Targeted Resume Synthesis Engine):** ⚪ **Not started**. Need variant synthesis engine in TypeScript / Python selecting verified facts by target role and tech focus.
  - **AC5 (Visual CSS Templates Integration):** ⚪ **Not started in CP**. 6 canonical templates exist in `wom7web/docs/backend/branding/templates/` (`ats-plain`, `classic`, `compact`, `modern`, `print-mono`, `single-page`) but are not yet wired to CP preview.
  - **AC6 (High-Fidelity PDF Printing & Markdown Export):** ⚪ **Not started in CP**. Currently relies on offline Python script (`bake_pdfs.py` / WeasyPrint). Requires browser-rendering / print stylesheet pipeline for CP web export.
  - **AC7 (Member CP Web Tool Experience):** ⚪ **Not started**. `/profile` in `apps/cp` renders `ProfileExperience` and `ResumeParser` upload, but no dedicated resume studio (`/profile/resume` or `/cv` view) for variant selection, live preview, and export.
  - **AC8 (Tenant Isolation & RLS Security Proof):** ⚪ **Not started**. Supabase RLS policies and authz probe suites must guarantee complete tenant isolation for member resumes under `public.profile_resumes` and `public.profile_experience`.

---

## 2. Acceptance Criteria Grounding

| AC | Requirement | Status | Evidence / Implementation Plan |
|---|---|---|---|
| **AC1** | Schema-Enforced Canonical Fact Store | ✅ Met | `project/schemas/cv/*`, verified with `just cv-validate` |
| **AC2** | Multi-Source Ingestion & Evidence Normalization | ✅ Met | `cv_import.py`, `company-aliases.json`, `conflicts.json` |
| **AC3** | Anti-Hallucination & Overclaim Gate (`cv-overclaim-check`) | ✅ Met | `cv_overclaim_check.py`, passes 10 backed / 10 accepted |
| **AC4** | Role- and Tech-Targeted Resume Synthesis Engine | ⚪ Not Started | Synthesis module filtering verified facts into targeted variants |
| **AC5** | Integration of 6 Visual CSS Templates | ⚪ Not Started | Bundle 6 templates into CP, live rendered Markdown preview |
| **AC6** | High-Fidelity PDF Printing & Markdown Export | ⚪ Not Started | Print-optimized CSS media queries + 1-click MD/PDF export |
| **AC7** | Member CP Web Tool Experience (`/profile` & `/cv`) | ⚪ Not Started | Svelte 5 interactive resume studio in `apps/cp` |
| **AC8** | Tenant Isolation & RLS Security Proof | ⚪ Not Started | Strict RLS on `profile_resumes` + multi-tenant test probes |

---

## 3. Dependencies & Blast Radius

### Dependent Systems & Precedents
- **T360 (Personal Profile Experience & Upwork Sync):** Shipped `public.profile_experience` and `public.profile_resumes`.
- **T293 (Member Profile CP UI & Office Scoping):** CP member experience foundation.
- **T420 (Design System Reconciliation):** Pinned shadcn color tokens and removed dead UI debt, ensuring clean Svelte 5 component authoring.

### Blast Radius (Files to Touch)
- **Database (`wom7api`):**
  - `supabase/migrations/*_profile_resumes_variants.sql` (if variant schema extensions or template preferences needed)
- **Monorepo UI & CP (`wom7web`):**
  - `apps/cp/src/pages/member/resume.astro` (or `/profile/resume.astro`)
  - `apps/cp/src/components/member/resume/` (ResumeStudio, VariantSelector, TemplatePicker, ResumePreview)
  - `packages/ui/src/lib/components/wom/` (reusable resume components)
  - `apps/cp/src/styles/resume-templates/` (6 visual CSS templates)
- **Governance & Spec:**
  - `openspec/changes/2026-09-23-member-resume-web-tool/` (`proposal.md`, `specs/`, `tasks.md`)

---

## 4. Risks, Debt & Earned Gotchas

1. **Anti-Hallucination Strictness (AC3):**
   - *Gotcha:* The generator must NEVER invent claims or extrapolate metrics beyond what is in `profile_experience` or `profile_resumes`.
   - *Control:* Enforce `cv-overclaim-check` as an automated gate.
2. **PostgreSQL RLS Permissive Policy Trap:**
   - *Gotcha (LESSONS.md Section 1 line 143):* Permissive policies are OR-combined. Never grant `anon` blanket `USING (true)` beside tenant-scoped policies.
   - *Control:* All tables strictly require `USING (auth.uid() = profile_id)` for both select and write.
3. **Print-to-PDF Fidelity across Engines:**
   - *Gotcha:* CSS `@page` margins, page breaks (`break-inside: avoid`), and custom typography must render identically in modern Chromium print dialogs and headless renderers.
   - *Control:* Standardized `@media print` rules within the 6 visual stylesheets.
4. **Clean Cutover & Zero Fallback Traps (AgDR-0025):**
   - *Gotcha:* No fallback ladders or duplicate data stores. The single source of truth for member facts must remain the canonical relational tables.

---

## 5. Recommended Next Gate

**`w0m-sdlc-spec`**: Author the OpenSpec change proposal (`openspec/changes/2026-09-23-member-resume-web-tool`) defining the detailed requirements, API contracts, CP UI wireframe/interactions, and testable tasks before starting implementation.
