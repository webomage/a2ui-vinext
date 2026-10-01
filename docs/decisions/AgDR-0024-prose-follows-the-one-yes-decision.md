---
id: AgDR-0024
title: "The 2026-08-16 one-yes decision stands; the prose that contradicted it is corrected and derived-checked"
timestamp: 2026-09-20
agent: claude-code
model: claude-opus-5
trigger: audit
status: accepted
superseded_by:
supersedes:
ticket: T407
---

# AgDR-0024 — The 2026-08-16 one-yes decision stands; the prose that contradicted it is corrected and derived-checked

## Y-statement

> In the context of a live `deploy-all` that passed `db-migrate` on the root consent while four
> documentation surfaces said it could not, facing a docstring that attributed the opposite rule to
> an explicit owner requirement, we decided **to treat the recorded 2026-08-16 owner decision as
> standing and correct the prose to match the data** — rather than change the policy to match the
> prose — to achieve one description of this gate instead of two contradictory ones, accepting that
> one human `yes` continues to authorise an irreversible live schema write for 45 minutes.

## Context

Measured 2026-09-19/20, in this order:

1. **Observed live.** During the `deploy-all` that restored production, the gate printed
   `✅ confirm: db-migrate — covered by 'deploy-all' (expires in 2697s, HEAD 51e28ad5)`. No
   re-prompt. Benign only by luck — `db-migrate` reported `0 pending / Remote database is up to
   date`, so nothing was written.
2. **The docstring said the opposite**, and sourced it to the owner: *"option to confirm only
   specific steps like migrations" — steps in `always_confirm` re-prompt even inside an agreed
   root, because `deploy-all` chains `db-migrate`…*
3. **The policy data disagreed, and is NEWER.** `confirm-policy.json` →
   `_notes.one_yes_is_the_decision`, dated **2026-08-16** (six days after the docstring's
   2026-08-10 spec): *"one yes from human should be enough here."* It records that the owner was
   shown the trade-off, was **offered the chance to put `db-migrate` and `sync-secrets` back, and
   declined**, and it instructs future readers **not to "restore" the carve-out as a fix for
   something else**.
4. **The behaviour was already pinned.** `test_confirm_step.py` asserts *"db-migrate is COVERED by
   an agreed deploy-all"*, with a comment saying the assertion was deliberately **inverted** from
   its original form and that re-adding the step "reverses a decision rather than fixing a bug".
5. **The drift is not a one-off.** Ten claims across four surfaces — `confirm_step.py`'s docstring,
   `confirm-policy.json`'s own `_always_confirm_why` (sitting ~100 lines above the `_notes` entry
   that contradicted it, **in the same file**), `docs/DEPLOY-CONFIRM.md`, and the `justfile`
   comment block above `_confirm` — all still described the pre-2026-08-16 behaviour, plus two
   stale TTL figures (15 min vs the real 2700s/45 min) and two stale probe counts (16 and 13,
   against 18 actually running). All date to the same 2026-08-16 change, which updated the JSON's
   `_notes` and the test and **nothing else**.
6. One docstring claim was **re-measured and does hold**: the harness `deny` rules it names
   (`db-migrate`, `db-psql`, `db-reset`, `db-backup`, `rotate*`, `sync-*secrets*`) are all present
   in the live 10-rule deny list.

⚠️ **The owner was asked in this session and did not answer.** The question put was whether the
live observation changes the 2026-08-16 call. With no answer, the recorded decision was treated as
standing — which is what "SETTLED" in that note means. This AgDR therefore records a
**documentation** decision taken under an **unchanged** owner decision; it does not claim fresh
owner sign-off.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **(b) Correct the prose; policy unchanged** | Matches the newest recorded owner decision; zero behavioural change; keeps the existing green test honest | Leaves one `yes` authorising a live schema write for 45 min | **CHOSEN** |
| (a) Re-add `db-migrate` to `always_confirm`, remove from `roots["deploy-all"]` | Makes the docstring true again; a schema write always re-prompts | Reverses an explicit owner decision that considered and rejected exactly this; breaks a test written to stop it; the policy file instructs against it in so many words | Rejected — available only as a fresh owner call |
| Delete the contradictory prose instead of fixing it | Fastest | Destroys the reasoning trail; the *why* is the load-bearing part of this module | Rejected |
| Fix the prose without a check | Cheap | Exactly what was done on 2026-08-16, and it rotted for 34 days | Rejected |

## Decision

Keep `confirm-policy.json` as it is. Correct all ten claims across the four surfaces. Add a
**derived** check so prose and data cannot silently diverge again: the suite now extracts the prose
regions that describe this gate and asserts they agree with the policy data on (i) which steps
re-prompt inside an agreed root, in **both** directions, (ii) the consent TTL, and (iii) the
advertised probe count.

## Consequences

**Positive.** One description of the gate. The contradiction now fails a test instead of waiting to
be noticed during a production deploy. The check is mutation-proved: it is shown to flag each exact
sentence removed here, and to stay silent on the replacements. Reversing the decision later stays
easy and stays loud — option (a) turns the checks red with messages naming the decision.

**Negative.** One `yes` still authorises an irreversible live schema write for 45 minutes,
including migrations committed by someone else since the person last looked; this AgDR does not
reduce that, it documents it. The new check reads English, so it matches claim *shapes*, not
meaning — it will not catch every way prose can lie, only the shapes that did. And it adds a
cross-repo coupling: the `justfile` surface is a symlink into `wom7api`, so the suite reports
UNMEASURABLE (and fails) when run from a checkout where that symlink does not resolve. That is
deliberate — fail closed — but it is a real cost.

## What this does NOT decide

Whether one yes *should* cover a schema write. That is the owner's, was settled on 2026-08-16, and
is untouched here. Also untouched: the TTL value itself (2700s), the forgeability of the cached
consent file (a stated known limit, not a new finding), and the harness deny-list drift tracked
separately.
