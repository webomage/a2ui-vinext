---
id: AgDR-0034
title: "Connector framework SSOT: T99 app-level AES-256-GCM token encryption, Upwork MCP local-only transport per T537, and GitHub App + LinkedIn live adapters"
timestamp: 2026-10-20T15:45:00-05:00
agent: antigravity
model: gemini-2.5-pro
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T442
---

# AgDR-0034 — Connector framework SSOT: app-level AES-256-GCM encryption, measured transport registry, and first live adapters

## Y-statement

> In the context of **building the unified multi-account, scope-aware connector framework (`T442`) across `public.connections` and `public.oauth_states`**, facing **(1) a contradiction between `T99` (application-level AES-256-GCM via `_shared/crypto.ts` + Infisical `CONNECTOR_TOKEN_KEY_V1`) and `T442` AC3's draft proposal (Supabase Vault `pgsodium` + `security definer` RPC), (2) `T537`'s empirical finding that Upwork's MCP DCR rejects non-localhost `https://` redirect URIs (`HTTP 400 invalid_redirect_uri`) while Upwork's legacy GraphQL API is deprecated and server storage awaits Upwork support sign-off, and (3) a 4-variant redirect-URI fallback loop in `upwork-callback` violating `AgDR-0025`**, we decided **to use `T99`'s application-level AES-256-GCM encryption (`_shared/crypto.ts` and `@webomage/lib/connectors/crypto`) as the single canonical token-encryption SSOT with dual-write transition until `CONNECTOR_TOKEN_KEY_V1` backfill completes, record Upwork in `project/policies/services-policy.json` as `transport: "mcp"`, `headless: false` with `T537`'s measured evidence, enforce a single exact redirect URI per provider with PKCE (`S256`) and single-use `oauth_states`, and ship GitHub App + LinkedIn as the first live OAuth adapters with Upwork capability-gated per `T537`** to achieve **one hardened connect/refresh/revoke flow, zero dual encryption mechanisms, and honest measured status across Me, Org, and Admin surfaces**, accepting **that plaintext token column removal remains gated on provisioning `CONNECTOR_TOKEN_KEY_V1` in Infisical and running the `T99` backfill**.

## Context

1. **Token Encryption (`T99` vs `T442` AC3)**:
   - `T99` already migrated `public.connections` (`20260912000000_t99_connections_encrypted_tokens.sql`) with `access_token_ciphertext`, `access_token_iv`, `refresh_token_ciphertext`, `refresh_token_iv`, and `token_key_version`, revoked `SELECT` on all secret and ciphertext columns from `anon` and `authenticated`, and shipped `wom7api/supabase/functions/_shared/crypto.ts` (AES-256-GCM via WebCrypto, 18/18 unit tests passing).
   - `T442`'s initial OpenSpec draft proposed a second mechanism (Supabase Vault + `security definer` decrypt function), which would create a dual SSOT with `T99` and require DB round-trips from Cloudflare Workers.
2. **Upwork MCP Transport Measurement (`T442` AC1 vs `T537`)**:
   - `T537` (`upwork_mcp_spike.py`, 2026-10-02..2026-10-05) measured `https://mcp.upwork.com/mcp` and its OAuth 2.1 Dynamic Client Registration endpoint (`https://mcp.upwork.com/register`).
   - Upwork DCR rejected `https://cp.webomage.com/api/connections/upwork/callback` with `HTTP 400 invalid_redirect_uri` and accepted only localhost loopback callbacks (`http://127.0.0.1:<port>/callback`).
   - Upwork's legacy GraphQL API is deprecated (`T537`), and server-side storage of member Upwork data is on hold pending Upwork support ToS sign-off (`T537`).
3. **Redirect URI Fallback Ladder (`AgDR-0025`)**:
   - `wom7api/supabase/functions/upwork-callback/index.ts` previously retried 4 redirect URI variants in a loop, violating `AgDR-0025` (zero silent fallbacks).

## Decision

1. **D1 — Token Encryption SSOT (`Option A`)**:
   - Application-level AES-256-GCM (`wom7api/supabase/functions/_shared/crypto.ts` and `@webomage/lib/connectors/crypto`, keyed by Infisical `CONNECTOR_TOKEN_KEY_VERSION` + `CONNECTOR_TOKEN_KEY_V<n>`) is the sole encryption mechanism for `public.connections`.
   - Column-level `GRANT SELECT` on `public.connections` and `public.oauth_states` excludes all token, ciphertext, IV, key-version, and `code_verifier` columns from `anon` and `authenticated`.
2. **D2 — Upwork Transport & `T537` Evidence**:
   - `project/policies/services-policy.json` records `upwork` with `transport: "mcp"`, `mcp_url: "https://mcp.upwork.com/mcp"`, `headless: false`, and the `T537` measurement evidence (2026-10-02..2026-10-05 DCR localhost restriction + ToS hold).
3. **D3 — First Live Adapters (`GitHub App`, `LinkedIn`, `Upwork` gated)**:
   - Ship live adapters for **GitHub App** (`GITHUB_APP_CLIENT_ID` / `GITHUB_APP_CLIENT_SECRET`, fine-grained repository, PR, and activity capabilities) and **LinkedIn** (`LINKEDIN_APP_ID` / `LINKEDIN_APP_SECRET`, personal and organization share/read capabilities) on `/api/connections/[provider]/{start,callback}` and `/api/connections/[id]`.
   - Register **Upwork** on the adapter contract with its scope/capability catalog and `upwork-mcp-allowlist.ts`, gated in the UI with its `T537` status and local MCP sync integration.
4. **D4 — Dual-Write Transition around `CONNECTOR_TOKEN_KEY_V1`**:
   - Connector writes populate AES-256-GCM ciphertext columns whenever `CONNECTOR_TOKEN_KEY_V<n>` is present in the runtime environment while preserving `T99` dual-write compatibility until `CONNECTOR_TOKEN_KEY_V1` is provisioned in Infisical and existing rows are backfilled (`T99`).

## Consequences

**Positive:**
- Eliminates the `T99` vs `T442` encryption conflict with zero Supabase Vault / `pgsodium` coupling.
- Enforces single-use PKCE (`S256`) state verification and a single exact redirect URI per provider (`AgDR-0025`).
- Provides multi-account connections (`(owner, provider, provider_urn)`), per-connection labels, and derived status (`connected | expired | error | revoked | never_synced | unmeasurable`) across Me, Org, and Admin surfaces without touching `auth.identities`.

**Negative:**
- Dropping the legacy plaintext `access_token` and `refresh_token` columns remains sequenced on `T99` (provisioning `CONNECTOR_TOKEN_KEY_V1` in Infisical and running the backfill).
