# Harness² (`google-research/harness2`) — Architectural Analysis & w0m Integration Guide

- **Date:** 2026-10-18
- **Upstream:** `https://github.com/google-research/harness2` (`arXiv:2610.14224`)
- **Fork:** `casualuser/harness2` (`wom7pr/harness2`, `main` synced `+0/-0` with `upstream/main`)
- **Tickets:** [[T556]], [[T557]]

---

## 1. Overview

**Harness²** (*Recursive Agent Harnessing for an Open World*) optimizes the 8-component system around a frozen model (`c1` system prompt, `c2` context policy, `c3` long-term memory, `c4` tool guidance, `c5` subagents, `c6` skills, `c7` scripts, `c8` hooks/plugins) using two coupled loops:
1. **Task-level recursion (Propose–Probe–Compose)**: Runs the base harness (`r0`), proposes invariant (`INV`) and domain-specific (`DOM`) component edits over a file-based evidence tree (`ContextTree`), probes candidates (`ri`, `rd`), and composes/selects from anonymized deliverables.
2. **Harnessing-level recursion (Experience Library)**: Reflects on behavioral contrasts and writes structured domain lessons (`cue`, `lesson`, `evidence`, `confidence`) with a generated `INDEX.md`.

---

## 2. Extending Orca (`casualuser/orca`) with Harness² ([[T556]] & [[T557]])

1. **Orca Worktrees as Harness² Propose–Probe–Compose Candidates ([[T556]] AC2)**:
   - Orca (`wom7pr/orca`) already orchestrates isolated git worktrees, Claude/Codex/OpenCode agent sessions, skills, and hooks across Desktop and Mobile.
   - Extending Orca with Harness²'s `SurfaceSpec` validator (`autotrigger` + `always_on_max` budget) and worktree-backed Propose–Probe–Compose runner lets Orca inspect surface health and spawn/compare candidate probe worktrees directly.
2. **Mobile Orca Camera Capture into Native Chat & Terminal Sessions ([[T557]])**:
   - Extends `mobile/src/session/mobile-image-source-picker.ts` with `'camera'` (`CameraPermissionError`, `ImagePicker.requestCameraPermissionsAsync()`, `ImagePicker.launchCameraAsync()`) and adds **"Take Photo"** to `MobileSessionSheets.tsx` so mobile users can snap a live photo and attach it directly into the active Native Chat composer or Terminal session.

---

## 3. Five High-Leverage Mechanisms for `w0m` & Orca ([[T556]])

1. **Skill Trigger Hygiene & Always-On Budget (`autotrigger` + `always_on_max`, `harness2/core/tree.py:192-214`)**:
   - Every installed skill in `.agents/skills/<name>/SKILL.md` must either have an explicit trigger reference in the always-on entrypoint (`AGENTS.md` / `CLAUDE.md`) or be declared in `.w0m/sdlc.json` lifecycle routing, while enforcing a measured character budget (`always_on_max`) on always-on instructions so prompt bloat never crowds out reasoning tokens.
2. **Structured `cue / lesson / evidence / confidence` Indexing for `LESSONS.md` (`harness2/core/library.py:84-163`)**:
   - Extend `just lessons` with a lightweight cue index so agents can scan recognizable trigger symptoms (`cue`) and behavioral proof (`evidence`) before opening full postmortems.
3. **Evidence-as-Filesystem Context Bundles (`ContextTree` + `EVIDENCE_BOUNDARY`, `harness2/core/context.py:43-189`)**:
   - Materialize structured `.w0m/context/<ticket>/` directories (`task.md`, `rollouts/`, `deliverables/`, `decisions/`, `INDEX.md`) with prompt-injection boundary guards (`EVIDENCE_BOUNDARY`) for `w0m-sdlc-review`, `w0m-ticket-audit`, and `doubt-driven-development` subagents instead of truncating large diffs/logs in prompts.
4. **Content-Addressed Runmark Fingerprinting (`fingerprint` + `why_not`, `harness2/core/runmark.py:36-108`)**:
   - Atomic completion markers carrying the configuration digest and a single-sentence `why_not()` cache-invalidation diagnostic for `run_suites.py` and pre-push certifications.
5. **Anonymous Candidate Selection (`POOL_MIXED_SELECT`, `harness2/core/prompts.py:66-83`)**:
   - Shuffled, anonymous candidate evaluation where keeping the unmodified baseline (`KEEP_BASE`) is explicitly a valid first-class outcome, preventing over-editing bias in `doubt-driven-development` and `w0m-personnel` resume synthesis.

