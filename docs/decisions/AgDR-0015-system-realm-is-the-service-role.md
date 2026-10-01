---
id: AgDR-0015
title: "system.* is exercised by the service role; the realm axis maps onto the enforcement axis"
timestamp: 2026-08-12T00:00:00Z
agent: claude-code
model: claude-sonnet-5
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T117
---

# AgDR-0015 — `system.*` is exercised by the SERVICE ROLE; the realm axis maps onto the enforcement axis

> **Amended by [[AgDR-0028]] decision 9 (2026-09-26):** the `client.*` realm retires, with no alias (a client is a side
> of an engagement, named by its full address); `system.*` = service role stands unchanged.

## Y-statement

> In the context of **[[T117]]'s office-namespace design (`<realm>.<area>.<role>`) needing to
> decide what enforces the `system.*` realm**, facing **a live `pg_roles` with exactly one
> `service_role` (`bypassrls=true`) and no per-service roles**, we decided **`system.*` offices are
> exercised by the Postgres service role, never by a person, while `w0m.*`/`client.*` remain
> enforced by RLS reading a person's grant** to achieve **a realm split that matches how the
> estate already runs machine vs. human actors**, accepting **that every `system.*` office
> collapses into one runtime identity today (49 of 55 edge functions share one service key), so an
> office there can name responsibility but cannot yet constrain it — until [[T206]] (per-service
> Postgres roles) ships**.

## Context

Backfilled from ticket prose per [[AgDR-0002]]'s criterion. Owner quote, 2026-08-12:

> *"I think that `system.*` realm will work via service role while others not."*

This maps the realm axis (who the office namespace names) onto the enforcement axis (what
actually checks it) — and narrows an open modelling question: if `system.*` never grants to a
person, `resource_grants(user_id, …)` only ever holds `w0m.*`/`client.*` rows, so `scope_type`
needs no `system` value.

**Measured live 2026-08-12:**

| realm | actor | an office is… | enforced by |
|---|---|---|---|
| `w0m.*` / `client.*` | a person, through RLS | a **constraint** | a policy reading the grant |
| `system.*` | the service role | a **label** | nothing — `bypassrls=true` means no policy applies |

`pg_roles` holds exactly one `service_role`; the only other non-builtin logins are `postgres`,
`authenticator`, `cli_login_postgres` and Supabase's own admins. **49 of 55 edge functions share
that one service key**, so `system.crawler` and `system.billing` are the same principal at
runtime — an office there can name responsibility, it cannot constrain it.

**The identity is wider than "backend jobs."** [[T202]]'s finding folds in directly: the shared
Supabase client prefers the service-role key and **42 files import it, 25 of them `.astro`
pages** — so under this definition, 25 SSR page renders currently run as `system.*`. This makes
T202 a **prerequisite** for the decision to be meaningful, not a parallel ticket: the realm is
only meaningful once the service role is reached deliberately.

**Options were weighed** (three, descending strength): per-service Postgres roles without
`bypassrls`; keep one shared role and gate inside each function (weakest — `cv-pdf` and
`log-event` have no gate at all, and the latter is `verify_jwt=false` **and** service-key **and**
ungated); or don't model `system.*` as offices at all (a grant table keyed on `user_id` is the
wrong home for machine capability).

**Resolved the same day** — the owner chose per-service Postgres roles, filed as **[[T206]]**,
which carries the cost measurement: 53 of 55 functions reach the DB through PostgREST, where a
per-service role is nearly free — *except* `SUPABASE_JWT_SECRET`/`JWT_SECRET` are absent from
infisical and the live keys are the new opaque format (`sb_publishable_…`/`sb_secret_…`), not
re-signable legacy JWTs. T206 AC1 is therefore an owner dashboard check, not an engineering step.

**Independent corroboration, found the next day (2026-08-12, later the same day):** the "office
realm: name or scope column" question this decision touches had already been decided
2026-07-16/22 via two unarchived OpenSpec changes (`2026-07-22-rbac-unified-axes`,
`2026-07-16-rbac-capability-model` tasks 3.2/3.3) — *"the two agree,"* per T117's own note.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Per-service Postgres roles (`svc_crawler`, `svc_poller`, …), no `bypassrls` | RLS applies; `system.*` offices become enforceable exactly like the others | each function needs its own connection identity instead of the shared key; blocked today by a missing re-signable JWT secret | **ACCEPTED** (filed as [[T206]]) |
| Keep one shared service role, gate inside each function | zero migration cost | self-policing; 2 of 55 functions (`cv-pdf`, `log-event`) have no gate at all today | rejected |
| Don't model `system.*` as offices at all | avoids forcing machine capability into a user-shaped grant table | throws away the namespace consistency the realm split buys; T117's design already assumes it | rejected |

## Decision

`system.*` is the realm exercised by the Postgres service role; `w0m.*`/`client.*` are exercised
by RLS reading a person's grant. `resource_grants` never needs a `system` scope value. Real
per-office enforcement inside `system.*` requires [[T206]] (per-service Postgres roles), which the
owner chose the same day as the strongest of three options.

## Consequences

**Positive.** One fewer CHECK value ever needed on `scope_type` (no `system`). The realm split
matches the estate's existing machine/human separation instead of inventing a new one. T206 gives
a concrete, costed path to real enforcement, and the office-realm naming question resolves
cleanly against the already-decided (but unarchived) `scope_type` design.

**Negative, plainly.** Until T206 ships, every `system.*` office is cosmetic — a label, not a
constraint — and the runtime identity behind it is wider than "backend jobs" (25 `.astro` SSR
pages included). Two edge functions (`cv-pdf`, `log-event`) currently run fully ungated. T206's
own AC1 is blocked on an owner action (locating/rotating a JWT-signing secret), not on code.

## What this does NOT decide

- The concrete per-service role names or migration mechanics — that is T206's own scope.
- Whether the 2 ungated functions (`cv-pdf`, `log-event`) get an interim function-level gate
  before T206 ships — not raised as a decision here.
- The office-namespace naming vocabulary (`fin`/`sales`/`account`/…) — still open per T117.
