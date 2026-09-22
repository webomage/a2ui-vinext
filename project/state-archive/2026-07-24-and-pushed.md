<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 1b. Shipped + LIVE (T123 / T49 / T124) — ✅ committed **and pushed** (verified 2026-07-24) -->

### 1b. Shipped + LIVE (T123 / T49 / T124) — ✅ committed **and pushed** (verified 2026-07-24)

wom7api `5b39a8d` and wom7web `bddd4f79` are **on `origin/beta`** (the earlier "not yet pushed"
warning here was stale — verified with `git merge-base --is-ancestor`). Both DB migrations are
applied to prod and 4 edge functions deployed. All hooks passed, no `--no-verify`.

- **T123 AC3** (authenticated-executable SECURITY DEFINER pass) — DONE. Migration
  `wom7api/supabase/migrations/20260723100000_t123_ac3_authenticated_definer_pass.sql`. Revoked the 4
  unguarded (`get_top_clicks`, `get_user_daily_tokens` [an IDOR], `trigger_vectorize_vault`,
  `hard_delete_user`); **guarded** `get_provider_quotas` in-body (CP admin calls it). Anon-over-REST
  now `42501`/404 on all of them (was `200` w/ data).
- **🔴 Live side-effect of T123 AC1 (yesterday), FOUND + FIXED:** the AI daily-token quota was
  **failing open**. `_shared/chat-core.ts` passed an **anon** client to `checkQuota`; AC1's
  anon-revoke made the RPC `42501`, and `checkQuota` returns `{allowed:true}` on error. Fixed to use
  the service client; `ai-utils.ts` fail-open now logs the error **code**. Redeployed
  agent-consultant / chat-internal / agent-architect / news-post-generator (public chat re-verified
  `200`). See memory `[[definer-revoke-quota-failopen]]`.
- **T49** (mutable search_path) — DONE. Migration `…101000_t49_fix_mutable_search_path.sql`. The
  ticket's named list was stale (4 already fixed by T68, 1 didn't exist); fixed the **9 real** live
  offenders + normalised `get_top_clicks`. `match_documents` needed `OPERATOR(extensions.<=>)` for
  `''` to resolve pgvector's operator. Advisor `function_search_path_mutable` class now **empty**.
- **T124** (publishable-key migration sweep) — DONE. Only 2 tracked `eyJ` literals repo-wide (both
  `wom7web/tests/*`, dead-JWT fallbacks removed; one also silently fell back service→anon). Supabase
  secret store **proven on the live `sb_publishable_` key by SHA-256 digest comparison** (never read
  a value); CF worker secret values are **write-only** (gap recorded). AC5 commit-time check added to
  `wom7api/scripts/security_audit.py` (proven red on a seeded key).
- **Standing checks** (T123 AC4 / T49 AC5) added to `project/scripts/w0m_audit.py`
  `check_db_grants()`: authenticated-executable definer allowlist + mutable-search_path assertion.
  Both proven red pre-migration, green post. Run: `just audit --deep`.
- **🔴 Spun-out background task (unstarted):** `news-post-generator` edge fn is **fully
  unauthenticated** (LLM spend + caller-supplied fetch w/ SSRF allowlist) and its only cost control
  was the quota check that was failing open. Task chip `task_eaabef77`. Also noted in the same pass:
  `get-upwork-status` (ungated Upwork metadata read) + `get-admin-metrics` (`!==` non-constant-time
  key compare).

Tickets T123/T49/T124 have full write-ups; T121 + T122 are effectively DONE but their rows still say
`queued` (T121 source is clean incl. ChatApp.svelte; T122 exposure closed + CV in a private bucket) —
worth flipping their status.
