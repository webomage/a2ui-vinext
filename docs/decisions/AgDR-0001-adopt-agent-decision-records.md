---
id: AgDR-0001
title: "Adopt Agent Decision Records, and index rather than migrate the 151 existing decisions"
timestamp: 2026-08-19T00:00:00Z
agent: claude-code
model: claude-opus-5
trigger: user-prompt
status: superseded
superseded_by: AgDR-0002
supersedes:
ticket: T232
---

# AgDR-0001 — Adopt Agent Decision Records

## Y-statement

> In the context of **an estate whose 151 recorded decisions follow no format and whose corrections
> are written in place**, facing **three decisions in one day that had silently stopped being true**,
> we decided **to adopt AgDR — ADR plus agent attribution and an explicit supersession link** for
> decisions from here on, to achieve **an overturned decision that announces itself**, accepting
> **that the 151 existing ones stay unstructured and are only indexed, not migrated**.

## Context

Measured 2026-08-19, not recalled:

- **151 decisions across 68 files** — 137 in ticket bodies, 6 in `.w0m/sdlc.json`, 3 in
  `TECH-DEBT.md`, 2 in `ROADMAP.md`, 2 in `cv/resolutions.json`, 1 in `confirm-policy.json`.
- Against Nygard's sections: **Context 0/68 · Decision 0/68 · Consequences 1/68 · Alternatives 0/68.**
  The 58 "Status" hits are the ticket template's `## Status notes`, not ADR status.
- **126 tickets and 199 of 667 commits contain a correction of an earlier claim**, all written *in
  place*. A reader of the original gets no signal it was overturned.
- 🔴 **Three superseded decisions surfaced in a single day**: `ide_surfaces` recording *"opencode
  exists in no project"* (true when written, false now); `AGENTS.md` pointing at
  `.agent/LESSONS.md` (retargeted weeks earlier, pointer left dangling); **D57** stating backups
  were not scheduled (false within hours — and repeated as fact anyway).
- **All 667 commits since 2026-08-01 carry one git author.** At least two agents and a human wrote
  them and **nothing on the commit says which**.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Nygard ADR** (2011) | de facto standard; forces consequences | no options table; no agent attribution; no supersession field | rejected — lacks the field that motivated this |
| **MADR** (2017) | options-considered first-class; markdown | still human-era; no agent/model; supersession by convention only | rejected — closer, still silent on who decided |
| **Lore** (arXiv 2026) | decisions in commit messages | 🔴 **explicitly proposed, not evaluated** — no benchmarks or user study; and **we already do it better**: median 21-line, 187-word messages, 80% with a real body, 617/667 naming a ticket | rejected — adopting an unevaluated spec to formalise existing practice |
| **AgDR** (2026) | ADR + `agent`/`model`/`trigger` + **`status: superseded`**; Y-statement forces the trade-off | newest and least proven; frontmatter is overhead on trivial decisions | **ACCEPTED** |
| Migrate all 151 into the format | uniformity | weeks of reformatting; the reasoning is already richer than an ADR; risks losing nuance to fit a template | rejected |

## Decision

**New decisions use AgDR** (`project/templates/decision.md`), stored in `docs/decisions/`.
**Existing decisions are left where they are and INDEXED** by `just decisions` → `docs/DECISIONS.md`.

⚠️ **The agent attribution was nearly dropped.** It was first argued as low-value — *"one owner, one
agent"* — and that was **wrong**: a parallel Antigravity agent commits into this estate today, and
[[T232]] is explicitly about adding Gemini and opencode. Multi-agent attribution is the estate's
direction, so the field earns its place. The owner caught this.

## Consequences

**Positive.** An overturned decision can announce itself instead of being corrected silently.
Attribution survives, so *"which agent decided this, on which model"* is answerable — and a decision
made by a superseded model can be re-reviewed on that basis. The Y-statement's trade-off clause
makes a decision with no stated cost visibly incomplete.

**Negative, stated plainly.** This is the **newest and least proven** of the formats — one blog
author's production experience, no independent evaluation. It adds ceremony that will be skipped for
small decisions, so the corpus will be **mixed** (151 unstructured + N structured) for a long time,
possibly forever. And the index must therefore keep reading both, which is more code than either
alone. ⚠️ **A format nobody writes in is worse than none** — if `docs/decisions/` holds only this
file in a month, that is the finding, and the honest response is to drop it rather than defend it.

## What this does NOT decide

Not that the 151 existing decisions get migrated — they do not. Not that every decision needs a
record; the threshold is deliberately unstated and will be set by practice. Not `AGENTS.md`'s role
as the agent-facing control plane, which is [[T232]] AC1 and already decided separately.
