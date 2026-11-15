---
id: AgDR-0026
title: "The w0m catalog uses Backstage's entity standard (catalog-info.yaml), typed in Python, served over MCP — without running Backstage"
timestamp: 2026-09-25
agent: claude-code
model: claude-opus-5-5
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T64
---

# AgDR-0026 — The w0m catalog uses Backstage's entity standard, typed in Python, served over MCP

## Y-statement

In the context of **T64's developer-portal catalog, whose July decision said "build the Backstage pattern natively"
without saying what the pattern's data looks like**, facing **four separate hand-rolled registers (stacks, repos, MCP
servers, skills) with no shared schema and 129 scripts reading JSON into untyped dicts**, we decided **to describe
every catalog item as a Backstage entity (`apiVersion`/`kind`/`metadata`/`spec`, `catalog-info.yaml`), validate it
with Python types generated from or checked against the official `@backstage/catalog-model` JSON Schemas, and expose
the catalog over MCP — while still not running the Backstage framework**, to achieve **a catalog that existing tools
can read and validate, a real outside contract for typing the estate's Python, and an exit to Backstage, Roadie,
Red Hat Developer Hub or Harness without remodelling data**, accepting **that w0m's own concepts (tickets, ratchets,
offices) must be expressed as Backstage kinds, annotations or custom kinds, that we track an upstream schema we do not
control, and that the entity files become one more thing that can drift from the code**.

## Context

Measured 2026-09-25 (research: `docs/research/tech/2026-09-25-developer-portals.md`):

- Backstage is TypeScript/React/Node; running it costs an estimated 6–12 months and 2+ engineers (vendor figures).
  The July rejection of the framework (`docs/design/T64-sdlc-devops-framework-decision-2026-07-24.md`) still holds.
- Backstage's entity format has become a standard beyond Backstage. Harness IDP reads it; Zatalog (Python), bsv and
  Roadie's validator work on it offline; the canonical JSON Schemas ship in `@backstage/catalog-model`.
- Backstage 2026 models MCP servers as `kind: API`, `spec.type: mcp-server`, and skills/rules as `kind: AiResource`
  (the latter's version per a community source, to verify), and serves the catalog to agents over MCP.
- w0m's catalog data is spread across `project/policies/stacks-policy.json` (T130), `.w0m/sdlc.json` (repos, MCP servers),
  `.w0m/skills.json` and `project/test-suites.json`, each with its own shape. Only 7 estate Python scripts use
  dataclasses/TypedDict/Protocol; mypy (T188) runs without `disallow_untyped_defs`.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **A. Keep w0m's own JSON registers, build the CP catalog view over them** (July's literal reading) | No migration; nothing external to track | Four shapes stay four shapes; no validator or reader exists outside w0m; typing Python means inventing a schema | Rejected |
| **B. Backstage entity format, typed in Python, MCP-served; no Backstage runtime** | Standard, validatable by existing tools; outside contract for Python types; exit path to four Backstage-based products; matches MCP-first transport | Map w0m concepts to Backstage kinds; follow upstream schema changes; entity files can drift | **Chosen** |
| **C. Run Backstage (self-hosted or Roadie)** | Full portal, plugins, TechDocs, MCP actions out of the box | Framework cost above; React/Node stack beside the Svelte CP; July decision already rejected it | Rejected (the exit remains open via B) |
| **D. Commercial portal (Port / Cortex / OpsLevel)** | Fast to stand up; scorecards included | Paid per developer; Port's own data model means lock-in; w0m's ratchets already are its scorecards | Rejected |

## Decision

1. **Entity model.** Every catalog item is a Backstage entity. Mapping: repo → `Component` (or `System` for the
   estate); stack in `stacks-policy.json` → `Component` with `spec.type` and w0m annotations; MCP server → `API`
   with `spec.type: mcp-server`; skill → `AiResource` (or a `w0m.dev/v1alpha1` custom kind until `AiResource` is
   confirmed); owners → `Group`/`User`. w0m-only facts (ticket ids, ratchet baselines, T435 gate status) go in
   `metadata.annotations` under the `w0m.dev/` prefix, never as invented top-level fields.
2. **Source of truth.** The entity files are generated from the existing registers first (one direction, no
   hand-edits), so the registers stay authoritative until a later decision moves ownership. A drift check fails when
   the generated entities and the registers disagree.
3. **Types.** Python models (Pydantic or equivalent) for the envelope and each kind used, validated against the
   `@backstage/catalog-model` JSON Schemas pinned to a version. This is the first concrete scope for typing the
   estate's Python (see the ticket split from T64).
4. **Serving.** The CP catalog view (Svelte, T64 AC2) and an MCP endpoint both read the same entity set. Read-only
   first.
5. **Not running Backstage** is unchanged from July. Adopting Backstage later remains an option, not a plan.

## Consequences

- Positive: `catalog-info.yaml` validators and viewers work on w0m's catalog with no w0m code; a later move to a
  Backstage-based product is a data copy, not a remodel; the Python typing work gets an external schema to target;
  agents query the catalog over MCP, matching the estate's MCP-first rule.
- Negative: an upstream schema to pin and follow; a mapping layer that can be wrong (a stack is not exactly a
  `Component`); one more generated artefact and one more drift gate; `AiResource` may still move upstream.
- Neutral: the scorecard half stays w0m's ratchets, surfaced per entity through annotations.

## What this does NOT decide

- Not whether to run Backstage, Roadie or any hosted portal (still no).
- Not which Python library (Pydantic vs dataclasses + jsonschema); the typing ticket decides, measured.
- Not moving ownership of data out of the existing registers; they stay authoritative for now.
- Not TechDocs/MkDocs; documentation stays Markdown served as today.
- Not Dagger (T64 AC1/AC3), which is unaffected.
