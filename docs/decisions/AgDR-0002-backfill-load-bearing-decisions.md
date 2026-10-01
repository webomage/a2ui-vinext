---
id: AgDR-0002
title: "Backfill the load-bearing decisions as AgDRs; leave the rest indexed"
timestamp: 2026-08-19T00:00:00Z
agent: claude-code
model: claude-opus-5
trigger: user-prompt
status: accepted
superseded_by:
supersedes: AgDR-0001
ticket: T232
---

# AgDR-0002 — Backfill the load-bearing decisions

## Y-statement

> In the context of **151 indexed decisions with no structure**, facing **an index that cannot tell a
> decision from a mention of one**, we decided **to write AgDRs for the load-bearing decisions only —
> those something still depends on** — to achieve **a reviewable record of what actually constrains
> the estate**, accepting **that the long tail stays unstructured and that "load-bearing" is a
> judgement no gate can make**.

## Context

**Supersedes [[AgDR-0001]]**, which stated: *"Not that the 151 existing decisions get migrated — they
do not."* The owner asked for decisions to be reviewed and fulfilled as AgDRs, which changes that.
⚠️ Recorded as a supersession rather than an edit **because AgDR-0001 is the record that argued
against this** — quietly rewriting it would erase the disagreement, which is exactly the in-place
correction this format was adopted to stop.

Measured 2026-08-19 on the index itself:

- **151 rows, of which 110 carry a strong marker** (`OWNER DECISION` / `RULING` / `DECIDED`) and
  **41 matched only a weak one** (`owner, <date>`).
- 🔴 **Some rows are MENTIONS, not decisions** — *"the scope question was ALREADY DECIDED, in
  writing, on 2026-07-16"* records that a decision exists elsewhere. **A line matcher cannot tell a
  decision from a reference to one**, and no amount of regex will fix that; only reading will.
- ⇒ The index's number is a **ceiling, not a count**. Treating 151 as "151 decisions to migrate"
  would have produced 151 records of uneven worth.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Migrate all 151 | uniform corpus | weeks of work; ~41 are weak matches and some are mentions; the prose is already richer than a template | rejected |
| Migrate none (AgDR-0001) | zero cost | leaves every load-bearing constraint unstructured and unsupersedable | **superseded** |
| **Backfill the load-bearing subset** | the constraints that actually bind become reviewable and supersedable | "load-bearing" is judgement, so the boundary is arguable | **ACCEPTED** |
| Backfill by recency | mechanical | recency ≠ importance; the oldest decisions bind hardest here | rejected |

## Decision

**A decision earns an AgDR when something still depends on it** — when not knowing it would change
what the next person builds. Concretely: it constrains code, tooling or process; it is still current;
and it is referenced from more than the one place it was written.

The long tail stays **indexed**, not migrated. `just decisions` continues to cover both.

## Consequences

**Positive.** The constraints that actually bind become reviewable in one place, and — the reason
this format was chosen — **supersedable**: overturning one now produces a struck-through record that
names its replacement, instead of a correction buried in a ticket nobody re-reads.

**Negative, plainly.** *"Load-bearing"* is a judgement **no gate can make**, so the boundary will be
argued and the backfill will be incomplete by someone's measure. A reader may take the AgDR set as
*the* decisions and miss the 151 indexed ones — mitigated only by the index carrying both, which is
weaker than a guarantee. And backfilled records are **reconstructions**: the Context is recovered
from what survives in tickets and config, so a consideration that was never written down is lost,
and the record will look more deliberate than the moment was.

## What this does NOT decide

Not a target number of AgDRs. Not that the indexed 151 are less true — they are the record; these
are a structured view over the part that still binds. Not that future decisions may skip AgDR: from
[[AgDR-0001]] onward, new decisions use the format.
