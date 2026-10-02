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

## 9. Can the poller run as an MCP client? Measured 2026-10-02

Question from the owner: the Upwork API needed a separate key per context; could a poller instead be an MCP client using each unit member's own connection?

**Measured (no secrets read; key names and public metadata only):**

| Fact | Evidence | Meaning |
|---|---|---|
| The MCP server's OAuth is Upwork's own OAuth | `https://mcp.upwork.com/.well-known/oauth-authorization-server`: `authorization_endpoint` `www.upwork.com/ab/account-security/oauth2/authorize`, `token_endpoint` `www.upwork.com/api/v3/oauth2/token` (the same endpoint `_shared/upwork.ts` refreshes against) | one identity system, not two |
| Grants offered | `authorization_code`, `refresh_token`, `client_credentials`; PKCE `S256` only | a refresh needs no browser; `client_credentials` is unexplored |
| Clients register themselves | `registration_endpoint` `www.upwork.com/register`; the local `mcp-remote` client is `token_endpoint_auth_method: none` (public, PKCE), `client_secret_expires_at: 0`, issued 2026-08-26 | no API key or secret to manage per context |
| Token shape | `expires_in` 86400, `refresh_token` present | same 24 h as the API token |
| Longevity | the registration is 37 days old and the token file was rewritten about 4 hours before this check | consistent with unattended refresh; NOT proof of refresh-token lifetime |

**Not measured (each decides the design):**
1. Whether `tools/list` exposes contracts, rooms and messages (the poller needs `roomList` and `roomStories`). The owner-run schema probe answers it.
2. Whether a token from a client we register ourselves is accepted by `mcp.upwork.com/mcp` from a server address.
3. Whether the refresh token rotates, and its lifetime. Rotation means one writer per grant: the laptop's `mcp-remote` and a server must never share one.
4. Whether an MCP-issued access token is also accepted by `api.upwork.com/graphql`. If yes, the existing poller code works unchanged with a different token source.
5. Rate limits for MCP calls (unpublished).

Sources: [Upwork MCP](https://www.upwork.com/ai/mcp), [Upwork GraphQL API docs](https://www.upwork.com/developer/documentation/graphql/api/docs/index.html).

## 10. The probe's result, 2026-10-02 (owner run; report `2026-10-02-t533-upwork-schema-probe.md`)

**Point 1 of section 9 is answered: yes.** The MCP offers 51 tools, and the poller's whole read surface exists in them:

| The poller needs | MCP tool and actions |
|---|---|
| rooms and messages | `upwork__get_messages`: `list_rooms`, `find_room`, `search_rooms`, `list_messages`, `get_message` |
| contracts | `upwork__list_contracts`: `list`, `get`, `search`, `timesheets`, `end_reasons`; `upwork__list_milestones` |
| offers (the link from a proposal to a contract) | `upwork__list_offers`: `get`, `list`, `list_mine`, `get_attachments` |
| proposals | `upwork__list_freelancer_proposals`: `get`, `list`, `invitations`, `get_room` (a proposal-to-room link) |
| the job behind a proposal | `upwork__find_jobs` `get`: not probed yet, so unknown whether it returns description, budget and skills for an old, closed posting |

**Proposal fields (5 of 5 fetched), against what we store.** The source returns `questionsAnswers[].question/answer`, `terms.chargeRate`, `terms.connectsBid`, `status.reason`, `auditDetails` dates and `marketplaceJobPosting.{id,url,content.title}`. The job posting inside a proposal carries only a title: no description, no budget, no skills. The screening answers are confirmed as the part of the response we did not store.

**A cost the section 9 sketch did not have: many of the 51 tools write.** The probe's own verb rule flags at least 19, and it misses some (`confirm_preview` executes any pending write, `end_contract`, `manage_meetings`, `save_job`), so no exact count is claimed here; what matters is that a read-only allowlist, not a deny-list, is the safe shape. Examples: `send_message`, `manage_proposals send_proposal/withdraw`, `post_job`, `end_contract`, `update_profile`, `manage_milestones`, `respond_to_offer`, and `set_tool_permission`, which can switch a tool's confirmation off). An MCP token held by a server can call them, where an API token is bounded by the scopes granted to the key. The MCP defaults write tools to `always_ask` confirmation, which protects a human session and does nothing for an unattended one. Any server-held MCP token needs the read-only tool allowlist the probe already enforces (`call_allowed`) built into the poller.

**Point 4 (does the MCP token work on `api.upwork.com/graphql`): not settled.** The probe got HTTP 403 with a body that was not JSON. Measured the same day with a dummy token: the same endpoint answers HTTP 401 with a JSON body for every User-Agent tried, so the 403 is not a User-Agent block and the endpoint distinguishes the two tokens. The probe now records the body's kind, size and a masked snippet so one more run can say whether this is the API refusing a recognised token or an edge page.

**Probe rerun (same day, with the body-shape recording):** the GraphQL check came back HTTP 403 with an HTML page (5,018 bytes, a Cloudflare-style template), not the API's JSON. The same Python transport with a dummy token gets a JSON 401 for every User-Agent tried, so the client is not the cause: a real MCP token is refused at the edge or gateway and a malformed one is not. Practical verdict: **the MCP token does not work on `api.upwork.com/graphql` from here**, so an MCP-sourced token cannot feed the existing poller unchanged, and a poller on the MCP would be a new client (rooms and messages are available there, see above). The API-key sign-in route stays the way to revive the current poller.

## 11. Spike result (a), 2026-10-02: Upwork's MCP registration refuses an https redirect

Owner ran `upwork_mcp_spike.py register` with `https://webomage.com/upwork-mcp-spike`: HTTP 400 `invalid_redirect_uri`, no client created. [n8n community report](https://community.n8n.io/t/mcp-oauth-dynamic-client-registration-fails-with-upwork-mcp/309437) and a [plugin PR](https://github.com/nvdigitalsolutions/mcp-ai-wpoos/pull/6794) report the same: loopback registers, public https does not (community reports, not an Upwork statement). The PR also reports HTTP 415 for JSON token requests, so token requests are form-encoded.

What this changes in the decision of section 9:
- A member connecting "from a profile page" through the MCP's own registration cannot use an https callback on our domain. The workable shapes are (1) a loopback redirect with the member pasting the address they land on back into w0m, (2) the existing Upwork API-Center app as the client, if the MCP accepts its tokens (untested), (3) a hosted client-metadata document, if Upwork applies a different redirect rule to it (untested), (4) Upwork allow-listing our redirect (a support request).
- The MCP's data is GraphQL-shaped (`data.vendorProposal`, the same wrapper the API returns). The screening answers we never stored may therefore be requestable from the API poller too; untested, because the API token is dead.
- What the MCP adds is Upwork's OAuth and tool surface, not data the API cannot return. The case for it rests on onboarding, which (a) just weakened.

## 12. How the MCP sync worked "last time", 2026-10-02 (read from the repository, nothing run)

It was never a server-side sync. It was the owner's laptop, using the owner's own MCP session.

| Step | What | Where |
|---|---|---|
| 1 | `just upwork-mcp-sync` runs `project/scripts/upwork_mcp_sync.py`, which starts `pnpm dlx mcp-remote https://mcp.upwork.com/mcp` and speaks JSON-RPC to it. `mcp-remote` registers itself as a public client ("MCP CLI Proxy") with a LOOPBACK redirect (`http://localhost:23037/oauth/callback`), runs a tiny local server there to catch the authorization code, and keeps the tokens in `~/.mcp-auth/`. | the owner's machine |
| 2 | The script reads contracts (`list_contracts search`), proposals (`list_freelancer_proposals list` and `invitations`), rooms and messages (`get_messages list_rooms`, `list_messages`), the profile (`get_profile get`) and the agency dashboard (`get_agency_dashboard check`), for the freelancer and agency contexts. | MCP |
| 3 | It writes line-delimited files to `project/data/upwork/` (`contracts.jsonl`, `proposals.jsonl`, `rooms.jsonl`, profile JSON) and markdown notes to the vault. Last written 2026-08-19. It makes NO database call. | the repository |
| 4 | `just upwork-harvest-proposals` (`upwork_harvest_proposals.py`) does the same for the full proposal history: `list_freelancer_proposals list` then `get`, keeping the whole response as `raw_proposal` in `proposals_archive.jsonl` (1,782 lines, last written 2026-08-19). | the repository |
| 5 | `backfill_upwork_proposals.py` (T155, 2026-09-15) loads cover letters and tags from the archive into `public.proposals`. Nothing equivalent loads rooms or messages from the JSONL into the database. | the database |

The CP button "Verify & Sync MCP" (`apps/cp/src/pages/api/sync/upwork-mcp.ts`) only calls that same Python script when the route runs under local Node. On the deployed Cloudflare runtime the call always throws, the route falls into "edge mode" and merely counts rows, and the response says no sync ran. So the button has never done a server-side sync.

What reached the database: contracts and rooms from the API poller (which died on 2026-09-19), proposals from steps 4 and 5. Messages stayed at 15 rooms because the poller's room-fetch budget was 10 per run.

Consequences for T537:
1. The MCP session that worked is the loopback mechanism option 2 describes, on one laptop. "MCP sync" was proven for the owner, locally, not for members or servers.
2. The owner's `mcp-remote` session is alive now (its token file was rewritten about 4 hours before the 2026-10-02 probe), so the laptop scripts can bring contracts, proposals, rooms and messages current today with no new sign-in.
3. The scripts call `get_profile` and `get_agency_dashboard`, which the T537 allowlist does not list. They are reads, but the allowlist decides for server code only; whether the connector needs them is a decision, not an oversight to patch silently.

