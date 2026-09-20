---
id: AgDR-0000
title: ""
timestamp:            # ISO-8601, absolute. Never "today".
agent:                # claude-code | antigravity | gemini | opencode | human
model:                # e.g. claude-opus-5. REQUIRED when `agent` is not `human` — a decision made
                      # by an older model may warrant re-review. Leave empty for a human decision;
                      # inventing one would attribute a person's judgement to a machine.
trigger:              # user-prompt | hook | automation | audit
status: proposed      # proposed | accepted | executed | superseded
superseded_by:        # AgDR id, when this decision is overturned. 🔴 THE FIELD THAT EARNED THIS FORMAT.
supersedes:           # AgDR id, when this one overturns an earlier decision
ticket:               # T## the decision was made under, if any
---

# AgDR-0000 — <title>

## Y-statement

> In the context of **<situation>**, facing **<concern>**, we decided **<choice>**
> to achieve **<goal>**, accepting **<trade-off>**.

⚠️ One sentence, and the trade-off clause is not optional. A decision with no stated cost is a
preference wearing a decision's clothes.

## Context

What was true when this was decided. **Measured, not recalled** — this estate has repeatedly found a
recorded fact that had silently stopped being true ([[T67]]'s "dead" PAT, D57's "backups not
scheduled"), so state the measurement and the date it was taken.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
|  |  |  |  |

⚠️ **Name the rejected options.** Nygard's format leaves the loser unnamed; MADR made this
first-class precisely because *"we chose X"* is unreviewable without knowing what X beat.

## Decision

## Consequences

Positive **and** negative in the same section, deliberately — the Nygard rule. A consequences
section with only upside means the trade-off was moved somewhere nobody will read it.

## What this does NOT decide

The scope boundary. Without it the next reader infers a wider decision than was made.
