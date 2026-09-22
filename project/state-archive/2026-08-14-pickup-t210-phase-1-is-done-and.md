<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ## ⭐ PICK UP HERE — 2026-08-14 — **T210 Phase 1 is done and proven; T72 closed; the board's status column was unreadable -->

## ⭐ PICK UP HERE — 2026-08-14 — **T210 Phase 1 is done and proven; T72 closed; the board's status column was unreadable for 41 of 203 rows and is fixed.**

**Session of 2026-08-14 — 45 commits across wom7web / wom7api / wom7ext. All pushed to `beta`, all repos clean.**

**Start here — two owner actions, in this order.**

```
cd wom7api && just db-migrate     # 20260814240000 — the legacy user_id was FORGEABLE
cd wom7api && just deploy         # the call sites now write profile_id
```

**Then the last task, gated:** `just t210-drop-readiness` decides when `social_integrations.user_id`
and `social_integrations_user_provider_urn_idx` may go. **All four callers are already clean in the
tree**; it stays red until the hardening is applied. The exact SQL is recorded in the change's
`tasks.md` — 🔻 **deliberately not a migration file yet**, because one that must not be applied is a
loaded gun in a directory whose contract is *apply everything here*, and this session paid for a
premature drop once. ⚠️ **The gate reads the GIT TREE and says so** — the edge functions run whatever
`just deploy` last pushed, so green means *ready to deploy*, not *already deployed*.
🔑 **The column and the index go TOGETHER**, and so does the bridge trigger — it exists only to keep
the two keys in step, and a trigger referencing a dropped column is a runtime error awaiting the
next write.

🔴 **THREE DEFECTS SURFACED WHILE MIGRATING THE CALL SITES.** All fixed; all worth reading once.
1. **The re-key broke the live LinkedIn connect flow.** `linkedin-oauth:145` upserts with `onConflict: 'user_id,provider,provider_urn'` — a name Postgres resolves against a **real index**, which the re-key dropped. ⇒ **A re-key has TWO contracts with its callers: the column they write and the key they NAME.** The migration was deliberately designed as two steps so the deploy could lag; that reasoning covered the column and missed the index, which makes it a one-step rollout with a longer comment.
2. **The legacy `user_id` was forgeable.** All four policies test `profile_id`, so nothing constrained `user_id`: an owner could write a victim's account id onto their own row and still satisfy the policy. ⚠️ **Not a token leak** — D1 blocks the read, `USING` blocks touching a victim's row — but **deployed code still reads by `user_id`**, so a row claiming a victim's account would be served *to that victim*. Measured **1 forged row before, 0 after**. ⇒ **A derived value must never be taken from the caller**; the bridge now recomputes it on every write.
3. **Two unscoped writes, same class, found in passing.** `linkedin-share`'s 401 handler deactivated by `provider_urn` alone on a **service-role** client, and `ConnectionsManager.disconnectIntegration` **DELETED** by `provider_urn` alone — two people who linked the same company page disconnected each other, and an admin (whose policy spans all rows) hit everybody. ⚠️ The file's own comment warns about this class three lines above the first one.

✅ **What held under attack:** `authenticated` cannot SELECT the tokens, cannot read them via
`UPDATE … RETURNING`, and cannot infer them through a `WHERE` clause (both permission-denied — D1
has no read *or* inference channel); an unconfirmed signup claims nothing; and a stranger cannot
reassign another person's connection, because the UPDATE policy's `USING` doubles as its
`WITH CHECK` ([[T198]] E7 does not regress).

🔑 **How it was found, which is the transferable part:** a probe expected 1 conflict row and got
**3**. Chasing that discrepancy — rather than adjusting the expectation to 3 — is what surfaced the
trigger's real event. **An off-by-N in a count is a claim about mechanism; make it explain itself.**

**Then the remaining work, which is deliberately post-apply:** re-point the **~12 call sites in 5 files** (`linkedin-oauth`, `linkedin-ingest` ×5, `linkedin-share` ×2, `ConnectionsManager.svelte` ×2, the system registry) from `user_id` to `profile_id`, then a follow-up migration dropping `user_id`. ⚠️ **They cannot be fixed first** — `profile_id` does not exist until the migration applies, which is the Phase 1 task 1.4 trap. A bridge trigger fills whichever key is missing, so the two steps do not have to be simultaneous.
🔑 **The bridge works only because RLS `WITH CHECK` evaluates the row AFTER a BEFORE ROW trigger** — an un-migrated caller supplying only `user_id` still satisfies a policy keyed on `profile_id`. **Measured with a throwaway table in a rolled-back transaction**, because the whole two-step rollout rests on it.

**[[T194]] AC5 is UNBLOCKED** (4.2), and the argument is worth carrying: T194 rejected nullable `user_id` because it *"breaks its `user_id = auth.uid()` RLS"* — correct **while the account was the only identity available**. Phase 1 supplied the other one, so the unique key and all four user-facing policies now key on `profile_id`, which is never null. ⚠️ **Unblocked ≠ done**: re-pointing the callbacks **newly** persists candidate tokens, so it lands with encryption ([[D1]]), not before.
🔴 **D1 is asserted inside the re-key migration and the assertion was mutation-tested** — granting `SELECT` to `authenticated` first makes it refuse by name. That revocation, **not** the RLS policies, is what keeps the token columns unreadable from a client.

**Phase 4 also closed three tasks outright:** 4.3 drop `linkedin_profiles` (0 rows / 0 FKs / 0 callers, Drizzle + both `authz_*` lists cleaned), 4.4 **KEEP `profile_data`** — its premise did not hold, it has a live reader at `ConnectionsManager.svelte:290` and is not a duplicate of `profile_snapshots` — and 4.5 filed as **[[D55]]**, which grew on measurement from one bad policy to **17 declared-and-absent** against **177 of 237 live policies undeclared**. ⚠️ D55 is a **documentation** defect, not a hole: Drizzle does not apply policies here.

**Phases 1–3 are all APPLIED LIVE and verified independently of their own probes.** Phase 3 turned out to be a **repair**: Phases 1 and 2 changed the identity model while `handle_new_user()` was left behind, so a new signup landed `auth_user_id = NULL` (⇒ **the user could not see their own profile**) and a candidate's signup **failed outright** on `profiles_email_unique`. 0 users were harmed — nobody signed up in the window — and both are regression cases now, **confirmed RED against the unmigrated schema**. Ticket ACs: **AC1/AC2/AC3/AC5 done, AC4 half** (conflict state live, provider fallback deferred), AC6/AC7 are Phase 4.
🔑 **The claim is a DB trigger, not application code** — the trigger already creates the profile on every path that mints an account (OAuth, email, admin API, dashboard), so claiming in a handler would race a row already inserted. And **confirmation is a security gate**: `email_confirmed_at` is NULL at INSERT for email/password signup and **6 of 20 live accounts are unconfirmed**, so an unconfirmed signup defers rather than being handed a stranger's résumé and credentials.

🔴 **THE LESSON OF THIS SESSION, and it recurred at two levels.** A probe must be re-run across the transition it exists to survive — and then checked for whether it can still see the thing it claims to measure.
1. **Phase 2:** the probe passed at authoring time and went **false-red** the moment its own migration landed — the duplicate fixture was rejected by the now-live index *before* the migration ran, so it announced "the guard did not fire" while the constraint worked perfectly. Fixed by dropping the index inside its own rolled-back transaction.
2. **Phase 3, one level up:** all nine cases re-apply the migration inside their transaction, so they proved the **FILE**, not production. Demonstrated by sabotaging the deployed `handle_new_user` to its old broken body — the suite **stayed green**, because `\i` reinstalled the good version first. The probe now opens with a live-state read that applies nothing and reports `APPLIED / NOT APPLIED / DRIFTED`; the same sabotage against it correctly reports `calls_claim: got 0, want 1`.
⇒ **Surviving the apply is not enough. Ask whether the probe can see past its own fixture to what is deployed.**
⚠️ Also: **a side-effecting call and an assertion that reads its effect cannot share one `SELECT` list** — SQL does not guarantee evaluation order there. A case reported `outcome='claimed'` beside `id_unchanged=0` until they were sequenced; only the self-contradiction gave it away.

**Phase 2 is APPLIED LIVE (owner ran `db-migrate` 2026-08-14) and verified independently of its own probe** — index definition as expected, both comments landed, ledger row `20260814180000` present, `db-drift-check` 211/211 clean, **2** `schema_change_log` events ⇒ in-band, not around `wom_ddl_guard`. Data: **20 rows · 20 distinct `lower(email)`**.
🔑 **The guard was seen RED, and a mutation test is why that means something.** The probe manufactures the duplicate the migration refuses. A guard-stripped mutant was run: **Postgres also exits 1** (`could not create unique index … is duplicated`) naming one key, no ids, no count — so *"did it fail?"* would have passed the mutant. The probe asserts the duplicates were **named**. ⇒ **When two failure paths share an exit code, the exit code is not the test.**
🔴 **And then the apply broke the probe, which is the better lesson.** RED/GREEN test the migration *file*; with the index live, the duplicate fixture was rejected by the constraint **before** `\i` ran, so the guard was never reached — and RED announced *"THE GUARD DID NOT FIRE. A duplicate was inserted and the migration proceeded"* while the constraint was in fact working perfectly. Fixed: both cases `DROP INDEX` inside their rolled-back transaction, and a third branch names a fixture rejected by the live index as a **probe** defect. ⇒ **A probe that passes only in the state it was written in has an expiry date — and here the expiry was the one event it existed to survive.** Re-run a probe across the transition it is meant to outlive, not only before it.
🔴 **Three facts the spec recorded were wrong** (corrected in place, not deleted): `profiles.email` is **`text NOT NULL`** — so "NULLs permitted" is automatic and the partial predicate is **vacuous** today, kept only for sibling consistency and labelled as such; there are **four** unique indexes on `profiles`, not one, incl. **`profiles_work_email_unique`** live since 2026-07-12, making Phase 2 the *third* instance of an established pattern rather than a new idea.

**What T210 Phase 1 delivered (all verified, not asserted)**

- Migration applied by owner: `profiles.auth_user_id` exists, `profiles_id_fkey` dropped, **20/20 backfilled**. `profiles.id` is now the PERSON; `auth_user_id` is the ACCOUNT, nullable.
- **`just profile-detach-probe`** proves AC1+AC2 **per role** against a real accountless fixture in a rolled-back transaction: `service_role=1, authenticated=0, anon=0`, 5 inbound FKs intact. It asserts service_role CAN see the row deliberately — a passing *"nobody can see it"* is otherwise indistinguishable from a revoked grant ([[T69]]'s failure).
- **15 call sites re-keyed**, against a spec that said **one**.

🔴 **The lesson this ticket taught three times: counting a pattern is not reading the code.**
1. The first census scanned `.from('profiles')` — blind to the FK writes entirely.
2. The spec said "one code site"; there were **fifteen**.
3. I filed `ResumeParser:133` as a low-severity *read* from its `.eq('profile_id', …)` shape. It is a **DELETE** — the highest-severity of its group.
⇒ **A blast radius is a property of the RELATIONSHIP being changed** (here, the five FKs into `profiles`), not of a table name appearing in a string.

**Also closed today**

- **[[T72]] DONE 6/6** — OpenSpec specifies CHANGES, Gauge specifies TESTS (**both standard, not rivals**; 381 `.spec` files are the test corpus and the gate has a probe asserting they are never flagged). Two legacy DSLs retired, decision recorded **first**. `just spec-systems` + `spec-systems-test`.
- **[[T134]] 11/12** — AC12 done: `system.read` named in `apps/cp/src/middleware.ts` with a **one-query promotion trigger** (`SELECT count(*) FROM capabilities WHERE capability LIKE 'system.%'`, **0** today). ⚠️ Measured: the RBAC machinery is **already live** (38 capabilities / 24 prefixes, 10 offices, `office_capabilities`) — only the `system.*` rows are missing, so the guard swap is a data change plus one line, not a subsystem.
- **[[T138]] 3/9** — `clients_email_unique` applied; UNSAFE is 0; gate promoted to blocking. **AC3's `leads.email` half REFUSED with cause**: `contact-submit` INSERTs one lead per enquiry, so a lead is an *event*, not an identity — that index would fail the second enquiry from the same person.
- **[[T94]] specified (0/10)** on the owner's connector ask; **[[T213]] filed** (P2, corrected down from P0 — see below); **[[T209]]/[[T211]]** duplicate resolved.

**🔴 Two gates that were lying, both fixed**

- **`TASKS.md` status column**: the parser split on every `|`, but **41 of 203 rows contain a literal one**, so those rows read as 7–14 columns and **every one silently defaulted to "queued"**. Also fixed the reverse: progress notes appended as *new columns*. Real impact — *now/live* went **12 → 3**. The generator now splits on unescaped pipes only.
- **`lookup-index`** had **two exit paths that disagreed**, and its `--json` branch was *crashing* (a `frozenset` in `json.dumps`) — a traceback exits 1 exactly like a finding. Both probed now.

**Owner actions outstanding**

1. **[[T213]]** — rotate **Adzuna** + **Jooble** at the providers (Reed's key is already dead). Then I fix the fail-open path: all three fetchers `return []` on any HTTP error and `job-aggregator` records that as `count: 0` **with no error field**, so a dead credential reads as a successful empty fetch.
2. **[[T134]] AC11** — a **read-only** infisical identity. Task 3.1 is explicit that a write-capable token would be privilege escalation for a read-only page.
3. **[[T72]] follow-up needs a ticket** — **16 Gherkin `.feature` files, every one inside a w0m repo**, none in a client project (the inverse of the standing rule). Grew **9 → 16** while nothing migrated; `cucumber-js` runs them as `test:e2e`, so they are live coverage to migrate, not delete. The gate reports and deliberately does not fail on it.

**Standing traps re-confirmed today**

- `just db-migrate` is **agent-denied** — write migrations, the owner applies.
- **Backticks in a `git commit -m` string execute as command substitution.** Bit twice; use a heredoc with `-F -`.
- `osv-scanner.toml` must sit **beside the lockfile**, not at the repo root — a root copy is silently ignored. That is why `wom7ext` needed `extension/osv-scanner.toml`.
- The shell resets to `/Users/proto/Projects/@self/@wom` between calls; `cd` into the repo first.

---
