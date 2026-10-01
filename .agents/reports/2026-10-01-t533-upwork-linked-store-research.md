# T533 research: one linked store for Upwork proposals, messages and contracts

Ticket: [[T533]]. Related: [[T468]] (Upwork as a synced source layer: mirror schema, source links), [[T498]] and [[T499]] (Resume Studio curated facts), [[T501]] (the `w0m-personnel` assistant), [[T493]] (the `/me/upwork` pages).
Date: 2026-10-01. Method: read-only. Every number below was measured today against the live database or the local archive; nothing was changed.

## 1. The request

Owner, 2026-10-01: the most valuable part of a proposal is the extra answers submitted with the project details. Messages, proposals and contracts must be linked to each other and all synced to our side. Find the best storage in our own stack. Later: process it all with AI, search mentions and proofs, and use it to enhance the resume in Resume Studio.

## 2. What is stored today, and what is missing

| Item | In Postgres today | Available from Upwork | Gap |
|---|---|---|---|
| Proposal cover letter | 1,782 of 1,782 (4.2 million characters, average 2,359) | yes | none |
| **Screening answers** (`questionsAnswers`) | **0** | **725 proposals, 1,894 question and answer pairs, 550 KB in total** (in the local archive) | **never written to the database** |
| Proposal terms (rate, duration) | 0 | all 1,782 rate, 170 duration | never written |
| **Job details** | `id` and `title` only, 87 characters on average | the MCP response carries `marketplaceJobPosting.content` with the title only | **the description, budget and skills are not in the response we request at all** |
| Proposal to contract link | 6 of 1,782 | not in the response | 67 of 73 Hired proposals unlinked |
| Room to proposal link | 46 of 55 rooms (all 55 name one in their data) | yes | 9 rooms unlinked though they name a proposal |
| Room to contract link | 12 of 55 | yes (`contractId`) | 43 |
| Messages | 170 in 15 of 55 rooms; **40 rooms have none**; the `direction` column is empty on all 170 | per-room history | the message sync is shallow |
| Contract detail | `title`, `status`, dates, `client` (182 characters) | `offerId` on 87 of 95 | no terms, budget, hours or feedback |

Where the answers sit: `wom7web/project/scripts/upwork_harvest_proposals.py` calls the Upwork MCP tool `upwork__list_freelancer_proposals` with `action: get`, keeps the full response as `raw_proposal` in `project/data/upwork/proposals_archive.jsonl` (10.8 MB, 1,782 lines), and writes only a reduced record to Postgres. **So the answers exist on this machine and were dropped on the way in. The gap is ours, not Upwork's.** The answers are spread across statuses: Archived 400, Accepted 110, Declined 82, Withdrawn 67, Activated 41, Hired 25.

Not verified: that the Upwork MCP or its GraphQL can return the job description, budget or skills. The schema file in `wom7ext/extension/specs/upwork.graphql` is a 225-line hand-written subset (22 types) and says nothing either way. The only way to know is a schema introspection call with the owner's token, which I did not make.

## 3. Linking: what is deterministic and what is a guess

| Link | Key | Today | Reachable with what we hold |
|---|---|---|---|
| room to proposal | `room.vendorProposal.id` | 46 of 55 | **55 of 55** (9 more by backfill) |
| room to contract | `room.contractId` | 12 of 55 | 12 |
| proposal to contract | via a room that carries both ids | 6 of 1,782 | the same 6 (checked: each proposal with a `contract_id` matches a room carrying that pair); no new links from this key |
| proposal to contract | `contract.offerId` to `offer.vendorProposal.id` | 0 | up to 87 contracts, but needs an offer fetch whose MCP tool name I have not confirmed |
| proposal to contract | exact title match | none | **50 of 73 Hired match exactly one contract**, 4 are ambiguous, 19 have no match; 56 of 95 contracts match a Hired title |

The title match is only a candidate. It must never be written as if it were a deterministic link: store it with a `link_basis` (`room`, `offer`, `title`) and a state (`confirmed`, `inferred`), and let the offer key replace it when it can be fetched.

## 4. Storage options, with the corpus measured

The whole corpus is small: the database is 83 MB, `proposals` is 11 MB, `platform_messages` is 456 kB, the screening answers are 0.55 MB, and the message text is 70 KB. Text to process is about 5 MB (roughly 1.2 million tokens at 4 characters each, an estimate).

| Option | Fit | Why |
|---|---|---|
| **Postgres (Supabase), with pgvector and full-text** | **best** | One system of record. `vector` 0.8.2 is installed and there is a 1024-dimension convention (`documents.embedding`). RLS by `profile_id` already scopes every table, which an owner-only corpus needs. Foreign keys give real link integrity, and it joins directly to `profile_cv_facts` for proofs. The T468 mirror schema (`upwork.*`) already exists and is empty. |
| Supabase Storage bucket `upwork` (private) | right for raw snapshots only | 327 objects, 354 kB. Keep the immutable raw MCP response per proposal for audit and replay. Not for querying. |
| Cloudflare Vectorize, R2 or D1 | no | A second store for about 20 MB, outside RLS and outside transactions; a link between a vector hit and its proposal row would be an unchecked reference. |
| Tinybird | no | It is the log and analytics sink (T43), not a document store. |
| Local JSONL archive | source of the backfill only | 10.8 MB on one laptop is the single-copy problem the push-cadence rule exists for. |

**Recommendation.** Postgres for everything queryable, in two layers:

1. **Source layer** (T468's `upwork.*`, or the public tables it feeds): proposal, room, message and contract rows with typed columns, the raw response in `raw jsonb`, `import_state`, and the link columns above. Add `questions_answers jsonb` and `terms jsonb` to proposals; add job detail columns once the source is confirmed.
2. **Evidence layer** (new): one row per citable passage, with `profile_id`, `source_kind` (`proposal_answer`, `cover_letter`, `message`, `contract`), `source_id`, the passage text, a `tsvector`, a `vector(1024)` embedding, and the links to its proposal, room and contract. This is what search, the assistant and Resume Studio read.

Size estimate for the evidence layer: about 1,500 to 3,000 passages of roughly 2,000 characters; a 1024-dimension float vector is 4 KB, so 6 to 12 MB, and an HNSW index roughly doubles that. Under 40 MB in total.

## 5. What already exists, and is idle

- Triggers `tr_vectorize_proposal`, `tr_vectorize_contract` and `tr_vectorize_job` call `trigger_vectorize_vault()`, which posts a webhook to a Cloudflare worker. **They do nothing today**: the function returns at once when `app.settings.cf_worker_url` is empty, and the database settings hold only `jwt_exp`. `public.documents` has 104 rows and none come from a table.
- The worker has `VectorizeVaultWorkflow`, `VectorizeJobWorkflow`, `VectorizeProfileWorkflow` and a `/ai/embed` route that proxies Workers AI embeddings.
- **Decision needed before reuse:** those triggers write into `public.documents`. Verified today: it has no `profile_id` column (columns: `id`, `content`, `metadata`, `embedding`, `is_public`, `access_scope`, `is_seo`, `category`, `created_at`), row security is on, and its read policies are by visibility, not by owner (authenticated users read `public` and `authenticated` scopes, anon reads `public`, the service role reads all). Proposals and messages are private to one member: in that table they could only be stored as an internal scope, which no member could read through RLS (so no member-facing search), and a wrong scope value would publish them to every signed-in user. The evidence layer should be a separate, owner-scoped table, and the old triggers retired or repointed, not left firing.

## 6. How the later uses would read it

- **Search for mentions.** Hybrid: a `tsvector` match for exact terms (a technology, a client, a name), a vector match for meaning, and a reciprocal-rank merge. Full-text needs no new extension; `pg_trgm` would help fuzzy names and is not installed (it is a Supabase-supported extension, to be enabled by migration).
- **Proofs.** A `profile_cv_facts.highlights` entry gains an optional list of evidence references (`evidence_id` plus the quoted span). A claim in a resume then points at the passage that supports it, which is what lets `w0m-personnel` check "no invention" against a source, not against the member's other text.
- **Resume Studio.** The assistant proposes a rewrite of a highlight, cites the passages it used, and the member approves; nothing is written without approval (the T501 rule).
- **Privacy.** Client names in proposals and messages are personal data of third parties. The evidence layer inherits owner-only RLS, and any output that leaves the member (a published resume, [[T510]]) must pass the existing masking rule, not the raw passage.

## 7. Open questions, with a recommendation each

1. **Can the Upwork MCP return the job description, budget and skills?** Recommend an owner-run introspection (`just upwork-schema-probe`, to be written), read-only, run with the owner's token. Weight: decides whether "project details" can be had at all; cheap.
2. **How are Hired proposals tied to contracts?** Recommend the offer key if the MCP can fetch an offer, with the title match as a labelled fallback. Weight: 67 of 73 Hired proposals today.
3. **Why are 40 of 55 rooms empty?** Traced (section 8): not the old `StoryFilter` bug, which is fixed and now throws. The 40 were all created on 2026-07-20 and retried for 61 days of successful runs without gaining a message, so they are probably empty at Upwork; unproven until the feed is alive again.
4. **Reuse the dormant vectorize triggers, or replace them?** Recommend replace, with an owner-scoped evidence table (section 5). Weight: avoids private text in a shared table.
5. **Embedding model and cost.** Not measured: the model behind `/ai/embed`, its dimension, and its price. Recommend measuring on 100 passages before committing to 1024 dimensions and to reprocessing 1.2 million tokens.

## 8. Update: the sync itself has been dead since 2026-09-19

Found while tracing the empty rooms; filed as [[T535]]. Measured read-only from `admin_activity_logs` and token metadata (no token text read).

| Fact | Value |
|---|---|
| Runs per day until 2026-09-19 | 48 successes (41 that day) |
| Failures since 2026-09-19 20:00 UTC | **582 in a row**, one every 30 minutes, to 2026-10-01 22:30 |
| The one failure message | "Could not authenticate any Upwork connection contexts. Check auth tokens." (no cause recorded) |
| Newest stored access token | expired 2026-09-20 02:30 UTC, 11.8 days ago; row last updated 2026-09-19 |
| What the last good runs synced | contracts 95, rooms 50, **proposals 0, messages 0** |
| Any alert or freshness gate | none: the T155 gate checks coverage, not age |

Consequences for this research: (a) a live sync cannot be tested until it is revived, which needs the owner's re-authorization if the refresh token is dead; (b) the local MCP harvest (`upwork_harvest_proposals.py`) uses a separate OAuth session and is the only path that carried the screening answers, so the backfill of the 725 archived proposals does not depend on the poller; (c) the poller reads only new items on its proposal leg, so even a revived poller would not backfill answers by itself.

Message fetch details: `roomStories` carries the `StoryFilter` fix and throws on schema errors; the poller fetches messages for at most 10 rooms per run, retries rooms that hold none, and wraps the entire room loop in one `try`, so one failing room stops all rooms after it. `direction` is never set.
