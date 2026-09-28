# Start Brief — T482: SkillOpt Integration for w0m7skills

**Ticket:** [[T482]]  
**Author:** Antigravity  
**Date:** 2026-09-28  
**Subject:** Start Brief and Grounded Context for T482  

---

## 1. Verified Reality & Pre-flight Findings

- **Tracking Surfaces**: Mechanically verified with `just ticket-audit T482`. All 4 tracking surfaces agree (`.tasks/T482.md`, `TASKS.md`, `STATE.md`, active git state). Zero contradictions.
- **Duplication Audit**: `just ticket-dups --check-ticket T482` verified clean (0 duplicates found, max lexical match 12% against unrelated historical tickets).
- **Toolchain Status**:
  - `skillopt` v0.2.0 installed via `uv pip` into Python 3.12 environment.
  - Native CLI entrypoints verified: `skillopt-sleep`, `skillopt-train`, `skillopt-eval`.
  - Harvester source inputs verified: Claude Code (`~/.claude/projects/`) and Antigravity (`~/.gemini/antigravity-cli/brain/*/transcript.jsonl`) are present on host.

---

## 2. Acceptance Criteria Status

- ⚪ **AC1 — Tooling & Dependency Setup**: Add `skillopt` to estate tooling dependencies via `uv`/`pyproject.toml`, and register `just sleep` recipe in `justfile` exposing subcommands (`status`, `dry-run`, `run`, `adopt`, `harvest`). Proved by `just sleep --help` executing cleanly.
- ⚪ **AC2 — Antigravity & Multi-Agent Transcript Harvester**: Implement a w0m transcript reader supporting both Claude Code (`~/.claude/projects/`) and Antigravity (`transcript.jsonl`) logs, with automatic secret redaction using w0m's `secrets-check` patterns before any transcript excerpts are passed to mining.
- ⚪ **AC3 — Friction Mining & Lesson Synthesis**: The miner extracts agent friction points (failing pre-commit gates, repetitive user corrections, compiler/typecheck errors) and generates candidate rules formatted per `LESSONS.md` conventions (Problem, Lesson =>, and The Tell) into staged `report.md`.
- ⚪ **AC4 — Held-Out Validation Gate (`gate_no_regression: true`)**: Skill patches are replayed against a held-out benchmark set of real w0m tasks (e.g. 5 tickets across SDLC lifecycle) and strictly blocked if any benchmark score regresses.
- ⚪ **AC5 — Staged Proposal & Human Adoption Flow**: Proposed skill modifications land in `.agents/reports/sleep/` with before/after diffs; `just sleep adopt --skill <name>` copies accepted patches into `.agents/skills/<name>/SKILL.md` and runs `just skill reconcile` into `wom7skills` with pre-commit gates passing.
- ⚪ **AC6 — Local MLX Backend Support (`wom7mlx`)**: Provide configuration to route reflection and replay calls through a local OpenAI-compatible endpoint (`http://127.0.0.1:8000/v1` via MLX or Ollama) for 100% air-gapped, zero-cost, secret-safe execution.

---

## 3. Dependencies & Blockers

- `blocked_by: []` — Zero dependencies. Unblocked and ready for Phase 1 implementation.

---

## 4. Blast Radius

- `justfile` (root): Add `sleep` and `sleep-test` recipes.
- `wom7web/pyproject.toml`: Add `skillopt>=0.2.0` dependency.
- `.gitignore`: Exclude `.skillopt-sleep/` local cache.
- `scripts/sleep_harness.py`: Custom w0m sleep harness uniting `skillopt-sleep`, Antigravity harvester, secret redaction, and `LESSONS.md` synthesis.
- `scripts/tests/test_sleep_cli.py`: Automated test probes for CLI help, harvesting, redaction, and mining.

---

## 5. Earned Lessons & Non-Negotiables

1. **Local Context Bounds ([LESSONS §7 line 960](file:///Users/proto/Projects/@self/@wom/LESSONS.md#L960))**: Apple Silicon Metal threadgroup limits crash if context exceeds GPU thread boundaries. Offline local reflection must maintain bounded prompt budgets (<3,000 tokens).
2. **Canonical Skill Sync ([LESSONS §4 line 600](file:///Users/proto/Projects/@self/@wom/LESSONS.md#L600))**: Adopted skills must be synced into `wom7skills` canonical repo, never left as orphaned local drift.
3. **Multi-Agent Worktree Safety ([AGENTS.md](file:///Users/proto/Projects/@self/@wom/AGENTS.md))**: Zero blanket git commands (`git checkout -- .`, `git clean -f`). Surgical edits only.
4. **Zero `--no-verify`**: All pre-commit and pre-push hooks must pass organically.

---

## 6. Next Gate

- **Next Gate**: `w0m-sdlc-build`.
