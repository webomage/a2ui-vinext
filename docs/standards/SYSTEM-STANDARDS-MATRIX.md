# System Standards & RFC Master Matrix (`T214` AC1)

> **Canonical Reference (`T214` AC1):** Every architectural layer, schema, API contract, MCP tool definition, design token, skill manifest, and meta-asset across the `w0m` estate (`root`, `wom7web`, `wom7api`, `wom7func`, `wom7ext`, `wom7sec`, `wom7skills`, `wom7mlx/wom7mlx`) maps to an explicit, approved RFC or industry standard with **strictly ONE Single Source of Truth (SSOT)**.
> Enforced continuously by `just standards-check` (`wom7web/project/scripts/standards_check.py`).

## 1. Master Layer-to-RFC Mapping Matrix

| # | Architectural Layer | Assigned Standard / RFC & Version | Canonical SSOT Origin | Downstream Consumers / Targets | Verification Gate |
|---|---|---|---|---|---|
| 1 | **Database & Schema** | **ISO/IEC 9075 (SQL-92 / PostgreSQL 15+ DDL)** | `wom7api/supabase/migrations/*.sql` | Drizzle ORM (`wom7api/src/db/`), generated TS types (`just db-types`), PostgREST catalog | `just migration-lint`, `just schema-drift`, `just standards-check` |
| 2 | **Internal RPC & Edge Functions** | **OpenAPI 3.1.0 · JSON Schema Draft 2020-12 · Zod v4** | `wom7api/supabase/functions/*/handler.ts` & `wom7func/src/index.ts` | `wom7web/apps/*/src/lib/rpc.ts`, Cloudflare Workers, internal webhooks | `just deno-check`, `just deno-test`, `just standards-check` |
| 3 | **Public & App HTTP APIs** | **RFC 9110 (HTTP Semantics) · RFC 8259 (JSON) · JSON Schema Draft 2020-12** | `wom7web/apps/{web,cp,join,job}/src/pages/api/**/*.ts` | Browser clients, SSR Astro pages, Svelte 5 islands, external webhook senders | `just test`, `just standards-check` |
| 4 | **Model Context Protocol (MCP)** | **Model Context Protocol Specification `2024-11-05` · JSON-RPC 2.0** | `.w0m/sdlc.json` (`mcp.servers`) & `.mcp.json` | Claude Code, Antigravity, OpenCode, Headroom proxy (`:8787`), Upwork/Supabase MCP | `just mcp-ratchet`, `just preflight`, `just standards-check` |
| 5 | **Web Agent Tools & Clipper Specs** | **W3C WebMCP Draft (`navigator.modelContext`) · JSON Schema Draft 2020-12** | `wom7web/packages/webmcp/` & `wom7ext/extension/specs/*.json` | `wom7ext` MV3 content scripts, browser AI agents | `just standards-check`, `clipper.test.ts` |
| 6 | **Frontend Types & Design System** | **W3C Design Tokens (DTCG) · CSS Custom Properties Level 1** | `wom7web/packages/ui/src/styles/tokens.css` & `wom7web/design-system/tokens/*.css` | `@webomage/ui` Svelte 5 primitives (`Button`, `Input`, `Select`, `Badge`, `Card`, `PageHeader`), `apps/*` | `just ds-conformance`, `just standards-check` |
| 7 | **Identity, Authz & RBAC** | **RFC 6749 (OAuth 2.0) · RFC 7519 (JWT) · NIST SP 800-162 (ABAC/RBAC)** | `public.offices`, `public.role_capabilities`, `public.resource_grants`, `wom7web/packages/authz/` | Postgres RLS (`public.wom_can`), Astro auth middleware, Control Panel (`apps/cp`) | `just authz-grant-gate`, `just rls-coverage` |
| 8 | **Prompt Skills & Agent Catalog** | **Agent Skill Specification v1.0 (YAML Frontmatter + Markdown)** | `wom7skills/skills/*/SKILL.md` & `wom7skills/skills.schema.json` | `.agents/skills/*`, `.claude/skills/*`, `wom7skills/skills-registry.json` | `just skills-version-check`, `just standards-check` |
| 9 | **SDLC, Commits & Meta-Assets** | **OpenSpec 1.x · Conventional Commits 1.0.0 · JSON Schema Draft 2020-12** | `.tasks/T*.md`, `.w0m/sdlc.json`, `wom7web/project/schemas/meta/*.schema.json` | `TASKS.md`, `STATE.md`, `docs/STATUS-DASHBOARD.html`, GitHub Projects v2 board | `just tickets-frontmatter-check`, `just standards-check` |
| 10 | **Logging & Telemetry** | **OpenTelemetry (OTel) Semantic Conventions 1.x · W3C Trace Context** | `wom7web/packages/logger/` & `wom7api/src/utils/logger.ts` | Tinybird event pipes, Cloudflare Workers logs, Sentry/PostHog sinks | `just standards-check` |

## 2. Exception & Evolution Policy

1. **No Unvalidated Boundaries:** Every new MCP tool, JSON policy file, skill definition, or ticket/meta-asset must declare or map to its JSON Schema Draft 2020-12 contract in `wom7web/project/standards-policy.json`.
2. **Unidirectional Propagation Only:** Downstream artifacts (`TASKS.md`, `STATE.md`, `docs/DECISIONS.md`, `docs/STATUS-DASHBOARD.html`, `_in/INDEX.md`, generated TypeScript database types) are compiled from their SSOT and must never be hand-edited out of band.
3. **Deprecation & Cutover (`AgDR-0025`):** When upgrading an RFC or schema version, 100% of callers are migrated atomically with zero silent fallback ladders or dual-SSOT shims.
