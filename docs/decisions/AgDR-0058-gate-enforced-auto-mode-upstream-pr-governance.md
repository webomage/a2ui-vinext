---
id: AgDR-0058
title: "Gate-enforced full auto-mode upstream PR governance and per-repository contribution compliance"
timestamp: 2026-11-06T00:44:00-05:00
agent: antigravity
model: gemini-2.5-pro
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T655
---

# AgDR-0058 — Gate-enforced full auto-mode upstream PR governance and per-repository contribution compliance

## Y-statement

> In the context of **maintaining 18+ open-source forks under `w0m-pr/*` with 23+ active upstream pull requests and 16+ prepared contribution branches (`T593`, `T654`)**, facing **two opposite failure modes: (1) `T435`'s blanket human Touch ID gate (`_confirm "prs-submit"`, `REFUSED-AGENT`) stalled routine upstream submissions behind manual copy-paste while (2) `w0m_prs.py:format_pr_proposal_body()` emitted a single internal `Why / What For / How` format that missed `stablyai/orca`'s mandatory 11-section template + `Fixes #<issue>` rule, `jundot/omlx`'s 3-section template, `headroomlabs-ai/headroom`'s 7-section `pr-governance.py` schema, and `ml-explore/mlx-lm`'s explicit contributor-ban policy against AI-authored PR descriptions and automated PR creation**, we decided **to replace the blanket Touch ID external-PR block with a mechanical 6-gate upstream compliance engine in `scripts/w0m_prs.py` (`just pr-auto`, `just pr-open`, `just pr-compliance`) that classifies every target repository by its `CONTRIBUTING.md` / `AGENTS.md` / `.github/pull_request_template.md` rules, hard-denylists `ml-explore/mlx-lm` (`AUTOMATION_BANNED`) and preserves `AgDR-0047` human sign-off on vulnerability disclosures, requires human-authored descriptions on `Graphify-Labs/graphify`, enforces CLA/cap gates on `oraios/serena` and `google-research/harness2`, and runs full unattended PR creation, body remediation, and obsolete-PR closure on AI-compatible upstreams once origin sync, GPG signature, standalone `upstream/<base>` conflict-free `merge-tree`, sibling/duplicate PR scan, `Fixes #<issue>` linkage, and target PR template + honest `Visual Proof` checks all pass** to achieve **zero-friction, maintainer-grade upstream contributions with zero contributor-ban or template-rejection risk**, accepting **that UI feature branches lacking required before/after media or branches conflicting with `upstream/<base>` are mechanically held (`HELD-NEEDS-VISUAL-PROOF` / `REFUSED-CONFLICT-UPSTREAM`) until satisfied**.

## Context

Measured on `2026-11-06` across all `18` `w0m-pr/*` repositories and `23` open external pull requests (`T655`):

1. **Divergent upstream AI & contribution rules across target projects**:
   - **`ml-explore/mlx-lm` (`AUTOMATION_BANNED`)**: `CONTRIBUTING.md:14-15` and `AGENTS.md:10-28` strictly prohibit AI-written PR descriptions, review replies, `git push`, and automated PR creation — penalty is immediate PR closure and contributor ban.
   - **`Graphify-Labs/graphify` (`HUMAN_DESCRIPTION_REQUIRED`, base `v8`)**: `CONTRIBUTING.md:128-135` allows AI code with `Co-Authored-By` commit trailers, requires human-authored PR descriptions, and enforces a 5-section template plus Conventional Commit PR titles (`pr-management.yml`).
   - **`oraios/serena` (`CLA_AND_AGREEMENT_REQUIRED`) & `google-research/harness2` (`CLA_REQUIRED`)**: Require signed CLA (`license/cla` / Google CLA); `serena` additionally enforces a hard `3`-open-PR cap per author, mandatory `CHANGELOG.md` entries, and prior issue agreement for non-trivial changes.
   - **`headroomlabs-ai/headroom` (`STRICT_GOVERNANCE_TEMPLATE`)**: Runs `scripts/pr-governance.py` in CI requiring 7 exact `##` headings, fenced `### Test Output`, 4 `- Label: value` lines under `## Real Behavior Proof`, 7 `- Label: value` lines under `## Runtime Rollout Safety`, `0` `CHANGELOG.md` edits, max `10` open PRs, and prior maintainer approval on new features.
   - **`stablyai/orca` (`AUTO_COMPLIANT`, template + mandatory issue link)**: `.github/CONTRIBUTING.md:218-227` and `.github/pull_request_template.md:1-64` explicitly welcome AI coding agents (requiring `## AI Disclosure` and an AI agent `## Review` section) while mandating `## ELI5`, `## What Changed`, `## Why`, `## Linked Issue` (`Fixes #<num>` — *"If you do not have one and are an outside contributor, your PR **will** be ignored"*), and `## Visual Proof` (before/after media for UI changes or literal `` `N/A` `` + reason when non-visual).
   - **`jundot/omlx` (`AUTO_COMPLIANT`, 3-section template + `<1,000` LoC cap)**: Welcomes AI (`docs/CONTRIBUTING.md:66-68`), requires `## Summary`, `## Validation`, and `## Checklist`, and auto-converts `>1,000` LoC PRs from external contributors to Draft (`triage.js`).
   - **`mizorewww/laya-mlx`, `oxiglade/mlx-rs`, `Blaizzy/mlx-vlm` (`Neywa-Labs/mlx-vlm`), `openai/tart-guest-agent`, `bulwarkid/virtual-fido` (`master`), `JeffHoogland/moksha` (`master`), `BodhiDev/*` (`main`)**: Allow automated submission (`mlx-vlm` requires GitHub-verified commit signatures).
2. **Defects under the prior `T435` Touch ID-only model**:
   - Manual `just pr-open` submitted 11 `stablyai/orca` PRs (`#37029`–`#38612`) with internal `## Why / ## What For / ## How` headings and zero `Fixes #<issue>` links, risking maintainer auto-ignore.
   - `submit_prepared_prs()` did not push local-only branches (`perf/terminal-chat-redraw-and-tab-caching`) or detect standalone `upstream/main` conflicts (`fix/linux-cli-stale-appimage-and-dispatcher`) prior to `gh pr create`.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Option A: Gate-enforced full auto-mode (`w0m_prs.py`) with per-repo rule profiles, hard `mlx-lm` denylist, `Fixes #<issue>` resolution, and template + `merge-tree` + duplicate gates** | Respects every upstream's `CONTRIBUTING.md` / `AGENTS.md` mechanically; prevents contributor bans on `mlx-lm`; upgrades open PR bodies and auto-submits compliant PRs unattended | Requires maintaining structured per-repo rule profiles in `scripts/w0m_prs.py` | **Chosen (Owner decision 2026-11-06)** |
| **Option B: Keep `T435` manual Touch ID on `prs-submit` / `prs-obsolete-close`** | Zero unattended external GitHub writes | Does not check upstream templates, issue links, or AI bans; creates manual operator toil | **Rejected** |
| **Option C: Unconditional `gh pr create` without per-repo policy profiles** | Simplest implementation | Violates `ml-explore/mlx-lm` (contributor ban), `stablyai/orca` (`Fixes #` + `Visual Proof`), and `headroom` (`pr-governance.py`) | **Rejected** |

## Decision

1. **Carve `prs-submit` (`pr-open`, `pr-auto`) and `prs-obsolete-close` out of `confirm-policy.json` (`T435`) into `w0m_prs.py`'s 6-gate compliance engine**:
   - `just db-migrate`, `just deploy*`, `rotate`, `sync-*-secrets`, and `AgDR-0047` vulnerability disclosures (`disclose/diodb`) remain strictly Touch ID / human-gated.
   - Raw unvalidated `gh pr create` outside `scripts/w0m_prs.py` remains forbidden in `AGENTS.md` and `w0m-web/CLAUDE.md`.
2. **Six mandatory pre-flight gates before any automated upstream PR write (`scripts/w0m_prs.py`)**:
   1. **Repo Automation Policy Gate**: Hard-refuse (`REFUSED-REPO-POLICY`) `ml-explore/mlx-lm` (`AUTOMATION_BANNED`), `Graphify-Labs/graphify` (`HUMAN_DESCRIPTION_REQUIRED` unless human body supplied), unverified CLA repos (`google-research/harness2`, `oraios/serena`), and feature PRs lacking maintainer approval on `headroomlabs-ai/headroom`.
   2. **Branch Sync & Verified Signature Gate**: Ensure local branch exists, carries a valid signature when required, and push/sync `origin/<branch>` on `webomage/<fork>` prior to `gh pr create`.
   3. **Standalone Upstream Mergeability Gate**: Run `git merge-tree --write-tree upstream/<true_base> refs/heads/<branch>` against the repository's true default branch (`v8` for `graphify`, `master` for `moksha` and `virtual-fido`, `main` otherwise); hold conflicting branches (`REFUSED-CONFLICT-UPSTREAM`).
   4. **Sibling & Duplicate PR Scan**: Query open and recently merged upstream PRs (both `casualuser` and third-party authors) to block duplicates and document sibling boundaries.
   5. **Linked Issue Gate (`Fixes #<num>`)**: Require a resolved upstream issue number whenever mandated by target rules (`stablyai/orca`), matching pre-existing open upstream issues first and auto-creating a focused upstream issue only when none exists and `auto_create_issue=True`.
   6. **Target Template & Honest Visual Proof Gate**: Render and validate the target repo's exact PR template (`orca` 11-section, `omlx` 3-section, `headroom` 7-section, or standard); hold UI feature PRs lacking real visual proof (`HELD-NEEDS-VISUAL-PROOF`) rather than fabricating `N/A`.

## Consequences

- **Positive**:
  - Compliant PRs across `stablyai/orca`, `JeffHoogland/moksha`, `BodhiDev/*`, `bulwarkid/virtual-fido`, `jundot/omlx`, and `mizorewww/laya-mlx` open and reconcile automatically with 100% template fidelity.
  - Zero risk of accidental agent activity on `ml-explore/mlx-lm` or unapproved VDP disclosures.
- **Negative / Trade-offs**:
  - UI feature branches on repos requiring screenshots (`stablyai/orca`) pause in `HELD-NEEDS-VISUAL-PROOF` until screenshot/video URLs are attached to the proposal entry.

## What this does NOT decide

- Does not relax `T161` / `T435` Touch ID confirmation for database migrations (`db-migrate`), deployments (`deploy*`), secret rotation/sync, or `AgDR-0047` security/bug-bounty disclosures.
