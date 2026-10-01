---
id: AgDR-0029
title: "Upwork (and any external marketplace) is a synced source layer that our records link to, never a shape copied into them"
timestamp: 2026-09-27T20:40:00Z
agent: claude-code
model: claude-opus-5-5
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T468
---

# AgDR-0029 — Upwork as a synced source layer

> **Amends** [[AgDR-0028]] decision 1 ("contracts from Upwork or elsewhere belong to an engagement"): an Upwork contract
> is a **source record** in the Upwork layer; the engagement **links** to it. It does not become a row of our
> `contracts`. Owner, 2026-09-27.

## Y-statement

In the context of **T458 S6 (engagements), where 94 of our 98 `contracts` rows, 1,782 `proposals` and 55 rooms / 170
messages are Upwork data copied into our own tables**, facing **copies that are already wrong (the Featherglass contract
is filed under client "Ben Israel", the Meetocean.ai one under "Healthcare"; the owner knows them as Jim Nista and Vadym
Ustymenko) and our model shaped around one marketplace's fields**, we decided **to keep Upwork as its own layer, a
faithful mirror synced from Upwork and owned by the person whose account it came from, and to connect our records to it
only through explicit links (engagement, contract, project, work-history entry → Upwork record)**, to achieve **an
Upwork view that always matches Upwork and a model of ours that stays marketplace-neutral**, accepting **a mirror schema
to build and keep in sync, a one-time move of the copied rows, and a link table instead of convenient columns**.

## Context (measured 2026-09-27, live, read-only)

- `public.contracts`: 98 rows; 94 `source = upwork` (all `CLOSED`, `external_id` = the Upwork contract id,
  `client` = a single text name), 4 `direct`. Client names are unreliable (two confirmed wrong by the owner).
- `public.proposals`: 1,782 rows, all `source = upwork`, 6 linked to a contract.
- `public.platform_rooms` 55 (12 linked to a contract) and `platform_messages` 170, with `source` / `external_id`.
- `public.profile_experience` (work history): 0 rows; already has `source` / `source_id` columns.
- Upwork access exists: `upwork_auth_tokens` (per profile), `upwork_poller_state`, the GraphQL sync
  `/api/profile/upwork-sync`, and the Upwork MCP (48 tools) shown on `/me/account`.

## Decision

1. **The Upwork layer.** A separate schema, `upwork`, mirrors Upwork objects field for field as Upwork returns them:
   contracts (with the client company **and** the client contact person, separately), offers/proposals, rooms and
   messages, and the Upwork organisations they belong to. Every row carries the Upwork id, the account it was synced
   through (the profile's Upwork connection), and `synced_at`. Only the sync writes it; nothing of ours writes it.
2. **Owned by the account holder.** Mirror rows are readable by the profile whose Upwork account produced them, and by
   the root. Syncing is per connection (freelancer, agency, client scopes as Upwork exposes them).
3. **Links, not columns.** One link table connects our entities to source records:
   `source_links(entity_kind, entity_id, provider, source_kind, source_id, linked_by, linked_at)`, with `entity_kind`
   in `engagement | contract | project | work_history | proposal`. Our tables carry no Upwork columns; `source` and
   `external_id` on our tables retire once their rows are linked.
4. **Work history maps to Upwork.** A person may link a work-history entry (`profile_experience`) to an Upwork contract
   synced to their own profile; the entry keeps its own text, the link proves it.
5. **Historical engagements (T458 S6) link to mirror contracts.** An engagement from Upwork history is ours (company,
   hats); its evidence is the linked Upwork contract. Our `contracts` holds only contracts we own (direct or signed
   outside a marketplace); an Upwork contract is not duplicated there.
6. **Marketplace-neutral.** The same pattern serves any later source (another marketplace, a CRM): a mirror schema per
   provider, the same `source_links` table.

## Consequences

- S6 splits: **T468** builds the Upwork mirror, the link table and the one-time move; S6 then creates companies and
  engagements and links each historical engagement to its mirror contract.
- The 94 Upwork `contracts` rows, 1,782 `proposals` and the rooms/messages move to the mirror (re-synced from Upwork
  where possible, so the client names become Upwork's, not our copies'); the rows that reference them
  (`proposals.contract_id`, `platform_rooms.contract_id`, milestones, invoices) are re-pointed or linked.
- Company names for historical engagements come from the mirror's client company, with the owner's corrections
  (Featherglass ← 40963804, Meetocean.ai ← 40441858) recorded as links.

## Answered questions (owner, 2026-09-27: "do all")

| # | Answer |
|---|---|
| Q1 | Sync with Upwork GraphQL and the stored token (unattended); the Upwork MCP for interactive checks only |
| Q2 | All three connected scopes (freelancer, agency, client), each tagged in the mirror |
| Q3 | The 1,782 proposals move to the mirror; the 6 tied to a contract get links |
| Q4 | Rooms and messages move to the mirror; the 12 tied to a contract get links |
| Q5 | Where Upwork cannot return an old record, the copy becomes a mirror row marked `imported_unverified`, corrected by owner links |

## Delivery (three phases, no period with two sources of truth for one record)

- **A** — the `upwork` schema, `source_links`, work-history linking. Additive: nothing existing reads or writes it yet.
- **B** — the sync writes the mirror from Upwork; the legacy copies are not written any more (the old writers are
  switched to the mirror in the same change).
- **C** — the ~19 readers of `contracts` / `proposals` move to the mirror or to links, the copies move out
  (`imported_unverified` where Upwork has no record), and the Upwork columns on our tables are dropped, in one
  migration + deploy.
