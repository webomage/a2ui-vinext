---
id: AgDR-0005
title: "This machine produces backups; Cloudflare stores them — no Worker in the loop"
timestamp: 2026-08-18T00:00:00Z
agent: claude-code
model: claude-opus-5
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T231
---

# AgDR-0005 — The backup producer is this machine

## Y-statement

> In the context of **backups proven to restore but living only on one laptop**, facing **a Worker
> that cannot run `pg_dump` and 5/5 Cloudflare cron slots already used**, we decided **to produce
> backups here via the existing launchd scheduler and push them to R2 directly**, to achieve **an
> offsite copy without new infrastructure**, accepting **that a laptop which is off does not run
> them**.

## Context

Owner, 2026-08-18: *"we can schedule backups triggering and performing at CF side and store backup
also on CF."* Inventoried rather than assumed:

| Candidate | Runs `pg_dump`? | Why not |
|---|---|---|
| Cloudflare Workers | ❌ | native binary; no equivalent |
| CF **Containers** | ✅ technically | needs Workers **Paid** — against [[AgDR-0003]] |
| Supabase Edge Functions | ❌ | Deno; only via a hand-rolled export nobody has restored |
| GitHub Actions | ✅ technically | **dead on this account — 339/339 `startup_failure`** |
| Hostinger | — | **not ours** — legacy for the 1945 project |
| **Local Mac** | ✅ **17.9 installed** | — |

🔑 **The scheduler already existed and was proven**: `project/launchd/schedules.jsonc` →
`just tools-schedule` → generated plists, with two agents firing on their declared days.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Worker triggers a dump elsewhere | keeps CF in the loop | the Worker adds a hop and decides nothing | rejected |
| Worker writes its own logical export | no `pg_dump` needed | 🔴 **an untested restore path** — the exact false confidence [[T229]] removed | rejected |
| **Mac produces, pushes to R2** | uses a proven dumper and an existing scheduler; no new infra | laptop must be on | **ACCEPTED** |
| Worker mirrors Mac→R2 | matches the original sketch | ⚠️ **impossible** — a Worker cannot reach a file on this laptop, so there is nothing to mirror *from* | rejected on measurement |

## Decision

`com.w0m.backup-daily` (03:15) and `com.w0m.backup-weekly` (Sun 04:00) run here; both push to
`r2://wom7-backups` and verify by round trip. **No Worker is involved** — the producer already holds
the bytes, so the producer uploads.

## Consequences

**Positive.** Offsite and proven: the R2 dump was pulled back and **restored** (114/114 tables, 6/6
content tables byte-identical), and the Storage tarball verified at **555/555 objects**. Adding
backups was an entry in a JSONC file, not new infrastructure.

**Negative.** 🔴 **A laptop that is off does not back up.** `StartCalendarInterval` fires on wake
after a missed run, so it degrades rather than fails silently — but a week away is a week with no
dump. This is acceptable **only because it is observable**: `just backup-freshness --r2` goes red
within `max_age_days` on **both** copies. Debt **D57** carries the residue. Also: `_confirm` needs a
TTY launchd lacks, so the scheduled recipes are **ungated by decision** — consent moved to a
versioned schedule reviewable in a diff, which is auditable in a way a prompt is not.

## What this does NOT decide

Not that a Worker is never used for backups — the Storage→R2 path could move cloud-to-cloud later.
Not the last hop of recovery: **re-uploading 555 objects into live Supabase Storage remains
untested** (debt **D59**) because there is no scratch bucket.
