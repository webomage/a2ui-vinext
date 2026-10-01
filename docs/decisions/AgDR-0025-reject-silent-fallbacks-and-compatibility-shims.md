---
id: AgDR-0025
title: "Reject Silent Fallbacks, Backward-Compatibility Shims, and Shadow Symlinks in Estate Architecture"
timestamp: 2026-09-21
agent: antigravity
model: gemini-2.5-pro
trigger: architectural-direction
status: accepted
superseded_by:
supersedes:
ticket: T414
---

# AgDR-0025 — Reject Silent Fallbacks, Backward-Compatibility Shims, and Shadow Symlinks in Estate Architecture

## Y-statement

> In the context of elevating estate-wide registers (`LESSONS.md`, `STATE.md`, `TECH-DEBT.md`, `ROADMAP.md`), SDLC machinery, and governance tooling to the workspace root (`@wom`), facing recurring architectural degradation from multi-tier search ladders, permanent compatibility wrappers, and legacy symlinks, we decided **to enforce three non-negotiable architectural invariants: (1) fail fast with zero silent fallbacks, (2) require clean atomic cutovers over backward-compatibility shims, and (3) ban shadow symlinks in legacy locations**, to establish pure Single Source of Truth (SSOT), prevent invisible state corruption, and ensure immediate observability of configuration drift across all tools and agents.

## Context & Problem

Over multiple development iterations across the w0m estate, tool and register migrations frequently introduced three well-intentioned but architecturally corrosive patterns:

1. **Silent Fallback Ladders (The "Fail-Slow" Pattern)**:
   Scripts and loaders often contained defensive fallback cascades:
   ```python
   # Anti-pattern: Defensive fallback ladder
   if (root / "CONFIG.json").is_file():
       path = root / "CONFIG.json"
   elif (subrepo / "CONFIG.json").is_file():
       path = subrepo / "CONFIG.json"
   else:
       path = default_fallback
   ```
   While intended to make scripts "resilient", this pattern masks missing files, path typos, and incomplete migrations. If a canonical file is deleted or misplaced, the tool silently falls back to a stale legacy copy. Execution succeeds with exit code 0, but operates on incorrect state. In multi-agent environments, this creates deceptive feedback loops where agents infer that legacy paths remain authoritative.

2. **Backward-Compatibility Shims in an Owned Monorepo (The "Accretion Trap")**:
   When tools or APIs were relocated, compatibility wrappers were left behind in legacy locations to avoid breaking unmigrated scripts. In a distributed multi-vendor ecosystem with uncoordinated third-party clients, deprecation shims are a necessary compromise. However, in an **owned monorepo/workspace where 100% of callers and configurations reside in the same repository tree**, permanent shims create accretion debt. Callers never get updated, dual write surfaces emerge, and the codebase accumulates dead indirection layers that obscure system architecture.

3. **Shadow Symlinks as Sneaky Fallbacks (Violation of Single Source of Truth)**:
   When files (`TASKS.md`, `sdlc.json`, scripts) were elevated to the workspace root, symlinks were created in `wom7web/` to prevent breakage. In practice, a shadow symlink is simply a filesystem-level silent fallback. It directly violates Single Source of Truth:
   - **Search & Tool Confusion**: `git grep`, `ripgrep`, language servers, and AST analyzers index both the canonical file and the symlink, producing double-counted hits and confusing search ranking.
   - **Agent Misdirection**: Autonomous agents discovering the symlink continue to use legacy relative paths (e.g., `cd ../wom7web && ...`) rather than adopting canonical root commands.
   - **Migration Incompleteness**: Because callers succeed through the symlink, developers never discover or fix the outdated call sites.

## Industry Evidence & Rationale

These three patterns violate foundational software engineering principles documented across industry literature:

### 1. Fail Fast, Never Fall Back Silently
- **Martin Fowler (*Fail Fast*, IEEE Software / Bliki)**:
  > *"The most fundamental principle of error handling is to fail fast... You'd rather know immediately that something is wrong than have the error propagate and cause confusion later."*
  Silent fallbacks convert clear configuration failures into subtle, hard-to-trace semantic corruptions downstream. If a canonical register or configuration is expected at a known path, failure to locate it must halt execution loudly with a non-zero exit code.
- **Michael Nygard (*Release It! Design and Deploy Production-Ready Software*)**:
  Nygard classifies silent fallbacks and uncontrolled recovery as primary culprits in cascading system failures, masking degradation until an entire cluster collapses from unobservable drift.

### 2. Atomic Cutover Over Backward-Compatibility Shims
- **Google Monorepo Practice (*Software Engineering at Google*, Winters, Manshreck, Wright — Chapter 22 "Large-Scale Changes" & Chapter 18 "Atomic Changes")**:
  In a monolithic codebase, the primary architectural advantage is the ability to make **atomic changes**—updating an interface and 100% of its call sites across the entire repository in a single commit. The authors emphasize that deprecation shims in a monorepo become permanent liabilities because consumers have no incentive to migrate. Instead, monorepo maintenance mandates updating all call sites at head and immediately retiring the old interface.
- **Hyrum's Law**:
  > *"With a sufficient number of users of an API, it does not matter what you promise in the contract: all observable behaviors of your system will be depended on by somebody."*
  Leaving a backward-compatibility shim guarantees that new code, scripts, or agents will latch onto the shim's behavior, making eventual removal exponentially harder.

### 3. Pure Single Source of Truth (Zero Shadow Symlinks)
- **Single Source of Truth (SSOT)** requires that every data element and operational contract has exactly one canonical, unambiguous representation and location.
- Placing symlinks in old locations maintains the illusion that the old location is active. Removing the legacy file entirely forces immediate compiler/runtime/test failure at any obsolete call site, driving the codebase to total alignment.

## Decision: The Three Non-Negotiable Estate Invariants

Effective immediately with Phase 2 Elevation (T414), all tooling, configurations, and documentation across the w0m estate MUST adhere to the following invariants:

1. **Rule 1: Fail Fast, Never Fall Back Silently (Ban Silent Fallbacks)**
   - Every script, test, and loader MUST target its canonical path directly.
   - Multi-path candidate search ladders (`candidates = [pathA, pathB, pathC]`) that silently catch `FileNotFoundError` or check existence sequentially across multiple repositories are strictly forbidden.
   - If a required canonical resource is missing, the tool MUST exit non-zero immediately with an explicit error naming the missing canonical path.

2. **Rule 2: Clean Cutover Over Backward-Compat Shims (Ban Monorepo Shims)**
   - When any script, configuration, or data file is moved or refactored, 100% of callers, tests, justfiles, and hook declarations MUST be updated atomically in the same commit.
   - Do NOT introduce forwarder scripts, stub wrappers, or dual-path aliases in the old location.

3. **Rule 3: Zero Shadow Symlinks (Pure Single Source of Truth)**
   - When an asset is moved to the workspace root (`@wom`), the legacy file in `wom7web/` (or any subrepo) MUST be deleted completely.
   - No filesystem symlinks may be placed in legacy locations to alias root files.
   - An asset exists at exactly one physical location in the workspace.

## Consequences

### Positive
- **True Single Source of Truth**: Eliminates duplicate search hits, double indexing, and confusing cross-repo relative path hops.
- **Immediate Drift Detection**: Any broken caller or outdated documentation breaks loudly and immediately, preventing silent decay.
- **Cleaner Agent Guidance**: Autonomous agents observe only canonical root paths, eliminating confusion over whether to invoke tools from `wom7web` or `@wom`.
- **Faster Workflows**: Governance scripts running at `@wom/` execute directly without spinning up unnecessary Astro/Vite subrepo build tooling.

### Negative / Trade-offs Accepted
- **Refactoring Rigor**: Moving any tool requires auditing and updating all 7 estate repositories atomically. Quick "move and symlink" shortcuts are prohibited.
- **No Grace Period**: Outdated scripts or unmerged agent branches referencing legacy paths will fail immediately upon execution rather than silently succeeding. This is accepted and desired.
