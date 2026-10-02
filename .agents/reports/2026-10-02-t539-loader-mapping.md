# T539 AC2: file to database mapping for the Upwork loader (2026-10-02)

Sources read: the Drizzle table definitions (`wom7api/supabase/functions/_shared/database/schema.ts`), the old poller's writes (`upwork-poller/index.ts`), the T155 backfill (`wom7web/project/scripts/backfill_upwork_proposals.py`), the laptop sync (`upwork_mcp_sync.py`), and the four data files in `wom7web/project/data/upwork/` (counts and key names only; no value was printed). Live counts are the ones the health gate printed earlier today: 95 contracts, 55 rooms, 170 messages, 15 rooms holding messages, 1,782 proposals.

**Not verified live, and why.** From this machine the system resolver could not look up the database host (`dig` and HTTPS to the REST endpoint both worked, so it is a local resolver problem, not an outage), and the REST service key answered 401. So the unique constraints, the id formats of the stored rows and the file-versus-database overlap are NOT checked against the live database here. They are checked by the loader's own dry run (T539 AC4), which prints the overlap before anything is written.

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
