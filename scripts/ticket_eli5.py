#!/usr/bin/env python3
"""T568 — `just eli5 T*`: plain-English one-paragraph ELI5 ticket explainer.

Usage examples:
  just eli5 T57                  # Single ticket (open or closed)
  just eli5 T57 T9 T37           # Multiple tickets
  just eli5 "T5*"                # Glob over ticket IDs (open by default; add --all for closed)
  just eli5 T*                   # All open tickets (recovers even when bash expands T* to TASKS.md TECH-DEBT.md)
  just eli5 --area ai            # Open tickets in a functional area
  just eli5 --priority P1        # Open P1 tickets
  just eli5 --status paused      # Paused tickets
  just eli5 T57 --json           # Structured JSON output
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import pathlib
import re
import sys

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import tasks_query as tq  # noqa: E402

# Curated plain-English ELI5 paragraphs for the open queue so every active ticket reads with
# everyday clarity and zero raw markdown clutter, while any newly filed or archived ticket
# falls through to the paragraph-aware plain-English synthesizer (`synthesize_eli5_paragraph`).
CURATED_ELI5: dict[str, str] = {
    "T9": (
        "Right now our chat logs often record 0 tokens for Cloudflare Workers AI calls, which is like having a car "
        "speedometer stuck at zero—you cannot enforce a budget if you cannot measure usage. This ticket pulls real AI "
        "neuron consumption from Cloudflare's GraphQL Analytics API, enforces daily spending and usage caps per user "
        "tier so no single visitor can run up the bill, and displays the real usage numbers on an Admin Control Panel card."
    ),
    "T10": (
        "Our Telegram webhook (`telegram-webhook/index.ts`) receives incoming bot messages, but still has an unfinished "
        "TODO instead of forwarding conversational questions to our AI consultant agent. This ticket wires the Telegram "
        "bot bridge to `agent-consultant` (`w0m-consultant`) and completes the remaining per-agent persona capabilities "
        "so users can chat with the consultant directly through Telegram."
    ),
    "T11": (
        "When a visitor in the public chat says 'Hi, my name is Alice and my budget is $10k, here is my email', a smaller "
        "LLM sometimes grabs only the required `email` field when calling `submit_service_request` and forgets to pass the "
        "optional `name`, `company`, `timeline`, or `budget` fields the visitor already volunteered. This ticket sharpens "
        "the tool schema descriptions and system prompt instructions (with unit/eval tests) so volunteered fields are never dropped."
    ),
    "T14": (
        "A parked Apple-Silicon-only spike in `wom7mlx` to compare two Rust machine-learning libraries (`mlx-rs` vs "
        "HuggingFace `candle`) for launching local Gemma models in Rust. Because the owner decided on 2026-08-08 that "
        "`omlx` (Python Apple MLX) is our production local LLM server and `Tart` is our Mac VM tool, this ticket stays "
        "parked at P3 under T184 unless custom Rust MLX work is explicitly revived."
    ),
    "T17": (
        "Months ago an old `.env.bak` backup file was accidentally committed and later deleted, meaning its contents still "
        "live inside old git history snapshots in `wom7web`. After rotating any affected credentials, this ticket runs "
        "`git filter-repo` during a scheduled quiet window to scrub `.env.bak` from every historical commit across all clones."
    ),
    "T28": (
        "Our domain `webomage.com` uses Google Workspace and Cloudflare Email Routing, and several workflows reference "
        "role addresses (`hello@`, `no-reply@`, `security@`). This ticket reconciles the live mailbox and routing inventory "
        "against code references and documents the exact setup for provisioning and testing `@webomage.com` addresses."
    ),
    "T37": (
        "Today our browser extension (`wom7ext`) calls Mistral or Gemini directly from the user's browser using client-side "
        "API keys in `llmService.ts`. This ticket moves the extension's cloud AI calls behind our own Cloudflare Worker "
        "`/ai/chat` proxy (matching T36's rule: Cloudflare primary, no third-party keys in client code), keeps the local "
        "on-device LLM option for strict privacy, and updates the extension's privacy docs to explain that cloud AI requests "
        "pass through our Worker."
    ),
    "T56": (
        "Our cross-repo dependency checker (`deps_sync.py`) currently only inspects root `package.json` files and leaves "
        "`@supabase/supabase-js` lagging on an older major version inside `wom7ext`. This ticket upgrades `deps_sync.py` "
        "to scan every workspace `package.json`, aligns `@supabase/supabase-js` across all repos, and assigns an explicit "
        "owner check for dependency currency."
    ),
    "T57": (
        "Instead of sending every AI prompt to the same expensive model, an 'Intent Router' acts like a hospital triage "
        "nurse: it inspects whether a prompt is routine/simple or complex, sends routine questions to fast, cheap Cloudflare "
        "Workers AI models (using `@cf/cloudflare/clef-flash` for low-latency classification), routes complex reasoning to "
        "flagship models (or Gemini 2.5 with context caching when the same context is reused), and logs every routing "
        "decision in `ai-router.ts` so we can measure blended cost savings."
    ),
    "T66": (
        "Indeed has no public API for updating a resume profile, so filling out `my.indeed.com/resume/edit/*` by hand is "
        "tedious. This ticket adds Indeed support to the `wom7ext` browser extension using our declarative `specEngine.ts` "
        "and `formFillerService.ts`: when you open your Indeed resume page, the extension popup shows 4 one-click helper "
        "buttons (Fill Summary, Fill Experience Bullet, Fill Skills, Fill Education) that pull canonical career data and "
        "type it cleanly into Indeed's React form fields."
    ),
    "T70": (
        "When the underlying Linux OS upgrades its C library (`glibc`), PostgreSQL warns that its text-sorting dictionary "
        "(`collation version`) was built on an older OS version, which can subtly affect text index ordering. This ticket "
        "runs and documents the safe PostgreSQL collation refresh procedure (`ALTER DATABASE ... REFRESH COLLATION VERSION` "
        "after reindexing) and verifies zero collation warnings remain."
    ),
    "T71": (
        "Several older architecture and runbook markdown files still mention retired services or tables that have already "
        "been decommissioned in code and migrations. This ticket sweeps the documentation corpus to remove or mark historical "
        "references to decommissioned components so agents and developers never mistake dead paths for live ones."
    ),
    "T76": (
        "Our `observability_map.md` claims to list every health check, log table, and alert across the estate, but some rows "
        "drifted from the actual code and cron jobs. This ticket cross-checks every row in `observability_map.md` against "
        "live edge functions, Worker crons, and database tables, fixing stale entries and adding a drift check."
    ),
    "T80": (
        "A few Control Panel Svelte islands still receive a raw Supabase `accessToken` prop from their parent `.astro` page "
        "and query Supabase directly from the browser instead of calling same-origin cookie-authenticated `/api/*` endpoints. "
        "This ticket finishes the F1 security migration so browser islands use `HttpOnly` session cookies via server routes "
        "and never hold raw JWTs in client-side props."
    ),
    "T82": (
        "A parked P3 ticket to rewrite a full Gemma 4 text+vision (`SigLIP`) model loader and transformer decoder from "
        "scratch in Rust inside `wom7mlx/wom7mlx` using `mlx-rs`. Like T14, it stays parked under T184 because `omlx` and "
        "`mlx-vlm` already serve Gemma 4 on macOS and Apple Metal (`mlx-rs`) does not run on Linux `x86_64` hosts."
    ),
    "T83": (
        "Since text/vision LLMs like Gemma 4 can read images but only output text, this parked P3 ticket proposes adding "
        "a local Apple Silicon image-generation server (like FLUX via `mflux`) behind an OpenAI-compatible "
        "`/v1/images/generations` endpoint when `USE_LOCAL_IMAGE_GEN=true`. Like T14 and T82, it is Apple-Silicon-specific "
        "and consolidated under T184."
    ),
    "T84": (
        "Our AST symbol index (`codegraph`) can fall behind when commits land across multiple member repositories without "
        "re-indexing, causing `just ask` to miss newly added functions. This ticket tightens cross-repo `codegraph` freshness "
        "checks and sync hooks so symbol lookups stay current across all 7 estate repos."
    ),
    "T88": (
        "Today, when our chat agent calls a tool, it only knows how to spit out a canned end-of-turn message "
        "(`submit_service_request`), and in streaming mode it drops tool calls if the model starts talking first "
        "(`ai-router.ts`). This ticket gives our agents a real multi-step 'think -> call tool -> read tool result -> "
        "stream natural-language answer' loop (`runAgentTurn` + `TOOL_REGISTRY`) that works identically in both streaming "
        "and buffered modes and sends live `tool_call` / `tool_result` status updates to the chat UI."
    ),
    "T106": (
        "Astro `.astro` files are currently formatted with Prettier because our fast Rust formatter (`oxfmt`) did not "
        "yet support `.astro` syntax cleanly when T106 first shipped. This watch ticket tracks upstream `oxfmt` `.astro` "
        "support so we can eventually retire the Prettier fallback and use `oxfmt` everywhere."
    ),
    "T109": (
        "We have hundreds of markdown specs, decisions, and architecture docs across the repo, but AI agents and our "
        "knowledge-base search (`public.documents`) only index a subset of them. This research ticket evaluates how best "
        "to chunk, embed, and expose the `.md` documentation corpus to RAG search and agent skills without leaking "
        "internal-only notes to public chat tiers."
    ),
    "T113": (
        "Different Cloudflare Workers and build scripts across the estate pin slightly different Cloudflare `compatibility_date` "
        "strings and Node.js versions, which can cause subtle runtime mismatches between local builds and deployed Workers. "
        "This ticket aligns all `wrangler.jsonc` `compatibility_date` values and Node build pins under a single governed check."
    ),
    "T128": (
        "The `wom7skills` repository holds our canonical agent skills and sync tooling, but its top-level architecture, "
        "propagation flow diagrams, and manifest schema docs need a clean revision after the recent estate skill expansions. "
        "This ticket updates `wom7skills` documentation, flow diagrams, and schema references to match the live registry."
    ),
    "T132": (
        "Building a UI replica from a reference screenshot or live web page by hand takes many visual tweak cycles. "
        "This ticket creates the `w0m-pixel-clone` skill: a guided workflow that inspects a visual source (URL or image), "
        "generates clean Astro/Svelte components using `@webomage/ui` tokens, and verifies visual fidelity with automated "
        "screenshot diffing."
    ),
    "T136": (
        "Many potential clients run slow, plugin-heavy legacy WordPress sites that they want modernized without losing "
        "SEO or content structure. This research ticket designs a repeatable client delivery offering and migration "
        "playbook for converting WordPress sites onto the fast `vinext` (Vite + React/Next-compatible) Cloudflare stack."
    ),
    "T143": (
        "Right now `wom7ext` has an old, untracked `extension-ff/` folder from an abandoned Manifest V2 Firefox experiment "
        "that rotted while the main `extension/` moved to Manifest V3. This ticket deletes the dead `extension-ff/` fork, "
        "records our target browsers (Chromium + Firefox MV3), and adds a single-source build target switch (`manifest.json` "
        "`background.scripts` vs `service_worker` + `browser.*` polyfill + `just` recipes) so one codebase builds cleanly "
        "for both Chrome and Firefox."
    ),
    "T152": (
        "A paused Apple-Silicon/OpenCode SDLC ticket to verify that every `wom7skills` command and OpenSpec workflow "
        "runs identically inside OpenCode as well as Claude Code, with small routine subtasks offloaded to a local Gemma 4 "
        "model via `omlx`."
    ),
    "T153": (
        "A paused runtime integration ticket to run `ZeroClaw` as a managed local agent backed by `omlx`, with tracked "
        "install configuration, bidirectional `w0m <-> zerocaw` task dispatch, and isolated sandboxed execution for "
        "client-project audits."
    ),
    "T164": (
        "Developers and agents rely on dozens of host CLI tools (`just`, `uv`, `pnpm`, `supabase`, `wrangler`, `infisical`, "
        "`gh`, `oxlint`), and a missing or outdated binary causes cryptic mid-task failures. This ticket inventories and "
        "governs the full host CLI surface in `stacks-policy.json` and surfaces toolchain health in `just preflight`."
    ),
    "T171": (
        "Before building a complex multi-VM fleet scheduler, we need to prove that a single batched Claude Code task can "
        "be dispatched into an isolated dev sandbox, run to completion, and return a verified git commit + test log. "
        "This ticket builds and proves that single-unit sandbox task runner first."
    ),
    "T179": (
        "A paused macOS/Apple-Silicon virtualization ticket to evaluate or wire a DevPod machine provider for `Tart` "
        "Linux guests while respecting macOS Virtualization.framework's 2-VM kernel limit."
    ),
    "T180": (
        "A paused macOS/Apple-Silicon ticket evaluating `Tart` macOS VMs as isolated sandboxes for autonomous coding "
        "agents (`T153`/`T171`), weighing snapshot speed against Apple's 2-concurrent-macOS-VM hardware ceiling."
    ),
    "T181": (
        "Alongside headless CLI sandboxes, some workflows need a full desktop GUI VM running Claude Desktop, Slack, and "
        "a browser inside a `Tart` guest. This ticket documents and scripts the GUI workstation VM image and decides "
        "whether the guest OS should be Linux or macOS given Apple's 2-VM macOS kernel cap."
    ),
    "T184": (
        "This is the master umbrella ticket (5/8 done) that recorded the owner's toolchain decision ('Tart = VMs, omlx = "
        "local LLM serving, custom Rust wom7mlx = optional P3') so that `wom7mlx`'s vendored `mlx-rs` build errors never "
        "block the rest of the estate. The remaining items record the exact revival trigger (`mistral.rs` vs custom "
        "`mlx-rs` bindings) and remove the 3-line `[patch.crates-io]` override in `wom7mlx/wom7mlx/Cargo.toml`."
    ),
    "T226": (
        "Two older advisory test suites still check hardcoded facts about external client folders (`bridgeroad`, etc.) "
        "that have changed since those tests were written. Per T302 (estate gates never depend on client workspaces), "
        "this ticket relocates client-specific checks into each client's own `-w0m` workspace and removes stale client "
        "assertions from estate suites."
    ),
    "T227": (
        "Running Astro dev server (`astro dev`) tests source files under Vite rather than the compiled Cloudflare Worker "
        "bundle that actually ships to production. This ticket adds a local built-artifact server recipe (`wrangler dev` "
        "over `dist/`) so verification gates can smoke-test the exact compiled Worker artifact locally."
    ),
    "T234": (
        "A paused tooling trial to evaluate `ai-memory` as a structured cross-session recall layer and measure how much "
        "of `MEMORY.md` auto-memory is duplicating facts that already belong in `LESSONS.md`, `CLAUDE.md`, or `.tasks/`."
    ),
    "T259": (
        "When someone deploys an individual Worker or edge function directly via `wrangler deploy` or `supabase functions deploy` "
        "instead of the estate release wrapper, the deployment never gets recorded in `public.deploy_log` or the release "
        "transcripts. This ticket closes the bypass so every deploy path records its version and commit in `deploy_log`."
    ),
    "T271": (
        "We already pay for Cloudflare (Workers, Pages, R2, D1/KV, Workers AI, DNS) and have access to many more Cloudflare "
        "capabilities on the free/included tiers (Queues, Images, Turnstile, Browser Rendering, Vectorize, Analytics Engine). "
        "This ticket surveys the remaining Cloudflare services against our real architecture needs, using free-tier limits "
        "as the primary decision filter."
    ),
    "T273": (
        "Cloudflare Workers can execute compiled Rust-to-WebAssembly (`WASM`) modules at near-native speed, provided the "
        "compiled `.wasm` binary stays within Cloudflare's Worker bundle size budget. This ticket establishes the build "
        "pipeline, size-budget gate, and first CPU-bound Rust->WASM utility module for our Cloudflare Workers."
    ),
    "T290": (
        "In the client portal, Stage 4 (Money / Invoicing) currently has a `simulate_payment` demo endpoint that lets a "
        "client mark their own invoice paid without real Stripe payment verification. This paused product/billing ticket "
        "replaces self-service payment simulation with real Stripe webhook reconciliation and admin-verified settlement."
    ),
    "T306": (
        "Instead of mixing personal and organization GitHub operations on two accounts, this ticket provisions dedicated "
        "`@webomage.com` work GitHub identities and updates our `gh` CLI profile switcher (`GH_CONFIG_DIR` isolation) "
        "so all 4 identities are governed and selectable without credential bleed."
    ),
    "T330": (
        "Over time a few stray top-level directories and files accumulated across repos (like legacy pre-migration `db/*.sql` "
        "files, duplicate skill folders, and scratch debug artifacts). This hygiene ticket audits each stray path, "
        "migrates anything still needed into its canonical location, and deletes the dead leftovers."
    ),
    "T343": (
        "Local developer machines accumulate tens of gigabytes of unused iOS/Android simulators, downloaded LLM weights, "
        "stopped VMs, and Docker layers across several separate scripts. This ticket unifies them under `just resources audit` "
        "and `just resources prune` (with a strict dry-run default) so disk space is governed in one place."
    ),
    "T347": (
        "When a client reports a bug (including Jam.dev video bug reports), the Control Panel needs to route it automatically "
        "to the project's assigned QA hat—or fall back to the Project Manager hat if no QA hat is assigned—and display "
        "the linked Jam recording right on the bug triage card."
    ),
    "T355": (
        "Ticket `epic:` fields currently mix prose strings like `ROADMAP §13.2 — skills platform` with slug names, making "
        "automated grouping fragile. This ticket migrates all tickets to canonical 3-level namespaced epic tags and enforces "
        "the format in `ticket-schema-check`."
    ),
    "T365": (
        "When launching a GUI sandbox browser for testing or clip capture, manually installing and configuring browser "
        "extensions every time is slow. This ticket provisions Chromium in our GUI sandbox with managed enterprise policies "
        "that pre-install Jam.dev, Obsidian Web Clipper, and the `wom7ext` extension automatically."
    ),
    "T368": (
        "A paused Apple-Silicon infrastructure research ticket evaluating Apple's native `apple/container` microVM framework "
        "(macOS 26), multi-container compose alternatives, and lightweight GUI management tools on Apple Silicon."
    ),
    "T383": (
        "Static analysis (`codegraph` + `knip`) identified orphaned TypeScript/Python modules and uncalled helper functions "
        "across the estate that no route, script, or test imports anymore. This cleanup ticket verifies each candidate is "
        "truly dead (not dynamically invoked) and removes the orphaned code."
    ),
    "T384": (
        "Inline linter/typechecker suppressions (`@ts-ignore`, `eslint-disable`, `# noqa`, `# nosec`) can hide real bugs "
        "or security regressions if left unchecked. This ticket removes any scripts that programmatically insert suppressions, "
        "fixes the underlying type/lint issues where possible, and locks the remaining justified exceptions behind a ratchet gate."
    ),
    "T387": (
        "Our GitHub Actions CI workflows experienced runner startup and secret/config drift while local pre-push gates became "
        "the primary verification path. This ticket restores clean remote GitHub Actions CI execution so remote runs match "
        "our local pre-push verification gates."
    ),
    "T400": (
        "Our background Cloudflare Workflows in `wom7func` (crawlers, enrichment, digests) need explicit per-step retry "
        "policies, Dead-Letter Queue (DLQ) capture when a workflow exhausts its retries, and structured health logging "
        "into `public.automation_runs` so failed background jobs never vanish silently."
    ),
    "T433": (
        "To welcome responsible security researchers safely, this ticket establishes `w0m`'s public vulnerability disclosure "
        "posture (`/.well-known/security.txt`, safe-harbor policy in `diodb` format) and defines a strictly human-gated "
        "workflow for any outbound bug-bounty research pilot."
    ),
    "T434": (
        "Dozens of places in `w0m` ask simple 'yes/no', 'pick 1 of N', or 'score 1-5' questions (like classifying whether "
        "a ticket is a `bug`, `feature`, or `task` in `type_backfill.py`, or scoring resumes and leads), and currently "
        "answer them with fragile regexes or slow chat LLMs. This ticket standardizes those bounded decisions on the "
        "System One protocol—wired to native Cloudflare Workers AI `@cf/cloudflare/clef-flash` (9B, ~39ms) and "
        "`@cf/cloudflare/clef` (27B) in `system-one.ts`—benchmarks it on our held-out ticket classification dataset, and "
        "enforces that hooks report `UNMEASURABLE` rather than silently falling back when a decision model is offline."
    ),
    "T454": (
        "Admin accounts already require two-factor authentication (TOTP/WebAuthn AAL2), but regular member and client "
        "accounts who voluntarily enroll a 2FA factor aren't prompted for their second factor during normal sign-in across "
        "all apps. This ticket wires the MFA challenge step into every app's login flow whenever a user has an enrolled factor."
    ),
    "T459": (
        "When an individual signs up, they get a personal organization; later, they may join or create a company organization "
        "and need their existing consulting/training engagements transferred over cleanly. This research ticket designs the "
        "safe database merge/transfer flow so engagements, invoices, and audit trails move without orphaning records."
    ),
    "T460": (
        "Today a training engagement links to a single organization, which makes it awkward when a cohort training class "
        "includes trainees from several different personal or company orgs. This research ticket designs the schema and "
        "access-control model for multi-trainee group training engagements."
    ),
    "T462": (
        "Our public sales chatbot (`agent-consultant`) searches our knowledge base (`public.documents` via `pgvector`) "
        "before answering, but our signed-in Technical Architect agent (`agent-architect`) currently answers from memory "
        "('zero-shot') without reading our stored architecture blueprints or diagrams. This research ticket measures what "
        "`agent-architect` actually reads today, checks our privacy rules (`KB-INDEX.md`—never leak private client data "
        "into public tiers), and delivers a weighted decision on how to connect Architect Mode to our indexed blueprints."
    ),
    "T475": (
        "High-trust identity verification (`@wom/kyc` and compliance profiles) needs a hardware-backed biometric anchor "
        "(like WebAuthn platform passkeys / Touch ID / fingerprint FIDO2 attestation) so sensitive compliance sign-offs "
        "are cryptographically tied to a verified physical device."
    ),
    "T479": (
        "Some Control Panel Astro pages still pass the user's Supabase `access_token` into client-side Svelte islands "
        "so the browser can call Supabase or edge functions directly. This ticket replaces those client-side token props "
        "with same-origin `/api/*` proxy routes that read the `HttpOnly` session cookie on the server."
    ),
    "T480": (
        "Our browser end-to-end Gauge test suite (`just test-e2e`) is slow when specs wait on full timeouts for known-bad "
        "states or run strictly one file at a time. This ticket replaces fixed sleeps/dead waits with fast readiness assertions "
        "and enables safe parallel Gauge spec execution."
    ),
    "T486": (
        "Several older Gauge browser specs under `specs/admin/` and `specs/web/` still assert old button labels or page "
        "layouts from before recent Control Panel redesigns. This ticket audits every stale Gauge spec against the current "
        "UI, updating live flows and retiring obsolete specs with a recorded reason."
    ),
    "T487": (
        "Visual golden screenshot comparisons can fail with tiny font-rendering or anti-aliasing differences when generated "
        "on one OS/machine and checked on another. This ticket either regenerates the visual goldens against the current UI "
        "in a pinned deterministic container/browser environment or standardizes the local render baseline."
    ),
    "T490": (
        "The Control Panel can broadcast remote commands (`extension_commands` over Supabase Realtime) to the browser "
        "extension, but `background.ts` currently only subscribes when `EXT_MODE === 'local'` (pointing at `127.0.0.1:54321` "
        "with a fake user)—meaning production (`normal`) extension builds never listen at all. This ticket wires normal-mode "
        "extension builds to subscribe to the private `extension_commands` channel using the signed-in admin's real Supabase "
        "session, validates incoming `RUN_SPEC` payloads against an allowlist, and stops retrying with a clear status if a "
        "non-admin session is refused by RLS."
    ),
    "T491": (
        "The `wom7func` repository actually holds our Cloudflare Workers, Workflows, and cron dispatchers rather than "
        "generic functions, and the owner decided in AgDR-0012 / T567 to rename it to `w0m-cf` as part of the unified "
        "`w0m-*` estate rebrand verified by `just name-refs --gate`."
    ),
    "T500": (
        "Right now the names for our AI agents and our AI model aliases collide and confuse readers—for example, the edge "
        "function is called `agent-architect`, its database persona points to a model alias named `w0m-architect`, and the "
        "admin agent function is named `chat-internal`. This ticket performs one clean, estate-wide rename so every agent "
        "persona and edge function is `w0m-<role>` (`w0m-architect`, `w0m-consultant`, `w0m-admin`) and every model alias "
        "in `ai_models` is `w0m-llm-<role>` (`w0m-llm-architect`, `w0m-llm-consultant`, `w0m-llm-admin`)."
    ),
    "T504": (
        "Historical `.dev.vars` files committed in May 2026 contained credentials that needed rotation after Google flagged "
        "an old Gemini API key as leaked. The tooling (`just secret-history-check` and `just secret-flow-check --vault`) "
        "is built; this paused P0 ticket tracks the owner-only credential rotations in external provider dashboards and "
        "final git history purge."
    ),
    "T508": (
        "Our skills catalog UI currently reads metadata from only 25 of our 143 governed skill entries and misses skills "
        "defined in `k7` surfaces. This ticket updates the skills catalog indexer so 100% of governed skills across `w0m` "
        "and `k7` are measured, indexed, and displayed with accurate provenance."
    ),
    "T509": (
        "When governance scripts moved to the `@wom` workspace root (T414/T419), cross-repo relative symlinks like "
        "`wom7web/justfile -> ../wom7api/justfile` were left behind as transitional bridges. This ticket finishes the "
        "root-first layout migration in staged units behind a stale-path probe that verifies every path referenced by a "
        "recipe, hook, or profile actually exists."
    ),
    "T512": (
        "Syncing agent skills currently requires separate steps across `wom7skills`, `@wom` root, `wom7web`, and `wom7api`. "
        "This ticket unifies skill propagation so a single command syncs and relocks every consumer across the estate, "
        "backed by one drift gate covering all repos."
    ),
    "T516": (
        "Twelve useful standalone scripts in `scripts/` (Group A from the script triage audit) lack a standard CLI contract. "
        "This ticket promotes those 12 scripts into first-class estate tools by giving each one a root `just` recipe, "
        "`--help` support, an automated unit test, and a `test-suites.json` registry entry."
    ),
    "T517": (
        "Nine small helper scripts (Group B from the script triage audit) duplicate checks that already belong inside "
        "existing tools like `authz-probe`, `zeroclaw` health, and `preflight`. This ticket folds those 9 scripts into "
        "their parent tools and deletes the standalone files."
    ),
    "T518": (
        "Seven scripts (Group C from the script triage audit—covering the news pipeline, tracks, crawler smoke test, "
        "internal-docs indexing, and Upwork backfill) depend on product direction before being promoted or retired. "
        "This ticket presents a weighted decision for each of the 7 scripts so they can be cleanly promoted or removed."
    ),
    "T519": (
        "Eight obsolete scripts (Group D from the script triage audit—one fake health check, four finished one-shot "
        "migrations, and three scripts whose input files no longer exist) are dead weight. This ticket verifies zero live "
        "callers remain and deletes all 8 dead scripts."
    ),
    "T521": (
        "Our Mermaid diagram validator (`mmd-validate`) currently has hardcoded `@wom` workspace paths, preventing client "
        "`-w0m` workspaces from installing it cleanly as a portable skill tool. This paused ticket removes the hardcoded "
        "paths and packages `mmd-validate` as a portable skill in `wom7skills`."
    ),
    "T522": (
        "Twenty-three user-scope skills in `~/.claude/skills` / `~/.agents/skills` load into every agent session without "
        "a lockfile or provenance check. This ticket inventories those user-scope skills, brings the keepers into governed "
        "manifest/lock tracking, and prunes the unverified ones."
    ),
    "T523": (
        "During golden browser test runs, missing seed images under `/cdn/news` and `/cdn/post-images` trigger hundreds of "
        "HTTP 404/503 console errors while the test suite still exits green, and the log auditor misclassifies harmless "
        "warnings. This ticket fixes the broken image asset paths/fallbacks and sharpens the golden run browser-error gate."
    ),
    "T524": (
        "By default in Supabase/PostgreSQL, newly created tables and functions in the `public` schema receive broad default "
        "grants (`anon`/`authenticated`) unless explicitly revoked via `ALTER DEFAULT PRIVILEGES`. This research ticket "
        "audits safe-by-default privilege lockdown in our migrations and prepares an upstream Supabase RFC/proposal."
    ),
    "T526": (
        "Today, clicking 'Sync Upwork' in the Control Panel tries to run a local Python script (`upwork_mcp_sync.py`) tied "
        "to a single laptop session, which always fails on deployed Cloudflare Workers. This ticket makes Upwork sync run "
        "per-member on the server using each member's own encrypted OAuth connection in `public.connections`—and is "
        "currently paused (`backlog-platform`) waiting on T537's Upwork-side OAuth redirect URI and ToS resolution."
    ),
    "T537": (
        "This is the server-side per-member Upwork MCP (`https://mcp.upwork.com/mcp`) connector that replaces the "
        "deprecated legacy Upwork GraphQL poller, with a strict read-only tool allowlist (AC3, already built and "
        "mutation-tested). Because Upwork's Dynamic Client Registration currently rejects non-localhost `https://` "
        "redirect URIs (`HTTP 400 invalid_redirect_uri`) and requires Upwork Support ToS confirmation for hosted server "
        "storage, this ticket stays paused (`backlog-platform`) until Upwork-side OAuth is ready."
    ),
    "T547": (
        "Our `just credential-probe` security gate flags `apps/cp/src/pages/api/profile/services.ts` because its filename "
        "matches the credential-surface path regex and it exports a `POST` handler, even though the route only saves public "
        "social/service handles (not secret tokens). This ticket verifies the route stores zero secrets, updates the probe's "
        "explicit exclusion list with a mutation test that real `admin/credentials` POST routes still fail, and turns "
        "`credential-probe` green."
    ),
    "T565": (
        "To pay down technical debt D38 (historical closed tickets without an OpenSpec link), this ticket classifies "
        "legitimately exempt closed tickets using `.w0m/sdlc.json -> spec_policy.exempt_classes` (`spec_exempt: <class>`) "
        "and authors validated retroactive OpenSpec specs for the remaining non-exempt feature/contract tickets."
    ),
    "T567": (
        "Per owner decision AgDR-0012, this ticket executes the 4-stage estate rebrand from personal `casualuser/wom7*` "
        "and `k7*` names to our unified GitHub organization taxonomy `github.com/webomage/w0m-*` (`w0m-web`, `w0m-api`, "
        "`w0m-cf`, `w0m-ext`, `w0m-sec`, `w0m-skills`, `w0m-mlx`), keeping deployed Cloudflare Worker script names and "
        "PostgreSQL identifiers stable."
    ),
    "T568": (
        "Looking up what a batch of tickets actually means in plain English used to require opening each `.tasks/T##.md` "
        "file and reading past YAML frontmatter, tables, and internal acronyms. This ticket adds `just eli5` (`scripts/ticket_eli5.py`) "
        "so passing any ticket ID (`T57`), wildcard (`T5*`, `T*`), or filter (`--area ai`) prints a single plain-English "
        "ELI5 paragraph per ticket, even when bash expands unquoted `T*` in the workspace root."
    ),
}

JARGON_GLOSSARY: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bRLS\b"), "RLS (row-level database security)"),
    (re.compile(r"\bAAL2\b"), "AAL2 (two-factor verified session)"),
    (re.compile(r"\bSSOT\b"), "SSOT (single source of truth)"),
    (re.compile(r"\bDORA\b"), "DORA (delivery speed & stability metrics)"),
]


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :]
    return text


def _extract_section(body: str, headings: tuple[str, ...]) -> str:
    for h in headings:
        m = re.search(
            rf"^##+\s+{re.escape(h)}\b[^\n]*\n(.*?)(?=\n##+\s+|\Z)",
            body,
            flags=re.I | re.S | re.M,
        )
        if m and m.group(1).strip():
            return m.group(1).strip()
    return ""


def _clean_prose_paragraphs(raw: str) -> list[str]:
    """Strip fenced code blocks, HTML comments, and markdown tables, joining wrapped lines into clean paragraphs."""
    cleaned = re.sub(r"```.*?```", "\n\n", raw, flags=re.S)
    cleaned = re.sub(r"<!--.*?-->", " ", cleaned, flags=re.S)
    blocks: list[list[str]] = []
    cur: list[str] = []
    for line in cleaned.splitlines():
        s = line.strip()
        if not s or s.startswith("|") or s.startswith("#") or re.match(r"^[-=:]{3,}$", s):
            if cur:
                blocks.append(cur)
                cur = []
            continue
        is_bullet = bool(re.match(r"^(?:[-*+]|\d+\.)\s+", s))
        s = re.sub(r"^[-*+]\s*(\[[ xX~N]\]\s*)?", "", s)
        s = re.sub(r"^\d+\.\s+", "", s)
        s = re.sub(r"\[\[([^\]]+)\]\]", r"\1", s)
        s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
        s = re.sub(r"\s+", " ", s).strip()
        if not s:
            continue
        if is_bullet and cur:
            blocks.append(cur)
            cur = [s]
        else:
            cur.append(s)
    if cur:
        blocks.append(cur)

    paragraphs: list[str] = []
    for b in blocks:
        joined = " ".join(b).strip()
        if len(joined) >= 20:
            if joined[-1] not in ".!?":
                joined += "."
            paragraphs.append(joined)
    return paragraphs


def _first_ac_summaries(body: str, limit: int = 3) -> list[str]:
    ac_sec = _extract_section(body, ("Acceptance criteria", "Acceptance Criteria"))
    if not ac_sec:
        return []
    items: list[str] = []
    for line in ac_sec.splitlines():
        m = re.match(r"^\s*-\s*\[[ xX~N]\]\s*(.+)$", line)
        if not m:
            continue
        item = m.group(1).strip()
        item = re.sub(r"^\*\*AC\d+\s*(?:[—–:-]\s*)?([^*]*)\*\*:?\s*", r"\1: ", item)
        item = re.sub(r"^\*\*([^*]+)\*\*:?\s*", r"\1: ", item)
        item = re.sub(r"\[\[([^\]]+)\]\]", r"\1", item)
        item = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", item)
        item = re.sub(r"\s+", " ", item).strip(" :.-")
        if item:
            items.append(item)
        if len(items) >= limit:
            break
    return items


def synthesize_eli5_paragraph(ticket: dict, ticket_path: pathlib.Path | None = None) -> str:
    """Return a single cohesive plain-English ELI5 paragraph for `ticket`."""
    tid = ticket["id"]
    path = ticket_path or (tq.TICKETS / f"{tid}.md")
    raw = ""
    fm: dict = {}
    if path.is_file():
        raw = path.read_text(encoding="utf-8", errors="replace")
        fm = tq.frontmatter(path)

    # 1. Explicit frontmatter `eli5:` override
    if fm.get("eli5"):
        return re.sub(r"\s+", " ", str(fm["eli5"])).strip()

    body = _strip_frontmatter(raw)

    # 2. Explicit `## ELI5` markdown section override
    eli5_sec = _extract_section(body, ("ELI5", "Explain Like I'm 5", "Plain English"))
    if eli5_sec:
        paras = _clean_prose_paragraphs(eli5_sec)
        if paras:
            return " ".join(paras)

    # 3. Curated high-signal explanation
    if tid in CURATED_ELI5:
        base = CURATED_ELI5[tid]
    else:
        # 4. Deterministic plain-English synthesis from Summary / Context / Why + ACs
        summary_sec = _extract_section(
            body,
            ("Summary", "Problem", "Why", "Context", "Background", "Goal", "Objective", "Decision", "Findings"),
        )
        paras = _clean_prose_paragraphs(summary_sec) if summary_sec else _clean_prose_paragraphs(body)
        lead = ""
        for p in paras:
            if len(p) + len(lead) <= 420:
                lead = f"{lead} {p}".strip() if lead else p
            elif not lead:
                lead = p[:417].rstrip() + "..."
            if len(lead) >= 180:
                break

        if not lead:
            title = ticket.get("title", "").strip().rstrip(".")
            lead = f"This ticket addresses `{title}`."

        ac_items = _first_ac_summaries(body, limit=3)
        if ac_items:
            ac_clause = "; ".join(ac_items[:3])
            base = f"{lead} Concretely, it delivers: {ac_clause}."
        else:
            base = lead

        for pattern, replacement in JARGON_GLOSSARY:
            base = pattern.sub(replacement, base, count=1)

    d, tot = tq.ac_progress(tid)
    blks = ticket.get("blockers") or {"declared": [], "inferred": []}
    open_blockers = sorted(set((blks.get("declared") or []) + (blks.get("inferred") or [])))
    status = ticket.get("status", "queued")

    state_notes: list[str] = []
    if tot > 0:
        state_notes.append(f"{d}/{tot} ACs complete")
    if status == "paused":
        q = fm.get("queue") or ticket.get("queue") or "paused"
        state_notes.append(f"currently paused ({q})")
    elif status == "done":
        state_notes.append("completed")
    if open_blockers:
        state_notes.append(f"waiting on {', '.join(open_blockers)}")

    paragraph = re.sub(r"\s+", " ", base).strip()
    if state_notes:
        paragraph = f"{paragraph} (Status: {' · '.join(state_notes)}.)"
    return paragraph


def _is_shell_expanded_root_t_files(selectors: list[str]) -> bool:
    """Detect when unquoted `just eli5 T*` in `@wom` or `wom7web` was expanded by bash into
    root filenames starting with `T` (e.g. `TASKS.md`, `TECH-DEBT.md`).
    """
    if not selectors:
        return False
    known_non_tickets = {"tasks.md", "tech-debt.md", "todo.md", "testing.md"}
    for s in selectors:
        name = pathlib.Path(s).name.lower()
        if name in known_non_tickets:
            continue
        if pathlib.Path(s).exists() and not re.fullmatch(r"T\d+[a-z]?(?:\.md)?", pathlib.Path(s).name, re.I):
            continue
        return False
    return True


def normalize_selectors(raw_selectors: list[str]) -> list[str]:
    """Normalize CLI selector arguments into ticket IDs or glob patterns."""
    if not raw_selectors or _is_shell_expanded_root_t_files(raw_selectors):
        return ["T*"]
    out: list[str] = []
    for raw in raw_selectors:
        for part in raw.split(","):
            tok = part.strip()
            if not tok:
                continue
            if tok.endswith(".md") and re.match(r"(?:.*/)?T\d+[a-z]?\.md$", tok, re.I):
                tok = pathlib.Path(tok).stem.upper()
            elif re.fullmatch(r"\d+[a-z]?", tok, re.I):
                tok = f"T{tok.upper()}"
            elif re.fullmatch(r"t\d+[a-z*?\[]*", tok, re.I):
                tok = "T" + tok[1:]
            out.append(tok)
    return out or ["T*"]


def select_tickets(
    tickets: list[dict],
    selectors: list[str],
    *,
    area: str | None = None,
    priority: str | None = None,
    status: str | None = None,
    include_all: bool = False,
) -> tuple[list[dict], list[str]]:
    """Return `(matched_tickets, unknown_selectors)`."""
    by_id = {t["id"].upper(): t for t in tickets}
    norm = normalize_selectors(selectors)

    explicit_exact = all(not any(ch in s for ch in "*?[") for s in norm)
    matched_ids: list[str] = []
    seen: set[str] = set()
    unknown: list[str] = []

    if explicit_exact:
        for s in norm:
            key = s.upper()
            if key in by_id:
                if key not in seen:
                    seen.add(key)
                    matched_ids.append(key)
            else:
                unknown.append(s)
        matched = [by_id[k] for k in matched_ids]
    else:
        pool = tickets if (include_all or status == "done") else [t for t in tickets if t.get("open")]
        for t in pool:
            tid = t["id"].upper()
            if any(fnmatch.fnmatchcase(tid, pat.upper()) for pat in norm):
                if tid not in seen:
                    seen.add(tid)
                    matched_ids.append(tid)
        matched = [by_id[k] for k in matched_ids]
        matched.sort(key=lambda t: tq.num(t["id"]))

    if area:
        matched = [t for t in matched if (t.get("area") or "").lower() == area.lower()]
    if priority:
        matched = [t for t in matched if (t.get("priority") or "").upper() == priority.upper()]
    if status:
        matched = [t for t in matched if (t.get("status") or "").lower() == status.lower()]

    return matched, unknown


def format_ticket_eli5(ticket: dict) -> str:
    tid = ticket["id"]
    d, tot = tq.ac_progress(tid)
    ac_str = f"{d}/{tot} ACs" if tot else "no ACs"
    prio = ticket.get("priority") or "—"
    status = ticket.get("status") or "queued"
    area = ticket.get("area") or "unassigned"
    title = ticket.get("title") or ""
    link = tq._ticket_link(ticket)
    para = synthesize_eli5_paragraph(ticket)
    return f"### {link} (`{prio}`, `{status}`, `area={area}`, `{ac_str}`) — {title}\n{para}\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="just eli5",
        description="Plain-English one-paragraph ELI5 explainer for w0m tickets (T568).",
    )
    ap.add_argument(
        "selectors",
        nargs="*",
        help="Ticket ID(s) or glob pattern(s): e.g. T57, 'T5*', T*, or 57",
    )
    ap.add_argument("--area", help="Filter by ticket area (e.g. ai, product, security, tools, sdlc, infra)")
    ap.add_argument("--priority", help="Filter by priority (P0, P1, P2, P3)")
    ap.add_argument("--status", help="Filter by status (queued, in-progress, blocked, paused, done)")
    ap.add_argument("--all", action="store_true", help="Include closed/done tickets when matching wildcards")
    ap.add_argument("--json", action="store_true", help="Emit JSON array of {id, title, priority, status, area, ac_done, ac_total, eli5}")
    args = ap.parse_args(argv)

    tickets = tq.load()
    matched, unknown = select_tickets(
        tickets,
        args.selectors,
        area=args.area,
        priority=args.priority,
        status=args.status,
        include_all=args.all,
    )

    if unknown:
        print(f"❌ Unknown ticket(s): {', '.join(unknown)}", file=sys.stderr)
        return 1

    if not matched:
        print("ℹ️  No tickets matched the given selector/filter.", file=sys.stderr)
        return 1

    if args.json:
        payload = []
        for t in matched:
            d, tot = tq.ac_progress(t["id"])
            payload.append(
                {
                    "id": t["id"],
                    "title": t.get("title", ""),
                    "priority": t.get("priority") or "",
                    "status": t.get("status") or "",
                    "area": t.get("area") or "",
                    "ac_done": d,
                    "ac_total": tot,
                    "eli5": synthesize_eli5_paragraph(t),
                }
            )
        print(json.dumps(payload, indent=2))
        return 0

    print(f"▶ ELI5 — {len(matched)} ticket(s)\n")
    for t in matched:
        tq.emit(format_ticket_eli5(t))
    return 0


if __name__ == "__main__":
    sys.exit(main())
