<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0t. 🆕 OWNER ASK 2026-07-25 (late) — DB relations on indexed identifiers. **DEEPLY GROUNDED — DO NOT FILE AS ASKED.** -->

### 0t. 🆕 OWNER ASK 2026-07-25 (late) — DB relations on indexed identifiers. **DEEPLY GROUNDED — DO NOT FILE AS ASKED.**

> *"we have to design w0m database relations on the base of fast calculated internal supabase indexes
> and have all slugs/usernames/company/project/etc matching via that schemas connexions indexes and
> objects properties"*

**Not ticketed.** A full grounding sweep ran 2026-07-25 (192 migrations + the drizzle mirror + app/edge
call sites + every ticket + `SCHEMA-AUDIT-2026-07-11.md`). **Do not re-derive any of this.**

**Verdict: not a duplicate of any ticket — but the ask is partly mis-premised, so filing it verbatim
would produce a wrong-shaped ticket.**

🔴 **Three of the four identifiers the ask names barely exist.**
- **`username` / `handle`: ZERO columns** anywhere in the schema. There is no username concept in the DB.
- **`slug`: only two real columns** — `posts.slug` and `gamification.badge_definitions.icon_slug`, plus
  `blueprints.blueprint_id` acting as one. **No slug on `projects`, `clients`, `contracts`, `squads`,
  `units`, or any user entity.**
- **Zero** `citext`, **zero** generated/derived columns, **zero** materialized views.
⇒ This is largely **net-new identifier design**, not re-indexing existing ones.

🔴 **The "ad-hoc string matching in app code" premise is only weakly supported.** All 3 slug call sites
are already index-backed; **zero `.ilike()`** in app or edge code. **The real damage is inside the
database:**
1. **`clients` / `leads` / `profiles` name+email are neither unique nor indexed** — while
   `client-register/index.ts:85` and `seed-demo` do `.eq("email", …).maybeSingle()` against them.
   `maybeSingle()` **throws on duplicates, and nothing prevents duplicates.**
2. **`units.squad` is a trigger-synced denormalized copy of `squads.name`** — and the trigger
   **shipped broken** (`search_path=''` + a bare table reference), so *"every unit insert carrying a
   squad_id, and every squad reassignment, fails today — including from the CP admin UI"*
   (`20260720190000_offices_split_and_squad_move.sql:80-96`).
3. **The ORM mirror cannot support "matching via schema connections" today:** `relations.ts` declares
   relations for **9 of ~80 tables** — none for `clients`/`projects`/`contracts`/`proposals`/`invoices`/
   `leads`/`profiles` — and `schema.ts` omits `contracts.client_id` entirely though it exists live.
4. **No index policy:** two competing naming conventions, **zero `CONCURRENTLY`**, **no
   `pg_trgm`/`unaccent`/`tsvector`/GIN**, exactly **one** functional index
   (`profiles(lower(work_email))`). The one bulk index pass was reactive (Supabase-advisor-driven).
5. **The clearest single piece of evidence for the ask:** migration `20260712120000_profiles_work_email.sql:12-16`
   backfilled org identity by matching **`lower(p.full_name) = lower(tm.name)`** because no FK existed;
   `team_members.user_id` only arrived 8 days later.

🟢 **Already owned — hand off, do not duplicate:** `contracts.client` free-text vs the `client_id` FK →
**[[T101]]** (verbatim in its scope) · platform/`source` enum-vs-free-text → **[[T90]]** ·
blueprint uuid-vs-slug duality → **`SCHEMA-AUDIT-2026-07-11.md` F2** (documented, unticketed).
⚠️ **`SCHEMA-AUDIT-2026-07-11.md` §6 already states the design principle the owner is asking for**
(Supabase as *"the relational index + RLS layer that ties systems together"*), dated 2026-07-11 — and
the file is at the **repo root**, not under `wom7web/docs`.

⚠️ **Caveats that must be honoured before sizing:** all of the above is **migration-file + ORM truth,
NOT live-DB truth** (the audit itself warns the migrations lagged the live DB) — re-verify against
`pg_indexes` / `information_schema`. And **"fast calculated internal supabase indexes" is ambiguous**
across B-tree indexes / generated columns / materialized views / the Supabase advisor; the last three
are entirely absent, so **one clarifying question to the owner is needed** before design.

🔴 **Side finding worth its own action: [[T87]], [[T90]] and [[T94]] are P1/P2 board rows with NO
ticket files** (same class as T99 and T109, both reconstructed) — and they are exactly the tickets a
schema-relations ticket must hand off to. `[[T90]]`/`[[T94]]` wikilinks across other tickets resolve to
nothing.
