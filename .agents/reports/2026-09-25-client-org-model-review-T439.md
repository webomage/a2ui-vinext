# Client / org / contractor model — review against the record (T439, T356, T354, AgDR-0019)

**Date:** 2026-09-25 · **Trigger:** owner direction during T439 C4 planning · **Tickets:** [[T439]] [[T356]] [[T354]] [[T117]]
**Method:** read AgDR-0019, `RBAC-PROJECT-ROLES-PIVOT.md` §6–§9, T354/T356/T117 tickets, the client-conversion and
org-federation OpenSpec changes, the owner's own chat messages (Claude transcripts + Antigravity plans); measured the
live schema read-only (`authz_probe`, `begin read only … rollback`).

## 1. The model as stated by the owner (2026-09-25)

1. Everyone is the same shape: **user → profile**, whether a w0m member, a lead, or a client person.
2. Every profile sits under an **org**. A solo client or a lead gets a **virtual org named after them**, by default.
3. A virtual org can be **converted to a real company**: company data, several users under it.
4. Users of any org work under the **same hats / offices RBAC**.
5. **Client ↔ contractor is a relation between two orgs, created by a project/contract.** Only w0m is a contractor
   for now; all other orgs (existing, and those imported from Aleksei's history) are clients with projects.
6. **Client and contractor may be the same org.** On the w0m project, Webomage is both; Aleksei holds contractor
   hats and client hats.

## 2. What the record already decided — agreement

| Owner point | Already recorded | Where |
|---|---|---|
| 2 (everyone under an org) | "No standalone profiles … every human and machine user attached to `<org>.<unit>`" | AgDR-0019 §2; pivot §9.1.3 (`profiles.org_unit_id`) |
| 5 (client = org, relation via project) | "A client is simply an Org … relationship established when w0m and the client Org are joined on a Project" (`host_org_id`, `client_org_id`) | AgDR-0019 §3; pivot §9.1.4 |
| 4 (same hats RBAC) | "offices define canonical bundles (`tech.lead`, `project.manager` …); an org hat is an office instantiated on an Org/Project" | AgDR-0019 §4 |
| 6 (both sides) | Owner quote: *"w0m eco system is project by Aleksei as Client and Contractor all hats now"* | T356 summary + AC5; pivot §9.2 |
| b2b between any orgs | *"architect this whole to be applied to any company/client/org … full b2b connections and even persons/roles in different companies interact the same unified way"* (owner, 2026-09-13) | origin of T354 / AgDR-0019 |

**Not recorded anywhere:** points 2's *virtual/personal org for a solo person*, 3 (*virtual → real conversion*), and 6
as a **project whose client org equals its contractor org** — §9.2 modelled "both" only as extra hats inside w0m.
T354's `actor_manifest` (design only, not built) gives a person its own actor kind (`owner_kind IN ('profile','client','org')`);
the owner's model makes that unnecessary — **everything is an org**, a person is a member of a (possibly personal) org.

## 3. What is live vs designed — measured 2026-09-25

**Built:** `orgs`, `org_units`, `unit_edges`, `worn_hats`, `profiles.org_unit_id`, `hats.org_id`,
`projects.host_org_id` + `projects.client_org_id`, `contracts.host_org_id`.

**Not built / half-done — each a conflict with the model:**

1. **`clients` was never retired.** AgDR-0019 said "`public.clients` and `client_users` must be migrated into `orgs`
   and `org_members`". Live: `org_members` does not exist; `client_users` is still the membership table; **7 foreign
   keys still point at `clients`** (`client_users`, `contracts.client_id`, `invoices`, `leads`, `projects.client_id`,
   `project_vaults`, `synced_vacancies`). The 10 client `orgs` rows exist only because migration `20260914140000`
   (step 7) **copied** them once, with the same ids.
2. **Live gap:** both code paths that create a client write **only** `clients` — the admin UI
   (`ClientManager.svelte:158`) and lead conversion (`lead-api/handler.ts`, on proposal acceptance). No trigger or FK
   ties them. The next client created has no org, so it cannot be opened in the new CP shell (`/o/<slug>`). Affected
   today: 0 (no client created since the backfill).
3. **Duplicate columns:** `projects` carries both `client_id` (→ clients) and `client_org_id` (→ orgs); 7/7 equal.
   The contract side has no client org column at all (`contracts.client_id` → clients).
4. **Offices are w0m-namespaced**, not canonical: `w0m.tech.lead`, `w0m.client.principal`, `w0m.delivery.manager`…
   plus one generic `client.member`. Contradicts point 4 and AgDR-0019 §4: a client company with its own tech lead
   has no office to hold.
5. **The same company exists twice:** `w0m` (host, 8 hats, 4 units) and `webomage` (client org + `clients` row, 0 hats).
   Point 6 needs **one** org that is both.
6. **§9.2 not realised:** Aleksei holds 5 `w0m.tech.*` hats (+1 with a null office); no client-side hat.
7. **`orgs.org_type` is single-valued** (`host` | `client` | …). Under the model an org is contractor or client **per
   project**, and can be both. T439 C3's host-only gate keys on `org_type = 'host'`, and my C4 draft (D1, "render by
   org type") would have hard-coded the wrong assumption.

**Allowed already:** no CHECK forbids `client_org_id = host_org_id`, so same-org projects are valid at schema level.

## 4. Impact on T439 (the CP shell)

- **C3 host-only gate (shipped):** correct for now (w0m is the only contractor), but should key on "this org is the
  contractor on a project" rather than `org_type`. Record, change when a second contractor exists.
- **C4 D1 must change:** not "render by org type" but **by side**: an org shows contractor sections if it is contractor
  on any project and client sections if it is client on any project; a project page shows the side the person's hats
  give them. w0m shows both.
- **C4 D2 (scope to the URL org) stands.**
- **Order:** C4a reads client data through `client_id → clients`; completing clients → orgs (below) first avoids
  building the client pages on the table that is being retired.

## 5. Recommendations, weighted

| # | Recommendation | Cost | Risk | Unblocks |
|---|---|---|---|---|
| R1 | **New AgDR** recording the model (points 1–6), superseding AgDR-0019 §3 wording, pivot §9.2, and T354's three owner kinds; `org_type` retired in favour of per-project side | small (doc) | none | everything below |
| R2 | **Stopgap now:** both create paths (admin UI, lead-api) create the `orgs` row in the same transaction, + a check that fails on any `clients` row without an org | small | low | closes the live gap before any new client |
| R3 | **Finish clients → orgs** (new ticket, P1): `orgs` is the one record; billing/KYC/Stripe fields move to an org extension keyed by `org_id`; `client_users` → hats with client offices; repoint the 7 FKs; drop `projects.client_id`; add `contracts.client_org_id` | large (migration, owner applies) | moderate — small data (10 orgs, 2 client users) | C4 client pages on the final model |
| R4 | **Personal org by default** (new ticket, blocked by R3): signup and lead conversion create an org named after the person (a `personal` flag, slug from name) and a membership hat; "convert to company" edits that org and adds members | medium | low | point 2/3; the imported history clients |
| R5 | **Merge `webomage` into `w0m`**; the w0m ecosystem project gets `host = client = w0m`; Aleksei gets a client-side hat | small migration | low (0 hats on `webomage`) | point 6 |
| R6 | **De-namespace offices** (`tech.lead`, `client.principal`, …) so any org instantiates them; hats stay per org | medium | low for UI (nav reads capabilities, not offices) | point 4 for client companies |

**Suggested sequence:** R1 → R2 → C4 re-planned on "side, not type" → R5 → R3 → R4 → R6. R2 and R5 are small enough
to run inside C4; R3, R4, R6 are their own tickets (split from T439 per the owner's split rule).

---

## 6. Revision 2 — owner corrections (2026-09-25, same day)

**Owner:** existing AgDRs are correct and are to be used. **`w0m` = the platform and the admin scope. `webomage` = the
org of aleksei@webomage.com, which is both client and contractor.** A registered user who does not create an org still
gets one, silently: the minimum solo-person org.

### 6.1 The picture under these corrections

| Entity | Is | Today (measured) | Target |
|---|---|---|---|
| `w0m` org | platform operator: admin, system, (talent?) | `host`, units `admin,delivery,system,talent`, 8 delivery hats | platform only; delivery leaves |
| `webomage` org | Aleksei's company; contractor on every project today, and its own client | `client`, 1 unit, 0 hats, has a `clients` row | contractor + client; holds the delivery hats |
| projects (7) | contractor org ↔ client org | all `host_org_id = w0m` | `host_org_id = webomage`; the w0m ecosystem project `host = client = webomage` |
| contracts (98) | Aleksei's Upwork history | all `host_org_id = w0m`; client linked for 4, free-text for 94 (78 distinct names) | host `webomage`; each client an org |
| people (28 users) | each under an org | 24 profiles with no org unit, 4 on `w0m.system` | everyone has at least a personal org |
| signup | creates the person | `handle_new_user` trigger creates the profile, no org | also creates the solo org |

### 6.2 Where the accepted AgDRs disagree with each other or with the corrections

- **AgDR-0019 supersedes 0013, 0014, 0017** (its frontmatter), but those three still read `accepted` with no
  `superseded_by`. And 0019 does not restate 0014's rule, so whether **hat resolution is exclusive** (only the worn
  hat counts) is formally undecided.
- **AgDR-0020 office keys are `<realm>.<area>.<role>` with realm = org** (`w0m.tech.lead`, `<client>.tech.lead`), so
  the delivery offices named `w0m.tech.*` would become `webomage.tech.*`, and each org gets its own office rows.
- **AgDR-0015 realms are `system.* / w0m.* / client.*`.** A `client.*` realm (live: office `client.member`) contradicts
  "a client is just an org" (0019 §3) and per-org realms (0020).
- **AgDR-0019 §2 anchors a person to exactly one `<org>.<unit>`** (`profiles.org_unit_id`, examples
  `w0m.talent.recruits`). With a personal org for everyone, the anchor and the talent-network membership compete.
- **AgDR-0018: the `@webomage.com` email gate** guards admin. `webomage.com` is now a customer org's domain, while the
  platform is `w0m`.
- **T439 C3 shipped on the old reading:** staff pages live at `/o/w0m/…`, the host-only gate keys on `org_type = 'host'`,
  and migration `20260925210000` shows admins every host org as "Platform admin".
