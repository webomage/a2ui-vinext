---
id: AgDR-0013
title: "project_roles/hats is the per-project RBAC axis; offices/capabilities/resource_grants stays company-wide"
timestamp: 2026-09-12T00:00:00Z
agent: claude-code
model: claude-sonnet-5
trigger: user-prompt
status: superseded
superseded_by: AgDR-0019
supersedes:
ticket: T117
---

# AgDR-0013 — `project_roles`/`hats` is the per-project RBAC axis; `offices`/`capabilities`/`resource_grants` stays company-wide

> **Superseded by [[AgDR-0019]] §4** (offices and hats unified; one axis, not two). Recorded 2026-09-26 under [[T458]]: AgDR-0019 declared the supersession but never set this field.

## Y-statement

> In the context of **[[T117]] AC3/AC4, which ask CASL/RLS to be driven off
> `capabilities`/`offices`**, facing **two parallel per-project-shaped mechanisms with wildly
> different live adoption — 2 `resource_grants` rows / 0 RLS policies / 0 CASL reads vs. 15
> `project_roles` rows staffed across 2 of 7 projects**, we decided **`project_roles`/`hats`
> ([[T311]]'s axis) becomes the authoritative source CASL/RLS wire to for PER-PROJECT decisions**
> to achieve **wiring the axis that already has real adoption instead of the one that was designed
> for this but never staffed**, accepting **that two axes now stay permanently parallel —
> `offices`/`capabilities`/`resource_grants` is not deprecated, merged, or migrated away from; it
> remains authoritative for company-wide, non-project-scoped responsibility, and which axis a given
> decision belongs to is a judgement call ("is this scoped to one project, or to the whole
> company"), not a migration path**.

## Context

Backfilled from ticket prose per [[AgDR-0002]]'s criterion — referenced from three places
(T117 AC3's 2026-09-12 supersession note, AC11, AC12) and still constraining which table CASL/RLS
target, so it earns a structured record rather than staying prose-only.

Measured 2026-09-12, restated in T117's own table:

| axis | mechanism | live adoption |
|---|---|---|
| `offices`/`capabilities`/`resource_grants` ([[T102]]'s Axis 3) | company-wide responsibility bundles (`accounting.principal`, `talent.recruiting`, …) | 2 `resource_grants` rows, 0 RLS policies, 0 CASL cases read it |
| `project_roles`/`hats` ([[T311]]'s axis) | per-project role (Tech Lead/PM/Developer/DevOps/QA/…) | 15 `project_roles` rows staffed across 2 of 7 projects ([[T313]], [[T314]], [[T319]], [[T352]]) |

`resource_grants` was already **built** (`20260828040000`, closing [[T102]] AC4's gap) — the open
question was never "does the table exist", it was "which of the two built-and-parallel mechanisms
does CASL/RLS actually read". T117's AC3/AC4 checkboxes had not been flipped when `resource_grants`
landed, which is the drift this decision also cleans up.

**Independent DSL-spec support, found 2026-09-13** (one day after this decision, during
[[T117]]'s terminology cross-reference pass): `openspec/specs/project-roles/spec.md`'s "DevOps
Canonical Project Role" requirement (L186) already states DevOps-as-project-role is *"unrelated to
the global `public.offices` security-capability slug `tech.ops` … different axis, different
table"* — the normative spec layer had independently arrived at the same two-axis split, for a
different concrete case (DevOps), before this AgDR formalized the general rule. See
[`TERMINOLOGY-MAP.md` §T4](../backend/TERMINOLOGY-MAP.md).

**Related prior decision, not superseded:** [[AgDR-0011]] (2026-08-28, T102 AC4) settled that a
*grant* is project-scoped via a *hat* and *units* stay org-chart slots, and named "a hat table" as
"a new subject for the office axis". That phrasing anticipated the hat table landing inside the
office axis; this decision clarifies that it did not — `project_roles`/`hats` is its own axis,
parallel to `offices`/`capabilities`, not a subject folded into it. AgDR-0011's actual ruling
(units vs. grant scoping) is untouched; only that one anticipatory phrase is refined here.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Wire CASL/RLS to `offices`/`capabilities`/`resource_grants` (the ticket's original Axis 3 target) | matches T117's original design intent; company-wide semantics are simpler | 0 RLS policies, 0 CASL reads, 2 rows total — would be wiring a mechanism nobody has staffed | rejected |
| Migrate `project_roles`/`hats` data into `offices`/`capabilities` and wire one axis only | one axis, one mental model | forces a company-wide-shaped table to represent a per-project concept it wasn't designed for; loses the 15 already-staffed rows' shape | rejected |
| **Wire CASL/RLS to `project_roles`/`hats` for per-project decisions; keep `offices`/`capabilities`/`resource_grants` for company-wide decisions, permanently parallel** | wires the axis with real adoption now; each mechanism keeps the shape it fits (per-project vs. company-wide) | two axes to reason about forever; "which axis does this belong to" is a judgement call with no gate to enforce it | **ACCEPTED** |

## Decision

`project_roles`/`hats` is the axis [[T117]] AC3/AC11 wire CASL/RLS to for **per-project** RBAC
decisions. `offices`/`capabilities`/`resource_grants` is **not deprecated or merged** — it remains
authoritative for **company-wide, non-project-scoped** responsibility. Client access extends the
same `project_roles` catalog rather than a third mechanism: Phase 1 (client org holds PM/Tech Lead
hats, standing in for DevOps/QA on the client's behalf) is decided now; Phase 2 (client's own
units/users holding DevOps/QA hats directly) is deferred, undesigned, out of scope here.

## Consequences

**Positive.** CASL/RLS gets wired to the mechanism that already has 15 staffed rows across 2 of 7
projects instead of one with 0 RLS policies and 0 CASL reads — the decision follows adoption
rather than original design intent. `abilities.ts`'s rank-only gap ([[T117]] AC3) now has an
unambiguous per-project target. The client-access extension (AC12) reuses an existing catalog
instead of inventing a third identity mechanism, and `client_users` profiles already satisfy the
shape staff hats use.

**Negative, plainly.** Two axes now stay parallel indefinitely — "is this company-wide or
per-project" is a judgement call made per decision, with no gate that catches a decision wired to
the wrong one. `offices`/`capabilities`/`resource_grants`'s near-zero adoption (2 rows) is not
resolved by this decision, only left alone; if it should have been retired instead, that question
is still open. The `client_users` vs. direct `projects.client_id`/`contract_id` anchoring question
(raised in the same ticket section) is explicitly **not** decided here either — see below.

## What this does NOT decide

- Whether `offices`/`capabilities`/`resource_grants` should eventually be retired, merged, or grown
  — only that it is not touched by this decision.
- Client access Phase 2 (client's own units/users holding DevOps/QA hats directly) — undesigned,
  out of scope.
- Whether `client_users` is kept, narrowed, or retired as the client↔project anchor — T117 raises
  this as an open question in the same section but explicitly defers it.
- Which 6 of the 12 live `user_roles` CHECK values survive ([[T117]] AC5/AC9/AC10) — a separate,
  still-owner-blocked question.
