---
id: AgDR-0014
title: "A hat carries permissions, is scoped, and a user may hold several in one project — enforcement input, not presentation"
timestamp: 2026-08-11T00:00:00Z
agent: claude-code
model: claude-sonnet-5
trigger: user-prompt
status: superseded
superseded_by: AgDR-0019
supersedes:
ticket: T117
---

# AgDR-0014 — a hat carries permissions, is scoped, and a user may hold several in one project — enforcement input, not presentation

> **Superseded by [[AgDR-0019]]** (its frontmatter declares it; field set 2026-09-26 under [[T458]]). AgDR-0019 did not
> restate this record's two rules; the owner reaffirmed both on 2026-09-25 and [[AgDR-0028]] decision 7 (accepted)
> restates them for engagements: one worn hat at a time; the root may wear any hat.

## Y-statement

> In the context of **[[T117]]/[[T200]] AC4's step-3 blocker — what a "hat" actually is**, facing
> **a live schema (`user_active_role`, one row per user, no scope column, `role text`) that cannot
> express any of "carries permissions" / "several hats per project" / "changes access, not just
> view"**, we decided **a hat resolves to an office (bundles capabilities), is scoped per-project
> (a user↔scope pair is one-to-many), and switching it changes enforcement, not merely
> presentation** to achieve **the three real requirements the owner named — a client-and-QA-and-
> developer user, separated views, and permissions that actually change**, accepting **that
> `is_capable(capability, scope_type, scope_id)` — which does not exist yet — becomes a hard
> prerequisite rather than a nice-to-have, and that the possession-based arm of [[T198]] AC6 must
> be removed rather than kept alongside the hat arm**.

## Y-statement — the two same-day follow-ons

> Facing **"does an unworn hat's capability still count?"** and **"can an admin act as an office
> nobody assigned them?"**, the owner additionally decided: **hat resolution is EXCLUSIVE** (a
> capability held through an unworn hat is inert, not summed with the worn one), and **an admin may
> wear any hat available on a project, assigned or filled or not** — accepting that a user can lock
> themselves out of their own data by wearing the wrong hat (by design), and that the admin
> "wear-anything" branch needs its own audit trail, distinct from impersonation ([[T39]]).

## Context

Backfilled from ticket prose per [[AgDR-0002]]'s criterion. Owner quote, 2026-08-11:

> *"hat is the set of permissions for a person with assigned role via this hat … a user can have 2
> hats in same project — the client and also the qa force in project or even developer … so to
> separate views we can change available hats to change access and scope"*

Three claims, each with a schema consequence:

1. **A hat CARRIES permissions** — not a label on a session, the bundle acted through. ⇒ resolves
   to an **office**, not a class.
2. **A user may hold SEVERAL hats in the SAME project.** ⇒ scoped; user↔scope is one-to-many.
3. **Switching hats changes access AND scope.** ⇒ an enforcement input, not presentation — answers
   [[T198]] AC6 directly.

**The live schema, measured 2026-08-11, cannot express any of the three:**

```
user_active_role   PRIMARY KEY (user_id)        ← ONE row per user, globally
                    columns: user_id, role, set_at   ← no scope column at all
wom_acting_role()   select coalesce(auth.jwt() ->> 'wom_active_role', wom_highest_role(...))
                    ← one scalar, no scope, no capability
```

`PRIMARY KEY (user_id)` structurally forbids a second hat; `role text` is a class value, not an
office; `wom_acting_is()` compares a scalar, when the real question under this definition is
row-scoped (*"do I hold capability C on THIS ROW's scope?"*).

**Same-day follow-on decisions, owner quotes:**

> *"exclusive — one hat at a time, others inert"*
> *"admin can wear any hat from available on projects, even not assigned or fulfilled"*

`wearable(user, scope) = grants(user, scope) ∪ offices_available_on(scope) IF admin`.

**Same-day correction to my own recommendation:** I proposed building a new `project_offices`
table for "which hats exist on a project, independent of who holds them." The owner corrected
this — `gamification.adventures.project_id → public.projects` plus
`adventure_role_slots(adventure_id, discipline, slot_count_required)` plus
`unit_members.discipline_slot` already is that surface. *"The surface exists; it is empty, not
absent."* (A residual vocabulary gap — `adventure_role_slots` keys on `discipline`, the model on
`office` — is noted as a reconciliation, not a missing table.)

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Hat = which of the user's global roles is active (prior reading) | matches the live schema exactly, no new function needed | cannot express 2 hats in one project or per-row enforcement; the owner's stated requirement is unmet | rejected |
| Hat = office, scoped, one-to-many, resolved EXCLUSIVELY per row via `is_capable()` | matches all three owner claims; a user can hold client+QA+developer on one project; enforcement is row-aware | requires a new function (`is_capable`) and removes the possession arm from existing policies — real build cost | **ACCEPTED** |
| Hat = office, scoped, but resolved as the UNION of all held grants (not exclusive) | simpler mental model, no lockout risk | contradicts the owner's explicit "exclusive" follow-on; silently reintroduces possession-like behaviour | rejected |

## Decision

A hat is a **scoped office**: `is_capable(cap, scope_type, scope_id)` resolves against the **one
hat currently worn** for that scope, not the union of the wearer's grants. `resource_grants`
(user × office × scope) IS this feature — the active hat is a pointer into `resource_grants`, not
a role column. Admins may wear any office available on a project regardless of assignment, and
that branch is audited separately from impersonation.

## Consequences

**Positive.** `is_capable()` now has an unambiguous contract (exclusive, row-scoped), which
directly determines [[T198]] AC6 (possession arm removed — no more ambiguity to resolve later).
The "which hats exist on a project" surface is confirmed to already exist
(`adventure_role_slots`), avoiding a redundant table. `resource_grants` gets a concrete reason to
exist rather than being spec-only.

**Negative, plainly.** `is_capable()` moves from desirable to **prerequisite** — [[T200]] AC4 is
now load-bearing, not a sequencing preference, and nothing in this decision builds it. A user can
lock themselves out of their own data by wearing the wrong hat; this is correct behaviour but
support-visible, and the UI must make the worn hat unmissable or "the CP is broken" tickets will
follow. The admin wear-anything branch needs a new audit trail this decision does not build, and
until it exists an unlogged admin bypass on a client's scope is indistinguishable from the hole it
replaces. `adventure_role_slots`'s `discipline` vocabulary still needs reconciling with `office`.

## What this does NOT decide

- D5's naming question (what to call `client.principal` / Cleo's office) — only its *shape*
  (a hat is just another office) is settled here.
- The office-realm naming scheme (`w0m.*`/`client.*`/`system.*`) — see [[AgDR-0015]].
- The admin wear-anything audit trail's concrete design — only that one must exist.
- Which 6 of 12 `user_roles` CHECK values survive — a separate, still owner-blocked question.
