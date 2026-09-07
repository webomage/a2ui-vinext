---
name: w0m-sdlc-review
description: >
  Code-review gate of the w0m SDLC lifecycle (start→spec→build→review→security→verify→deploy→
  archive). Trigger after w0m-sdlc-build, or "review my changes for T37". Reviews the working diff
  for correctness bugs and reuse/simplification/efficiency cleanups, verifies findings, applies or
  files them, then routes to security. Project-agnostic via `.w0m/sdlc.json`.
metadata:
  author: w0m
  namespace: w0m-sdlc
  gate: review
  version: "2026.07.27-1785131185"
---

# w0m-sdlc-review — the code-review gate

Catch correctness bugs and quality issues in the change **before** the security and verify gates.
Review the diff, not the whole repo.

## Step 0 — Load config
Read `.w0m/sdlc.json`. Use `repos`, `commands`, `tech_debt`, `conventions`.

## Steps
1. **Scope the diff.** Determine the change range for this ticket across the ticket's `repos`
   (`git -C <repo> diff` vs the base branch / uncommitted). Confirm it matches the intended blast
   radius.
2. **Review.** Invoke the `/code-review` skill (or `torvalds` persona for a ruthless pass) at an
   effort level matched to the change size. Cover: correctness/edge cases, requirement coverage,
   reuse & simplification, efficiency, and adherence to surrounding patterns + the domain lexicon.
3. **Verify each finding.** Don't trust a plausible finding — confirm it against the code (repro
   path or file:line). Drop the ones that don't survive.
4. **Resolve.** For confirmed findings: fix the in-scope ones now (small, safe); file genuinely
   out-of-scope ones as a row in `{tech_debt.register}` (TECH-DEBT.md) — plain markdown, one row
   insert) with a note + ticket link — never let them silently ride along or vanish.
5. **Record.** Summarize what was fixed vs filed under the ticket `## Status notes`. Commit fixes,
   id referenced (`fix(T37): <what>`), per `conventions`.

## Conventions
From config `conventions`: conventional commits w/ id, never skip hooks, no coauthor trailer, tool
ladder. Absolute dates.

## Next gate
`w0m-sdlc-security`. Hand off the reviewed diff + any filed debt ids.
