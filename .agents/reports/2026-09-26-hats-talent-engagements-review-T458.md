# Hats, talent and engagements — access boundaries review, round 4 (T458)

**Date:** 2026-09-26 · **Ticket:** [[T458]] · **Follows:** `2026-09-26-backstage-model-review-T458.md`
**Owner input:** designer collapses into PM; PM ≈ the frontend scope, TL ≈ backend + DevOps; both extensible with
decollapsed hats (QA for example); PM/TL as a complementary pair; abilities tied to real actions on services, data,
code and infra. Talent (trainee/applicant) is separate from engagement hats; any registered person can be a trainer
or a trainee; access must be strict RBAC. Straighten terminology across all data (org ids via engagements?). A
person who claims a company keeps their personal profile.

## 1. PM and TL — the two halves

| | **PM — the surface** | **TL — the system** |
|---|---|---|
| owns | what the client sees and accepts: frontend, design, acceptance, milestones, client communication | what runs underneath: backend, data model, infrastructure, deploys, security |
| collapses in | `qa`, `design`, `frontend-dev` | `devops`, `backend-dev` |
| **code** | `repo.read`, `repo.write` (new), `test.run` | `repo.read`, `repo.write` (new), `repo.manage` (branch protection, collaborators), `test.run` |
| **infra** | none | `infra.manage`, `deploy.approve`, `deploy.execute` (through `devops`), `secret.use.prod` (new) |
| **services** | preview environments, client message rooms | connectors and integrations (`service.connect`, new) |
| **data** | `project.view/manage`, `milestone.approve`, `proposal.view`, `contract.view`, `client.view`, `quality.gate` and `bug.report` (through `qa`), `design.view/manage` (through `design`) | `project.view/manage`, `milestone.approve` (technical sign-off), `resume.view` (staffing) |
| no access | infra, secrets | commercial amounts (`contract.view`, `invoice.*`), per [[AgDR-0020]] (tech seats see no money) |

**Measured gaps in the live catalogue (44 capabilities):** there is no `repo.write` / `pr.open` (the only write-level repo
capability is `repo.manage`, which is admin); no capability for secrets or environments; no capability for connectors.
Nine capabilities have no office (`grant.manage`, `job.outstaff.claim`, three `client.*.view`, …).

**Separation-of-duties trade-off:** `tl` approves deploys, `devops` executes them. While `devops` is collapsed into `tl`,
one person holds both. It cannot be avoided on a one-person engagement; the mitigation is that every deploy is logged
with the worn hat, and splitting `devops` out restores the separation automatically.

## 2. Talent and training access — argued from four sides

**The rule this must keep:** access has **one source**: a worn hat → its office → capabilities ([[AgDR-0019]] §4,
[[AgDR-0028]]). Today the CP also has five "intrinsic" capabilities computed in code (`self`, `hat.delivery`,
`network.member`, `context.member`, `platform.admin`); `network.member` is exactly the kind of second source the owner
is worried about.

| Option | How access is granted | For | Against | Verdict |
|---|---|---|---|---|
| **A. Tier grants capabilities** | a trainee tier grants `pipeline.learn` etc. directly | simplest | a **second permission source** beside hats; grants are platform-wide, so a trainee reaches every cohort's material, not just their own | reject |
| **B. Training is an engagement** | an engagement of kind `training`: contractor = the trainer's org (personal or company), client = the trainee's org (personal, or their employer); hats `trainer` / `trainee` | **one mechanism**; scoping comes free (a trainee sees only material attached to their engagement, a trainer only their trainees); works peer-to-peer between two personal orgs; a certification-prep contract is a contract record like any other; same Backstage shape | the "three minimum hats" rule must depend on the engagement kind; "client" is only the side's name (the served side) | **recommend** |
| **C. Programmes as a second hat container** | hats on a `programme`, not an engagement | keeps learning apart from commerce | two scoping code paths for the same thing; an engagement under another name | reject |
| **D. Talent has no access at all** | tier and certifications are profile data only | smallest | trainer review and certification tests still need scoped access, which ends up as B | subsumed by B |

**Recommended combination: A's tier kept as data only, B for every access.**
- **Talent tier** (`applicant → trial → trainee → active → senior`, [[AgDR-0017]] decision 2) is a platform (L1)
  attribute of the person: eligibility for staffing, a badge on the profile. **It grants no permission.**
- **Engagement kinds with their own minimum hats:** `delivery` (client; PM, TL) and `training` (trainee; trainer).
- **The `w0m.talent.*` slots** govern the programme itself (curriculum, cohorts, blueprints, applicant pipeline), which
  are platform surfaces; they give no access to a trainee's work, which comes only through a training engagement.
- **A person's own data** (profile, portfolio, test results, certifications) belongs to the person (the Backstage
  `User`), visible to them, public only when they publish it.
- **The intrinsic `network.member` capability retires** (it becomes "holds a talent tier", a data check for staffing
  lists, not a permission).
- Platform-run cohorts: the contractor is the org that runs training (today `webomage`, whose members hold
  `w0m.talent.trainer`); `w0m` stays out of engagements.

**Vocabulary:** "member" alone is ambiguous. Proposed: **org member** (L2, belongs to an org's unit), **talent** (L1, a
person in the network, with a tier), **applicant** / **trainee** (early tiers).

## 3. Q15 — org ids through engagements, and how Backstage draws it

The owner prefers straight terms in the data too. Then the orgs of a project or contract should come **only** from its
engagement:

- **`engagements`**: `id` (uuid), `public_id` (12-char base32), `kind` (`delivery | training`), `contractor_org_id`,
  `client_org_id`.
- **`projects`** and **`contracts`**: `engagement_id` only. `host_org_id`, `client_org_id` and `client_id` are backfilled
  into engagements, then dropped (clean cutover, [[AgDR-0025]]): one source for "who serves whom".
- **`hats`**: `engagement_id` (delivery/training work) or a unit slot (org chart), never both.

**Backstage, the same picture:** engagement = `Group` (`spec.type: engagement`, `spec.parent` = the contractor,
annotations `w0m.dev/client` and `w0m.dev/engagement-kind`); project = `System` with `spec.owner` = the engagement;
contract = `Resource` (`spec.type: contract`) with `spec.owner` = the engagement and annotation `w0m.dev/source`
(`upwork | direct | …`); hat = `Group` with `spec.parent` = the engagement. Backstage derives `ownedBy`, `childOf` and
`memberOf` from those fields itself. The client link has to be an annotation because a `Group` has one parent and core
kinds have no second group reference; a custom relation would need a catalog processor, which [[AgDR-0026]] avoids.

This reverses my earlier Q15 answer (keep `host_org_id`), following the owner's preference for one vocabulary.

## 4. Q27 — claiming a company page

Owner: the claimant keeps their personal profile, becomes the company's main person (its first unit slot), and may
publish their personal profile page in the network.

**Proposed:**
- **Profile ≠ personal org.** The profile (Backstage `User`) is the person and their public page; the personal org
  (`Group`) is only what a solo person contracts through.
- Claiming makes the person holder of `<company>.owner` (the main-person slot) and a `<company>.team` member.
- **Their personal org stays while it is a party to any engagement** (history keeps its parties, [[AgDR-0025]]: never
  rewritten), and is removed when it has none. The earlier "personal org archived" answer is withdrawn.
- This relaxes "exactly one home": a person has their companies plus, when needed, their personal org. The **default
  hat** is the first company's `team` membership, else the personal org's.

## 5. What changes in the decisions (on the owner's yes)

AgDR-0028: engagement kinds (`delivery`, `training`) with per-kind minimum hats; PM/TL table (§1); collapse rules
(`qa`, `design`, `frontend-dev` → PM; `devops`, `backend-dev` → TL); tier grants nothing; `network.member` retires;
`engagement_id` replaces org columns on projects and contracts. AgDR-0027: "one home" becomes "companies plus a personal
org while it has engagements"; claim flow; vocabulary (org member, talent). New capabilities: `repo.write`,
`secret.use.prod`, `service.connect`.
