# Plan Progress & Urgent Findings Strategic Review (2026-09-29)

**Date**: 2026-09-29  
**Estate**: w0m (`@wom` umbrella)  
**Primary Ticket Context**: [[T488]] (Closed) · [[T482]] (Closed) · [[T478]] (Closed)  
**Companion Diagram**: [2026-09-29-t488-plan-progress.mmd](file:///Users/proto/Projects/@self/@wom/.agents/reports/2026-09-29-t488-plan-progress.mmd)

---

## 1. Executive Summary: The 3 Progress Planes

### Plane 1: Recently Shipped & Closed
1. **[[T482]] — SkillOpt Nightly Self-Evolution Harness & Harvester**:
   - Harvester implemented in `scripts/sleep_harness.py` for Google Antigravity and Claude Code.
   - Held-out validation gate with 5 canonical SDLC benchmark tasks (`CANONICAL_SDLC_BENCHMARKS`).
   - Local Apple MLX OpenAI-compatible inference backend (`http://127.0.0.1:8888/v1` or `8000/v1`) with offline deterministic fallback.
   - 6 friction rules auto-mined from 148 historical sessions and adopted into `LESSONS.md`.
2. **[[T488]] — Resume Studio, Private CV & Contact Form Security**:
   - Signed URL streaming on private bucket `resumes` via `createSignedUrl` in `ResumeStudio.svelte` (11/11 unit tests, 4/4 Gauge scenarios pass).
   - Old CV and 17 non-public CVs moved to `private/resumes/` as upload source; buttons repointed to 2026 public CV (`Aleksei_CV_2026_Public.pdf`).
   - `contact-submit` email validation enforced (rejects empty/whitespace email with 400).
   - Unauthenticated Turnstile captcha bypass via `testMode: true` closed (now requires `isE2EBypassRequest` or `debugBypassKey`).
   - 12 synthetic contact messages (ids 819-830) safely deleted via migration `20260929090000`.
   - All 6 scenarios in `005-contact-submit-api.spec` pass locally.
3. **[[T478]] — Local Full Regression & Network Live-Guard**:
   - Local stack test environment fixed with in-process live guard refusing live network requests during local runs.
   - 151 failing scenarios triaged and cleanly split into [[T486]], [[T487]], [[T488]], and [[T489]].

---

### Plane 2: Canonical Strategic Plan (`ROADMAP.md §19` — Security & RBAC Hardening)
The active program declared in `.w0m/sdlc.json -> current_plan` is **ROADMAP.md §19**:

- **Stage 0 — Confirmed-Live Exposure**: **100% (16/16 ACs)** ✅
  - `T196` (decommissioning audits git), `T201` (Turnstile captcha replacement), `T329` (authz probe actor binding) all closed.
- **Stage 1 — RLS & Authz Enforcement Residue**: **100% (21/21 ACs)** ✅
  - `T381` (lead-api/guild-api admin authz), `T382` (withServiceRole least-privilege), `T327` (CP staff SSR client audit), `T208` (user_profiles schema) all closed.
- **Stage 2 — Identity & MFA Surface**: **100% (16/16 ACs)** ✅
  - `T53` (profile connected auth & PATs), `T100` (sign-in 2FA challenge) both closed.
- **Stage 3 — Posture Composition & Remaining Hygiene**: **48% (14/29 ACs)** 🔄
  - `T233` (composed `just audit`, 8/8 done) & `T139` (materialized views/columns, 5/5 done) closed.
  - Open items: `T244` (revoked CF token hygiene, 1/5 done), `T213` (job-board sources fail closed, 0/8 queued), `T52` (compromised password checks, 0/3 queued).

---

### Plane 3: In-Flight Engineering Scope & Immediate Candidates

| Ticket | Priority | Status | Progress | Area | Key Objective | Blockers |
|---|---|---|---|---|---|---|
| **[[T476]]** | **P1** | `in-progress` | 2/5 (40%) | security | `/me/account`: merge `ConnectedServices` into `ConnectedIdentities` & `social_integrations` | None (AC1 & AC2 shipped, ready for AC4) |
| **[[T439]]** | **P1** | `in-progress` | 2/12 (17%) | product | CP shell IA — Me / Org / Admin context switcher (#1 on HOT board) | None |
| **[[T290]]** | **P1** | `in-progress` | 3/7 (43%) | product | Stage-4 Money — simulate payment & client billing hats | None |
| **[[T486]]** | **P2** | `queued` | 0/5 (0%) | sdlc | Align stale admin/web Gauge specs with current UI or retire | None (005 already resolved) |
| **[[T489]]** | **P2** | `queued` | 0/2 (0%) | security | Live test-team provisioning & non-founder verification | Owner Touch ID confirm gate (`DEPLOY-CONFIRM.md`) |
| **[[T468]]** | **P1** | `in-progress` | 1/7 (14%) | data | Upwork synced source layer: mirror schema & source links | In progress |

---

## 2. Weighted Decision Matrix for Next Pickup

| Option | Ticket | Cost | Risk | What It Unblocks | Recommendation |
|---|---|---|---|---|---|
| **A** | **[[T476]] AC4** (/me/account identity merge) | Low (S) | Low | Completely eliminates legacy `localStorage` handles, establishes unified identity model in `social_integrations` | **(Recommended)** Finishes high-priority privacy/account epic |
| **B** | **[[T439]]** (CP Shell IA switcher) | Medium (M) | Low | Unifies navigation across Me, Org, and Admin, solving visual IA clutter | Top HOT candidate, large UI surface |
| **C** | **[[T486]]** (Stale spec alignment) | Medium (M) | Low | Cleans up the remaining 150 local test failures, driving suite pass rate >95% | Excellent for regression health |
| **D** | **[[T489]]** (Live test-team provisioning) | Low (S) | Medium | Requires owner Touch ID prompt to provision live test users in Supabase Auth & Infisical | Owner-run action |

---

## 3. Recommended Immediate Action

Execute **Option A: Resume [[T476]] AC4**:
1. Implement the server-backed `social_integrations` persistence and UI component for external handles.
2. Delete the legacy `ConnectedServices.svelte` component (eliminating browser `localStorage` drift).
3. Run `just ticket-audit T476`.
