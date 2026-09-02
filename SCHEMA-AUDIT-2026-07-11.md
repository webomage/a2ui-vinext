# Schema Audit — Contracts, Proposals & Money Model

*2026-07-11. Sourced from the LIVE DB (information_schema + data), not the migration files
(which lagged). Purpose: master the entity model so we can decide the contracts refactor +
accounting wiring.*

---

## Executive summary

1. **The multi-source refactor is ALREADY DONE.** `contracts` and `proposals` already have
   `id uuid` PK + `source text NOT NULL` + `external_id text` (Upwork id lives in `external_id`).
   Migration `20260708200000_generic_contracts.sql`. **Do not rebuild it.**
2. **Contracts are already wired to AR.** `invoices.contract_id → contracts` and
   `client_milestones.contract_id → contracts` exist; `invoices` is multi-platform
   (`platform`, `external_invoice_id`). Migration `20260708000000_economy_and_multiplatform.sql`.
3. **Only Upwork DATA exists.** 188 contracts + 539 proposals, all `source='upwork'`;
   `invoices` = 0 rows; `payment_status` all null; wallets are `operations`-backed, not contract-backed.
   The multi-source *capability* is unused.
4. **Real remaining gaps:** (a) direct proposal↔contract mapping, (b) message history,
   (c) sync-health observability, (d) contract→economy and contract→documents links.
5. **Migration hygiene flag:** 5 committed migrations are **unapplied** to prod (the
   `ai_models`/scout changes) — live `ai_models` was set out-of-band. Reconcile.

---

## 1. Entity map — the money/contract cluster (live FKs)

```
blueprints(id uuid, blueprint_id text slug) ◄── contracts.blueprint_id
                                            ◄── proposals.blueprint_id
                                            ◄── projects.blueprint_id
clients(id) ◄── contracts.client_id, invoices.client_id, projects.client_id, leads.client_id
            ◄── client_users.client_id
projects(id) ◄── contracts.project_id, proposals.project_id
             ◄── gamification.adventures.project_id, gamification.billing_circles.project_id
contracts(id uuid, source, external_id, client_id, project_id, blueprint_id, payment_status, data jsonb)
   ◄── invoices.contract_id
   ◄── client_milestones.contract_id ◄── revision_requests.milestone_id
   ◄── engagement_closures.contract_id
proposals(id uuid, source, external_id, blueprint_id, project_id, data jsonb)   ← NO link to contracts
leads(id, client_id) ◄── lead_proposals.lead_id, lead_artifacts
economy(gamification): projects → billing_circles(treasury) ; wallets(player, backing_ref) ; withdrawals(payouts) ; xp_ledger ; operations_treasury
```

Key shape notes:
- `contracts`/`proposals` keep the raw Upwork payload in **`data jsonb`**; only a few columns are promoted.
- `contracts.payment_status` exists but is **unused** (all null) — a ready hook for AR status.
- `documents` (102 rows) is the **RAG/KB vector store** (`embedding` column) — **NOT** contract documents.

## 2. State vs the five requirements

| Requirement | State | Detail |
|---|---|---|
| Live Upwork sync (API key) | ✅ working & stable | cron ~30min, `SYNC_UPWORK_SUCCESS`, 188 contracts / 539 proposals |
| Multi-source contracts | ✅ **schema done** (unused) | `id uuid + source + external_id`; only `upwork` data so far |
| Proposal ↔ contract mapping | ❌ missing | related only *indirectly* via shared `project_id` |
| Full message history | ❌ net-new | no messages table; poller syncs contracts+proposals, not rooms |
| Sync-status verification | ⚠️ thin | `upwork_poller_state` = seen-tracker (item_id/type); no run/health/error model |
| Contracts → accounting | 🟡 partial | AR done (`invoices`,`client_milestones`); economy + docs not linked |

## 3. Findings & inconsistencies

- **F1. Two "proposals" tables** — `proposals` (Upwork sync, 539) vs `lead_proposals` (internal pipeline). The `2026-07-11` conversion change adds blueprint/adventure to `lead_proposals`; the Upwork one is separate. Naming collision risk for implementers.
- **F2. Two "blueprint" ids** — `blueprints.id` (uuid) vs `blueprints.blueprint_id` (text slug, e.g. `ai-rag-llm`). Existing FKs (contracts/proposals/projects) all use the **uuid**. The conversion spec's "blueprint_id text slug" on `lead_proposals` contradicts this — should be uuid FK.
- **F3. proposal↔contract only via project** — on Upwork a won proposal becomes a contract; that lineage isn't persisted (no FK), only inferrable if both share `project_id`.
- **F4. No message history** — proposal/contract conversations live only inside Upwork; `data jsonb` may hold snapshots but there's no queryable thread.
- **F5. `payment_status` unused, `invoices` empty** — AR plumbing exists but has never carried a transaction.
- **F6. Economy not contract-backed** — `wallets.backing_type='operations'`; the only bridge from a contract to crew payouts is `contract → project → billing_circle(treasury) → wallets/withdrawals`, and no code populates it from contract value.
- **F7. `documents` ≠ contract docs** — it's the RAG store; signed contracts/receipts have no home.
- **F8. 5 unapplied migrations** — `2026071023xx…2026071101xx` (ai_models scout/fallback) are committed but not pushed; live `ai_models` differs from what a fresh migrate would produce.

## 4. Wise proposals (per gap)

**P1 — Proposal↔contract mapping.** Add `contracts.proposal_id uuid REFERENCES proposals(id)` (a
contract has at most one originating proposal). Populate from the poller for `upwork` (Upwork exposes
the proposal→contract relation) and set directly for `direct` on acceptance. Cheap, unlocks the funnel
report "proposal → won contract → revenue".

**P2 — Message history.** New `contract_messages` (`id, contract_id?, proposal_id?, source,
external_msg_id, author, direction, body_md, sent_at, data jsonb`). Extend `upwork-poller` to sync
Upwork **rooms/messages** for each contract/proposal (incremental by `external_msg_id`). Reuse the
`chats` table? No — `chats` (4020) is the site AI chat; keep client/upwork threads separate.

**P3 — Sync-health observability.** Add `sync_runs` (`id, provider, started_at, finished_at, status,
items_checked, items_new, error text`) written by every poller run; keep `upwork_poller_state` as the
dedup index. Surface latest per provider in `get-upwork-status` + a CP "Integrations health" panel
(freshness, last error, item counts). This is what "verify sync status, make it stable" needs.

**P4 — Accounting wiring (the decision).** Three layers, pick per appetite:
- **(a) AR / client billing — ALREADY DONE.** `invoices.contract_id`, `client_milestones`. Just start
  writing rows (populate `payment_status`, generate invoices from milestones). *Recommend: turn on.*
- **(b) Economy / crew payouts — bridge exists, unused.** Wire `contract (value) → billing_circles.
  deposit_ref (project treasury) → wallets → withdrawals`. This is **legal-gated** (KYC/AML per the
  economy design). *Recommend: spec separately, gate behind compliance; not v1.*
- **(c) Contract documents — net-new.** New `contract_documents` (or reuse the CV/deck PDF generator
  surface) for signed contracts, statements, receipts — **not** the RAG `documents` table.
  *Recommend: light `contract_documents` table + link to the existing generator.*

**P5 — Migration hygiene.** Decide whether the 5 pending `ai_models` migrations should be applied
(`just db-migrate`) or superseded/deleted to match the out-of-band live state. Don't leave them dangling.

## 5. Recommended sequencing

1. **Reconcile migrations** (P5) + document that contracts/proposals are already multi-source (so the
   `2026-07-11` "add platform/platform_ref" tasks are **obsolete** — the columns exist as `source`/`external_id`).
2. **P1 proposal↔contract FK** + **P3 sync-health** — small, high-leverage, make the existing sync trustworthy.
3. **P2 message history** — moderate (schema + poller rooms sync).
4. **P4a** turn on AR (invoices/milestones from contracts).
5. **P4c** contract_documents; **P4b** economy payouts as a separate, compliance-gated change.

*All of the above is spec-first; nothing here is implemented yet beyond the existing multi-source schema.*

---

## 6. Beyond Supabase — system-of-record map

*(Added per "we're not limited by Supabase only.")* The money/contracts/docs model spans
several systems already wired in the stack. Supabase Postgres should be the **relational index +
RLS layer** that ties them together — **not** the ledger of record for every concern.

| Concern | System of record | Supabase's role | Status in stack |
|---|---|---|---|
| Contract/proposal **source** | Upwork API (+ future: direct, other platforms) | `contracts`/`proposals` mirror via `source`+`external_id` | ✅ live (poller) |
| Client **billing / AR** | **Stripe** (invoices, checkout, webhooks) | `invoices` = local mirror (`platform`,`external_invoice_id`,`contract_id`) | 🟡 Stripe fns exist (`stripe-checkout`,`stripe-webhook`); `invoices` table empty |
| Crew **payouts / AP** | **Crypto rail (Solana)** + `withdrawals` ledger | economy tables as ledger; `withdrawals.destination_address` | ❌ `process-payout` is a `// TODO: Solana Web3` stub; legal-gated |
| Internal **value/tokens** | gamification economy (`wallets`,`xp_ledger`,`billing_circles`,`operations_treasury`) | authoritative (it's Postgres-native) | 🟡 built; 2 ops-backed wallets |
| **Documents** (contracts, receipts, statements) | **Cloudflare R2** (blob) + PDF generator | `contract_documents` = metadata/index → R2 key | ❌ new; R2 already used for assets/resumes |
| **Sync orchestration** | **Cloudflare Workers/Workflows** (poller already a workflow) + Queues for backfill | `sync_runs` health table written by the workflow | 🟡 poller live; health model missing |
| **Messages** | Upwork rooms API (source) | `contract_messages` index | ❌ new + poller extension |

**Revised accounting recommendation (P4, multi-system):**
- **AR:** don't build a bespoke invoice engine — drive billing through **Stripe** (already wired) and
  keep `invoices` as the queryable mirror linked to `contract_id`. Upwork contracts carry Upwork's own
  billing; `invoices.platform` distinguishes `stripe` vs `upwork`.
- **Docs:** store blobs in **R2**, index in a small `contract_documents` table (never the RAG `documents`).
- **Payouts:** finish the **Solana** rail behind the compliance gate; economy tables stay the ledger.
- **Orchestration:** run sync + message backfill + webhook ingestion on **CF Workers/Workflows**;
  write `sync_runs` health to Postgres for the CP panel.

Net: the entity/RLS graph lives in Supabase; **money moves through Stripe (in) and Solana (out); docs
live in R2; orchestration runs on Cloudflare.** Supabase links them by `contract_id`/`external_id`.
