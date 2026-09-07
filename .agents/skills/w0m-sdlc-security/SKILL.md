---
name: w0m-sdlc-security
description: >
  Security-review gate of the w0m SDLC lifecycle (start→spec→build→review→security→verify→deploy→
  archive). Trigger after w0m-sdlc-review, or "security review for T37". Runs the project's security
  quality gates + a targeted security review of the change (authz/secrets/injection/RLS), verifies
  findings, then routes to verify. Project-agnostic via `.w0m/sdlc.json`.
metadata:
  author: w0m
  namespace: w0m-sdlc
  gate: security
  version: "2026.07.27-1785131185"
---

# w0m-sdlc-security — the security-review gate

Prove the change doesn't open a hole. Combine the automated gates with a human-grade review of
the change's security-sensitive surface.

## Step 0 — Load config
Read `.w0m/sdlc.json`. Use `quality_gates` (required + security_review_skill), `commands`, `repos`,
`secrets.run`, `tech_debt`, `conventions`.

## Steps
1. **Run the required gates.** For each check in `quality_gates.required` (e.g. gitleaks, semgrep,
   osv, type-gate), run it over the change (these usually already run in pre-commit — run them
   explicitly here too, e.g. `pre-commit run --all-files` or the individual tools). Record
   pass/fail; a fail blocks the gate.
2. **Targeted review.** Invoke `quality_gates.security_review_skill` (e.g. `security-guardrails`)
   or `/security-review` on the diff. Focus on: authn/authz & role checks (RLS/active-hat where
   applicable), secret handling (nothing hardcoded — the `sbp_`/DB-password rules exist for a
   reason), input validation & injection, SSRF/open-redirect, and unsafe defaults.
3. **DB/RLS check** (if the change touches data) — confirm new tables/columns have policies and
   the change doesn't widen access. Read-only introspection via Supabase MCP or `{secrets.run}
   psql`.
4. **Verify + resolve.** Confirm each finding is real (repro/file:line). Fix in-scope issues now;
   file out-of-scope ones as a row in `{tech_debt.register}` (TECH-DEBT.md) under Security, with a ticket link. Nothing
   unresolved-and-forgotten.
5. **Record.** Summarize gate results + findings under the ticket `## Status notes`. Commit fixes,
   id referenced (`fix(T37): <security fix>`), per `conventions`.

## Conventions
From config `conventions`: conventional commits w/ id, never skip hooks, no coauthor trailer, tool
ladder. Credentials are never handled by the agent — flag rotation to the owner. Absolute dates.

## Next gate
`w0m-sdlc-verify`. Hand off gate results + any filed security debt.
