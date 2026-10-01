---
id: AgDR-0022
title: "Gamification Model A: Pure event-driven reputation and retirement of phantom campaign tables"
timestamp: 2026-09-17T00:00:00Z
agent: claude-code
model: claude-sonnet-5
trigger: user-prompt
status: accepted
superseded_by:
supersedes: AgDR-0016
ticket: T27
---

# AgDR-0022 — Gamification Model A: Pure event-driven reputation and retirement of phantom campaign tables

## Y-statement

> In the context of **T27 (SDLC-as-quests) and T203 review**, facing **a bloated 8-table campaign hierarchy (`adventures`, `raids`, `quests`, `project_questmasters`, `units`, `unit_members`, `unit_slot_templates`, `adventure_role_slots`) holding strictly zero data rows since inception and creating duplicate task-tracking overhead**, we decided **to adopt Model A (Pure Event-Driven Gamification), retiring the 8 zero-row phantom tables in migration `20260917140000_t27_retire_gamification_hierarchy_phantom_tables.sql` and anchoring gamification strictly as an event-driven reputation lens (`xp_ledger`, `wallets`, `badge_definitions`, `badge_awards`)**, to achieve **zero redundant database state, zero task-synchronization drift, and a crystal-clear boundary between the canonical corporate "Web" core and the internal "Mage" guild mechanics**, accepting **that `AgDR-0016` (which settled the FK hierarchy for those 8 tables) is now superseded because the hierarchy itself is retired in favour of event-driven simplicity**.

---

## Context

Under migration `20260702120000_gamification_hierarchy_v2.sql` and `20260625181500_create_clients_and_raids.sql`, eight tables were introduced to model a campaign delivery structure (`gamification.adventures`, `public.raids`, `gamification.quests`, etc.).

Measured on 2026-08-11 and re-verified on 2026-09-17:
- All 8 campaign hierarchy tables held **0 data rows**.
- Real engineering work was tracked canonically in `TASKS.md`, `project/tickets/T##.md`, GitHub issues, pull requests, and `public.projects`.
- Meanwhile, an active gamification economy was already functioning via `gamification.xp_ledger` (audited candidate interview and onboarding seed data), `gamification.wallets`, and `gamification.badge_awards`.

Attempting to build a bidirectional synchronization layer between real engineering work and a shadow database schema (`gamification.quests`, `public.raids`) introduced unnecessary complexity, maintenance debt, and confusion over naming.

On 2026-09-17, the system owner reviewed the gamification architecture and selected **Model A**:
1. **Legacy Corporate Core ("Web")**: Canonical, active, and uncompromised across core schemas (`projects`, `contracts`, `milestones`, `tickets`, `invoices`, `user_roles`), documentation, APIs, and client portals.
2. **Guild Theme ("Mage")**: Applied as an internal motivational and reputational lens for developers and agents.
3. **Pure Event-Driven Mechanics**: No shadow task tables. Real engineering events (`pr_merged`, `pr_bugfix`, `spec_written`, `ticket_completed`, `onboarding_complete`, `milestone_approved`) trigger `award_gamification_xp`, updating `xp_ledger`, `wallets`, and `badge_awards` idempotently.

---

## Decision

1. **Retire the 8 Phantom Hierarchy Tables:**
   The following zero-row relations and their helper functions/triggers are dropped in `wom7api/supabase/migrations/20260917140000_t27_retire_gamification_hierarchy_phantom_tables.sql`:
   - `gamification.adventures`
   - `gamification.adventure_role_slots`
   - `public.raids`
   - `gamification.quests`
   - `gamification.project_questmasters`
   - `gamification.units`
   - `gamification.unit_members`
   - `gamification.unit_slot_templates`
   - Helper functions: `raid_budget`, `adventure_budget`, `quest_project_id`, `default_adventure_for`, `raids_attach_default_adventure`, and trigger `trg_raids_default_adventure`.

2. **Surviving Core Gamification Tables:**
   The gamification schema is preserved strictly for reputation, progression, and economic tracking:
   - `gamification.xp_ledger` (immutable append-only event log)
   - `gamification.wallets` (cached player balances)
   - `gamification.badge_definitions` & `gamification.badge_awards` (achievement system)
   - `gamification.player_xp_totals` (security_invoker aggregation view)
   - Treasury/compliance relations: `operations_treasury`, `billing_circles`, `withdrawals`, `compliance_profiles`.

3. **Public Schema Invariants:**
   - `public.units` is **untouched** — it represents org-chart role slots/vacancies in the corporate matrix and has no relation to the dropped `gamification.units`.
   - `public.onboarding_quests` and `public.player_onboarding_progress` are **untouched** — they govern user onboarding checklists in `apps/join`.

4. **UI & API Modernization:**
   - CP Guild menu is streamlined to `Bounty Board` (`/guild/bounties`) and `Certifications` (`/guild/certifications`).
   - `QuestBoard.svelte` renders live player standings, earned badges, recent XP ledger entries, and development bounty guidelines.
   - Legacy routes (`/business/adventures`, `/business/raids`) 301 redirect to `/guild/bounties`.
   - `guild-api` edge function returns 410 Gone for retired hierarchy operations, while preserving `enroll_certification` and `complete_onboarding_quest`.

---

## Consequences

- **Positive:**
  - Zero duplicate database state or sync lag.
  - Zero risk of orphan quest records diverging from git/ticket reality.
  - Simplified codebase: removes ~400 lines of dead CRUD and schema overhead.
  - Client portal and corporate systems remain 100% professional and audit-ready with no fantasy naming contamination.
- **Negative / Trade-offs:**
  - Bounties in the CP UI are driven from repository tickets and ledger milestones rather than ad-hoc quest CRUD.
  - Supersedes `AgDR-0016`, rendering past discussions on adventure/raid FK direction obsolete.
