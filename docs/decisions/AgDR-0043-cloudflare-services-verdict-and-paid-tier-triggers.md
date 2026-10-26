---
id: AgDR-0043
title: "Cloudflare Catalogue Verdicts, Free-Tier Adoptions (KV, Turnstile, Email Routing), and Paid-Tier Upgrade Triggers (Workers Paid $5/mo Before Supabase Pro $25/mo)"
timestamp: 2026-10-25T23:25:00Z
agent: antigravity
model: claude-opus-4-6
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T271
---

# AgDR-0043 — Cloudflare Catalogue Verdicts, Free-Tier Adoptions, and Quantitative Paid-Tier Triggers

## Y-statement

> In the context of **surveying the Cloudflare Developer Platform catalogue against real `@wom` estate needs (`[[T271]]`) and comparing `Cloudflare Workers Paid ($5/mo = $1.67/mo/project)` against `Supabase Pro ($25/mo = $8.33/mo/project)` using `[[T272]]` per-project cost attribution**, facing **standing free-tier discipline (`[[AgDR-0003]]`), a `5/5` account cron ceiling on `wom7func`, single-laptop backup execution (`[[AgDR-0005]]`), and the discovery that Supabase Pro base (`$25/mo`) neither includes PITR (`+$100/mo` add-on = `$125/mo`) nor backs up Supabase Storage (`555` objects)**, we decided **to keep `[[AgDR-0003]]` ($0/mo free tiers) in force today, adopt the proven free-tier Cloudflare winners (`Workers KV` for `[[T262]]` outage resilience, `Turnstile` for `[[T81]]` auth/form hardening, `Email Routing` for inbound `@webomage.com` role aliases, and `R2` + free Zone Image Transformations for public media), defer `Hyperdrive` (`REVISIT-WHEN-X` due to `439` PostgREST RLS call sites and `60s` non-invalidating cache), and rank `Cloudflare Workers Paid ($5/mo)` ahead of `Supabase Pro ($25/mo)` with explicit quantitative upgrade triggers**, to achieve **resilient public rendering, bot-hardened auth, and zero unbudgeted recurring spend while ensuring the first `$5/mo` of future spend eliminates the single-laptop backup risk (`[[AgDR-0005]]`) at 1/5th the price of Supabase Pro**, accepting **that local `launchd` → `r2://wom7-backups` remains the backup producer until a Tier 1 trigger fires**.

## Context

1. **Re-measurable Binding Baseline (`[[T271]]` AC8, `scripts/cf_bindings_inventory.py`):**
   - Across `7` Wrangler configs (`wom7api`, `wom7func`, `wom7web/apps/{cp,demo,job,join,web}`), the estate uses `ai`, `browser`, `workflows` (`19`), `durable_objects` (`CHAT_MEMORY`), `kv_namespaces` (`SESSION`, `SETTINGS`), `r2_buckets` (`PUBLIC_ASSETS` + `wom7-backups`), `services` (`CF_WORKERS`, `WOM7API`), and `5/5` account cron triggers.
2. **Tested Resilience & Architecture Reality (`[[T271]]` AC4/AC7):**
   - **Hyperdrive vs KV for `[[T262]]`:** Live probes confirmed IPv6 (`138 ms`, TLS `b'S'`) and Supavisor IPv4 (`302 ms`, TLS `b'S'`) reachability on Supabase Free, but Hyperdrive's `60s` cache has no write-invalidation, cannot serve an extended Supabase outage, and cannot replace `439` `.from()` PostgREST calls across `98` RLS tables without shifting RLS enforcement to manual caller `set_config` transactions. **Workers KV** (free `100k` reads/day, already bound on `apps/web`) solves `[[T262]]` cleanly.
   - **Turnstile (`AC4`):** Already wired on 3 public forms (`contact-submit`, `apply-submit`, `submit-service-request`) via `wom7api/supabase/functions/_shared/turnstile.ts`; extending it to `/api/auth/*` (`[[T81]]`) costs `$0/mo` (`1M` free assessments/mo).
3. **`Workers Paid ($5/mo)` vs `Supabase Pro ($25/mo)` vs `Supabase PITR ($125/mo)` (`[[T271]]` AC9/AC10, `[[T272]]`):**
   - Across `3` active client projects (`artemio`, `1945`, `bridgeroad`), Workers Paid costs **`$1.67/mo/project`**, Supabase Pro base costs **`$8.33/mo/project`**, and Supabase Pro + 7-day PITR costs **`$41.67/mo/project`** (`$25` base + `$100` PITR add-on).
   - **Neither `$25/mo` Supabase Pro nor `$125/mo` PITR backs up the `555` objects in Supabase Storage (`[[T229]]`)**, and base Pro daily backups are 24-hour snapshots, not PITR. Running our proven `pg_dump` + Storage tarball backup (`[[T231]]`) inside a **Cloudflare Container on Workers Paid (`$5/mo`)** removes the single-laptop dependency (`[[AgDR-0005]]`) for both DB and Storage at `1/5th` the cost of Supabase Pro.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Option 1: Keep `AgDR-0003` ($0/mo) + adopt Free CF winners + lock quantitative paid triggers** | `$0/mo` recurring spend today; solves `T262`, `T81`, and inbound mail immediately; prevents buying `$25/mo` Supabase Pro under the false belief it includes `$100/mo` PITR or Storage backups | Local Mac `launchd` remains the backup producer until Tier 1 trigger fires | **ACCEPTED** |
| **Option 2: Upgrade to Cloudflare Workers Paid (`$5/mo`) immediately** | Unlocks Containers (off-laptop backups), `250` crons, Queues, Vectorize for `$1.67/mo/project` | Violates `AgDR-0003` while current `5/5` crons and `launchd` backups (`just backup-freshness --r2`) are green | Deferred until Tier 1 trigger fires |
| **Option 3: Upgrade to Supabase Pro (`$25/mo`) immediately** | `8 GB` DB cap, `250 GB` egress, daily managed DB snapshots | `5×` cost of Workers Paid (`$8.33/mo/project`), does **not** include PITR (`+$100/mo`), and does **not** back up `555` Storage objects | Rejected for now |
| **Option 4: Adopt Hyperdrive for `T262`** | Free `100k` queries/day; IPv6 reachable (`138 ms`) | Fails `T262` (`60s` cache, no write-invalidation) and endangers `98` RLS tables across `439` PostgREST call sites | Rejected for `T262` (`REVISIT-WHEN-X` for latency only) |

## Decision

1. **Catalogue Verdicts (`[[T271]]` AC5/AC6):**
   - **ADOPT (Free Tier, `$0/mo`):** `Workers KV` (routed to `[[T262]]`), `Turnstile` (routed to `[[T81]]`), `Email Routing` (inbound `@webomage.com` role aliases alongside `[[AgDR-0040]]`), and `R2 + Free Zone Image Transformations` (`<= 5,000` unique transformations/mo).
   - **REVISIT-WHEN-X:** `Hyperdrive` (only if CP server-side latency is proven to be PostgREST-bound and unfixable via `.rpc()`), `Containers` / `Vectorize` / `Queues` (when Workers Paid `$5/mo` is unlocked).
   - **REJECT:** `Analytics Engine` (redundant with Workers `observability` + Tinybird `[[T43]]`), `D1` (violates Postgres SSOT), and paid `Cloudflare Images` (`$5/mo` storage redundant with R2).
2. **Ordered Upgrade Ladder & Quantitative Triggers (when `[[AgDR-0003]]` is superseded):**
   - **First Paid Upgrade — Cloudflare Workers Paid (`$5.00/mo` = `$1.67/mo/project`):** Triggered when (a) a 6th cron schedule cannot be multiplexed into `wom7func`'s `5/5` slots, (b) `just backup-freshness --r2` breaches `max_age_days` more than twice in 14 days due to laptop-off windows (moving `[[AgDR-0005]]` backups to a Cloudflare Container), or (c) Worker invocations cross `70,000/day` (`70%` of Free cap).
   - **Second Paid Upgrade — Supabase Pro (`$25.00/mo` = `$8.33/mo/project`):** Triggered only when `just supabase-limits` warns at `70%` of the `w0m` DB cap (`>= 350 MB` of `500 MB`), Storage cap (`>= 700 MB` of `1 GB`), or monthly egress (`>= 3.5 GB` of `5 GB`), or when a client contract explicitly funds Pro/PITR in `[[T272]]`.

## Consequences

- **Positive:**
  - `scripts/cf_bindings_inventory.py` makes Wrangler binding usage across all `7` configs re-measurable in `< 0.4s`.
  - Prevents a `$300/yr`–`$1,500/yr` premature Supabase spend by proving that `$25/mo` Pro excludes PITR (`+$100/mo`) and Storage backups, and establishes `$5/mo` Workers Paid + Containers as the first-line operational upgrade.
- **Negative:**
  - Until a Tier 1 trigger fires, `[[AgDR-0005]]` (`launchd` on the owner's machine) remains responsible for daily/weekly backup production.

## What this does NOT decide

- Does not supersede `[[AgDR-0003]]` or `[[AgDR-0005]]` today — both remain `status: accepted` until one of the quantitative triggers in Decision §2 fires.
