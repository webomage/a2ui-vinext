---
name: w0m-sdlc-deploy
description: >
  Delivery gate of the w0m SDLC lifecycle (start→spec→build→review→security→verify→deploy→archive).
  Trigger after w0m-sdlc-verify, or "deploy T37". Ships the verified change using the project's
  deploy command, confirms it live (health/version), records the release, then routes to archive.
  Project-agnostic via `.w0m/sdlc.json`. Deploy is outward-facing — confirm before shipping.
metadata:
  author: w0m
  namespace: w0m-sdlc
  gate: deploy
  version: "2026.07.27-1785131185"
---

# w0m-sdlc-deploy — the delivery gate

Ship the verified change and **prove it's live**. Deployment is hard to reverse and outward-facing:
confirm with the user before running the deploy command.

## Step 0 — Load config
Read `.w0m/sdlc.json`. Use `commands.deploy`, `commands.build`, `vcs` (default_branch), `repos`,
`secrets.run`, `tickets.sync`, `conventions`.

## Steps
1. **Pre-flight.** Confirm the verify gate passed (all acceptance ✅). Confirm the working tree is
   committed and on `vcs.default_branch`, pushed. Check any known deploy prerequisites for the
   project (e.g. secrets manager session valid, migrations ready). **Get explicit user go-ahead.**
2. **Build (if separate).** Run `commands.build` if the deploy doesn't build internally; fix any
   failure before shipping.
3. **Deploy.** Run `commands.deploy` (e.g. `just deploy-all`). Watch for the documented pipeline
   gotchas the project records (lockfile rewrites, account/session flips, transient 502s → retry).
   Never bypass safety checks to force a deploy.
4. **Confirm live.** Verify the deployed surface reports the new version — hit `/health` or the
   version endpoint; check the deploy log / CHANGELOG entry exists. A deploy isn't done until
   observed live.
5. **Record.** Note the release (commit, version, timestamp) under the ticket `## Status notes`.
   If github-mirrored, reference the issue on the release. Commit any release metadata, id
   referenced, per `conventions`.

## Conventions
From config `conventions`: conventional commits w/ id, never skip hooks, no coauthor trailer, tool
ladder. Outward-facing action → confirm first. Report the real outcome (version live or not).
Absolute dates.

## Next gate
`w0m-sdlc-archive`. Hand off the release info.
