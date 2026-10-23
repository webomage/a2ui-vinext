---
id: AgDR-0046
title: "w0m-<role> Agent Naming and w0m-llm-<role> Model Alias Disambiguation"
timestamp: 2026-10-23T11:15:00-05:00
agent: antigravity
model: claude-opus-4-6
trigger: user-prompt
status: executed
superseded_by:
supersedes:
ticket: T500
---

# AgDR-0046 — w0m-<role> Agent Naming and w0m-llm-<role> Model Alias Disambiguation

## Y-statement

> In the context of **governed AI agent endpoints, personas (`public.ai_personas`), and model aliases (`public.ai_models`) across `wom7api` and `wom7web` (`T500`, `T501`)**, facing **name collisions where `w0m-architect`, `w0m-consultant`, and `w0m-admin` were previously used as `public.ai_models.id` model alias rows while the agents themselves carried mixed prefixes (`agent-architect`, `agent-consultant`, `agent-admin`, and `chat-internal`)**, we decided **to standardize every agent edge function and `public.ai_personas.name` on `w0m-<role>` (`w0m-consultant`, `w0m-architect`, `w0m-admin`, `w0m-personnel`) and every chat model alias in `public.ai_models.id` on `w0m-llm-<role>` (`w0m-llm-consultant`, `w0m-llm-architect`, `w0m-llm-admin`, `w0m-llm-personnel`), while preserving `w0m-embed` for the embedding alias** to achieve **one unambiguous naming convention across the estate with zero collision between agent identity and model alias identity**, accepting **a coordinated atomic database migration (`20261023100000_t500_w0m_agent_and_model_alias_cutover.sql`), edge function directory cutover, and full caller/spec sweep enforced by `just name-refs <old> --gate`**.

## Context

Measured on 2026-09-30 and 2026-10-23 across `wom7api/supabase/functions/`, `wom7api/supabase/migrations/`, and `wom7web`:

1. **Pre-cutover Naming Collision**:
   - The three core chat agents had three different naming conventions across three layers:
     - **Architect**: Edge function `agent-architect`, persona `agent-architect`, model alias `w0m-architect` (`@cf/meta/llama-3.3-70b-instruct-fp8-fast`).
     - **Consultant**: Edge function `agent-consultant`, persona `agent-consultant`, model alias `w0m-consultant` (`@cf/mistralai/mistral-small-3.1-24b-instruct`).
     - **Admin**: Edge function `chat-internal`, persona `agent-admin`, model alias `w0m-admin` (`@cf/meta/llama-3.3-70b-instruct-fp8-fast`).
   - Meanwhile, `T501` introduced `w0m-personnel` (agent function & persona) paired with `w0m-llm-personnel` (model alias in `public.ai_models`), proving the `w0m-<role>` / `w0m-llm-<role>` disambiguation pattern.
2. **Foreign-Key Constraint in `public.ai_personas`**:
   - `public.ai_personas.model` holds a foreign key `ai_personas_model_fkey REFERENCES public.ai_models(id) ON DELETE SET NULL`. Deleting or renaming `public.ai_models.id` before inserting the new `w0m-llm-<role>` rows and repointing `ai_personas.model` would null out the persona model assignments.
3. **Public Persona Definer Gate (`T246`)**:
   - `public.wom_public_persona(p_name text)` (`SECURITY DEFINER`) explicitly whitelists the public consultant persona name (`AND p_name = 'w0m-consultant'`) so `anon` callers can resolve the public consultant prompt without granting `SELECT` on `public.ai_personas`.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Option A — Keep `agent-*` / `chat-internal` for functions and `w0m-*` for model aliases** | Zero migration or function redeploy cost. | Perpetuates the exact confusion the owner flagged on 2026-09-30 (`w0m-architect` looked like an agent name but was a model alias, while `chat-internal` broke even the `agent-*` prefix); leaves `T501` (`w0m-personnel` / `w0m-llm-personnel`) inconsistent with the other three agents. | **Rejected** |
| **Option B — Add backward-compatibility proxy edge functions or dual DB rows (`agent-*` alongside `w0m-*`)** | Allows lazy caller migration. | Directly violates `AgDR-0025` (zero silent fallbacks, clean cutovers over shims) and leaves duplicate unauthenticated/authenticated endpoints live. | **Rejected** |
| **Option C — Clean atomic cutover: `w0m-<role>` for all agents (functions + `ai_personas.name`) and `w0m-llm-<role>` for all chat model aliases (`ai_models.id`), keeping `w0m-embed` (Recommended)** | One uniform rule across all four agents (`w0m-consultant`, `w0m-architect`, `w0m-admin`, `w0m-personnel`); zero ambiguity between agent and LLM alias; 100% compliant with `AgDR-0025`. | Requires atomic DB migration ordering (`INSERT ai_models` → `UPDATE ai_personas` → `DELETE old ai_models` → `CREATE OR REPLACE wom_public_persona`) and updating all callers, specs, and docs. | **Accepted & Executed** |

## Decision

1. **Agent Identity (`w0m-<role>`)**:
   - Every w0m AI agent uses `w0m-<role>` for both its Supabase Edge Function directory (`wom7api/supabase/functions/w0m-<role>/`) and its `public.ai_personas.name` primary key:
     - `w0m-consultant` (public sales & discovery consultant, formerly `agent-consultant`)
     - `w0m-architect` (signed-in/internal technical architect, formerly `agent-architect`)
     - `w0m-admin` (admin/internal operations assistant, formerly `chat-internal` / `agent-admin`)
     - `w0m-personnel` (CV & Resume Studio specialist, established in `T501`)
2. **Model Alias Identity (`w0m-llm-<role>`)**:
   - Every chat persona's model alias in `public.ai_models.id` uses `w0m-llm-<role>`:
     - `w0m-llm-consultant` (`@cf/mistralai/mistral-small-3.1-24b-instruct`, fallback `@cf/meta/llama-3.1-8b-instruct-fp8-fast`)
     - `w0m-llm-architect` (`@cf/meta/llama-3.3-70b-instruct-fp8-fast`, fallback `@cf/meta/llama-4-scout-17b-16e-instruct`)
     - `w0m-llm-admin` (`@cf/meta/llama-3.3-70b-instruct-fp8-fast`, fallback `@cf/meta/llama-4-scout-17b-16e-instruct`)
     - `w0m-llm-personnel` (`@cf/meta/llama-4-scout-17b-16e-instruct`, fallback `@cf/meta/llama-3.3-70b-instruct-fp8-fast`)
   - `w0m-embed` (`@cf/qwen/qwen3-embedding-0.6b`) is an embedding alias rather than a chat persona and retains `w0m-embed`.
3. **Database Cutover Order (`20261023100000_t500_w0m_agent_and_model_alias_cutover.sql`)**:
   - Inside a single transaction: (1) upsert `w0m-llm-*` rows into `public.ai_models`, (2) update `public.ai_personas` (`name` and `model`), (3) delete retired `w0m-consultant`/`w0m-architect`/`w0m-admin`/`w0m-default` rows from `public.ai_models`, (4) replace `public.wom_public_persona(text)` to check `p_name = 'w0m-consultant'` and re-grant `EXECUTE` to `anon, authenticated, service_role`, and (5) assert `count(*) = 0` for any legacy persona or model alias names.

## Consequences

- **Positive**:
  - `w0m-<role>` unambiguously identifies an agent endpoint and persona; `w0m-llm-<role>` unambiguously identifies an `ai_models` routing alias.
  - All four agents (`w0m-consultant`, `w0m-architect`, `w0m-admin`, `w0m-personnel`) follow the exact same naming law across `wom7api` and `wom7web`.
  - Enforced mechanically by `just name-refs <old> --gate` and `ai_model_justification_check.py`.
- **Negative**:
  - Deploying to hosted Supabase requires running `just db-migrate`, deploying `w0m-consultant`, `w0m-architect`, and `w0m-admin`, and deleting the retired hosted functions (`supabase functions delete agent-architect agent-consultant chat-internal`).

## What this does NOT decide

- Underlying provider or model weights for each alias (governed separately by `AgDR-0038` and `wom7web/project/ai-model-justifications.json`).
