---
id: AgDR-0039
title: "Agent Transport Stack per Layer: WebMCP (Page), Authenticated HTTPS (Extension), MCP Streamable HTTP (Service APIs), and ACP (Host)"
timestamp: 2026-10-22T16:05:00-05:00
agent: antigravity
model: claude-opus-4-6
trigger: user-prompt
status: executed
superseded_by:
supersedes:
ticket: T220
---

# AgDR-0039 — Agent Transport Stack per Layer: WebMCP, Authenticated HTTPS, MCP Streamable HTTP, and ACP

## Y-statement

> In the context of **connecting browser pages, `wom7ext`, w0m backend/portal APIs, and local IDE/daemon hosts (`ZeroClaw`, `Antigravity`, `Claude Code`) (`T220`, `T21`, `T153`, `T154`, `T560`)**, facing **the retirement of `wom7mcp` and its dead `ws://localhost:8008` WebSocket bridge, the three-time rename of WebMCP (`window.agent` -> `navigator.modelContext` -> `document.modelContext`), MCP's replacement of HTTP+SSE with Streamable HTTP (`Mcp-Method`/`Mcp-Name` headers), and the name collision between Zed's live ACP and IBM's archived ACP/A2A**, we decided **to assign exactly one protocol and transport to each of the four architectural layers — (1) `WebMCP` (`document.modelContext`) for own-page-to-agent tools via `@webomage/webmcp`, (2) Authenticated HTTPS REST (`outreach-clip-ingest` + `extension_commands`) for `wom7ext` on third-party sites while permanently retiring `ws://localhost:8008`, (3) `MCP Streamable HTTP` (`/api/mcp` stateless JSON-RPC 2.0 POST with `Mcp-Method`/`Mcp-Name` headers) for agent-to-service APIs, and (4) Zed `ACP` (JSON-RPC 2.0 over stdio) for host-to-agent pairing — while keeping `@webomage/webmcp` dependency-free (`@mcp-b/webmcp-types` schema-compatible without `@mcp-b/webmcp-polyfill` runtime bloat)** to achieve **four non-overlapping, testable transport contracts with zero dead localhost WebSocket bridges (`AgDR-0025`)**, accepting **that `wom7ext` no longer acts as an inbound WebSocket MCP server and all third-party page clips flow through authenticated HTTPS (`AgDR-0033`)**.

## Context

Measured on 2026-08-15 and 2026-10-22 across `wom7web`, `wom7ext`, `wom7api`, and current upstream specifications:

1. **Four Conflated Layers**:
   - Historically, "MCP" was treated as a single transport question across browser pages, the Chrome extension (`wom7ext`), backend APIs, and local agent hosts. When `wom7mcp` (`ws://localhost:8008`) was deprecated, `wom7ext/extension/src/services/mcpService.ts` still unconditionally attempted `new WebSocketClientTransport(new URL("ws://localhost:8008/?type=extension"))` (`FORCE_LOCAL = true`), failing on every Service Worker boot.
2. **WebMCP Evolution & `@mcp-b` (`WebMCP-org`) Re-Evaluation (`T220` AC2)**:
   - Chrome 146+ / 150 moved the imperative WebMCP API from `navigator.modelContext` to `document.modelContext` (tools belong to a document, not the browser process). `@webomage/webmcp` (`wom7web/packages/webmcp/src/detect.ts` & `register.ts`, `T21`) already isolates `document.modelContext` with a `navigator.modelContext` fallback and role-scoped manifest registration.
   - Re-tested `@mcp-b/webmcp-types` and `@mcp-b/webmcp-polyfill` (now maintained under `WebMCP-org/npm-packages`):
     - `@mcp-b/webmcp-types` defines `ModelContext` (`registerTool`, `unregisterTool`, `provideContext`) matching `@webomage/webmcp`'s descriptor shape (`name`, `description`, `parameters`, `execute`).
     - `@mcp-b/webmcp-polyfill` injects an in-page DOM relay + postMessage bridge intended for sites that embed their own iframe agent host. On w0m's 5 Astro portals (`web`, `cp`, `job`, `join`, `demo`), non-WebMCP browsers already use w0m's native chat widget and server-side tool router (`routeChat`), so shipping `@mcp-b/webmcp-polyfill` adds unnecessary client bundle weight and attack surface.
     - **Verdict on `@mcp-b`**: `@webomage/webmcp` maintains wire- and type-level compatibility with `@mcp-b/webmcp-types` (`WebMCP-org`), while rejecting `@mcp-b/webmcp-polyfill` at runtime in favor of our zero-dependency progressive-enhancement `detect.ts` / `register.ts`.
3. **MCP Streamable HTTP (`2025-03-26` / `2026-07-28` RC)**:
   - MCP deprecated the dual-endpoint `HTTP+SSE` transport in favor of **Streamable HTTP** (`POST /api/mcp` carrying JSON-RPC 2.0 `initialize`, `tools/list`, `tools/call`) with `Mcp-Method` and `Mcp-Name` headers for gateway routing and observability without body buffering.
4. **ACP Disambiguation**:
   - **Zed's Agent Client Protocol (ACP)** is the active JSON-RPC 2.0 over `stdio` protocol spoken by `zeroclaw acp`, Claude Code, and IDE hosts (`T153`).
   - **IBM's Agent Communication Protocol (ACP)** merged into Linux Foundation **A2A** and its repository is archived.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Option A — Re-build a local `:8008` WebSocket daemon to revive `wom7ext`'s `WebSocketClientTransport`** | Keeps legacy `mcpService.ts` code path unchanged. | Requires every user machine to run a local Node WebSocket relay just to use the browser extension; duplicates `AgDR-0033`'s authenticated HTTPS `outreach-clip-ingest` pipeline; violates `AgDR-0025`. | **Rejected** |
| **Option B — Bundle `@mcp-b/webmcp-polyfill` across all 5 Astro portals and use HTTP+SSE for backend MCP** | Drop-in polyfill from `WebMCP-org`. | Ships dead polyfill JS to Firefox/Safari visitors who never invoke `document.modelContext`; HTTP+SSE is deprecated in MCP 2025-03-26+. | **Rejected** |
| **Option C — Four-layer complement stack: WebMCP (`document.modelContext`) for own pages, Authenticated HTTPS (`outreach-clip-ingest`) for `wom7ext` on third-party sites, MCP Streamable HTTP (`POST /api/mcp`) for service APIs, and Zed ACP (JSON-RPC 2.0 / stdio) for host<->agent pairing (Recommended)** | Every layer uses the standard designed for its trust boundary; zero local `:8008` bridge requirement; stateless edge-compatible `/api/mcp`. | Retires inbound WebSocket MCP inside `wom7ext` (`mcpService.ts` becomes a fail-closed HTTPS/ZeroClaw bridge). | **Accepted & Executed** |

## Decision

| Layer | Chosen Protocol | Chosen Transport | Canonical Implementation | What It Is **NOT** For |
|---|---|---|---|---|
| **1. Page ↔ Agent (own sites: `web`, `cp`, `job`, `join`, `demo`)** | **WebMCP** (W3C WebML / Chrome 150+ `document.modelContext`) | In-page browser DOM API (`document.modelContext.registerTool`) | `@webomage/webmcp` (`wom7web/packages/webmcp/src/{detect,register,manifest}.ts`) | **NOT** for third-party sites, cross-origin background scraping, or unauthenticated write actions without `window.confirm` / `confirmCallback`. |
| **2. Extension ↔ w0m Services (third-party sites in `wom7ext`)** | **w0m Extension REST + Realtime Command Protocol** (`AgDR-0033`) | **Authenticated HTTPS POST** (`/functions/v1/outreach-clip-ingest`, `/functions/v1/sync-linkedin-profile`) + Supabase `extension_commands` | `wom7ext/extension/src/services/mcpService.ts` & `specEngine.ts` | **NOT** a `ws://localhost:8008` or `ws://localhost:8009` WebSocket MCP server (`wom7mcp` is permanently retired per `AgDR-0025`). |
| **3. Agent ↔ w0m Services / APIs** | **MCP** (Model Context Protocol `2025-06-18` / `2026-07-28`) | **MCP Streamable HTTP** (`POST /api/mcp`, JSON-RPC 2.0, `Mcp-Method` & `Mcp-Name` headers, Bearer/Cookie session auth) | `wom7web/apps/cp/src/pages/api/mcp.ts` + `@webomage/webmcp` | **NOT** legacy dual-endpoint `HTTP+SSE`, and **NOT** unauthenticated public mutation. |
| **4. Host / Editor ↔ Coding or Local Agent** | **ACP** (Zed Agent Client Protocol) | **JSON-RPC 2.0 over `stdio`** (newline-delimited UTF-8 frames between host and child agent process) | `zeroclaw acp` (`T153`) & `@webomage/webmcp` ACP frame validator | **NOT** IBM's archived Agent Communication Protocol (now A2A), and **NOT** exposed over public TCP/HTTP sockets. |

## Consequences

- **Positive**:
  - Eliminates repeated `ws://localhost:8008` / `ws://localhost:8009` connection-refused errors in `wom7ext` Service Worker logs (`AgDR-0025`).
  - Exposes a real, authenticated MCP Streamable HTTP endpoint at `wom7web/apps/cp/src/pages/api/mcp.ts` supporting `initialize`, `tools/list`, and `tools/call` with `Mcp-Method` and `Mcp-Name` headers.
  - All 4 transport layers are proven by automated unit tests in `wom7web/packages/webmcp/src/transport-stack.test.ts`.
- **Negative**:
  - External desktop agents that want to invoke w0m tools call `POST /api/mcp` over Streamable HTTP (or pair with `zeroclaw acp` over stdio) rather than connecting to a browser extension WebSocket port.

## What this does NOT decide

- Individual third-party SaaS OAuth vs remote MCP server choices (e.g., Upwork's `https://mcp.upwork.com/mcp` local-only DCR constraint), which are governed by `AgDR-0034` and `wom7web/project/services-policy.json`.
