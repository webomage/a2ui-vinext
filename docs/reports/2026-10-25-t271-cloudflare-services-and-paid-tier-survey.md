# T271 — Cloudflare Services Catalogue Survey & `Workers Paid ($5/mo)` vs `Supabase Pro ($25/mo)` Spend Comparison

**Date:** 2026-10-25
**Ticket:** [[T271]]
**Decision Record:** [[AgDR-0043]] (`docs/decisions/AgDR-0043-cloudflare-services-verdict-and-paid-tier-triggers.md`)
**Governing Precedents:** [[AgDR-0003]] (Stay on Supabase Free), [[AgDR-0005]] (Local Backup Producer to R2), [[AgDR-0010]] (Decline Kitesurf), [[AgDR-0040]] (3-Channel Outbound Mail)
**Related Tickets:** [[T272]] (Per-Project Cost Attribution), [[T262]] (Public-Site Outage Resilience), [[T229]] & [[T231]] (Backup & Restore Pipeline), [[T81]] (Auth & Bot Hardening)

---

## Executive Summary

1. **Re-measurable Binding Inventory (`AC8`, `scripts/cf_bindings_inventory.py`):**
   Across all `7` Wrangler configurations (`wom7api`, `wom7func`, and the 5 Astro apps in `wom7web/apps/*`), the estate actively binds **Workers AI** (`wom7api`, `wom7func`), **Browser Rendering** (`wom7func`), **19 Workflows** (`wom7api`), **1 SQLite Durable Object** (`CHAT_MEMORY` on `wom7api`), **2 KV Namespaces** (`SESSION` across all 5 apps; `SETTINGS` on `web`), **1 R2 Bucket binding** (`PUBLIC_ASSETS` on `web`, plus `wom7-backups` via CLI), **Service Bindings** (`CF_WORKERS`, `WOM7API`), and **5/5 account Cron Triggers** (`wom7func`). Thirteen catalogue bindings (`d1_databases`, `hyperdrive`, `queues`, `vectorize`, `images`, `send_email`, `turnstile`, `analytics_engine_datasets`, `containers`, `pipelines`, `mtls_certificates`, `dispatch_namespaces`, `assets`) are declared in **zero** Wrangler configs.
2. **Free-Tier Cloudflare Adoptions (`AC1–AC7`):**
   - **Workers KV (Free Tier):** **ADOPT** for [[T262]] public-site outage resilience (serving cached public page payloads when Supabase is unavailable).
   - **Cloudflare Turnstile (Free Tier):** **ADOPT** — `AC4` code measurement proved Turnstile is already live on 3 public forms (`contact-submit`, `apply-submit`, `submit-service-request`) via `_shared/turnstile.ts` HTTP `siteverify` (`0x4AAAAAAE9GS8gtYiRYPdzL`), while `0` `wrangler.jsonc` bindings exist and [[T81]] auth ceremonies (`/api/auth/*`) remain to be protected.
   - **Cloudflare Email Routing (Free Tier):** **ADOPT** for inbound `@webomage.com` role aliases (`dmarc@`, `security@`, `support@`), complementing [[AgDR-0040]]'s 3-channel outbound mail architecture.
   - **Cloudflare R2 + Free Image Transformations (Free up to 5,000 unique transformations/mo):** **ADOPT** over paid Cloudflare Images (`$5/mo`) for public media (`wom-public-assets`).
   - **Cloudflare Hyperdrive (Free Tier):** **REVISIT-WHEN-X** — `AC7` live network probes proved IPv6 (`138 ms`, TLS `b'S'`) and Supavisor IPv4 (`302 ms`, TLS `b'S'`) work on Free, but Hyperdrive's `60s` non-invalidating cache **cannot solve [[T262]]**, and rewriting `439` `.from()` calls across `98` RLS tables into manual `set_config('request.jwt.claims', ...)` SQL transactions is an unacceptable RLS security-posture regression without a measured latency bottleneck.
3. **Vendor Spend Comparison (`AC9–AC11`):**
   Grounded in [[T272]] per-project cost attribution across `3` active client projects (`artemio`, `1945`, `bridgeroad`):
   - **Cloudflare Workers Paid (`$5.00/mo` = `$1.67/mo` per project)** is **5× cheaper** than **Supabase Pro (`$25.00/mo` = `$8.33/mo` per project)** and **25× cheaper** than **Supabase Pro + PITR (`$125.00/mo` = `$41.67/mo` per project)**.
   - **Critical `AC10` Backup Finding:** Supabase Pro base (`$25/mo`) provides only **7-day daily backups** — **Point-in-Time Recovery (PITR) costs an extra `+$100/mo` (`$125/mo` total)**! Furthermore, **neither Supabase daily backups nor `$100/mo` PITR backs up Supabase Storage buckets (`555` objects in `T229`)**, and logical daily dumps carry the exact same `pgvector`/role limitations measured in `T229`. Moving off-laptop backup execution (`AgDR-0005`) into a **Cloudflare Container on Workers Paid (`$5/mo`)** solves the single-laptop risk for **both** Postgres and Storage at `$1.67/mo/project`.
   - Per owner decision, **[[AgDR-0003]] ($0/mo free tiers) remains active today**, and **[[AgDR-0043]]** locks the quantitative triggers that will promote the estate to **Workers Paid (`$5/mo`) first** and **Supabase Pro (`$25/mo`) second**.

---

## 1. Re-Measurable Estate Binding Inventory (AC8)

Generated deterministically via `python3 scripts/cf_bindings_inventory.py` (verified by `pytest scripts/tests/test_cf_bindings_inventory.py`, `3/3` passing in `0.31s`):

| Config Path | Worker Name | Active Bindings | Cron Triggers | Observability | Custom Routes |
|---|---|---|---|---|---|
| `wom7api/wrangler.jsonc` | `wom7api` | `ai`: `AI`; `durable_objects`: `CHAT_MEMORY->ChatMemoryDO`; `workflows`: `19` classes | `0` | `on` (+ source maps) | — |
| `wom7func/wrangler.jsonc` | `wom7func` | `ai`: `AI`; `browser`: `BROWSER` | `5 / 5` (`*/15 * * * *`, `*/30 * * * *`, `0 8 * * *`, `0 */6 * * *`, `0 14 * * SUN`) | `on` (+ source maps) | — |
| `wom7web/apps/cp/wrangler.jsonc` | `webomage-cp` | `kv_namespaces`: `SESSION`; `services`: `CF_WORKERS->wom7func`, `WOM7API->wom7api` | `0` | `off` | `cp.webomage.com`, `cp.w0m.xyz` |
| `wom7web/apps/demo/wrangler.jsonc` | `webomage-demo` | `kv_namespaces`: `SESSION` | `0` | `off` | `demo.webomage.com` |
| `wom7web/apps/job/wrangler.jsonc` | `webomage-job` | `kv_namespaces`: `SESSION` | `0` | `off` | `job.webomage.com` |
| `wom7web/apps/join/wrangler.jsonc` | `webomage-join` | `kv_namespaces`: `SESSION` | `0` | `off` | `join.webomage.com` |
| `wom7web/apps/web/wrangler.jsonc` | `webomage` | `kv_namespaces`: `SESSION`, `SETTINGS`; `r2_buckets`: `PUBLIC_ASSETS->wom-public-assets`; `services`: `CF_WORKERS->wom7func`, `WOM7API->wom7api` | `0` | `off` | `webomage.com` |

**Declared in ZERO Wrangler configs (`13` binding types):**
`assets`, `d1_databases`, `hyperdrive`, `queues`, `vectorize`, `images`, `send_email`, `turnstile`, `analytics_engine_datasets`, `containers`, `pipelines`, `mtls_certificates`, `dispatch_namespaces`.

---

## 2. Cloudflare Catalogue Pricing, Quotas & Need-Pairing Matrix (AC1, AC2, AC3, AC5, AC6)

All pricing and quotas below were re-verified against Cloudflare Developer Platform pricing documentation as of **2026-10-25**:

| Service | Workers Free Tier Quota & Price (`$0/mo`) | Workers Paid Tier Quota & Price (`$5/mo` base) | Paired Estate Need / Ticket | Prior Decision Checked (`AC3`) | Verdict (`AC5`) & Action Routing (`AC6`) |
|---|---|---|---|---|---|
| **Workers KV** | **Included Free:** `100,000` reads/day, `1,000` writes/day, `1,000` deletes/day, `1,000` lists/day, `1 GB` storage (`100` namespaces) | `10M` reads/mo, `1M` writes/ deletes/lists/mo, `1 GB` storage (`+$0.50/GB`, `+$0.50/M` reads) | **[[T262]]** — Public site (`webomage.com`) must keep rendering when Supabase is down; already bound for `SESSION` + `SETTINGS` | Compatible with [[AgDR-0003]] (`$0/mo`) | **ADOPT (Free Tier)** — Route implementation to **[[T262]]** using existing/dedicated KV namespace on `apps/web` for edge-cached public page snapshots (`stale-if-error`). |
| **Turnstile** | **Included Free:** `1,000,000` siteverify assessments/mo, up to `20` widgets, managed/invisible challenges | Enterprise Bot Management required only above `1M` assessments/mo or `> 20` widgets | **[[T81]]** — Public form & auth ceremony bot protection | Compatible with [[AgDR-0003]] (`$0/mo`) | **ADOPT (Free Tier)** — Live on 3 public forms (`AC4`); route remaining auth-ceremony protection (`/api/auth/*`) to **[[T81]]**. |
| **Email Routing** | **Included Free:** Unlimited custom addresses, rules, and forwarding; Email Workers free within `100k/day` Worker invocation cap | Same (Email Workers share `10M/mo` Paid request pool) | **[[T326]]** — Inbound delivery for `dmarc@webomage.com`, `security@webomage.com`, and client support aliases | Outbound mail settled by **[[AgDR-0040]]** (Supabase Auth + Workspace SMTP + Resend Free) | **ADOPT (Free Tier, Inbound Only)** — Use for inbound `@webomage.com` routing (`dmarc@`, role aliases). Keep outbound strictly on [[AgDR-0040]]'s 3-channel split. |
| **R2 + Image Transformations** | **R2 Free:** `10 GB-mo` storage, `1M` Class A ops/mo, `10M` Class B ops/mo, **`$0` egress**.<br>**Transformations Free:** `5,000` unique transformations/mo per zone | R2: `+$0.015/GB-mo`; Image Transformations: `$0.50 / 1,000` unique transformations above `5k`. Paid **Cloudflare Images Storage** is `$5/mo` per `100k` stored images | **[[T229]] / [[T262]]** — `555` Supabase Storage objects + unmeasurable `5 GB` Supabase Free egress cap | [[AgDR-0005]] already uses `r2://wom7-backups`; `apps/web` binds `wom-public-assets` | **ADOPT R2 + Free Zone Transformations / REJECT `$5/mo` Cloudflare Images** — `555` objects (~`54 MB`) sit at `0.5%` of R2's `10 GB` free cap with `$0` egress. |
| **Hyperdrive** | **Included Free:** `100,000` queries/day (resets `00:00 UTC`; cached queries count), `~20` max origin connections, `10` configs | **Unlimited** queries/day, `~100` max origin connections, `25` configs (included in `$5/mo` Workers Paid) | Originally paired to **[[T262]]** (proven false in `AC7`); re-paired to server-side Postgres latency | Compatible with [[AgDR-0003]] on price, but fails [[T262]] resilience (`AC7`) | **REVISIT-WHEN-X** — `X` = measured CP server-side latency dominated by PostgREST multi-query round-trips that an `.rpc()` cannot collapse. Do **not** use for [[T262]]. |
| **Containers** | **Not available on Free** | **Requires Workers Paid (`$5/mo`)** + usage (`$0.000020/vCPU-s`, `$0.0000025/GiB-s` above free allowance) | **[[T231]] / Debt D57** — Running `pg_dump` + Storage sync in the cloud so backups do not depend on one laptop being awake | **Already decided in [[AgDR-0005]]** (rejected while on Free tier) | **ALREADY DECIDED ([[AgDR-0005]]) / REVISIT-WHEN-WORKERS-PAID** — Immediate #1 beneficiary the day Workers Paid (`$5/mo`) is triggered. |
| **Vectorize** | **Not available for production on Free** | **Requires Workers Paid (`$5/mo`)**: includes `30M` queried vector dimensions/mo + `5M` stored dimensions (`+$0.01/M` queried, `+$0.05/100M` stored) | **[[T229]]** — `pgvector` tables (`11` tables / embeddings) do not restore from a Supabase logical dump | Blocked by [[AgDR-0003]] (`$0/mo`) | **REVISIT-WHEN-X** — `X` = Workers Paid (`$5/mo`) is active AND re-embedding `pgvector` tables after a disaster recovery exceeds acceptable RTO. |
| **Queues** | **Not available on Free** | **Requires Workers Paid (`$5/mo`)**: includes `1,000,000` operations/mo (`+$0.40/M` ops) | Async background job dispatch (currently handled by `19` Cloudflare Workflows in `wom7api` + `5` crons in `wom7func`) | Blocked by [[AgDR-0003]]; Workflows (`wom7api`) already active on Free | **REVISIT-WHEN-X** — `X` = Workers Paid is active AND a high-fanout producer exceeds Cloudflare Workflows free-tier instance quotas. |
| **Analytics Engine** | **Included Free:** `100,000` data points written/day, `10,000` read queries/day | `10M` data points written/mo (`+$0.25/M`), `1M` read queries/mo | Worker telemetry & product analytics | `observability: { enabled: true }` is already active on `wom7api` & `wom7func`; Tinybird (`[[T43]]`) handles product events | **REJECT (Redundant)** — Adding a third telemetry sink violates SSOT. |
| **D1 (SQLite)** | **Included Free:** `5M` rows read/day, `100k` rows written/day, `5 GB` total storage (`10` DBs) | `25B` rows read/mo, `50M` rows written/mo, `5 GB` storage | None — Supabase Postgres (`98` RLS tables) + Durable Objects (`ChatMemoryDO`) already cover relational & edge state | Violates Triangulated SSOT (`AGENTS.md`) if introduced alongside Postgres | **REJECT (Available, No Use)** — Zero need for a second relational database engine. |

---

## 3. Installed vs Deployed Measurement: Turnstile & Second Supabase Org (AC4)

Per [[T154]] (*declared ≠ configured ≠ listening ≠ connected*), code and live DNS were inspected rather than inferred from installed skills:

### 3.1 Turnstile Deployment Audit (`AC4`)

1. **Skill Surface:** `.gemini/skills/turnstile-spin/SKILL.md` is installed on the host.
2. **Wrangler Binding Surface (`scripts/cf_bindings_inventory.py`):** `0` of `7` `wrangler.jsonc` files declare a `turnstile` binding.
3. **Frontend Widget & Edge Function Verification Surface (`git grep -i turnstile`):**
   - **Frontend widgets deployed (`wom7web`):** Sitekey `0x4AAAAAAE9GS8gtYiRYPdzL` (`PUBLIC_TURNSTILE_SITE_KEY`) is wired in `apps/web/src/components/templates/sections/ContactFormSection.astro`, `apps/cp/src/components/templates/sections/ContactFormSection.astro`, `apps/web/src/components/forms/ApplicationForm.svelte`, `apps/cp/src/components/forms/ApplicationForm.svelte`, and `apps/web/src/components/ChatApp.svelte` (`#quote-turnstile`).
   - **Backend `siteverify` enforcement (`wom7api`):** `wom7api/supabase/functions/_shared/turnstile.ts` (`verifyTurnstile()` calling `https://challenges.cloudflare.com/turnstile/v0/siteverify` with `TURNSTILE_SECRET`) is actively called in `apply-submit/index.ts`, `contact-submit/index.ts`, and `submit-service-request/index.ts`.
   - **Remaining gap (`[[T81]]`):** Self-service auth ceremonies (`apps/cp/src/pages/api/auth/reset-request.ts`, `apps/web/src/pages/api/auth/reset-request.ts`, OTP login) do **not** yet pass a Turnstile token before invoking Supabase Auth.

### 3.2 Second Supabase Project DNS Status

- As measured during the Hyperdrive probe (`2026-09-21`), `db.rlttvlyvjtrtpwewcflm.supabase.co` and `rlttvlyvjtrtpwewcflm.supabase.co` return **no `A`, `AAAA`, or `CNAME` DNS records** (project paused/deleted), leaving `pqbbjgeapylcengbuvee` (`w0m`) and `solar_flares` (`284 MB`, ~`57%` of `500 MB` cap) as the measured Supabase footprint.

---

## 4. Resilience Claims Tested, Not Reasoned: Hyperdrive vs KV for `T262` (AC7)

[[T262]] requires that `webomage.com` continue rendering public pages when Supabase is unavailable. Both candidates were evaluated against actual network and failure mechanics:

1. **Network Reachability Test (Measured `2026-09-21`):**
   - `db.pqbbjgeapylcengbuvee.supabase.co` resolves to IPv6 `2600:1f16:1e8d:b801:e0e4:a3c8:f444:fff8`, completes TCP `:5432` handshake from Cloudflare WARP IPv6 egress in **`138 ms`**, and returns Postgres `SSLRequest -> b'S'` (clearing Hyperdrive error `2012`).
   - Supavisor IPv4 poolers `aws-0-us-east-1.pooler.supabase.com:6543` (`309 ms`) and `:5432` (`302 ms`) also answer with `TLS=b'S'`.
   - **Result:** Infrastructure/IPv6 is **not** a blocker for Hyperdrive on Supabase Free.
2. **Why Hyperdrive Fails `T262` Outage Resilience & RLS Safety:**
   - **Cache mechanics:** Hyperdrive caches read queries for `60s` by default (`1h` max) with **no write invalidation** and **no `stale-if-error` origin-down serving guarantee**. Any outage lasting `> 60 seconds` (or any uncached route/query containing `NOW()`/`CURRENT_TIMESTAMP`) immediately fails with an origin connection error.
   - **Architecture & RLS barrier:** `wom7web/apps/*` (`387` call sites) and `wom7api/src` (`52` call sites) total **`439` `.from()` PostgREST calls** (plus `124` `.auth.*`, `41` `.rpc()`, `15` `.functions.invoke()`, `14` `.channel()`, `7` `.storage.*`). Replacing PostgREST with direct Postgres wire-protocol queries over Hyperdrive requires manual `set_config('request.jwt.claims', ..., true)` inside an explicit SQL transaction across **`98` RLS-protected tables** — turning a caching experiment into a systemic RLS bypass hazard.
3. **Why Workers KV Satisfies `T262`:**
   - `apps/web/wrangler.jsonc` already binds `kv_namespaces` (`SESSION`, `SETTINGS`). Writing serialized public page props / rendered HTML fragments into KV with an long TTL (`24h–7d`) and serving from KV whenever Supabase returns `5xx` or times out (`> 1,500 ms`) keeps `webomage.com` online indefinitely during a full Supabase outage with **zero RLS changes** and **`$0/mo` cost** (`100k` free KV reads/day).

---

## 5. Vendor Spend Comparison (`Workers Paid $5/mo` vs `Supabase Pro $25/mo`) & What PITR Actually Covers (AC9, AC10)

### 5.1 Side-by-Side Comparison with `T272` Per-Project Cost Attribution (`AC9`)

Per [[T272]] (`project/clients-policy.json` → `computeProjectCostAttribution`), shared platform costs are attributed equally across the **`3` active client projects** (`artemio` `33.33%`, `1945` `33.33%`, `bridgeroad` `33.33%`):

| Dimension | Status Quo: Free Tiers (`AgDR-0003`) | Option A: **Cloudflare Workers Paid** | Option B: **Supabase Pro (Base Plan)** | Option C: **Supabase Pro + 7-Day PITR Add-On** |
|---|---|---|---|---|
| **Gross Monthly Cost** | **`$0.00 / mo`** | **`$5.00 / mo`** | **`$25.00 / mo`** | **`$125.00 / mo`** (`$25` Pro + `$100` PITR) |
| **Per-Project Attributed Cost (`3` active projects, `T272`)** | **`$0.00 / mo / project`** | **`$1.67 / mo / project`** | **`$8.33 / mo / project`** | **`$41.67 / mo / project`** |
| **Annualized Estate Spend** | `$0 / yr` | `$60 / yr` | `$300 / yr` | `$1,500 / yr` |
| **What Capabilities It Unlocks** | • `100k` Worker req/day<br>• `5` account cron triggers (`5/5` used)<br>• `100k` KV reads/day<br>• `10 GB` R2 (`$0` egress)<br>• `500 MB` Supabase DB (`w0m` at `13.5%`, `solar_flares` at `57%`)<br>• `5 GB` Supabase egress (unmeasurable via API) | • **`10M` Worker req/mo**, `30M` CPU ms/mo<br>• **`250` cron triggers/script** (relieves `5/5` cap)<br>• **Cloudflare Containers** (can run native `pg_dump` + Storage sync in cloud)<br>• **Queues** (`1M` ops/mo)<br>• **Vectorize** (`30M` queried dims/mo)<br>• **Unlimited Hyperdrive queries/day** | • **`8 GB` Postgres DB** (`16×` cap)<br>• **`250 GB` egress** + **`100 GB` Storage**<br>• **7-day automated daily backups**<br>• No 7-day inactivity pause<br>• *Note:* Per-project egress remains unattributable inside one shared Supabase project | • Everything in Supabase Pro Base, **PLUS**:<br>• **Physical WAL shipping & Point-in-Time Recovery (PITR)** to any second within 7 days (`+$100/mo` add-on; 14-day PITR is `+$200/mo`) |
| **What Manual / Single-Laptop Toil It Deletes** | None — relies on local Mac `launchd` (`com.w0m.backup-daily` / `weekly`) pushing to `r2://wom7-backups` (`AgDR-0005`, Debt `D57`) | **Deletes the "single laptop must be awake" backup exposure (`AgDR-0005` / `D57`)**: a scheduled Cloudflare Container + Worker cron runs `pg_dump` + Storage tarball sync directly to `r2://wom7-backups` for **`$5/mo`** | Replaces local daily SQL dump schedule with managed daily DB snapshots, **BUT does NOT back up Supabase Storage (`555` objects) and does NOT provide minute-level PITR** | Deletes local DB backup toil and restores `pgvector` indexes via physical disk/WAL replay, **but STILL does not back up `555` Supabase Storage objects** (`T231` R2 sync still required) |

### 5.2 Critical Audit: What Supabase Pro Backups & PITR Actually Cover (`AC10`)

Before valuing *"Supabase Pro gives us simpler backups naturally"*, we audited the exact technical and pricing mechanics of Supabase's backup tiers against the gaps measured in [[T229]]:

| Backup Gap / Requirement (Measured in `T229`) | Local `pg_dump` + Storage Sync to R2 (`AgDR-0005`, `$0/mo`) | Supabase Pro **Base Daily Backups** (`$25/mo`) | Supabase Pro **+ Physical / PITR Add-On** (`$125/mo` = `$25` + `$100`) |
|---|---|---|---|
| **1. Real Monthly Price** | **`$0 / mo`** | **`$25 / mo`** (`$8.33/project`) | **`$125 / mo`** (`$41.67/project`) — 🔴 **PITR is NOT included in the `$25/mo` base Pro plan!** |
| **2. Recovery Point Objective (RPO)** | `24 hours` (daily `03:15` launchd run when laptop is awake) | `24 hours` (daily automated snapshot, 7-day retention) | **`1 second / 2 minutes`** (continuous WAL archive shipping) |
| **3. `pgvector` Tables & HNSW Indexes (`T229` gap)** | Logical dump loses/skips `pgvector` data unless custom-dumped or re-embedded | Logical daily backups (`pg_dumpall` on standard small instances) carry the **same logical dump constraints** unless migrated to Physical Backups | **Covered:** Physical base backup + WAL replay restores raw disk pages, preserving `pgvector` tables and HNSW indexes intact |
| **4. Cluster Roles (`postgres` superuser grants)** | Stripped during non-superuser restore (`T229` restore script normalizes ownership) | Managed restore runs inside Supabase control plane with platform role handling | **Covered:** Physical disk/WAL restore preserves full cluster role catalog |
| **5. Supabase Storage Objects (`555` files / `53.9 MB` in `T229`)** | **Covered (`555/555` verified in `r2://wom7-backups` via `T231`)** | ❌ **NOT COVERED.** Supabase database backups only snapshot Postgres; Storage buckets (`storage.objects` bytes in S3) are **completely excluded** | ❌ **NOT COVERED.** Even at `$125/mo`, PITR only restores Postgres metadata (`storage.objects` rows), **not** the underlying bucket files in S3! |
| **6. Independent Offsite Ownership** | **Yes** — encrypted/verified artifacts live in our Cloudflare R2 bucket (`r2://wom7-backups`) | ❌ **No** — backups live inside the same vendor/account control plane | ❌ **No** — WAL archives live inside Supabase's managed storage |

> **Key `AC10` Conclusion:**
> Upgrading to **Supabase Pro at `$25/mo` does NOT include PITR** (which costs **`$125/mo`** with the `+$100/mo` PITR add-on), and **neither `$25/mo` Pro nor `$125/mo` PITR backs up the `555` files in Supabase Storage**. Therefore, `T231`'s R2 Storage backup pipeline cannot be retired by upgrading to Supabase Pro. Conversely, unlocking **Cloudflare Workers Paid (`$5/mo` = `$1.67/mo/project`)** lets us move the existing proven `T229`/`T231` Postgres + Storage backup producer from this laptop into a scheduled **Cloudflare Container** pushing to `r2://wom7-backups`, eliminating the single-laptop risk (`AgDR-0005` / Debt `D57`) at **1/5th the cost of Supabase Pro** and **1/25th the cost of Supabase PITR**.

---

## 6. Decision & Quantitative Upgrade Triggers (`AgDR-0043`, AC11)

Per owner direction (`2026-10-25`), **[[AgDR-0003]] ($0/mo free tiers) remains active today**, and **[[AgDR-0043]]** is adopted to lock:

1. **Immediate Free-Tier Adoptions (`$0/mo`):**
   - **Workers KV** → [[T262]] (public-site outage resilience cache).
   - **Cloudflare Turnstile** → [[T81]] (extend existing `_shared/turnstile.ts` protection from the 3 public forms to auth ceremonies).
   - **Cloudflare Email Routing** → [[T326]] (inbound `@webomage.com` role aliases `dmarc@`, `security@`, `support@`).
   - **Cloudflare R2 + Free Zone Image Transformations** → [[T262]] / [[T229]] (serve public media from `wom-public-assets` with zero Supabase egress).
2. **Ordered Paid-Tier Upgrade Ladder & Quantitative Triggers (when `AgDR-0003` is superseded):**
   - **Tier 1 Spend (`$5.00/mo` = `$1.67/mo/project`): Upgrade to Cloudflare Workers Paid FIRST when ANY of these 3 triggers fire:**
     1. **Cron Ceiling:** A 6th distinct schedule is required beyond `wom7func`'s `5/5` account cron limit and cannot be multiplexed into existing `*/15` or `*/30` ticks.
     2. **Off-Laptop Backup Automation (`AgDR-0005` / Debt `D57`):** Laptop-off gaps cause `just backup-freshness --r2` to breach `max_age_days` (`> 2` missed daily runs in a 14-day window), triggering migration of `com.w0m.backup-daily` into a Cloudflare Container on Workers Paid.
     3. **Request / Vectorize Quota:** Worker requests exceed `70,000/day` (`70%` of Free cap) OR production `Vectorize` / `Queues` is required by a contracted client feature.
   - **Tier 2 Spend (`$25.00/mo` = `$8.33/mo/project`): Upgrade `w0m` to Supabase Pro SECOND only when ANY of these 3 triggers fire:**
     1. **Database Size Warning (`just supabase-limits`):** `w0m` database size crosses **`350 MB` (`70%` of the `500 MB` Free cap)** (currently `68 MB` / `13.5%`).
     2. **Storage / Egress Quota Warning:** Supabase Storage crosses **`700 MB` (`70%` of `1 GB`)** OR dashboard-reported monthly egress crosses **`3.5 GB` (`70%` of `5 GB`)** after static public assets have moved to R2 (`wom-public-assets`).
     3. **Contracted Client SLA:** A paying client contract explicitly mandates vendor-managed daily snapshots or (`+$100/mo`) PITR and funds the `$8.33/mo`–`$41.67/mo` attributed cost row in [[T272]].
