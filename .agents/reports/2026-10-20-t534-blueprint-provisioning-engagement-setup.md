# T534 Research Report — Blueprint Provisioning in Engagement Setup

- **Date:** 2026-10-20
- **Ticket:** [[T534]] (Split from [[T525]] AC2; related to [[T458]], [[T461]], [[T493]])
- **Author:** Antigravity
- **Status:** Grounded across Schema, Live DB, Code, and Specs (Triangulated SSOT Protocol)

---

## 1. Grounded Reality Check (5-Surface Audit)

### 1.1 Database & Live Data (`wom7api`)
1. **`public.blueprints` (27 rows: 24 `public`, 3 `internal`)**:
   - Primary key `id uuid`, slug key `blueprint_id text NOT NULL`.
   - Write policy `"Blueprint writers hold the capability"` requires `public.is_capable('blueprint.publish') AND public.wom_acting_is('admin')`.
   - Read policy `"Unified read access"` exposes `access_scope = 'public'` to `anon` and `authenticated`, and restricts `access_scope = 'internal'` (`ai-amazon-scanner`, `integration-upwork`, `test-ab9be401`) to authenticated staff (`admin`, `manager`, `member`).
2. **`public.technologies` (80 rows)**:
   - Canonical technology registry (`id text PRIMARY KEY`, e.g., `astro`, `supabase`, `postgresql`, `react`, `nextjs`, `python`, `rust`, `go`, `kubernetes`, `kafka`, `openai`, `anthropic`, `pinecone`, `weaviate`, `langchain`, etc.).
3. **`public.blueprint_technologies` (0 rows prior to T534)**:
   - Columns: `blueprint_id text NOT NULL`, `technology_id text NOT NULL`, `role text DEFAULT 'primary'` (`CHECK (role IN ('primary', 'optional', 'alternative', 'mentioned'))`), `component_id text`, `notes text`, `sort_order integer DEFAULT 0`.
   - Every blueprint in `apps/cp/src/data/blueprints.json` (25 blueprints) and `apps/cp/src/content/blueprints/*.md` already declares an explicit `stack` and `components` map, but those links were never migrated into `public.blueprint_technologies`.
   - Furthermore, `20260817240000_t198_ac4_close_unread_public_catalogues.sql` dropped the blanket `"Public read access"` policy on `public.blueprint_technologies` because it had 0 rows and no reader; it needs a scoped SELECT policy tied to `public.blueprints` visibility (`public` blueprints readable by all; `internal` blueprints hidden from `anon` and `client`).
4. **`public.projects` (7 rows)**:
   - 2 projects are linked to blueprints (`Artemio, quiero comer!` → `webomage-stack`; `TheorQL` → `ai-rag-llm`), and 0 rows have `metadata.tech_chips` populated in live Postgres.

### 1.2 Code & Archetypes (`wom7web/apps/cp`)
- `apps/cp/src/lib/project-archetypes.ts` defines 5 commercial delivery archetypes (`externally_managed`, `bug_bounty`, `test_plan`, `consultation`, `fast_extended_audit`) from `src/data/project-archetypes.json`. Each archetype has `default_tech_chips` (capability/stack tags that map to agent `skills` and `mcp_servers`) and a default `hat_collection`.
- `ProjectManager.svelte` and `/api/project/index.ts` previously wrote `metaObj.tech_chips` into the untyped `projects.metadata` JSONB blob, while `blueprint_id` was just a passive foreign-key dropdown at the bottom of the modal with zero connection to technologies or tech chips.

---

## 2. Triangulated SSOT Decision: Where Engagement Technologies Live

| Candidate Surface | Role in the Architecture | Verdict |
|---|---|---|
| **`public.blueprint_technologies`** | Canonical template mapping each `blueprint_id` to `public.technologies(id)` with `role` (`primary`, `optional`, `alternative`, `mentioned`), `component_id`, and `sort_order`. | **Template SSOT** (Admin-managed) |
| **`public.project_technologies`** | Relational join table (`project_id`, `technology_id`, `role`, `chip_activated`, `source_blueprint_id`, `source_blueprint_version`, `provisioned_at`). | **Engagement Instance SSOT** (Provisioned at setup) |
| **`project-archetypes.json` (`default_tech_chips`)** | Commercial archetype defaults when no blueprint is selected, or supplemental skill/MCP capability tags (`deriveProjectConfiguration`). | **Archetype Derivation Input Only** |
| **`projects.metadata.tech_chips`** | Legacy untyped JSONB array in `projects.metadata`. | **Retired & Removed** (Clean cutover per AgDR-0025; no dual SSOT) |

### How Engagement Setup (`T458` / `T461` / `T534`) Meets Blueprints
1. During project/engagement setup (`ProjectManager.svelte` and `POST /api/project`), the admin or PM selects a **Blueprint** (`formData.blueprint_id`).
2. Selecting a blueprint loads its linked technologies from `public.blueprint_technologies` joined to `public.technologies` (ordered by `sort_order`, displaying each technology's name, category, and `role`: `primary`, `optional`, `alternative`).
3. Primary technologies have their tech chips ticked (`chip_activated = true`) by default; optional/alternative technologies can be toggled on or off by the admin/PM before saving.
4. Ticked technology slugs feed directly into `deriveProjectConfiguration(selectedArchetypeId, activatedTechChips)` to derive agent `skills` and `mcp_servers`.
5. Saving the project calls `public.wom_provision_blueprint_technologies(p_project_id, p_blueprint_id, p_activated_technology_ids)`, which writes `public.project_technologies` once (recording `source_blueprint_id` and `source_blueprint_version` from `blueprints.updated_at`) and strips any legacy `tech_chips` key from `projects.metadata`.

---

## 3. Open Questions & Weighted Decisions

| # | Question | Recommended Answer | Cost | Risk | Unblocks |
|---|---|---|---|---|---|
| **Q1** | Should `source_blueprint_version` on `public.project_technologies` use a separate integer column on `blueprints` or the blueprint's `updated_at` ISO timestamp (`to_char(b.updated_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"')`)? | **Use `to_char(b.updated_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')`** — `blueprints.updated_at` is already maintained by trigger `update_blueprints_updated_at` on every edit. | Low | Low | T534 AC2, AC4 |
| **Q2** | Should `internal` blueprints (`ai-amazon-scanner`, `integration-upwork`, `test-ab9be401`) have their `blueprint_technologies` rows hidden from `anon` and `client` roles via RLS? | **Yes** — `blueprint_technologies` SELECT policy joins `public.blueprints` and requires `b.access_scope = 'public'` for `anon`, or staff role (`admin`, `manager`, `member`) for `internal`. | Low | Zero | T534 AC3 |
| **Q3** | What happens when a project has no blueprint (`blueprint_id IS NULL`)? | Archetype default chips still compute `metadata.skills` and `metadata.mcp_servers` via `deriveProjectConfiguration`, while `project_technologies` holds any explicitly selected canonical technologies. | Low | Low | T534 AC4, AC5 |
