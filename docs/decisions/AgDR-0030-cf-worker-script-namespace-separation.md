---
id: AgDR-0030
title: "Separate Cloudflare Worker script namespaces between wom7api and wom7func"
timestamp: 2026-08-01T12:00:00Z
agent: human
model:
trigger: audit
status: accepted
superseded_by:
supersedes:
ticket:
---

# AgDR-0030 — Separate Cloudflare Worker script namespaces between wom7api and wom7func

## Y-statement

> In the context of **having two independent edge workers in `wom7api` and `wom7func` both configured with `"name": "wom7cfworkers"` in `wrangler.jsonc`**, facing **silent script overwrite collisions during `just deploy-api` and `just deploy-workers` that destroyed endpoints and dropped cron triggers**, we decided **to enforce distinct, strictly separated Worker script namespaces (`wom7api` for backend API dispatch, `wom7func` for cron and ATS/workflow routines)** to achieve **independent deployments and complete isolation between API routes and cron routines**, accepting **the migration and DNS/route re-binding in Cloudflare**.

## Context

Prior to 2026-08-01:
- `wom7api/wrangler.jsonc` and `wom7func/wrangler.jsonc` both declared `"name": "wom7cfworkers"`.
- A deploy from `wom7api` (`just deploy-api`) replaced the worker in Cloudflare, silently unpublishing cron triggers and `/api/ats/*` routes in `wom7func`.
- Conversely, a deploy from `wom7func` (`just deploy-workers`) dropped API and workflow endpoints belonging to `wom7api`.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Merge workers into one repo** | Single deploy target | Violates boundary separation between API capability and cron workers | Rejected |
| **Monorepo script namespace separation** | Clean boundary; each worker deploys independently without collision | Requires route/trigger configuration in Cloudflare dashboard | **Accepted** |
| **Keep shared script with monolithic build** | No naming change | Fragile build-time bundling across repo boundaries | Rejected |

## Decision

1. **Explicit Script Names:** `wom7api` worker deploys as script `wom7api`. `wom7func` deploys as script `wom7func`.
2. **Cron Ownership:** `wom7func` owns all account cron schedules and ATS routines.
3. **Workflow Dispatch:** `wom7api` owns workflow dispatch (`/trigger`, `/event`). `wom7func` responds with 501 for unhandled workflow names.

## Consequences

- Deploying one repository never alters or overwrites the edge worker of the other.
- No shared script name hazards across estate repos.
