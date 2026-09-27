# T458 S3 — account and fixture deletion batches (measured 2026-09-26, read-only, live)

**Ticket:** [[T458]] step S3 (AgDR-0027 decision 11: fixtures go after the non-real test accounts exist and before S4
creates personal orgs, so no junk orgs are made). Nothing here has been deleted; every batch waits for the owner.

**Method:** all 22 `auth.users`, each with its profile, roles, factors, sign-in providers and every row that points at
it through the 58 foreign-key columns referencing `auth.users` or `public.profiles`, plus `clients`/`leads` by email.

## Keep (not S3)

| Account | Why |
|---|---|
| `w0m@webomage.com` | platform root, only admin, 1 factor |
| `aleksei@webomage.com` | owner; 1,782 proposals, 95 contracts, 170 messages, 8 hats |
| `elena@webomage.com` | operator member; PM hat on BridgeRoad |
| `eva@webomage.com` | real client of artemio (contract, 2 milestone approvals) |
| `m.adil2018223@gmail.com` | **a real job applicant** (1 application, never signed in); a person's data, not a fixture |
| `demo-client@demo.webomage.com`, `demo-candidate@demo.webomage.com` | current demo personas (T41 tour, `seed-demo`) |
| `casualuser@gmail.com` | S5, not S3 (becomes a secondary credential of `aleksei@`); **its 92 `admin_activity_logs` rows have a NO ACTION key and block deleting the user** until reassigned to `aleksei@` |

## Batch 1 — throwaway fixtures (10): never signed in, own only their profile and a role row

| Account | Created | Owns |
|---|---|---|
| `dup@example.com` | 2026-05-07 | profile, `recruit` role |
| `noname@example.com` | 2026-05-07 | profile, `recruit` role |
| `gauge-test-1787199003951@example.com` | 2026-08-20 | profile, `recruit` role |
| `gauge-test-1787199948665@example.com` | 2026-08-20 | profile, `recruit` role |
| `gauge-test-1788793901770@example.com` | 2026-09-07 | profile, `recruit` role |
| `gauge@test.com` | 2026-05-12 | profile |
| `test_create@webomage.com` | 2026-06-23 | profile |
| `test_role_client_1783562701322@webomage.com` | 2026-07-09 | profile |
| `test_role_client_1783618987803@webomage.com` | 2026-07-09 | profile |
| `test_role_client_1788794515203@webomage.com` | 2026-09-07 | profile |

Order per account: `user_roles` row (its key is NO ACTION and blocks the user delete) → `profiles` row (its key is SET
NULL, so deleting only the user would leave an orphan profile) → the auth user through the Auth Admin API (takes
identities, sessions, factors). Risk: none found. **Root cause to fix alongside:** Gauge specs create timestamped
`gauge-test-*` / `test_role_client_*` accounts on the live database and never remove them; they will come back.

## Batch 2 — `merge-test-client` (org + client row)

Created 2026-07-06; 0 projects, 0 contracts, 0 invoices, 0 leads, 0 users, 0 hats; 2 `synced_vacancies` rows (they
cascade). Delete the client row, then the org (its `team` unit cascades).

## Batch 3 — legacy demo personas (2), blocked on a `seed-demo` fix

| Account | Owns |
|---|---|
| `demo-client@webomage.com` | the `demo` client's only `client_users` link, `clients.email` of `demo`, 1 hat, `client` role, 1 lead by email |
| `demo-candidate@webomage.com` | 1 job application, `recruit` role |

The legacy client account still owns the demo client, which is why the demo persona `demo-client@demo.webomage.com`
reaches nothing (found earlier today). `just seed-demo` would normally move it, but **since S0 it would break the demo**:
both old and new accounts exist, so its one-time rename does not fire; it deletes the `demo` client row but not the
`demo` org (nothing links them), and the reseed then gets a new org `demo-2` from the S0 trigger. Fix `seed-demo`
first (reuse the existing `demo` org id for the new client row, or move the link in place), then reseed, then delete
these two.

## Batch 4 — accounts tests depend on (2), after the test accounts exist

| Account | Signed in | Used by |
|---|---|---|
| `legioner@webomage.com` | 2026-09-08 | default `TEST_USER_EMAIL` in `tests/steps/login-redirect.steps.ts` and `tests/helpers/auth.ts` |
| `jane@webomage.com` | never (2026-03-11) | candidate details in `specs/web/admin_interviews.spec` |

Repoint those specs to the new non-real test accounts, then delete.

## The four non-real test accounts (T439 AC10), to create first

One per context: **Me** (member), **contractor org** member (`webomage` staff view), **client org** member, **admin**.

## Open questions (weighted)

| # | Question | Recommendation | Weight |
|---|---|---|---|
| Q1 | A test **admin** contradicts AgDR-0027 decision 2 and T463 (root is the only admin). How are admin screens tested? | No second admin. Admin goldens run as `w0m@` in an owner-attended session, or admin pages are covered by component tests; the other three accounts are automated. | Keeps "one admin" true; costs automation of admin goldens |
| Q2 | Test account emails | `e2e-member@`, `e2e-contractor@`, `e2e-client@` on a subdomain we control (e.g. `test.webomage.com`), never `@webomage.com` (the operator gate) and never a real inbox | Clear fixtures; magic-link flows need a catch-all mailbox on that subdomain |
| Q3 | Demo personas in S4 | They join the `demo` company as members; no personal orgs | Keeps demo data out of the personal-org count |
| Q4 | `m.adil2018223@gmail.com` | Keep; S4 gives a personal org like any applicant | Deleting a real applicant's data is a privacy decision, not cleanup |
| Q5 | How deletion runs | A `just s3-delete --batch N` recipe: dry run by default (prints every row it would remove), `--apply` behind the Touch ID confirm gate, owner-run only | One reviewed path instead of hand SQL; audit trail in the deploy log |
