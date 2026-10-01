---
id: AgDR-0019
title: "Unified <org>.<unit> namespace, client-as-org-relation, offices-to-hats unification, and decorative gamification"
timestamp: 2026-09-14T00:00:00Z
agent: antigravity
model: gemini-3.8-flash
trigger: user-prompt
status: accepted
superseded_by:
supersedes: AgDR-0013, AgDR-0014, AgDR-0016, AgDR-0017
ticket: T117
---

# AgDR-0019 — Unified `<org>.<unit>` Namespace, Client-as-Org-Relation, Offices-to-Hats Unification, and Decorative Gamification

> **Amended (2026-09-26, [[T458]]):** §2's home anchor and the `org_type` values by [[AgDR-0027]] (`w0m` is the
> platform; a person's default home is a company or a personal org). §3 stands and is made concrete by [[AgDR-0028]]
> (engagements are the only link between orgs; minimum hats per kind). Of the records this one lists as superseded:
> AgDR-0014's rules are restated by AgDR-0028 decision 7; AgDR-0017 is superseded in decision 4 only.

⚠️ **Supersession note:** This record supersedes the separate client-entity model from [[AgDR-0013]]/[[AgDR-0017]], the DB-level RPG delivery schema from [[AgDR-0016]], and the dual-axis split between `project_roles` and `offices` from [[AgDR-0013]].

## Y-statement

> In the context of **[[T117]]'s RBAC consolidation**, facing **(a) fragmented identity silos (separate recruit profiles, separate client tables), (b) parallel un-reconciled hat vs. office mechanisms, (c) DB-level RPG gamification schemas bloating core authorization, and (d) ad-hoc resource scoping strings**, we decided:
> 1. **All subjects and objects operate within a unified `<org>.<unit>[.<subpath>]` URI namespace** (e.g. `w0m.system`, `w0m.admin`, `w0m.manager`, `w0m.projects.public`, `w0m.blog.posts.published`, `w0m.client.bridgeroad.github`);
> 2. **No personal profiles separately for trainees or recruits** — every user entity in the system exists under an `<org>.<unit>` identity;
> 3. **The client is not a separate entity type** — a client is simply an Org with its own units; the client relationship is a project-scoped relation between Orgs established via shared projects (managed by w0m PM and subscription);
> 4. **`org.hats` are constructed directly from offices and office capabilities**, unifying Axis 3 and Axis 3b into a single coherent construct;
> 5. **Gamification is moved completely out of database schemas and core code**, available strictly as an opt-in decorative presentation theme,
> to achieve **a clean, unified, enterprise-grade B2B/c2b2b2c authorization architecture with zero schema duplication and zero semantic drift**, accepting **that legacy `gamification.*` schemas and legacy `public.clients`/`client_users` will be migrated into standard Org relations, and existing delivery tickets will author against canonical project tasks rather than quest tables**.

---

## Context

Over successive iterations ([[T102]], [[T117]], [[T198]], [[T311]], [[AgDR-0011]]–[[AgDR-0018]]), authorization accumulated several disconnected constructs:
1. **Identity fragmentation:** Candidates, recruits, and external trainees were given ad-hoc profile rungs or floating accounts without an organizational home.
2. **Client isolation via separate tables:** Clients lived in `public.clients` and `public.client_users`, isolated from internal staffing machinery and unable to use standard hat/office structures.
3. **Dual-axis divergence:** `project_roles`/`hats` (Axis 3) gained 15 staffed rows while `offices`/`office_capabilities` (Axis 3b) remained company-wide with 2 grant rows, forcing engineers to ask "is this a project role or an office?"
4. **RPG gamification in core schemas:** The `gamification` schema (`adventures`, `raids`, `quests`, `adventure_role_slots`) sat in PostgreSQL alongside business tables, despite carrying zero live rows and running a divergent grant regime (`postgres` alone).
5. **Ad-hoc scoping:** Scopes were inconsistently stored across UUID columns, enum strings, and parsed namespaces.

The owner directive (2026-09-14) cleans this estate down to first principles.

---

## Options Considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Status Quo (Dual axes, separate client schema, DB gamification)** | No migrations required immediately | High cognitive overhead, 4 mutually-blind mechanisms, ongoing terminology collisions | Rejected |
| **Fold Offices into Project Roles only (AgDR-0013 interim)** | Fixes per-project adoption | Leaves clients as an edge-case join table; ignores trainees; leaves gamification in DB | Superseded |
| **Unified `<org>.<unit>` Namespace + Client as Org Relation + Decorative Gamification + Hats from Offices** | One universal subject/object URI grammar; uniform B2B multi-tenant model; removes DB bloat; unites hats and offices | Requires migrating `public.clients` into `orgs` and updating CASL/RLS helpers to parse/evaluate URI hierarchy | **ACCEPTED** |

---

## Decision Details

### 1. Unified Namespace Grammar: `<org>.<unit>[.<resource/subpath>]`

Every subject and every object in the ecosystem is addressed by a hierarchical, dot-notated identifier:

```
<org>.<unit>[.<subpath>]
```

#### Subject URIs (Who is acting):
- `w0m.system` — machine principal / service role
- `w0m.admin` / `w0m.admin.alice` — platform operations
- `w0m.manager` / `w0m.delivery.pm` — engagement lead
- `w0m.talent.recruit` — applicant within w0m's talent unit (no floating profile)
- `bridgeroad.engineering.bob` — external contractor/partner within BridgeRoad's org unit

#### Object / Resource URIs (What is being accessed):
- `w0m.projects.public` — public project catalog
- `w0m.blog.posts.published` — public content
- `w0m.client.bridgeroad.github` — client integration resource scoped to BridgeRoad's project relation
- `acme.finances.invoices.2026` — org-scoped internal accounting object

**Interaction Rule:** A Subject-URI requests an Action on an Object-URI. Authorization is the evaluation:
`can(Subject-URI, Action, Object-URI)`.

---

### 2. No Standalone Profiles for Recruits or Trainees

There are no unattached "candidate" or "recruit" personal profiles in the system:
- Every human and machine user is attached to an `<org>.<unit>`.
- Internal recruits belong to `w0m.talent.recruits`.
- Partner or client trainees belong to `<client_org>.<unit>`.
- Seniority and progression (applicant → trial → active → senior) are metadata attributes within their unit, not separate database tables.

---

### 3. Client as a Project-Scoped Org Relation (Not a Distinct Entity)

The `public.clients` table is retired from being an isolated security primitive:
- A "client" is simply an **Org** (e.g. `bridgeroad`, `acme`).
- It has its own units and users: `bridgeroad.exec`, `bridgeroad.devops`.
- The "client relationship" is established when w0m and the client Org are joined on a **Project**:
  ```
  projects (id, title, host_org_id = 'w0m', client_org_id = 'bridgeroad', status, subscription_tier)
  ```
- Access to client-facing deliverables is granted by the w0m Project Manager based on contract/subscription rules.

---

### 4. Org Hats Constructed from Offices and Capabilities

Axes 3 and 3b merge into a single model:
- **`offices`** define canonical responsibility bundles (`tech.lead`, `project.manager`, `devops`, `accounting.principal`).
- **`office_capabilities`** define the atomic permissions held by each office.
- An **`org.hat`** is an office instantiated on an Org/Project context:
  ```
  org_hats (id, org_id, project_id, office_id, user_id, is_active)
  ```
- When a user wears an `org.hat`, they dynamically inherit the capabilities of that office scoped to that Org and Project.

---

### 5. Gamification as an Opt-in Decorative Theme

The `gamification` PostgreSQL schema is purged from core database migrations:
- `adventures`, `raids`, and `quests` are removed as database constraints.
- Core delivery runs on standard engineering entities: `projects → epics → tasks` (or `issues`).
- Gamification terminology (XP, badges, gladiator/legioner ranks, quest skins) exists purely in the frontend UI as an **enabled/disabled decorative theme** toggled per project or per user profile.

---

## Consequences

### Positive
- **Conceptual purity:** Everything is an Org, a Unit, or a Resource. One syntax describes subjects, permissions, and objects.
- **True B2B / multi-tenant readiness:** Client orgs can bring their own units, managers, and developers without special-casing "client users" vs "staff users."
- **Unified hat/office pipeline:** No more tension between `project_roles` and `offices`. An org hat is simply an instantiated office.
- **Radical schema decluttering:** Purging the `gamification` DB schema removes unused tables, eliminates grant disparities (where `postgres` alone held rights), and simplifies foreign key chains.

### Negative & Migration Cost
- `public.clients` and `public.client_users` data must be migrated into standard `orgs` and `org_members`.
- References to `gamification.quests` / `adventures` in code must be refactored to standard project task primitives, and game elements moved to the UI theme layer.
- `abilities.ts` (CASL) and `wom_can_on` (RLS) must be updated to evaluate dot-notated URI patterns.

---

## What This Does NOT Decide

- The exact frontend design tokens for the decorative gamification theme.
- The external billing provider / Stripe subscription tiers that enable multi-unit org features.
- The concrete timeline for running the DDL dropping legacy `gamification.*` tables in production.
