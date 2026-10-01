---
id: AgDR-0018
title: "The @webomage.com email gate is decided real, narrowly reversing locked decision 3's domain-openness clause"
timestamp: 2026-08-10T00:00:00Z
agent: claude-code
model: claude-sonnet-5
trigger: user-prompt
status: accepted
superseded_by:
supersedes: AgDR-0017
ticket: T117
---

# AgDR-0018 — the `@webomage.com` email gate is decided real, narrowly reversing [[AgDR-0017]] decision 3's domain-openness clause

> **Amended by [[AgDR-0027]] decision 7 (2026-09-26):** the `@webomage.com` gate guards membership of the operator
> company `webomage`, and `w0m` unit slots go only to holders of `webomage.team`. The domain is necessary, not
> sufficient, and grants nothing by itself, so this record's blocking precondition (demo seeds on `@webomage.com`
> falsely admitted) no longer applies.

⚠️ **Scope of this supersession, stated precisely:** this reverses only the clause of
[[AgDR-0017]] decision (3) reading *"trainees may come from any company / any email domain, not
only `@webomage.com`."* Decision (3)'s five-class split, decisions (1), (2) and (4), and the
talent-tier bands are **untouched**.

## Y-statement

> In the context of **[[AgDR-0017]] decision 3's "any email domain" clause, put to the owner again
> after live measurement showed nothing enforces it**, facing **the owner reaffirming the gate is
> real despite that measurement**, we decided **the `@webomage.com` email gate IS real and
> intended**, reversing the domain-openness clause, to achieve **an authorization boundary the
> owner actually wants**, accepting **a blocking precondition that had not shipped yet: the
> `seed-demo` accounts sit on `@webomage.com`, so shipping the gate as literally stated would admit
> exactly the two classes it exists to deny (`client`, `recruit`) at a 2-of-2 false-positive rate,
> until the seeds move to a non-org domain**.

## Context

Backfilled from ticket prose per [[AgDR-0002]]'s criterion — this decision directly narrows a
clause of [[AgDR-0017]], is still current (the precondition it named was resolved in code the same
day), and is referenced from T117's Definition of Done ("client access reads
`projects.client_id`/`contract_id` rather than `client_users`" traces back to this cluster).

**What triggered the re-check.** Owner, 2026-08-10: *"candidate also a registered user, but only
members have access to internal resources on base of @webomage.com e-mails — and candidates and
clients not, also outside trainees."* Three of four claims were already the locked model
(candidate=recruit; candidates/clients have no internal access; outside trainees are excluded by
enrollment, not membership). The email-domain claim **contradicted** [[AgDR-0017]] decision 3, so
it was measured before being recorded, not written down on say-so:

- **Nothing enforces such a gate today** — 0 RLS policies, 0 functions, 0 constraints/index
  predicates reference `work_email` or the domain. `profiles.work_email` is written by one
  backfill migration and read by nothing — a label, not an input.
- **The domain does not discriminate the classes it's meant to separate** — live, the 1 `client`
  row and 1 of 2 `recruit` rows are on `@webomage.com` (the `seed-demo` accounts
  `demo-client@webomage.com`, `demo-candidate@webomage.com`). The rule as stated would admit both
  classes it exists to deny.
- The correlation is real (7 `work_email`-bearing profiles are all org, all `member`) but the
  causal direction is backwards: staff get an org address *because* they are members, not the
  reverse.

**Put to the owner with this evidence, 2026-08-10 — OWNER DECISIONS (4 decided, 3 opened):**

> 🔴 **1. The `@webomage.com` email gate is DECIDED REAL** — reaffirmed after the evidence was put
> to them. This reverses part of locked decision 3 ("any company/any email domain"), struck
> through in the design doc with a pointer to this reversal.

**Blocking precondition, resolved same day, in code:** demo identities moved from
`@webomage.com` to `@demo.webomage.com` (owner chose a dedicated subdomain over `@w0m.xyz`,
correcting a factual premise — live DB showed both demo accounts were actually on
`@webomage.com`, zero profiles existed on `w0m.xyz`, which is real only for staging HOST routing).
Landed in `seed-demo/index.ts`, with two defects fixed in the same pass (email-keyed
`findOrCreateDemoUser` needed a rename-in-place branch to avoid orphaning FKs; `resetClientData`
needed to match every historical address, not just the current one). **Owner action still
pending as of this writing**: deploy `seed-demo` and run `just seed-demo` — live accounts remain
on the org domain until that runs.

**Recommended shape, not yet built:** gate on **provisioned org identity**
(`work_email IS NOT NULL`) with the domain as the *provisioning convention*, rather than a literal
domain string — this preserves the owner's intent while keeping the two locked cases that a
literal domain string would kill (external contractor-member; fully-independent trainee alive).

**Three same-batch decisions also recorded (not part of this reversal, listed for
completeness):** `trainer` → `is_management=true`; `talent.lead` → `recruiting.lead` (rename);
`ai-interviewer` → `member` + `subject_type='ai'` + `interview.conduct` grant (unblocks build task
1.0). A related defect found the same day (`client.principal` is agency-side but named
client-side) is tracked separately, not resolved here.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Keep [[AgDR-0017]] decision 3 as originally locked (any email domain) | no reversal, no migration | contradicts what the owner actually wants once evidence was shown; leaves an intent unimplemented | rejected |
| Gate on a literal `@webomage.com` string match | simplest possible check | fails immediately — 2-of-2 false positives on live data (both seed-demo accounts) until seeds move | rejected |
| **Gate on provisioned org identity (`work_email IS NOT NULL`), domain as provisioning convention; move seed-demo off the org domain first** | preserves owner intent; keeps external-contractor-member and independent-trainee cases alive; unblocks safely once precondition ships | requires the seed-demo migration to land and be run before the gate can ship at all | **ACCEPTED** (precondition shipped in code 2026-08-10; owner deploy step still pending) |

## Decision

The `@webomage.com` email gate is real and intended, narrowing [[AgDR-0017]] decision 3's
domain-openness clause. It ships as a `work_email IS NOT NULL` provisioning-identity check, not a
literal domain-string match, and only after `seed-demo` accounts are moved off the org domain
(code landed 2026-08-10; deploy + `just seed-demo` still an owner action).

## Consequences

**Positive.** The authorization boundary the owner actually wants now has a concrete, measured
path to shipping that doesn't self-defeat on the two live seed accounts. The precondition was
caught and fixed in code the same day rather than discovered after the gate shipped inverted.

**Negative, plainly.** The gate itself is still **not enforced anywhere** as of this decision —
0 RLS policies, 0 functions reference it; only the precondition (seed-demo domain move) has
landed. Until an owner runs `just seed-demo` against the deployed function, the live accounts
remain on the org domain and the gate cannot ship without immediately failing its own purpose
again.

## What this does NOT decide

- The concrete RLS policy or function that implements the `work_email IS NOT NULL` check — not
  yet built.
- [[AgDR-0017]] decisions (1), (2), (4), or the rest of decision (3) — untouched by this record.
- The `client.principal` rename/split, `devops`'s `is_management` status, or the two founder-side
  offices' tier status — opened the same day, still unresolved, not decided here.
