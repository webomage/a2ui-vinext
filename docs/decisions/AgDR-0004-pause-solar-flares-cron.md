---
id: AgDR-0004
title: "Pause the solar_flares cron by deactivating, not unscheduling"
timestamp: 2026-08-18T00:00:00Z
agent: claude-code
model: claude-opus-5
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T229
---

# AgDR-0004 — Pause solar_flares by deactivating

## Y-statement

> In the context of **a project the owner put on hold that was in fact running a 5-minute cron**,
> facing **a shared Free-tier budget it was quietly consuming**, we decided **to deactivate the job
> rather than unschedule it**, to achieve **an immediate stop that is reversible in one statement**,
> accepting **that the job definition — including a plaintext service_role JWT — stays in the
> database**.

## Context

Owner, 2026-08-18: *"let's kill solar_flares cron — the project on hold for now."*

🔴 **It was believed idle and was not.** Measured before acting:

- `cron.job` id 1, schedule `*/5 * * * *`, **active**, calling `net.http_post`.
- **81,052 runs since 2025-11-10** · 288 in the last 24 h · **0 failed**.
- `public.space_weather_data`: **301,044 rows / 215 MB**, growing **+973 rows/day**.
- Database **284 MB — 4× the w0m project's 68 MB — ≈57% of the Free 500 MB cap**.
- 📌 `last_autovacuum` said *today* and **proved nothing** — autovacuum runs on idle databases.
  What settled it was `cron.job_run_details`, i.e. asking what had **executed**.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **`cron.alter_job(active := false)`** | stops immediately; definition, schedule and history survive; resume is one statement | the plaintext JWT stays in `cron.job` | **ACCEPTED** |
| `cron.unschedule()` | removes the row and the secret with it | destroys the definition and 81k runs of history for a project only *on hold* | rejected |
| Leave it running | no action | consumes a shared budget for a paused project; ~8 months to its cap | rejected |

## Decision

Deactivated. **"On hold" is not "delete forever"**, so the reversible form was chosen:

```sql
select cron.alter_job(job_id := 1, active := true);   -- resume
```

## Consequences

**Positive.** Growth stopped — verified by **output, not by the flag**: checked at 19:05:55 after the
19:00 *and* 19:05 boundaries, `runs_since_pause 0`, `rows_since_pause 0`, last run still 18:55. The
~8 months of runway is held rather than reset, and `cron.job_run_details` (54 MB, ~19% of the
database) remains reclaimable.

**Negative.** 🔴 **The job command contains a hardcoded `service_role` JWT in plaintext**, and
deactivating does **not** remove it. `service_role` bypasses RLS entirely, so anyone who can read
`cron.job` — or any dump of that database — holds a full-access key. **Pausing hid the job, not the
secret.** Per [[leaked-db-superuser-2026-07-12]] the rule is *rotate, do not hide*, and that rotation
has **not** been done: it is an outward-facing change on a project outside w0m's remit.

## What this does NOT decide

Not whether the project resumes. Not the JWT rotation, which is an owner action and remains open.
Not the `cron.job_run_details` retention that would reclaim 54 MB.
