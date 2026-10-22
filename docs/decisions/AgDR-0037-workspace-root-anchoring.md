---
id: AgDR-0037
title: "Workspace-Root Anchoring for Skills, Tools, and Estate SDLC Contract"
timestamp: 2026-10-22T12:25:00-05:00
agent: antigravity
model: claude-opus-4-6
trigger: user-prompt
status: executed
superseded_by:
supersedes:
ticket: T316
---

# AgDR-0037 — Workspace-Root Anchoring for Skills, Tools, and Estate SDLC Contract

## Y-statement

> In the context of **multi-repo estate (`@wom`) and half-managed/self-managed client workspaces (`bridgeroad-w0m`, `k7`)**, facing **the risk of polluting third-party client repositories (`BridgeMvp`) with w0m-owned skills/config and hardcoding component-repo paths (`wom7web/.w0m/sdlc.json`) across sibling repos (`wom7api/scripts/supabase_limits.py:42`)**, we decided **to anchor `.w0m/sdlc.json`, `.agents/skills`, and `.claude/skills` at the workspace root one level above nested code repositories while keeping stack-specific runtime scripts, migrations, and app builds inside their respective member repositories** to achieve **zero client-repo pollution and uniform root-first contract resolution**, accepting **that cross-repo scripts must resolve `.w0m/sdlc.json` root-first and `install_generic.ts` must enforce a mechanical refusal guard against nested `repos` targets**.

## Context

- Under `[[T294]]` and `[[T412]]`, the `.w0m/sdlc.json` contract moved to the workspace root (`@wom/.w0m/sdlc.json` for the estate; `bridgeroad-w0m/.w0m/sdlc.json` for BridgeRoad).
- However, measured live on `2026-09-05` and `2026-10-22`:
  1. `bridgeroad-w0m` (`/home/aleksei/Projects/_proj/bridgeroad`) carried `.w0m/sdlc.json` at its workspace root, but had zero installed skills (`.agents/skills` and `.claude/skills` were absent), while nothing mechanically stopped `wom7skills/scripts/install_generic.ts` from being pointed at its nested third-party client repo `BridgeMvp` (`BridgeRoad/bridgeroad-app`).
  2. `wom7skills/portability.jsonc` was named without indicating that it classifies **skills** universally across all client installs.
  3. Inside the w0m estate, `wom7api/scripts/supabase_limits.py:42` still hardcoded `SDLC = API.parent / "wom7web" / ".w0m" / "sdlc.json"` instead of resolving the workspace-root `@wom/.w0m/sdlc.json` first.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Option A — Install skills & contract inside each nested code repo (`BridgeMvp`, `wom7web`)** | Every repo is self-contained when opened in isolation. | Pollutes third-party client repos (`BridgeMvp`), risks leaking w0m config/secrets (`T294` incident), and duplicates skill trees across sibling repos. | **Rejected** |
| **Option B — Hoist ALL scripts, migrations, and app configs into the workspace root repo** | Single top-level directory for every script. | Violates stack isolation (`wom7api` migrations, `wom7web` Astro build, `wom7skills` TS CLI belong with their own `package.json` and tests); creates a monolithic root repo. | **Rejected** |
| **Option C — Workspace-root anchoring for `.w0m/`, `.agents/skills`, `.claude/skills`, and estate policies (`project/policies/`), while keeping repo-scoped build/runtime scripts in member repos (Recommended)** | Keeps client code repos (`BridgeMvp`) 100% clean; eliminates hardcoded `wom7web/.w0m/sdlc.json` assumptions; preserves member-repo autonomy for tests/migrations. | Requires a mechanical refusal guard in `install_generic.ts` against nested `repos` paths and root-first `SDLC` resolution in cross-repo scripts (`supabase_limits.py:42`). | **Accepted & Executed** |

## Decision

1. **What Hoists to the Workspace Root (`@wom` and `<client>-w0m`) — YES**:
   - `.w0m/sdlc.json`, `.w0m/skills.json`, `.w0m/skills.lock.json` (workspace contract and skill lock).
   - `.agents/skills/` and `.claude/skills/` for workspace-shaped client projects (`bridgeroad-w0m`), enforced by `checkNestedClientRepoGuard()` in `wom7skills/scripts/install_generic.ts` which refuses to install into any nested path declared under `repos` in `clients-policy.json` or parent `.w0m/sdlc.json`.
   - Estate-wide governance policies (`@wom/project/policies/*.json`) and ticket/decision registers (`@wom/.tasks/`, `@wom/docs/decisions/`).
   - Cross-repo `SDLC` resolution in `wom7api/scripts/supabase_limits.py:42`, updated to resolve `API.parent / ".w0m" / "sdlc.json"` root-first before falling back to `wom7web/.w0m/sdlc.json`.
2. **What Remains Inside Component / Member Repositories — NO (Do Not Hoist)**:
   - `wom7skills/` canonical skill sources (`wom7skills/skills/`), `wom7skills/skill-portability.jsonc` (renamed from `portability.jsonc` under `T316` AC1), and the `tsx` skill toolchain.
   - `wom7api/` Supabase migrations (`supabase/migrations/`), edge functions, and DB quota scripts (`wom7api/scripts/supabase_limits.py`).
   - `wom7web/` Astro apps (`apps/web`, `apps/cp`), `@webomage/ui` design system, and `wom7web/project/scripts/` implementation runners.
   - `wom7func/`, `wom7ext/`, `wom7sec/`, `wom7mlx/wom7mlx` runtime code and package manifests.

## Consequences

- **Positive**:
  - `bridgeroad-w0m` now ships all 35 portable skills at `/home/aleksei/Projects/_proj/bridgeroad/{.agents,.claude}/skills` while `BridgeMvp` (`bridgeroad-app`) has zero files touched.
  - Pointing `install_generic.ts` at `BridgeMvp` fails closed with exit code `1`.
  - `wom7skills/skill-portability.jsonc` clearly states what it classifies (`skill-portability`), with zero remaining active references to `portability.jsonc`.
  - `wom7api/scripts/supabase_limits.py:42` resolves `@wom/.w0m/sdlc.json` root-first.
- **Negative**:
  - Developers opening a nested client repo (`BridgeMvp`) directly in an IDE rather than opening the parent workspace (`bridgeroad-w0m`) will not see workspace-root `.agents/skills` unless they open the workspace root (which is the intended workflow under `[[T268]]` and `[[T294]]`).

## What this does NOT decide

- This decision does not move `wom7web/project/scripts/*.py` out of `wom7web`; root `justfile` delegates to them from `@wom` (`[[T412]]`), and relocating those implementation files would churn test imports for no governance benefit.
