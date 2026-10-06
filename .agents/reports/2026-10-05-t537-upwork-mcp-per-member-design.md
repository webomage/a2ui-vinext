# T537: Upwork on the MCP, per member, and later as a service (design, 2026-10-05)

Scope decided by the owner on 2026-10-05: **team members with w0m accounts now; later any registered and verified user, as a service.** This report is what that changes. Nothing here is built.

## 1. The finding that decides the plan: Upwork's terms

**Status of the evidence: unverified.** Every Upwork page below returned HTTP 403 to a direct fetch (2026-10-05). What follows is what a web search tool reported those pages say. The owner must read the primary text before anyone relies on it:

- `https://www.upwork.com/legal` (the "API & MCP Terms of Use" and the "Integration Terms of Use")
- `https://support.upwork.com/hc/en-us/articles/55446516654611-How-to-use-Upwork-with-AI-agents-through-MCP`
- `https://www.upwork.com/ai/mcp`
- `https://developer.upwork.com/api-tos.html` (redirects to the API documentation; the older API terms)

What the search tool reported:

| Reported statement | Source | Why it matters here |
|---|---|---|
| Upwork's own MCP support page says to contact Upwork Support **before** a custom workflow such as "scheduled activity, AI-based filtering or scoring, **storing MCP output**, **connecting a hosted client**, or using more than one tool" | MCP support article | Every one of these is the plan: a hosted client, scheduled sync, stored output |
| The terms are between Upwork and the "Developer", anyone who registers a Developer Application or connects to the MCP; permitted uses include "operating an Agent on behalf of an Upwork User within scopes the Upwork User has granted" | API & MCP Terms | The per-member shape looks permitted in principle |
| "You may not use the tools to build a service that competes with the Upwork marketplace" | API & MCP Terms | A service must stay clearly on the freelancer-tooling side |
| Request, store and process only the minimum data fields and permissions needed | API & MCP Terms | The read-only allowlist helps; a full message archive may not be "minimum" |
| Upwork Content may not be sold, shared or made available to third parties; no use for profiling or advertising; no training or fine-tuning models on it | API & MCP Terms | Any AI feature over the stored data (T533, Resume Studio) needs a clear answer |
| Older API terms: caching Upwork Content for **more than 24 hours** is not allowed, apart from tokens and ids; delete user data promptly on request, on uninstall or on account closure | API documentation and support articles (described as over 4,000 days old, so possibly superseded) | If this applies to the MCP, **permanent storage of messages is not allowed at all**, for the owner's own account too |
| The API is "personal and internal use only; commercial use isn't supported" | support page on API keys | The same question for a paid service, if the MCP follows the API's rule |
| Rate limits are per **IP address**, not per user or application (300 per minute, or 10 per second; the sources disagree) | API documentation, support article | A hosted service shares one egress address across all users |

**What this means for work already done.** T539's loader keeps 2,614 messages and 162 rooms in the database indefinitely, and `rooms.jsonl` on disk. If the 24-hour rule or "minimum data" applies to MCP output, that is already outside the terms even for the owner's own account. It is unverified, but the owner should know it, and it is the first thing to ask Upwork.

## 2. The decision the terms force (owner)

Three questions, to Upwork Support, in writing, before any server connector is built:

1. May a hosted client connect on behalf of a member (and later of any user) with their authorization?
2. May we store the output (contracts, proposals, rooms, messages), and for how long? Is there an exception for the account owner's own data?
3. May this be offered as a paid or free service to other freelancers, and what counts as "competing with the marketplace"?

Draft for the owner to send (their account, their name; I do not send it):

> Subject: Hosted OAuth client for the Upwork MCP: confirming what is allowed
>
> We run a workspace tool for freelancers. We want each user to connect their own Upwork account to our service through the Upwork MCP (OAuth, read-only tools only), so the user can see their own contracts, proposals and conversations inside our app. Before building, we need written answers to: (1) Is a hosted client acting for the connected user permitted, and is a client-ID metadata document (`client_id_metadata_document_supported`) the supported way to identify it, with our https callback? Dynamic registration refused our https redirect (HTTP 400 `invalid_redirect_uri`). (2) May we store the returned data, and for how long? Is a user's own data treated differently from other people's content? (3) May we offer this to other freelancers as a service? (4) What request rate applies to a client serving many users from one server address?

## 3. Architecture, shaped by "service later"

The team-only version and the service version share one design if these choices are made now. Each is a decision about a place where a team-only shortcut would have to be redone for a service.

| Concern | Choice | Why |
|---|---|---|
| Who may connect | A capability, `integration.upwork`, granted by role. Team now; later granted to "verified registered user". The gate is enforced on the server routes, not only in the page | The owner's decision of 2026-10-02 (T537 notes). Widening is a grant, not a code change |
| Client identity | **One client for the deployment**, identified by a hosted client-metadata document if Upwork accepts it; never one registered client per user | Per-user registration does not scale and creates records at Upwork per person |
| Token storage | One `connections` row per member (`owner_kind = 'member'`), tokens encrypted at rest with the key held as a secret; never selectable by another member (RLS test, not an assumption) | Already the registry's shape (T94). A service multiplies the blast radius of a leak |
| Refresh | One writer per grant, compare-and-swap on the stored refresh token | Rotation is unmeasured; a lost race silently kills a connection |
| Reads | The read-only allowlist (done, T537 AC3), per leg opt-in | Minimum data; the allowlist already refuses every write tool |
| Writes to our tables | **One path**: SQL merge functions called by both the owner's Python loader and the edge function | Two implementations of "existing rows only gain information" will drift. T539's rules move into SQL |
| Scheduling | A queue with a global request budget and per-user cursors, not a per-user cron | Rate limits are per server IP across ALL users |
| Retention | A per-connection retention setting and a purge function by `profile_id` (rows, files, tokens, revoke at Upwork) | Deletion on request is in every version of the terms. A TTL is what a 24-hour rule would need |
| Freshness | `wom_upwork_freshness()` becomes per profile | Built 2026-10-05 for the owner's feed; the shape generalises |
| Verification | Gate the capability on the verified level (T475 and KYC work decide what "verified" means) | "Registered and verified users" is the owner's wording |

## 4. Ways to get a member's authorization to our server

Measured today (2026-10-05, public metadata, read-only): the MCP's authorization and token endpoints are Upwork's own OAuth; the only PKCE method is `S256`; client authentication may be `none`, `client_secret_basic`, `client_secret_post` or `private_key_jwt`; `client_id_metadata_document_supported` is `true`. The owner's `mcp-remote` client is public, auth method `none`, with a `localhost:23037` redirect.

| | Shape | Unknown | How to learn it |
|---|---|---|---|
| A | Hosted client-metadata document at an https URL, our https callback inside it | Does Upwork exempt metadata clients from the loopback rule? | Host one static file; the owner opens one authorize URL. Nothing is created at Upwork |
| B | The existing API-Center app as the client | Does the MCP accept its tokens? (the reverse was refused with HTTP 403) | One authorization with credentials already slated for retirement |
| C | One shared loopback client; the member pastes the address they land on back into w0m | None for the exchange; the server-address and refresh facts below still apply | Works today; costs the member a paste |
| D | Upwork allow-lists our redirect | Whether they will | The email in section 2 |
| E | Each member's laptop (`mcp-remote`, sync script, loader) | None | Works for technical members only, and does not suit a service |

Unmeasured for A to D: does `mcp.upwork.com` accept a token used from a server address; does the refresh token rotate and how long do the tokens live. The lifetime and presence of a refresh token can be read from the owner's own `mcp-remote` cache (printing only those facts).

## 5. Recommendation and weights

| Step | Cost | Risk | Unblocks |
|---|---|---|---|
| 1. The owner sends the section 2 email, and reads the primary terms | 20 minutes | none | Everything. Without it a server connector may be built for a use Upwork forbids |
| 2. Meanwhile, host the metadata document (A) and test it once | small; ships with the pending deploy | low: nothing is created at Upwork | The one-click path |
| 3. Build the parts that are the same under every answer, behind `integration.upwork`: the `oauth_states` verifier column and member `connections` row, SQL merge functions, the per-profile freshness function, the purge function | medium | low | The connector the moment A or C is confirmed |
| 4. Do NOT build the sync legs or a scheduler until the answer to question 2 is known | none | avoids rework or a terms breach | |

Not recommended: starting the server-side sync before the answer. Storing messages for other people is the highest-risk part of this whole plan, legally and for privacy, and it is the part that costs the most to undo.

## 6. Owner-only decisions

- Send the email (their account, a statement about their company).
- Whether the owner's own stored archive (2,614 messages) stays while the answer is pending. Recommendation: keep, do not grow it, and stop committing message text anywhere new (already done: `rooms.jsonl` is out of git).
- Whether a service is worth the compliance work (privacy policy, a data-processing statement, deletion and export, EU users). That is a business call.
- Anything involving money (a paid tier) or public statements.
