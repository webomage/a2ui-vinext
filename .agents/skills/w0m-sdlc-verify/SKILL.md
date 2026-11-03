---
name: w0m-sdlc-verify
description: >
  Proof gate of the w0m SDLC lifecycle (start→spec→build→review→security→verify→deploy→archive).
  Trigger after w0m-sdlc-security, or "verify T37 works". Proves the change does what the spec says
  by running tests/typecheck/e2e AND driving the affected flow end-to-end, then routes to deploy.
  Project-agnostic via `.w0m/sdlc.json`.
metadata:
  author: w0m
  namespace: w0m-sdlc
  gate: verify
  version: "2026.11.02-1793666924"
---

# w0m-sdlc-verify — the proof gate

Don't take "tests pass" as proof the *feature* works. Exercise the real flow and observe the
behavior the spec promised.

## Step 0 — Load config
Read `.w0m/sdlc.json`. Use `commands` (test/typecheck/e2e/build), `specs`, `secrets.run`, `repos`,
`conventions`.

## Steps
1. **Automated suite.** Run `commands.test`, `commands.typecheck`, and (if the change has UI/flow
   surface) `commands.e2e` — via `secrets.run` when env is needed. All must be green for the code
   you touched. Pre-existing unrelated failures: note them, don't let them mask new ones.
2. **Spec verification.** If `specs.system` is set and the ticket has a `spec`, invoke
   `specs.verify_skill` (e.g. `openspec-verify-change`) — implementation must now match the spec
   (this is the drift-gate the lifecycle is built to enforce).
3. **Drive it end-to-end & prove zero unused/unwired parts.** Invoke the `verify` skill (or the project's run/preview flow) to
   actually exercise the changed behavior — hit the endpoint, click the flow, run the command —
   and observe the promised outcome. Verify zero unused/unwired surfaces remain (no dead UI controls, no `.from(...)` or `.upsert({...})` calls to non-existent SQL relations/columns per `supabase_surface_drift_check.py`, no synthetic `200 OK` placeholder fallbacks on missing resources, and live append-only `*_audit_log` triggers on mutable security/privacy/commercial settings). Tests + typecheck alone are not sufficient for a change with
   a runtime surface.
4. **Map to acceptance.** Mark each acceptance criterion ✅ met with the evidence (test name, e2e
   run, screenshot/output). Any 🟡/⚪ sends the work back to `w0m-sdlc-build`.
5. **Record.** Put the verification evidence under the ticket `## Status notes`. Commit any test
   additions, id referenced (`test(T37): <what>`), per `conventions`.

## Conventions
From config `conventions`: conventional commits w/ id, never skip hooks, no coauthor trailer, tool
ladder. Report results faithfully — if something failed or was skipped, say so. Absolute dates.

## Next gate
`w0m-sdlc-deploy` (only if all criteria are ✅; otherwise back to `w0m-sdlc-build`). **Agent human-gate rule (T613):** When `commands.deploy` / `db-migrate` is human-gated (`docs/DEPLOY-CONFIRM.md`), never stop after `verify` — immediately run `w0m-sdlc-archive` + full Session Wrap-Up (`status: done`, `LESSONS.md` + `lessons_check.py`, repo-first `.agents/reports/`, `just agent-tree-land`, live `--ff-only`, `just agent-tree-remove`) BEFORE handing the human deploy command to the operator.
