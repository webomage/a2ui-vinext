---
id: AgDR-0053
title: "Visual golden snapshots: local stack with seeded data as canonical source of truth and audited diff-summary regeneration gate"
timestamp: 2026-11-01T08:52:00-05:00
agent: antigravity
model: gemini-4-argon
trigger: ticket-ac
status: accepted
superseded_by:
supersedes:
ticket: T487
---

# AgDR-0053 — Visual golden snapshots: local stack with seeded data as canonical source of truth and audited diff-summary regeneration gate

## Y-statement

> In the context of **operating visual regression golden snapshots (`w0m-web/screenshots/goldens/en-<viewport>-<name>.png`) across `apps/web`, `apps/cp`, `apps/job`, and `apps/join` under [[T487]] (split from [[T478]] and [[T439]])**, facing **(1) 66k–112k pixel mismatches when comparing local dev-server renders against baselines previously captured against live `https://webomage.com` (`scripts/update_goldens.mjs`), (2) absent baselines for `job/goldens.spec`, `join/goldens.spec`, and `cp_client_org` in `visual/cp_visual.spec` causing fail-closed throws, and (3) the risk of silent visual drift if seed data or font tokens change without an explicit diff review**, we decided **to establish the local stack with seeded data (`just goldens` / `just e2e-local`) as the single canonical source of truth for visual goldens, enforce 100% baseline completeness across all golden `.spec` tables (`just goldens-check`), and require all baseline updates to run through an audited regeneration recipe (`just goldens-regen` / `scripts/regen_goldens.py`) that prints a per-file pixel/dimension/SHA-256 diff summary and fails if regenerated baselines are left uncommitted**, to achieve **zero false-red environment mismatches on local runs (`0` golden failures on an unchanged tree), complete baseline coverage across all 4 portals (`web`, `cp`, `job`, `join`), and auditable git-tracked visual changes**, accepting **that cross-OS font subpixel differences between `darwin-arm64` and `linux-x86_64` are absorbed by the 2,000-pixel / `0.15` threshold on section-scoped goldens (`specs/web/goldens.spec:40`) while intentional typography or seed changes require running `just goldens-regen` and committing the updated PNGs**.

## Context

1. **Live vs Local Capture Drift (`T478` Run 4)**:
   - `w0m-web/scripts/update_goldens.mjs` previously hardcoded `const BASE_URL = process.env.E2E_BASE_URL || "https://webomage.com"` and wrote `en-<name>.png` (without the viewport segment `en-<viewport>-<name>.png` that `tests/steps/ui.steps.ts` actually reads).
   - Because live production data (blog feed length, dynamic metrics, live Upwork/LinkedIn counts) differs from local seeded data, full-page goldens captured on live failed locally with 66,000–112,000 mismatched pixels or height dimension mismatches.
2. **Missing Portal Baselines (`AC2`)**:
   - `tests/steps/ui.steps.ts` rightly fails closed (`No golden for <viewport>-<name> — refusing to pass on an absent baseline`, `T222 AC2`).
   - However, 10 baselines referenced by `specs/job/goldens.spec` (`job_home`, `job_list`), `specs/join/goldens.spec` (`join_home`, `join_dashboard`, `join_assessments`, `join_interview`), `specs/visual/join_visual.spec` (`join_home`, `join_assessments` mobile), and `specs/visual/cp_visual.spec` (`cp_client_org` desktop & mobile) had never been committed to `w0m-web/screenshots/goldens/`.
3. **Multi-OS Agent Execution (`darwin-arm64` vs `linux-x86_64`)**:
   - Both macOS (`proto@MacBook-Pro`) and Linux (`aleksei@HP`) hosts execute gates across the estate (`AgDR-0052`).
   - Section-scoped goldens (`specs/web/goldens.spec:40`) with `VOLATILE_SELECTORS` masking (`.metrics-overlay`), disabled CSS animations, and `pixelmatch` (`threshold: 0.15`, `mismatchedPixels <= 2000`) isolate layout/token regressions from dynamic feed height and minor subpixel antialiasing differences.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **O1 — Capture baselines from live `https://webomage.com` (`scripts/update_goldens.mjs`)** | Reflects production CDN state at capture time. | Violates `liveGuard` on local runs; mutates whenever live content/feed changes; cannot capture local `test-team-local` CP/Job/Join states without hitting production. | **Rejected** |
| **O2 — Require a remote/Dockerized render container for every `just goldens` run** | Identical Linux freetype rasterization on every host. | Adds heavy container startup overhead to every local pre-deploy verification and breaks when Docker daemon is stopped. | **Rejected** |
| **O3 — Canonical local stack source of truth + `just goldens-check` completeness gate + `just goldens-regen` diff-summary & clean-tree gate** | Self-contained local execution; 100% baseline coverage across `web`, `cp`, `job`, and `join`; prints exact pixel/dimension diff summary on regeneration and requires committing updated PNGs. | Intentional design-system or seed changes require running `just goldens-regen` and committing the resulting baseline PNG diff. | **Accepted ([[T487]])** |

## Decision

1. **Canonical Source of Truth (`AC1`)**:
   - All visual golden baselines in `w0m-web/screenshots/goldens/en-<viewport>-<name>.png` are rendered against the local Astro stack (`WEB :4321`, `JOIN :4323`, `JOB :4324`, `CP :4325`) with local seeded data and `VOLATILE_SELECTORS` masking.
   - `w0m-web/scripts/update_goldens.mjs` is updated to default to `http://127.0.0.1:4321` (never `https://webomage.com`) and delegates to `scripts/regen_goldens.py`.
2. **100% Baseline Completeness (`AC2`)**:
   - Every `(viewport, name)` pair referenced across `specs/web/goldens.spec`, `specs/job/goldens.spec`, `specs/join/goldens.spec`, `specs/visual/web_visual.spec`, `specs/visual/join_visual.spec`, and `specs/visual/cp_visual.spec` must have a non-empty committed PNG in `w0m-web/screenshots/goldens/en-<viewport>-<name>.png`.
   - `just goldens-check` (`python3 scripts/regen_goldens.py --check`) statically parses all `.spec` files for golden snapshot steps, verifies every referenced `en-<viewport>-<name>.png` exists and has valid PNG dimensions matching `VIEWPORTS[viewport].width`, and fails closed if any baseline is missing or uncommitted.
3. **Audited Regeneration & Diff Summary (`AC3`)**:
   - `just goldens-regen` (`python3 scripts/regen_goldens.py --regen`) snapshots the pre-regeneration SHA-256 and PNG dimensions of `w0m-web/screenshots/goldens/*.png`, runs the golden capture with `GAUGE_UPDATE_GOLDENS=true`, computes a per-file diff summary (created / modified / unchanged, dimension delta, and pixelmatch delta), and exits with a reminder that modified baselines must be committed before `just goldens-check` / pre-push passes.

## Consequences

- **Positive**:
  - `just goldens` passes deterministically (`0` failures across back-to-back runs on an unchanged tree, `AC4`).
  - Missing baselines in `job`, `join`, and `cp_client_org` are populated and mechanically enforced by `just goldens-check`.
  - No golden script in the repository defaults to `https://webomage.com`.
- **Negative / Trade-offs**:
  - Adding a new row to a golden `.spec` table immediately fails `just goldens-check` until its baseline PNG is generated and committed.

## Compliance / Verification

- Enforced by `scripts/regen_goldens.py` (`just goldens-check` and `just goldens-regen`) and unit-tested in `scripts/tests/test_regen_goldens.py` (`just goldens-check-test`).
