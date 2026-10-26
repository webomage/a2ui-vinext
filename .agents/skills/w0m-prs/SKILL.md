---
name: w0m-prs
description: GitHub PR discovery, health audit, background polling, and visual reporting tool for w0m and open-source estate. Use when tracking upstream open-source PRs, auditing review decisions and mergeability, monitoring background status updates, or generating publication-grade Markdown reports with validated Mermaid charts.
metadata:
  version: "2026.10.26-1793009642"
---

# w0m-prs

## Overview

`w0m-prs` is the canonical w0m developer tool and agent skill for discovering, auditing, polling, and reporting on GitHub Pull Requests across internal repos, upstream dependencies (`w0m-pr`), and contributor portfolios.

It provides deterministic CLI interfaces via `just prs`, outputs structured JSON or formatted terminal output, and generates publication-grade Markdown reports with headless `mmd-validate`-compliant Mermaid graphs.

## Subcommands & Usage

### 1. Discovery & Search
Search PRs by author username, repository target, or preset:
```bash
# Search PRs across active w0m-pr dependencies (stablyai/orca, openai/tart-guest-agent, bulwarkid/virtual-fido)
just prs search --preset w0m-pr

# Search PRs authored by a specific user
just prs search --author casualuser --limit 20

# Output machine-readable JSON
just prs search --preset w0m-pr --json
```

### 2. Deep Health & Mergeability Audit
Audit merge status (`MERGEABLE` vs `CONFLICTING`), review decisions (`REVIEW_REQUIRED`, `CHANGES_REQUESTED`, `APPROVED`), comments, review threads, and CI rollup:
```bash
# Audit a specific PR in a repository
just prs audit --repo openai/tart-guest-agent --pr 62

# Audit all open PRs in w0m-pr preset
just prs audit --preset w0m-pr
```

### 3. Autonomous Background Watch Poller
Monitor active PRs on a schedule without busy-waiting. Emits delta alerts on state changes (review submissions, CI completion, merge status transitions):
```bash
# Watch w0m-pr PRs every 5 minutes for 30 minutes with terminal notification on change
just prs watch --preset w0m-pr --interval 5 --duration 30 --notify

# Watch a single critical PR
just prs watch --repo stablyai/orca --pr 16597 --interval 2 --duration 60
```

### 4. Publication-Grade Visual Report Generator
Generates comprehensive Markdown portfolio reports embedding three compliant Mermaid diagrams:
- `flowchart TD`: Multi-tier lifecycle topology (Ingestion -> Review/CI -> Terminal).
- `xychart-beta`: PR volume breakdown by state (Open, Merged, Closed).
- `flowchart LR`: Milestone progression phases.

```bash
# Generate report for an author to a markdown file
just prs report --author casualuser --out docs/reports/github_prs_report.md
```

### 5. Fresh Status Table (`just prs-open` / T369 / T417)
Instantly query, audit, and display an aligned terminal or Markdown table of active PRs across all managed `w0m-pr` dependencies (`jundot/omlx`, `Blaizzy/mlx-vlm`, `stablyai/orca`, `openai/tart-guest-agent`, `cirruslabs/tart`, `bulwarkid/virtual-fido`, `headroomlabs-ai/headroom`, `oraios/serena`).
Includes active feedback inspection (`Feedback` column) displaying reviewer questions (`❓`), suggestions (`💡`), comment volume (`💬`), and reviewer attribution (`opcode81`, `AmirF194`).

```bash
# Print fresh report table for active PRs in w0m-pr dependencies
just prs-open

# Or via explicit subcommands and flags
just prs table --preset w0m-pr
just prs table --preset w0m-pr --all
just prs table --preset w0m-pr --markdown
```

### 6. Continuous Fork Synchronization Verification (`just forks` / T377)
Audit all local open-source forks under `w0m-pr/` against upstream and origin remotes:

```bash
# Fast cached inspection of all forks (ahead/behind counts, dirty worktree)
just forks --no-fetch

# Live fetch and inspection of all forks against upstream
just forks

# Strict CI/pre-commit gate mode (exits non-zero if any fork is behind upstream or dirty)
just forks-check

# Output Markdown table for reports
just forks --no-fetch --markdown

# Output machine-readable JSON
just forks --no-fetch --json
```

### 7. Fork Remote Management & Synchronization (`just forks-fetch`, `forks-info`, `forks-update`)
Granular management of external fork repositories in `w0m-pr/`:

```bash
# Explicitly fetch upstream and origin remotes for all forks (or a single fork)
just forks-fetch
just forks-fetch tart

# Deep dive into a single fork (commit log diff vs upstream, modified files, active branch)
just forks-info tart
just forks-info omlx
just forks-info omlx --json

# Safe synchronization: fast-forward clean default branches, report feature branch status
just forks-update tart
just forks-update --rebase omlx
just forks-sync       # alias to forks-update
```

## Agent Best Practices
- **Mandatory upstream pre-flight (prior art & discovery)**: Always search open AND closed PRs and issues (`gh pr list --state all --search "<keywords>"`, `gh issue list --state all --search "<keywords>"`, or `just prs search`) before opening an upstream PR or issue.
  - If an active PR exists, **do not open a duplicate PR** (Zero Redundant PRs principle). Test it, validate behavior, and contribute constructive QA or targeted patches directly on that PR.
  - If stalled/closed PRs exist, inspect why they stalled (unmerged dependency abstractions, CLA blocks, merge conflicts, architecture). Citing them in the PR body is mandatory: state what is superseded, contrast architectural trade-offs upfront (e.g. single vs. companion server), and preemptively address maintainer design concerns.
  - If an open issue exists, link it in the PR description (`Fixes #123` / `Addresses #123`) and notify the issue thread.
- **Verify upstream health**: Always run `just prs-open` or `just prs audit` before marking tickets depending on upstream PRs as complete.
- **Audit fork alignment**: Regularly run `just forks` or `just forks-check` to confirm local feature branches in `w0m-pr/` are not lagging behind `upstream/main`.
- **Check for conflicts**: Run `just prs-open` to proactively catch merge conflicts across upstream contributions.
- **Diagram validation**: All Mermaid diagrams generated by `just prs report` conform to the estate's `mmd-validate` pre-commit gate.
