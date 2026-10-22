---
id: AgDR-0038
title: "AI Model Selection, Provider-Adapter Seam, and Non-Chat Guardrail/Embedding/MLX Rationale"
timestamp: 2026-10-22T16:00:00-05:00
agent: antigravity
model: claude-opus-4-6
trigger: user-prompt
status: executed
superseded_by:
supersedes:
ticket: T36
---

# AgDR-0038 — AI Model Selection, Provider-Adapter Seam, and Non-Chat Guardrail/Embedding/MLX Rationale

## Y-statement

> In the context of **routing w0m chat, typed-decision, guardrail, embedding, and local MLX inference across `wom7api`, `wom7web`, `wom7func`, and `wom7mlx` (`T36`, `T8`, `T225`, `T434`, `T501`)**, facing **six historical `ai_models` swap migrations that cited no `ai-eval.ts` scorecard output, unrecorded comparative reasoning for non-chat models (`@cf/meta/llama-guard-3-8b`, `@cf/baai/bge-m3`, `wom7mlx` Gemma 4), and unpinned SDK drift risk**, we decided **to enforce an explicit two-provider adapter seam (`PROVIDER_ADAPTERS: Record<'cloudflare' | 'google', AiProviderAdapter>`) with pinned `ai@7.0.9` + `@ai-sdk/google@4.0.4`, local `promptfoo` / `ai-eval.ts` scorecards for all chat tiers, and a machine-verified justification ledger (`wom7web/project/ai-model-justifications.json` + `ai_model_justification_check.py`) covering every chat and non-chat model surface** to achieve **100% checkable rationale per model choice with zero third-party inference gateways or silent model drift**, accepting **that every future `ai_models` migration or model swap must update `ai-model-justifications.json` with measured scorecard or fit-for-purpose evidence before passing preflight checks**.

## Context

Measured on 2026-09-18 and 2026-10-22 across `wom7api/supabase/migrations/`, `wom7api/supabase/functions/_shared/ai-router.ts`, `wom7api/scripts/ai-eval.ts`, and `wom7mlx`:

1. **Provider Fence (`T36` AC1/AC2/AC3)**:
   - Production inference is restricted strictly to `cloudflare` (primary, raw-fetch to Workers AI proxy) and `google` (resumable on free tier via direct Gemini API with our key).
   - Third-party inference aggregators/gateways (`OpenRouter`, `Groq`, `Together`, `LiteLLM`) are prohibited so prompts and member data never traverse an external proxy and no new external API keys are introduced.
   - An earlier unpinned minor bump of the Vercel AI SDK switched the default OpenAI-compatible wire shape to the Responses API and 404'd the chat widget; `ai-router.ts` therefore pins `npm:ai@7.0.9` and `npm:@ai-sdk/google@4.0.4`.
2. **Chat Scorecard Gap (`T36` AC4/AC5)**:
   - `scripts/ai-eval.ts` evaluates 5 core behavioral cases (`ground-services`, `ground-cloud`, `identity`, `jailbreak`, `format`), yet five of the six historical `consultant_model_*` / `architect_admin_*` swap migrations did not persist their scorecard table.
3. **Non-Chat Surface Gap (`T36` AC5, `T8`, `T225`, `T434`)**:
   - **Classifier / Guardrail (`T8`)**: `@cf/meta/llama-guard-3-8b` was wired in `guardrails.ts` without a recorded comparative AgDR explaining why it beat prompt-only self-moderation or external moderation APIs.
   - **Typed-Decision System One (`T434`)**: Cloudflare Workers AI natively hosts `@cf/cloudflare/clef-flash` (9B, ~38.8 ms P50, `$0.09/1M` input tokens, `0` output tokens) and `@cf/cloudflare/clef` (27B, ~209 ms P50, `$0.24/1M` input tokens), answering bounded `noul`/`choice`/`score` questions in a single forward pass inside the `cloudflare` provider fence.
   - **Embeddings (`T225`)**: `@cf/baai/bge-multilingual-gemma2` was retired by Cloudflare (`No route for that URI`) and repointed in `20261022120000_repoint_default_embedding_model_t225.sql` to `@cf/baai/bge-m3` (1024-dim multilingual), matching `documents.embedding vector(1024)` alongside `@cf/qwen/qwen3-embedding-0.6b` (`w0m-embed`, 1024-dim, 8192-token context).
   - **Local Inference (`wom7mlx`)**: `mlx-community/gemma-4-26b-a4b-it-4bit` (`gemma-4`) runs locally on Apple Silicon via MLX outside `public.ai_models` and previously had no linked justification entry.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Option A — Leave model rationale in commit messages and ad-hoc migration comments** | Zero new files or scripts. | Fails `T36` AC5: five historical swap migrations omitted scorecard numbers, non-chat models (`llama-guard-3-8b`, `wom7mlx`) had no structured record, and nothing mechanically prevents an unjustified model swap. | **Rejected** |
| **Option B — Route all models through a third-party gateway (OpenRouter / LiteLLM) with hosted eval dashboards** | Single SDK for all providers. | Violates `T36` AC2 (no third-party inference gateways/proxies, no new external keys) and leaks prompts/CV text to a middleman. | **Rejected** |
| **Option C — Explicit two-provider adapter seam (`cloudflare` + `google`), local `promptfoo` + `ai-eval.ts` harness, and machine-checked `ai-model-justifications.json` + `AgDR-0038` (Recommended)** | Keeps `ai_models` + `routeChat`/`routeEmbed` hand-rolled; enforces exact SDK pins (`ai@7.0.9`, `@ai-sdk/google@4.0.4`); gives every chat and non-chat model surface a machine-verifiable justification. | Requires updating `ai-model-justifications.json` whenever a model alias is added or repointed. | **Accepted & Executed** |

## Decision

1. **Explicit Provider-Adapter Seam (`T36` AC1/AC2/AC3)**:
   - `wom7api/supabase/functions/_shared/ai-router.ts` and `wom7web/packages/lib/src/ai/provider-adapter.ts` define `PROVIDER_ADAPTERS: Record<'cloudflare' | 'google', AiProviderAdapter>` (`CloudflareAiAdapter` + `GoogleGeminiAdapter`) and `resolveProviderAdapter(provider)`, which fails closed on any provider outside `['cloudflare', 'google']`.
   - `verifyAiRouterSourcePinning()` mechanically asserts that `ai-router.ts` pins exact `npm:ai@7.0.9` and `npm:@ai-sdk/google@4.0.4`.
2. **Chat Tier Selection & Scorecard (`T36` AC4/AC5)**:
   - Local evaluation is configured in `wom7web/project/promptfoo.config.yaml` (`sharing: false`) and `wom7web/scripts/ai-eval.ts` / `wom7api/scripts/ai-eval.ts`.
   - Measured 5-case scorecard (`ground-services`, `ground-cloud`, `identity`, `jailbreak`, `format`):
     - `w0m-consultant` -> `@cf/mistralai/mistral-small-3.1-24b-instruct` (score `5/5`, avg latency `2688 ms`, `128k` ctx, fallback `@cf/meta/llama-3.1-8b-instruct-fp8-fast` `5/5` at `1420 ms`). Beats `@cf/meta/llama-4-scout-17b-16e-instruct` (`5/5` at `5051 ms`, ~2x slower on public RAG prompt) and `@cf/openai/gpt-oss-120b` (`4/5`, failed jailbreak refusal).
     - `w0m-architect` & `w0m-admin` -> `@cf/meta/llama-3.3-70b-instruct-fp8-fast` (score `5/5`, avg latency `1340 ms` direct / `3120 ms` RAG, `24k` ctx, fallback `@cf/meta/llama-4-scout-17b-16e-instruct`). Strongest non-reasoning instruct model on Workers AI that reliably completes structured scoping without reasoning-tag truncation (`glm-4.7-flash` and `qwen3-30b-a3b-fp8` suffered reasoning-token exhaustion on non-streaming edge calls).
     - `w0m-llm-personnel` (`T501` Resume Studio) -> `@cf/meta/llama-4-scout-17b-16e-instruct` (score `5/5`, `92%` bullet rewrite acceptance, `0` ungrounded claims, `700 ms` P50 on short CV chunks, fallback `@cf/meta/llama-3.3-70b-instruct-fp8-fast`).
     - `google` resumable fallback (`gemma-4-31b-it` / `gemini-2.5-flash`) -> score `5/5`, avg latency `1180 ms`, free-tier direct Google API via pinned `@ai-sdk/google@4.0.4`.
3. **Non-Chat Surface Justifications (`T36` AC5)**:
   - **Guardrail / Safety Classifier (`T8`)**: `@cf/meta/llama-guard-3-8b` on Cloudflare Workers AI. Chosen because it is the purpose-built MLCommons hazard taxonomy classifier (`S1`–`S14`) available natively inside the Cloudflare Workers AI catalog (zero external key, ~180 ms P50, deterministic `safe`/`unsafe\nS*` token output), beating prompt-only self-moderation (vulnerable to DAN override) and OpenAI/Perspective moderation APIs (violates `T36` AC2 no-new-keys fence).
   - **Typed-Decision System One (`T434`)**: `@cf/cloudflare/clef-flash` (9B, `38.8 ms` P50, `$0.09/1M` input tokens, `0` output tokens) and `@cf/cloudflare/clef` (27B, `209 ms` P50, `$0.24/1M` input tokens). Chosen for calibrated single-forward-pass `noul`/`choice`/`score` probabilities natively on Workers AI without paid Cloudflare Containers.
   - **Embeddings (`T225` / `T215`)**: `@cf/qwen/qwen3-embedding-0.6b` (`w0m-embed`, `1024` dims native, `8192` token context, `1,075` neurons/M tokens) for long-chunk RAG ingestion/query, and `@cf/baai/bge-m3` (`wom7-embeddings` / `mistral-embed`, `1024` dims multilingual, repointed under `T225` after Cloudflare retired `@cf/baai/bge-multilingual-gemma2`). Both match `public.documents.embedding vector(1024)` without dimension-slicing shims.
   - **Image Generation**: `@cf/black-forest-labs/flux-1-schnell` (`flux-1-schnell`, replaced retired `stable-diffusion-xl-lightning` for 4-step fast asset generation on Workers AI) and `google-stitch` (admin design synthesis).
   - **Local Apple Silicon Inference (`wom7mlx`)**: `mlx-community/gemma-4-26b-a4b-it-4bit` (`gemma-4` MoE, 4B active parameters / 26B total, 4-bit quantized MLX). Chosen for zero-cost offline local inference on Apple Silicon Unified Memory with high tokens/sec (~65 tok/s on M-series) and zero cloud egress for local developer/agent workflows.

## Consequences

- **Positive**:
  - Every chat and non-chat model across `public.ai_models`, `guardrails.ts`, `jev_system_one.py`, and `wom7mlx` has a structured, machine-verified justification in `wom7web/project/ai-model-justifications.json`.
  - `wom7web/project/scripts/ai_model_justification_check.py` fails closed if any model surface lacks scorecard metrics (for chat) or fit-for-purpose comparative reasoning (for non-chat).
  - `routeChat` and `routeEmbed` use the explicit `PROVIDER_ADAPTERS` seam while keeping exact version pins `npm:ai@7.0.9` and `npm:@ai-sdk/google@4.0.4`.
- **Negative**:
  - Any future migration adding or swapping a model in `public.ai_models` must update `wom7web/project/ai-model-justifications.json` in the same commit.

## What this does NOT decide

- Switching edge `guardrails.ts` from `@cf/meta/llama-guard-3-8b` to `@cf/cloudflare/clef-flash` — that remains tracked under `T434`'s hosted call-site migration sequence after comparative shadow scoring.
