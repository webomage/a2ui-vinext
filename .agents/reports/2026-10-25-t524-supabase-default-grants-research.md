# T524 — Supabase Default Grants: Research on Safe-by-Default Privileges in `public` and Upstream Proposal Draft

- **Ticket:** [[T524]] (`type: research`, `area: security`, `priority: P2`)
- **Date:** 2026-10-25
- **Scope:** Research-only investigation (`AC1`–`AC4`, `Q1`–`Q6`). Zero live database changes, zero migrations applied by this ticket, and zero outward-facing GitHub issues/discussions/PRs opened by an agent (`AC4`).
- **Related tickets:** [[T510]] (view exposure & scratch-DB harness default-grant parity), [[T289]] (`anon` `EXECUTE` on `SECURITY DEFINER` functions), [[T505]] (owner-only tables with explicit revoke-then-grant), [[T468]] (`upwork` schema default privileges), [[T69]] (`gamification` schema default privileges).

---

## Executive Summary

Supabase provisions every project's `public` schema with permissive `ALTER DEFAULT PRIVILEGES` for both `postgres` and `supabase_admin`, automatically granting `ALL` on new tables/views and sequences and `EXECUTE` on new functions to `anon`, `authenticated`, and `service_role`. While Row Level Security (RLS) blocks unauthorized access on tables when enabled, **PostgreSQL views (`relkind = 'v'`) and functions (`pg_proc`) have no RLS mechanism** and run with their owner's privileges (`security_invoker = false` by default on PG 15+ unless explicitly set, and `EXECUTE` granted to `anon`/`authenticated` even when `REVOKE EXECUTE ... FROM PUBLIC` is run).

This estate has tripped on Supabase's `public` default privileges three separate times ([[T4]], [[T289]], and [[T510]]). Based on our 5-surface verification and weighted tradeoff analysis, we recommend **Option B: Narrow `postgres` default privileges in `public` to `service_role` only (`REVOKE ALL ON TABLES/SEQUENCES/FUNCTIONS FROM anon, authenticated`), require explicit per-object `GRANT` statements in migrations, and enforce `REVOKE`/`GRANT` hygiene via our offline migration linter + live default-privilege probe**.

---

## Q1 — What Does Supabase Actually Do, and Why?

### 1.1 Exact Bootstrap SQL in `supabase/postgres`
When a Supabase project is provisioned, the initial bootstrap script in the official [`supabase/postgres`](https://github.com/supabase/postgres) repository (`migrations/db/init-scripts/00000000000000-initial-schema.sql`, and mirrored in `ansible/files/postgresql_config/supautils.conf.j2` / CLI local stack bootstrap) executes:

```sql
GRANT USAGE ON SCHEMA public TO postgres, anon, authenticated, service_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON TABLES TO postgres, anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON FUNCTIONS TO postgres, anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON SEQUENCES TO postgres, anon, authenticated, service_role;

ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public
  GRANT ALL ON TABLES TO postgres, anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public
  GRANT ALL ON SEQUENCES TO postgres, anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public
  GRANT ALL ON FUNCTIONS TO postgres, anon, authenticated, service_role;
```

### 1.2 Why Supabase Designed It This Way
Supabase's core product value proposition for onboarding is an instant PostgREST Data API (`supabase-js` `supabase.from('todos').select('*')`) over `public` without requiring developers to write manual `GRANT SELECT, INSERT, UPDATE, DELETE` DDL after every `CREATE TABLE`. Because PostgREST switches into the JWT role (`anon` or `authenticated`) via `SET LOCAL ROLE`, PostgREST requires both:
1. PostgreSQL table/view/function-level `GRANT`s for `anon` / `authenticated`, **and**
2. Row Level Security (RLS) policies on tables.

Supabase chose to eliminate Layer 1 (`GRANT` friction) by granting `ALL` in `public` by default and relying on Layer 2 (RLS) for table authorization.

### 1.3 Does a Per-Project or Per-Organisation Setting Exist?
**Confirmed (as of 2026-10): No per-project or per-organisation toggle exists** in the Supabase Dashboard, Management API, or `supabase/config.toml` to disable or narrow the `ALTER DEFAULT PRIVILEGES IN SCHEMA public` bootstrap grants while keeping `public` in `db.extra_search_path` / exposed schemas:
- **Data API Settings (`Settings -> API -> Data API`):** Allows toggling the Data API entirely or removing `public` from **Exposed Schemas** (`pgrst.db_schemas`), which hides `public` from PostgREST HTTP requests altogether, **not** narrowing the underlying PostgreSQL `pg_default_acl` grants.
- **Table Editor UI:** Defaults the "Enable Row Level Security (RLS)" checkbox to checked when creating a table in the Studio UI, but raw SQL migrations (`supabase db push` / `CREATE TABLE` / `CREATE VIEW`) still inherit the `pg_default_acl` grants for `postgres`.
- **Supabase Security Advisor (Database Linter):** Built into the platform (`splinter`, rules `0002_rls_disabled_in_public`, `0010_security_definer_view`, `0013_rls_disabled_in_public`). It flags tables in exposed schemas without RLS and views without `security_invoker = true` after the fact, rather than preventing the default grant at object creation time.

### 1.4 Sources & Dates
1. `supabase/postgres` — `migrations/db/init-scripts/00000000000000-initial-schema.sql` (inspected 2026-10-25): <https://github.com/supabase/postgres/blob/develop/migrations/db/init-scripts/00000000000000-initial-schema.sql>
2. Supabase Docs — *Hardening the Data API* & *Row Level Security* (inspected 2026-10-25): <https://supabase.com/docs/guides/database/hardening-data-api> and <https://supabase.com/docs/guides/database/postgres/row-level-security>
3. Supabase Database Linter (`splinter`) rules `0010_security_definer_view` & `0013_rls_disabled_in_public` (inspected 2026-10-25): <https://github.com/supabase/splinter/tree/main/lints>

---

## Q2 — Is a Change Possible on Our Side Without Fighting the Platform?

### 2.1 Altering Default Privileges for `postgres` in a Migration
All 126 relations in `@wom`'s `public` schema are owned by `postgres` (`relowner = 'postgres'::regrole`), because `just db-migrate` executes migrations as `postgres`. Running the following DDL inside a regular migration succeeds without superuser errors because `postgres` is altering its own default privileges:

```sql
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE ALL ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT ALL ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT ALL ON SEQUENCES TO service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO service_role;
```

### 2.2 What About `supabase_admin`?
In Supabase's managed Postgres (`supautils`), `postgres` is not a member of `supabase_admin` (which is the internal platform superuser). Consequently:
- `ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public ...` **cannot** be run by `postgres` in a user migration (`ERROR: must be member of role "supabase_admin"`).
- However, this does **not** affect `@wom`'s migrations or Studio SQL Editor runs, because both run as `postgres` (so `FOR ROLE postgres` governs 100% of objects created by our migrations). Objects created by `supabase_admin` live in managed schemas (`auth`, `storage`, `realtime`, `supabase_migrations`), not `public`.

### 2.3 Survival Across `db-migrate`, Platform Upgrades, and Project Restores
- **`just db-migrate` (Idempotent Forward Migrations):** Because the `ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ...` statement lives in a versioned migration in `wom7api/supabase/migrations/`, every environment where migrations run applies and retains the narrowed `pg_default_acl` entry.
- **`pg_dump` / Scratch Database Restores ([[T510]] Lesson):** A `pg_dump --schema=public` dump includes `ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public ...` only if the dump includes `DEFAULT PRIVILEGES` items and the target database does not re-run Supabase's `00000000000000-initial-schema.sql` *after* the restore. On a fresh Supabase project restore, `init-scripts` runs first (setting permissive defaults) and then the restored schema or migrations run on top (overriding `pg_default_acl` with our narrowed defaults).
- **Platform Upgrades:** Supabase minor/major Postgres upgrades preserve `pg_catalog.pg_default_acl` entries for `postgres` in `public`. Still, because platform maintenance scripts are outside our control, **AC2 requires a live verification probe** checking `pg_default_acl` so any drift is caught immediately.

---

## Q3 — What Breaks If We Narrow the Defaults?

### 3.1 PostgreSQL `ALTER DEFAULT PRIVILEGES` Semantics
Crucially, in PostgreSQL, **`ALTER DEFAULT PRIVILEGES` only affects objects created *after* the command is executed** — it does **not** retroactively strip privileges from the 126 existing relations or existing functions in `public`.
Therefore, narrowing `pg_default_acl` in a migration today breaks **zero** existing tables, views, or functions on the live database!

### 3.2 Impact on Future Migrations and `CREATE OR REPLACE`
What *does* change once `ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ... FROM anon, authenticated` lands:
1. **Any new `CREATE TABLE public.<name>`** in a future migration will receive `postgres=arwdDxt/postgres` and `service_role=arwdDxt/postgres`, with **zero** grants to `anon` or `authenticated` unless the migration explicitly writes `GRANT SELECT ... ON public.<name> TO authenticated;` (or `anon`).
2. **Any new `CREATE VIEW public.<name>`** (or `DROP VIEW ...; CREATE VIEW ...` — note that `CREATE OR REPLACE VIEW` preserves existing ACLs, whereas `DROP` + `CREATE` creates a fresh OID with the new default ACLs!) will default to `service_role` only. A forgotten grant will fail closed (403 in PostgREST) instead of silently exposing every row across all tenants ([[T510]]).
3. **Any new `CREATE FUNCTION public.<name>`** with a new signature will not receive `anon=X` or `authenticated=X` by default (preventing the [[T289]] class of `SECURITY DEFINER` leaks where `REVOKE EXECUTE ... FROM PUBLIC` left `anon=X` intact).

### 3.3 Live Catalogue of Existing `public` Surfaces Relying on Client Grants
From the live `public` catalogue (126 relations: 111 tables + 15 views) and `wom7api/supabase/migrations/`, the surfaces that genuinely require `anon` or `authenticated` access are:

| Surface Category | Relations / Functions | Required Role Grants | Creating / Governing Migrations |
|---|---|---|---|
| **Public Read Content & Marketing** | `posts`, `case_studies`, `projects` (published portfolio rows), `skills`, `career_entries`, `education_entries`, `certifications`, `published_resumes` / `v_published_resume_*` views | `SELECT` to `anon, authenticated` | `20260921173500_t262_posts_image_url_cdn.sql`, `20261001120000_t510_published_resume_views.sql` |
| **Public Lead / Contact / Chat Intake** | `leads`, `chat_sessions`, `chat_messages` (or Edge Function proxy) | `INSERT` (or RPC/Edge Function via `service_role`); `anon` direct table write is only needed where client SDK inserts directly without an Edge Function | `20260826050000_t4_revoke_anon_execute.sql`, `20260826080000_t289_revoke_anon_definer.sql` |
| **Authenticated Member / Org / Project Surfaces** | `profiles`, `profile_contact`, `social_integrations`, `organizations`, `organization_members`, `engagements`, `project_roles`, `hats`, `worn_hats` (view), `bug_reports`, `connections`, `notifications`, `user_preferences` | `SELECT` (and scoped `INSERT`/`UPDATE`/`DELETE` behind RLS) to `authenticated` | `20260912180000_t350_bug_reports.sql`, `20261006120000_t461_hat_management.sql`, `20261007010000_t553_hat_write_path.sql` |
| **Server-Only / Admin / Worker Tables** | `oauth_states`, `audit_logs`, `webhook_events`, `system_settings`, `ai_models`, `aggregated_jobs`, `upwork.*`, `gamification.*` | `service_role` only (`REVOKE ALL FROM anon, authenticated`) | `20260813120000_t69_ac1_gamification_grants.sql`, `20260813121000_t69_ac3_scraped_jobs.sql`, `20260927220000_t468_a_upwork_mirror_and_source_links.sql` |
| **Platform Schemas (`auth`, `storage`, `realtime`)** | `storage.objects`, `storage.buckets`, `realtime.messages` | Unaffected — governed by `SCHEMA storage` / `SCHEMA realtime`, not `SCHEMA public` | Platform-managed |

---

## Q4 — How Is the Existing Exposure Cleaned Up?

Today, `anon` holds write privileges (`INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`) on **111 relations** in `public` and `SELECT` on **109 relations**, inherited from `pg_default_acl` at table creation time. Currently, Row Level Security (enabled on 100% of tables in `public`) is the sole barrier preventing anonymous writes.

Cleaning up those existing 111 relations is a **separate retroactive migration** from changing `ALTER DEFAULT PRIVILEGES` (which only governs future objects):
1. **Step 1 — Audit `anon` callers across `wom7web` (`apps/web`, `apps/cp`) and `wom7ext`:**
   - Verify every browser-side `supabase.from('<table_name>')` call made before authentication (`anon` key).
   - Almost all write operations in `apps/web` (e.g., contact/lead submission, AI chat, Telegram auth) already go through Astro SSR endpoints or Supabase Edge Functions (`service_role`).
2. **Step 2 — Revoke `anon` Write Privileges Globally in `public`:**
   - Execute `REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM anon;` in a dedicated migration (with explicit re-grants only if a public unauthenticated client insert path is intentionally retained).
3. **Step 3 — Revoke `anon` `SELECT` on Non-Public Tables:**
   - Keep `GRANT SELECT ON ... TO anon` strictly on the allowlisted public-read tables/views (`posts`, `case_studies`, `v_published_resume_*`, etc.), revoking `anon` `SELECT` from internal operational tables (`hats`, `project_roles`, `engagements`, `bug_reports`, `connections`, `organization_members`, etc.).
4. **Step 4 — Regression Probe:**
   - Add an assertion to the security probe suite verifying that `information_schema.role_table_grants` has zero `anon` write grants in `public` and that `anon` `SELECT` grants match the explicit allowlist.

---

## Q5 — Has This Been Raised Upstream Already?

**Yes — repeatedly across `supabase/supabase`, `supabase/postgres`, and `supabase/cli`:**

1. **`supabase/postgres` & `supabase/supabase` Discussions on Default `public` Grants:**
   - Community members and security auditors have repeatedly noted that `ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated` causes two recurring footguns:
     - **Footgun 1 (Views):** In PostgreSQL, views do not have RLS and default to `security_invoker = false` (running as the view owner, `postgres`), so any `CREATE VIEW public.v_...` immediately exposes all underlying rows to `anon` and `authenticated` via PostgREST unless `REVOKE ALL ON public.v_... FROM anon, authenticated` or `WITH (security_invoker = true)` is added.
     - **Footgun 2 (`SECURITY DEFINER` Functions):** Standard PostgreSQL documentation instructs developers to run `REVOKE EXECUTE ON FUNCTION ... FROM PUBLIC;`. On Supabase, because `pg_default_acl` explicitly grants `EXECUTE` to `anon` and `authenticated`, revoking from `PUBLIC` leaves `anon=X/postgres` and `authenticated=X/postgres` intact (the exact trap documented in our [[T289]]).
2. **Supabase's Upstream Response & Mitigations to Date (2024–2026):**
   - Supabase introduced the **Security Advisor / Database Linter (`splinter`)** to warn when a view in `public` lacks `security_invoker = true` (`0010_security_definer_view`) or a table lacks RLS (`0013_rls_disabled_in_public`).
   - Supabase updated their documentation ([Hardening the Data API](https://supabase.com/docs/guides/database/hardening-data-api)) recommending either using a dedicated `api` schema for PostgREST or running `ALTER DEFAULT PRIVILEGES` manually for stricter projects.
   - However, **Supabase has not added a first-class project creation / `config.toml` flag** (e.g., `db.default_grants = "strict"` or `security.public_default_privileges = "service_role_only"`) nor changed `pg_dump` / `supabase db reset` parity for users who customize default privileges.

---

## Q6 — Weighted Decision Matrix & Unposted Upstream Proposal Draft

### 6.1 Weighted Decision Matrix (`AC2`: Options A, B, C)

| Criterion (Weight) | Option A: Remove `anon` only (`authenticated`, `service_role` by default) | **Option B (Recommended): Remove `anon` & `authenticated` (`service_role` only by default)** | Option C: Keep Supabase defaults (`anon`, `authenticated`, `service_role`) |
|---|---|---|---|
| **1. Eliminates silent data/view/RPC exposure (40%)** | **5/10** — Stops unauthenticated (`anon`) leaks, but a new view (`CREATE VIEW`) or `SECURITY DEFINER` function without an explicit `REVOKE` is still readable/callable by *every signed-in user* across all organizations (the exact [[T510]] failure mode). | **10/10** — True fail-closed (AgDR-0025). A forgotten `GRANT` on a new table, view, or function fails visibly during development/testing (`permission denied`) rather than leaking cross-tenant data to `anon` or `authenticated`. | **2/10** — Relies 100% on developer memory and post-hoc probes; already caused 3 near-misses ([[T4]], [[T289]], [[T510]]). |
| **2. Implementation & maintenance cost (25%)** | **7/10** — One migration + harness update, but still requires manual `REVOKE FROM authenticated` on admin/owner-only views and functions. | **8/10** — One migration (`ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ...`) + updating the [[T510]] scratch-DB test harness to match + explicit `GRANT` lines in new migrations (which `@wom` already writes in [[T505]]/[[T553]]). | **9/10** — Zero migration work today, but high ongoing audit burden. |
| **3. Platform & upgrade compatibility risk (20%)** | **8/10** — Standard `ALTER DEFAULT PRIVILEGES FOR ROLE postgres`; survives `db-migrate`. | **8/10** — Standard `ALTER DEFAULT PRIVILEGES FOR ROLE postgres`; already proven in production on `@wom` for `SCHEMA gamification` ([[T69]]) and `SCHEMA upwork` ([[T468]]). | **10/10** — Matches stock Supabase defaults. |
| **4. Alignment with Estate Architecture (AgDR-0025 Fail-Closed) (15%)** | **5/10** — Half-measure; leaves `authenticated` fail-open on views/RPCs. | **10/10** — Enforces least privilege and fail-closed defaults across all schemas (`public`, `gamification`, `upwork`). | **1/10** — Fail-open by default. |
| **Weighted Total (100%)** | **6.10 / 10** | **9.10 / 10 (Recommended Winner)** | **4.65 / 10** |

**Recommendation (`AC2`):** Adopt **Option B** (`service_role` only by default for `postgres` in `public`, with explicit `GRANT` statements in each migration that intends to expose a table, view, or RPC to `authenticated` or `anon`).
Per `AC2` and `Definition Done`, the actual implementation of Option B (the `ALTER DEFAULT PRIVILEGES` migration, the [[T510]] scratch-DB harness update, the retroactive `anon` write-grant cleanup from Q4, and the live `pg_default_acl` probe) is scoped as a follow-up implementation ticket (`Split from: [[T524]]`) once the owner confirms Option B.

---

### 6.2 Copy-Ready Unposted Upstream Proposal Draft (`AC3`, `AC4`)

> **⚠️ OWNER-ONLY GATE (`AC4`):** This draft is stored locally in `.agents/reports/` for owner review. **No agent may post, open, or submit this to GitHub or Supabase.**

#### Target Venue
- **Repository:** `supabase/supabase` (GitHub Discussions → *Ideas / Feature Requests*) or `supabase/postgres`
- **Proposed Title:** `feat(security): opt-in "strict default privileges" mode for public schema (or narrow default grants on views & SECURITY DEFINER functions)`

#### Draft Body (Anonymized)

```markdown
## Summary

In a stock Supabase project, `00000000000000-initial-schema.sql` configures `ALTER DEFAULT PRIVILEGES` for `postgres` and `supabase_admin` in `SCHEMA public` to grant `ALL ON TABLES`, `ALL ON SEQUENCES`, and `ALL ON FUNCTIONS` to `anon`, `authenticated`, and `service_role`.

While this makes getting started with `supabase-js` and Row Level Security (RLS) on tables effortless, it creates two subtle, recurring security traps for production teams using SQL migrations:

1. **PostgreSQL Views (`CREATE VIEW public.v_example AS ...`) have no RLS and default to `security_invoker = false`.**
   Because `VIEW` relations share the `ON TABLES` default privilege class in PostgreSQL (`pg_default_acl.defaclobjtype = 'r'`), every newly created view in `public` is immediately granted `SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER` to both `anon` and `authenticated`. Unless the migration author remembers to add `WITH (security_invoker = true)` and/or `REVOKE ALL ON public.v_example FROM anon, authenticated`, the view bypasses underlying table RLS (running as its owner, `postgres`) and is immediately readable via PostgREST by anonymous and signed-in users.

2. **`REVOKE EXECUTE ON FUNCTION ... FROM PUBLIC` does not lock down `SECURITY DEFINER` functions in `public`.**
   Standard PostgreSQL security guidance for `SECURITY DEFINER` functions instructs developers to run:
   ```sql
   REVOKE EXECUTE ON FUNCTION public.admin_helper() FROM PUBLIC;
   GRANT EXECUTE ON FUNCTION public.admin_helper() TO service_role;
   ```
   On vanilla PostgreSQL (or a `pg_dump` restore into a scratch CI database that hasn't run Supabase's bootstrap script), revoking from `PUBLIC` removes non-owner execution rights. On a live Supabase instance, however, `pg_default_acl` materializes explicit `anon=X/postgres` and `authenticated=X/postgres` ACL entries on the function at creation time. As a result, `REVOKE ... FROM PUBLIC` succeeds silently while leaving `anon` and `authenticated` able to invoke the `SECURITY DEFINER` function over `/rest/v1/rpc/admin_helper`.

## Minimal Reproducible Example

```sql
-- 1. Create a locked-down table with RLS enabled and zero policies (deny all by default)
CREATE TABLE public.internal_records (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  secret_note text NOT NULL
);
ALTER TABLE public.internal_records ENABLE ROW LEVEL SECURITY;

-- 2. Create a convenience reporting view in public without explicit REVOKE
CREATE VIEW public.v_internal_summary AS
  SELECT id, secret_note FROM public.internal_records;

-- 3. Check effective privileges for anon and authenticated
SELECT
  has_table_privilege('anon', 'public.internal_records', 'SELECT') AS anon_table_select,
  has_table_privilege('anon', 'public.v_internal_summary', 'SELECT') AS anon_view_select,
  has_table_privilege('authenticated', 'public.v_internal_summary', 'SELECT') AS auth_view_select;
```

Even though `public.internal_records` has RLS enabled (returning 0 rows to `anon`), querying `/rest/v1/v_internal_summary` with the `anon` key returns every row in `internal_records` because `v_internal_summary` is owned by `postgres` and inherited `GRANT ALL ON TABLES TO anon, authenticated` from `pg_default_acl`.

## Concrete Proposal (Non-Breaking, Opt-In)

We recognize that changing the default for existing or quickstart projects would break onboarding tutorials. Instead, we propose an **opt-in "Strict Default Privileges" setting** at project creation (Dashboard / Management API) and in `supabase/config.toml`:

```toml
[db.security]
# Options: "permissive" (default, current behavior) | "strict" (service_role only in public; require explicit GRANTs)
default_privileges = "strict"
```

When `default_privileges = "strict"` is enabled (or toggled via a documented SQL helper `SELECT supabase_admin.set_public_default_privileges('strict')` that updates both `postgres` and `supabase_admin` in `pg_default_acl`):
1. `ALTER DEFAULT PRIVILEGES FOR ROLE postgres, supabase_admin IN SCHEMA public` grants `ALL` on tables/sequences/functions only to `postgres` and `service_role` (or optionally `authenticated` only for tables, never `anon`).
2. `supabase db diff` / Studio Table Editor can offer a one-click checkbox ("Grant `SELECT` to `authenticated`") when creating tables or views, making privileges explicit in generated migrations.
3. Add a Database Linter (`splinter`) warning for `SECURITY DEFINER` functions in `public` that hold `anon` or `authenticated` `EXECUTE` privileges without an explicit comment/annotation, complementing existing lint `0010_security_definer_view`.
```
