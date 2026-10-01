---
id: AgDR-0006
title: "AGENTS.md is the agent control plane; CLAUDE.md and GEMINI.md point at it"
timestamp: 2026-08-18T00:00:00Z
agent: claude-code
model: claude-opus-5
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T232
---

# AgDR-0006 — AGENTS.md is the control plane

## Y-statement

> In the context of **an estate that must behave identically under Claude, Gemini and opencode**,
> facing **`CLAUDE.md` in 7 repos and `GEMINI.md` in none**, we decided **to make `AGENTS.md` the
> single source that the per-agent files POINT at**, to achieve **one set of rules three agents
> read**, accepting **an indirection that only works while the pointers resolve**.

## Context

Owner, 2026-08-18: *"I want our system to operate the best-choice same way with Claude and Gemini at
least, but also planning to use opencode for tasks batching."*

Measured on disk: **`CLAUDE.md` 7/7 · `AGENTS.md` 2/7 · `GEMINI.md` 0/7 · `.opencode` 2/7.**

- `AGENTS.md` is the **actual cross-vendor convention** — GitHub studied **2,500+ repositories** of
  it. `LESSONS.md` and the rest are this estate's own inventions.
- 🔬 The estate is **not** Gemini-naive: the **`artemio` client project carries a live 7-file
  `.gemini`** with no generator and no declaration, already flagged by `just ide-trace`.
- [[T192]] had already ruled that **parity is satisfied by POINTING** — a resolvable pointer whose
  target carries the rules — after its founding "duplication" finding turned out to be a symlink.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Copy the rules into each agent's file | every agent reads a complete file | **three files that will disagree within a week** — the failure mode, not the goal | rejected |
| Keep `CLAUDE.md` canonical | already 7/7 | Claude-specific name for an estate-wide contract; Gemini would read a file named for another vendor | rejected |
| **`AGENTS.md` canonical, others point** | one source; matches the cross-vendor convention; [[T192]]'s existing rule | breaks silently if a pointer dangles | **ACCEPTED** |

## Decision

`AGENTS.md` carries the rules and the routing table. `CLAUDE.md` / `GEMINI.md` / opencode surfaces
**point at it**. `just ide-trace` checks the declared surfaces.

## Consequences

**Positive.** One edit reaches every agent. The routing table gives each register a stated job, so
*"which file answers this?"* stops being folklore.

**Negative — and it has already happened.** 🔴 **A pointer that dangles is worse than a copy**, because
it reads as authoritative: `AGENTS.md:304` sent agents to `wom7web/.agent/LESSONS.md`, **a file that
does not exist**, for weeks — while 21 real lessons sat unread in the root file. The indirection is
only as good as the check on it, and **that check is [[T232]] AC10 and is not built**. Until it is,
this decision's main risk is unmitigated.

## What this does NOT decide

Not that `CLAUDE.md` disappears — agents autoload it, so it stays as a pointer. Not the content of
the rules. Not whether `artemio`'s `.gemini` is the template or the debt ([[T232]] AC6).
