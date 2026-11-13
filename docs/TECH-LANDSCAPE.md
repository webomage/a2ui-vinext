# `@wom` (`w0m`) Canonical Technology Landscape Reference

> **Canonical Estate Technology Encyclopedia (`docs/TECH-LANDSCAPE.md`, `T734`, `T735`):** Paired with [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) and the self-contained interactive visual HTML explainer [`docs/visuals/w0m-tech-landscape-explainer.html`](visuals/w0m-tech-landscape-explainer.html) (`just tech-explainer`). Indexed in `~/.w0m/knowledge-index/corpus.sqlite` (`just kb-index` / `just kb-search`).

---

## 1. Executive Architecture Principles

1. **4-Tier Free-Tier-First Allocation (`AgDR-0055`, `AgDR-0003`, `AgDR-0043`):**
   - **Tier 0 (Client & Browser `$0` Compute):** Isomorphic FIPS 180-4 SHA-256 checksums (`prompt-workflow-library.ts`), `buildK7GitWasmTuiFrame` 5-flavour Git TUI frames (`k7-git-browser.ts`), `LinuxOnTab` (`v86` WASM Alpine sandbox), client-side Mermaid validation, and `WebMCP` (`navigator.modelContext`).
   - **Tier 1 (Cloudflare Free-Tier Edge Compute & `$0`-Egress Storage):** **6 active Cloudflare Workers** — `webomage` (`apps/web`), `webomage-cp` (`apps/cp`), `webomage-me` (`apps/me`), `webomage-demo` (`apps/demo`), `wom7api` (`w0m-api` with `19` Durable Workflow classes + `ChatMemoryDO`), and `wom7func` (`w0m-cf` with `5/5` account crons + stateless JSON-RPC `POST /mcp` + `550 B` `#![no_std]` Rust WASM) — backed by R2 (`wom-engagement-vaults` under prefix `engagements/eg-<slug>`, `wom-public-assets`), KV (`SESSION`, `SETTINGS`), Turnstile + `@webomage/fingerprint`, and Workers AI.
   - **Tier 1b (Project-Scoped Mistral Free Tier, `T677`):** Per-project Mistral accounts (`<project>@webomage.com`) and Infisical `MISTRAL_API_KEY_<PROJECT_UPPER>` keys strictly isolated to `w0m-web/projects/<slug>/vault` (`allow_global_key_fallback = (pid == "w0m")` in `scripts/mistral_project_scope.py` — `False` for external client projects, `True` for `w0m` core).
   - **Tier 2 (Supabase Free-Tier Relational & Auth Ledger):** GoTrue Auth (`3` PKCE OAuth login providers: `google`, `linkedin_oidc`, `github`; TOTP MFA; WebAuthn/FIDO2 passkeys), PostgreSQL `17.6` (`w0m-api/supabase/baseline/schema.sql`, local CLI DB `:54322`; `393` SQL migrations, 4-axis RBAC `public.wom_can`, deterministic `public.hats`, append-only `*_audit_log` triggers), and `64` Deno 2 Edge Function directories (`63` active + decommissioned `trigger-hatchet-workflow/` stub, `--frozen=true`).
2. **Single-Branch `beta` Trunk & Certified Agent-Tree Delivery (`AgDR-0032`, `AgDR-0057`):**
   - Isolated 10-repo worktrees (`just agent-tree <name>`), `16` default `balance` / `18` `wise` `session-complete` verification gates (`4` in `ultra`), SHA-256 tree-set deploy certificates (`scripts/deploy_cert.py`), and atomic `HEAD:beta` landing (members first, `@wom` root last).
3. **First-Place Code, Agent & Secret Security (`just check-guardrails`):**
   - Simultaneous enforcement across code/dependencies (`gitleaks 8.30.1`, `osv-scanner 2.7.0` across `6` `pnpm-lock.yaml` lockfiles, `semgrep 1.183.0`, `ast-grep 0.51.0`, `worker_env_gate.py`, 4-axis RBAC red probes), agent skills/MCP (`NVIDIA/SkillSpector v2.12.0` across `71` unique skill roots + `skill_audit.ts` + `mcp_ratchet.py`), and Infisical zero-`.env` runtime secret injection (`71` active `beta` secrets; `AES-256-GCM` pre-prune backup of `44` retired keys).
4. **Graph-Before-Grep & Elephant-Goldfish Verification:**
   - Combines `codegraph v1.6.2` AST symbol graphs, `92,477`-node `graphify 0.9.100` (`136,105` edges), and `w0m_kb_vector.py` SQLite FTS5 BM25 + `128-dim` Randomized SVD Reciprocal Rank Fusion (`1,937` curated SHA-256-deduplicated docs / `19,011` chunks at `max_chars=1600`, or `1,605` docs / `16,718` chunks with `--no-archive`, in `corpus.sqlite`) with Google Elephant-Goldfish (`egm-*`) fresh-context adversarial verification.

---

## 2. Verified Stack & Inventory Matrix

| Layer | Technologies & Versions | Canonical Governance & Paths |
|---|---|---|
| **Estate Control Plane (`@wom`)** | Python `>=3.12` · `mypy` `min 1.15.0 / known_good 2.4.1 (host 2.4.0)` · `just` · `10` git repos (`@wom` root + `7` core repos + `2` companion repos `w0m-ava`, `w0m-clips`) · `77` pinned CLI tools (`22` required) · `16` `*-policy.json` (`23` `*.json`) in `project/policies/` (`23` `*-policy.json` estate-wide) | `justfile`, `.w0m/sdlc.json`, `project/policies/*.json` |
| **Web SSR & UI (`w0m-web`)** | Astro `7.3.3` · `@astrojs/cloudflare 14.3.4` · Svelte `5.56.4` resolved (`^5.56.7` spec; `220` `.svelte` files: `206` direct runes + `8` rune-free wrappers + `6` legacy `export let` files) · Vite `7.3.7` / Rolldown `1.2.14` · Tailwind `4.3.3` · TypeScript `6.0.3` · `9` workspace packages · `25` `@webomage/ui` primitives | `w0m-web/apps/{web,cp,me,demo}`, `w0m-web/packages/*`, `design-system/_ds_manifest.json` |
| **API, Workflows & DB (`w0m-api`)** | Hono `4.13.18` resolved (`>=4.13.16` floor, `wom7api`) · `19` Cloudflare Durable Workflow classes · `ChatMemoryDO` SQLite DO · PostgreSQL `17.6` (`393` SQL migrations, `public.wom_can`) · `64` Deno 2 Edge Function dirs (`63` active + `trigger-hatchet-workflow/`, `--frozen=true`) | `w0m-api/src/workflows/`, `w0m-api/supabase/{migrations,functions}/` |
| **Edge Crons, MCP & WASM (`w0m-cf`)** | Hono `4.13.18` (`>=4.13.16` floor, `wom7func` `:8790`) · `5/5` account cron triggers · stateless JSON-RPC `POST /mcp` · Workers AI + Mistral proxy · `#![no_std]` `w0m-wasm-utils` (`550 B` raw / `389 B` gzipped) | `w0m-cf/src/index.ts`, `w0m-cf/crates/w0m-wasm-utils/` |
| **Browser & Vault Extensions (`w0m-ext`)** | Desktop + iOS 16.4+ Safari/Orion + Orca Electron MV3 extension (`11` external platform `specs/*.json`, `16` host domains, authenticated HTTPS REST + ZeroClaw `:42617`; `:8008` WS retired per `AgDR-0039`) · `obsidian-w0m 1.0.0` R2 delta sync (`engagements/eg-<slug>`) | `w0m-ext/extension/`, `w0m-ext/obsidian-w0m/`, `scripts/orca_ext_install.py` |
| **Rust `@k7` Toolchain (`@k7`)** | Rust `>=1.95.0` (`known_good 1.99.1`) · `16` Cargo packages (`11` top-level dirs: `k7hub` + `k7env`, `k7pwd`, `k7d`, `k7s`, `k7c` [6 pkgs], `k7llm`, `k7spec`, `k7sol`, `k7tg`, `k7kb`; `9/11` top-level / `8/10` non-hub crates on `ratatui`) · `5`-flavour `k7hub::git_browser` (`wasm32-unknown-unknown`) | Sibling `../k7` checkout, `w0m-web/packages/lib/src/security/k7-git-browser.ts` |
| **Local Apple MLX & Knowledge (`w0m-mlx`)** | Optional companion listeners in `ports-policy.json`: `wom7-mlx-rs` (`mlx-rs 0.33.0`, `:1339/:1340`) · `omlx 0.7.3` (`:8888`) · `mlx-vlm 0.7.11` (`:8080`) · `headroom 0.39.0` (`:8787/:8788`) · `codegraph v1.6.2` · `graphify 0.9.100` · `w0m_kb_vector.py` (`corpus.sqlite`) | `w0m-mlx/w0m-mlx/`, `scripts/w0m_kb_vector.py`, `scripts/graph_health.py` |
| **Skills, SDD & Security (`w0m-skills`, `w0m-sec`)** | `69` top-level skill dirs (`79` registry entries, `42` deployed, `71` `SkillSpector v2.12.0`-scanned) · `7` SDD dialects · `14` governed MCPs (`5` in `.mcp.json`) · `w0m-sec` `--network none` containment · `377` registered test suites | `w0m-skills/`, `w0m-sec/`, `scripts/client_spec_bridge.py`, `w0m-web/project/test-suites.json` |
| **Upstream OSS Forks (`w0m-pr/*`)** | `23` local `w0m-pr/*` checkouts + `48` `FORKED_AI_TOOLS_CATALOG` entries (`63` distinct upstream forks) · `AgDR-0058` 6-gate `w0m_prs.py` | `scripts/w0m_prs.py`, `scripts/fork_catalog_sync.py` |

---

## 3. Deep Subsystem Reference

### 3.1 `w0m-web` Applications & 9 Shared Packages
- **Applications (`4` Cloudflare Workers):**
  1. `webomage` (`apps/web`, `:4321`): Marketing, `/services` & `/solutions` 1-click PKCE OAuth + fixed-price Stripe Checkout (`T723`), `/audit` read-only security/AI intake (`T711`), `/blueprints`, Pagefind `1.5.2`, RFC 9116 `security.txt`.
  2. `webomage-cp` (`apps/cp`, `:4325`): Unified Org/Client/Crew Control Plane, Onboarding Wizard + Services Configurator (`T703`), 7-dialect SDD selector (`T715`), full-scope HMAC Admin Impersonation (`/api/auth/impersonate-handoff`, `T722`), printable multi-page Audit PDF Dossiers (`T701`/`T704`), and `CrewToolkitAndTabLinuxConsole.svelte` (`@k7` Git TUI Browser, `T708`).
  3. `webomage-me` (`apps/me`, `:4323`): Unified Personal Identity & Talent Cloud (`AgDR-0056`), `.ics`/CalDAV Calendars (`T700`), GitHub-Issues Feature Voting & Roadmap Board (`/me/oss`, `/board/*`, `/api/board/*`, `T725`), and R2 Vault Gateway (`/api/vault/r2/*`).
  4. `webomage-demo` (`apps/demo`, `:4324`): Interactive sandbox tours and component showcase.
- **Shared Packages (`9`):** `@webomage/ui` (`25` canonical primitives), `@webomage/lib` (`0` `node:*` imports in browser barrel enforced by `browser-barrel-node-free.test.ts`), `@wom/authz`, `@webomage/webmcp`, `@webomage/fingerprint`, `@webomage/crawler`, `@wom/kyc` (WebAuthn FIDO2 + LATAM fiscal/ID validators), `@wom/logger`, and `mcp-aws-fundamentals`.

### 3.2 `w0m-api` & `w0m-cf` Edge Compute, Workflows & Data
- **`19` Cloudflare Durable Workflow Classes (`wom7api`):** `GamificationEventWorkflow`, `DomainScannerWorkflow`, `JobScannerWorkflow`, `LinkedinSyncWorkflow`, `LinkedinBroadcastWorkflow`, `LinkedinDataErasureWorkflow`, `CertEvaluatorWorkflow`, `CertIngestionWorkflow`, `JobAggregatorWorkflow`, `JobScorerWorkflow`, `VectorizeJobWorkflow`, `VectorizeProfileWorkflow`, `VectorizeVaultWorkflow`, `NewsletterWorkflow`, `CvGeneratorWorkflow`, `DeckGeneratorWorkflow`, `WebnamesBatchWorkflow`, `CrawlerWorkflow`, `PdfGeneratorWorkflow`, plus `ChatMemoryDO`.
- **`wom7func` (`w0m-cf`):** `5/5` account cron schedules (`*/15`, `*/30`, `0 8 * * *`, `0 */6 * * *`, `0 14 * * SUN`), stateless JSON-RPC 2.0 `POST /mcp`, `/ai/chat` & `/ai/embed`, Browser Rendering, Inbound Email Routing, unified ATS (`huntflow`, `merge`), and `550 B` `#![no_std]` `w0m-wasm-utils`.
- **Supabase Relational & Edge Function Layer:** `393` SQL migrations on PostgreSQL `17.6`, 4-axis `public.wom_can` RLS, `SECURITY DEFINER` append-only `*_audit_log` triggers (`T614`), `64` Deno 2 Edge Function directories (`63` active + decommissioned `trigger-hatchet-workflow/` stub, `--frozen=true` via `deno_lock_parity_check.py`), Tinybird analytics, Opik/OTel tracing, strict DMARC (`p=quarantine`) mail (`GoTrue` + Google Workspace + Resend), and 7 AES-256-GCM connector families.

### 3.3 `@k7` Rust Family, Extensions, Local MLX & Security Gates
- **`@k7` Git TUI Browser (`T708`):** `5` Git & LLM remote flavours (`GitHub`, `GitLab`, `HuggingFaceHub` with `u64` `>4 GiB` shard lengths, `ForgejoGitea`, and `LlmAgentCheckpoint` for GitButler/Orca/Agent Lanes).
- **7-Dialect SDD Bridge (`T712`–`T715`, `T718`):** `w0m-openspec`, `github-speckit` (`.specify/`), `open-gsd` (`.planning/`), `openspec`, `bmad` (`_bmad/`), `conductor` (`conductor/`), and `cc-sdd` (`.kiro/specs/`), protected against slopsquatting by `package_legitimacy_check.py`.
- **Hybrid Knowledge & Interactive Explainer Commands:**

```bash
cd ~/Projects/'!self'/w0m
just kb-index
just kb-search "4-tier free-tier-first architecture"
just ask "computePromptChecksum"
just tech-explainer
```
