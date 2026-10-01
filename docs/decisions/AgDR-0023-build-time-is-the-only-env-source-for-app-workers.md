---
id: AgDR-0023
title: "Delete the `|| process.env.X` fallback in the app Workers — build time is the only source, and the fallback made that look untrue"
timestamp: 2026-09-19T21:30:00-05:00
agent: claude-code
model: claude-opus-5
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T404
---

# AgDR-0023 — Build time is the only env source for the app Workers

## Y-statement

> In the context of **four Astro-on-Cloudflare app Workers whose Supabase config is inlined by Vite
> at build time**, facing **a `|| process.env.X` fallback beside every read that has never once
> executed and that sent a live outage's diagnosis to Cloudflare's secret store instead of to the
> build command**, we decided **to delete the fallback and enforce provisioning at build time with
> a post-build gate**, to achieve **one honest source of truth and a failure that is caught before
> deploy rather than by users**, accepting **that rotating `PUBLIC_SUPABASE_URL` or
> `PUBLIC_SUPABASE_ANON_KEY` now requires rebuilding and redeploying all four apps, because no
> running Worker can pick up a new value on its own**.

## Context

**Measured 2026-09-19/20**, during and after the outage that prompted this.

`webomage.com` and `cp.webomage.com` both returned 500 with
`Middleware Error: Supabase environment variables are missing`. The cause was not the code, the
Worker, or the secret store: an agent ran `pnpm --filter web build` **without**
`infisical run --env=beta`, then `wrangler deploy` from `apps/web/dist/server`, bypassing
`just deploy-web` (which wraps the build in `infisical run`).

Three facts, each verified rather than reasoned about:

1. **The fallback is inert.** The `webomage` Worker HAS `PUBLIC_SUPABASE_URL` set as a Cloudflare
   secret, the deployed code DOES read `process.env.PUBLIC_SUPABASE_URL`, and it still threw. All
   five app Workers are `compatibility_date` **2024-11-18** with `nodejs_compat`
   (`apps/{web,cp,join,job,demo}/wrangler.json`), which predates Workers populating `process.env`
   from bindings. The object is empty at runtime.
2. **Build-time inlining is the only working source.** `import.meta.env.X` is replaced with a
   literal by Vite. Re-proved 2026-09-19 on `apps/job`: built under `infisical run` the bundle
   carries both values and no throw; built bare it carries the throw and neither value.
3. **The shape was widespread.** 23 occurrences of `import.meta.env.X || process.env.X` across 14
   worker-bundled files — `packages/lib/src/auth/{server-client,middleware}.ts`, all three apps'
   `src/lib/supabase-ssr.ts`, and 9 routes (8 in CP, 1 in web).

The estate has also already written the working alternative down: `apps/demo` reads the runtime env
properly, via `import { env } from "cloudflare:workers"` — so "make the fallback real" is a live
option here, not a hypothetical.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **A. Delete the fallback; gate the build** | One source of truth, and the code says so. Failure stays loud and total, i.e. catchable. The gate moves detection from *users* to *before `wrangler deploy`*. | A rotated URL/anon key needs a rebuild + redeploy of 4 apps. | ✅ **chosen** |
| **B. Make it real via `cloudflare:workers` env** | A runtime safety net that actually fires; matches `apps/demo`. | 🔴 **Half-fixes an unprovisioned build.** These are `PUBLIC_*` values, so Vite also inlines them into the CLIENT bundle — a server-side runtime read cannot reach that half. The 500 becomes a server that works and a browser that silently cannot authenticate. A loud total failure is traded for a quiet partial one. Also creates two sources that can disagree: built against one project, running against another. | ❌ |
| **C. Make it real by raising `compatibility_date`** | One config line per app. | Same client/server split as B, plus it changes **every** compat-flag default between 2024-11-18 and today across all four production Workers, to fix a problem that is not a runtime problem. Blast radius wildly out of proportion. | ❌ |
| **D. Keep the fallback, add the gate only** | Smallest diff. | Leaves the code asserting a safety net that does not exist. That assertion is not free: it is what sent the outage's diagnosis to the Cloudflare secret store (where everything was correctly set) instead of to the build command. | ❌ |

## Decision

Delete every `|| process.env.X` fallback from worker-bundled source (23 occurrences, 14 files) and
let `import.meta.env.X` stand alone. Keep the existing `throw new Error("Supabase environment
variables are missing")` — a missing value must stay loud.

Enforce the now-single source with `project/scripts/build_provisioning_gate.py`, called by
`just deploy-{web,cp,join,job}` after the build and **before** `wrangler deploy`. It fails closed
on an absent bundle, and refuses to pass itself if the sentinel it greps for ever leaves the source.

If a genuine runtime read is ever needed, the route is `import { env } from "cloudflare:workers"`
(as `apps/demo` uses) — not `process.env`, and not without revisiting option B's client/server
split first.

## Consequences

**Positive.** The code now states what is true. The 2026-09-19 failure mode cannot reach production
through `just deploy-*` — it is caught at build time with a message naming the cause. The inverted
diagnostic (*a hit means broken*) is executable instead of tribal. The survey done under T404 found
a second, worse class the fallback was hiding: 11 worker-bundled `process.env` reads with **no**
`import.meta.env` alternative at all — code that has simply never run.

**Negative.** Rotating `PUBLIC_SUPABASE_URL` or `PUBLIC_SUPABASE_ANON_KEY` is now unambiguously a
rebuild-and-redeploy of all four apps; there is no runtime path left that could pick a new value up.
This was already true in practice (the client bundle was always build-time only) — the decision
makes it explicit rather than introducing it. A hand-run `wrangler deploy` still bypasses everything;
no justfile can prevent that, and the gate closes the sanctioned path only.

## What this does NOT decide

- **It does not ban `process.env` in this repo.** Astro configs, Playwright configs, `apps/*/scripts/*.mjs`
  and the Python/Node tooling all run in Node, where `process.env` is real and correct (27 such reads,
  measured). The decision is scoped to source bundled into an app Worker.
- **It does not dispose of the 11 sole-source worker-bundled `process.env` reads** it uncovered
  (`packages/lib/src/{supabase.ts,auth/handlers.ts}`, `apps/cp/src/pages/api/bug-report.ts`, …).
  Those are dead reads, not inert fallbacks: deleting one deletes a feature that has never worked,
  which is a per-site judgement. Filed as T404 AC5.
- **It does not raise any app's `compatibility_date`.** That may still be worth doing for unrelated
  reasons; it is not a consequence of this.
