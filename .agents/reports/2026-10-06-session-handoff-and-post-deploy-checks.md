# Session handoff 2026-10-06: what is landed, what the deploy does, what to check afterwards

Ticket: [[T439]] (context shell), with [[T544]], [[T545]], [[T546]], [[T547]], [[T548]], [[T535]], [[T543]], [[T537]], [[T505]], [[T533]], [[T112]].
Everything below is on `origin/beta`. Nothing in the "deploy" column is live until the owner runs `just deploy-all` (agents never run it).

## 1. What the next `just deploy-all` does

| Change | Ticket | Effect |
|---|---|---|
| Migration `20261004140000` | T543 | project-manager enforcement functions (proven on a throwaway Postgres only) |
| Migration `20261005210000` | T535 | `wom_upwork_freshness()`; the Upwork card on `/admin/sync-health` reads it |
| Migration `20261006120000` | T544 | `profile_experience` readable by its owner or an MFA admin only (was: every signed-in account) |
| Migration `20261006130000` | T545 | admin read of `profile_cv_facts`, `profile_contact`, `profile_identity`, `profile_public_settings` behind `wom_admin_reads_personal_data()` |
| CP app: `/` home router; `/admin` widgets moved to `/admin`, `/admin/secrets`, `/admin/scrapers`, `/admin/domains`, `/admin/ai-agents`; `AdminLayout`, `ClientLayout`, `member-routes.ts` deleted; hat switcher in the shell | T439 C4a, C4b | what to look at in section 2 |
| Authz probes X8/X13/X18/X23 replaced by switch-aware ones, X30-X35 added | T544, T545 | they switch on when the ledger lists the migrations |

**Correction, same day: the first deploy attempt FAILED at its pre-flight, and my readiness claim was wrong.** I had measured readiness with `just test-prepush`, which does not include `state-check`, `check-guardrails`, the full `test` tier or `goldens`. The attempt stopped at `state-check` (STATE.md stale: T548 was created after `state-save`). Replaying the deploy's own later stages then found five more blockers, all fixed and landed (see [[T503]] status note): inline-credential scan tripped by four test fixtures, `py-test` collection error (`psycopg` 3 undeclared), skills integrity drift (an OSV ignore file in the active `mmd-validate` copy only), a board row disagreeing with a done ticket (`tasks-bounds`), and the new `tools-upgrade` suite resolving to "recipe not found". Nothing was applied: the failure was before the confirm prompt, migrations and ship.

**Measured on the real live tree after the fixes (2026-10-06 evening):** `just _deploy-preflight` rc 0, `just check-guardrails` rc 0, `just test` rc 0 (all blocking suites pass; the 7 advisory failures are the same 7 as on Oct 4), `just goldens` rc 0 (1 scenario), `just check-warp` rc 0, `just check-infisical` rc 0, en0 has IPv6. Live checkouts of all five repos are 0 behind, 0 ahead, 0 dirty. Four migrations are still pending. The only stages not exercised are the Touch ID confirm, `db-migrate`, the app deploys and `smoke-live`, which only the owner's run can do.

## 2. After the deploy: check, in this order

Read-only checks an agent can run for you are marked (A); the rest need a signed-in browser (owner).

1. (A) `just db-drift-check`: 0 pending.
2. (A) `just authz-probe`: X8, X13, X18, X23, X30-X35 present and GREEN. The only RED allowed is X20 (`profile_identity` empty, T505).
3. (A) T544 AC4: a non-owner non-admin counts 0 rows of `profile_experience`; the owner's count is still 95.
4. (A) T545 AC3: an aal2 admin sees each of the four tables' full counts; a plain member only their own.
5. (A) T535 AC5: `wom_upwork_freshness()` answers; the card has live numbers.
6. Owner, signed in as an MFA admin: `/` lands on `/admin`; `/admin`, `/admin/secrets`, `/admin/scrapers`, `/admin/sync-health`, `/admin/domains`, `/admin/ai-agents` load; the hat switcher shows on `/me` and on an org page; `/o/w0m/money/contracts` loads.
7. Owner, as a client persona (artemio or demo): `/` lands on `/o/<org>`; `/client/portal` redirects there; each money page shows only that org's rows.
8. Owner, as a plain member: `/` lands on `/me`.
9. Then tick: T439 AC4/AC5, T535 AC5, T544 AC4, T545 AC3, T543 as applied.

If anything fails, tell the agent what you saw; start from the logs and the code, not from a redeploy.

## 3. Owner decisions waiting, with a recommendation each

| # | Decision | Recommendation | Weight |
|---|---|---|---|
| 1 | `/` fixed rule vs "last-used context" (T439) | keep the fixed rule | low cost, nothing blocked |
| 2 | Client in several orgs lands in the first by name (T439) | keep until someone has two | low |
| 3 | Keep hats and `switch-role` (T439 D3, assumed) | keep until T458 AC6 | low |
| 4 | Admin read of personal data is ON for the testing phase (T545) | ON now; narrow before the first outside user; decide `profile_identity` (KYC) separately | tracked on T537 AC10 |
| 5 | Screening-answers import into `proposals.data`, additive (T533 AC2/AC3) | go | medium, no code yet |
| 6 | Weekly tools job proposes, never writes (T546) | done (option C); manual `known_good` edits stay allowed | AC4 after 2026-10-12 |
| 7 | `credential-probe` red on a member route (T547) | decide probe-or-route, test first | low, but a red nobody sees |

## 4. Owner actions that are not decisions

Run the deploy; save identity details in Studio (clears X20, T505); send the Upwork Support email and read the primary terms (T537); run `just upwork-lists-probe`; decide the stale 6-character message body; close T505 after the identity row exists; T535 AC3/AC6/AC7 closure; KYC provider decision (T528).

## 5. Findings and corrections from this session

- Retracted: I reported `packages/lib` `middleware.spec.ts` as unable to load (`astro:middleware`). It passes 5/5 from the workspace root; I had run vitest from the package directory.
- Corrected: C4c is not waiting on T532 (`status: done`); check its sandbox guard covers the local stack first.
- The weekly tools job used to dirty the live checkout and could write a bump its own smoke had held (semgrep, 2026-10-05). T546 fixes the path; T112 records the baseline commit and the OSV floor bump.
- OSV advisories can block any commit in any repo (`sharp`, `source-map-js`, `tinypool` this time). Supported path: raise the `pnpm.overrides` floor by hand and regenerate the lockfile only.
- `STATE.md` ticket links point into the agent tree that generated them and die when it is removed (20 today, agy's tree): [[T548]].
- Land output does not show the pre-push gate; "pushed" was the only signal. Worth a ticket if it matters again.
