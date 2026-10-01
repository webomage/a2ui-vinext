---
id: AgDR-0012
title: "Orca/ZeroClaw absorption + wom7*/k7* to w0m rebrand — hold for owner decision"
timestamp: 2026-09-11T00:00:00Z
agent: claude-code
model: claude-sonnet-5
trigger: audit
status: proposed
superseded_by:
supersedes:
ticket:
---

# AgDR-0012 — Orca/ZeroClaw absorption + estate rebrand: hold for owner decision

## Y-statement

> In the context of three inbound documents proposing (a) retiring the standalone ZeroClaw daemon
> in favor of absorbing its capabilities into Orca, and (b) rebranding all `wom7*`/`k7*` estate
> names to a unified `w0m-*` taxonomy, facing direct overlap with the in-progress [[T153]] (which
> is building ZeroClaw as a *managed, bidirectional* w0m runtime — the opposite direction) and
> `wom7open/orca`'s currently ungoverned status, we decided to **record this as a proposed decision
> point and take no ticketing or execution action**, to avoid either committing to a hard-to-reverse
> outward-facing rename or silently reversing T153's in-flight direction without owner sign-off,
> accepting that the proposal sits unactioned until reviewed.

## Context

**Source:** three of six documents from Antigravity session `22fc09aa-07f7-4f3c-8a29-c873e5b5c186`,
dated 2026-09-11, read in full from `_in/`:
- `2026-09-11-analysis-orca-vs-zeroclaw-unification.md`
- `2026-09-11-spec-w0m-fullsize-orca-zeroclaw-and-rebranding-research.md`
- `2026-09-11-strategy-unified-w0m-ecosystem-orca-rebranding.md`

**What they propose, combined:**
1. Deprecate the standalone ZeroClaw Rust daemon; absorb its 4 "gems" (Hermes skill distillation,
   Honcho ToM memory, w0m SDLC gate interception, visual Tart VM control) directly into Orca
   (`wom7open/orca`)'s Electron/TypeScript main process.
2. Rebrand every `wom7*` repo, every `k7*` TUI, and `orca` itself into a unified `w0m-*` naming
   scheme (`w0m-web`, `w0m-api`, `w0m-orca`, a consolidated `w0m` CLI replacing the `k7*` binaries),
   in three phases ending in an optional full monorepo consolidation into `casualuser/w0m`.

**Measured, checked against the live estate before recording this:**
- **[[T153]]** ("ZeroClaw as a managed w0m runtime") is `in-progress`, P1, 1/8 AC, with a real spec
  (`openspec/changes/2026-08-20-zeroclaw-runtime-and-ecosystem-integration`) already under the
  opposite premise: ZeroClaw stays a standalone runtime, bidirectionally integrated with w0m, used
  for sandboxed client-project audits — not retired and absorbed into Orca. Proposal 1 above is not
  additive to T153; it reverses it.
- **`wom7open/orca` is not declared in `.w0m/sdlc.json` → `repos`** — it has no SDLC governance,
  no ticket history, and is outside the `wom7*` set this estate's non-negotiables (AGENTS.md) are
  written against. Absorbing ZeroClaw into it, or renaming it, would be the first governed action
  taken on that repo.
- The rebrand's own blast-radius section (in the spec doc) names GitHub remotes/CI secrets, `.agent`/
  `.claude`/`.opencode` symlinks between `wom7api` and `wom7web`, and `stacks-policy.json` as things
  that break on a naive rename — i.e. it is self-documented as outward-facing and hard to reverse
  cleanly.
- `.w0m/sdlc.json` was **not** re-read line-by-line for this record beyond what earlier verification
  in this session already covered (repos/lifecycle/conventions) — no new config claim is made here
  beyond "`orca` is absent from `repos`", which was directly grepped.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Ticket the rebrand + Orca absorption now as new work | Captures the idea while fresh; owner can triage it in the normal queue | Commits scope before owner review; silently conflicts with in-progress T153's opposite direction; tickets an already-ungoverned repo without first deciding to govern it | Rejected |
| Execute the rename / absorption directly | None that justify skipping review | Hard-to-reverse (GitHub repo renames, CI secrets, symlinks, DB trigger names per the spec's own analysis); zero owner authorization; would reverse T153 mid-flight | Rejected |
| Drop the proposal, discard the documents | Simplest | Loses a substantive architecture analysis; the "7 repos" naming premise is already factually broken (`@wom` became an 8th repo 2026-09-02), which is a real, correct observation worth keeping | Rejected |
| Record as a **proposed** AgDR, take no ticket/execution action, surface the T153 conflict explicitly | Preserves the analysis git-durably; makes the conflict with T153 visible to whoever next opens either; forecloses nothing | Proposal sits idle until the owner reviews it | **Adopted** |

## Decision

Record this as a `status: proposed` AgDR — a decision point, not a decision. No ticket is filed,
no repo is renamed, no code is written toward absorbing ZeroClaw into Orca, and `wom7open/orca` is
not added to `.w0m/sdlc.json` governance as a side effect of this record. The three source documents
are moved from the ephemeral (gitignored) `_in/` tray into `docs/reports/` so their content is
git-durable, cited from here rather than left as untracked inbox items.

If the owner accepts direction 1 (absorb ZeroClaw into Orca), **T153's spec and status notes need
real reconciliation**, not a supersession note alone — its 1 already-done AC and its
bidirectional-integration design would need to be re-evaluated against "ZeroClaw retired" rather
than assumed compatible.

If the owner accepts direction 2 (rebrand), the first ticket should scope **Phase 1 only** (logical
aliases in `.w0m/sdlc.json`, no renames) per the source strategy doc's own phased plan — not the
full three-phase execution in one ticket.

Either direction, or neither, may be chosen independently — they are coupled in the source
documents but are not logically dependent on each other.

## Consequences

**Positive:** the architecture research survives in a durable, reviewable location instead of an
ephemeral inbox file; the T153 conflict is explicit rather than discovered later as duplicated or
contradictory work; no irreversible action (rename, retirement) was taken without the person who
owns that call.

**Negative:** the proposal produces no forward progress until the owner reviews it — three
substantial documents' worth of analysis sits as a recorded option rather than active work; if the
owner does want to proceed, the reconciliation work against T153 is real, non-trivial follow-up
that this record does not do.

## What this does NOT decide

Whether ZeroClaw is retired or kept as a standalone runtime; whether any `wom7*`/`k7*`/`orca` repo
or tool is renamed; whether `wom7open/orca` becomes an SDLC-governed repo; whether T153's spec or
scope changes. This record does not modify T153 itself (a one-line cross-reference is added to its
Status notes pointing here, nothing else).
