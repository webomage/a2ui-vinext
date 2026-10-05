# T539 AC2: file to database mapping for the Upwork loader (2026-10-02)

Sources read: the Drizzle table definitions (`wom7api/supabase/functions/_shared/database/schema.ts`), the old poller's writes (`upwork-poller/index.ts`), the T155 backfill (`wom7web/project/scripts/backfill_upwork_proposals.py`), the laptop sync (`upwork_mcp_sync.py`), and the four data files in `wom7web/project/data/upwork/` (counts and key names only; no value was printed). Live counts are the ones the health gate printed earlier today: 95 contracts, 55 rooms, 170 messages, 15 rooms holding messages, 1,782 proposals.

**Verified live on 2026-10-03** (after the WARP reconnect fixed name resolution; read-only transaction, counts and key names only): see the last section. The first draft of this report, written on 2026-10-02, could not reach the database and said so; nothing in it was changed except where the live result differs, and those places are marked.

## What the files hold, and what they cannot give

| File | Rows | Facts |
|---|---|---|
| `contracts.jsonl` | 95 | ids are 8-digit strings, unique, no slug suffix; every `status` is `CLOSED`; keys `clientOrganization{id,name}`, `clientTeam`, `createDate`, `startDate`, `endDate`, `freelancer`, `title`, `id`; `deliveryModel` and `offerId` on 87 |
| `rooms.jsonl` | 18 | ids are 37-character strings with an underscore; keys `roomName`, `topic`, `createdAtDateTime`, `lastVisitedDateTime`, `numUnread`, `recent_messages`, `_context`; 18 of 18 rooms hold messages |
| messages (inside rooms) | 113 | ids 38 characters, unique; keys `id`, `actionVerb`, `createdDateTime`, `message` ONLY: **no author, no direction** |
| `proposals_archive.jsonl` | 1,782 | ids 18 to 19 digits (beyond JavaScript's safe integer range: strings only), unique; 725 carry `questionsAnswers` (1,894 question and answer pairs); 1,759 carry a cover letter; every one carries `terms` and `marketplaceJobPosting.id` |
| `proposals.jsonl` | 11 | a latest-status snapshot; the archive covers all of it |

Three findings that shape the loader:

1. **The files cannot reach what the database already holds.** `upwork_mcp_sync.py` asks for 10 rooms and 10 messages per room (50 rooms with `--full`, but `max_rooms` is 15), and its message reduction keeps only four keys, dropping the author. The database has 55 rooms and 170 messages, with authors from the old poller. The files hold 18 rooms and 113 messages with no authors. A loader fed these files adds rooms and messages but can never set `author` or `direction`. The laptop script itself must change (keep the author's display name, page through all rooms and messages) before the message leg is worth running. That change belongs to T539 AC1.
2. **The old poller overwrote ownership on every conflict** (`profile_id` and `attribution_state = 'attributed'` in its `ON CONFLICT DO UPDATE`). The loader must not: T493 classified contracts by owner decision (including the Northwind demo contract), and a blind re-write would undo it.
3. **The T155 backfill finds the owner by a hardcoded email lookup.** The loader will not guess an owner: `--profile-id` is required, checked to exist, and the dry run prints which profile ids the rows it matched already carry.

## Mapping, per leg

Conventions for every leg: dry run by default, `--apply` to write; one transaction per leg; the idempotency key is the table's own unique constraint (`external_id` with `source = 'upwork'`); a malformed row is counted and skipped; output is counts and key names only, never message text or a body.

### Contracts: `contracts.jsonl` to `public.contracts` (key `contracts_ext_src_unq`)

| File | Column | Rule |
|---|---|---|
| `id` | `external_id` | the bare id, as a string (what the poller's `resolveIdentity` produced; the file ids are already bare) |
| `title` | `title` | required; a row without one is skipped |
| `status` | `status` | as given |
| `clientOrganization.name` | `client` and `data.client` | `Unknown` when absent, as the poller did |
| `startDate`, `endDate` | `data.start_date`, `data.end_date` | `Unknown` and `Present` defaults as the poller did, so a row the file agrees with is not changed |
| `offerId`, `deliveryModel`, `createDate` | `data.offerId`, `data.deliveryModel`, `data.createDate` | additive keys; `offerId` is the proposal-to-contract link [[T533]] AC4 needs |
| (new rows) | `profile_id`, `attribution_state`, `attribution_note` | `--profile-id`, `attributed`, `T539 loader`; **existing rows keep theirs** |
| (existing rows) | `status`, `data` only | updated only when the file is newer than the row (`row.updated_at` against the file's modification time) and the content differs |

### Rooms: `rooms.jsonl` to `public.platform_rooms` (key `platform_rooms_ext_src_unq`)

| File | Column | Rule |
|---|---|---|
| `id` | `external_id` | as a string |
| `topic`, else `roomName` | `topic` | the file already strips the untrusted-content wrapper |
| the room object without `recent_messages` | `data` | the poller stored the whole GraphQL room; same here |
| newest `recent_messages[].createdDateTime` | `last_message_at` | null when no messages |
| (new rows) | `profile_id` | `--profile-id` |
| (new rows) | `proposal_id`, `contract_id` | left null; the file has no link. Resolving them is [[T533]] AC4 (`get_room` on a proposal); **existing links are never overwritten** |

### Messages: `recent_messages[]` to `public.platform_messages` (key `platform_messages_ext_src_unq`)

| File | Column | Rule |
|---|---|---|
| `id` | `external_id` | as a string |
| parent room | `room_id` | the id of the `platform_rooms` row for the parent room's `external_id`; rooms load first; a message whose room is missing is skipped and counted |
| `message` | `body` | as given |
| `createdDateTime` | `sent_at` | ISO 8601 as given |
| `actionVerb`, `id`, `createdDateTime` | `data` | |
| (none) | `author`, `direction` | **null: the file does not carry them** (finding 1). [[T533]] sets direction once the author exists |
| (new rows) | `profile_id` | `--profile-id` |
| existing rows | | **insert-only**: an existing message keeps its author and body; the loader only adds the missing |

### Proposals and screening answers: `proposals_archive.jsonl` to `public.proposals` (key `proposals_ext_src_unq`)

BLOCKED on [[T533]] AC2, as the ticket says. For the record, what is known: `external_id` is the id as a string (the T155 backfill does this); the screening answers are `raw_proposal.questionsAnswers[].{question,answer}`, 725 proposals and 1,894 pairs; `proposals.data` already holds the cover letter. The interim candidate for where the answers land is `proposals.data.questionsAnswers`, stored verbatim, which needs no schema change; whether they instead belong in a layer of their own is the T533 decision, so the loader's first version does not write them.

## Ordering, safety and the freshness row

- Order: contracts, rooms, messages. A failed leg rolls back its own transaction and stops the run; earlier legs stay.
- Newer wins by timestamp, never by file order. Because the database rows written by the dead poller are newer than the 2026-08-19 files, running the loader on the current files would update almost nothing; that is the intended safety, and it is why AC1 comes first.
- On success the loader writes one `admin_activity_logs` row with its own action name (`SYNC_UPWORK_LOADED`) holding per-leg inserted, updated, unchanged and skipped counts. T539 AC5 points the freshness gate at that row.
- The loader never calls Upwork. It reads local files and writes the database, nothing else.

## Verification still owed (T539 AC4)

The dry run must print, from the live database: how many file ids already exist per leg, the `profile_id` values those rows carry (counts only), and how many rows would be inserted, updated or left unchanged. Only after the owner has read that does `--apply` run.

## Verified live, 2026-10-03

Read-only queries through the standard helper. File ids were passed into the SQL as arrays (identifiers only) and only counts came back.

**Unique keys.** All four tables have a plain unique index on `(external_id, source)`, so `ON CONFLICT (external_id, source)` works. Naming drift, harmless for column-based conflicts: the live indexes on `contracts` and `proposals` are `contracts_external_id_source_key` and `proposals_external_id_source_key`, while `schema.ts` declares `contracts_ext_src_unq` and `proposals_ext_src_unq`; `platform_rooms` and `platform_messages` match.

**Ids agree.** Database ids have the same shape as the file ids: contracts 8 digits, bare (no slug suffix; 0 of 95 would match by prefix), proposals 18 to 19 digits, rooms 37 characters, messages 38.

**Overlap, files against the database.**

| Leg | File rows | Already in the database | The loader would insert | In the database but not in the files |
|---|---|---|---|---|
| contracts | 95 | 95 | 0 | 0 |
| rooms | 18 | 17 | 1 | 38 |
| messages | 113 | 82 | 31 | 88 |
| proposals (archive) | 1,782 | 1,782 | 0 | 0 |

Every existing row carries a `profile_id`, and there is exactly one distinct profile across all Upwork rows. All 82 overlapping messages already have an `author`.

**What this changes in the mapping.**
1. **The current files are almost entirely redundant.** The loader on today's files would insert 1 room and 31 messages and change nothing else. The database is newer than the files for every table (newest `updated_at`: contracts 2026-09-25, rooms 2026-09-19, messages 2026-09-09, proposals 2026-09-16; files 2026-08-19), so newer-wins updates nothing. The loader earns its keep only after a fuller sync (T539 AC1).
2. **One exception to newer-wins: additive keys.** The stored contract `data` holds only 5 keys (`title`, `status`, `client`, `start_date`, `end_date`); the file adds `offerId` (on 87 contracts), `deliveryModel` and `createDate`. Missing keys are added to existing rows regardless of timestamp and a key already present is never overwritten. `offerId` is the proposal-to-contract link [[T533]] AC4 needs, and it currently exists nowhere in the database.
3. **Ownership: confirmed as a hard rule.** Contracts are `client_less` 94 and `attributed` 1 (the T493 classification). The loader must not touch `profile_id` or `attribution_state` on existing rows.
4. **Messages.** The database messages carry `data.user` (the author's source) and `direction` is null on all 170. The 31 messages the loader would add come from the file, which has no author, so they would arrive without one.
5. **Room links are largely already there.** Stored room `data` holds `vendorProposal` and `contractId` on all 55 rooms, and `proposal_id` is set on 46 rooms and `contract_id` on 12. The file's rooms carry neither key, so link resolution ([[T533]] AC4) comes from the database, not from the loader.
6. **Proposals and screening answers.** 6 of 1,782 proposals are linked to a contract and none holds `questionsAnswers` in `data` (the answers live only in the archive file: 725 proposals, 1,894 pairs). That leg stays blocked on [[T533]] AC2.

## 2026-10-05 — what changed from the mapping above

- The loader (`upwork_loader.py`) implements this mapping with ONE rule changed: an existing row only GAINS information. The "newer wins by timestamp" rule is gone, because a stored room's `data` holds `vendorProposal` and `contractId` that the file does not carry, and a stored contract's status can be newer than the file's.
- `author` now comes from the file's `from` (the sync keeps it since 2026-10-04) and `direction` from `from_my_organization` (`out` or `in`, the values the CP's `messageView` reads). Existing messages with an empty author or direction are filled; a non-empty one is never replaced.
- Rooms: `topic` is the job name, else the room name; the room object without `recent_messages` is the `data`.
- Proposals and screening answers remain blocked on T533 AC2.
