# `@wom` Estate Infrastructure & System Architecture

> **Canonical Workspace Root Architecture Entrypoint (`AGENTS.md`, `T680`):** This document defines the live multi-repository topology, Free-Tier-First cloud hierarchy (`AgDR-0055`), per-project Mistral & Obsidian data isolation (`T677`), Orca ACP + `LinuxOnTab` + `@k7` module runtime (`T679`), and Infisical zero-`.env` deployment pipeline (`AgDR-0057`).

---

## 1. Estate Repository Topology

The `@wom` workspace root orchestrates the first-party estate repositories alongside the `@k7` Rust TUI toolchain and `w0m-pr/` upstream open-source forks:

| Repository / Surface | Primary Stack | Role & Live Runtime Boundary |
|---|---|---|
| **`@wom` (root)** | Python 3.12+ · `just` · Git | Estate control plane, `.tasks/T##.md` tracker, `STATE.md`, `LESSONS.md`, `scripts/session_complete.py`, `scripts/deploy_cert.py`, `scripts/mistral_project_scope.py`, `scripts/w0m_prs.py` |
| **`w0m-web`** | Astro 7.3 SSR · Svelte 5 · Tailwind 4 | 4 Cloudflare Workers web apps (`web`, `cp`, `me`, `demo`; `AgDR-0056` retired `join` & `job` into `me`), 9 `packages/*` libraries, `@webomage/ui` design system (`25` canonical primitives), OpenSpec specs, and SDLC gates |
| **`w0m-api`** | Supabase (Postgres 15 + Deno 2) · Hono | 393 SQL migrations, 4-axis RBAC (`public.wom_can`), 64 Supabase Edge Functions (`--frozen=true`), Hono `>=4.13.16` API worker (`wom7api`), `ChatMemoryDO` SQLite DO, and 19 Cloudflare Workflows |
| **`w0m-cf`** | Cloudflare Workers · Hono · Rust/WASM | Account-level cron triggers (`5/5` free-tier crons), `POST /mcp` Streamable HTTP MCP server, `#![no_std]` `w0m-wasm-utils` (`550 B`), `/ai/chat` & `/ai/embed` Workers AI + Mistral Free-Tier proxy (`wom7func`) |
| **`w0m-ext`** | Cross-Browser MV3 · TypeScript · WebMCP | Desktop & iOS Safari/Orion MV3 extensions (`Webomage Agent`, 17-platform `specEngine`, Orca loader `T710`), `obsidian-w0m` R2 delta sync plugin, WebSocket/WebMCP bridge |
| **`w0m-sec`** | Python · Docker `--network none` · Pytest | Air-gapped containment runner, RFC 9116 `security.txt` audit, and `AgDR-0047` Touch-ID-gated bug-bounty governance |
| **`w0m-skills`** | Agent Skill Spec v1.0 · TypeScript (`tsx`) | 69 canonical skills (`79` registry entries, `71` `NVIDIA/SkillSpector v2.12.0`-audited units), 7-dialect SDD (`GENERIC-SDLC-SET.md`), and Elephant-Goldfish (`egm-*`) workflows |
| **`w0m-mlx/w0m-mlx`** | Apple MLX (`mlx-rs` 0.33 + `omlx` 0.7.3) | Local Apple Silicon Metal inference (`wom7-mlx-rs` Rust server + `omlx` `:8888` + `mlx-vlm` Gemma 4 & FLUX `:8080`) and `headroom` context compression |
| **`@k7` (`k7hub` + 11 crates)** | Rust 1.95 · `ratatui` · `ratzilla` WASM | Unified `@k7` Super-TUI (`k7`) + standalone modules (`k7env`, `k7pwd`, `k7d`, `k7s`, `k7c`, `k7llm`, `k7spec`, `k7sol`, `k7tg`, `k7kb`, `k7log`) + `k7hub.wasm` (`wasm32-unknown-unknown` Git TUI Browser, `T708`) |
| **`w0m-pr/*`** | Git Forks (`github.com/webomage/*`) | 23 local / 48 org-governed upstream forks (`AgDR-0058` 6-gate `w0m_prs.py`), including `SkillSpector`, `orca`, `linuxontab`, `graphify`, `headroom`, `omlx`, `mlx-rs`, `mlx-vlm`, `serena`, `virtual-fido` |

```mermaid
flowchart TD
    subgraph ClientLayer["Client, IDE & Browser Layer"]
        Browser["Browser Apps (web, cp, me, demo)"]
        Ext["w0m-ext (Desktop + iOS MV3 + obsidian-w0m + WebMCP)"]
        Orca["Orca ACP Desktop / CLI / Mobile"]
        LOT["LinuxOnTab (v86 WASM Alpine + @k7 Module Bar)"]
        K7["@k7 Unified Super-TUI (k7hub + k7hub.wasm Git Browser)"]
    end

    subgraph EdgeLayer["Tier 1: Cloudflare Free-Tier Edge (AgDR-0055)"]
        CFPages["Cloudflare Workers SSR (4 Apps: web, cp, me, demo)"]
        CFWork["w0m-cf (Crons, Queues, /ai/chat, /ai/embed)"]
        CFApi["w0m-api Worker (Hono + 19 CF Workflows)"]
        CFR2["Cloudflare R2 ($0 Egress Vaults, Media & Artifacts)"]
        CFKV["Cloudflare KV & Turnstile Bot Gate"]
        CFAI["Cloudflare Workers AI (Mistral Small 3.1, Llama 3.3 70B, BGE-M3, Qwen3-Embed)"]
    end

    subgraph AddonAI["Tier 1b: Per-Project Mistral Free-Tier Add-On (T677)"]
        Mistral["Mistral API Free Tier (mistral-small-latest, codestral-latest, mistral-embed)"]
        ObsidianScope["Private Obsidian Project Vault Scope (<project>@webomage.com)"]
    end

    subgraph DataLayer["Tier 2: Supabase Free-Tier Relational Backbone (AgDR-0003)"]
        GoTrue["Supabase Auth (GoTrue JWT + Passkeys)"]
        PG["PostgreSQL 15 (4-Axis RBAC, RLS, Append-Only *_audit_log)"]
        EdgeFn["Supabase Edge Functions (ai-router.ts, chat-core, manage-document)"]
    end

    Browser --> CFPages
    Ext --> EdgeFn
    Orca --> LOT
    Orca --> K7
    CFPages --> GoTrue
    CFPages --> PG
    CFPages --> EdgeFn
    CFPages --> CFR2
    CFPages --> CFKV
    EdgeFn --> CFWork
    EdgeFn --> Mistral
    CFWork --> CFAI
    CFWork --> Mistral
    CFWork --> CFApi
    Mistral --> ObsidianScope
```

---

## 2. Free-Tier-First Resource Hierarchy (`AgDR-0055`, `AgDR-0003`, `AgDR-0043`)

1. **Client-Side First (`$0` Server Compute):**
   - Compress images (`WebP`/`AVIF`), compute `SHA-256` content digests, validate schemas, and execute disposable Linux sandboxes (`LinuxOnTab` `v86.wasm` in browser RAM) on the client before touching edge compute.
2. **Cloudflare Free Tier First (Edge Compute, Object Storage, Cache, Bot Gate & Primary AI):**
   - **Compute & SSR:** 5 Astro SSR Worker apps + `wom7api` + `wom7func` (`100k req/day` free tier, Rust->WASM hot paths `< 300 KB` gzipped per `AgDR-0044`).
   - **Object & Vault Storage:** Cloudflare R2 (`10 GB/month` free, **$0 egress**) stores all Obsidian vault snapshots, resume PDFs, avatars, and media blobs (`projects/<slug>/vault` -> `r2://<slug>/`).
   - **Primary AI:** Cloudflare Workers AI (`@cf/mistralai/mistral-small-3.1-24b-instruct`, `@cf/meta/llama-3.3-70b-instruct-fp8-fast`, `@cf/baai/bge-m3`, `@cf/qwen/qwen3-embedding-0.6b` 1024-dim).
3. **Mistral Free-Tier Add-On & Per-Project Private Obsidian Scope (`T677`):**
   - Each enabled project in [`project/policies/clients-policy.json`](../project/policies/clients-policy.json) (`w0m`, `1945`, `artemio`, `servicios777`, `personaje0`, `bridgeroad`, `k7`, `solar`, `mantrabox`, `pandatransfer`) maps to a dedicated Mistral account `<project>@webomage.com` and an isolated Infisical secret `MISTRAL_API_KEY_<PROJECT_UPPER>`.
   - Enforces **fail-closed tenant isolation** ([`scripts/mistral_project_scope.py`](../scripts/mistral_project_scope.py)): non-`w0m` client projects have `allow_global_key_fallback = False` and `cross_project_access = False`, confining Obsidian ACP and RAG context strictly to `w0m-web/projects/<slug>/vault`.
4. **Supabase Free Tier Second (Auth, RLS Metadata & Audit Ledger Only):**
   - Strictly reserved for GoTrue Authentication, PostgreSQL 15 RLS-governed relational rows (`500 MB` cap), and compact append-only `*_audit_log` triggers (`T614`). Never store binary blobs or high-frequency unauthenticated telemetry in Supabase.

---

## 3. Unified `@k7` Module System, Orca ACP & `LinuxOnTab` Runtime (`T677`, `T679`)

### 3.1 Orca as First-Class Agent Client Protocol (ACP) Client
- Orca (`w0m-pr/orca`, `src/main/acp/`, listed on `agentclientprotocol.com/get-started/clients` via `PR #2770`) provides Desktop, CLI (`orcad` / `orca`), and Mobile ACP client surfaces driving `opencode`, `antigravity`, `claude`, `codex`, `gemini`, and `mistral-vibe` (`vibe`) across isolated Git worktrees.

### 3.2 Unified `@k7` Super-TUI (`k7hub`) & 9 Standalone Crates
- [`k7hub`](file:///home/aleksei/Projects/!self/k7/k7hub/k7hub/src/main.rs) (binary `k7`) unites all 9 `@k7` tools in a single multi-tab `ratatui` interface (`[1]` `env`, `[2]` `pwd`, `[3]` `vm`, `[4]` `k8s`, `[5]` `cloud`, `[6]` `llm`, `[7]` `spec`, `[8]` `sol`, `[9]` `tg`) with a shared Infisical environment (`dev`/`beta`/`prod`) and cross-module `k7pwd -> k7env` secret bus, while every crate remains runnable standalone (`k7 run <module>`).

### 3.3 `LinuxOnTab` (`v86` WASM Alpine Linux) Browser & Orca Module Tabs
- Forked at `w0m-pr/linuxontab` (`github.com/webomage/linuxontab`, branch `feat/k7-orca-module-bar`) and served locally with mandatory `COOP`/`COEP` `SharedArrayBuffer` headers via [`scripts/linuxontab_serve.py`](../scripts/linuxontab_serve.py) (`just linuxontab-serve`).
- Supports `?autoboot=1&iso=alpine.iso&k7=<slug>&project=<project>&env=<env>` and an interactive `@k7` module bar (`#k7-module` + `#k7-run`) executing `/local/k7-module.sh` inside the Alpine guest.

---

## 4. Zero-`.env` Infisical Secret Pipeline & Tree-Set-Certified Deploy (`AgDR-0057`)

- **Zero `.env` Files in Production or Repo:** All secrets are stored in Infisical (`dev` and `beta` environments, workspace `87a1718d-17c6-4c5e-b0c1-f8bb2fd9d13c`) and injected into processes via `infisical run --env=<env> --silent -- <cmd>`.
- **Operator Secret Tooling:** Generate CSPRNG secrets with `k7pwd` (`/dev/urandom` 24-char alnum+sym, `openssl rand -base64 16`, `diceware`, `prefixed-api-key`) and audit/bind Infisical profiles with `k7env` and `just mistral-scope-status`.
- **Isolated Agent Worktrees & Certified Landing (`AgDR-0032`, `AgDR-0057`):**
  - Agents work exclusively inside `~/.w0m/work/<name>/w0m` (`just agent-tree <name>`) and land via `just session-complete T##`, which runs 14 verification gates, certifies the estate tree-set digest (`scripts/deploy_cert.py`), pushes member repos before `@wom` root, fast-forwards the canonical checkout, and verifies `just state-check` last.

---

## 5. Quick Infrastructure Verification Commands

Verify estate preflight, per-project Mistral/Obsidian isolation, and `LinuxOnTab` readiness:

```bash
cd ~/Projects/'!self'/w0m
just preflight --fast
just mistral-scope-status
just linuxontab-serve 8770 --dry-run
just state-check
```
