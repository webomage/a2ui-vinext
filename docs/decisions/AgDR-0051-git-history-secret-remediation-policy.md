---
id: AgDR-0051
title: "Git-history secret remediation: rotation-first invariant, Cloudflare Workers AI cutover, and deferred filter-repo window"
timestamp: 2026-10-26T20:20:00-05:00
agent: antigravity
model: claude-opus-4-6
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T504
---

# AgDR-0051 — Git-history secret remediation: rotation-first invariant, Cloudflare Workers AI cutover, and deferred filter-repo window

## Y-statement

> In the context of **[[T504]] (where May 2026 `.dev.vars` commits in `w0m-web` and historical `.env` commits in `w0m-api` committed 27 credential-shaped values, and Google disabled `GEMINI_API_KEY` via GitHub Secret Scanning Partner Program) and [[T17]] (purging `.env.bak` from `w0m-web` git history)**, facing **the operational blast radius of a destructive `git filter-repo` + force-push across 8 estate repositories and active multi-agent worktrees (`just agent-tree`), plus the standing estate hazard that pushing any pre-rewrite local branch or worktree resurrects purged git objects**, we decided **to enforce a strict Rotation-First Policy — (1) migrate all 8 `w0m-api` Cloudflare Workflows and `ai-router.ts` Google fallbacks onto bound Cloudflare Workers AI (`@cf/google/gemma-4-26b-a4b-it` and `@cf/baai/bge-m3`), (2) immediately overwrite all 8 Tier-A decommissioned/revoked secrets in Infisical `beta` with fresh CSPRNG tokens (`w0m-api/scripts/rotate_leaked_secrets.py`), (3) require 100% credential rotation (`just secret-history-check` exiting 0) BEFORE any `git filter-repo` history rewrite is permitted, and (4) keep `w0m-web` and `w0m-api` private while blocking [[T17]] on [[T504]] completion** to achieve **immediate elimination of runtime dependency on `GEMINI_API_KEY` and `MISTRAL_API_KEY` in Workflows and zero risk of hiding still-live credentials behind a cosmetic history rewrite**, accepting **that historical `.dev.vars` and `.env.bak` blobs remain inert in private repository history until all Tier-B/Tier-C credentials are rotated and a single coordinated `filter-repo` maintenance window is executed**.

## Context

1. On 2026-09-30, `GEMINI_API_KEY` (`sha256[:12]=b5db0d9e811a`, committed in `w0m-web` `de6cf1a2f6` and `12dade3e2e` on 2026-05-08/14 and untracked in `1e4935539b` on 2026-06-03) was disabled by Google (`HTTP 403: Your API key was reported as leaked`).
2. `just secret-history-check` (`w0m-web/project/scripts/secret_history_check.py`, [[T504]] AC3) measured 27 credential-shaped secrets in Infisical `beta` whose SHA-256 digests still matched historical commits in `w0m-web`, `w0m-api`, or `w0m-ext`.
3. [[T17]] proposed running `git filter-repo` + force-push to remove `.env.bak` from `w0m-web` history, under the earlier assumption that all values in `.env.bak` were already dead. Re-measurement proved that several keys in `.env.bak` and `.dev.vars` were still live in Infisical `beta`.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **O1 — Immediate `git filter-repo` + force-push before completing rotation** | Removes `.env.bak` and `.dev.vars` blobs from `origin/beta` immediately. | **Dangerous:** Hides still-live credentials from `just secret-history-check` without revoking them at upstream providers; breaks all active agent trees (`~/.w0m/work/*`), and any un-rewritten clone push resurrects the purged objects. | **Rejected** |
| **O2 — Rotate-First Policy + Cloudflare Workers AI Workflow Cutover + Deferred Single-Pass `filter-repo` (`T17` blocked by `T504`)** | Eliminates actual security exposure by revoking/rotating credentials first; migrates all 8 `w0m-api` Workflows and `ai-router.ts` to bound Cloudflare Workers AI so `GEMINI_API_KEY` is no longer a single point of failure; preserves `just secret-history-check` as the authoritative progress gate until 0 active digests remain in history. | Leaves revoked/inert ciphertexts in private git history until the post-rotation `T17` window. | **Accepted ([[T504]] AC4/AC6)** |

## Decision

1. **Cloudflare Workers AI Cutover for Workflows & Router ([[T504]] AC6)**:
   - All 8 `w0m-api` Cloudflare Workflows (`job-scorer`, `cv-generator`, `deck-generator`, `cert-evaluator`, `cert-ingestion`, `vectorize-job`, `vectorize-profile`, `webnames-batch`) and `public.ai_models` legacy rows (`gemma-4-31b-it`, `gemini-embedding-2`, `google-stitch`, `llama-3.3-70b-versatile`) run on Cloudflare Workers AI (`@cf/google/gemma-4-26b-a4b-it` with `@cf/meta/llama-3.3-70b-instruct-fp8-fast` fallback for chat/JSON, and `@cf/baai/bge-m3` for 1024-dim embeddings).
   - `GoogleGeminiAdapter` in `w0m-api/supabase/functions/_shared/ai-router.ts` degrades automatically to `CloudflareAiAdapter` when `GOOGLE_API_KEY`/`GEMINI_API_KEY` is absent or rejected (`403`/`leaked`).
2. **Three-Tier Credential Rotation (`w0m-api/scripts/rotate_leaked_secrets.py`, [[T504]] AC2)**:
   - **Tier A (8 decommissioned/revoked secrets)**: `SUPABASE_KEY`, `HUGGINGFACE_API_TOKEN`, `OPIK_API_KEY`, `HATCHET_CLIENT_TOKEN`, `SIGNOZ_API_KEY`, `LITELLM_MASTER_KEY`, `COHERE_API_KEY`, `GROQ_API_KEY` — rotated immediately in Infisical `beta` to fresh 256-bit CSPRNG values.
   - **Tier B (5 internal CSPRNG secrets)**: `CRON_SECRET`, `CRYPTO_KEY`, `E2E_ACCESS_SECRET`, `ADMIN_PASSWORD`, `MEMBER_PASSWORD` — rotated via `rotate_leaked_secrets.py --rotate-tier B --apply` immediately prior to `just deploy-all`.
   - **Tier C (14 external provider console keys)**: rotated in upstream provider consoles and synced to Infisical `beta` until `just secret-history-check` exits 0.
3. **Git History Disposition ([[T504]] AC4 & [[T17]])**:
   - `w0m-web` and `w0m-api` remain private repositories; `just secret-history-check` is required before any repository is ever made public.
   - [[T17]] (`git filter-repo` purge of `.env.bak` and `.dev.vars`) is explicitly `blocked_by: [T504]` and may only execute after `just secret-history-check` exits 0 and `just agent-tree-list` confirms zero active worktrees.

## Consequences

- `parse-resume`, `ai-router.ts`, and all 8 `w0m-api` Workflows operate on Cloudflare Workers AI without requiring an active Google Gemini key.
- 8 Tier-A historical secret matches are eliminated immediately in Infisical `beta`.
- `just secret-history-check` remains an honest, un-blinded gate for the remaining Tier-B and Tier-C rotations.
