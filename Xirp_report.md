# Xirp Project Audit Report

Date: 2026-08-12
Workspace: `/Users/proto/Projects/@self/@wom`

## Scope

Reviewed active project repositories:

- `wom7api`: Supabase Edge Functions, migrations, Workers API code, wrangler config.
- `wom7web`: Astro/Svelte apps, shared auth middleware, deployment/task docs.
- `wom7cfworkers`: Cloudflare Worker cron and AI proxy surfaces.
- `wom7ext`: browser extension manifest, background bridge, content execution.
- `wom7skills` and `wom7sec`: quick posture review only.

Excluded from deep findings:

- `wom7mlx`, treated as a separate ML/vendor tree for this pass.
- Live Cloudflare/Supabase console state, because this audit used local source and local git history only.

## Method

- Used CodeGraph first in indexed repos before direct reads, per `AGENTS.md`.
- Checked trust boundaries for Edge Functions, middleware, Workers, extension messaging, deployed-source governance, and secret history.
- Cross-checked prior audit themes against current source and avoided repeating issues that are now visibly fixed.
- Limitation: the workspace union graph reported stale sub-repo indexes, so report evidence is grounded in current on-disk source reads and per-repo CodeGraph where available.

## Executive Summary

- P0: 1 finding. Historical secrets remain in git object history and rotation/purge cannot be proven locally.
- P1: 6 findings. The largest risk is Supabase Edge Function authorization: several service-role functions are callable with a public project JWT because they rely on `verify_jwt = true` without in-function authorization.
- P2: 5 findings. Extension external messaging, public analytics ingestion, newsletter HTML injection, missing CI, and Worker config drift need hardening.
- Positive controls found: admin Edge Functions now use `requireAdminAuth`, `client-api` has current role/ownership checks, `seed-demo` is service-role guarded, the extension overlay no longer uses direct `innerHTML`, and cron dispatch now logs rejected targets.

## Findings

### P0-1: Historical `.env.bak` secrets remain in git history

Status: confirmed in local git history.

Evidence:

- `git -C wom7web log --all --name-status -- apps/cp/.env.bak apps/join/.env.bak apps/web/.env.bak` shows commits `12dade3e` and `de6cf1a` adding `.env.bak` files.
- The deletion commits `85b44060` and `340ce8c3` state that the files held live AWS, Supabase service-role, database, GitHub App, and other credentials, and that rotation/purge remained separate work.
- `git -C wom7web rev-list --objects --all -- apps/cp/.env.bak apps/join/.env.bak apps/web/.env.bak` still lists historical blobs including `857a8b7f... apps/cp/.env.bak` and `c7360fb... apps/join/.env.bak`.

Impact:

- Anyone with access to cloned repo history can recover old secret values.
- If any historical value is still valid, this is direct account, database, or deployment compromise.
- Even if all values were rotated, history still creates recurring leak risk when the repo is mirrored or shared.

Recommended fix:

- Confirm every credential from the historical `.env.bak` files is rotated, including Supabase service-role keys, database URLs, AWS keys, GitHub App material, SMTP keys, and third-party API keys.
- Purge or quarantine the historical blobs using a deliberate history-rewrite process, then invalidate old clones where possible.
- Keep the current tracked-source scan in CI, but treat this as an incident-response item, not only a `.gitignore` issue.

### P1-1: Public project JWT can trigger `daily-news-scheduler` service-role work

Status: confirmed in source; exploit path requires the public Supabase anon/publishable key.

Evidence:

- Shared auth guidance states `verify_jwt = true` is not a substitute because the anon/publishable key is a valid project JWT shipped in page bundles: `wom7api/supabase/functions/_shared/auth.ts:27`.
- `daily-news-scheduler` is configured with `verify_jwt = true`: `wom7api/supabase/config.toml:174`.
- The handler creates a service-role Supabase client before processing requests: `wom7api/supabase/functions/daily-news-scheduler/index.ts:17`.
- The request handler starts at `wom7api/supabase/functions/daily-news-scheduler/index.ts:19` and performs no `requireAuth`, `isServiceRoleRequest`, cron secret, or method guard before work begins.
- It calls downstream generation functions with the service-role key: `wom7api/supabase/functions/daily-news-scheduler/index.ts:91`.
- It writes generated posts with the service-role client: `wom7api/supabase/functions/daily-news-scheduler/index.ts:116`.
- The Cloudflare cron caller also invokes `daily-news-scheduler` using `SUPABASE_SERVICE_ROLE_KEY || WEBHOOK_SECRET`: `wom7cfworkers/src/index.ts:534` and `wom7cfworkers/src/index.ts:617`.

Impact:

- A caller with the public project JWT can trigger RSS parsing, LLM post generation, image generation, and service-role writes.
- This creates cost abuse, content poisoning, and operational-noise risk.
- Cron still works because the Worker sends a service-role bearer, which can hide the public-JWT exposure during normal operation.

Recommended fix:

- Change this class of scheduler to `verify_jwt = false` only if it enforces `isServiceRoleRequest(req)` or a dedicated cron HMAC/secret inside the function.
- Add method checks, idempotency, cooldowns, and explicit rate limits.
- Add tests for both missing authorization and the public anon/publishable key path.

### P1-2: Public project JWT can trigger `weekly-digest` email sends

Status: confirmed in source; exploit path requires the public Supabase anon/publishable key.

Evidence:

- `weekly-digest` is configured with `verify_jwt = true`: `wom7api/supabase/config.toml:251`.
- The handler starts at `wom7api/supabase/functions/weekly-digest/index.ts:14` and has no in-function auth check after CORS handling.
- It creates a service-role Supabase client at `wom7api/supabase/functions/weekly-digest/index.ts:20`.
- It reads active subscribers at `wom7api/supabase/functions/weekly-digest/index.ts:86`.
- It sends email via SMTP with subscriber BCC at `wom7api/supabase/functions/weekly-digest/index.ts:108`.
- The Cloudflare scheduled worker triggers it every Sunday at `wom7cfworkers/src/index.ts:618`.

Impact:

- A caller with the public project JWT can trigger bulk newsletter sends.
- This creates spam, sender-reputation, cost, and subscriber-trust risk.
- The response includes send metadata and recipient count, which can leak operational state.

Recommended fix:

- Require `isServiceRoleRequest(req)` or an HMAC cron header before any DB read or SMTP action.
- Return a minimal response body.
- Add replay protection and an execution ledger keyed by digest period.

### P1-3: Public project JWT can poison the RAG corpus through `seed-cv`

Status: confirmed in source; exploit path requires the public Supabase anon/publishable key.

Evidence:

- `seed-cv` is configured with `verify_jwt = true`: `wom7api/supabase/config.toml:232`.
- The function creates a service-role Supabase client at `wom7api/supabase/functions/seed-cv/index.ts:13`.
- The request handler starts at `wom7api/supabase/functions/seed-cv/index.ts:44` with no in-function authorization.
- POST body text is accepted directly at `wom7api/supabase/functions/seed-cv/index.ts:50`.
- Each chunk is embedded and inserted into `documents` at `wom7api/supabase/functions/seed-cv/index.ts:57`.

Impact:

- A caller can consume embedding resources and inject arbitrary content into the document store used by retrieval paths.
- This is a persistent data-poisoning vector rather than a one-request abuse vector.

Recommended fix:

- Decommission the function if it is a legacy prototype.
- If still needed, require service-role authorization, cap input size and chunk count, attach source metadata, and insert into a quarantined namespace pending review.

### P1-4: Third-party webhooks are likely blocked before their own signature checks

Status: confirmed configuration mismatch; live delivery needs console/provider validation.

Evidence:

- `stripe-webhook` is configured with `verify_jwt = true`: `wom7api/supabase/config.toml:239`.
- The same config comment states Stripe does not send a Supabase JWT, so the gateway rejects before function code runs: `wom7api/supabase/config.toml:237`.
- The Stripe function expects Stripe's `stripe-signature`, verifies `STRIPE_WEBHOOK_SECRET`, and then marks invoices paid: `wom7api/supabase/functions/stripe-webhook/index.ts:21`, `wom7api/supabase/functions/stripe-webhook/index.ts:28`, and `wom7api/supabase/functions/stripe-webhook/index.ts:42`.
- `platform-webhook-gateway` is also configured with `verify_jwt = true`: `wom7api/supabase/config.toml:220`.
- Its real guard is HMAC verification over raw body with `PLATFORM_WEBHOOK_SECRET` or `DEEL_WEBHOOK_SECRET`: `wom7api/supabase/functions/platform-webhook-gateway/index.ts:41` and `wom7api/supabase/functions/platform-webhook-gateway/index.ts:51`.
- The gateway writes webhook payloads and upserts contracts only after its own signature verification: `wom7api/supabase/functions/platform-webhook-gateway/index.ts:69` and `wom7api/supabase/functions/platform-webhook-gateway/index.ts:79`.

Impact:

- Stripe payment settlement can silently fail before the code that marks invoices paid.
- Platform contract sync can silently fail before the HMAC guard runs.
- The security model is inverted: these endpoints have the correct provider-specific guards, but the Supabase gateway is probably preventing legitimate provider traffic from reaching them.

Recommended fix:

- Set `verify_jwt = false` for true third-party webhooks while keeping provider signature/HMAC verification fail-closed inside the function.
- Add provider delivery probes and alert on rejected webhook attempts.
- Add a deploy check that rejects `verify_jwt = true` for known third-party webhook endpoints unless the provider is confirmed to send a valid project JWT.

### P1-5: Shared web middleware treats any dotted path as a static asset and skips auth/RBAC

Status: confirmed bypass primitive in source; direct data exposure depends on route matching and existing dotted IDs/slugs.

Evidence:

- The shared middleware sets `isAsset = pathname.includes(".")`: `wom7web/packages/lib/src/auth/middleware.ts:77`.
- The auth/RBAC gate is skipped when `isAsset` is true: `wom7web/packages/lib/src/auth/middleware.ts:193`.
- CP uses this shared middleware for business/admin routes: `wom7web/apps/cp/src/middleware.ts:15`.
- The web app's dynamic visibility resolver also skips dotted paths: `wom7web/apps/web/src/middleware.ts:16`.
- Current sensitive SSR pages rely heavily on middleware and lack equivalent page-level RBAC:
  - Contracts fetch `contracts.select("*")` by route ID with no page auth guard: `wom7web/apps/cp/src/pages/business/contracts/[id].astro:14`.
  - Proposals fetch `proposals.select("*")` by route ID with no page auth guard: `wom7web/apps/cp/src/pages/business/proposals/[id].astro:10`.
  - Blueprint edit page reads cookies but does not validate them before fetching the blueprint: `wom7web/apps/cp/src/pages/business/blueprints/edit/[id].astro:20` and `wom7web/apps/cp/src/pages/business/blueprints/edit/[id].astro:25`.
  - Content edit validates only that a user exists, then can create a service-role-backed client and update posts: `wom7web/apps/cp/src/pages/content/edit/[slug].astro:30`, `wom7web/apps/cp/src/pages/content/edit/[slug].astro:66`, and `wom7web/apps/cp/src/pages/content/edit/[slug].astro:79`.

Impact:

- Any sensitive route whose pathname contains a dot bypasses the shared auth/RBAC gate.
- Existing dotted dynamic IDs or slugs can expose or mutate admin data.
- Future admin routes are likely to inherit the bypass because the static-asset test is global and easy to cargo-cult.

Recommended fix:

- Replace `pathname.includes(".")` with an explicit allowlist for true public assets, such as `/_astro/`, `/favicon.ico`, `/robots.txt`, and known extension assets.
- Add page-level RBAC to sensitive SSR pages, especially admin edit and business detail routes.
- Add route tests for dotted dynamic params, for example `/content/edit/test.slug`, `/business/proposals/foo.bar`, and private web pages with dotted slugs.

### P1-6: Live deployed Supabase functions have no local source

Status: not independently live-validated in this pass; confirmed as an open project governance finding.

Evidence:

- `wom7web/project/tickets/T199.md:141` lists `apply-migration`, `heatmap-event`, `jobs-list`, `linkedin-sync`, `otel-test`, `trigger-cloudflare-workflow`, and `trigger-hatchet-workflow` as deployed functions with no local source.
- `wom7web/project/tickets/T199.md:142` marks `heatmap-event` as publicly invokable and no local source.
- `wom7web/project/tickets/T199.md:143` marks `jobs-list` as publicly invokable and no local source.
- `wom7web/project/tickets/T199.md:151` states a redeploy from this repo will never update those functions.
- `wom7web/project/tickets/T199.md:273` calls out `heatmap-event` and `jobs-list` as open edge functions that should be handled first.

Impact:

- Production can execute code that cannot be reviewed, tested, redeployed, or patched from the repo.
- Open functions with no source are security unknowns by definition.
- Workflow trigger names are especially sensitive because they may dispatch privileged platform work.

Recommended fix:

- Pull the deployed source for each live function into a repository or delete the function after confirming no live caller depends on it.
- Prioritize `heatmap-event` and `jobs-list` because they are reported open.
- Add a deploy gate that compares local function names against live functions and fails on unmanaged production code.

### P2-1: Browser extension exposes privileged background actions through `onMessageExternal`

Status: confirmed in source.

Evidence:

- The manifest allows external messages from `https://webomage.com/*`: `wom7ext/extension/manifest.json:101`.
- The same background handler is registered for internal and external messages: `wom7ext/extension/src/background.ts:297` and `wom7ext/extension/src/background.ts:298`.
- `handleMessage` logs `sender.url` but does not validate sender identity or origin before dispatch: `wom7ext/extension/src/background.ts:76`.
- Externally reachable message types include privileged actions:
  - `RUN_SPEC_ACTION`: `wom7ext/extension/src/background.ts:99`.
  - `SUPABASE_LOGIN`: `wom7ext/extension/src/background.ts:142`.
  - `PROFILE_SYNC_INGEST`: `wom7ext/extension/src/background.ts:181`.
  - `JOB_SYNC_INGEST`: `wom7ext/extension/src/background.ts:215`.
  - `LINKEDIN_CAPTURE_CANONICAL_PROFILE`: `wom7ext/extension/src/background.ts:251`.
  - `LLM_CONFIG_SET`: `wom7ext/extension/src/background.ts:282`.

Impact:

- Any script running on `webomage.com` can ask the installed extension to perform actions with extension privileges.
- A web XSS or compromised page can pivot into LinkedIn automation, profile capture, auth/session changes, logs, and LLM config mutation.

Recommended fix:

- Remove `onMessageExternal` if no first-party web page actively needs it.
- If external messaging is required, create a narrow external handler with an allowlist of safe message types, origin validation, runtime schema validation, tab URL checks, and a per-session nonce/handshake.
- Never expose login, logs, config mutation, or LinkedIn capture through the external channel.

### P2-2: Weekly digest injects unescaped post data into email HTML

Status: confirmed in source.

Evidence:

- Post title is interpolated directly into an HTML anchor: `wom7api/supabase/functions/weekly-digest/index.ts:48`.
- Post summary is interpolated directly into a paragraph: `wom7api/supabase/functions/weekly-digest/index.ts:50`.
- `source_url` is interpolated directly into an `href`: `wom7api/supabase/functions/weekly-digest/index.ts:52`.
- The resulting HTML is sent directly via SMTP: `wom7api/supabase/functions/weekly-digest/index.ts:108`.

Impact:

- If any untrusted feed, generated post, or database row reaches the weekly digest, it can inject email HTML.
- This enables phishing links, tracking markup, visual spoofing, and malformed email rendering.

Recommended fix:

- HTML-escape title, summary, and date fields before interpolation.
- Validate `source_url` as `https:` and optionally allowlist trusted hosts or display it as plain text.
- Use a small email template helper that escapes by default.

### P2-3: `log-event` is public, service-role backed, and ungated

Status: confirmed in source and corroborated by the project ticket.

Evidence:

- `log-event` is configured with `verify_jwt = false`: `wom7api/supabase/config.toml:11`.
- It creates a service-role Supabase client at `wom7api/supabase/functions/log-event/index.ts:4`.
- It accepts arbitrary JSON POST bodies without auth or rate limiting: `wom7api/supabase/functions/log-event/index.ts:11`.
- It inserts caller-controlled event data into `analytics_events`: `wom7api/supabase/functions/log-event/index.ts:44`.
- It dual-writes funnel events to Tinybird: `wom7api/supabase/functions/log-event/index.ts:58`.
- `wom7web/project/tickets/T199.md:108` identifies `log-event` as the one unauthenticated function that holds the service key and has no gate.

Impact:

- Public callers can poison analytics, inflate funnels, and consume DB/Tinybird ingestion.
- Service-role access makes the endpoint more powerful than a least-privilege anonymous insert path.

Recommended fix:

- Decide whether this is intentionally public.
- If public, replace service-role inserts with a least-privilege RPC or table policy, add schema and length limits, origin checks, bot protection, and per-IP/session rate limits.
- If not public, require signed ingestion tokens.

### P2-4: Extension runs a captcha detector on every URL

Status: confirmed in manifest.

Evidence:

- The extension requests broad content coverage for `dist/content/captchaDetector.js` on `<all_urls>`: `wom7ext/extension/manifest.json:90`.
- The content script runs at `document_start`: `wom7ext/extension/manifest.json:97`.
- The extension also exposes specs as web-accessible resources on `<all_urls>`: `wom7ext/extension/manifest.json:46`.

Impact:

- The extension observes every page load where it is enabled, which expands privacy and review risk.
- A bug in the detector or message pipeline has a wider blast radius than the LinkedIn/marketplace automation scope suggests.

Recommended fix:

- Narrow `captchaDetector.js` to the sites where it is actually needed.
- If all-site detection is necessary, document the privacy model, message payload fields, and data retention behavior.
- Add automated tests that prove the detector does not exfiltrate page content.

### P2-5: No repository CI workflow is present; deployment gates are manual

Status: confirmed by workspace scan and local justfile.

Evidence:

- `rg --files --hidden -g ".github/workflows/**"` returned no workflow paths in this workspace.
- `wom7web/justfile:651` explicitly states there is no CI/CD and deploys are manual.
- Manual deploy is protected by `check-guardrails`: `wom7web/justfile:683`.
- The guardrails include gitleaks and admin-test checks: `wom7web/justfile:685` and `wom7web/justfile:687`.

Impact:

- Security gates only run if the deploy operator invokes the expected `just` path.
- Pull requests or branch changes can drift without automated tests, auth checks, secret scans, or function-inventory checks.

Recommended fix:

- Add minimal CI per active repo or a root orchestrator workflow.
- Start with secret scan, typecheck, unit tests, Edge Function auth posture check, and live-vs-local Supabase function inventory.
- Keep manual deploy gates, but do not make them the only enforcement point.

### P3-1: Cloudflare Worker hardening drift

Status: confirmed in source/config; lower severity than the authorization findings.

Evidence:

- `wom7cfworkers` uses direct string comparison for bearer secrets: `wom7cfworkers/src/index.ts:17`.
- `wom7api` manually maintains Worker `Env` bindings because secrets are not generated by wrangler types: `wom7api/worker-env.d.ts:5`.
- `wom7api` and `wom7cfworkers` compatibility dates are `2026-05-06`: `wom7api/wrangler.jsonc:16` and `wom7cfworkers/wrangler.jsonc:10`.
- The Astro app Workers still use `2024-11-18`: `wom7web/apps/web/wrangler.jsonc:3`, `wom7web/apps/cp/wrangler.jsonc:3`, `wom7web/apps/join/wrangler.jsonc:3`, `wom7web/apps/job/wrangler.jsonc:3`, and `wom7web/apps/demo/wrangler.jsonc:3`.

Impact:

- Direct string comparison is a timing side-channel. Practical exploitability is likely low over normal HTTPS, but this is cheap to fix.
- Hand-written Env types drift from real bindings and secrets.
- Old compatibility dates delay runtime changes and make future upgrades more abrupt.

Recommended fix:

- Use timing-safe comparison for bearer secrets.
- Generate Worker binding types with the current Wrangler flow and layer secret-only declarations deliberately.
- Schedule compatibility-date bumps with smoke tests instead of letting app Workers sit on 2024 runtime semantics.

## Fixed Or Not Repeated From Prior Audit

These prior themes were checked but are not current top findings in this pass:

- `admin-todos-api` and `admin-invite-candidate` now use `requireAdminAuth`.
- `client-api` now performs user auth, role checks, and ownership checks before client operations.
- `seed-demo` checks the bearer token against the service-role key before provisioning data.
- `documents` RLS has later hardening migrations that drop the older public read shape.
- The extension spec overlay now uses DOM construction and `textContent` rather than obvious `innerHTML` injection.
- `wom7cfworkers` cron dispatch now logs non-2xx target responses instead of silently treating rejected fetches as success.

## Remediation Order

1. Incident response for historical secrets: rotate, verify, purge/quarantine history.
2. Fix Edge Function auth posture for `daily-news-scheduler`, `weekly-digest`, and `seed-cv`.
3. Flip real third-party webhooks to `verify_jwt = false` while keeping provider HMAC/signature guards.
4. Replace dotted-path asset bypass and add page-level RBAC to sensitive SSR routes.
5. Bring live untracked Supabase functions into source control or remove them.
6. Lock down extension external messaging.
7. Add CI for secret scanning, auth-posture checks, function inventory, typechecks, and focused tests.

## Follow-Up Validation Checklist

- Run an authenticated request using only the public anon/publishable key against the three scheduler/prototype functions and confirm they are rejected after fixes.
- Replay Stripe and platform webhook delivery in staging and confirm provider signatures reach the function code.
- Add SSR route tests for dotted pathnames and sensitive dynamic params.
- Compare live Supabase function list with local `supabase/functions/*` on every deploy.
- Confirm all historical `.env.bak` credentials are rotated in the owning providers.
