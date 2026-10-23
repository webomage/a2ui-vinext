# Webomage (w0m) Feature Backlog & Roadmap

> **Live task queue:** [`wom7web/TASKS.md`](wom7web/TASKS.md) (git-traced) tracks what's NOW / NEXT / backlog / done across all repos. This file is the strategic backlog; TASKS.md is the working queue.

*Generated on 2026-07-08*

This document serves as the master backlog for features that have been discussed, identified in architectural designs, or partially mapped out but not yet fully implemented or specified across the `wom7*` ecosystem.

---

## 1. Described Features Missing OpenSpecs

> **Epic slug:** `missing-specs`
These features are mentioned in our high-level architecture (like `USER-FLOWS.md` or Gamification economics) but lack a formal `openspec` defining exactly how they should function. They require formal specification before implementation can begin.

### 1.1 Telegram Bot Integrations & Notifications
* **Context**: We rely on this for outbound alerts (Upwork poller, CV generator completion, gamification XP) and inbound webhooks.
* **Missing**: A formal spec for message formatting, bot commands, inbound webhook parsing, and delivery resilience (handling Telegram API rate limits).

### 1.2 Crypto / Solana Payouts
* **Context**: The gamification economy ties `w0m` tokens to USD and allows for crypto payouts (Solana, ERC, TRC) for contractors.
* **Missing**: A formal spec detailing the payout rails, smart contract interactions, and the critical KYC/AML/1099-NEC compliance gates required to build this safely.

### 1.3 CV & Deck Generator Pipeline
* **Context**: We have tests for this AI pipeline, which generates tailored PDFs and PPTXs for candidates based on their DB/LinkedIn/Upwork profiles.
* **Missing**: A formal OpenSpec defining the exact prompt chains, Python rendering templates (`reportlab`/`python-pptx`), and error handling logic.

---

## 2. Designed Features Needing Implementation

> **Epic slug:** `features-implementation`
These features have been formally designed and architected in recent sessions, but the actual code (frontend components, edge functions, etc.) has not been written yet.

### 2.1 Client Portal UI (`wom7web`)
* **Status**: Database schema built (`invoices`, `client_milestones`, `revision_requests`).
* **Next Steps**: Build the authenticated frontend portal in `wom7web` where clients can actually log in securely, view and pay their invoices, and approve project milestones.

### 2.2 Agentic Platform Engineering
* **Status**: Architecture mapped (`agentic_platform_engineering_design.md`) for agents to provision their own infrastructure using Terraform and deploy self-hosted LLMs.
* **Next Steps**: Build the orchestration API and Terraform workers that will translate agent intents into actual cloud infrastructure deployments.

### 2.3 Impersonation & Access Roles
* **Status**: RBAC and impersonation flows designed (`impersonation_and_access_design.md`) to allow admins to safely debug issues as other users without permanently violating RLS boundaries.
* **Next Steps**: Implement the secure Edge Function routes for issuing impersonation JWTs and build the Svelte admin UI components for user switching.

### 2.4 Unified ATS Integration
* **Status**: Data schema designed (`ats_integration_analysis.md`) for fetching external ATS vacancies and pushing candidate milestones to external systems.
* **Next Steps**: Develop the Edge Functions that will perform the daily cron sync of vacancies and process outbound webhooks for candidate progression.

---

## 3. Immediate Next Tasks (Up Next)

> **Epic slug:** `immediate-tasks`
1. **[DECISION REQUIRED]**: Select one of the above domains to be our primary focus.
2. If selecting from **Group 1**, we will draft the `openspec` document.
3. If selecting from **Group 2**, we will begin the codebase implementation (writing the Implementation Plan first).

---
*Backlog expanded 2026-07-10 (session: webomage.com incident + hardening).*

## 4. Release Versioning, Healthchecks & Changelog

> **Epic slug:** `release-versioning-healthchecks`
* **Goal**: Every service/API stamped with a single `YYYY.MM.DD-<unixtimestamp>` version, propagated to healthchecks and a CP "Services & Versions" panel; a per-deploy changelog tying agent progress to ROADMAP.
* **Current state**: `deploy_version := date +%Y.%m.%d-%s` in `wom7api/justfile`; injected only as ephemeral `DEPLOY_VERSION` secret (wrangler/supabase) for *some* targets. CF worker `/health` returns hardcoded `version: '1.0.0'`. Deploys leave the tree dirty via `apps/web/scripts/snapshot-*.mjs` rewriting `apps/web/src/config/*.json`.
* **Plan (OpenSpec change `release-versioning`)**:
  1. Single source of truth: compute version once per `just deploy`/`deploy-all`, write to a generated (git-ignored) `version.json` per service + inject as build env; never leave committed files dirty (git-ignore snapshots or commit them deliberately in a dedicated step).
  2. Healthchecks read the injected version (kill the hardcoded `1.0.0`); uniform `{service, version, commit, deployed_at}` shape.
  3. CP "Services & Versions" admin page (see §9 infra) polls each `/health` + a `deploy_log` Supabase table.
  4. Append-only `deploy_log` table + a `CHANGELOG` generator that records each deploy (version, repo, commit range, actor/agent) and links back to ROADMAP items.
* **Type**: Spec → Build. **Effort**: M.

## 5. Cross-Repo Tech-Debt Knowledgebase

> **Epic slug:** `cross-repo-tech-debt`
* **Goal**: Research/observe/record tech debt across all repos in a queryable KB.
* **Engine options**: SonarQube/SonarCloud (breadth, SQALE debt rating), **CodeScene** (behavioral hotspots — prioritizes debt by change-frequency × complexity), Code Climate/Codacy/DeepSource. Cheap self-hosted path: aggregate outputs we ALREADY run (semgrep, ruff, tsc/deno, osv, gitleaks) + TODO/FIXME/HACK census + dep-staleness into a Supabase `tech_debt` table surfaced in CP.
* **Recommendation**: start with the self-hosted aggregator (reuses existing tooling + ties into §4/§9), evaluate CodeScene for prioritization if we want behavioral analysis.
* **Type**: Research → Spec → Build. **Effort**: M–L.

## 6. SDLC Skill Set for w0m Guild Crew

> **Epic slug:** `sdlc-skills-crew`
* **Goal**: A composable skill pack for the dev lifecycle mapped to agent roles (ai-agent / ai-architect / ai-interviewer / admin).
* **Reuse**: we already have `openspec-*` (spec workflow), `test-driven-development`, `playwright-best-practices`, plus Anthropic built-ins `code-review`, `security-review`, `verify`, `skill-creator`. Compose into a pipeline: explore → new-change → impl-plan → TDD → code-review → security-review → verify → deploy(§4) → archive.
* **External**: evaluate skills.sh registry + skill-search for reusable SDLC skills to embed (needs web research pass).
* **Type**: Research → Build (author via skill-creator). **Effort**: M.

## 7. wom7swarm Revalidation — DECOMMISSIONED (2026-07-11)

> **Epic slug:** `swarm-revalidation`
* **Resolved**: retired. Only caller was the Telegram webhook (`SWARM_URL` never set); GCP project `webomage-1337` has billing off + closed billing accounts + disabled Run/Artifact APIs + deleted gcloud account → nothing runs, **no cost**, its 16 CVEs are moot.
* **Done**: repo moved out of the active workspace; dead `SWARM_URL` branch removed from `telegram.ts`; recorded in [`DECOMMISSIONED.md`](DECOMMISSIONED.md); CVE task closed. ⚠️ **This line used to warn
that the log was unversioned at the workspace root and that the `wom7web/` path "has never
existed" — both were true until 2026-08-31 and neither is now.** D15 is closed: the log moved here
and gained a reader (`just decommission-check`), which asserts `SWARM_URL` has stayed gone rather
than trusting this sentence. The one remaining mention, in `telegram.ts`, is the comment that
explains the decommission and is declared as an allowed exception with that reason.
* **Leftover follow-up**: the Telegram bot now has no backend — repoint it to the `w0m-consultant` edge function if wanted (`TODO(telegram)` in `telegram.ts`).

## 8. wom7mlx Refresh + Fast Rust Gemma Launcher (R&D)

> **Epic slug:** `wom7mlx-fast-launcher`
* **Goal**: Update all vendored packages in `wom7mlx/wom7mlx`; build a very fast Rust launcher for Gemma optimized for the MLX raw API.
* **Approach**: MLX-from-Rust = `mlx-c` (C API) + `mlx-rs` bindings; candle is the pure-Rust alternative. This is a benchmark/spike, not a committed build.
* **Recommendation**: time-boxed spike — refresh deps, prototype Gemma inference via mlx-rs vs candle on Apple Silicon, measure cold-start + tok/s, then decide.
* **Type**: Spike → (maybe) Build. **Effort**: L.

## 9. CP People Visibility — Hierarchy Scoping (FEATURE, not a leak)

> **Epic slug:** `cp-people-hierarchy`
* **Severity correction (2026-07-10)**: NOT a live data exposure. Verified against the live DB — `public.profiles` SELECT RLS is "Admins view all" + "Users view their own" (no permissive `USING(true)`), and `PeopleManager` uses the member's own session (RLS applies), not the service role. The `/team/people` screenshot was an **admin** view (correct behavior). A regular member sees only their own profile today.
* **Requested model (feature)**: a member sees (a) teammates on the same attached project(s), (b) their PM and up the chain to the boss; with escalation/direct-contact that CCs intermediate/mentioned persons.
* **Needs (net-new primitives — none exist yet)**: a project↔user membership table AND a reporting-line model (`manager_id`/`reports_to`), then RLS/query scoping + a contact/escalation flow. Overlaps RBAC/impersonation (§2.3) and cp-guild-operations OpenSpec.
* **Type**: Spec → Build (needs org-model design decision). **Effort**: M–L. **Priority**: normal (feature, not security).

## 10. Client Conversion Funnel, Blueprint Proposals & Unified Contracts

> **Epic slug:** `client-conversion-contracts`

> 🔀 **2026-09-29: this section's OPEN client-facing tickets moved to §34 "Client Beta"** (owner: organize as the Client Beta epic):
> T101, T5, T3, T204, T272, T284, T288, T285, T217, T263, T279, T280, T338, T287, T292. Done tickets and [[T6]] stay here.
* **Decision (2026-07-11)**: a successful public-AI-consultant conversation must **end with a guided, successful client registration** — the visitor leaves with a CP account and their request visible, not just a lead row.
* **Scope** (OpenSpec change [`2026-07-11-client-conversion-and-contracts`](wom7web/openspec/changes/2026-07-11-client-conversion-and-contracts/)):
  1. **Client self-registration + shared CP access**: chat-guided signup after intake submit (magic-link, idempotent, `client` role auto-provisioned, `leads.converted_user_id`); clients and team share ONE CP app with role-scoped nav + a client portal home (requests, proposals, contracts, project/adventure progress). Extends the invite-only path from `2026-07-02-client-engagement-and-lead-pipeline`.
  2. **Proposal drafts with assigned blueprint**: `lead_proposals` + `blueprint_id` (site blueprints catalog) + `adventure_id` (hierarchy-v2) — proposals become concrete reviewable plans; consultant conversations can seed machine-drafted proposals; acceptance hands off to contract AND delivery container.
  3. **Unified contracts — internal + external platforms**: one registry over `source: direct` (self-owned, in-system lifecycle) and platform contracts (Upwork today; `platform`/`platform_ref` columns make Toptal/Contra/etc. representable) — external terms read-only mirrors, internal annotations editable, client sees both under own-linkage RBAC.
  4. **Advanced agent prompts/workflows**: staged consultant funnel (`discover → qualify → intake → register`), versioned per-stage prompt library (`agent_prompts`/`agent_workflows`, no-deploy editing, versions recorded per conversation), stage-transition events → conversion measured per prompt version (feeds the AI-agents eval harness, gap #3).
* **Builds on**: `client-engagement`/`lead-pipeline` (2026-07-02), `ai-intake-service-requests` (2026-07-05), gamification hierarchy-v2, AI-agents gaps #1–2 (fallbacks + streaming, shipped 2026-07-11).
* **Type**: Spec (written) → Build. **Effort**: L (schema S, edge fns M, CP surfaces M, widget S).

## 11. AI Agent Engine — Engine-Agnostic Agents (status 2026-07-12)

> **Epic slug:** `ai-agent-engine`
* **Source of truth**: [`wom7web/docs/backend/AI-AGENTS-RESEARCH.md`](wom7web/docs/backend/AI-AGENTS-RESEARCH.md) §6. Four foundational gaps are now **all shipped & verified live**:
  1. ✅ **Registry hardening** — capability metadata + output normalization (`stripReasoning`) + per-alias fallback chains (`fallback_model_id`). Verified live incl. a controlled fallback test.
  2. ✅ **Streaming** — SSE end-to-end (CF worker passthrough → `routeChatStream` → ChatApp reader loop in web+cp). Consultant paints in ~2s instead of 5–7s.
  3. ✅ **Eval harness** — `wom7api/scripts/ai-eval.ts`; data-picked consultant → `mistral-small-3.1-24b` (live).
  4. ✅ **Tool/function calling** — `submit_service_request → ai_chat lead`, deterministic execution, `normalizeToolCalls` for the 3 CF per-model shapes. Verified live (real lead created).
* ✅ **Streaming ↔ tool-calling integration (was the 🔴 follow-up)** — `routeChatStream` now forwards tools and, on a tool-call SSE frame, re-issues one non-streaming call for authoritative args (CF streams tool args in unreliable fragments); `processChatQueryStream` executes + emits the confirmation. api `b985b3f`, verified live 2026-07-12 (isolated-session streaming intake 4/4, full email preserved). (TASKS T1.)
* **Remaining cross-cutting (§4.1, unstarted)**: durable/summarized conversation memory; guardrails via `llama-guard-3-8b`; cost + rate accounting from CF GraphQL (chat logs 0 tokens today). Then per-agent feature depth (§4.2–4.5) + Telegram bridge (also the §7 leftover: repoint the bot to `w0m-consultant`).
* **Funnel linkage**: gap #4's `submit_service_request` is the **intake** stage of the client-conversion funnel (§10). The **registration** stage (`client-register`, lead → CP client) is specced in `2026-07-11-client-conversion-and-contracts` but not built — the tool's confirmation is where the guided-registration offer belongs.

## 12. WebMCP — Role-Gated Agent Tools Across All Apps (P1, status 2026-07-12)

> **Epic slug:** `webmcp-agent-tools`
* **What**: adopt **WebMCP** (W3C Draft Community Group Report, 2026-02-10; `navigator.modelContext`; origin trial Chrome 149) so every w0m app declares its features as structured, callable tools an in-browser AI agent (Claude in Chrome, Gemini, Copilot) can discover and invoke — instead of screenshot-and-click. WebMCP tools **inherit the user's authenticated browser session**, which makes **RBAC the central design problem**.
* **Scope** (OpenSpec change [`2026-07-12-webmcp-agent-tools`](wom7web/openspec/changes/2026-07-12-webmcp-agent-tools/)):
  1. **Shared `@webomage/webmcp`** — `navigator.modelContext` adapter with feature-detection + origin-trial token; **progressive enhancement** (no-op, zero regression where unsupported).
  2. **One tool manifest** (`name`/`params`/`requiredRole`/`endpoint`/`sideEffect`) shared with the server-side LLM tool-calling in `chat-core`, so the browser and server surfaces can't drift (engine-agnostic, AI-AGENTS §1).
  3. **Role-gated registration** across **web / cp / join / job** — only tools the session's role (public/recruit/member/admin/`client`) permits are registered/discoverable; deregister on sign-out/role change.
  4. **Server stays authoritative (defense in depth)** — each tool is a thin client over an existing RBAC-enforcing edge fn (w0m-consultant, guild-api, lead-api, client-api); client gating is UX only; args re-validated server-side.
  5. **Audit + safety** — every invocation logged (`user/role/tool/args_hash`); write tools require confirmation + per-role rate limits.
* **Initial catalog**: web → `search_knowledge`, `submit_service_request`, `list_services`; cp → member `claim_quest`/`submit_quest`/`list_bounties`, admin `assign_questmaster`/`approve_payout`/`query_metrics`, client `list_my_requests`/`view_proposal`/`accept_proposal` (gated on the `client` role, T2); join/job → `apply`/`check_application_status`.
* **Relates to**: #46 CF-hosted MCP server (server-side sibling), the tool-calling engine (T1 done), T2 (`client` role for client-scoped cp tools).
* **Type**: Spec (written) → Build. **Tracked**: TASKS `T21`. **Effort**: L (shared pkg S, per-app registration M, audit/rate-limit S, verify in Chrome 149 origin trial S).

## 13. Platform Health, Tooling & Knowledge Infrastructure (P1, added 2026-07-12)

> **Epic slug (parent):** `platform-health-tooling`
Standing operational capabilities — not one-off features.

> 🔴 **RESYNCED 2026-07-27 — this section had lost sync with the queue.** It said *"Tracked in
> `TASKS.md` T22–T26"* (5 tickets). **Measured: 33 tickets declare `ROADMAP §13` as their epic.**
> The section had not been updated since 2026-07-12 while the strand kept growing, so the roadmap
> was describing a five-ticket plan against a thirty-three-ticket reality — and **two of its
> recommendations below are now contradicted by measurement** (13.1) **or superseded by an owner
> decision** (13.4). ⇒ **Re-derive the ticket set with
> `just tasks list` rather than reading a range out of this heading.**

**Done:** T23 · T119 · T130 · T146 · **T149** (the consolidation epic).
**In progress:** T22 · T77 · T117 · T127 · T135 · T145 · T150.
**Queued:** T24 · T25 · T26 · T27 · T48 · T51 · T109 · T128 · T129 · T132 · T140 · T141 · T142 ·
T143 · T144 · T147 · T148 · T151 · T152 · T153 · **T154 (P0 security)**.

> **⬆️ PROMOTED TO TOP PRIORITY 2026-07-16 (owner): 13.2 (T23) + 13.4 (T25).** The tooling inventory
> (2026-07-16) established that **13.2 is the "main w0m skill/hook"** unifying DSL/lexicon/Gauge/
> truth-vs-code/knowledge/tasks — most substrate already exists (SPEC-AUTHORING-STANDARD, the
> `project/README.md` delivery chain, `quality_gate_synergy.mmd`, 193 Gauge specs, the lexicon at
> `docs/gamification/09-naming-lexicon.md`); the missing piece is *connective automation* (spec↔code
> drift gate + lexicon-lint). 13.4 (knowledge-graph) feeds it. Both moved to TASKS **NOW**.

* **13.1 Standing health, status & guardrails (T22)** · **Epic slug:** `health-status-guardrails` — evolve the §4 release-versioning `/health` + CP "Services & Versions" panel into *continuous* monitoring (uptime, AI hot-path liveness, DB reachability, egress/billing-gate) with a status surface + alerting. Add **functional guardrails** (agent I/O classifier — `llama-guard-3-8b`, = AI-AGENTS §4.1 / TASKS T8) and make the **security guardrails permanent**: the pre-commit stack (gitleaks/osv/semgrep/conventional/type-gate, see [[wom-precommit-hooks-standard]]) exists locally — promote it to server-side enforcement — but NOTE (confirmed 2026-07-12): there is currently NO CI/CD in any repo; hooks run locally only and deploy is manual `just`. ~~So this is a real build decision: (A) add GitHub Actions CI … — recommended, repos are on GitHub; or (B) keep hooks+manual `just`.~~ 🔴 **SETTLED 2026-07-27, and option (A) is not available.** Measured: **GitHub Actions has never successfully run on this account — 339 runs across 4 repos, 100% `startup_failure` at 0s**, which is account-level (likely billing) rather than a per-repo workflow bug. The `CI` workflow the API reports as *active* is a phantom read off `main`, 692 commits stale; `beta` has no `.github` at all, and CI was deliberately disabled in `604779db` (2026-05-08) in favour of local `just` gates. ⇒ **Option (B) by owner decision** (*"if it's fast enough now and working let's keep it simple git hooks"*, [[T150]]). The hook layer is now genuinely enforced: `just hooks-check` verifies at pre-push that **every declared gate phase is actually wired** (14/14) and that exactly one sanctioned forge call site exists. **OWNER ACTION: check the account's Actions billing/spending limit** — recorded, but no longer blocking anything.
* **13.2 SDLC skill pipeline + tech-debt tracing in hooks (T23) — THE UNIFIER, now top priority** · **Epic slug:** `sdlc-pipeline-hooks` — compose the skills+tools we already have into a standing lifecycle (explore → openspec → TDD → code-review → security-review → verify → deploy(§4) → archive) and **wire the hooks to emit tech-debt findings into a traced store** — the self-hosted aggregator from §5 (semgrep/osv/deno/tsc/gitleaks + TODO/FIXME/HACK census → `tech_debt` table surfaced in CP). Goal: use skills+tools together by default, and debt is measured continuously, not audited occasionally. Supersedes/absorbs §5 + §6 into an operational loop. **The concrete build (2026-07-16 inventory): the substrate exists — unify it via (1) a spec↔code drift gate (`openspec-verify-change` promoted from manual → pre-push/`just deploy`), (2) lexicon-lint against `docs/gamification/09-naming-lexicon.md` + feed lexicon to RAG, (3) the tech-debt store.** Ties §15/T33 (verifiable specs) + §13.2/T27 (SDLC-as-quests).
* **13.3 Skills expansion (T24)** · **Epic slug:** `skills-expansion` — import [`kepano/obsidian-skills`](https://github.com/kepano/obsidian-skills) into `wom7skills`; survey [skills.sh](https://skills.sh) top skills and classify each **import/connect** vs **master & craft ourselves**; maintain a skills catalog.
* **13.4 Knowledge-graph engine research (T25) — now top priority, feeds 13.2** · **Epic slug:** `knowledge-graph-engine` — evaluate [`Understand-Anything`](https://github.com/Egonex-AI/Understand-Anything) vs [`graphify`](https://github.com/Graphify-Labs/graphify) vs extending our Supabase **pgvector** RAG, for codebase understanding + tech-debt (feeds 13.2). Stack-fit caveat: the two OSS tools are file/Neo4j-based, not Supabase/pgvector/CF-native — decide adopt-as-dev-tool vs build-on-stack. ~~**Inventory (2026-07-16)** … Recommendation deliverable.~~ ✅ **DELIVERED and DECIDED.** The recommendation exists (`docs/KNOWLEDGE-GRAPH-RECOMMENDATION.md`) and the owner decided 2026-07-27: **graphify is PRIMARY** across all repos with a united global graph → [[T151]]. 🔴 **But the measured starting position is worse than the inventory implies:** graphify is installed in **1 of 8 repos**, its graph is **250 commits stale**, and the global (multi-repo) graph is **EMPTY** — the cross-repo union that is the tool's whole advantage has never been built. Meanwhile codegraph is indexed in **6 repos** and re-syncs every commit. ⚠️ **The succession must be ordered**: the global `~/.claude/CLAUDE.md` tells every agent to reach for codegraph first, so flipping that instruction while graphify is stale would silently degrade every agent session. Parity first, then the instruction ([[T151]] AC9).
* **13.5 Package discovery via MCP (T26)** · **Epic slug:** `package-discovery-mcp` — connect awesome-repositories.com's read-only MCP server (`https://awesome-repositories.com/api/mcp`, HTTP, OAuth 2.1 auto-discovery; `search_repositories`/`search_metadata_tags`/`get_repository`/`list_curated_searches`/`list_repository_docs`) as a standing tool for finding vetted OSS packages during design/build.

> 🔬 **SPLIT 2026-08-25 — this section held 114 tickets, 41% of the queue, in one bucket.** A
> roll-up where two in five items share a label is not rolling anything up. 13.1-13.5 above are each
> anchored to a single original ticket (T22-T26) and are too narrow to absorb what the strand became,
> so **13.6-13.11 below name what the 114 actually were**, derived from their own titles and tags
> rather than invented. Largest bucket after the split: **29 (10%)**.
> ⚠️ **Seven of the 114 were not a §13 problem at all — they were MIS-FILED.** Six security tickets
> (T159 · T175 · T196 · T201 · T233 · T244) and T210 sat under *Platform Health & Tooling* while
> being authorization and credential work; they now sit under **§19**. T252/T275 moved to **§26**,
> and T107/T108/T109 to **13.4**, which already existed for exactly them.
> 🔴 **This section has now drifted twice.** It was resynced 2026-07-27 at **33 tickets** with the
> warning above; it reached **141** before anyone looked again. ⇒ The count is the thing to watch,
> not the prose — `just tasks overview` prints it.

* **13.6 The delivery record — ticket, board and tracker must agree** · **Epic slug:** `delivery-record-sync` — the ticket file, the
  `TASKS.md` row and the GitHub projection are three encodings of one fact, and they disagree.
  Queue ranking, sync indexing, STATE.md retention and spec backfill all live here.
* **13.7 Gate integrity — a gate that cannot fail is not a gate** · **Epic slug:** `gate-integrity` — vacuous greens, gates scoped
  wider or narrower than the change, suites invisible to the runner, and the type/emoji/AC gates
  that check the estate's own gate code.
* **13.8 Agent substrate — many agents and sandboxes, one estate** · **Epic slug:** `agent-substrate-sandboxes` — Claude, Gemini and opencode
  reading the same rules; Tart VMs and DevPod; the code graph; IDE surfaces; MCP transport; skills
  packaged as portable plugins.
* **13.9 Governed projects — what it means for a project to be in the estate** · **Epic slug:** `governed-projects` — the client-import
  path, the half-managed tier, `sdlc.json` conformance, and the workspace-vs-single-repo shapes.
* **13.10 Toolchain currency — dependencies, runtimes and type safety** · **Epic slug:** `toolchain-currency` — dependency floors and
  ceilings, deployed runtime alignment, the Rust and MLX toolchains, and the per-stack registry.
* **13.11 Platform operations — backups, deploys, migrations and cloud services** · **Epic slug:** `platform-operations` — restorable
  backups, the migration chain, deploy warnings nobody reads, and which Cloudflare services we
  actually use.
* **13.6 Toolset consolidation ([[T149]]) — ✅ DONE 2026-07-27.** The epic that made the
  above one toolset rather than several adjacent ones. Shipped: `just toolset-status` (composed
  status), `just hooks-check` (declared gates must be wired; one sanctioned forge call), `just
  typecheck-ratchet` (ungated apps may not degrade), and a scope-declaring `w0m skill check`.
  Its organising finding — *a gate reports zero because it only looks where it already knows to
  look* — now has **12 recorded instances, 5 of them found inside the tools written to catch it.**
* **13.7 Ticket mirror ([[T150]])** — the GitHub mirror is indexed: a no-op sync went from ~435
  round trips / ~10 min to **1 fetch, 0 mutating calls, 3.6s**, and it now actually mirrors (titles,
  bodies and closed-state were silently never updated). Placement settled: **stays in the git hook**.
* **13.8 Agent runtimes ([[T152]] P2, [[T153]])** — OpenCode as a second runtime, and ZeroClaw as a
  managed local one with omlx. ⚠️ Both inherit one measured constraint: **Gemma-4-via-MLX cannot emit
  structured tool calls and FABRICATES results**, which is fatal for agentic use until shimmed.
* **13.9 🔴 Exposed MCP interfaces ([[T154]], P0 security)** — an exposed HTTP service leaks data; an
  exposed MCP server leaks **capability**. Found live 2026-07-27: the Obsidian vault MCP servers were
  bound to `0.0.0.0` with **unauthenticated tool access including `edit`**. Network exposure closed
  and verified same day; the inventory + standing monitoring remain. **Should precede §12/[[T21]]'s
  `/api/mcp` work** — adding MCP surfaces before exposure monitoring exists repeats the pattern.
* **Type**: mostly standing capabilities + 1 research spike. **Effort**: 13.1 M · 13.2 M–L · 13.3 S
  · 13.4 spike · 13.5 S · 13.6 ✅ · 13.7 M · 13.8 L · 13.9 S–M.

## 14. Agency Delivery & Portal Access Model (P1, added 2026-07-12)

> **Epic slug:** `agency-delivery-portal`
OpenSpec change [`2026-07-12-agency-delivery-and-access-model`](wom7web/openspec/changes/2026-07-12-agency-delivery-and-access-model/). Defines how w0m operates as an agency once a deal is won. TASKS T29 (delivery) + T30 (access).
* **`project-delivery`**: on blueprint acceptance, provision **private repos under the Webomage agency GitHub org** + a PM-owned project board with epics/tasks seeded from the blueprint; a blueprint may span **multiple repos**; board mirrors contract/milestones; delivery tasks are quest-operable (T27) and WebMCP/MCP-operable. The delivery stage after the client-conversion funnel (§10).
* **`portal-access-control`**: identity as a defense-in-depth barrier on top of RBAC — **member CP admits only `@webomage.com` logins**; client/job/join admit **whitelisted addresses** (client scoped to own engagement; applicants self-added on join); admin = `@webomage.com` + admin role; deny-by-default, audited.
* **🔴 Lockout trap (must sequence)**: members log in with personal emails today (`casualuser@gmail.com`, …). The member-CP domain gate ships **behind a flag** and refuses to enable until every active member has a verified `@webomage.com` login → depends on real mailboxes (T28) + re-onboarding. Gate on the **auth login email**, not `profiles.work_email`. Break-glass admin required.
* **Owner/infra prerequisites**: create the **`webomage` GitHub org** (+ Teams); stand up `@webomage.com` mailboxes (T28); add the `client` role (§10 T2). All gate the build.
* **Type**: Spec (written) → Build. **Effort**: L (GitHub App + provisioning M, access layer M, board sync M).

## 15. Verifiable Spec-Authoring Standard (P1, added 2026-07-12)

> **Epic slug:** `spec-authoring-standard`
Every OpenSpec requirement must carry a **verification contract**, not just a `SHALL`: wider feature description, binary **acceptance criteria**, **skill-mapped verification** (`test-driven-development`/`playwright-best-practices`/`verify`/`code-review`/`security-review`/`openspec-verify-change`/`schema`/`supabase`), a **w0m ecosystem checklist** (RLS/RBAC, edge-fn `agent-io` contract, migrations+`schema_migrations`, AI registry+fallback, `/health`, `just check-guardrails` gate, egress reality), a **security checklist** (server-side authz, no inline secrets, injection, abuse controls, guardrails, portal identity), and a change-level **Definition of Done** gating `openspec-archive-change`. Standard: [`wom7web/openspec/SPEC-AUTHORING-STANDARD.md`](wom7web/openspec/SPEC-AUTHORING-STANDARD.md); TASKS T33. It's the spec layer of SDLC-as-quests (§13.2/T27): acceptance criteria = test targets, skill map = the quest's tools, checklists = the gates.

## 16. Multi-Hat — Multi-Role & Active Context (incl. Impersonation) (P1, added 2026-07-12)

> **Epic slug:** `multi-hat-active-context`
OpenSpec change [`2026-07-12-multi-hat`](wom7web/openspec/changes/2026-07-12-multi-hat/). TASKS T35.
* **Decision (user)**: a user MAY hold multiple roles but **acts under one active role at a time**, dropping the others' privileges (e.g. a CTO/`admin` who is also a `client` runs their own projects as `client` with internal powers suspended).
* **Reality today**: `user_roles` already allows multi-role (`UNIQUE(user_id,role)`), but `apps/cp/src/middleware.ts:53` collapses to a single role by precedence (`admin>member>first`) — so `client` always loses to internal roles and the client experience is unreachable on a multi-role account. Only "be someone else" primitive is admin impersonation (sudo token).
* **Change**: role resolution → explicit **active role** (server-verified ∈ the user's set; default = highest-precedence); a **role/workspace switcher** that *drops* other privileges (active `client` = zero internal reach, RLS scoped to own `client_users`); **unify with admin impersonation** as one effective `(user,role)` context (impersonation = act-as-another-user; switch = act-as-own-other-role); every switch audited; active role still bound by §14 portal policy. No `user_roles` schema change; active role = signed session claim (reuse the sudo/`CRYPTO_KEY` pattern).
* **Security invariant**: never union privileges (drop, don't add); switch can't assume another user or an unheld role; this is what makes one identity holding internal+client acceptable under §14's identity-as-barrier.
* **Reconciles**: §14 portal access, T2/T3 client portal, the impersonation model. **Type**: Spec (written, to the authoring standard) → Build. **Effort**: M (middleware/resolver + signed claim + switch endpoint + RLS + switcher UI).
* ✅ **Status**: SHIPPED & Verified (2026-07-13). Active-role enforced via middleware, RoleSwitcher UI live.

## 17. AI Provider-Adapter Seam & Lib Hygiene (P1, added 2026-07-12)

> **Epic slug:** `ai-provider-adapter-seam`
Decision from the "libs for harness/routing?" review. **Router + `ai_models` registry stay hand-rolled — the moat** (AI-AGENTS §1); libraries plug in only at the `provider → adapter` seam *behind* `routeChat`/`routeEmbed`, never in front. **Provider policy:** `cloudflare` (raw-fetch, primary) + `google` (**resumable on free tier**) only — **no third-party inference gateways/proxies** (we don't route inference through anyone else's aggregator) and **no new external provider keys** planned. The Vercel AI SDK (`ai`/`@ai-sdk/google`, **pinned**) is the google-only *client* adapter (direct to Google with our key — pinning prevents the unpinned-bump drift that once 404'd chat). Adopt a **local eval lib (promptfoo/evalite)** for the eval harness (not a proxy). Guardrails = `llama-guard-3-8b` (T8, CF-native); durable memory = CF Agents SDK (T7). TASKS T36. Avoid LangChain/LangGraph (Deno-edge misfit + churn; would fight the CF proxy quirks already solved).

## 18. Pending Past Tasks Archive

> **Epic slug:** `past-tasks-archive`
These are pending tasks recovered from past Antigravity sessions that need to be reviewed, prioritized, and merged into the active backlog or archived.
* [Pending Past Tasks](docs/archive/pending_past_tasks.md)
* [Past Plans and Tasks](docs/archive/past_plans_and_tasks.md)

---

## 19. Security, RBAC & Platform Hardening (P0, added 2026-07-14)

> **Epic slug:** `security-rbac-hardening`
* **Goal**: Rectify critical vulnerabilities and structural gaps identified in the 2026-07-14 audit.
* **Scope**:
  1. **Active Hat RLS Enforcement (R1)**: Implement Supabase custom access-token hook to project `user_active_role` into JWT claims, making RLS policies acting-role aware (`auth.acting_role()`). [✅ Live in DB].
  2. **Role Storage Unification (R2)**: Unify role storage into `public.user_roles` and sync to `app_metadata.role` via triggers to prevent privilege drift. [✅ Live in DB].
  3. **Supabase Postgres Password Rotation (T32)**: Rotate the superuser database password in Supabase and run `git filter-repo` to scrub history. [✅ Rotated live 2026-07-14; history purge rides with T17].
  4. **Tailwind v4 Purge Fix (T38)**: Prevent utility class purges from shared `@webomage/ui` components by adding `@source` directories. [✅ Done].
  5. **Burn Down 29 Deno Compiler Errors (T40)**: Fix type errors across edge functions to ensure type safety. [✅ Done].
  6. **The authorization core, batched ([[T200]], added 2026-08-11)**: the 2026-08-10/11 surveys measured
     all **115 tables** and found **15 live authorization defects** plus **four ungoverned layers**.
     The work is batched because the four tickets share the same tables, the same missing
     `is_capable()` reader, and the same owner-applied migration path — four separate migrations
     touching overlapping policies on the same tables is how a fix gets silently undone.
     Members: [[T198]] (defects) · [[T102]] (project-scoped grants — the reader) · [[T117]] (the
     model) · [[T199]] (the gates). Sequencing and the shared blockers live in T200.
     🔑 **Authorization here is decided in five places** — a table `GRANT`, an RLS policy, a
     `SECURITY DEFINER` function, an edge function's own code, and an app route — **and the office
     model addresses two.** Current state: `docs/backend/RBAC-MAP.md` + `docs/backend/SCHEMA-MAP.md`
     (generated from `project/authz-probe/`, so they are current rather than dated).
  7. **Parent Batch Closeout & Governance Modernization (T200 / T199, updated 2026-09-17)**:
      Parent batch [[T200]] and child governance batch [[T199]] are **100% DONE & ARCHIVED** (core children
      [[T198]], [[T102]], [[T117]], [[T202]], and [[T199]] 12/12 ACs fully closed; Stage 0 & Stage 1 exits met).
      Governance architecture modernized:
      - **Telemetrics:** `log-event` retired; Microsoft Clarity (`@microsoft/clarity` v1.0.2) + Tinybird SDK handle client/funnel telemetry.
      - **Connectors:** Legacy webhooks (`stripe-webhook`, `platform-webhook-gateway`) deprecated in favor of per-profile connections (`public.social_integrations`, [[T210]]) and system services (`svc_*` roles, [[T206]]).
      - **Handshake Protocol:** Brittle local file deny-lists superseded by **Agentic Handshakes (a2h, a2a, h2a)** followed by clean [[T117]] 4-axis RBAC role resolution.
      - **Bi-Directional TypeScript Cross-Check Mesh:** Non-repo-scoped infrastructure checks rewritten in TypeScript: Cloudflare cron (`wom7cfworkers`) checks Supabase, and Supabase edge functions (`wom7api`) check Cloudflare, exposing live `/health/governance` telemetry to the Client Portal (`cp.webomage.com` / `cp.w0m.xyz`).
  8. **Why this section, and not a new one**: until 2026-08-11 this section held only two tickets
      (T138/T139, both schema-integrity), while the RBAC work was spread across §10, §13, §13.2, §14
      and §16 — so no ranking could see it as one thing. The section the work belonged in was nearly
      empty. It did not need a new epic; it needed this one to be used.
  9. **Active Execution Plan & Remeasurement (47/55 Done, updated 2026-09-25)**:
      Following T200/T199 and the 2026-09-25 credential rotation, **47 of 55 tickets in the epic are DONE (85%)**.
      
      🟢 **Critical Vulnerability Remediated (2026-09-25):**
      - **[[T18]] (Leaked `sb_secret_` rotated & resolved — 100% DONE, 3/3 ACs):** The legacy service role key that shipped in `wom7ext` (created 2025-11-29) was rotated in Supabase Cloud Dashboard. Old key verified dead (HTTP 401). New key installed into Infisical (`beta` and `dev` environments, HTTP 200) and propagated to consumers. Edge functions tested and verified live (`jobs-list` returning HTTP 200).
      - **T17 (".env.bak holds only dead values" is FALSE):** 10 of 19 keys in `.env.bak` still match live Infisical vault values (`ADMIN_PASSWORD`, `HATCHET_CLIENT_TOKEN`, `MEMBER_PASSWORD`, `PUBLIC_HONEYCOMB_API_KEY`). `ADMIN_EMAIL` (`casualuser`) has a live password hash. Live values must be rotated before executing the `git filter-repo` history scrub; scrubbing first merely hides active secrets.
      
      **Stage-by-Stage Measured Status (8 remaining open tickets):**
      - **Stage 0 — Confirmed-Live Exposure [100% DONE, 3/3 tickets, 16/16 ACs, Exits Met 2026-09-19]:**
        - [[T196]] (done, 5/5): Telegram bot token & Hatchet token rotated; quarantine removed; `just host-surface` secrets gate delivered.
        - [[T201]] (done, 6/6): Cleartext `DEBUG_BYPASS_KEY` removed; frontend & backend cut over to Cloudflare Turnstile; `HCAPTCHA_SECRET` purged.
        - [[T329]] (done, 5/5): Atomic client actor binding in `authz_probe_suite.py` prevents cross-tenant pairing; 18/18 live and 20/20 offline red probes passing.
      - **Stage 1 — RLS & Authz Enforcement Residue [100% DONE, 4/4 tickets, 21/21 ACs, Exits Met 2026-09-20]:**
        - [[T381]] (done, 4/4): Admin authorization enforced in `lead-api`; dead `isAdmin` pruned from `guild-api`; 16 red probes.
        - [[T382]] (done, 5/5): `withServiceRole` least-privilege transaction switcher adopted across edge functions with companion migration.
        - [[T327]] (done, 7/7): CP staff business pages migrated to `adminClient()`/`userClient()`; ambiguous re-export in `apps/cp/src/lib/supabase.ts` removed; baseline ratcheted 17 → 13 in `project/authz-admin-client-baseline.json` via enforcing `just authz-admin-client --enforce`; `just authz-probe` 18/18 green.
        - [[T208]] (done, 5/5): Phantom `user_profiles` relation eliminated from `handlers.ts` and `linkedin-data-erasure.ts`; native `auth.identities` adopted; `just callsite-drift --enforce` reports GHOST: 0 across all 612 call sites.
      - **Stage 2 — Identity & MFA Surface [IN PROGRESS, 1/2 tickets, 50%, 7/14 ACs]:**
        - [[T53]] (done, 7/7): Delivered OAuth identities panel, TOTP MFA enrollment and `/mfa/challenge` route, and SHA-256 hashed `personal_access_tokens` schema with owner RLS.
        - [[T100]] (queued, 0/7, P0): Live counts: 0 enrolled factors (ticket's "10 factors" is the `mfa_max_enrolled_factors` limit); identities: email:21, google:4, github:0, linkedin:0. 🔴 AC7 blocked: `security_manual_linking_enabled = false`. Middleware catch (`middleware.ts:391`) fails open for admin on non-admin domain. Plan: enable manual linking, fix fail-open catch, split non-admin MFA into separate ticket.
      - **Stage 3 — Posture Composition & Remaining Hygiene [IN PROGRESS, 2/5 tickets, 48%, 14/29 ACs]:**
        - [[T233]] (done, 8/8): Unified `just audit` host and platform families (macOS host controls, loopback postgres assertion, startup surface ratchet, TCC fail-closed check, 19/19 red probes, daily launchd schedule).
        - [[T139]] (done, 5/5): Evaluated and closed under AC1 (rejected with evidence: 0 generated columns and 0 materialized views; plain B-tree functional indexes from T138 suffice; avoids staleness contracts and RLS-bypass risks).
        - [[T213]] (queued, 0/8, P2): Hardcoded job-board literals in `wom7api/src/utils/job-sources/`, none in vault; internal duplication with `src/lib/job-boards.ts`; Reed credential dead (403); ast-grep rule missing.
        - [[T52]] (queued, 0/3, P2): `password_hibp_enabled = false`, `password_min_length = 6`, free tier. Plan: add app-side HIBP range API in signup/password handlers + min length 8+.
        - [[T244]] (queued, 1/5, P3): `CF_RUNTIME_API_TOKEN` invalid; sync recipe in `wom7api/justfile:264` targets `wom7func`. Second reader `scripts/ai-eval.ts:16` uses prohibited `||` fallback.
      - **Deferred Decisions & Scope Guards:**
        - [[T19]] (done, 1/1): Synthetic test lead `jordan@acme-test.io` deleted from `leads` table via API (HTTP 204).
        - [[T31]] (paused, 2/4): AC4 ticked (verified active as pre-commit hook `guard-test-admin`). AC2/AC3 remain owner infra actions.
        - [[T32]] (paused, 3/4): DB password rotated; history purge (AC2) in 9 commits on `origin/beta`, rides with T17.
        - [[T396]] (queued, 0/5): Nonexistent `just security-check` in AC5 satisfied by T233 `just audit`; narrow to client-facing surfaces.
  10. **Remeasured 2026-09-29 (supersedes the 2026-09-25 counts above; those stay as the record of that day):**
      - **Stages 0, 1, 2 are fully done** (T100 closed 9/9, T53 7/7; the 09-25 line listing T100 as queued is out of date).
        Stage 3: T233 and T139 done; **T52 2/3**, **T213 5/8**, T244 1/5, all raised to P0 on 2026-09-29 with T396, T468 and T457.
      - **T457 DONE** (3/3): the admin-client ratchet now counts inline, factory and fallback constructions (0 fallbacks, 1 registered
        inline). **T453 DONE** (7/7): default-deny for undeclared `/api/*`, shared capability model. **T335 DONE**: validated plan setter.
      - 🔴 **T497 (new, P0): a regression found by the authz probes** — T465 re-introduced possession-based admin/manager policies on
        contracts, projects and project_roles (RED for three days, 98 violations); fixed by migration `20260929150000`, probes 20/20.
        Open: probes for the other tables, and a scheduled full probe run (see LESSONS "A gate scoped to pushes that touch X").
      - **Owner-blocked in this section:** T213 AC3/AC5 (provision + rotate the job-source keys, none exist in the vault today),
        T52 AC3 (where the documentation lives), T17/T32 (history rewrite), T31 (owner infra), T244 AC1 (what `CF_RUNTIME_API_TOKEN` was for).
* **Type**: Spec → Migration → Build. **Priority**: P0.


## 20. Full-Observability Logging (P1, added 2026-07-15)

> **Epic slug:** `observability-logging`
* **Goal**: One structured log line shape across every surface, correlated by a single trace id, in one queryable sink — so any request or incident is traceable end-to-end (today logs are scattered console/`@wom/logger` sinks with no cross-surface trace, no central store, no alerting, no enforced redaction).
* **Scope**:
  1. **Unified structured logging** — JSON via `@wom/logger` everywhere (no raw `console.*`); standard fields (`ts, level, event, service, env, deploy_version, traceId, spanId, userId?, role?, meta`).
  2. **Cross-surface trace correlation** — `x-wom-trace-id` minted at the entry edge, propagated app→edge-fn→worker, reusing the OTel trace id (complements OTel spans, doesn't replace them).
  3. **Central queryable sink + retention** — CF Logpush (apps+workers) + Supabase log drain (edge fns) → **Tinybird** (in-stack); query by `traceId`/`service`/`userId`/`level`/time.
  4. **Secret/PII redaction** — a redaction pass in `@wom/logger` (deny-list keys + connection-string regex + email→hash); the logging analogue of the gitleaks guard.
  5. **Error alerting** — error-rate spikes + `/health` red → a channel (reuse `notify-telegram`/webhook).
  6. **CP Observability dashboard** — extend System→Services with per-service error rate + recent errors + `deploy_version` + a `traceId` lookup (admin-gated; DS-cited UI).
* **Extends** §13.1 (T22) monitoring; ties §4 health/versioning. **Type**: Spec (written to the authoring standard) → Build. **Priority**: P1. **TASKS T43**; OpenSpec `2026-07-15-observability-logging`.


## 21. Market Research & Business Strategy Continuation (P1, added 2026-07-15)

> **Epic slug:** `market-research-strategy`
* **Goal**: Conduct deeper, focused research into core operational, infrastructural, and discovery layers of the Webomage system to inform AIOps strategy.
* **Scope**:
  1. **Compute Economics & SLM Profitability (R1)**: Investigate the pricing evolution of specialized models (SLMs) and hardware improvements vs. frontier model usage-based billing, mapping out margins for the w0m Open Routing layer. (TASKS T44) [Report: compute_economics_and_slm_profitability.md](docs/research/business/compute_economics_and_slm_profitability.md)
  2. **AI-Native Security Auditing & Code Verification (R2)**: Analyze automated verification tools (SAST, SCA, and AST parsers) that AI agents can use to pre-validate code, minimizing "agentic slop" and volume-induced technical debt. (TASKS T45) [Report: ai_native_security_auditing.md](docs/research/business/ai_native_security_auditing.md)
  3. **Unified ATS Providers (Merge vs. Kombo) (R3)**: Evaluate Merge.dev and Kombo unified API platforms for integration with our candidate-to-vacancy sourcing pipelines (ATS Greenhouse/Ashby/Lever sourcing), focusing on data schemas, Deno Edge Function compatibility, rate-limiting, and cost models. (TASKS T46) [Report: unified_ats_merge_vs_kombo.md](docs/research/business/unified_ats_merge_vs_kombo.md)
  4. **Generative Engine Optimization (GEO) Tracking & Metrics (R4)**: Explore tools/frameworks (like AirOps or custom scraping) to measure "Share of Model" and brand citation frequency across Perplexity, ChatGPT Search, and Gemini. (TASKS T47) [Report: geo_tracking_and_metrics.md](docs/research/business/geo_tracking_and_metrics.md)
  5. **Zero-Cost Funding & Bootstrapping Strategy**: Outline pathways to launch and sustain w0m operations at zero initial capital via automated bidding, startup credit pools, and audit pre-sales. [Report: zero_cost_funding_strategy.md](docs/research/business/zero_cost_funding_strategy.md)
  6. **Claude Developer Certification Syllabus & Study Plan**: Document exam domains, syllabus requirements, and preparation tracks for the Claude Certified Developer Foundations credential. [Report: claude_certification_exam_guide.md](docs/research/business/claude_certification_exam_guide.md)

## 22. Platform & Security Integrations Implementation (P1, added 2026-07-17)

> **Epic slug:** `platform-security-integrations`
* **Goal**: Implement primary integration hooks for w0m dynamic routing, inner-loop safety, third-party ATS pipelines, and brand citation indexing based on Phase 1 research.
* **Scope**:
  1. **w0m Open Routing Layer (T57)**: Deploy dynamic task-complexity categorization and context caching rules between Gemini and local SLMs to optimize compute economics.
  2. **Inner-Loop Agent Security Verification (T58)**: Wire AST-grep syntax validators and OSV-Scanner dependency checks directly into agent commit flows to prevent security regressions.
  3. **ATS Sourcing & Syncing via Kombo (T59)**: Integrate Kombo unified endpoints and secure webhook validators inside edge functions for candidate-to-vacancy mapping.
  4. **GEO Metrics Tracker & llms.txt (T60)**: Deploy automated cron checks via Perplexity and index structured metadata in `llms.txt` for generative engine search optimization.
  5. **Indeed & X-Team Integrations (T63)**: Build the extension DOM importer for Indeed (`wom7ext`) and static query page-data sniffer for X-Team's Gatsby careers portal. [Report: indeed_and_xteam_integration.md](docs/research/business/indeed_and_xteam_integration.md)
  6. **w0m + Dagger + Backstage Synergy Integration (T64)**: Deploy TypeScript Dagger SDK workflows replacing legacy bash deploys, and Svelte catalog cards mimicking Backstage widgets. [Report: open_source_sdlc_alternatives.md](docs/research/business/open_source_sdlc_alternatives.md)
  7. **Gitpod Cloud Developer Workspaces (T65)**: Configure and launch `.gitpod.yml` templates for single-click cloud onboarding. [Report: open_source_sdlc_alternatives.md](docs/research/business/open_source_sdlc_alternatives.md)

## 23. Project Governance & Cohort Staffing Model (P2, added 2026-07-17)

> **Epic slug:** `project-governance-staffing`
* **Goal**: Shift from static global team profiles to dynamic cohort-based staffing and enforce dual DevOps/PM project governance.
* **Scope**:
  1. **Dual-Manager Project Governance Policy (T61)**: Establish rigid sign-off constraints demanding separate PM (Org Manager) and DevOps (Tech Manager) approvals. [Report: project_governance_and_cohort_staffing.md](docs/research/business/project_governance_and_cohort_staffing.md)
  2. **Cohort Staffing Units Schema & UI (T62)**: Migrate Postgres profiles, define `unit_templates` and `project_team_members` tables, and build the role-switching interface inside the Member Control Panel.

## 24. Session Follow-ups (P2, added 2026-07-19)

> **Epic slug:** `session-followups`
* **Goal**: Track the residual follow-ups collected while shipping F1 auth-hardening, the wom7mlx→Gemma 4 re-align, and the cross-repo codegraph rollout. All **P2**.
* **Scope**:
  1. **Finish F1 — access-token-only data components (T80)**: `HealthDashboard`, `ResourceLibrary`, `CandidateManager` (cp+web) still receive `refreshToken` as a server-injected prop and `setSession()` it → the refresh token sits in the DOM (XSS exposure). Convert to the Stage-1 access-token-only pattern (Bearer, no refresh) so F1's intent (no client-side refresh token) is complete. The session cookie itself is already HttpOnly (F1 stage 3, live 2026-07-19). Extends §19. See `docs/backend/AUTH-HARDENING-PLAN-2026-07-18.md`.
  2. **F4 — Origin check on state-changing auth POSTs (T81)**: add an Origin/Referer allowlist check on `switch-role`/`impersonate` as defense-in-depth beyond `SameSite=Lax` (from the F1 Phase-6 review; overlaps T78 G6).
  3. **Gemma 4 Rust port (T82)**: port `wom7-mlx-rs` from the retired GLM-4.6V path to Gemma 4 — a gemma4 loader + dense Gemma decoder + SigLIP vision (+ audio) on `mlx-rs`. The mlx-vlm (Python) gemma4 serving is now live as the numerical reference. Extends §8 / T14; parks the GLM logit-mismatch diagnostic.
  4. **Local image generation (T83)**: Gemma 4 on mlx-vlm is multimodal-**in → text-out** only. For image **output**, add a separate MLX image-gen model/endpoint (mlx-vlm `--image-model` / `--output-modality image`, or a diffusion model). Ties §8.
  5. **codegraph freshness + cross-repo hygiene (T84)**: all 7 wom7* repos now carry `.codegraph/` indexes, but only wom7web keeps fresh (pre-push `codegraph sync`); add a sync step to the other repos so indexes don't drift. Also sync the held dirty vendored repos in wom7mlx (`mlx-rs`, `wom7mlx`, `mlx-web-ui`, `mlx-data` — stash/commit first). Ties §13.4.
* **Priority**: P2. **TASKS**: T80–T84.

## 25. Platform-Integration Sync Restoration & Admin-CP Reorg (P1, added 2026-07-19)

> **Epic slug:** `integration-sync-admin-cp`
* **Why**: The `generic_contracts` migration (`20260708200000_generic_contracts.sql`) made `contracts`/`proposals` multi-source (`source` enum + `external_id` + `UNIQUE(external_id, source)`) — the right model (extends §10.3) — but it was applied **semi-blindly**: the Upwork-specific sub-structure was flattened into an opaque `data` JSONB, the Upwork ID moved from PK → `external_id`, and the platform-specific **sync sub-layer degraded**. A parallel investigation (2026-07-19) confirmed the concrete damage.
* **Findings (as-built)**:
  1. **Two divergent pollers.** The live cron path `supabase/functions/upwork-poller/index.ts` (fired every 30 min by `wom7cfworkers` `src/index.ts`) UPSERTs the `contracts`/`proposals` DB tables; the newer CF-Workflow port `wom7api/src/workflows/upwork-poller.ts` writes **only** storage + Tinybird — **not the DB tables**. Which trigger fires silently decides whether the DB updates.
  2. **Messages sync is entirely absent.** No rooms/messages/conversations table exists in any of the ~177 migrations; neither poller fetches conversations. The only code that ever did — `wom7api/scripts/upwork_exporter.ts` (`roomList` → `room(id).stories`) — is **dead** (imports a removed `mcp-server` client) and its vault output (`wom7web/src/data/upwork_vault/proposals/`) is empty. **Restoring messages is a net-new build**, not a re-wire; also not in the OpenSpec `upwork_pipeline/spec.md` (spec update required).
     ✅ **SUPERSEDED 2026-07-21 by [[T89]] — messages sync EXISTS.** Rooms + messages are modelled and populated (`platform_rooms`/`platform_messages`), and T89 caught a real defect doing it: `Room.stories` takes `filter: StoryFilter` with pagination nested inside, and `graphql()` swallows non-rate-limit errors, so the sync would have persisted **zero messages every run while reporting success**.
     🔴 **But re-measured 2026-07-31, what it captured is a 5% sample → [[T155]].** Live: **129 messages in 10 of 50 rooms**, dated **2026-02-05 → 2026-06-02** against a contract history starting **2012**; `contracts` holds 189 rows for **~94 real** contracts (89 duplicate groups); `proposals` carry **no cover-letter body**. The corpus is an **index, not a record** — it proves a contract existed and cannot say what was built. T89 verified *idempotency*, which a 5% sample passes perfectly; nothing asserted **coverage**. Finding 3's `proposals.contract_id` is likewise still 0-linked for the WebRTC proposals.
  3. **Dropped linkages.** `proposals` has no `contract_id` (proposal↔contract link lost). `projects.contract_id` is still `TEXT` while `contracts.id` became `UUID` → a **broken/orphaned FK** (the `generic_contracts` CASCADE dropped the old constraint; the column type was never migrated).
  4. **Leaky abstraction.** All Upwork structure lives untyped in `contracts.data`/`proposals.data`; `upwork_poller_state` + the `upwork` storage bucket are hard-coded Upwork-only (no `source` dimension); `source` is a closed CHECK enum while `invoices.platform`/`platform_webhooks.platform` are free text (two vocabularies); two read planes (public site reads local vault markdown via `apps/web/src/lib/vault.ts`; CP/client read the DB) reconciled only by a manual `sync_upwork_full.js`.
  5. **Admin CP scatters platform integrations.** Three homes for external-platform surfaces — LinkedIn under "Content" (`/marketing/*`), Upwork buried in the home-dashboard `OpenCLAWDashboard` (not in nav at all), Domain Scanner under "System". No **Integrations/Platforms** hub, no **Sync Health** surface. Generic managers are Upwork-assumed (`contracts/[id].astro` hardcodes Upwork deep-links; `ContractManager` defaults `source='upwork'`; `ProposalManager` bakes in a Connect-Upwork OAuth panel). `InvoiceManager`'s `platform` enum is the one clean generic pattern to generalize. Trigger dispatch is inconsistent (Astro route `/api/admin/domains/trigger` also fires `linkedin:sync` vs. direct `supabase.functions.invoke`). Orphaned pages not in nav: `/business/clients`, `/business/leads`, `/business/vault`, `/business/ats`, `/system/users`.
* **Scope**:
  - **Restore the Upwork platform-sync sub-layer** on top of the generic model (keep multi-source): model + sync for **contracts + proposals + messages**; converge the two pollers; re-establish proposal↔contract + projects↔contract FKs; make sync-state + storage `source`-aware.
  - **Decouple platform adapters from the generic models** in both schema (promote high-value fields out of `data`, or formalize the per-source `data` shape; reconcile `source` enum vs free-text `platform`) and UI (source-agnostic managers; platform specifics behind an adapter).
  - **Reorg the admin CP** around a first-class **Integrations / Platforms** area + a **Connections / Sync-Health** board; unify trigger dispatch behind admin-role-enforced routes; surface or retire the orphaned pages.
* **Uses central knowledge**: CodeGraph (wom7api `.codegraph`), `supabase`/`schema` skills, SCHEMA-AUDIT-2026-07-11.md, OpenSpec `upwork_pipeline` + `2026-07-11-client-conversion-and-contracts`.
* **Type**: needs OpenSpec change(s) → build. **Effort**: L (messages = M net-new; poller convergence + FKs = M; CP reorg = M). **Priority**: P1. **TASKS**: T89, T90.

## 26. Design System — Master, Unify & Claude-Design Sync (P1, added 2026-07-19)

> **Epic slug:** `design-system-unification`
* **Why**: The canonical **Webomage Design System** (`wom7web/design-system/`, a Claude Design "design container" export wrapped as the `webomage-design` skill) is authoritative for **tokens** but only a **spec/reference** for **components** (its component specs are **React JSX**; the runtime is **Svelte 5 + Astro**), and the live code has drifted hard from it. This section makes the DS the mastered, enforced single source and unifies the fractured component layer. Supersedes/expands **T42** (audit → master → sync) and pairs with **T87/T54** (identity surface) and [[design-system-reference]].
* **Findings (2026-07-19 audit)**:
  - **Canonical DS** = `tokens/*.css` (7 files, ~190 tokens in `_ds_manifest.json`, incl. the `--brand-rgb`/`--bg-rgb`/`--text-rgb` golden-rule triplets) — **directly linkable CSS, the real bridge**; + React-JSX component specs (`brand/ core/ data/ overlay/ domain/ forms/`), `guidelines/*.card.html`, `ui_kits/`, `templates/`. Governance artifacts already present: `_adherence.oxlintrc.json` (enforcement ruleset, forbids raw hex/px/non-Inter, encodes prop contracts — but authored for **React selectors**), `_ref/migration/codemod.mjs` (retire `#0a84ff`), and `.dc.html` dashboards (`Audit` / `SpecVsCode` / `GapComponents`).
  - **`_ds_arc/`** = five prior/variant exports (all namespace `WebomageDesignSystem_288053`); the **live `design-system/` is a strict superset** — archives are safe history. (Only inverse gap: canonical `domain/`+`forms/` components aren't in its own `_ds_manifest.json` — staleness to fix.)
  - **Runtime DS** (`packages/ui`, `@webomage/ui`) = 10 shadcn-svelte primitives + custom (`AuthWidget`, `ResumeParser`, `DemoBanner`, `Walkthrough`). **The 7 brand/domain components the DS specs — BlueprintCard, SegmentBadge, ComplexityBadge, TechIcon, GlassCard, StatusDot, QuickViewModal — are NOT in the shared package**; they're forked per app. This is the single biggest structural gap.
  - **Duplication/divergence**: **80 identically-named files** exist in both `apps/web` and `apps/cp`; `Footer.astro` + `ui/Card.astro` are byte-identical dupes; `Header.astro`/`ChatApp.svelte`/`BlueprintCard.astro` are forked-and-diverged; whole trees (`three/`, `templates/`, `interviews/`) are copied. **CP is the epicenter**: ~85 admin components, only ~24/140 files import `@webomage/ui`, **25 native `<select>`** files, **~175 hardcoded `#0a84ff`** + hundreds of macOS-system hex — CP is **~85% off the DS** (already quantified in `design-system/CP-CONFORMANCE-GAP-2026-07-16.md`).
* **Scope**:
  1. **Master (deep audit)**: audit every component/widget across `web/cp/join/job` + `packages/ui` vs the DS; refresh `_ds_manifest.json` (add `domain/`+`forms/`); regenerate the `Audit`/`SpecVsCode`/`GapComponents` dashboards; lock the unified target component set.
  2. **Unify**: promote the 7 brand/domain specs into `@webomage/ui` as Svelte; dedup the identical/forked shared components (Footer, Card, Header, badges, BlueprintCard, ChatApp); migrate the apps off per-app forks; run the `#0a84ff` codemod on CP; wire the per-app `[data-app]` theme mechanism.
  3. **Claude-Design sync pipeline + enforcement**: a repeatable **export → diff → apply** flow — Claude Design export refreshes `design-system/`; a token-drift diff (manifest = source of truth) checks `packages/ui` CSS vars + app `global.css`; apply = generate one consumable token CSS bundle + port JSX specs → Svelte + codemod hardcoded hex; port `_adherence.oxlintrc.json` to a **Svelte-aware** linter wired into the pre-commit hook stack ([[wom-precommit-hooks-standard]]) so drift can't re-enter.
* **Uses central knowledge**: the `webomage-design` skill, `design-system/` artifacts (manifest, dc.html, codemod, adherence ruleset), [[header-ui-spec]] golden rule, [[design-system-reference]].
* **Type**: T42 is the umbrella; this is its concrete breakdown. Needs OpenSpec change → build. **Effort**: L (unify = the bulk; sync tooling = M). **Priority**: P1. **TASKS**: T91 (master/audit), T92 (unify shared components), T93 (sync pipeline + enforcement). Supersedes T42's three phases.

## 27. Platform Connector/Plugin Architecture + Connected-Services Docs (P1, added 2026-07-19)

> **Epic slug:** `platform-connector-architecture`
* **Why**: The team wants a **plugin/connector per platform**, usable both for **system-internal needs** (contracts/jobs/webhooks sync) AND for **members'/trainees' profile syncing + integration with other APIs**. A 2026-07-19 multi-agent inventory found the pieces exist but are ad-hoc: connectors are hand-rolled per service with no shared contract or registry.
* **Findings — connected-services inventory (as-built, 2026-07-19)**. Grouped:
  - **Infrastructure** (platform runs on): Supabase (DB/auth/storage + the edge-fn gateway to everything), Cloudflare Workers (AI proxy chat/embed via `ai_models` registry, Browser-Rendering PDF, workflow trigger, image-gen REST), Infisical (deploy-time secrets), GitHub App (`github-repos` edge fn), AWS (tooling).
  - **External-platform integrations** (business/profile data — the connector candidates): **Upwork** (GraphQL+OAuth; tokens in `upwork_auth_tokens`; contracts/proposals; pg_cron 30 min → `upwork-poller`), **LinkedIn** (OAuth+REST v2; tokens in `social_integrations`; `profile_snapshots`/`linkedin_post_analytics`), **Deel** (inbound `platform-webhook-gateway`, HMAC, `contracts source=deel` — minimal), **ATS Merge.dev/Huntflow** (a **clean connector factory already exists** in `wom7cfworkers/src/services/ats/{types,factory,merge,huntflow}.ts` — `AtsConnector` interface + strategy selection), **job boards** (RemoteOK/Remotive/WWR/NoFluffJobs/CryptoJobsList/Adzuna via `job-scanner`), **Credly/Accredible** (credential verify → `verified_credentials`).
  - **AI/inference**: CF Workers AI (primary), Google Gemini/Gemma (fallback+news), Mistral (CF fallback), Google Stitch (mockup, partial). (OpenAI/Groq/Cohere/Perplexity NOT wired.)
  - **Messaging/notify**: Telegram (bot+webhook+notify; partly decommissioned per §7), SMTP (nodemailer).
  - **Observability/analytics**: Tinybird, Opik/Comet, OTel→Honeycomb+PostHog, GA4, Calendly.
  - **Member/trainee profile SOURCES** (the profile-sync connector targets): LinkedIn, Upwork, resume/CV (`parse-resume`), GitHub, Credly/Accredible.
  - **Payments**: Stripe (checkout+webhook, HMAC — live), Solana/crypto payout (stubbed).
  - **Existing abstraction attempts**: (1) the **ATS connector factory** (the clean pattern to generalize); (2) `platform-webhook-gateway` inbound seam (`?platform=`, HMAC, `platform_webhooks` table, hard-coded `if(deel)` branch); (3) the `source`/`platform` multi-source column on contracts/proposals/invoices; (4) `platform-orchestrator` (Score/Kratix, mocked — separate concept). **No central `connectors`/`integrations` registry; OAuth lives per-service** (`upwork_auth_tokens` vs `social_integrations`).
  - **🔒 Security flags surfaced**: hard-coded fallback API keys committed in `wom7cfworkers/src/utils/job-sources/{adzuna,jooble,reed-courses}.ts` (dead/unwired code, but leaked values in source → rotate+remove); the `debug_key`→hCaptcha `"bypass"` path in web `ContactFormSection`.
* **Scope**:
  1. **Formal connector contract + registry**: generalize the ATS factory into a platform-agnostic `Connector` interface (`connect/auth`, `sync`, `profileSync`, `handleWebhook`, `status`) + a **`connectors`/`integrations` registry** (one row per platform+account: kind, auth-ref, scopes, health, last-sync) that unifies `upwork_auth_tokens` + `social_integrations` under one model.
  2. **Two connector modes**: (a) **system connectors** (Upwork contracts/proposals/messages [ties T89], Deel, job boards, ATS) and (b) **member/trainee profile connectors** (LinkedIn/Upwork/GitHub/CV/Credly → a unified profile-sync that populates member & trainee profiles + enables outbound integration to other APIs).
  3. **Generalize the inbound gateway** beyond the `if(deel)` branch (dispatch by registered connector).
  4. **Connected-services documentation** (request #2): a single **connector map** doc + per-service **data-flow (.mmd)** + **event/workflow** docs; fill the zero-doc gaps (GA4, Calendly, GitHub App, AWS, Stripe/fiat, Hume EVI); reconcile the drift the inventory found. The 2026-07-19 inventory is the seed artifact.
* **Uses central knowledge**: CodeGraph, `supabase`/`schema`/`mcp-builder` skills, `openspec/specs/observability_map.md`, `docs/backend/ats_integration_analysis.md`, the ATS factory as the reference pattern.
* **Type**: needs OpenSpec change(s) → build. **Effort**: L. **Priority**: P1. **TASKS**: T94 (connector architecture + registry), T95 (connected-services discovery → docs/schemas/data-flows/events).

## 28. w0m Full Audit/Status Command — git-triggered + manual (P1, added 2026-07-19)

> **Epic slug:** `full-audit-status-command`
* **Why**: The team wants one **`just` command for a full w0m audit/status** — drift + diff determination with knowledge and docs refreshed — runnable **both from a git hook and manually**. The building blocks already exist but aren't composed into a single authoritative sweep + report.
* **Findings — existing `just` knowledge/guardrail recipes**: `check-guardrails` (gitleaks×2 + guard-test-admin + connection-string scan), `check-status`/`healthcheck.py`, `health`, `spec-drift` (`spec_drift_gate.py`), `codegraph-sync`, `tech-debt` (census), `lexicon-lint` (T23/T25 truth), `status-dashboard`, `knowledge` (full: graph + tech-debt + lexicon + spec-drift + codegraph + dashboard), `knowledge-light` (fast, post-deploy), `report-tracks`, `audit-seo`, `audit-media`, `deno-check`, `snapshot-knowledge.mjs`. The **pre-push hook** already runs `spec-drift` + `codegraph-sync` scoped to the push.
* **Scope**: a single **`just audit`** (a.k.a. `just w0m-status`) that: (1) **drift** — spec-drift, lexicon/schema truth, codegraph freshness, tech-debt census, DS conformance (ties T91), decommission-doc drift; (2) **diff** — working-tree vs deployed version (DEPLOY_* stamps / `deploy_log`), migrations-applied vs on-disk, secrets-declared vs used (the inventory found declared-but-unused secrets); (3) **health** — `check-status`/`/health` across apps+edge fns+workers; (4) **knowledge/docs refresh** — regenerate status dashboard + knowledge-light + the connector map (T95); (5) emit one **audit report** artifact (md/html) with a pass/fail summary. Wire a **fast subset into a git hook** (pre-push, already partial) and the **full sweep as manual** (`just audit`) + optionally a scheduled run. Extends T22 (guardrails/monitoring) + T23 (SDLC/knowledge) + T84 (codegraph freshness).
* **Type**: mostly composition of existing recipes + new drift/diff checks + a report. **Effort**: M. **Priority**: P1. **TASKS**: T96.

## 29. Tours→Docs/Screencasts, Publishable Docs & LinkedIn Premium (P2, added 2026-07-19)

> **Epic slug:** `docs-screencasts-content`
* **Why**: (a) turn the T79 walkthrough **`TOURS` registry** into a generator that also **bakes screencasts + per-audience `.md`/`.pdf` docs** for members, clients and trainees (docs stay in sync with the real product because they're generated from the same tagged UI); (b) review what documentation is safe to **publish as whitepapers / media / promo**; (c) evaluate the **LinkedIn Premium trial**.
* **Scope**:
  - **Tours→docs engine** (T97): the `TOURS` registry (`packages/ui/.../walkthrough/tours.ts`) is the single source — each tour = ordered steps (title/body/`data-tour` target). Add a generator that drives the tour with Playwright to (1) **record a screencast** per audience-tour, (2) capture per-step screenshots + compose **`.md` and `.pdf`** guides. Audience variants (member/client/trainee) select tour sets. Integrate with the docs/knowledge base so generated guides land in the right KB tier.
  - **Publishable-docs review** (T97): audit `docs/**` for what can become **whitepapers / media / promo** vs. what must stay internal — governed by the **KB content policy** ([[kb-content-policy]]: projects/client work never public). Produce a publish-allowlist + a public-docs pipeline.
  - **LinkedIn Premium trial** (T98): the trial maps to the recruiting/sourcing funnel — **Sales Navigator** advanced search + lead lists + InMail for candidate/client sourcing; who-viewed/profile-unlock to enrich `profile_snapshots`/CV. **⚠️ ToS-bounded**: Premium ≠ API access and ≠ scraping rights; the official LinkedIn Talent/Marketing API is a separate gated partner program. So the trial is a **manual evaluation** (does SN sourcing justify a paid recruiter seat? feed leads by hand) — NOT a signal to automate `wom7ext` against Premium (bans hit paid+reputational). Also assess pursuing the sanctioned LinkedIn API partnership.
* **Type**: T97 = build (generator + pipeline); T98 = research/evaluation (no build). **Effort**: M / S. **Priority**: P2. **TASKS**: T97 (tours→docs + publishable), T98 (LinkedIn Premium eval).

## 30. wom7sec — Standalone Security & Code-Audit Toolchain, deployable as a service (P1, added 2026-07-21, updated 2026-09-11)

> **Epic slug:** `wom7sec-audit-toolchain`

* **Why**: `wom7sec` is the **comprehensive, multi-tier audit toolchain and customer acquisition engine** powering Webomage. It runs progressive security, code, and cloud infrastructure audits on external client projects, usable as a public web lead magnet, as an authenticated client diagnostic, and deployed as an automated service. It also outpositions visual IaC platforms like **Brainboard** by pairing automated reverse-engineering and visual topology graphing with senior guild execution and self-healing AIOps.
* **Three progressive audit depths (the core definition)**:
  - **Level 1 — Public Surface & Perimeter Audit (Free Lead-Magnet)**: Zero-friction public web form (`apps/web` / `/audit`). Runs a fast (<10s) passive edge scan across TLS ciphers, HTTP security headers, DNS/DMARC/SPF, and public exposures (`security.txt`). Results are rendered as an instant teaser scorecard, while actionable vulnerability details and PDF downloads are gated behind free client registration (via `client-register` edge fn, delivering into `apps/cp`). (TASKS: [[T336]]).
  - **Level 2 — Advanced Code & Blueprint Audit (Sandboxed Static Analysis)**: Requires read-only git repository access. Executed inside an **ephemeral, strictly isolated sandbox** (Tart microVM / Cloudflare Sandbox). The repository is cloned into a quarantined volume, and all outbound network interfaces are severed (`--network none`) before executing polyglot SAST (Semgrep), SCA (Trivy), secret scans (Gitleaks), and IaC checks (Checkov). Defends against malicious repositories, SSRF traps, and prompt injection payloads. (TASKS: [[T337]], [[T111]]).
  - **Level 3 — Deep Cloud Infrastructure & Runtime Posture (Brainboard Competitor)**: Connects via read-only cloud IAM credentials (AWS, GCP, Cloudflare, Supabase) and optional Kubernetes sidecars. Integrates the curated `@k7` stack (`terraformer` / `terracognita` for live cloud reverse-engineering, `k7tg` Rust engine for visual topology graphing, and `terracost` for FinOps waste detection). Unlike Brainboard's $99/seat DIY software, Webomage pairs automated discovery with senior guild execution and self-healing AIOps. (TASKS: [[T337]], [[T111]]).
* **Scope** (OpenSpec change: `openspec/changes/2026-09-11-multi-tier-audit-and-secure-sandboxes`):
  - **Sandboxed repo ingest**: run an audit against a private clone from **GitHub / GitLab / Bitbucket / any git remote** inside an **isolated sandbox** (no audited code executes on the host). Candidate substrate: **Tart microVMs** (proven under [[T296]]/[[T297]]) and **Cloudflare Sandbox SDK** (`sandbox-sdk` skill) — evaluate isolation, egress control, and per-run teardown as a hard requirement.
  - **Blueprint-driven profiles**: each mastered blueprint (design system, auth/RBAC, observability, edge-fn contract, …) exposes an **audit profile** = the rule packs + skills that check conformance. A project selects profiles; the toolchain composes them. This is how "mastered audit tools and skills for all of them" accretes over time — one profile per blueprint, added as each is mastered.
  - **Polyglot code coverage**: audit **TS/JS, Python, Go, Rust, PHP, …** as first-class — each language's SAST/lint/SCA (semgrep/bandit/ruff/gosec/cargo-audit/trivy/osv/eslint/…) wrapped in the uniform result contract. **IaC/cloud tooling is first-class too**: **Terraform** (tfsec/checkov/terraform validate), plus the **AWS and GCP CLIs/SDKs** for config and posture review — not an afterthought bolted onto the code scanners.
  - **Deep-mode infra + network — two access patterns**:
    - **API-side** (read-only, no deploy): pull config/posture by **talking to provider APIs** — **AWS, GCP, Azure, Cloudflare, Supabase, Vercel, …** — IaC/config review, IAM/permission posture, exposure. A pluggable **provider-connector layer** (one adapter per API) is core, not per-audit glue.
    - **In-cluster** (for runtime + network analysis that an external API can't see): deploy a **short-lived sidecar / job into the target's own cluster** — **GKE, ECS, EKS, k8s, …** — to observe the running app from inside (live network analysis, reachability, in-cluster exposure, TLS), then tear down. Sidecar is the mechanism for *runtime* depth; the sandbox is the mechanism for *code* depth.
    - **Authorization-gated throughout**: never touch infra the caller can't prove they own; read-only by default; no exploitation; sidecars are explicitly consented, minimal-privilege, and self-terminating.
  - **Deploy as a service**: **the service itself is TS** — a TypeScript API is the single **endpoint** for the whole toolchain (submit a repo URL *or* a cloud scope → report). Multi-tenant, per-run sandbox, artifact storage, webhook/PR-comment output. TS is chosen precisely so the toolchain has one clean HTTP endpoint and control plane.
  - **Reuse the `@k7` infra tooling — integrate, don't rebuild.** The sibling `@k7` family (at `Projects/@self/@k7`, same level as `@wom`) already curates the Terraform→graph/data stack this needs — full survey in **[docs/K7-FAMILY.md](docs/K7-FAMILY.md)**: **`k7c`** bundles **inframap** (Terraform/state → infra graph diagrams), **terracost** (cost estimation — the **FinOps** seed), and **terraformer** + **terracognita** (reverse/import live cloud → Terraform); **`k7tg`** is k7's own Rust Terraform-graph tool (spec-driven, with the infra-dump-to-graph/data + **dashboard** the owner described). wom7sec's infra layer should **wrap these as scanners/connectors** behind the uniform result contract rather than re-implementing graphing and cost. Also relevant next door: **`k7s`** (k9s, process-compose — k8s/runtime, feeds the sidecar model), **`k7d`** (ctop — container observability), **`k7spec`** (spec-kit — methodology).
  - **FinOps as a first-class audit dimension** (not only security): surface **cost / waste / rightsizing** findings alongside vulnerabilities — orphaned resources, over-provisioning, untagged spend, egress cost, idle infra — seeded by **terracost** and the provider billing APIs. A **FinOps audit profile** sits beside the security profiles. This is a deliberate scope expansion: wom7sec audits *security **and** cost posture*.
  - **`@k7` is also the first audit target (dogfood).** The k7 family is w0m-adjacent code + infra we own — scan it first to prove shallow (polyglot code) and deep (its Terraform/infra) before external customers.
  - **Competitor study & positioning**: **Brainboard** (visual Terraform/IaC designer — canvas + infra graph + cost estimation + CI/CD) is the closest reference for the graph+FinOps+dashboard angle. Webomage beats Brainboard by eliminating the $99/seat DIY software barrier: Webomage provides a zero-friction Level 1 entrypoint, full-stack application code scanning (Level 2), automated cloud topology graphing via `@k7` (Level 3), and end-to-end senior execution and self-healing AIOps.
  - **Observability of the tool stack**: the scanners and connectors are polyglot; wrap each with a **uniform structured-result contract** (ties §20 logging) so a Python tool, a Go linter, a Terraform check and a TS connector all report the same shape, with per-tool timing/exit/coverage — the tool stack is itself observable.
* **Tech direction (near-term)**: **TypeScript service core + skills, deployed to Cloudflare.** TS owns the **endpoint + control plane** (submit → schedule → sandbox/sidecar → collect → report) and the **provider-connector layer** (CF/Supabase/Vercel/AWS/GCP APIs). **The polyglot scanners (Python/Go/Rust/… + Terraform/aws/gcp CLIs) run inside the CF Sandbox / Tart microVMs** (code audit) or inside a **dispatched sidecar** in the target's cluster (runtime audit) — TS orchestrates, they execute, everyone reports the uniform contract.
* **Relationships**: productises internal `just audit`/`w0m_audit.py` (§28/T96) for external targets · **integrates the `@k7` infra stack** (`k7c` inframap/terracost/terraformer/terracognita, `k7tg`) as its graph + FinOps engine · consumes mastered blueprints ([[design-system-reference]], auth/RBAC §19, observability §20) as audit profiles · shares the universal skill set (`wom7skills`, `GENERIC-SDLC-SET.md`) · `security-guardrails` / `rbac-auditor` skills are early profile material · competitor benchmark: Brainboard.
* **Type**: research + spec now. **Effort**: L (multi-phase — Level 1 lead magnet → Level 2 sandboxed code → Level 3 deep cloud/infra). **Priority**: P1. **TASKS**: [[T111]], [[T336]], [[T337]].
* **Sequencing**: (1) Level 1 Public URL Lead Magnet & Client Registration Gate ([[T336]]); (2) Level 2 Ephemeral Air-Gapped Code Sandbox Runner ([[T337]]); (3) Level 3 Cloud Provider Connectors & `@k7` Visual Topology Graph vs Brainboard ([[T337]]); (4) Mastered blueprint profile library accretion.

## 31. Content & Blueprint Deep-Review + DS Alignment (P1, added 2026-07-22)

> **Epic slug:** `content-blueprint-review`
* **Why**: The non-code **content corpus** — the branding/application material (CV, role templates, cover letter, screening Q&A), the published **blueprints**, and the marketing/doc surfaces — has grown fast and now risks drifting from the record (the CV, the live DB) and from the mastered Design System. §26/T91–T93 harden the **component** DS; this section hardens **content**: what it *claims* and how it *reads*, not just how it's built. Prompted by the 2026-07-22 branding-templates session, where a role-focused application summary had to be reconciled against the live `projects`/`contracts` tables and the CV (several claims needed correcting — e.g. Meetocean's HIPAA-healthcare vs CRM tag, Airflow/Hatchet not on the CV, Kayse's SOC 2 legal RAG).
* **Scope**:
  1. **Branding/application content hardening** — audit `docs/backend/branding/**` (CV × 3 formats, `role-templates/` × 6, `cover_letter.md`, `qa_screening.md`) for: **accuracy/honesty** (every project·metric·compliance claim traces to the CV or the live DB), **cross-file consistency** (shared facts live once), **ATS keyword coverage** per role, and **char-limit/ASCII-safety** of the Upwork intros. Regenerate CV `.html`/`.pdf` from the `.md` source on change. Spec + running checklist: `docs/backend/branding/TODO-content-hardening-audit.md`.
  2. **Blueprints deep-review** — review each published blueprint (`apps/web/.../blueprints/*` + blueprint DB rows) for correctness, positioning, and conformance to the canonical DS + [[design-system-reference]]; every **mastered blueprint** ships an **audit profile** (the tools+skills that verify conformance) — the same profile concept §30/T111 consumes.
  3. **DS enhance + align** — feed content findings back into the DS: align blueprint/marketing/doc surfaces to the canonical tokens + `@webomage/ui`, and close copy/voice/token drift the T91–T93 component pass doesn't reach.
* **Tooling (build small, reuse)**: a **claim-extraction → source-diff** checker (parse factual claims from branding docs, diff against a CV/DB export, flag unsupported) + an **intro char-counter** over every fenced "Short Intro" block. Optionally grow the `qa_screening.md` library from real applications via the AI job-scoring pipeline.
* **Respect** [[kb-content-policy]] — client/project work never enters a public KB tier.
* **Relationships**: extends §26 (DS master/unify/sync, T91–T93) · feeds §30/T111 blueprint audit profiles · consumes [[design-system-reference]] · governed by [[kb-content-policy]].
* **Type**: recurring hardening pass; needs an OpenSpec change before the tooling build. **Effort**: M (content audit = the bulk; checkers = S). **Priority**: P1. **TASKS**: T118.

## 32. Universal System Standards, RFCs & Single-Source-of-Truth Enforcement (P1, added 2026-08-14)

> **Epic slug:** `universal-system-standards`
* **Why**: The `w0m` ecosystem across 6 monorepos encompasses multiple architectural tiers: database DDL, REST/Edge functions, MCP tool definitions, W3C WebMCP adapters, UI design tokens, and agent skills. Without an explicit standard assigned per tier, data structures drift and contracts duplicate (e.g., manual TypeScript types diverging from Postgres DDL; MCP tools using custom unvalidated schemas).
* **Core Rule**: Every entity, schema, model, interface, and API must adhere to a recognized, explicit Standard / RFC, with **strictly ONE Single Source of Truth (SSOT)** per domain and unidirectional compilation/validation.
* **Standards Mapping**:
  - **Database & DDL**: PostgreSQL SQL-92 / ANSI DDL migrations (`supabase/migrations/*.sql`) → generates TS types via `just db-types`.
  - **REST / Edge APIs**: OpenAPI 3.1.0 / JSON Schema Draft 2020-12 via Hono `@hono/zod-validator`.
  - **Model Context Protocol (MCP)**: MCP Specification 2024-11-05 with JSON Schema Draft 2020-12 input schemas.
  - **Browser Agent Tools**: W3C WebMCP (`navigator.modelContext`) via `@webomage/webmcp`.
  - **Design System Tokens**: W3C DTCG Design Token Format / CSS Variables (`design-system/tokens/*.css`) → `@webomage/ui`.
  - **Agent Skills**: Agent Skill Specification v1.0 (`wom7skills/skills/*/SKILL.md`).
  - **SDLC & Governance**: OpenSpec 1.x + Conventional Commits.
* **Scope**:
  1. Master the **System Standards Matrix** (`docs/standards/SYSTEM-STANDARDS-MATRIX.md`) and **SSOT Authority Graph** (`docs/standards/SSOT-AUTHORITY-GRAPH.md`).
  2. Perform an ecosystem-wide audit across all repositories for hand-rolled non-standard schemas and unvalidated payloads.
  3. Deploy automated static validation gate `just standards-check` into CI and `just sdlc-doctor`.
* **Type**: Architecture → Spec → Audit → Build. **Effort**: L. **Priority**: P1. **TASKS**: T214.


## 33. Client Alfa — Full Feature Support, Staged (P0, added 2026-08-17, completed 2026-10-19)

> **Epic slug:** `client-alfa` · **Status:** ✅ **COMPLETE (`23/23` tickets `done`, 2026-10-19)**

> 🔀 **Split, owner decision 2026-09-12 & rebalanced 2026-10-19: this program is "Client Alfa" (complete);
> Money & expansion are "Client Beta" (§34).** Stage 4 below (real Stripe reconciliation) and post-onboarding
> service expansion moved to §34 so the first-client funnel/tenancy/portal foundation (Alfa) and commercial
> expansion (Beta) progress independently. With `client-alfa` (`23/23`) and `hero-epic` (`10/10`) both `100%`
> complete on 2026-10-19, `current_plan` advances to **§34 Client Beta**.

> **Cross-cutting dependency, added 2026-08-22 (✅ done):** [[T254]] — unified device identity
> (`session → device → visitor → user`). Shipped with fail-closed quota enforcement and shadow telemetry.

* **Owner ask (2026-08-17)**: *"full features support for clients, but let's split it in stages"* —
  the destination is the §10 feature set (register → discovery → proposals → contracts → portal), reached
  in gated stages.
* ✅ **Measured completion position, 2026-10-19 — both the funnel and multi-tenant portal are live and verified (`23/23` tickets `done`):**
  * ✅ **Registration & intake are live end-to-end.** Chat carries `submit_service_request` in `public` scope
    ([[T246]], [[T249]], [[T251]], [[T253]]); the widget renders the interactive **"Review & submit"** intake card
    ([[T263]]) and 10-question **technical-discovery interview** ([[T217]]) that ranks blueprints and seeds
    machine-drafted proposals ([[T4]]); CP LeadManager splits `AI consultant` vs `Manual / other` leads ([[T263]]).
  * ✅ **[[T198]], [[T202]], [[T281]], [[T289]], [[T324]], [[T325]], [[T358]] — safety floor and multi-tenant isolation verified.**
    All 11 ACs of [[T198]], all 7 ACs of [[T202]], and [[T358]]'s RLS/definer grants and Stage 3 exit probes are green (`0` cross-tenant rows for a client actor).
  * ✅ **[[T229]] (P0, `done`)** — Supabase Pro tier + PITR + restore verification completed.
  * ✅ **[[T3]], [[T5]], [[T283]], [[T338]], [[T346]], [[T349]], [[T350]] — shared client/team CP, unified contracts, and MX KYC.**
    `/o/[org]` (`ClientDashboard.svelte`) surfaces client projects, **Proposals & Service Requests**, contracts, and activity ([[T3]], [[T283]]); `/o/[org]/money/contracts` (`unified-registry.ts`) unifies `direct` contracts with read-only `upwork_contracts_view` mirrors and editable `source_links` annotations ([[T5]]); `@wom/kyc` + Admin CP corporate verification are live ([[T346]], [[T349]]).

### Stage 0 — Safety floor (COMPLETE)
* [[T229]] paid tier + PITR + restore exercised (✅ done).
* [[T198]] all nine authorization defects closed (✅ `11/11` ACs done).
* [[T202]] shared Supabase client RLS/key separation (✅ `7/7` ACs done).
* [[T358]] Client Alfa Safety Floor: RLS policies, definer grants, and Stage 3 exit verified (✅ `4/4` ACs done).
* **Exit criterion, measured:** T198/T358 actor probes show **0 cross-tenant rows** for a client actor.
* **Type**: Fix → Verify. **Effort**: M. **Priority**: **P0**.

### Stage 1 — Register, intake & discovery (COMPLETE)
* [[T263]] `ai-intake-service-requests` (✅ done 2026-10-19: widget "Review & submit" card + CP lead source-split).
* [[T217]] structured technical-discovery interview (✅ done 2026-10-19: `DiscoveryProfileV1`, blueprint ranking, customization diff, offer math, T4 handoff).
* [[T338]] GitHub-repo link field (`vcs`) in client registry + Artemio `vcs.repo` fix (✅ done 2026-10-19).
* [[T2]] AC4/AC5 — registration chain (✅ done).
* [[T20]]-F deterministic submit affordance (✅ done).
* [[T3]] shared client/team CP with role-scoped nav and client portal home surfacing requests / proposals / contracts / progress (✅ done 2026-10-19).
* [[T253]] a visitor's chat becomes their own content on signup (✅ done).
* **Exit criterion:** registration chain — chat → card → magic link → portal — verified with automated regression tests.
* **Type**: Build → Verify. **Effort**: S–M. **Priority**: P0.

### Stage 2 — Proposals & acceptance (§10 item 2, COMPLETE)
* [[T4]] `lead_proposals` + `blueprint_id` + `adventure_id`; consultant conversations seed machine-drafted
  proposals (`seedMachineDraftProposal` wired with [[T217]] discovery handoff); acceptance hands off to a contract **and** a delivery container (✅ done).
* Proposal review/accept surface in the client portal (`ClientDashboard.svelte` `Proposals & Service Requests`, ✅ done in [[T3]]).
* **Type**: Spec (written) → Build. **Effort**: M. **Priority**: P1.

### Stage 3 — Contracts & delivery visibility (§10 item 3, COMPLETE)
* [[T5]] unified contracts registry over `source: direct` + external platform mirrors (`upwork_contracts_view` + `source_links`); read-only mirror terms, editable internal annotations (✅ done 2026-10-19).
* [[T325]] contract attribution to clients and client org user linkage (✅ done).
* **Type**: Build. **Effort**: M. **Priority**: P1.

### Stage 4 — Money — MOVED to §34 "Client Beta", 2026-09-12

* This stage (real Stripe reconciliation, [[T290]]) is tracked in **§34 — Client Beta** below.

### Parallel track — internal w0m mechanics (COMPLETE)
* [[T203]] guild machinery (✅ done).
* [[T117]]/[[T200]] unified roles/capabilities/offices (✅ done).
* [[T22]] standing health & guardrails (✅ done).
* **Type**: Program. **Effort**: L. **Priority**: P1 (internal-facing).


## 34. Client Beta — Client Delivery, Contracts & Money (P1, added 2026-09-12, broadened 2026-09-29, rebalanced 2026-10-19)

> **Epic slug:** `client-beta`

> 🔀 **Split out of §33 "Client Alfa", owner decision 2026-09-12** (was Alfa's Stage 4, "Money"), **broadened 2026-09-29**,
> and **rebalanced 2026-10-19 (owner direction)**: essential first-client funnel & portal foundations ([[T263]], [[T217]], [[T338]],
> [[T3]], [[T5]]) moved into §33 `client-alfa` and shipped to `done`, while advanced post-onboarding expansion tickets
> ([[T282]] compliance/audit packets, [[T364]] LATAM KYC & subscription gating, [[T344]] mandatory Telegram, [[T357]] external
> work-report ingestion, [[T528]] KYC personal half) moved from `client-alfa` into `client-beta`.

**Workstreams** (a proposed order, not a decision — the owner confirms; each ticket keeps its own ACs):

| # | Workstream | Tickets | Gate / precondition |
|---|---|---|---|
| B1 | **Money & Stripe** | [[T290]] (reconciliation; `simulate_payment` already out of production), [[T351]] (Mexican rails), [[T373]] done | **Owner:** connect Stripe (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` in `beta`) — T290 AC0 |
| B2 | **Contracts & registry** | [[T101]] contract model; [[T204]] `projects` split (paused) ([[T5]] and [[T3]] moved to §33 `client-alfa` and done) | none; T101 first |
| B3 | **What a client sees & expansion** | [[T272]] services + costs, [[T284]] knowledge hubs, [[T288]] case-study publishing (✅ done), [[T285]] message threads (✅ done), [[T344]] mandatory Telegram, [[T357]] external report ingestion (✅ done) | T272 touches credential display: read its security ACs first |
| B4 | **Managed-client onboarding, KYC & compliance** | [[T279]] (Maksim: servicios777, personaje0), [[T280]] SDLC/tenancy scoping, [[T287]] repos as entities (✅ done), [[T292]] GitLab/Bitbucket/self-hosted, [[T282]] compliance/audit packets (✅ done), [[T364]] LATAM KYC & subscriptions, [[T528]] KYC personal half | **Owner:** account onboarding is owner-only |
| B5 | **Jobs Portal, Resume Studio & Outreach Vault (`AgDR-0033`)** | [[T560]] `job.webomage.com` CP shell & boundary cutover (✅ done), [[T561]] Outreach & Clipping Vault schema + `outreach-clip-ingest` (✅ done), [[T562]] `wom7ext` universal & multi-platform clipper (✅ done), [[T563]] `apps/job` Outreach & Communications Hub UI (✅ done) | `AgDR-0033` decided & shipped 2026-10-19 |

* Invoices -> `stripe-checkout` is **already live from the client UI**
  (`apps/cp/src/components/client/InvoiceList.svelte:29`); what is missing is reconciliation
  against real Stripe activity and keeping `simulate_payment` out of the production path.
* [[T290]] is the money stream's ticket. Its own AC0 documents the standing business precondition:
  reconciliation (AC3–AC5) cannot be built until an owner connects a Stripe account and sets
  `STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET` in `beta` — a reconciler built against an absent
  account would compare an empty set to an empty set and report success forever. That connection
  began 2026-09-12; AC0 tracks whether it is complete.
* **Exit criterion (money, unchanged):** invoices reconcile against real Stripe activity, and `simulate_payment` is
  out of the production path (✅ already true, verified on the deployed function — see T290 AC1/AC2).
* **Proposed epic exit (owner to confirm):** a managed client can sign in, see their own project, contract, services and
  costs, and pay an invoice that reconciles against Stripe — with none of it visible to another tenant.
* **Type**: Build → Audit. **Effort**: L. **Priority**: P1. **TASKS**: T290, T351, T101, T272, T284, T288, T285, T279, T280, T287, T292, T204, T282, T364, T344, T357, T528, T560, T561, T562, T563.


## 35. Apple Virtualization & MicroVM Sandboxes (P1, added 2026-09-18)

> **Epic slug:** `apple-virtualization-sandboxes`

* Native Apple Silicon microVM containerization and desktop guest agent virtualization, establishing isolated code-execution sandboxes for AI agents and developer workloads.
* Incorporates Tart-based full macOS/Linux desktop sandboxes and lightweight ephemeral microVM virtualization (`apple/container` and Tart Guest Agent).
* Provides automated guest packaging, headless control pipelines, dynamic memory bounding, and security boundaries separating untrusted client/agent code from the host system.
* **Key tickets:** [[T373]] (Tart & Tart Guest Agent virtualization packaging and microVM sandboxes), [[T368]] (Research Apple Silicon native microVM containerization, compose orchestration, and GUI tooling), [[T365]] (GUI sandbox browser & extension bundling).
* **Exit criterion:** Reproducible sub-second microVM launch with automated guest-agent RPC communication, verified under air-gapped network rules.
* **Type**: Infra → Tooling. **Effort**: M. **Priority**: P1. **TASKS**: T373, T368, T365.


## 36. Generative Video & Media Subprojects — wom7clips & wom7ava (P2, added 2026-09-18)

> **Epic slug:** `generative-video-media`

* Standalone AI generative media subprojects targeting automated business marketing content and consented-identity virtual avatars.
* **wom7clips** ([[T322]]): Generates short thematic videos ("shorts"/"reels") for SMB marketing content on Instagram, TikTok, and YouTube Shorts. Ports and reuses provider abstractions (`IVoiceEngine`, `IVisualMotionEngine`, `ILLMEngine`), hardware profiling, and brand kit vaults (logos, palettes, guidelines) from sibling research.
* **wom7ava** ([[T323]]): Real-time virtual avatar synthesis for video conferencing with biometric consent ledgers, facial reenactment, low-latency audio/video pipelines, and strict anti-impersonation guardrails.
* **Exit criterion:** Scaffolding complete for `casualuser/wom7clips` and `casualuser/wom7ava` with typed provider contracts and clean CI/build gates.
* **Type**: Product → AI. **Effort**: L. **Priority**: P2. **TASKS**: T322, T323.


## 37. Open Source Forks & PR Federation — wom7pr Tooling & CP Integration (P1, added 2026-09-18)

> **Epic slug:** `forks-pr-federation`

* Continuous tracking, synchronization, and governance of external open-source dependencies and upstream forks maintained in the estate (`wom7pr/` namespace: `omlx`, `headroom`, `orca`, `tart`, `tart-guest-agent`, `claude-obsidian`).
* Terminal automation via `just forks` and `just forks-check`, providing real-time branch divergence auditing, upstream/origin ahead-behind calculation, remote fetching, and safe fast-forward synchronization.
* Visual Developer Tools in w0m Control Panel (`apps/cp/src/pages/system/forks.astro` and `ForksManager.svelte`) allowing engineers to monitor fork health, inspect commit logs and branch diffs, trigger remote fetches, and review open upstream pull requests.
* **Key tickets:** [[T377]] (Refactor wom7open into wom7pr and build continuous fork synchronization verification tooling), [[T378]] (w0m User Control Panel: Developer Forks and Upstream PRs Management Tool), [[T369]] (Upstream PR health audits and visual reporting), [[T345]] (Upstream PR tracking).
* **Exit criterion:** `just forks-check` integrated into pre-push gates and CP Developer Forks & PRs interface operational in staging/production.
* **Type**: Tooling → Web. **Effort**: M. **Priority**: P1. **TASKS**: T377, T378, T369, T345.

## 38. Hero Epic (P1, added 2026-10-01)

> **Epic slug:** `hero-epic`

* One target, worked in a stated order: finish the member-facing area and the resume and profile work that is already most of the way built, and prove each piece live. Everything in it is already underway, so the epic adds no new scope; it gathers seven tickets that sat under four different epics (`session-followups`, `security-rbac-hardening`, `design-system-unification`, `profile-cv-studio`) so one plan can track them.
* **Stage 1, member area:** [[T493]] (move the personal and business features from the admin CP into the member profile), [[T476]] (`/me/account`: link a second Google account, verified live), [[T439]] (CP information architecture: one shell, context routes, one nav source, gates and golden baselines).
* **Stage 2, resume and profile:** [[T498]] (Resume Studio curated highlights: the owner steps), [[T499]] (highlights and tags in the database: Studio editing and the saved-variant live proof), [[T501]] (the `w0m-personnel` assistant: usage metering and quota live), [[T505]] (contact and identity record: KYC reads it, CURP and RFC move onto it).
* **Order is the owner's:** stage 1 before stage 2, and within a stage in the order listed. A step that only the owner can run (applying a migration, a live proof, a decision) is named in its ticket and does not stop the next buildable step.
* **Exit criterion:** all seven tickets at 100% of their own acceptance criteria, each live proof recorded in the ticket's status notes with the measured result. There is no single probe for this; each ticket closes on its own criteria, and a ticked box is a claim, not evidence.
* **Type**: Product → Web. **Effort**: L. **Priority**: P1. **TASKS**: T493, T476, T439, T498, T499, T501, T505.

## 39. Roots Epic (P0, added 2026-10-01)

> **Epic slug:** `roots-epic`

* The foundational platform, identity, tenancy, developer credential, repository governance, and test verification roots of the estate. Brings the core architecture into alignment with reality and closes open authz, isolation, and vacuous testing gaps.
* **Stage 1, identity, tenant isolation & active-hat closure:** [[T396]] (P0, client delivery readiness: active-hat validation live verification and audit closure), [[T458]] (P1, org and engagement model: finish S0-S5 live reconciliation, living docs, S6 engagements backfill after T468, relation-hat follow-up, S8/S9 split tickets), [[T461]] (P1, hat management in the CP: PM and root assignment, custom hats and mixes, collections with fallback rules).
* **Stage 2, developer profile & project governance isolation:** [[T366]] (P1, per-developer credential isolation: workspace-scoped routing for Infisical, Jam, Git, preventing host cross-contamination), [[T299]] (P1, replace role enum with base role plus per-service switches in clients-policy.json).
* **Stage 3, test & verification truth:** [[T237]] (P1, revalidate spec corpus against reality: eliminate candidate login stub, resolve the 4 triple-vacuous auth specs and 10 mute scenarios, point E2E harness to sandbox).
* **Order and dependencies:** Stage 1 first (T396 is immediate P0; T458 unblocks T461), Stage 2 second, Stage 3 third.
* **Exit criterion:** All six tickets verified against live code, authz probes green, zero host credential leakage, and spec corpus executing reliably against sandbox without vacuous passes.
* **Type**: Architecture → Platform. **Effort**: XL. **Priority**: P0. **TASKS**: T396, T458, T461, T366, T299, T237.

