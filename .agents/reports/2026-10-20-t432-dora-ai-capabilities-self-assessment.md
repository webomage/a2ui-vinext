---
title: "DORA AI Capabilities Model (v2025.2) Self-Assessment & Delivery Baseline SKU Outline"
ticket: T432
related_tickets: [T432, T448, T64, T531, T503, T473]
date: 2026-10-20
status: final
author: antigravity
---

# DORA AI Capabilities Model (v2025.2) Self-Assessment & Client Offering Outline (`T432` AC8 & AC10)

Grounded self-assessment of the `@wom` 7-repo estate against the **7 capabilities of the DORA AI Capabilities Model (v2025.2)**, paired with the one-page client offering outline for the **"Delivery & Developer-Experience Baseline"** engagement (`T432` AC8, AC9, AC10; charter: [`AgDR-0036`](../../docs/decisions/AgDR-0036-delivery-and-devex-measurement-charter.md)).

---

## 1. Executive Summary & Measured Estate Baseline (`just dora`)

Measured on `2026-10-21` via `python3 scripts/dora_metrics.py --since 30` (`T432` AC5/AC6/AC7):

| Dimension | Metric | 30-Day Measured Reading | Source of Truth |
|---|---|---|---|
| **DORA Throughput** | Deployment Frequency | **35 releases** (`1.17 / day`, `8.17 / week`) | `releases/*.json` (`T473`) |
| **DORA Throughput** | Lead Time for Changes | **0.21h median** (`1.18h p90`, `n=35`) | `releases/*.json` + `git log` |
| **DORA Throughput** | Failed Deployment Recovery Time | **1.88h median** (`2.25h max`, `n=2`) | `.incidents/INC-*.json` (`T432` AC4) |
| **DORA Instability** | Change Fail Rate (CFR) | **5.71%** (`2 / 35` releases) | `releases/*.json` + `.incidents/INC-*.json` + `public.deploy_log` (`T432` AC3) |
| **DORA Instability** | Deployment Rework Rate | **5.71%** (`2 / 35` releases) | `releases/*.json` + `.incidents/INC-*.json` + `public.deploy_log` (`T432` AC3) |
| **Guardrail Coverage** | Python Typed Definitions | **93.28%** (`1,956 / 2,097` defs typed; `178 / 201` files 100% typed) | `wom7web/project/py-typing-baseline.json` (`T448` AC3) |
| **DX Core 4 Impact** | Done-Ticket Share by Area | **22.31% Product** vs **76.86% Platform/SDLC/Security** (`363 / 564` done, `0` unconfirmed inferred areas) | `.tasks/T*.md` (`T432` AC7) |

---

## 2. DORA AI Capabilities Model (v2025.2) — 7-Capability Self-Assessment (`T432` AC8)

The DORA 2025 AI Capabilities Model identifies **7 technical and cultural practices** that amplify the positive impact of AI on software delivery while preventing instability and burnout.

| # | DORA v2025.2 Capability | Maturity (1–5) | Grounded Estate Evidence | Remaining Gap / Next Ratchet |
|---|---|---|---|---|
| **1** | **Clear and Communicated AI Stance** | **5 / 5** | Canonical root `AGENTS.md` + `CLAUDE.md` + `.w0m/sdlc.json` define every agent's role, non-negotiable gates, human-only Touch ID boundaries (`T435`), and virtual agent identity claims (`T564`). | Maintain parity across all 7 estate repos via `wom7skills` sync checks. |
| **2** | **Healthy Data Ecosystem** | **4 / 5** | Triangulated SSOT (`AgDR-0025`, `T214`), single baseline schema (`wom7api/supabase/baseline/schema.sql`), pinned Backstage v1alpha1 JSON Schema (`T448`), and generated `catalog-info.yaml` (`T64` AC2, 58 entities). | Run `just db-migrate` in a human terminal to apply `20261021010000_t432_deploy_log_outcome_and_incidents.sql` (`T432` AC3). |
| **3** | **AI-Accessible Internal Data (Knowledge & Context)** | **5 / 5** | Pre-built AST & semantic graphs (`codegraph` + `graphify` + `code-review-graph`), `just ask` / `just graph-query`, `TASKS.md` projection (`T411`), `docs/DECISIONS.md` (`374` indexed decisions), and Backstage catalog (`T64`). | Keep `codegraph sync` per-commit hook fast (`<2s`). |
| **4** | **Strong Version Control Practices** | **5 / 5** | Single-branch trunk-based development (`beta`) with isolated per-agent worktrees (`just agent-tree`, `AgDR-0032`, `T531`), landing lock coordination, detached release tags (`T473`), and zero `--no-verify`. | Continue enforcing `agent-tree-land` ticket-gap and migration-collision checks (`T551`). |
| **5** | **Working in Small Batches** | **4 / 5** | 35 releases in 30 days (`1.17/day`), median commit-to-release lead time `0.21h`, and fingerprint-scoped app deploys (`W0M_RELEASE_APPS` via Dagger TypeScript pipeline in `wom7api/dagger/pipeline.ts`, `T64` AC1/AC3). | Reduce multi-ticket mega-sessions by keeping WIP per agent tree `<= 3` tickets. |
| **6** | **User-Centric Focus** | **3 / 5** | DX Core 4 Impact measurement (`just dora`) reveals **22.31% product vs 76.86% platform/SDLC/security** across 363 completed tickets. The heavy platform investment hardened the foundation (`T503`, `T531`, `T448`). | Shift completed-ticket share toward `product` / client-facing features now that SDLC/security ratchets are in place. |
| **7** | **Quality Internal Platform (Fast Feedback & Guardrails)** | **4.5 / 5** | 296 registered test suites (`wom7web/project/test-suites.json`), fast pre-push tier (`_deploy-preflight`), AST Python typing ratchet (`T448`), Dagger step cache (`T64`), and `just dora` / `just devex-pulse` (`T432`). | Populate weekly owner 3-question perceptual pulse (`just devex-pulse --flow ... --feedback ... --cognitive-load ...`). |

---

## 3. Architectural Decisions on CP Panel, Tinybird Sink & Client Offering (`T432` AC9 & AC10)

### 3.1 CP "Delivery" Panel & Tinybird Dual-Write (`T432` AC9)
- **Recommendation (Weighted Decision)**: **Defer (`later`)** until `T43` (Tinybird full-observability sink) is active and 4 weeks of post-migration `deploy_log.outcome` + `devex-pulse.jsonl` readings have accumulated.
  - **Cost**: 0 hours now (CLI JSONL via `just dora` and `just devex-pulse` is already live and tested).
  - **Risk**: Building a CP chart before `deploy_log.outcome` has 30 days of live rows would display mostly `unmeasurable` placeholders.
  - **What it unblocks**: Immediate closure of `T432` with CLI JSONL + Backstage catalog view (`BackstageCatalogView.svelte`, `T64` AC4) already available for admin inspection.

### 3.2 One-Page Client Offering Outline: "Delivery & Developer-Experience Baseline" (`T432` AC10)
- **Product Name**: **w0m Delivery & Developer-Experience Baseline** *(deliberately avoids "DORA" in title to prevent confusion with the EU Digital Operational Resilience Act in financial/enterprise accounts)*.
- **Target Buyer**: VP Engineering / CTO of 15–150 engineer product organizations adopting AI coding assistants (Claude Code, Cursor, Copilot, Antigravity) who suspect AI commit volume is masking delivery friction or rework.
- **Duration & Phases (3 Weeks)**:
  1. **Week 1 — Telemetry & Charter Instrumentation**: Deploy the SPACE/anti-weaponization measurement charter (`AgDR-0036` template), wire `deploy_log` outcome/trigger tagging and `.incidents/` ledger, and run the DORA v2025.2 7-Capability audit.
  2. **Week 2 — Perceptual Pulse & Pipeline Bottleneck Mapping**: Run the 3-question Developer/Agent friction pulse, instrument CI/pre-push hook latency, and generate the Backstage `catalog-info.yaml` software catalog from repo config.
  3. **Week 3 — DX Core 4 Readout & 90-Day Ratchet Roadmap**: Deliver the executive DX Core 4 scorecard (Speed · Effectiveness · Quality · Impact), identify the top 3 delivery/AI-rework bottlenecks, and install automated non-regression ratchets.
- **Price Hypothesis**: **$12,500 – $18,000 fixed-scope diagnostic** (or credited toward a quarterly w0m Platform & AI-SDLC Enablement retainer).
