# Org / engagement model — Backstage-anchored review, round 3 (T458)

**Date:** 2026-09-26 · **Ticket:** [[T458]] · **Decisions under review:** [[AgDR-0027]], [[AgDR-0028]] (both `proposed`)
**Reference:** `@backstage/catalog-model` 1.10.1: its JSON Schemas, kind validators and entity policies ([[AgDR-0026]]).
Every Backstage claim below was run, not recalled. Live figures: read-only queries, 2026-09-26.

## 1. Q1 — the identifier in `<contractor>.<id>.<client>`

**Backstage's own pattern:** an entity has a machine id (`metadata.uid`, a UUID the catalog assigns) and a
human-readable `metadata.name` (at most 63 characters, `[a-zA-Z0-9]` groups separated by `-`, `_` or `.`), unique per
kind and namespace, plus an optional free-text `metadata.title` for display. We mirror that split.

**Measured: 20,000 of each format, validated as Backstage names, and embedded in the worst live key**
(`webomage.<id>.kayse-renowned-marketing-llc.devops`, limit 63):

| Format | Length | Valid name (of 20k) | Worst key fits 63 | Lowercase | Time-ordered |
|---|---|---|---|---|---|
| UUID v4 / v7 | 36 | 20000 | no (81) | yes | v7 only |
| ULID (upper / lower) | 26 | 20000 | no (71) | lower only | yes |
| TypeID (`ct_…`) | 29 | 20000 | no (74) | yes | yes |
| KSUID | 27 | 20000 | no (72) | no | yes |
| NanoID default | 21 | **18778** (6% invalid: `-`/`_` at ends or doubled) | no (66) | no | no |
| CUID2 default | 24 | 20000 | no (69) | yes | no |
| CUID2 length 10 | 10 | 20000 | yes (55) | yes | no |
| NanoID, Crockford base32, 10 | 10 | 20000 | yes (55) | yes | no |
| NanoID, Crockford base32, 12 | 12 | 20000 | yes (57) | yes | no |
| Sqids (encodes a sequence) | 6+ | 20000 | yes (51) | yes | leaks count |

Database: PostgreSQL 17.6, no native `uuidv7()`, no `pg_uuidv7` extension; every table's key is `gen_random_uuid()`.

**Recommendation (Backstage-native):**
1. The row key stays a **UUID** (`gen_random_uuid()`), the equivalent of Backstage's `metadata.uid`.
2. The engagement gets a **public id: 12 characters of lowercase Crockford base32** (NanoID-style custom alphabet,
   60 random bits; generated in SQL from `gen_random_bytes`, unique index). No sequence leak, URL-safe, always a
   valid Backstage name. At a million engagements the collision chance is about 4 in 10 million, and the unique index
   refuses the rare one.
3. **The full key is notation, not the entity name.** In the catalog the engagement is `metadata.name: eg-<id>` and its
   hats `eg-<id>.pm`; `metadata.title` carries `webomage → acme`. The string `<contractor>.<engagement>.<client>`
   stays the canonical address in docs, logs, the UI and the AgDRs, computed from the relations. So org slug length
   never couples to the 63-character cap, and **Q17 (refuse long slugs) is no longer needed**. The `eg-` prefix
   keeps engagement names from colliding with org and unit names, which share the `Group` kind.

## 2. Q2 — the word for the relation, and the other entity names

The owner: "contract" is Upwork's word and should keep meaning what Upwork (and other sources) sync; the relation
may come from Upwork, a direct deal or another platform.

**Proposed vocabulary**

| Term | Is | Cardinality | Backstage |
|---|---|---|---|
| **engagement** | the relation: contractor org serves client org; where hats live; key `<contractor>.<engagement>.<client>` | between exactly 2 orgs (may be the same) | `Group`, `spec.type: engagement`, parent = contractor, annotation `w0m.dev/client` |
| **contract** | a commercial agreement record from a **source**: Upwork (synced, Upwork's shape), direct, another platform | 0..n per engagement | `Resource`, `spec.type: contract`, owner = the engagement, annotation `w0m.dev/source` |
| **project** | a delivery workspace (repo, milestones, vault) | 0..n per engagement | `System`, `spec.type: project`, owner = the engagement |
| **hat** | a role on one side of one engagement, resolving to an office | ≥ 3 per engagement | `Group`, `spec.type: hat`, parent = the engagement, members = holders |

**Collision check** (living docs, specs and code): "engagement" appears 399 times, already in this meaning in the
`client-engagement` spec ("Client sees only own engagements"), the site's case studies ("Typical engagement: 4–12
weeks") and ordering flows. The one foreign meaning is LinkedIn **post engagement** (analytics copy in the LinkedIn
panel), confined to that UI. No table is named engagement. Rejected: *agreement*/*deal* (commercial-only, collide
with contract), *assignment* (collides with staffing), *relationship* (too generic; also social graph).

**Import rule for history (98 contracts, 78 clients):** one engagement per Upwork contract, lossless; repeat
contracts with one client stay separate engagements unless the owner merges them.

**Terms revalidation — measured uses in living surfaces**

| Term | OpenSpec specs | Active changes | Gauge specs | Docs | Open tickets | Verdict |
|---|---|---|---|---|---|---|
| contract | 238 | 282 | 52 | 661 | 264 | keep; nearly all already mean the commercial record |
| hat | 226 | 379 | 1 | 674 | 115 | keep; one meaning only (the account-class sense is "acting role", TERMINOLOGY-MAP T6, 2026-08-28) |
| office | 47 | 188 | 3 | 492 | 19 | keep: the permission bundle behind a hat |
| engagement | 32 | 87 | 7 | 139 | 24 | adopt for the relation |
| host org / client org (as kinds) | 8 | 96 | 0 | 40 | 17 | retire: sides of an engagement |
| `client_users` / `client.member` | 27 | 85 | 0 | 112 | 11 | retire with `public.clients` (step S8) |
| tenant | 33 | 12 | 3 | 81 | 35 | retire: "org" |
| active/worn role (class) | 26 | 43 | 0 | 117 | 7 | retire with Axis-1 classes (Q8) |
| squad / guild | 41 | 92 | 9 | 204 | 14 | theme words only ([[AgDR-0020]], [[AgDR-0022]]) |

**DSL surfaces:** user stories ("As a … I want … so that …", `docs/flows/multi-role-user-stories.md`, the client
manual), OpenSpec requirements (GIVEN/WHEN/THEN) and Gauge specs (personas Ada/admin, Carol/client, Ravi, Nox). The
Gauge personas are account classes; in the model they become: platform root, operator member, network member, solo
client, company-client member. The four non-real test accounts of T439 AC10 are the same set.

**Proposed enforcement:** extend the advisory lexicon lint (T23) with the retired terms, so new text stops using them;
rewriting the ~350 existing retired-term uses is its own ticket.

## 3. Q3 — offices, hats and how permissions are wired

The owner's reading is right: **a hat is a role; it resolves to an office; an office is a bundle of capabilities; the
worn hat's capabilities are the effective permissions; collapse adds the fallback role's office to the main holder.**

**Live wiring (measured):** `project_roles.slug` → `wom_role_office(slug)` → office → `office_capabilities` →
`wom_context_capabilities(org, project)` (unions the caller's hats and direct grants) → the CP menu and gate
(`nav.ts`, `holds()`); row security reads capabilities in **5 of 334 policies** (`blueprints`, `profile_skills`,
`verified_credentials`, `profile_resumes` ×2).

**Backstage:** the catalog records **possession** (a `User` is a member of a hat `Group`). Permissions are not catalog
data; Backstage keeps them in its Permission framework (policy code). So offices stay w0m-side; a hat carries
`w0m.dev/office` as an annotation.

**The pasted "Offices in w0m" note is right in concept and stale in facts:** none of its seven office names exist live
(`project.manager`, `tech.lead`, `accounting.principal`, `tech.delivery`, `client.principal`, `tech.ops`,
`quality.owner`: all renamed to `w0m.*` under AgDR-0020); `pm` maps to `w0m.tech.program` (5 capabilities), not a
delivery-manager office; row security on invoices/contracts/milestones/payouts does **not** read capabilities; the
GitHub/Infisical/Cloudflare provisioning by office is not built.

**Recommendation:** offices lose the `w0m.` prefix and become one generic catalog (`project.manager`, `tech.lead`,
`tech.ops`, `quality.owner`, `tech.dev`, `client.principal`, …), because the hat supplies the context
(engagement + side); unit slots keep `<org>.<area>.<role>`. Open: which office backs `pm` (Q24).

## 4. The default hat (owner, 2026-09-26)

**Backstage:** a `User`'s `spec.memberOf` always lists its groups; the home org's `team` unit is one of them. That
membership **is** the default hat.

**Proposed:** every person's default hat = membership of `<home org>.team` (a personal org's single person included).
For `webomage`, **`w0m` unit slots are granted to holders of the `webomage.team` default hat** (the operator gate made
structural), and the `w0m` platform group carries `w0m.dev/operator: group:default/webomage`. That is the link between
the platform's units and the operator org. *(Interpretation of the owner's sentence, to confirm: Q25.)*

## 5. The platform as a directory: verified people and orgs, portfolios, claims

**Aim (owner):** not an Upwork clone; a catalogue of verified service providers (people: indie devs, freelancers,
seasoned contractors; companies) with portfolio pages, and businesses claiming and confirming their company page.

**Backstage mapping:** a person is a `User`, a company a `Group` (`company`); a public page is the entity page
(`spec.profile` name/picture/email, `metadata.description`, `metadata.links`, `metadata.tags`); verification is an
annotation (`w0m.dev/verified-level`) backed by the verification record; a portfolio item is a `System`/`Resource`
owned by the person or company, public by annotation.

**What exists (measured):** verification: T346 (done, corporate registries) and T349 (done) wrote `kyc_level` /
`verification_status` onto `public.clients` and `gamification.compliance_profiles`, **not** onto orgs or persons;
the design for `portfolio_items` and `identity_verifications` is in `RBAC-PROJECT-ROLES-PIVOT.md` §7 (T354, design
only); no public profile or portfolio page is built; T439 AC8's split tickets (public profiles; brand/page claims and
anti-squatting; Job/Join UI) are **not filed yet**.

**Proposed shape:**
- **Unclaimed company pages** come from history: the 78 imported clients are companies with no members.
- **Claiming** a company page = proving control (domain email, SAT RFC / CSF QR through `packages/kyc`) and becoming its
  main person. The claimant's home moves from their personal org to the company (Q27).
- **Portfolio items are owned by the person**, not the personal org, so a home move loses nothing; company portfolio
  items are owned by the company.
- **Verification moves to orgs and persons** when `public.clients` retires (step S8).
- **Listing** = catalog query: companies and persons that are public and verified.

## 6. What changes in the decisions (pending the owner's yes)

- AgDR-0028: "contract relation" → **engagement**; key `<contractor>.<engagement>.<client>`; engagement public id
  12-char base32 with `eg-` catalog names; Q17 dropped; offices generic; default hat; Q1–Q3 answered as above.
- New decision for the directory (verified people and orgs, claims, portfolios), or fold into T439 AC8's split tickets.
