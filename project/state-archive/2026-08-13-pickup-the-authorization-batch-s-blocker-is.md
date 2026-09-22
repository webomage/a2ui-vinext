<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### ⭐ (was) PICK UP HERE — 2026-08-13a — **the authorization batch's blocker is UNBUILT SPEC WORK, not an owner decision -->

### ⭐ (was) PICK UP HERE — 2026-08-13a — **the authorization batch's blocker is UNBUILT SPEC WORK, not an owner decision (corrected 2026-08-12). Probe suite 14 RED → 6 RED / 11 GREEN. Astro 7 unblocked; T202 AC3/AC6 + T207 AC1 done.**

> **Written for an agent with none of my context. Every number measured 2026-08-12 against the live
> database.**
>
> ### ✅ A. What is GREEN now — and what proves it
> `just authz-probe` — **17 probes, 6 RED / 11 GREEN** (was 14 RED when the suite was built).
> Four gates, each with its own red probes, all wired into `wom7api/justfile`:
> `authz-probe` · `authz-blanket-check(-test)` · `authz-definer-check(-test)` ·
> **`authz-bucket-check(-test)`** (new 2026-08-12, 8/8 probes firing) · `authz-write-probe`.
>
> **Closed and verified live in the last session** (ledger 206/206, `db-drift-check` OK):
> · **[[T199]] AC5** — both T155 backup tables **dropped**. They held **188 rows, more than
>   `contracts`' 96**, closed only by `rowsecurity` + **zero policies** — an accident of RLS
>   semantics that **does not hold for the service role**, which 51 of 55 edge functions present.
>   Proven redundant first: all 93 rows absent from `contracts` matched a survivor by `external_id`,
>   no survivor was poorer, and the fk backup's repoint had completed (0 orphans).
> · **[[T199]] AC1** — `project/authz-buckets.jsonc` is now the **single authority** for which
>   buckets may be public. `blueprints` closed on **both axes** (`public=false` **and**
>   `Public Access` narrowed `['assets','blueprints']→['assets']`, with `assets` asserted intact).
>
> ### 🔬 B. Three things measured that were WRONG in the tickets — do not re-derive them
> 1. **[[T198]] E7 is REFUTED — there is no defect.** It claimed 6 UPDATE policies lack
>    `WITH CHECK` so "the resulting row is unvalidated". **Postgres uses the `USING` expression as
>    the `WITH CHECK` when none is defined**, so a missing check is the SAFE default. Refuted by
>    attempt: a non-admin reassigning their own `social_integrations` row gets
>    `new row violates row-level security policy`. The earlier "CONFIRMED LIVE" run was false
>    because **the table's one row is owned by an admin**. ⇒ **An actor probe must assert WHO it
>    ran as** — `LIMIT 1` inherits that owner's privileges.
> 2. **[[T199]] F1's severity was wrong.** It read as "blueprints bucket PUBLIC while 3 blueprints
>    are internal", implying client content was exposed. The bucket held **7 objects, all
>    `test-<timestamp>.png` from one day**, and **no blueprint row referenced any of them.**
> 3. **The office catalog authorises NOBODY.** `user_roles` has **no office column**; the only FK
>    into `offices` is `office_capabilities.office`; **0 of 259 policies** and **0 functions**
>    mention an office; **`resource_grants` does not exist**. The 10 offices are a *vocabulary*.
>
> ### 🔴 C. The blocker is UNBUILT SPEC WORK, not a decision — corrected 2026-08-12
> The 6 remaining RED probes all trace to **[[T198]] AC6: remove the possession arm.** It cannot land
> alone — removing possession without a scoped replacement locks admins out — so it needs
> **`resource_grants` + `wom_can_on()`**.
>
> 🔬 **Do not re-open the "realm: name or scope column?" question. It was decided in writing on
> 2026-07-16 and confirmed 2026-07-22, and never built.** Three earlier summaries (mine) called it an
> open owner decision. It is not:
> · `openspec/changes/2026-07-22-rbac-unified-axes/proposal.md` — office is **axis 3,
>   resource-scoped** (`offices` + `resource_grants`), and it **DROPS** `office_grants(user_id,
>   office, project_id)` explicitly: *"Neither table exists live, so this costs nothing now and would
>   have cost a migration later."*
> · `openspec/changes/2026-07-16-rbac-capability-model/tasks.md` **3.2** — **the full DDL**:
>   `scope_type('global'|'project'|'blueprint'|'client'|'contract'|'cohort'|'interview'|'lead')`,
>   `num_nonnulls(office,capability)=1`, `(scope_type='global')=(scope_id IS NULL)`. **3.3** —
>   `wom_can_on(cap, resource_type, resource_id)` AND-ed with `wom_can(cap)`.
> Both changes are **ACTIVE and validated**, at **0/49** and **6/43** tasks. Neither is archived.
>
> ⇒ **Two migrations, already written as spec tasks, stand between AC6 and the 6 RED probes.**
> ⚠️ **Never land `resource_grants` without `wom_can_on()` in the same change** — a grant table with
> no reader is a fifth place authorization *looks* like it happens and does not.
> ⚪ **The only owner call left here is the office VOCABULARY** — see D.
>
> ### ⚪ D. Other owner decisions outstanding
> · **[[T206]] AC1 — a Supabase DASHBOARD check only the owner can do.** Per-service Postgres roles
>   (owner's choice 2026-08-12) need a `role: svc_x` JWT. **No JWT secret exists in infisical and the
>   keys are the new opaque format** (`sb_publishable_`/`sb_secret_`). If the legacy JWT secret is
>   still retrievable, or a new secret key can bind to a custom role ⇒ **cheap**. If neither ⇒
>   **rewriting DB access in 53 edge functions**. It gates the estimate, not the design.
> · **[[T117]]** office **VOCABULARY** — the only genuinely open piece, and it is cheap.
>   **Q1 the area names**: `fin · sales · account · delivery · eng · quality · talent · design ·
>   growth · gov`, derived from live capability domains. ⚠️ **3 are agency-only** (`sales`,
>   `talent`, `growth`) — **the realms are NOT symmetric**, and assuming they are invents six
>   offices nobody can hold. **Q2 realm prefix in the key?** ⇒ **recommend B: realm as a COLUMN on
>   `offices`, area as the key.** `client.acme.fin` re-introduces the parsed-string failure the
>   scope column removed (**5th instance** here) and needs a `clients.slug` that does not exist
>   ([[T204]] AC8). ⏳ Free until **task 3.2 runs** — `resource_grants` is not empty, it **does not
>   exist**; `scope_type` is a CHECK constraint, so widening it after grants exist is a migration
>   on live rows.
> · **[[T203]] AC1b** — 14 of 20 `xp_ledger` rows are test residue, and a **wallet exists for a user
>   that is not in `auth.users`**. Clear or keep (⚠️ the ledger is append-only by design).
> · **[[T165]]** — still ON HOLD by owner decision 2026-08-07; **[[T167]] must not start before it.**
>
> ### 🟢 F. Astro 7 is UNBLOCKED (2026-08-13) — the blocker was an empty patch file
> The owner asked why we are not on Astro 7 and recalled a package-compatibility problem.
> **There was none.** `pnpm-workspace.yaml` declared a patch for `@astrojs/cloudflare@13.3.0`
> pointing at a **0-byte file**, created empty in `79ab2e30` and never having had content. pnpm
> hard-fails on `ERR_PNPM_UNUSED_PATCH`, so it **pinned the adapter to exactly 13.3.0** — and the
> adapter is what Astro builds against.
> ✅ **Deleted. `pnpm install` clean, ALL FIVE apps build, lockfile shed 61 packages (1687→1626).**
> ✅ **Every peer is already satisfied**: node 24.17.0 · wrangler 4.112.0 · svelte 5.56.4 · TS 6.0.3.
> The upgrade **fixes** a live unmet peer (`@astrojs/svelte@8` wants TS ^5.3.3; we run 6.0.3).
> ⚠️ **Still to do, and it is real work** ([[T103]] AC6-AC8): bump **all six** manifests — the dry
> run bumped 3 and pnpm cheerfully resolved **astro 6.2.1 AND 7.2.1 side by side**, so assert one
> major in the lockfile; `wrangler` is a **three-repo lockstep**; and Astro 7's breaking changes
> across **220 `.astro` files** are unexercised. Clears **6 of 13** osv suppressions.

> ### ⚠️ E. Gotchas earned this session
> · **`just authz-remap` did NOT regenerate the office catalog** until 2026-08-12 — a stale
>   `office_caps.json` showed a separation-of-duties break that a migration had fixed two days
>   earlier. **Fixed**, but the general rule stands: a "re-measure everything" recipe that skips an
>   input is green, confident and a day old.
> · **Two authorities disagreeing is worse than one being wrong.** The F1 probe carried its own
>   hardcoded bucket allowlist, so the gate went GREEN while the probe stayed RED on the same
>   bucket. Both looked correct on their own output.
> · **`boolean::text` in Postgres is `'true'`, not the `'t'` psql displays.** A gate that got this
>   wrong reported 0 public buckets out of 7 and emitted 6 confident STALE findings.
