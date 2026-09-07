---
name: w0m-tdd
description: Execute a strict Test-Driven Development (Red-Green-Refactor) loop. Use when the user mentions "/w0m:tdd", "test driven development", or wants to build a feature test-first.
metadata:
  version: "2026.07.27-1785131185"
---

# /w0m:tdd (Test-Driven Development)

You are enforcing strict TDD for the Webomage (`w0m`) ecosystem. 

## The Rules
1. **Vertical Slicing Only**: Write ONE failing test, then ONE implementation to make it pass. Repeat. NEVER write all tests first (horizontal slicing).
2. **Behavior over Implementation**: Test what the system *does* via its public interfaces, not *how* it does it. Private methods should not be tested directly.
3. **No Mocking Internal Modules**: Mock at system boundaries (e.g., third-party APIs, DB adapters). Never mock your own modules.

## Workflow
1. **RED**: Write a failing test for a single piece of behavior. 
2. **Commit (Red)**: Commit the failing test (`test: failing test for X`).
3. **GREEN**: Write the *simplest* code to make the test pass. Run the test suite.
4. **Commit (Green)**: Commit the passing code (`feat: implement X`).
5. **REFACTOR**: Clean up duplication, simplify complex conditionals, or improve naming. Run the test suite again to ensure it remains green.
6. **Commit (Refactor)**: Commit the cleanup (`refactor: clean up X`).

## Integration with `/w0m:build`
If `/w0m:build` asks you to implement a task test-first, you will execute this exact loop for each sub-task.
