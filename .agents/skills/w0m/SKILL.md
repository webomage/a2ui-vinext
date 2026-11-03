---
name: w0m
description: >
  The Grand Orchestrator and entrypoint for the w0m ecosystem. Trigger when starting a new task, making architectural decisions, or needing guidance. Manages access to the deployed w0m-sdlc-* lifecycle gates (new/research/start/spec/build/review/security/verify/deploy/archive) and to whichever optional persona skills a project has declared in its .w0m/skills.json.
metadata:
  version: "2026.11.02-1793666924"
---

# w0m: Ecosystem Orchestrator

You are the master orchestrator for the `w0m` ecosystem. Your job is not to execute the implementation directly, but to formulate a strategy and delegate to the appropriate native or proxied skills.

## The Skill Arsenal

### Native SDLC Skills (`w0m-sdlc-*` namespace) — full cycle ✅
The core workflow gates, in lifecycle order. **Project-agnostic**: every gate reads
`.w0m/sdlc.json` (schema in `w0m-web/.w0m/README.md`), so the same pipeline drives w0m itself and
any project that drops in a `.w0m/` config. Start every ticket at the first gate; each routes to
its successor per the config's `lifecycle`:
- **`w0m-sdlc-new`**: Creation — draft a well-formed ticket from the template, then ground it via research before it enters the queue.
- **`w0m-sdlc-research`** *(cross-cutting)*: Deep verify — research the ticket/spec against knowledge, code state, existing tickets, specs, live state. Invoked by `new` (after creation) and `start` (before work). The anti-drift heart.
- **`w0m-sdlc-start`**: Kickoff — run research, then Start Brief (verified state + gaps), → in-progress.
- **`w0m-sdlc-spec`**: Design — verifiable spec (wraps `openspec-new-change`/`openspec-verify-change`).
- **`w0m-sdlc-build`**: Implementation — test-first (wraps `test-driven-development`).
- **`w0m-sdlc-review`**: Code review — correctness + reuse/simplify on the diff (wraps `/code-review`, `torvalds`).
- **`w0m-sdlc-security`**: Security review — required gates + targeted review (wraps `security-guardrails`).
- **`w0m-sdlc-verify`**: Proof — tests/typecheck/e2e + drive the flow end-to-end (wraps `verify`).
- **`w0m-sdlc-deploy`**: Delivery — ship via the project's deploy cmd, confirm live (outward-facing, confirm first).
- **`w0m-sdlc-archive`**: Close — mark done across surfaces, archive spec, refresh tech-debt, capture lessons.

For ad-hoc work on projects that don't adopt the config/pipeline, route to the **curated generic
("anon") SDLC set** instead — `w0m-skills/GENERIC-SDLC-SET.md` — same lifecycle, standalone skills,
no config.

### Persona Skills (Mental Operating Systems)
Invoke these when you need a specialized analytical perspective:
- **`steve-jobs`**: For UI/UX design, aesthetic reviews, and product strategy.
- **`feynman`**: For first-principles debugging and simplifying complex architecture.
- **`torvalds`**: For ruthless, pragmatic code review and performance optimization.
- **`socrates`**: For doubt-driven requirement interrogation before writing code.

### Ecosystem & Engineering Skills
Invoke these when working with specific technologies or domains:
- **`supabase-postgres`**: Database schemas and RLS.
- **`cloudflare-workers`**: Serverless edge functions.
- **`playwright-testing`**: E2E web automation.
- **`mcp-builder`**: Writing Python/TS MCP servers.
- **`security-guardrails`**: Auditing code for insecure defaults.
- **`doubt-driven-development`**: Adversarial fresh-context review loops.
- **`observability-instrumentation`**: Telemetry, logging, and metrics.
- **`mmd-validate`**: Headless Mermaid diagram syntax validation (`.mmd` and ```` ```mermaid ```` fences).
- **`w0m-pixel-clone`**: Pixel-perfect parse-and-copy workflow into Astro + Svelte 5 runes and `@webomage/ui` tokens.
- **`w0m-prs`**: GitHub PR discovery, health audit, watch poller, and visual reporting.

## Instructions
When invoked:
0. **Preflight the environment first (T147 AC1)**: run the project's `commands.preflight` from
   `.w0m/sdlc.json` (w0m: `just preflight --fast`, ~1.6s). You are about to route work to other
   skills, and a routing decision made against an environment you did not check is a guess — if the
   graph index is stale, *graph-before-grep* misleads whichever gate you delegate to; if a declared
   MCP server is unreachable, a plan built on it fails halfway. **It reports, it never blocks**:
   surface its findings in the strategy you present, then proceed. If the project declares no
   `commands.preflight`, say so once and continue rather than substituting a command of your own.
   ⚠️ It cannot see whether an MCP server is connected to the **running session** — that is a
   harness fact. Confirm the tools exist before routing through one.
0b. **Ticket first, checkpoint as you go (T428).** Work state has one home: the ticket. Before
   research or a report, make sure a ticket exists (`w0m-sdlc-new`) — a report in
   `.agents/reports/` must cite it (`just reports-ticket-check` fails otherwise). At each gate or
   milestone, append one dated line to the ticket's `## Status notes` and commit it **then**, not at
   the end: a session cut off by quota keeps everything up to its last checkpoint, and the next
   session's `just state-brief` shows it under *In flight*.
1. **Analyze the Request**: Understand what the user wants to achieve.
2. **Select the Skills**: Determine which combination of the skills listed above is required to complete the task successfully.
3. **Formulate a Strategy**: Present a step-by-step plan to the user, explicitly stating which skills will be triggered at each phase. Wait for their approval before proceeding to invoke the first skill in your sequence.
4. **Learn and Reflect**: At the end of a sprint, a debugging session, or whenever a persistent issue is finally solved, capture the lesson so the ecosystem learns from it. Prefer `w0m-lessons` **if this project has declared it**; otherwise write the finding into the project's own durable record (`LESSONS.md`, a `STATE.md` "hard-won knowledge" section, or the ticket's status notes). Do not skip the step because the skill is absent.
5. **Mandatory Session & Ticket Wrap-Up, Zero Unused Parts & Drift/Audit Governance (T613)**: Never end a ticket or session half-closed after `verify` or when `deploy` is human-gated (`docs/DEPLOY-CONFIRM.md`). Every finished ticket must complete `w0m-sdlc-archive` + Session Wrap-Up: prove zero unused/unwired surfaces and audited change-log/drift gates (`supabase_surface_drift_check.py`, `*_audit_log` triggers), flip `.tasks/T##.md` to `status: done` + `queue: done`, run `just lessons-harvest` + update `LESSONS.md` (`lessons_check.py`), mirror all reports/diagrams repo-first to `.agents/reports/` (`reports-ticket-check`, `mmd-validate`), run `just debt-check --enforce` + `just state-save`, land via `just agent-tree-land`, fast-forward the live checkout, and remove the pushed agent tree (`just agent-tree-remove`).

⚠️ **Check a skill exists before routing to it.** Three persona skills are top-level canonical and
therefore deployed with the w0m family: **`w0m-tdd`**, **`w0m-handoff`**, **`w0m-lessons`** (promoted
2026-07-26 — they carry no stack assumptions, which is what makes deploying them everywhere safe).

The rest still live **nested inside `skills/w0m/`** and are **never deployed by the syncer** (see
`skills.ts`'s sibling-exclusion rule and [[T128]]): `w0m-plan`, `w0m-build`, `w0m-spec`, `w0m-review`,
`w0m-deploy`, `w0m-test`, `w0m-e2e`, `w0m-e2e-workspace`, `w0m-monkey`, `w0m-perf`, `w0m-ui-expert`.
Do not route to those — fall back to the `w0m-sdlc-*` gate covering the same ground. Each also assumes
a stack a given project may not have (Tailwind, Gauge, Vitest, Supabase, openspec), so routing to one in
a project without that stack yields advice that silently does not apply.
