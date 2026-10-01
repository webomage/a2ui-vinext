---
id: AgDR-0011
title: "A grant is project-scoped via a hat; units stay org-chart slots"
timestamp: 2026-08-28T00:00:00Z
agent: claude-code
model: claude-opus-5
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T102
---

# AgDR-0011 — a grant is project-scoped via a hat; units stay org-chart slots

## Y-statement

> In the context of **[[T102]] AC4, which asks whether a UNIT is scoped to a project or a GRANT is**,
> facing **a Summary that says "team unit slots per project" while `units` has no project column at
> all**, we decided **that units remain org-chart slots and the project scope lives on a hat** — the
> chain being **unit → profile → person (email)**, with a hat as the project-scoped assignment of a
> unit — to achieve **one org chart that does not fork per project**, accepting **that "hat" now
> names two different things in this estate and one of them structurally forbids the other**.

## Context

Owner, 2026-08-28, answering T102 AC4 directly:

> *"grant is project-scoped via Hats, units stay org-chart slots … at the beginning I was in mind to
> use 'units' naming for both org-core and projects but it looks like project's unit representation
> is a hat assigned to unit. unit assigned to profile and profile assigned to person with e-mail"*

The alternative — making units project-local — was considered and rejected by the owner: it forks
the org chart once per project, so a person's place in the company becomes N places.

## 🔴 The word "hat" is already taken, and the two meanings conflict

Measured on production 2026-08-28. There is **no table named `hat`**; the existing hat model is a
set of functions plus one table:

| | existing hat (`wom_acting_*`) | hat as decided here |
|---|---|---|
| what it is | the caller's **current acting role** | a **project-scoped assignment of a unit** |
| stored in | `user_active_role` — `user_id, role, set_at` | nothing yet |
| keyed to | **`user_id`** — the account | **`profile`** — the person |
| cardinality | **`PRIMARY KEY (user_id)`** — exactly one | *"a user can have 2 hats in same project"* (owner, quoted in [[T198]] AC6) |
| value | a role name: `admin`, `client`, `member`, … | a unit, scoped to a project |
| read by | `wom_acting_role()`, `wom_acting_is()`, `wom_acting_in()` — **13 anon-reachable RLS policies** | nothing yet |

⇒ **`user_active_role`'s primary key structurally forbids the decided model.** [[T210]] already
recorded this — *"`user_active_role` has `PRIMARY KEY (user_id)`, so it structurally forbids the
second hat"* — and it is not a detail: one row per user cannot hold two hats on one project, let
alone hats on several.

⚠️ **Do not resolve this by renaming either concept casually.** `wom_acting_is` and `wom_acting_in`
are read by **13 RLS policies that `anon` evaluates**, measured under [[T289]]; revoking or renaming
them makes those policies *error* rather than return false, which takes public reads down. The
estate has already paid for that once ([[T246]], a day).

## Consequences

- **[[T102]] AC4 is answered**: `scope_type='project'` hangs off the **grant**, not the unit. `units`
  gains no project column.
- **A hat table is a new subject for the office axis** — the thing [[T198]] AC7 found missing when it
  measured **zero** tables linking a person to an office. It must land with its reader in the same
  change ([[T200]] AC4, [[T102]] AC2): `just office-axis-check` must never report `HALF-WIRED`.
- **The keying follows [[T210]]**: the chain terminates at a **profile**, not an account, so a hat
  attaches to the person and survives an account change. This is the same decision `connections`
  took on 2026-08-28 with `ConnectionOwner = member | estate`.
- ✅ **The naming collision is settled — owner, 2026-08-28: *"rename the existing one to acting
  role."*** In prose the existing concept is an **acting role**: one role, per account, at a time —
  what `wom_acting_role()` returns. **"Hat" now means only** the project-scoped unit assignment
  decided here.
  🔴 **The FUNCTIONS are not renamed, and that is the resolution working rather than an exception to
  it.** `wom_acting_is` / `wom_acting_in` / `wom_acting_role` were *already* named for the acting
  role — the code was right and the prose drifted away from it. Renaming them would also be
  dangerous: [[T289]] measured **13 anon-reachable RLS policies** reading them, and a policy whose
  function is missing **errors** rather than returning false.
  ⚠️ **Historical text is not rewritten** — 74 occurrences in applied migrations, 5 in archived docs
  and the closed tickets keep the word they were written with. Editing them would falsify the record
  of a decision to tidy a term. The resolution lives in
  [`TERMINOLOGY-MAP.md` §T6](../backend/TERMINOLOGY-MAP.md), which is where a reader meeting "hat"
  in an old file is meant to arrive.
- **`team_members.user_id` is populated** (2 of 2, with `unit_id`), so the unit → person link
  already resolves. The prereq T102's Summary recorded as blocking is met.
