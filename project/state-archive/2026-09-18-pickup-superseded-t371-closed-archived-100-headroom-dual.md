<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ## ⭐ PICK UP HERE — 2026-09-18 (SUPERSEDED) — **T371 closed & archived (100%), Headroom dual-port architecture (:8787 Cl -->

## ⭐ PICK UP HERE — 2026-09-18 (SUPERSEDED) — **T371 closed & archived (100%), Headroom dual-port architecture (:8787 Cloud vs :8788 Local), claude-omlx standardized at 54 tok/s, T373 spec gate passed, T374 oMLX process manager delivered.**

**What this session completed:**

1. **T371 (Claude-Obsidian ecosystem, per-project client vaults, and CP knowledge hub embedding)**:
   - **Ingestion & Skills Governance**: Ingested `AgriciDaniel/claude-obsidian` (v2.2.0) into `wom7open` and governed 15 LLM Wiki skills in `wom7skills` via `.w0m/skills.json` (`wiki`, `save`, `wiki-ingest`, `wiki-query`, `wiki-lint`, `autoresearch`).
   - **Per-Project Vaults**: Standardized client project vault topologies in `clients-policy.json` (`inbox/`, `sources/`, `claims/`, `notes/`, `mocs/`) with automated initialization recipes.
   - **CP Knowledge Hub**: Delivered native Svelte 5 / Astro SSR knowledge hub at `cp.webomage.com` (`/client/vault`), rendering markdown, Mermaid diagrams, wikilinks, and interactive 2D/3D knowledge graphs with desktop deep-links (`obsidian://open?vault=...`).
   - **Archive & Ticket Closure**: Closed and archived under commit `d254cf845`.

2. **Headroom Dual-Port Architecture & Port Isolation (Cloud :8787 vs Local :8788)**:
   - **Diagnosed & Fixed 400 Context Limit Error**: Identified root cause of `API Error: 400 Prompt too long: 45396 tokens exceeds max context window of 32768 tokens` on "normal Claude". `OMLX_TARGET_API_URL` defined in `sh.brew.headroom.plist` caused Headroom's handler to classify `"model": "sonnet"` as `not is_cloud`, diverting cloud sessions into local oMLX hardware.
   - **Strict Port Partitioning**: Removed `OMLX_TARGET_API_URL` from Port 8787 (`sh.brew.headroom`), dedicating it 100% to Anthropic Cloud (`https://api.anthropic.com`, full 200k context). Dedicated Port 8788 (`sh.brew.headroom-local`) strictly to local oMLX (`http://127.0.0.1:8888`).

3. **Local Inference Acceleration & Model-Agnostic `claude-omlx` Abstraction**:
   - **Throughput Breakthrough**: Replaced memory-leaking Gemma 4 12B with `mlx-community/Qwen2.5-Coder-7B-Instruct-4bit`. RAM footprint plummeted from 18.8 GB to 4.17 GB, completely eliminating 20.6 GB of host SSD swap thrashing and accelerating inference **540x** (from 0.1 tok/s to 54.1 tok/s).
   - **Universal Local Identity**: Decoupled agent tooling from ephemeral weight names by standardizing on `claude-omlx` across oMLX backend (`model_alias: claude-omlx`), `~/.openclaude/settings.json`, and `/Users/proto/.local/bin/claude-omlx` (with `opencode` and `openclaude` symlinks). Verified sub-second CLI turns.

4. **T373 (Unified Stripe Commercial Billing) — Completed & Archived (100%)**:
   - **Database**: Migration `20260918120000_t373_stripe_commercial_billing.sql` applied live via `just db-migrate` (285/285 schema migrations synchronized, `just db-drift-check` clean). Added Stripe customer and subscription metadata to `public.clients` and Stripe session identifiers to `public.invoices`.
   - **Backend / Edge Functions**: Built `stripe-billing.ts` shared library (`wom7api`), updated `stripe-checkout` to support `audit`, `subscription`, and `invoice`, implemented signature-verified `stripe-webhook` handling `checkout.session.completed`, `customer.subscription.*`, `invoice.paid`, and added `stripe-portal` endpoint. 58/58 edge function entrypoints pass Deno check, 141 Deno tests pass.
   - **Frontend**: Shipped `/audit` with `AuditPricing.svelte` on main (`apps/web`), `/client/billing` with `SubscriptionManager.svelte` and `/api/client/billing-portal` proxy in CP (`apps/cp`), linked in `ClientLayout.astro`, and wired `amount_usd` in `InvoiceList.svelte`. `just typecheck` 0 errors across all 4 apps; `pnpm test` 335/335 passed.
   - **Reconciliation & Anti-Vacuity**: Implemented `wom7api/scripts/reconcile_stripe_invoices.py` with 3-state exit contract (`0` = matched, `1` = mismatched/vacuous, `2` = unmeasurable). Verified via unit tests (`Ran 2 tests, OK`) and live recipe `just reconcile-stripe` asserting anti-vacuity protection.
   - **Archive**: OpenSpec change archived to `openspec/specs/commercial-billing/spec.md`. Ticket T373 closed across all surfaces (`project/tickets/T373.md`, `TASKS.md`, GitHub Project #2 Issue #373).

5. **T374 (Unified oMLX Process & Service Management)**:
   - Delivered `project/scripts/omlx_service.py` to arbitrate port 8888 across Homebrew daemon (`sh.brew.omlx`), desktop GUI (`oMLX.app`), and manual CLI runner.
   - Implemented multi-mode PID discovery, graceful SIGTERM/SIGKILL port clearing, and exposed estate recipes: `just omlx-status`, `omlx-start`, `omlx-stop`, `omlx-restart`.

6. **T8 (Guardrails: `llama-guard-3-8b` AI Safety Classification) — Completed, Deployed & Archived (100%)**:
   - **Backend / Edge Functions**: Implemented `@cf/meta/llama-guard-3-8b` classifier in `_shared/guardrails.ts` with Cloudflare Workers AI integration (`/ai/chat` proxy), supporting `safe` vs `unsafe\nS<category>`, fail-closed error handling, and synthetic test bypasses (`isE2EBypassRequest`).
   - **Integration**: Wired input safety classification before RAG embedding/search and output classification before response delivery in `agent-consultant` and `_shared/chat-core.ts`. Emitted telemetry (`guardrail_reason`, `was_blocked`) to `ai_usage` and structured JSON logs. Blocked malicious turns from entering Durable Object chat memory.
   - **Testing & Verification**: 100% test pass in `guardrails.test.ts` across 155 edge tests. Deployed live to Supabase production (`pqbbjgeapylcengbuvee`). Verified benign query returns grounded answer; verified hostile injection query immediately triggers `SAFE_REFUSAL_INPUT` without token burn or DO memory poisoning.
   - **Downstream Impact**: Ticket T8 closed across all surfaces (`project/tickets/T8.md`, `TASKS.md`, `project/tickets.json`). Change archived to `openspec/specs/ai_guardrails/spec.md`. Unblocked **T22 AC4** (`blocked_by` cleared).

7. **T201 (Cloudflare Turnstile Migration & Secret Hygiene) — Completed, Verified & Closed (100%)**:
   - **Frontend**: Replaced hCaptcha across all forms (`ContactFormSection.astro`, `ApplicationForm.svelte`, `ChatApp.svelte`, `careers.astro`) in `apps/web` and `apps/cp` with Cloudflare Turnstile (`cf-turnstile` widget `0x4AAAAAAE9GS8gtYiRYPdzL`), backed by config-driven `PUBLIC_TURNSTILE_SITE_KEY`.
   - **Backend / Edge Functions**: Created `_shared/turnstile.ts` with `verifyTurnstileToken()` and `turnstileConfigured()`. Migrated `contact-submit`, `apply-submit`, and `submit-service-request` to validate Turnstile tokens via siteverify endpoint. Added `TURNSTILE_SECRET` to `sync_supabase_secrets.py` allowlist.
   - **Verification & Acceptance**: Gauge test `010-contact-secure.spec` rewritten for Turnstile and verified 4/4 passing against live production.
   - **Secret Hygiene**: Verified `DEBUG_BYPASS_KEY` rotated and cleartext fallbacks eliminated from specs and test files. Deleted `HCAPTCHA_SECRET` from Supabase function secrets and Infisical `beta` (with `--type=shared`).
   - **Ticket Closure**: Closed and archived across all surfaces (`project/tickets/T201.md`, `TASKS.md`, `project/tickets.json`, GitHub Issue #201).

8. **T399 (Cloudflare Infrastructure Cutover & wom7cfworkers Decommission) — Completed, Deployed & Archived (100%)**:
   - **Secrets & Configuration**: Synced all 21 production secrets to `wom7func` via Infisical (`beta`); updated `WORKERS_WEBHOOK_URL` to `https://wom7func.webomage.workers.dev` in Infisical and consumer workers.
   - **Cron Triggers**: Cleared 5 legacy cron schedules from `wom7cfworkers` and bound all 5 schedules to `wom7func` (`0 14 * * SUN`, `0 */6 * * *`, `0 8 * * *`, `*/15 * * * *`, `*/30 * * * *`).
   - **Runtime & Consumers**: Updated `wom7func/src/index.ts` to return `service: "wom7func"`; updated `HealthDashboard.svelte`, `sources.ts`, and `w0m_audit.py`. Redeployed `webomage` and `webomage-cp` workers to bind `wom7func`.
   - **Decommissioning**: Successfully called Cloudflare API `DELETE /workers/scripts/wom7cfworkers` (HTTP 200). Verified worker list contains only `wom7func` and active web apps.
   - **Governance & Ticket Closure**: Updated workspace root scripts (`no_nested_repos.py`, `install_excludes.py`) and `wom7func` repository metadata. Closed T399 across all surfaces (`project/tickets/T399.md`, `TASKS.md`, GitHub Issue #399).

**Next immediate action:**
- Pick up next ticket: **T22** (Standing project health, status & continuous monitoring — now #1 on both Hot and SDLC boards, 75% complete, unblocked) or **T290** (Stage-4 Money & Reconciliation).
