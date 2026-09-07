---
name: fact-checker
description: Enforce rigorous verification of facts in code, architecture, or live deployments against docs, specs, Gauge user stories, and current codebase state. Use this skill whenever checking if an implementation aligns with specifications, verifying architectural claims, or testing live system behavior.
metadata:
  version: "2026.08.10-1786372074"
---

# Fact Checker Skill

This skill instills an adversarial, Torvalds-esque rigor when making assumptions about the `wom7` ecosystem architecture or implementation details. It forces agents to check the source of truth—whether that's documentation, OpenSpec specifications, Gauge tests, live endpoints, or codebase state—before writing code or accepting premises.

## When to use this skill
- Verifying if a deployed feature or local code actually matches the requirements in OpenSpec or Gauge user stories.
- The user requests modifications to systems known to be deprecated (e.g., `openclaw`, `wom7unit`, `wom7workers`, `wom7swarm`, `wom7md`, LiteLLM). ⚠️ **The authoritative list is the workspace-root `DECOMMISSIONED.md`** — check it rather than this sentence, which is a sample and will lag. It records `packages/openclaw` + `UpworkPollerWorkflow` (2026-07-20), `wom7swarm` (2026-07-11) and `wom7md` (2026-08-08). 🔴 That file lives at the workspace root, which is not a git repo, so it is unversioned — see debt row D15.
- You are unsure if a package belongs in Supabase Edge Functions or Cloudflare Workers.
- The user makes an architectural claim that contradicts your current context or seems out of date.
- You need to validate that a live deployment is behaving as documented.

## Core Directives

1. **Check the Docs & Specs First**: Before accepting a user's premise, ALWAYS consult the relevant sources of truth:
   - **Architecture**: `docs/ECOSYSTEM.md` and `docs/ARCHITECTURE.md`.
   - **Rules**: `AGENTS.md` (for agent-specific rules, deprecated repos, and porting policies).
   - **Capabilities & Specs**: OpenSpec files in `openspec/specs/` (e.g., `observability_map.md`).
   - **Tests & User Stories**: Gauge specification files (`.spec`) in `tests/` or `openspec/`.

2. **Revalidate Code State**: Use `grep_search` to verify if the actual codebase reflects the documentation. Documentation can drift from reality; the code is the ultimate truth for *what is*, while specs are the truth for *what should be*.

3. **Revalidate Live Deployments**: When verifying live endpoints or production behavior, use the `run_command` tool to execute `curl` requests or test scripts against the live API, or use Playwright tools to verify UI behavior.

4. **Reject False Premises**: If the user asks to write code in a deprecated repository (like `wom7unit`), you MUST refuse and inform them of the current active system (e.g., `wom7web/apps/join` or `wom7cfworkers`). ⚠️ **A repo name not resolving on disk is not evidence it is deprecated, and the reverse is also true** — the live estate is the seven repos declared in `wom7web/.w0m/sdlc.json → repos`. Read that and `DECOMMISSIONED.md`; do not infer either way from a failed `ls`.

## Fact Revalidation Protocol
When triggered to revalidate a fact, follow these exact steps:

1. **Identify the Claim**: What is the fact that needs verifying? (e.g., "The API returns X", "Service Y is deprecated", "Feature Z is in OpenSpec").
2. **Consult Architecture Documentation**:
   - Check `docs/ECOSYSTEM.md` and `docs/ecosystem.mmd` to see if the service/API exists and how it connects.
   - Check `docs/ARCHITECTURE.md` for high-level system descriptions.
3. **Cross-Reference Specifications**:
   - Use `grep_search` to find matching Gauge `.spec` files (e.g., `tests/` or `openspec/`) to verify what is actually tested for requirements.
   - Consult relevant `openspec/specs/*.md` files.
4. **Revalidate Code State**:
   - Use `grep_search` to verify if the actual codebase reflects the documentation. Code is the ultimate truth for *what is*.
5. **Revalidate Live Deployment**:
   - For live endpoints or production behavior, use `run_command` to execute `curl` requests or test scripts against the live API, or use `webapp-testing`/Playwright tools for UI.
6. **Synthesize & Correct**:
   - If the codebase, live deployment, specs, and architecture documents are misaligned, point out the discrepancy.
   - If the user's request contradicts the established facts, forcefully correct them using evidence from your revalidation, and propose an updated plan.
