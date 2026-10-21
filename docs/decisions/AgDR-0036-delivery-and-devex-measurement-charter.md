---
id: AgDR-0036
title: "Delivery and Developer-Experience Measurement Charter (DORA 5, Agent-DevEx, DX Core 4, SPACE)"
timestamp: 2026-10-21T00:20:00-05:00
agent: antigravity
model: gemini-2.5-pro
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T432
---

# AgDR-0036 — Delivery and Developer-Experience Measurement Charter (DORA 5, Agent-DevEx, DX Core 4, SPACE)

## Y-statement

> In the context of **instrumenting delivery pipeline health and developer/agent effectiveness across the w0m 7-repo estate (`T432`)**, facing **(1) unrecorded deployment outcomes and triggers in `public.deploy_log` that left Change Failure Rate and Deployment Rework Rate unmeasurable, (2) degenerate activity counts in an AI-agent workspace (~967 commits in 30 days) where raw commit or token counts reward churn (`T261`), and (3) the risk of silent zero-fallback reporting (`T242`)**, we decided **to establish a formal Delivery & DevEx Measurement Charter spanning the 5 DORA 2024/2025 metrics, Agent-DevEx friction telemetry, a weekly 3-question owner perceptual pulse, and a DX Core 4 scorecard, backed by explicit `outcome`/`trigger`/`incident_ref` columns on `public.deploy_log`, structured `.incidents/INC-*.json` records, and an explicit `unmeasurable` state whenever required inputs are missing** to achieve **system-level delivery observability, honest gap reporting, and productizable methodology for the w0m "Delivery & Developer-Experience Baseline" client engagement**, accepting **that metrics without live DB connectivity or incident history report `unmeasurable` (with reason) rather than fabricated zeros, and that all metrics are strictly scoped to system/estate health rather than individual or agent rankings**.

## Context

Measured across the w0m estate (`T432`, grounded in `.agents/reports/2026-09-23-t432-research-dora-space-devex-for-w0m.md`):
1. **DORA 5-Metric Model (2024/2025)**:
   - **Throughput**: Deployment Frequency, Lead Time for Changes, Failed Deployment Recovery Time (formerly MTTR).
   - **Instability**: Change Fail Rate (CFR), Deployment Rework Rate (unplanned deployments to fix a user-facing bug).
2. **Audit of w0m Deploy Telemetry (`T432` AC2)**:
   - `just deploy` and `just deploy-all` wrote `public.deploy_log` only at the end of `_deploy-ship` (`_log-deploy`) on successful completion; a deploy that failed mid-ship wrote no `failed` row.
   - `just deploy-function` (`scripts/deploy_function.py`, `T431`) replaced the process via `os.execvp` and never wrote a `deploy_log` row.
   - `public.deploy_log` lacked `outcome`, `trigger`, and `incident_ref`, making CFR and Rework Rate impossible to compute from schema truth.
3. **Why Activity Metrics Fail in an Agentic Estate (`T261`, SPACE)**:
   - Raw commit counts, PR counts, lines of code, and token consumption measure activity, not value or throughput. Setting targets on activity in an agentic workflow directly incentivizes fragmented commits and churn.

## Decision

### 1. Mandatory Multi-Dimensional Measurement (SPACE Rulebook)
- Every engineering effectiveness report (`just dora`, `just devex-pulse`) must span **at least 3 SPACE dimensions**, including **at least 1 perceptual dimension** (the weekly 3-question owner pulse: Flow/Focus, Feedback Loop Friction, Cognitive Load, scored 1–5).
- **System / Estate Level Only (Anti-Weaponization Invariant)**: Metrics are computed and reported exclusively at the estate, repository, or service level. Individual human or agent leaderboards, commit quotas, and stack rankings are prohibited.
- **Activity is Context, Never a Target**: Commit counts, ticket counts, and suite counts may be printed as denominator context, never as optimization targets or KPIs.

### 2. Fail-Closed `unmeasurable` State (`T242` Invariant)
- When a metric's required ground-truth input is absent (e.g., `DATABASE_URL` unset when querying live `deploy_log`, or zero incident records in window), the extractor (`scripts/dora_metrics.py`) **must emit `"status": "unmeasurable"` with an explicit `"reason"` string**.
- A missing input must **never** be coerced to `0`, `0.0%`, or `"elite"`.

### 3. Canonical Data Sources (Single Source of Truth per Metric)
- **`public.deploy_log` + `releases/*.json`**: SSOT for Deployment Frequency, Lead Time for Changes, Change Fail Rate (`outcome IN ('failed', 'rolled_back', 'hotfixed')`), and Deployment Rework Rate (`trigger = 'incident'` or `outcome IN ('rolled_back', 'hotfixed')`).
- **`.incidents/INC-*.json`** (validated against `.incidents/incident.schema.json`): Version-controlled SSOT for incident lifecycle (`detected_at`, `recovered_at`, `cause_deploy_version`, `resolution_deploy_version`, `severity`, `summary`), powering Failed Deployment Recovery Time.
- **`.tasks/T*.md` (`area` & `status`)**: SSOT for DX Core 4 **Impact** (share of completed tickets in `product` vs platform/SDLC/tooling areas).
- **`deploy-logs/agent-devex.jsonl` & `deploy-logs/devex-pulse.jsonl`**: Append-only JSONL telemetry for Agent-DevEx friction signals (hook duration, gate failure rate, permission prompts) and the 3-question owner pulse.

## Consequences

- **Positive**: `just dora` and `just devex-pulse` produce deterministic, schema-grounded JSONL scorecards covering DORA 5, Agent-DevEx, and DX Core 4 without fabricating data when offline.
- **Trade-off**: Every production deploy entrypoint (`_log-deploy`, `deploy_logged.py`, `deploy_function.py`) must pass valid `outcome` (`success` · `failed` · `rolled_back` · `hotfixed`) and `trigger` (`planned` · `incident`) values; invalid values fail closed (`exit 1`).

## Evidence

- Migration: `wom7api/supabase/migrations/20261021010000_t432_deploy_log_outcome_and_incidents.sql`
- Incident schema & ledger: `.incidents/incident.schema.json`, `.incidents/README.md`
- Extractor & test suite: `scripts/dora_metrics.py`, `scripts/dora_metrics_test.py` (`just dora`, `just dora-test`, `just devex-pulse`)
- AI Capabilities Self-Assessment: `.agents/reports/2026-10-20-t432-dora-ai-capabilities-self-assessment.md`
