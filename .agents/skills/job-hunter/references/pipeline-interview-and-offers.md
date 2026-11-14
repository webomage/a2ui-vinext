# Pipeline Tracking, Interview Prep & Offer Negotiation

Load this guide when initializing or updating an opportunity tracker, preparing for technical/behavioral interviews, reviewing reverse-interview questions, or comparing and negotiating competing offers.

## 1. Pipeline State Machine & Tracker Schema

Maintain a single structured Markdown or JSON tracker in the user's chosen workspace path. Enforce clean transitions so stale leads do not clog active follow-ups:

`Discovered -> Triaged -> Clarifying -> Draft Ready -> User Confirmed -> Submitted -> Recruiter Screen -> Technical Loop -> Offer -> Closed (Won / Withdrawn / Rejected / Passed)`

```markdown
| ID | Source | Organization | Role | URL | Score | Verdict | Compensation | Status | Next Action | Updated |
|---|---|---|---|---|---:|---|---|---|---|---|
| JH-01 | Ashby | Example Cloud | Staff Edge Engineer | [Example Cloud — Staff Edge](https://jobs.ashbyhq.com/example/123) | 88/100 | Priority Apply | $190k-$220k | Draft Ready | User review & submit | 2026-11-14 |
```

### Follow-Up Cadence Rules

- **No Response After Application (`+7` business days):** Send one concise, value-adding follow-up note citing an engineering detail; if still silent at `+14` days, mark `Stale / Archived`.
- **Active Interview Loop:** Update status and log interviewer names, questions asked, and technical gaps identified immediately after each round while recall is fresh.

## 2. Interview Preparation (`STAR + Tradeoffs` Story Bank)

For every `Submitted` or interviewing role, prepare **3–5 verified Architecture Deep-Dive Stories** structured beyond basic STAR so senior technical panels see real engineering judgment:

| Story Element | What to Ground Strictly in Real Work |
|---|---|
| **Context & Hard Constraints** | Scale metrics, latency/cost ceiling, compliance or legacy compatibility limits, team size |
| **Alternatives Considered & Rejected** | Why simpler or trendy options failed under actual constraints (cost, lock contention, cold starts) |
| **Architecture Implemented** | Key interfaces, storage engine, failure-isolation boundary, verification/CI strategy |
| **Production Failure Mode & Recovery** | Real edge case encountered, observability signal that caught it, and root fix shipped |
| **Retrospective Simplification** | What you would remove or redesign today with hindsight |

### Rapid Pre-Call Technical Check

- Audit the company's public engineering blog, open-source repositories, API docs, or release notes prior to the call.
- Map each core JD requirement to 1 concrete story so zero behavioral answers rely on vague generalizations.

## 3. Reverse-Interview Diagnostic Questions

Reserve `3-4` high-signal questions to evaluate engineering health and role reality before committing:

1. **Delivery & Verification:** *"How does a non-trivial schema or API change get verified from PR to production, and what breaks most often today?"*
2. **Ownership & On-Call:** *"How is incident ownership divided between product teams and platform/infra engineers, and what was your last meaningful postmortem change?"*
3. **Spec & Decision Culture:** *"When engineers disagree on an architecture tradeoff here, how is the decision recorded and revisited 6 months later?"*
4. **90-Day Success Signal:** *"What measurable technical or product outcome in the first 90 days separates a good hire from a clear win?"*

## 4. Offer Comparison & Negotiation Playbook

When evaluating one or more offers (full-time or long-term contract/retainer), normalize commercial and execution dimensions side by side before counter-offering:

| Dimension | Weight | Offer A | Offer B | Candidate Floor / Target |
|---|---:|---|---|---|
| Guaranteed Cash / Effective Hourly Rate | 35% | Base / Rate x Guaranteed Hours | Base / Rate x Guaranteed Hours | Explicit candidate floor |
| Variable Bonus / Equity (Risk-Adjusted) | 15% | Liquidity horizon & dilution check | Liquidity horizon & dilution check | Discount illiquid private paper conservatively |
| Scope, Autonomy & Title Trajectory | 25% | Core ownership & decision authority | Core ownership & decision authority | High technical leverage |
| Sustainable Schedule & Async Fit | 15% | Overlap load, on-call, travel % | Overlap load, on-call, travel % | Protected deep-work blocks |
| Stability & Runway / Client Solvency | 10% | Funding runway or verified profit | Client payment history & contract length | Low payment risk |

### Negotiation Checklist

1. **Anchor on Value & Total Package:** Negotiate base/rate, sign-on bonus, milestone schedule, paid PTO/notice period, or equipment/conference budget as one coherent trade.
2. **Cite Grounded Leverage:** Point to specific scope expansion requested in interviews (e.g., owning security/compliance or multi-region rollout) or competing confirmed offers without bluffing.
3. **Confirm Written Final Terms:** Verify IP assignment clauses, non-compete scope, payment net terms (`Net-15` / `Net-30` for contracts), and start date in writing before closing competing threads.
