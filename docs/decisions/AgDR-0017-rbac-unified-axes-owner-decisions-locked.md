---
id: AgDR-0017
title: "RBAC unified-axes design: 4 owner decisions locked (naming, talent-tier bands, 5 classes, client-as-hat)"
timestamp: 2026-07-22T00:00:00Z
agent: claude-code
model: claude-sonnet-5
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T117
---

# AgDR-0017 — RBAC unified-axes design: 4 owner decisions locked

> **Partly superseded (2026-09-26, [[T458]]):** decision 4 (`client` is a class) is replaced by [[AgDR-0019]] §3 and
> [[AgDR-0028]] (client is a side of an engagement; account classes retire, `admin` = the platform root only).
> Decisions 1 (keep live naming) and 2 (talent-tier band, now data that grants nothing) stand; decision 3 is amended by
> [[AgDR-0018]] and [[AgDR-0027]]. AgDR-0019's frontmatter lists this whole record as superseded; that overstates it.

⚠️ **Partial supersession note:** decision **(3)**'s email-domain clause ("any company / any email
domain, not only `@webomage.com`") was reversed 2026-08-10 by [[AgDR-0018]]. Decisions (1), (2),
(4), and the rest of decision (3) (talent-tier bands remain unaffected; the five-class split
itself is untouched — only the domain-openness detail within it was struck) stand as recorded
here. See [[AgDR-0018]] for the narrow scope of what changed.

## Y-statement

> In the context of **[[T117]]'s unified 4-axis RBAC design draft, which shipped with 4 open
> owner questions**, facing **a request to unblock the design so build could start**, we decided
> **(1) keep current live DB naming with no Greek/Latin rename, (2) talent tier is a stored band
> (`applicant→trial→trainee→active→senior`), (3) Axis 1 is five classes
> (`admin/manager/member/client/anon`) with member open to any email domain, (4) `client` is a
> class (hat) unified with `member`, isolated by project-scoping** to achieve **T117 UNBLOCKED —
> the design proceeds to an OpenSpec change** accepting **that "manager" becomes a derived class
> (≥1 `is_management` grant) rather than a stored value, which changes the model from the
> originally-drafted `admin/standard` + `subject_type` split**.

## Context

Backfilled from ticket prose per [[AgDR-0002]]'s criterion — this is the foundational decision set
the entire rest of T117's RBAC work builds on (referenced from the 2026-07-23 amendments, the
2026-08-10 grounding pass, and the 2026-08-10 reversal below), still constrains the live OpenSpec
change (`2026-07-22-rbac-unified-axes`, validated strict, unbuilt), and is current except for the
one clause [[AgDR-0018]] narrows.

**The four locked decisions, owner-recorded 2026-07-22:**

1. **Naming: keep current naming** — no Greek/Latin rename; offices use the values already live
   in the DB (`project.manager`/`tech.lead`/`devops`/`accounting.principal`). Owner correction: the
   review's "tech manager" is actually `devops`; the `tpm`/`tech_program` placeholder is dropped.
2. **Talent tier = band**: `applicant(0)→trial(1)→trainee(2)→active(3)→senior(4)`; "member" is
   derived (`rank >= 2`), never a stored value.
3. **Axis 1 = five clearly separated classes**: `admin / manager / member / client / anon`.
   `manager` = power member units (PM, devops, guru/trainer, accountant), **derived** — requires
   ≥1 grant of an `is_management` office. `member` = devs + trainees, and **trainees may come from
   any company / any email domain**, not only `@webomage.com`. `anon` = applicants, trial-client
   project applications, demo accounts, consultations — TTL soft-rotated, limited data access.
4. **`client` = a class (hat), unified with member** — same grants/capabilities machinery,
   isolated because every client grant is project-scoped (`project_id NOT NULL`); "brother of
   member but completely on the other side of the interaction flows." A member can also hold a
   client hat, so the trainee→client transition stays open by construction.

**Also captured the same day:** agent reach is governed by the same class axis (anon→public agent
scope; member/manager→work-helper + SDLC agent hard-scoped to granted projects per active hat;
admin→full observability; client→needs a new client-facing agent surface, an open sub-question,
not a blocker).

**Resulted in:** `openspec/changes/2026-07-22-rbac-unified-axes` (proposal + tasks +
`specs/security_rbac/spec.md`), validated strict 53/0 at authoring time (later 61/0 after the
2026-08-10 reconciliation pass). Two same-week refinements folded in without reopening this
record: 2026-07-23 added a distinct `tpm` office (supersedes the part of decision 1 that dropped
it) and a 6th class `recruit` between `anon` and `member`/`client`.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Ship the originally-drafted `admin/standard` + `subject_type` Axis 1 | simpler two-value rank | doesn't match the owner's actual mental model (5 distinct classes with different reach); would need reworking almost immediately | rejected |
| Rename offices to a fresh Greek/Latin taxonomy | a clean, project-agnostic vocabulary | throws away 10 already-live, already-seeded office values for no functional gain; pure churn | rejected |
| **Keep current naming; 5 classes; talent tier as a stored band; client unified with member via project-scoping** | matches live data, matches the owner's actual model, minimal migration | leaves genitive-ambiguous names like `client.principal` unaddressed (surfaced later as a defect, 2026-08-10) | **ACCEPTED** |

## Decision

The four decisions above are locked. `openspec/changes/2026-07-22-rbac-unified-axes` is authored
against them and T117 is unblocked to proceed to build.

## Consequences

**Positive.** T117 moves from a 4-open-question draft to an unblocked, OpenSpec-validated design.
The naming decision avoids a needless rename of 10 live office values. The client-as-hat
unification means client access reuses the same grants/capabilities machinery instead of a third
mechanism.

**Negative, plainly.** Decision (3)'s "any email domain" clause was reversed 18 days later
([[AgDR-0018]]) once it was checked against live authorization behaviour — it had not actually
been enforced anywhere, and the reversal needed a precondition (moving `seed-demo` off
`@webomage.com`) before it could ship safely. The `manager`-is-derived framing also took a later
correction: [[T117]]'s 2026-08-10 notes clarify manager IS stored ("the class is assigned, the
grant makes it legal"), not purely derived as first written here.

## What this does NOT decide

- The office-namespace realm/scope naming scheme (`w0m.*`/`client.*`/`system.*`) — see
  [[AgDR-0015]].
- What a hat actually is, mechanically (office vs. class, scoped vs. global) — see [[AgDR-0014]].
- The `client.principal` naming defect and the missing client-side office — surfaced 2026-08-10,
  still open per T117's own record.
- `devops`'s `is_management` status and the two founder-side offices' tier status — opened
  2026-08-10, still unresolved.
