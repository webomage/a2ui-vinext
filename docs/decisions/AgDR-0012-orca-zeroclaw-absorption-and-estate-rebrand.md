---
id: AgDR-0012
title: "Mandatory w0m-* estate rebrand and repository migration to github.com/webomage"
timestamp: 2026-10-22T00:00:00Z
agent: antigravity
model: claude-opus-4-6
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T567
---

# AgDR-0012 — Mandatory `w0m-*` estate rebrand and repository migration to `github.com/webomage`

## Y-statement

> In the context of **ten estate repositories and fork remotes still living under personal `github.com/casualuser/*` with fragmented historical naming (`webomage.com`, `api.webomage.com`, `wom7func`, `wom7*`, `k7*`) while `w0m` is the canonical platform brand and `github.com/webomage` is the organization**, facing **a high blast radius across 11 reference classes (git remotes, local folders, `.w0m/sdlc.json`, `stacks-policy.json`, `agent_tree.py`, `release.py`, `install_excludes.py`, Cloudflare Worker scripts, and Infisical paths)**, we decided **to make the `w0m-*` rebrand and migration of all estate repositories to `github.com/webomage/w0m-*` mandatory (with `wom7func` renamed once to `w0m-cf` per [[T491]] Option B, and `k7*` TUIs unified into the `w0m` CLI), executed in 4 atomic, gate-verified stages under [[T567]]**, to achieve **one cohesive `w0m` brand and organization-owned repository topology (`github.com/webomage/w0m*`) without breaking active deploys or renaming `wom7func` twice**, accepting **the staged engineering effort and the requirement that `just name-refs <old-name> --gate` and `T509` root-first decoupling gate the folder cutover**.

## Context

Originally recorded as `status: proposed` on 2026-09-11 from three strategy/spec documents (`2026-09-11-analysis-orca-vs-zeroclaw-unification.md`, `2026-09-11-spec-w0m-fullsize-orca-zeroclaw-and-rebranding-research.md`, `2026-09-11-strategy-unified-w0m-ecosystem-orca-rebranding.md`).

On **2026-10-22**, the owner reviewed all 40 AgDRs and locked the decision:
1. **Rebranding `wom7*`/`k7*` to `w0m-*` and moving all repositories to our GitHub organization is mandatory** (despite its complexity).
2. Because `github.com/w0m` is occupied by an unrelated third-party GitHub user and `github.com/webomage` is our canonical GitHub Organization (per owner direction 2026-10-18), the target repository namespace is **`github.com/webomage/w0m*`**.
3. **Hyphenated `w0m-*` naming is locked** for all member repositories and local directories, and **`wom7func` becomes `w0m-cf`** (solving [[T491]] Option B in the same pass so the Cloudflare repo is renamed once rather than twice).

### Target Repository & Directory Mapping

| Current Local Path | Current GitHub Remote | Target Local Path | Target GitHub Remote (`github.com/webomage`) | Stack / Role |
|---|---|---|---|---|
| `.` (`@wom` root) | `casualuser/w0m` | `.` (`@wom` root) | **`webomage/w0m`** | Umbrella workspace root & SDLC orchestrator |
| `wom7web` | `casualuser/webomage.com` | **`w0m-web`** | **`webomage/w0m-web`** | Canonical web monorepo (Astro apps + shared packages) |
| `wom7api` | `casualuser/api.webomage.com` | **`w0m-api`** | **`webomage/w0m-api`** | Backend API, Supabase migrations, edge functions & workflows |
| `wom7func` | `casualuser/wom7func` | **`w0m-cf`** | **`webomage/w0m-cf`** | Cloudflare Worker crons & ATS routines (resolves [[T491]]) |
| `wom7ext` | `casualuser/wom7ext` | **`w0m-ext`** | **`webomage/w0m-ext`** | Browser extensions (Manifest V3 clipper & command runner) |
| `wom7sec` | `casualuser/wom7sec` | **`w0m-sec`** | **`webomage/w0m-sec`** | Security probes, authz RLS matrix & red-team suite |
| `wom7skills` | `casualuser/wom7skills` | **`w0m-skills`** | **`webomage/w0m-skills`** | Canonical Agent Skills registry & sync tooling |
| `wom7mlx` | `casualuser/wom7mlx` | **`w0m-mlx`** | **`webomage/w0m-mlx`** | Apple Silicon MLX local inference subsystem |
| `wom7ava` | `casualuser/wom7ava` | **`w0m-ava`** | **`webomage/w0m-ava`** | Avatar generation subsystem |
| `wom7clips` | `casualuser/wom7clips` | **`w0m-clips`** | **`webomage/w0m-clips`** | Media/video clip subsystem |
| `wom7pr/orca` | `casualuser/orca` | **`w0m-pr/w0m-orca`** | **`webomage/w0m-orca`** | Flagship desktop AI IDE & visual cockpit |

### Developer CLI Consolidation (`k7*` → `w0m`)

- Disjoint `k7*` terminal binaries (`k7d`, `k7s`, `k7c`, `k7llm`, `k7spec`, `k7tg`) converge into subcommands of the unified **`w0m` CLI** (`w0m vm`, `w0m k8s`, `w0m cloud`, `w0m llm`, `w0m spec`, `w0m notify`).

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Reject or indefinitely defer the rebrand | Zero migration churn | Leaves 3 competing naming schemes (`webomage.com`/`wom7*`/`k7*`/`w0m`) and personal `casualuser/*` remotes permanently across the estate | Rejected (Owner 2026-10-22: rebrand & GH move is mandatory) |
| Compact `w0m*` (`w0mweb`, `w0mapi`, `w0mcf`) | Slightly shorter folder names | Harder to read visually (`w0mmlx`, `w0mskills`) and diverges from `w0m-sdlc-*` / `w0m-orca` hyphenated convention | Rejected |
| **Hyphenated `w0m-*` under `github.com/webomage` (`webomage/w0m`, `webomage/w0m-web`, `webomage/w0m-api`, `webomage/w0m-cf`, …) executed in 4 atomic stages** | Clean visual hierarchy; aligns with `w0m-sdlc-*` skills; folds [[T491]] (`w0m-cf`) into one rename; staged cutover prevents deploy breakage | Requires disciplined 4-stage execution across 11 reference surfaces | **Accepted (Owner 2026-10-22)** |

## Decision

1. **Status flipped from `proposed` to `accepted` (2026-10-22).** Tracked in **[[T567]]** (with [[T491]] AC1 satisfied by choosing `w0m-cf`).
2. **Execute in 4 atomic stages to guarantee zero deploy regression:**
   - **Stage 1 — GitHub Org Transfer & Remote Cutover (Zero Local Path Churn):**
     - Ensure `webomage` org PAT policy (`<= 366 days` lifetime) and [[T306]] work identities are ready.
     - Transfer/rename the GitHub repositories from `casualuser/*` to `github.com/webomage/w0m` and `github.com/webomage/w0m-*` (GitHub preserves automatic 301 redirects for git/GHCR).
     - Repoint `git remote set-url origin` across the live checkout, `~/.w0m/confirmed/w0m`, and `release.py`, keeping local directory names unchanged during Stage 1.
   - **Stage 2 — Finish Root-First Decoupling ([[T509]]):**
     - Complete [[T509]] so cross-repo relative symlinks (`wom7web/justfile -> ../wom7api/justfile`, `wom7func/justfile -> ../wom7api/justfile`) are eliminated before any local folder rename.
   - **Stage 3 — Coordinated Local Directory & Governance Cutover (`wom7*` → `w0m-*`):**
     - Using `just name-refs <old> --files` before and `just name-refs <old> --gate` after, atomically rename local directories (`wom7web` → `w0m-web`, `wom7api` → `w0m-api`, `wom7func` → `w0m-cf`, `wom7ext` → `w0m-ext`, `wom7sec` → `w0m-sec`, `wom7skills` → `w0m-skills`, `wom7mlx` → `w0m-mlx`, `wom7ava` → `w0m-ava`, `wom7clips` → `w0m-clips`) and update `.w0m/sdlc.json`, `stacks-policy.json`, `layout-policy.json`, `install_excludes.py`, `release.py`, `agent_tree.py`, and `.serena/project.yml`.
     - Keep PostgreSQL internal identifiers (`wom_*` triggers/functions) and historical migration filenames untouched.
   - **Stage 4 — Deployed Worker Script Names & `k7*` → `w0m` CLI Convergence:**
     - Keep Cloudflare Worker script names (`wom7api`, `wom7func` in `wrangler.jsonc`) pinned during Stage 3 so live cron triggers, Durable Objects, and `WORKERS_WEBHOOK_URL` never break; rename Worker scripts only in a dedicated secret-rotation window if desired.
     - Unify `k7*` developer TUIs into subcommands of the `w0m` CLI.

## Consequences

- **Positive:** Eliminates the obsolete "7" counter (`wom7*`, `k7*`) and personal `casualuser/*` repo URLs; establishes a single `github.com/webomage/w0m*` identity across all repos, tools, and skills; resolves [[T491]] without a double rename.
- **Negative / Trade-off:** Every active agent worktree (`~/.w0m/work/*`) must be landed or removed before Stage 3's folder cutover, and all 11 reference classes must pass `just name-refs --gate`.
