---
name: fact-checker
description: Enforce rigorous verification of facts in code, architecture, specs, or live deployments against docs, OpenSpec specifications, Gauge user stories, SQL migrations, and current codebase state. Use this skill whenever checking if an implementation aligns with specifications, verifying architectural claims, auditing completed tickets/specs (`just reality-verify`), or testing live system behavior.
metadata:
  version: "2026.11.02-1793677165"
---

# Fact Checker Skill

This skill instills adversarial, evidence-first rigor when making or evaluating claims about the
`w0m` ecosystem architecture, completed tickets, OpenSpec specifications, or live deployments.
Never accept prose claims without cross-checking the 5 surfaces: **Docs vs Specs vs Code vs Tests vs
Live Infra / Release Manifests**.

## When to use this skill
- Verifying whether local code or a deployed service matches `w0m-web/openspec/specs/` or Gauge `.spec` files.
- Auditing completed tickets and canonical specs against current repository state (`just reality-verify` / `just ticket-audit T##`).
- Checking whether a referenced repository, script, table, or component was renamed or retired.
  ⚠️ **Authoritative sources are `@wom/.w0m/sdlc.json -> repos`, `AGENTS.md` (Canonical Script & Policy Locations), and `w0m-web/DECOMMISSIONED.md`** — read them directly rather than guessing legacy `wom7*` or moved `w0m-web/project/` paths.
- Validating whether a `status: done` change is actually live in production (`releases/*.json` `deployed (<version>)`) vs `landed_pending_deploy` awaiting owner Touch ID `just deploy-all` / `just db-migrate`.

## Core Directives

1. **Check Canonical Sources of Truth First**:
   - **Estate Conventions & Canonical Paths**: `AGENTS.md`, `CLAUDE.md`, and `@wom/.w0m/sdlc.json`.
   - **Architecture & Decisions**: `docs/ECOSYSTEM.md`, `docs/ARCHITECTURE.md`, and `docs/DECISIONS.md` (`just decisions`).
   - **Capabilities & Specs**: `w0m-web/openspec/specs/` and `just spec-drift` (`scripts/spec_drift_gate.py`).
   - **Database Schema**: `w0m-api/supabase/baseline/schema.sql`, `w0m-api/supabase/migrations/`, and `python3 w0m-web/project/scripts/supabase_surface_drift_check.py`.
   - **Tests & Suites**: `w0m-web/project/test-suites.json` and `w0m-web/specs/` (Gauge).

2. **Revalidate Code State Using Estate Graph & Search Tools**:
   - Run `just ask "<symbols>"` first for symbol/call-path lookup across all repos, and `just search "<pattern>"` for multi-repo text search (never a bare grep at `@wom` root, whose `.gitignore` excludes member repos).
   - Run `just reality-verify` (`python3 scripts/ticket_audit.py --completed --specs --strict --offline`) to catch nonexistent paths, missing exported symbols, retired `wom7*` prefixes, and nonexistent `public.<relation>` SQL references.
   - Code is the truth for *what is*; specs are the truth for *what should be*.

3. **Distinguish Landed Code from Deployed Production**:
   - Compare commit ancestry against `releases/*.json` (`just ticket-audit T## --offline`) and, when verifying live behavior, inspect live endpoints/health probes rather than inferring deployment from `status: done`.

4. **Reject False Premises & Silent Fallbacks (`AgDR-0025`)**:
   - If a request targets a retired repository (`wom7*`, `openclaw`, `wom7swarm`) or a shadow symlink path (`w0m-web/TASKS.md`, `w0m-web/.w0m/sdlc.json`), refuse the stale path, cite the canonical surface in `@wom/.w0m/sdlc.json` / `w0m-web/DECOMMISSIONED.md`, and propose the clean cutover path.

## Fact Revalidation Protocol

1. **Identify the Claim**: Isolate the exact file path, exported symbol, SQL relation, API contract, or deployment claim.
2. **Consult Specs & Architecture**: Check `w0m-web/openspec/specs/`, `docs/DECISIONS.md`, and `docs/ARCHITECTURE.md`.
3. **Verify Code & Schema Reality**: Query `just ask`, `just search`, `supabase_surface_drift_check.py`, and `just reality-verify`.
4. **Verify Test & Release Reality**: Run the governing test suite (`test-suites.json`) and check `releases/*.json` / live health when deployment status is claimed.
5. **Synthesize & Correct**: Report confirmed vs contradicted claims with exact file/line citations and reconcile drifted specs or tickets before building on them.
