---
id: AgDR-0027
title: "One platform (w0m) with one root admin, persons with a default home org (company or silent personal org), one account per person, and the operator-company gate"
timestamp: 2026-09-26T04:58:00Z
agent: claude-code
model: claude-opus-5-5
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T458
---

# AgDR-0027 — One platform, persons and their home orgs, one account per person, the operator-company gate

> **Accepted 2026-09-26** with [[AgDR-0028]] after four review rounds (Q1–Q34 answered). **Amends, does not replace:**
> [[AgDR-0019]] §2 (a person's anchor) and its `org_type` values; [[AgDR-0018]] (what the `@webomage.com` gate guards).
> Both stay `accepted` and carry a pointer here. Engagements, hats and access: [[AgDR-0028]].

## Y-statement

In the context of **T439's CP shell reaching client orgs and the owner restating the model (2026-09-25/26)**, facing
**a live schema where `w0m` is both the platform and the delivery business, persons float with no org, clients live in
a separate `clients` table, and one person has two user accounts**, we decided **that `w0m` is the one platform with one
root admin and is nobody's home; that every person has a default home org (a company, or a personal org created
silently) and a public profile separate from it; that one person is one account whose other logins are secondary
credentials; and that `webomage` is the company that operates the platform, whose members alone fill `w0m` unit slots
and must hold an `@webomage.com` email**, to achieve **one identity shape for staff, clients, leads and talent, with the
platform's staff unambiguous**, accepting **a data migration that moves all delivery from `w0m` to `webomage`, a
personal org for every person without a company, and the retirement of `public.clients` that AgDR-0019 decided but
never ran**.

## Context — measured 2026-09-25 (read-only, live)

- `public.orgs`: 11 rows. `w0m` (`host`, units `admin, delivery, system, talent`, 8 active delivery hats) and 10
  `client` orgs, one of them `webomage` (1 unit, 0 hats). CHECK allows `host | client | partner | vendor`. Three slugs end
  in `-` (`artemio-quiero-comer-`, `kayse-renowned-marketing-llc-`, `inovus-investments-inc-`), which Backstage rejects.
- All 7 projects and all 98 contracts have `host_org_id = w0m`.
- 28 auth users: 12 on `@webomage.com` (Aleksei, Elena, `w0m@`, a client of artemio, fixtures), 7 `test.com`,
  5 `example.com`, 2 `gmail.com`, 2 `demo.webomage.com`. 24 profiles have no org unit; 4 (`test.com` fixtures) sit on
  `w0m.system`. Signup (`handle_new_user`) creates a profile and no org.
- `public.clients` still exists; its 10 rows were copied once into `orgs` (same ids, migration `20260914140000`); 7
  foreign keys still point at it; both create paths (admin `ClientManager`, `lead-api` on proposal accept) write
  `clients` only.
- `casualuser@gmail.com` is a separate auth user sharing Aleksei's profile through `account_profiles` (T440).
- Verification (T346, T349) lives on `public.clients` and `gamification.compliance_profiles`, not on orgs or persons.

## Decision

1. **`w0m` is the one platform** (org kind `platform`, exactly one row), nobody's home. Its units are the platform's own
   functions: `w0m.admin`, `w0m.system`, `w0m.talent` (slots `w0m.talent.recruiting`, `w0m.talent.trainer`). Delivery is
   not a platform function and leaves `w0m`. The **talent network** belongs to the platform.
2. **`w0m@webomage.com` is the platform root and the only admin.** It belongs to no org and may wear any hat. The
   `w0m.admin` slot stays empty (the T362 split between the institutional admin and Aleksei's person). Machine actors
   stay the service role ([[AgDR-0015]]).
3. **Org kinds are `platform | company | personal`.** Contractor and client are sides of an engagement ([[AgDR-0028]]),
   not kinds; `host | client | partner | vendor` retire. Slugs follow Backstage's name rule (end alphanumeric); the three
   slugs ending in `-` are renamed.
4. **Persons and their orgs.**
   - A person's **public profile** (the Backstage `User`) is the person: theirs to publish in the network or not.
   - Every person has a **default home org**: the company they belong to, or, if none, a **personal org** created
     silently at registration (slug from their name, collision suffix `-2`, renamable).
   - Their **default hat** is membership of the home org's `team` unit; every org gets a `team` unit (existing
     `engineering` units are renamed).
   - A personal org **converts to a company in place**; nothing is copied.
   - A personal org that is a party to any engagement is **kept**, so completed engagements keep their parties; a person
     may therefore keep their personal org alongside their company. Merging a personal org into a company is research,
     [[T459]].
   - Membership in another org comes through its unit slots or engagement hats.
5. **Claiming a company page.** The claimant keeps their personal profile, holds `<company>.owner` (the main-person
   slot) and joins `<company>.team`.
6. **One person, one account.** Other logins (another email, an OAuth identity) are **secondary credentials** linked to
   the primary account, never second users. `casualuser@gmail.com` becomes a secondary credential of
   `aleksei@webomage.com`: the owner deletes the `casualuser` auth user, then links its Google identity to `aleksei@`;
   `ADMIN_EMAIL` (Gauge) moves to a non-real test admin. Email rules read the primary email. A person's Backstage `User`
   name is their handle (`aleksei`), never the email.
7. **`webomage` is the operator company** (Aleksei its main person, Elena a member).
   - Membership requires a primary email on `@webomage.com`.
   - `w0m` unit slots are granted only to holders of the `webomage.team` default hat.
   - The domain is **necessary, not sufficient**: an `@webomage.com` account is a client, a fixture or a stranger until
     it is made a member (`eva@webomage.com` is a client of artemio).
   - Finance and growth are the operator's own slots: `webomage.fin.principal`, `webomage.growth.lead`.
   - **What a slot is (owner, 2026-09-26, reading A):** an office held through a hat on an org's unit, displayed
     `<org>.<unit>.<role>`. `webomage.fin.principal` is the `fin` unit of `webomage` plus the `fin.principal` office;
     `<company>.owner` is the `owner` office held on the company's `team` unit. Units carry the org chart, offices the
     capabilities; no separate slot table.
8. **Layers.** Each is its own scope; a higher one never implies a lower one.

   | Layer | Holds | Examples |
   |---|---|---|
   | L0 identity | credential → account → person (profile) | `aleksei@` + secondary `casualuser@` |
   | L1 platform | root admin; `w0m` unit slots; talent tier (data, grants nothing) | `w0m@`; `w0m.talent.recruiting`; tier `trainee` |
   | L2 organisation | home org, its units, the default hat ([[AgDR-0011]]) | `webomage.team`, `webomage.fin.principal` |
   | L3 engagement | engagements and their hats ([[AgDR-0028]]) | `webomage.eg-<id>.acme.pm` |

   Vocabulary: **org member** (L2), **talent** (a person in the network, with a tier: applicant, trial, trainee, active,
   senior), **hat wearer** (L3; any registered person).
9. **The public directory** (verified people and orgs, claims, portfolios) is a separate decision, with T439's three split
   tickets; verification moves from `public.clients` onto orgs and persons.
10. **`public.clients` retires into `orgs`** ([[AgDR-0019]] §3): business fields (verification, KYC, Stripe) move to a
    company-details record keyed by org; `client_users` becomes client-side hats; the 7 foreign keys move. Until then,
    every path that creates a client creates its org in the same transaction, and a check fails on any client without an
    org.
11. **Fixtures before homes.** Test and demo accounts are deleted (owner-confirmed batches) after the four non-real test
    accounts of T439 AC10 exist and before personal orgs are created, so no junk orgs are made.

## Consequences

- AgDR-0019 §2's home example (`w0m.talent.recruits`) becomes an L1 talent tier; homes are companies and personal orgs.
- AgDR-0018's blocking precondition disappears: the domain grants nothing by itself.
- Delivery data moves from `w0m` to `webomage`; T439's staff pages follow (`/o/w0m/…` → `/o/webomage/…`); `/admin`
  stays the platform console, for the root.

## Backstage alignment ([[AgDR-0026]])

Orgs, units and slots are `Group`s (`spec.type` = org kind, or `unit`/`slot`, parented by their org); persons are
`User`s with `spec.profile.email` = the primary email and `spec.memberOf` listing their groups (the `team` membership is
the default hat); secondary credentials stay out of the catalog, as Backstage's sign-in resolvers do. Validated with
`@backstage/catalog-model` 1.10.1; details in [[AgDR-0028]] §Backstage alignment.

## Migration

Ordered, owner-applied, each step verified read-only: OpenSpec change `2026-09-25-org-engagement-model`,
`design.md` §Migration.
