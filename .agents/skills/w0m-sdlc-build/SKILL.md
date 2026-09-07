---
name: w0m-sdlc-build
description: >
  Implementation gate of the w0m SDLC lifecycle (start→spec→build→review→security→verify→deploy→
  archive). Trigger after w0m-sdlc-spec, or "implement T37", "build this change". Implements the
  spec test-first (TDD), keeping the change tightly scoped and traceable to requirements, then
  routes to review. Project-agnostic via `.w0m/sdlc.json`.
metadata:
  author: w0m
  namespace: w0m-sdlc
  gate: build
  version: "2026.08.04-1785835505"
---

# w0m-sdlc-build — the implementation gate

Implement the spec **test-first**, in the smallest coherent diff that satisfies the requirements.
Every change traces to a requirement; nothing extra rides along.

## Step 0 — Load config
Read `.w0m/sdlc.json`. Use `commands` (test/typecheck/lint), `repos`, `specs`, `codegraph`,
`secrets.run`, `conventions`.

## Steps
1. **Orient.** Load the ticket + spec (from the ticket's `spec:`). Map the requirement→criterion
   list to the files/symbols to touch — **`just ask` first, Grep only when the graph misses**
   (T163); query by symbol name, not prose, because the query tokenizes on filler words. Confirm
   the blast radius matches the Start Brief; if it grew, note why.
   ⚠️ **Do not re-Read a file you have already edited to "check" it.** Measured over 317 sessions,
   *stale (edit after read)* is **1,139 calls / ~1,524K tokens = 46.7% of all Read bytes** — the
   single largest source of wasted context in this estate. Edit/Write error on failure; the harness
   already tracks file state.
2. **Red — write failing tests first.** For each requirement/acceptance scenario, add a test that
   fails for the right reason. Use the project's test runner (`commands.test`). Invoke the
   `test-driven-development` skill for the loop discipline. Run tests via `secrets.run` if they
   need env.
3. **Green — implement.** Write the minimum code to pass, matching surrounding style, naming, and
   the domain lexicon. Keep edits scoped to the change; don't refactor unrelated code.
4. **Refactor.** Clean up while green. Run `commands.lint` + `commands.typecheck` and fix what you
   introduced (don't inherit pre-existing failures silently — note them as tech-debt instead).
5. **Trace + commit.** Confirm each requirement now has a passing test. Commit in coherent
   increments, id referenced (`feat(T37): <what>`), per `conventions`. Keep the ticket
   in-progress; update `## Status notes` with what landed.

## Conventions
From config `conventions`: conventional commits w/ id, never skip hooks, no coauthor trailer, tool
ladder MCP>CLI>Python>TS>bash (no complex multiline bash). Absolute dates.

## Next gate
`w0m-sdlc-review`. Hand off the diff range + the requirement→test map.
