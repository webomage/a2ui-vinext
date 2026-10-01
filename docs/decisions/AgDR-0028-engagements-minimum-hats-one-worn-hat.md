---
id: AgDR-0028
title: "Engagements <contractor>.<engagement>.<client>: the only link between orgs, two kinds with minimum hats, collapse, one worn hat"
timestamp: 2026-09-26T05:10:00Z
agent: claude-code
model: claude-opus-5-5
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T458
---

# AgDR-0028 — Engagements: the only link between orgs, minimum hats, collapse, one worn hat

> **Amended by [[AgDR-0029]] (proposed 2026-09-27):** an Upwork contract is a source record in the Upwork layer that the
> engagement links to, not a row of our `contracts`.
>
> **Accepted 2026-09-26** after four review rounds with the owner (Q1–Q34 answered, table at the end; reviews in
> `.agents/reports/2026-09-25-client-org-model-review-T439.md`, `2026-09-26-backstage-model-review-T458.md`,
> `2026-09-26-hats-talent-engagements-review-T458.md`). **Restates [[AgDR-0014]]** (one worn hat; the root may wear any
> hat). **Amends, does not replace:** [[AgDR-0020]] decision 3 (offices become a generic catalogue; unit slots keep
> `<org>.<area>.<role>`), [[AgDR-0015]] (the `client.*` realm retires), [[AgDR-0017]] decision 4 (client is a side, not
> a class). Companion: [[AgDR-0027]] (platform, orgs, persons, operator gate). Catalog shape: [[AgDR-0026]].

## Y-statement

In the context of **the owner defining how orgs work together (2026-09-25/26)**, facing **hats keyed to one host org and
one project, client access through a separate `client_users` table and a `client.*` realm, org columns duplicated on
projects and contracts, a w0m-namespaced office list, and trainee access granted by an account class**, we decided
**that an engagement is the only link between two orgs, directed from contractor to client and addressed
`<contractor>.<engagement>.<client>`; that engagements come in two kinds, delivery (minimum hats `client`, `pm`, `tl`) and
training (`trainee`, `trainer`), into whose main hats every other role collapses until staffed; that a person wears one
hat at a time and any registered person can be a hat wearer; and that access comes only from the worn hat's offices**,
to achieve **one mechanism for serving, being served, delivering and training, with who-serves-whom readable from the
address and every permission traceable to one hat**, accepting **a new `engagements` table that replaces the org columns
on projects and contracts, the retirement of the w0m-realm offices and of the CP's account-class switcher, three new
capabilities, and a backfill of the historical Upwork contracts into engagements**.

## Context — measured 2026-09-25/26

- Hats (`public.hats`) are keyed by `org_id` + `project_id`; 8 active, all Aleksei's, all on `w0m`, offices `w0m.tech.*`.
- Collapse exists for projects: the `project-roles` spec "Fallback Hat Provisioning Unstaffed Roles" provisions an
  `is_fallback` hat (QA → PM, DevOps → Tech Lead) by trigger, keyed `(project_id, role_slug)` ([[T347]]).
- Offices (14): `client.member`, `w0m.client.principal`, `w0m.delivery.manager` (9 capabilities), `w0m.design.lead`,
  `w0m.fin.principal`, `w0m.growth.lead`, `w0m.quality.owner`, `w0m.talent.{recruiting,trainer}`,
  `w0m.tech.{dev,lead,ops,program,qa}`; `pm` maps to `w0m.tech.program` (5). 44 capabilities; no `repo.write`, nothing
  for secrets or connectors. Row security reads capabilities in 5 of 334 policies.
- Contracts: 98 (Upwork history), 3 linked to a project; 4 of 7 projects have no contract; clients of 94 contracts are
  free text (78 names). Projects and contracts carry `host_org_id` (all `w0m`), projects also `client_org_id` and
  `client_id` (7/7 equal).
- The CP switches an account class ("hat" `admin/manager/member/client/recruit`, `sb-active-role`); T439 computes five
  intrinsic capabilities in code, among them `network.member`.
- PostgreSQL 17.6: no native `uuidv7()`; keys are `gen_random_uuid()`.

## Decision

1. **Engagement — the only link between two orgs.** An engagement is directed: the **contractor** serves, the
   **client** is served; both may be the same org. Orgs connect to each other through engagements only:
   `engagements (contractor_org_id, client_org_id)`. A **contract** is a commercial record from a source (Upwork,
   direct, another platform) belonging to one engagement; a **project** is a delivery workspace belonging to one
   engagement; both carry `engagement_id` and no org columns. Today `webomage` is the only contractor; every other org
   is a client. Historical Upwork contracts import as one engagement each, except that a contract already linked to a
   project joins that project's engagement (a contract and its project can never sit in different engagements); the owner
   reviews which contract-less projects match which historical contracts.
2. **Identifier.** The row key is a UUID, Backstage's `metadata.uid`. The public id is 12 characters of lowercase
   Crockford base32 (60 random bits, unique index; or an explicit semantic slug). Following owner decision (2026-09-27),
   the `eg-` prefix is dropped: the catalog name and public id are used as-is without prefix (`<id>`), and `metadata.title`
   reads `contractor → client`. The **address** `<contractor>.<engagement>.<client>` (e.g. `webomage.7k3m9x2qfahd.acme` or
   `webomage.platform.webomage`) is how docs, logs and the UI name it.
3. **Two kinds, each with its minimum hats**, present even when vacant and even when one person holds them all:
   - **delivery:** `client` (client side); `pm` and `tl` (contractor side);
   - **training:** `trainee` (client side); `trainer` (contractor side). One engagement per trainee; a group training
     across several personal orgs is research, [[T460]].
4. **Hats.** Address `<contractor>.<engagement>.<client>.<role>`. Role codes: `client`, `pm`, `tl`, `qa`, `devops`,
   `dev`, `design`, `trainer`, `trainee`. Each resolves to an office; offices form one generic catalogue (`w0m.` prefix
   dropped); `pm` is backed by `delivery.manager`. A role may have several holders (three `dev` hats on one engagement is
   fine) and one person may hold several hats.
5. **Collapse.** `qa`, `design` and program management collapse into `pm`; `dev` and `devops` collapse into
   `tl`; every other client-side role collapses into `client`. The `is_fallback` mechanism moves from project to
   engagement and gains the client side. A main hat's own office is never reduced by collapse or split; a vacant
   role's capabilities reach the main holder through a fallback hat, removed when the role is staffed (Q5, settled
   2026-09-26 after the subset rule failed on the live catalogue). Either main hat can be extended
   with split-out hats; a vacated hat returns to its collapse target.
6. **Who may hold a hat.** Any registered person is a potential hat wearer in any engagement. The `client` main hat
   goes to members of the client org; `pm` and `tl` to members of the contractor org; non-manager hats (`dev`,
   `devops`, `qa`, `design`, …) to the PM or TL holder, an operator (`webomage`) member, a network member, or a member of
   the client org or client team; `trainer` and `trainee` to any registered person.
7. **One worn hat** (restates [[AgDR-0014]]). A person wears one hat at a time, chosen in the CP switcher from the hats of
   their assigned engagements; only the worn hat's capabilities apply. `admin` means only the platform root, which may
   wear any hat. The account-class switcher (`sb-active-role`, JWT `wom_active_role`) retires: in the CP here, in
   web/join/job with [[T453]].
8. **Access has one source:** the worn hat's offices and their capabilities, plus unit slots for platform and org
   surfaces ([[AgDR-0027]]). A **talent tier grants nothing**; the intrinsic `network.member` capability retires. The two
   delivery halves are defined by real actions:

   | | `pm` — what the client sees and accepts | `tl` — what runs underneath |
   |---|---|---|
   | code | `repo.read`, `repo.write`, `test.run` | `repo.read`, `repo.write`, `repo.manage`, `test.run` |
   | infra | none | `infra.manage`, `deploy.approve`, `deploy.execute` (via `devops`), `secret.use.prod` |
   | services | preview environments, client rooms | `service.connect` |
   | data | `project.view/manage`, `milestone.approve`, `proposal.view`, `contract.view`, `client.view`; `quality.gate`, `bug.report` (via `qa`); `design.view/manage` (via `design`) | `project.view/manage`, `milestone.approve`, `resume.view`; no commercial amounts ([[AgDR-0020]]) |

   New capabilities: `repo.write`, `secret.use.prod`, `service.connect`. While `devops` is collapsed into `tl`, one
   person both approves and executes deploys; every deploy records the worn hat, and splitting `devops` out restores the
   separation.
9. **No `client.*` realm and no alias.** The client side is always named by the full address.
10. **Naming against [[AgDR-0020]]:** unit slots keep `<org>.<area>.<role>` (`w0m.talent.recruiting`,
    `webomage.fin.principal`, `webomage.growth.lead`); the w0m-realm delivery offices and `client.member` retire into
    the generic catalogue and engagement roles.
11. **Worked example.** `webomage.<id>.webomage` (or `webomage.platform.webomage`), the w0m platform project: Aleksei holds `client`, `pm` and `tl`
    (and through collapse `qa`, `design`, `dev`, `devops`) and wears one at a time.
12. **Hat management (owner, 2026-09-26; OpenSpec change `2026-09-26-hat-management`, [[T461]]).**
    - The root assigns any hat in any engagement to any registered person.
    - An engagement's `pm` holder assigns hats in it, including `tl` and the hats under it (`dev`, `devops`), and may
      assign a hat to themselves.
    - Custom hats and mixes are composed in the CP from the office catalogue; hat **collections** (a named set of hats
      plus fallback rules) are chosen when a project is created.
    - A collection's rule decides what staffing a collapsed role does; the default revokes the main holder's fallback
      (the `pm` who takes the `dev` hat retracts the `tl`'s `dev` fallback). Keeping a fallback is refused for `devops`
      (decision 8).
    - New capability `engagement.staff` (assign and compose hats in one engagement), held by `pm`.

## Settled in the final review (2026-09-26) — decision 5's subset rule

Measured on the live catalogue, no collapse pair satisfied the subset rule first recorded for Q5: `qa`, program
management and `dev` hold `repo.read` and `test.run` that the main offices lack; `design` holds `design.*` and
`blueprint.publish`; `devops` holds `deploy.execute` and `infra.manage`. The rule also contradicted decision 8 and the
built `is_fallback` trigger. The owner accepted the replacement reading (decision 5): main offices unchanged, fallback
hats add and retract a vacant role's capabilities. No office changes and no subset check.

## Backstage alignment ([[AgDR-0026]]) — `@backstage/catalog-model` 1.10.1

| This model | Backstage entity |
|---|---|
| engagement | `Group`, `spec.type: engagement`, `metadata.name: <id>`, `spec.parent` = the contractor org; annotations `w0m.dev/client`, `w0m.dev/engagement-kind` (`delivery` / `training`) |
| hat | `Group`, `spec.type: hat`, `spec.parent` = the engagement, `spec.members` = holders; annotations `w0m.dev/office`, `w0m.dev/fallback-of` |
| contract | `Resource`, `spec.type: contract`, `spec.owner` = the engagement; annotation `w0m.dev/source` |
| project | `System`, `spec.type: project`, `spec.owner` = the engagement |
| worn hat, permissions | not catalog data (Backstage keeps permissions in policy code, not entities) |

Checked with the package's own kind validators and entity policies: 20/20 model entities valid; 6/6 red probes
rejected (a slug ending in `-`, a 78-character name, a `Group` without `children`, a `User` without `memberOf`, a `User`
named by an email, a `Group` with two parents). Two consequences: the client is an annotation (a `Group` has one
parent); bare `<id>` names (12-char base32 or slug) easily satisfy the 63-character cap without prefix overhead.

## Answered questions (owner, 2026-09-26, 2026-09-27)

| # | Answer |
|---|---|
| Q1 | UUID row key as in Backstage (`metadata.uid`); public id / catalog name `<12-char base32>` or slug as-is without `eg-` prefix (owner decision 2026-09-27); address as notation (decision 2) |
| Q2 | "engagement" for the link; contract = source record; project = workspace |
| Q3 | short role codes; generic office catalogue |
| Q4, Q28 | `qa`, `design`, program manager → `pm`; `dev` (one role, no frontend/backend split), `devops` → `tl` |
| Q5 | main office never reduced; a vacant role reaches the main holder through a retractable fallback hat (the subset rule first recorded failed on live data) |
| Q6, Q33 | holders per decision 6; several holders per role; several hats per person |
| Q7 | alias dropped |
| Q8 | talent falls into the hats schema via training engagements; any registered person can wear hats; `admin` = root only; CP switcher lists assigned engagement hats; class switcher retires |
| Q15, Q31 | orgs connect only through engagements; `engagement_id` replaces org columns |
| Q17 | not needed (bare `<id>` names) |
| Q18 | engagement = `Group` parented by the contractor, client annotated |
| Q20 | hat address `<contractor>.<engagement>.<client>.<role>` |
| Q24 | `pm` backed by `delivery.manager` |
| Q29 | add `repo.write`, `secret.use.prod`, `service.connect` |
| Q30 | training through engagements; tier grants nothing; group training → [[T460]] |
| Q34 | neutral names `pm`, `tl` |

Persons, orgs, homes, claims, fixtures, slugs and slots (Q9–Q14, Q16, Q19, Q21–Q23, Q25–Q27, Q32): [[AgDR-0027]].

## Consequences

- `/o/<org>` shows contractor sections when the org is a contractor on any engagement, client sections when it is a
  client on any; `webomage` shows both. T439 C3's host-only gate is replaced by this rule.
- Every engagement keeps its minimum hats. The 98 historical Upwork contracts become engagements (the 3 linked to a
  project share its engagement; the 4 contract-less projects are matched to history by owner review), with vacant client
  hats where the client has no users, and Aleksei on the contractor side.
- The admin console follows the platform root, not a worn class.

## What this does NOT decide

Billing and subscription tiers; cross-org trust federation ([[T354]]); the public directory (its own decision,
[[AgDR-0027]] decision 9); the decorative guild theme ([[AgDR-0020]], [[AgDR-0022]]).
