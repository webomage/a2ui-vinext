---
id: AgDR-0003
title: "Stay on the Supabase Free tier; Pro only if genuinely needed"
timestamp: 2026-08-18T00:00:00Z
agent: human
model:
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T229
---

# AgDR-0003 — Stay on Supabase Free

## Y-statement

> In the context of **two Supabase projects on the Free tier after a downgrade**, facing **limits
> that fail abruptly rather than gradually**, we decided **to stay on Free and not hit the limits**,
> to achieve **no recurring spend while the estate is pre-revenue**, accepting **no PITR, a 2-project
> per-org cap, and egress we cannot even measure**.

## Context

Owner, 2026-08-18: *"one project should be stale with no activity, and the second (w0m) could get Pro
if we really need it — but for now let's keep Free and try not to hit limits."*

Measured the same day:

- **Two organisations, both `plan: free`** — `webomage` (**2/2 projects, at the cap**) and
  **`w0m space` (0/2, empty)**. ⚠️ The MCP reports **one** org; the Management API PAT reports both.
- ⇒ **A third project does not need Pro. It needs the other org.**
- w0m project: **68 MB database (13.5% of 500 MB)**, 53.9 MB storage (5% of 1 GB) — comfortable.
- 🔴 **Egress (5 GB/month) is NOT measurable**: `/v1/projects/{ref}/usage`,
  `/v1/organizations/{id}/usage` and `/daily-stats` all **404**.
- The downgrade's real cost was **backups**, not limits — no PITR and an empty backup list, which is
  what [[T229]] was filed for.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Stay on Free** | no spend; measured headroom is comfortable | no PITR; 2-project cap; egress unmeasurable; limits fail abruptly | **ACCEPTED** |
| Upgrade w0m to Pro | PITR, 250 GB egress, higher caps | recurring cost while pre-revenue; solves a backup problem [[T229]] solved for free | rejected for now |
| Upgrade both orgs | uniform | doubles the cost for a project that is now paused | rejected |

## Decision

Free tier stays. **Because the limits are chosen rather than imposed, the headroom is a budget and
must be watched** — `just supabase-limits` reports plan, project count against the cap, and
database/storage against their limits, warning at 70% and failing at 90%.

## Consequences

**Positive.** No spend. The constraint forced [[T229]]: a dump proven to restore, Storage covered,
scheduled, offsite in R2, and staleness watched on both copies — recovery the Pro tier would have
supplied invisibly and less verifiably.

**Negative.** No PITR: recovery granularity is the last dump, not the last minute. The `webomage`
org is **at its cap**, so a third project must go in `w0m space`. And **egress cannot be observed at
all** — it is reported as NOT MEASURED and must be read from the dashboard, so the one limit the
owner named first is the one nothing can watch.

## What this does NOT decide

Not that Pro is refused permanently — the trigger is "genuinely needed", deliberately unquantified.
Not the fate of the paused `solar_flares` project, which is [[AgDR-0004]].
