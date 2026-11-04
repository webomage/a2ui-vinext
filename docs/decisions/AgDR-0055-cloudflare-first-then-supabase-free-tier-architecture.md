---
id: AgDR-0055
title: "Free-Tier-First Resource Allocation Rule — Target Cloudflare Free Tier First, Then Supabase Free Tier"
timestamp: 2026-11-03T20:40:00Z
agent: antigravity
model: claude-opus-4-6
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T630
---

# AgDR-0055 — Free-Tier-First Resource Allocation Rule (Cloudflare Free Tier First, Supabase Free Tier Second)

## Y-statement

> In the context of **designing and shipping storage, compute, media, sync, AI inference, and public intake surfaces across the `@wom` estate (`w0m-web`, `w0m-api`, `w0m-cf`, `w0m-ext`, `w0m-sec`) while operating at `$0/mo` recurring infrastructure cost (`[[AgDR-0003]]`, `[[AgDR-0043]]`)**, facing **asymmetric free-tier ceilings where Cloudflare Free provides generous object storage (`10 GB` R2 + `$0` egress), edge compute (`100,000` req/day), bot defense (`1,000,000` Turnstile assessments/mo), and daily AI inference (`10,000` Workers AI Neurons/day) whereas Supabase Free enforces tight, abrupt relational and egress caps (`500 MB` Postgres DB, `1 GB` Storage, `5 GB/mo` unmeasurable egress, `200` concurrent Realtime connections)**, we decided **to codify a mandatory 4-tier Free-Tier-First Resource Allocation Rule: (0) Client/Browser & Static Edge Assets first, (1) Cloudflare Free Tier FIRST for compute, binary/vault/media storage (`R2`), caching (`KV`), bot gating (`Turnstile`), and opportunistic AI (`Workers AI`), (2) Supabase Free Tier SECOND strictly for GoTrue Auth, RLS-governed relational metadata, compact hashes, and append-only `*_audit_log` rows, and (3) Paid Tiers ONLY when a quantitative `[[AgDR-0043]]` trigger fires with owner approval**, to achieve **maximum product capability (shared wishlists, picture/voice tasks, native R2 Obsidian vault sync, verified website security audits) at `$0/mo` without exhausting Supabase's `500 MB` DB or `5 GB` egress limits**, accepting **client-side media compression/bounds, conservative delta-sync cadences over idle WebSockets/WebDAV polling, and graceful non-blocking fallback when daily free Workers AI neurons are exhausted**.

## Context

1. **Owner Direction (`2026-11-03`, `[[T630]]`):**
   - *"our philosophy for now based on free tier so we target CF free tier first and then Supabase free tier resources — spell this as architecture rule in AgDRs."*
2. **Measured Free-Tier Headroom Asymmetry (`2026-11-03`, cross-referencing `[[AgDR-0003]]` & `[[AgDR-0043]]`):**
   - **Cloudflare Free Tier (`$0/mo`):**
     - **Static Assets (`wrangler` `[assets]`):** Unlimited static requests and `$0` bandwidth.
     - **Workers / Astro Edge SSR:** `100,000` requests/day (`~3,000,000`/month), `10 ms` CPU time/invocation.
     - **Cloudflare R2:** `10 GB`-months storage (`10×` Supabase Storage Free), `1,000,000` Class A ops/mo (`PUT`, `POST`, `LIST`), `10,000,000` Class B ops/mo (`GET`, `HEAD`), and **`$0.00/GB` egress**.
     - **Workers KV:** `100,000` reads/day, `1,000` writes/day, `1 GB` storage.
     - **Cloudflare Turnstile:** `1,000,000` bot assessments/month free (`siteverify`).
     - **Workers AI:** `10,000` Neurons/day free across `@cf/*` models (e.g. `@cf/openai/whisper-large-v3-turbo`).
     - **Cloudflare DoH (`cloudflare-dns.com/dns-query`):** Free JSON DNS resolution for `TXT`/`SPF`/`DMARC`/`DNSSEC` verification without raw UDP sockets.
   - **Supabase Free Tier (`$0/mo`):**
     - **Postgres Database:** **`500 MB` hard cap** (measured `68 MB` in `[[AgDR-0003]]`, monitored via `just supabase-limits` with `70%` warning / `90%` fail).
     - **Supabase Storage:** **`1 GB` hard cap** + **`5 GB/mo` uncached egress cap** (and not covered by base Pro PITR per `[[AgDR-0043]]`).
     - **Edge Functions:** `500,000` invocations/month (`1/6th` of Workers Free daily request volume).
     - **Realtime:** `200` concurrent connections / `2,000,000` messages/month.
     - **GoTrue Auth:** `50,000` MAUs free.
3. **Concrete Architectural Risks Without an Explicit Ordering Rule:**
   - Storing user-uploaded images, voice notes, or vault markdown snapshots inside Postgres `bytea`/`text` or Supabase Storage rapidly consumes the `500 MB` DB and `5 GB` egress caps.
   - Chatty WebDAV `PROPFIND` + per-file `HEAD` sync loops (`Remotely Save`) multiply R2 Class A/B operations compared to a single JSON SHA-256 delta manifest (`w0m-obsidian-sync`, `[[T628]]`).
   - Executing unauthenticated public website security scans immediately on form submit (`[[T630]]`) exposes Worker CPU, subrequests, and Supabase lead writes to bot abuse before Turnstile, visitor fingerprinting, and domain ownership are confirmed.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **O1 — Unordered dual-cloud usage (ad-hoc Supabase Storage, Edge Functions, or Postgres blobs)** | Minimal upfront thought when prototyping a single feature. | Burns scarce `500 MB` Postgres and `1 GB` / `5 GB` Supabase Storage/egress caps first; forces premature `$25/mo` Supabase Pro upgrade (`[[AgDR-0043]]`). | **Rejected** |
| **O2 — Cloudflare-only (replace Supabase Postgres/Auth with D1 + custom auth)** | Single vendor on Cloudflare Free. | Violates Postgres SSOT (`[[AgDR-0043]]`), forfeits `98+` RLS-governed tables, `security_barrier` views, `SECURITY DEFINER` audit triggers (`[[T614]]`), and GoTrue OAuth/MFA. | **Rejected** |
| **O3 — Strict Free-Tier-First Cascade: Client/Static → Cloudflare Free Tier First → Supabase Free Tier Second → Triggered Paid Ladder** | Exploits `10 GB` `$0`-egress R2, `3M/mo` Workers requests, free Turnstile, and `10k/day` Workers AI Neurons first while preserving Supabase Postgres (`500 MB`) exclusively for high-value relational truth, Auth, RLS, and audit logs at `$0/mo`. | Requires client-side media compression, HTTP delta manifests instead of chatty polling/WebSockets, and graceful degradation when daily free AI neurons cap out. | **Accepted (`[[T630]]`)** |

## Decision

Every feature, specification, migration, and runtime service across `@wom` MUST allocate resources in the following **4-Tier Free-Tier-First Order**:

| Priority | Tier | Mandatory Responsibilities | Hard Guardrails |
|---|---|---|---|
| **Tier 0** | **Client, Browser & Static Build (`$0`, zero quota)** | Resize/compress images to WebP (`<= 1600px`) in-browser; encode voice notes with Opus (`16–32 kbps`) + precompute 40-bar waveforms client-side; compute SHA-256 digests & `@webomage/fingerprint` signals via Web Crypto; serve static marketing/docs via Wrangler static assets. | Never upload raw uncompressed camera photos or multi-megabyte WAV/PCM audio to edge endpoints; keep edge ZIP/archive builders zero-CPU (`store` method `0`) within Workers Free `10 ms` CPU budget. |
| **Tier 1** | **Cloudflare Free Tier FIRST (`$0/mo` primary edge, storage, cache, AI & shield)** | **Workers / Astro SSR** for HTTP APIs & gateways; **R2 (`VAULT_R2` / `PUBLIC_ASSETS`)** for all binary media, todo/wishlist attachments, engagement vaults, and backups; **KV** + Cache API for hot public reads; **Turnstile + `@webomage/fingerprint`** at the front door of every public order/intake form; **Workers AI** (`10k Neurons/day`) for opportunistic inference (e.g. Whisper voice transcription); **Cloudflare DoH** for DNS `TXT` ownership checks. | Prefer single-round-trip JSON delta sync (`delta_sync`) over chatty per-file WebDAV `PROPFIND`; never add Workers Paid-only bindings (`Queues`, `Containers`, `Vectorize`) without an owner-approved `[[AgDR-0043]]` trigger; always fail-honest (preserving raw R2 audio/data) if daily free Workers AI neurons are exhausted. |
| **Tier 2** | **Supabase Free Tier SECOND (`$0/mo` relational SSOT, Auth & RLS)** | **GoTrue Auth** (sessions, OAuth, MFA, magic links); **Postgres RLS** tables, `security_barrier` public views (`authz-public-views.jsonc`), `SECURITY DEFINER` RPCs (`authz-definers.jsonc`), and append-only `*_audit_log` triggers (`[[T614]]`). | Store **only** compact relational rows, R2 object keys, SHA-256 hashes, and bounded JSONB metadata in Postgres (`500 MB` cap). **Banned**: storing binary blobs/base64 media in Postgres or new buckets in Supabase Storage (`1 GB` / `5 GB` egress cap) when R2 fits; running expensive unverified scans or writes prior to Turnstile + Fingerprint + ownership gates; opening idle Realtime channels where HTTP delta/on-focus fetch suffices. |
| **Tier 3** | **Paid Tier Escalation (`[[AgDR-0043]]` triggers + owner confirm)** | `Cloudflare Workers Paid ($5/mo)` first, `Supabase Pro ($25/mo)` second. | Never assumed by agents; requires crossing a measured `[[AgDR-0043]]` threshold (`70%` quota warning) and explicit owner confirmation (`Money, accounts, and public posts stay owner-only`). |

## Consequences

- **Positive:**
  - Keeps recurring infrastructure spend at **`$0.00/mo`** while unlocking media-rich todos, shared public wishlists, cross-platform Obsidian R2 vault sync, and domain-verified security audits.
  - Protects Supabase's scarce `500 MB` database and unmeasurable `5 GB/mo` egress budget by offloading `100%` of new object/media/vault payloads and bot-filtering traffic onto Cloudflare's `10 GB` `$0`-egress R2 and `1M/mo` Turnstile free tiers.
  - Eliminates unauthorized/bot-driven website scanning costs by deferring `runPassiveDomainAudit` until Turnstile + Fingerprint + post-registration zero-page-code domain ownership (`DNS TXT` or `/.well-known/w0m-verify.txt`) succeed (`[[T630]]`).
- **Negative / Trade-offs:**
  - Workers Free enforces a `10 ms` CPU ceiling per request and `5` account cron slots (`w0m-cf`), requiring streaming/store-mode binary handling and multiplexed cron dispatch.
  - Workers AI Free caps at `10,000` Neurons/day; features using `@cf/*` models (such as Whisper voice-note transcription) must treat AI enrichment as additive (`transcript_status = 'failed'` fallback while keeping the playable R2 voice note intact).

## What this does NOT decide

- Does not alter the quantitative paid-tier upgrade thresholds already established in `[[AgDR-0043]]` (`Workers Paid $5/mo` at Tier 1 triggers; `Supabase Pro $25/mo` at `>= 70%` of `just supabase-limits`).
- Does not mandate migrating legacy pre-existing `555` objects out of Supabase Storage inside this decision, though all new object/media/vault surfaces must target Cloudflare R2 (`Tier 1`).
