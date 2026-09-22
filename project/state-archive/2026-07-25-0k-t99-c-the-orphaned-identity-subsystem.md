<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0k. ✅ DONE 2026-07-25 (evening) — T99 (c): the orphaned identity subsystem is GONE from prod -->

### 0k. ✅ DONE 2026-07-25 (evening) — T99 (c): the orphaned identity subsystem is GONE from prod

`project/tickets/T99.md` (GH #94). wom7api `61e6b1b`, wom7web `e748614c`. **Applied to production.**

Seven tables created **outside the migration history**, referenced by no functional code, one of
which (`github_user_token`) stored a real GitHub credential for an identity absent from
`auth.users`. Owner signed off on dropping all 7.

**How it was done — the shape is worth reusing for any destructive migration:**
- **Dumped first** → `<scratchpad>/t99-orphan-dump/orphan-subsystem-2026-07-25.json` (see the
  perishability warning in the ⭐ block).
- **The migration REFUSES rather than destroys.** It caps expected rows per table and `RAISE`s if
  reality exceeds them. **Proven, not assumed:** seeded one unexpected `session` row inside
  `BEGIN … ROLLBACK` → it raised *"refusing to drop public.session — it holds 1 row(s), expected at
  most 0"* and every later statement aborted, so nothing dropped.
- Dry-run green in a rolled-back transaction, then applied via **`psql`** with the
  `schema_migrations` row inserted **by hand** (`supabase db push` is unusable — history drift, §4).
- **Verified live after commit:** 0 of the 7 remain · stamp `20260725170000` present · `auth.users`
  untouched at 20.
- Code: 7 `pgTable` mirrors + 4 relation blocks + 4 dead imports removed from
  `_shared/database/{schema,relations}.ts`; `just deno-check` exit 0.
  ℹ️ `supabase/migrations/drizzle/` **still mentions the tables** — that is drizzle-kit's generated
  introspection snapshot (`out:` in `drizzle.config.ts`), imported by nothing. Left deliberately;
  do not hand-edit generated output.
- **TECH-DEBT D2 deleted** (deleted, not annotated).

🔴 **AC4 is ticked as "flagged", NOT "revoked"** — see the owner action in the ⭐ block.

**Two grounding corrections from this ticket that a future agent will otherwise repeat:**
1. 🔴 **Do NOT audit T99(a) via `pg_policy`.** The RLS policy still reads
   `USING (auth.uid() = user_id)` and looks exactly like the *unfixed* state. The fix is a
   **column GRANT**. Check `information_schema.column_privileges`. This misread briefly "reopened" a
   closed P0 during this session.
2. 🔴 **(d) is NOT a port.** The board said to reuse `github_user_token`'s `ciphertext`+`iv`
   "pattern". That is a **table shape with no implementation** — `git grep` across all 5 repos finds
   no encrypt/decrypt code, and the only holder of the shape was the subsystem (c) just deleted.
   Also: the token surface is **3 call sites, not 4** — `linkedin-{oauth,share,ingest}`;
   `src/workflows/linkedin-sync.ts` reads `social_integrations` but **never a token column**.

**The (d) design is already decided and written into the spec — do not re-litigate:**
application-level **AES-256-GCM**, key from **Infisical**, DB never holds the key. `pgcrypto` was
rejected (the key must be a literal in the SQL statement → lands in query logs / `pg_stat_statements`)
and `supabase_vault` was rejected (its root key lives in the same platform, so `vault.decrypted_secrets`
still decrypts for a compromised service-role or a platform dump — the exact threat). Sequencing is
**load-bearing**: expand → dual-write + backfill → contract. The temporary plaintext fallback in
section 4 **must not survive** section 5.
