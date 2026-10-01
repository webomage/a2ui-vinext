---
id: AgDR-0016
title: "The delivery hierarchy is settled: project -> adventure -> raid -> quest, no FK inversion"
timestamp: 2026-08-12T00:00:00Z
agent: claude-code
model: claude-sonnet-5
trigger: user-prompt
status: superseded
superseded_by: AgDR-0022
supersedes:
ticket: T117
---

# AgDR-0016 — the delivery hierarchy is settled: `project → adventure → raid → quest`, no FK inversion

> ⚠️ **SUPERSEDED (2026-09-17) by [[AgDR-0022]]:** Under Model A (Pure Event-Driven Gamification, [[T27]]), the 8 zero-row campaign hierarchy tables (`adventures`, `raids`, `quests`, `units`, etc.) were dropped in migration `20260917140000_t27_retire_gamification_hierarchy_phantom_tables.sql`. Software work is tracked canonically in repository tickets, and gamification is pure event-driven reputation (`xp_ledger`, `wallets`, `badge_awards`). The delivery hierarchy discussed below is retired.


## Y-statement

> In the context of **a same-day-earlier 2026-08-11 inversion proposal (raid=project,
> adventure=milestone)** conflicting with **four independent existing sources all agreeing on the
> opposite order**, we decided **the hierarchy fork is `project → adventure → raid → quest`, and
> the inversion is withdrawn** to achieve **a single canonical vocabulary every downstream spec can
> be authored against** to achieve **unblocking [[T16]]'s hold on
> `gamification-hierarchy-and-economy-v2` and [[T27]] AC4**, accepting **that this was cheap only
> because every table in the chain holds 0 rows — the same decision made after data lands would be
> a migration across four tables, not a sentence**.

## Context

Backfilled from ticket prose per [[AgDR-0002]]'s criterion. Owner quote, 2026-08-12:

> *"the hierarchy fork — `project → adventure → raid → quest` (four sources) is correct"*

**Four independent sources, all agreeing, measured 2026-08-12:**

1. **FK direction** — `adventures.project_id`, `raids.adventure_id`, `quests.raid_id`.
2. **Migration headings**, `20260702120000` — *"Adventure → Raid → Quest"*, *"top of the
   hierarchy"*, *"the atomic, claimable leaf."*
3. **The naming lexicon** — campaign phase / feature epic / atomic task.
4. **The Authority Model doc** — *"walking Quest → Raid → Adventure → project_id."*

**Canonical terms for every downstream spec:**

```
project    the engagement                        public.projects
adventure  a major campaign phase of a project    gamification.adventures
raid       a feature epic / sprint                public.raids
quest      the atomic, claimable task              gamification.quests
```

**No FK inversion. No column moves.**

**Independent DSL-spec corroboration**, `openspec/specs/gamification-schema/spec.md`:

- *"The system SHALL maintain a `gamification.adventures` table as the **top level of the campaign
  hierarchy**"* (Requirement: Adventure table, L66).
- *"The system SHALL maintain a `gamification.quests` table as **the atomic, claimable leaf unit of
  work**"* (Requirement: Quest table, L91).

The normative spec layer had already encoded the same order and the same descriptive language
("top level," "atomic, claimable leaf") independently of this decision — the DSL spec and the
owner's ruling agree.

**Unblocked by this:** [[T16]]'s hold on `gamification-hierarchy-and-economy-v2`, and [[T27]] AC4
(the spec can now be authored against a fixed vocabulary). **NOT unblocked:** archiving that
change — it validates strict but `tasks.md` reads 0/31, a stale-completion-authority problem
unrelated to the fork itself.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Keep the 2026-08-11 inversion (raid=project, adventure=milestone) | matches a same-day sketch someone had already started reasoning from | contradicts all four independent sources (FK direction, migration headings, naming lexicon, Authority Model doc) | rejected |
| **`project → adventure → raid → quest`, as originally built** | matches every existing source; zero migration cost while every table holds 0 rows | none identified — this is a confirmation of the status quo, not a new design | **ACCEPTED** |

## Decision

The delivery hierarchy is `project → adventure → raid → quest`. FK direction, column names, and
the naming lexicon are unchanged. The 2026-08-11 inversion is withdrawn.

## Consequences

**Positive.** [[T16]] and [[T27]] AC4 are unblocked with a fixed vocabulary. The decision cost
nothing beyond a sentence, because every table in the chain (`adventures`, `raids`, `quests`)
holds 0 rows — no data migration, no column moves. The DSL spec layer already agreed
independently, so no spec rewrite is needed on that front either.

**Negative, plainly.** Archiving `gamification-hierarchy-and-economy-v2` is still blocked — not by
this decision, but by `tasks.md` reading 0/31 against a change that otherwise validates strict.
That is a separate stale-completion-authority problem this decision does not resolve.

## What this does NOT decide

- Whether `gamification-hierarchy-and-economy-v2` gets archived — blocked on its own task-count
  drift, untouched here.
- The milestone-is-one-object-or-two question, named alongside this one in the same ticket section
  as "name-independent, can proceed now" but not itself resolved by this decision.
- Office-realm naming or `scope_type` values — see [[AgDR-0015]].
