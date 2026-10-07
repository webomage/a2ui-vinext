# Telegram and Threads integration: search, message, manage bots (research, measured 2026-10-06)

Ticket: [[T550]]. Method: the estate's own code read first, then primary sources (Telegram `core.telegram.org` pages, Meta `developers.facebook.com/documentation/threads` pages and changelog); secondary articles were used only to find the primary page and were contradicted by it once (below). One live test (section 1) was run read-only on public pages.

## 1. The test you asked for: `@it_chats`, USD, fully remote, matching the canonical resume

**What `@it_chats` is.** A 32.5K-subscriber *directory* of Russian-language IT chats and channels, not a job feed. Its jobs post (837) lists channels; there is no remote section.

**What I could read, and what I could not.** Telegram serves a public web preview (`t.me/s/<channel>`) only for channels that leave it on. I tried 15 job-related handles (those the directory names plus the `*_feed` channels their descriptions point to). **2 render** (`@devops_jobs_feed`, `@founderStackJobsFeed`); **12 answer HTTP 302** (no public preview), including `@devops_jobs`, `@hot_itjobs`, `@overemployed`, `@ru_freelancers`, `@richlance_chat`, `@e7unity`; 1 (`@founderstackjobs`) showed only a landing card through the fetch tool and I did not re-check it with curl. A Bot API bot receives channel messages only where it is a member (Bot API FAQ); making it a member of someone else's channel is not something a reader can do. So the no-login path reaches 2 of 15.

**What I read.** 210 posts: 200 from `@devops_jobs_feed` (a 4-week window, 2026-09-11 to 2026-10-06) and 10 from `@founderStackJobsFeed` (2025-11 to 2026-07). Of 210, **166 are candidate résumés** (`#резюме`), not offers. Only 41 are vacancies.

**Funnel (vacancies only):** 41 vacancies, 26 remote-tagged, 16 fully remote with no hybrid, office or relocation wording, **4 with a USD or USDT figure**, 4 relevant to the resume's role and stack. My first filter was wrong (it counted `#remote` hashtags, which sit on almost every post, and matched candidate résumés and an infrastructure budget as offers); the second over-excluded; the third used the feed's own `#вакансия` / `#резюме` labels and was checked by reading every match in full.

| Posted | Role | Pay | Fit against the resume | Link |
|---|---|---|---|---|
| 2026-09-19 | SRE, Middle+/Senior, Lagrange Labs (blockchain/ZK infrastructure), full-time remote | 6,500 to 9,300 USD | **Strong on stack**: Kubernetes expert (Helm, operators), Terraform/Pulumi, AWS primary, Python or Go, GitOps, blockchain nodes a plus. Asks 4 to 5 years; the resume is 20+ and titled Principal, so this is below level and the band may sit under a principal expectation | https://t.me/devops_jobs_feed/23554 |
| 2026-09-29 | DevOps/Infrastructure Engineer (HFT), Triple Lemniscate Research, full-time remote | 5,000 to 7,000 USD | Partial: Linux performance, Ansible, Kafka, low latency are not on the resume; seniority not stated | https://t.me/devops_jobs_feed/23630 |
| 2026-07-09 | Senior ML Engineer / ML Lead, DeltaEra (trading strategies), remote | up to 12k USD net plus bonus | Weak: PyTorch/JAX and strong maths for trading models; the resume's AI work is LLM/RAG and agents | https://t.me/founderStackJobsFeed/34 |
| 2025-11-25 | PHP/Laravel backend, part-time, remote | 800 to 1,200 USDT | Not a fit (stack, hours, pay); stale | https://t.me/founderStackJobsFeed/26 |

Contact handles are in the posts and deliberately not copied here. **This is a thin sample, not "the market"**: one 4-week feed, 2 of 15 channels, and a regex plus my reading. Widening it needs a channel read the Bot API does not offer (section 2).

## 2. Telegram: what each access path can and cannot do (Bot API 10.3, 2026-08-24)

| Need | Bot API bot | Business bot (account owner connects it) | User-account client (MTProto: Telethon, TDLib) |
|---|---|---|---|
| **Search** messages or history | **No.** The changelog (9.0 to 10.3) has no search or history method. Guest mode explicitly gives no history or participant list | **No.** Only `business_message`, `edited_business_message`, `deleted_business_messages` updates for chats the owner grants | **Yes**: global and per-chat search, any chat the account can see |
| Read a channel it did not create | Only as a member; privacy mode limits groups; **never sees other bots** unless both opt in (10.0) | Only the owner's own connected private chats | Public channels without joining; joined chats |
| **Message** | Yes, to users who started it; limits 1 msg/s per chat, 20/min per group, about 30/s broadcast (paid broadcast needs 100,000 Stars and 100,000 monthly users) | Reply and edit in private chats with an incoming message in the last 24 hours (`can_reply`); mark read; delete | Anything the account may do, as the person |
| **Manage bots** | **Yes since 9.6 (2026-04-03):** a manager bot creates child bots from a `t.me/newbot/<manager>/<name>` link, then `getManagedBotToken`, `replaceManagedBotToken`, and (10.0) `get/setManagedBotAccessSettings` | Business account name, bio, photo, stars, gifts, stories (9.0) | Not applicable |
| Official, ToS-safe | Yes | Yes (Bot Developer ToS §5.4) | **Unclear and risky**, see below |

Other 2026 additions worth using: `sendMessageDraft` streaming for every bot (9.5), bot-to-bot messaging by username when both opt in (10.0, loops must be guarded by the developer), guest mode (a mention anywhere gives a one-shot reply, 10.0), rich messages (10.1), ephemeral messages in groups (10.2). `setWebhook` takes `secret_token` (the estate already checks it), `max_connections` 1 to 100, `allowed_updates`.

**The user-account path is where "search my chats" lives, and it is the risky one.** Telegram's `obtaining_api_id` page says all API client libraries are "strictly monitored to prevent abuse", accounts on unofficial clients are "under observation", and flooding or spam is a permanent ban; the API Terms do not address personal-account automation either way. A session string is full account access, an MCP server with send tools acts as the person with no review (prompt injection from message text is the live risk), and a "read-only" flag only hides tools, it does not reduce the session's authority. Search coverage of Telethon's FAQ (secondary, not re-read) reports the library maintainers advise established accounts only and warn about `PeerFlood`; the same coverage says Telegram may also ban VoIP numbers. **API Terms §1.5 prohibits using or aggregating Telegram data for AI or machine-learning development**: personal filtering is not training, but a stored, aggregated corpus would be hard to defend, so any design should hold nothing beyond what is needed to answer the query.

## 3. Threads: official API only, and there is no chat API

Primary sources: Meta's Threads overview, keyword-search, webhooks, long-lived-token pages and changelog.

- **No messaging or DM endpoint exists.** Not in the documentation index, not in the changelog from 2025 to 2026-08-12. Consumer DMs (July 2025), group chats (up to 50, not end-to-end encrypted) and web DMs (2026-05-05) exist in the product only. "Message" on Threads therefore means **replies and posts**; reading a DM thread would require scraping the product, which I do not recommend.
- **Search:** `GET /keyword_search` (`threads_keyword_search`, then App Review for public posts; without it, only your own posts). `q`, `search_type` TOP or RECENT, `search_mode` KEYWORD or TAG, `media_type`, `since`/`until`, `author_username` (2026-01-20), limit 100. **2,200 queries per rolling 24 hours per user**, shared across apps. A secondary article said 500 per 7 days; the primary page and the changelog (2025-06-25 "limit changed") show that was the old figure.
- **Replies:** read (`threads_read_replies`), create and manage (`threads_manage_replies`: hide, who may reply, **reply approvals since 2026-02-13**), mentions (`threads_manage_mentions`). Per profile per 24 hours: 250 posts, 1,000 replies, 100 deletes, 500 location searches.
- **Webhooks:** `replies`, `delete`, `mentions`, `publish` (2024-10 to 2025-08; `is_verified` and `profile_picture_url` added 2026-01-26). Needs Live Mode or Advanced Access, a verified business, and a non-private account for replies and mentions. **Only a callback token handshake is documented, no payload signature**, so treat payloads as untrusted and re-fetch by id before acting.
- **Tokens:** short-lived 1 hour, long-lived 60 days, refresh after 24 hours and before expiry, 90 days of app permission for private profiles. Server-side exchange only.
- No paid tier. The cost is App Review and token upkeep.

## 4. What the estate already has

- **Telegram, built:** one bot. `telegram-webhook` (secret-token header checked in constant time, fails closed with 503 when unset; command router for `/start /status /quests /claim_quest /approve_payout` and payout-approval callback buttons for linked admins; every update stored in `telegram_webhooks`), `notify-telegram` (one-way, service role or own `user_id`), `auth-telegram` and `profiles.telegram_chat_id` (unique), `get-bot-status` (`getMe`), a status card on `/admin/sync-health`, a log viewer, workers that notify (gamification, doc generators, Upwork poller, job aggregator, health and backup watchdogs).
- **Job pipeline, built:** `job-aggregator` with six sources (Adzuna, HN, Jooble, RemoteOK, Remotive, WeWorkRemotely), `job-scorer`, `scraped_jobs`. Telegram is only the notification channel; **no Telegram or Threads job source exists.**
- **Threads: nothing.** No code, tables or secrets.
- **Pattern to reuse:** [[T537]]'s per-member connector design (OAuth per profile, read-only tool allowlist, per-IP rate limits, laptop-side daemon for what must not run in the cloud) and `social_integrations` (service handles, T476).

Small defects seen while reading, none fixed here: the webhook's and notifier's `sendMessage` ignore the response, so a Telegram 4xx is silent; `parse_mode: "Markdown"` (legacy) rejects unescaped text, so any message containing `_` or `*` from user data is dropped without a trace; the webhook does not set `allowed_updates` and logs full message payloads (user text) to `telegram_webhooks` with no retention rule.

## 5. Recommendation: three tiers, in this order

1. **Tier A, official bots only, no new risk.** (a) A Telegram job source in the existing pipeline: follow the channels that expose a preview (2 of 15 today) through the public `t.me/s` pages at a few requests per hour, score with the existing scorer against the canonical resume, and DM matches through the existing notifier. (b) Per-member bots through **managed bots** (a `t.me/newbot/...` link, token via `getManagedBotToken`) so a registered user gets their own bot without BotFather steps; this is the "any registered user as a service" direction. (c) A bot registry and admin page (list, `getWebhookInfo`, rotate token, access settings). (d) Fix the three small defects. (e) **Threads** through the official API: per-member OAuth, `replies`/`mentions` webhooks into the same inbox, keyword search for the topics you track, a reply-approval gate on every outbound reply. Cost: App Review for `threads_keyword_search` and Advanced Access for webhooks; start the application early because it is the long pole.
2. **Tier B, a read-only user-account client, only after a spike and your explicit go.** A local daemon on your laptop (not the cloud, not an edge function), a **secondary aged account**, an allowlist of read tools (list, search, read), sends only through a human-approved queue, no stored corpus. It is the only way to search `@devops_jobs`-style channels and your own chats. Measure the ban behaviour at low volume before depending on it.
3. **Tier C, not recommended:** scraping Threads DMs, sending as a user account unattended, bulk anything.

## 6. Owner decisions, each with a recommendation

| # | Decision | Recommendation | Weight |
|---|---|---|---|
| D1 | Build Tier A (Telegram job source plus managed bots plus Threads API) | yes, in that order (job source first: one day, no review) | low cost, low risk |
| D2 | Is a user-account client (Tier B) acceptable at all, on a secondary account | yes for a time-boxed spike, read-only, laptop-only; no for the main account | medium risk (ban, ToS silence, §1.5) |
| D3 | Start the Meta App Review for `threads_keyword_search` and webhooks now | yes, it runs in parallel with the code | zero code cost, calendar cost |
| D4 | Where per-member bot tokens live | encrypted in the database (Vault or pgsodium), never in a repo file or a plain column; decide the mechanism before the first managed bot | high: a leaked token is a bot takeover |
| D5 | Retention for `telegram_webhooks` payloads | 30 days then purge; keep ids and types only | low cost, privacy |

## 7. Caveats on this report

Telegram's `bots/api` page was truncated mid-fetch, so `BotAccessSettings` fields, `BusinessBotRights` fields and the exact parameters of `getUserPersonalChatMessages` are from the changelog only and not verified. The Business page says rights include reply, read and delete; the full rights list is not confirmed. The Bot Developer ToS (§5.4) was not read. I did not use the Telegram plugin MCP in this session (it failed to connect). The `@it_chats` posts for sections 01 to 29 (languages and frameworks) were not visible in the preview, so channels listed only there are not covered.
