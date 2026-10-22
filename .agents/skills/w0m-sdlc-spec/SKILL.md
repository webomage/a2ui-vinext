---
name: w0m-sdlc-spec
description: >
  Design/requirements gate of the w0m SDLC lifecycle (start→spec→build→review→security→verify→
  deploy→archive). Trigger after w0m-sdlc-start, or when a ticket needs a verifiable design before
  coding ("write the spec for T37", "design this change"). Turns a ticket into a verifiable spec,
  validates it against the authoring standard, then routes to build. Project-agnostic via
  `.w0m/sdlc.json`.
metadata:
  author: w0m
  namespace: w0m-sdlc
  gate: spec
  version: "2026.10.22-1792685701"
---

# w0m-sdlc-spec — the design gate

Turn the ticket into a **verifiable design** before any code is written. A spec is done when its
requirements are observable/testable and map to acceptance criteria — not when it "reads well".

## Step 0 — Load config
Read `.w0m/sdlc.json` (discover from cwd up). Use `specs` (system/dir/standard/verify_skill),
`tickets`, `repos`, `conventions`. If `specs.system` is `"none"`, this gate degrades to writing a
short design note in the ticket body instead of a formal spec — say so and proceed.

## Steps
1. **Confirm the ticket + brief.** Load the ticket (per `tickets`). If `w0m-sdlc-start` already
   produced a Start Brief this session, build on it; otherwise run its verify checks first so you
   design against reality, not the stale status.
2. **Author the spec (identify `Testing seams` BEFORE scenarios — T276).** For
   `specs.system:"openspec"`, invoke `openspec-new-change` to scaffold the change under
   `specs.dir`, then write `## ADDED/MODIFIED Requirements` where each requirement is a single
   observable behavior. Follow `specs.standard` (`SPEC-AUTHORING-STANDARD.md`) exactly:
   - **Identify `Testing seams` BEFORE writing `#### Scenario:` blocks** (for all new and modified
     requirements; retrofitting existing/archived specs is out of scope). Every seam must name:
     1. **the observable** — the actual property read (e.g. computed `font-size` of `h1`, not
        *"looks right"*).
     2. **where it is read** — the existing integration point / attachment seam (`prefer existing
        seams` and `minimise new seams` so requirements do not spawn bespoke harnesses nobody runs).
     3. **its failure shape** — answer the mandatory question: *"What does a catastrophic failure
        look like in this measurement, and does it look like a pass?"* If the answer is *"a pass"*
        (e.g. a 16px collapsed `h1` passing a `lines === 1` check in T261), the seam is wrong and
        must be replaced before the scenarios are written.
   - Reuse the domain lexicon — run `tech_debt.lexicon_lint` if present so new entity/vocab names
     don't drift.
3. **Cross-check.** Every ticket acceptance criterion must be covered by ≥1 requirement, and every
   requirement must trace to a criterion. List any gaps and resolve them (edit spec or ticket).
4. **Validate.** Invoke `specs.verify_skill` (e.g. `openspec-verify-change`) — the spec must be
   internally coherent, every new/modified requirement must carry `Testing seams` ordered before its
   `#### Scenario:` blocks with a non-vacuous failure shape, and where code already exists, flag
   spec↔code drift. Do not leave the gate with verify failing.
5. **Single Source of Truth (SSOT) Audit (`schema-critique`).**
   Before freezing the design, audit all proposed data models, API routes, and state machines:
   ensure every column, table, route, and axis answers exactly ONE real-world question with zero
   duplicate mechanisms answering the same question (no dual SSOT). Settle any open design
   tradeoffs with a weighted decision matrix (cost, risk, unblocks, recommendation).
6. **The ticket's Definition of Done must be its OWN — run `just dod-check --ticket <id>`.**
   🔴 This gate is where a DoD is written, and it is the only gate where that is cheap. A DoD
   authored later is composed by reading the outcome and is met by construction.
   The check refuses three states and each means something different:
   · **SHARED** — byte-identical to other tickets. This is the DEFAULT for a new ticket: the
     template is what it starts with. Replacing it IS the work this step requires. Measured
     2026-08-25, **146 tickets** still carried one of two generic process checklists.
   · **STALE** — scope grew past it. Update the DoD in the same commit as the AC.
   · **MISSING** — a ticket with acceptance criteria and no DoD.
   ⚠️ Write what must be observably TRUE for this ticket, in its own domain language — not a
   restatement of the criteria. If it says nothing the checkboxes do not already say, it is not
   earning its place. See `SPEC-AUTHORING-STANDARD.md` -> **Ticket entities**.

6. **Link + track.** Set the ticket `spec:` field to the change dir; note the design decision under
   `## Status notes`. Commit ticket + spec together, id in the message
   (`docs(T37): spec — <change>`), per `conventions`.

## Conventions
From config `conventions`: conventional commits, id referenced, never skip hooks, no coauthor
trailer, tool ladder MCP>CLI>Python>TS>bash. Absolute dates.

## Next gate
`w0m-sdlc-build` (the successor of `spec` in `lifecycle`). Hand off the change name + the
requirement→criterion map.
