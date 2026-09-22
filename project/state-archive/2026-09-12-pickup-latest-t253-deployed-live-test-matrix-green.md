<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ## ⭐ PICK UP HERE — 2026-09-12 (LATEST) — **T253 deployed live; test matrix green (skills + stage2-schema fixed); next:  -->

<details><summary>Previous pickup block (2026-09-12) — superseded, kept for trace</summary>

## ⭐ PICK UP HERE — 2026-09-12 (LATEST) — **T253 deployed live; test matrix green (skills + stage2-schema fixed); next: advance Client Alfa via T117 RBAC / Stage 2 proposal UI.**

**What closed this session (all committed and verified, working tree clean):**

**T253 (Visitor Chat Session Claim on Signup)** — DONE & DEPLOYED (release `2026.09.12-1789246682`, commit `526df17`). Full SDLC lifecycle completed: start → spec → build → review → security → verify → deploy → archive. Edge function `client-register` verifies `session_id` UUID format and claims chats. `openspec/archive/2026-09-12-chat-session-claim/` archived, synced to GitHub #256. CHANGELOG recorded (`59a43bc`), CP dashboard updated (`03ef79ca`). TASKS.md 6/6 ACs ✅.

**Test Matrix Gaps Resolved (Blocking + Advisory)**:
1. `skills` suite (`just skill-test`): Synced 23 canonical skills from `wom7skills` to active agent directories, relocked `.w0m/skills.lock.json`, verified 148/148 passing (commit `fa4153ad`).
2. `stage2-schema` (`just stage2-schema-check`): Updated `scripts/stage2_schema_check.py` to assert anon access is 0 for internal projects while matching public projects, verified 35/35 passing, committed to `wom7api` (`ea0a23c`). Full matrix `just test` confirmed: 2,454 checks across 140 suites, all blocking suites passed.

**T346 (Corporate Verification & MX Registry Requester)** — DONE, commit `01be36ae`. Admin CP surface at `/business/verification`, backend dispatcher at `/api/admin/corporate-verify`. Covers INEGI DENUE, SAT RFC + EFOS blacklist, SAT Constancia QR (SSRF-guarded), CompraNet. Vitest suite (21/21) + Python suite registered as `just corporate-verify-test`. Spec at `openspec/specs/corporate_verification_requester.md`. TASKS.md marked ✅.

**T348 (Project Types Taxonomy & @mob Indie Mobile Apps Onboarding)** — DONE, commit `14aad1f9`. 5 delivery types in `apps/cp/src/lib/project-types.ts`. Admin CP `ProjectManager.svelte` gained toolbar filter + modal selector + badges. 1-click Indie Role Provisioning added. `@wom/mob` symlink + `solar`/`mantrabox`/`mantrabox-flutter` declared in `clients-policy.json`. Python suite 35/35. TASKS.md marked ✅.

**T345 (w0m-prs dev tool)** — code committed `2d0e0ca4` (+ root justfile forwarder `06a5a89` in `@wom`), ticket still `queued`/0 of 6 ACs. The CLI (`search`/`audit`/`watch`/`report`) exists and is wired to `just prs`.

**T350 (own BugReportWidget)** — DONE, 7/7 ACs, commit `87c87445` (+ migration `fc206e85`). The
`design-system/components/domain/BugReportWidget.{jsx,d.ts,prompt.md}` files a different
agent/process had left untracked are now owned end-to-end: `public.bug_reports` migration applied
live, `/api/bug-report` SSR endpoint (9/9 tests), best-effort Telegram dispatch, Svelte port in
`packages/ui` wired into both `AdminLayout.astro` and `ClientLayout.astro`. ⚠️ **Correction**: an
earlier draft of this pickup block called these files "not committed — needs an owner call" and
recommended filing a *new* T350 for Mercado Pago/SPEI — both stale. T350 was already used for this
ticket; the Mercado Pago/SPEI work below is **T351**.

**T351 (Mercado Pago + SPEI/CLABE transfers, §34 Client Beta)** — filed, `queued`, 7 ACs, ticket
`project/tickets/T351.md`. Not started.

**Client Alfa Status (ROADMAP §33 — Stages 0–3)**:
- **Stage 0 (Safety Floor)**: ✅ MET (0 cross-tenant rows visible to client actor).
- **Stage 1 (Register & See)**: 🟢 96% complete. Registration chain live front-to-back; T253 chat claim deployed live. Remaining: T20 AC4 (rolling-summary memory blocked on T7) + end-to-end Playwright registration verification spec.
- **Stage 2 (Proposals & Acceptance)**: 🟡 Schema complete & verified (35/35 in `stage2-schema-check`). Remaining: Proposal review/accept surface in Client Portal + T204 project table decomposition.
- **Stage 3 (Contracts & Delivery Visibility)**: 🟡 Active focus. Primary blocker is **T117** (RBAC review → advanced unified roles, capabilities & offices, 4/10 ACs).

**Recommended Next Actions**:
1. Pick up **T117** via `w0m-sdlc-start T117` to implement unified RBAC / capabilities / offices and complete Stage 3 delivery visibility.
2. Build the Stage 2 Client Proposal review/accept UI surface in CP (`/client/proposals`).
3. Pick up **T351** (Mercado Pago + SPEI transfers) via `w0m-sdlc-start T351` — already filed, not started.

**Found but unclaimed (2026-09-12):** `wom7ext/extension/src/content/bugReporter.ts` — a
standalone content-script bug-report widget (hardcoded to POST to
`https://artemioquierocomer.mx/api/bug-report`), untracked, unwired (no manifest entry, no
imports anywhere), no ticket. Same "dropped by another agent" shape T350 already resolved for the
design-system half — this one is in a different repo and T350 did not cover it. Needs an owner
call: own it under a ticket (T350-style) or discard.

**Stripe status (T290):** `STRIPE_SECRET_KEY` + `STRIPE_PUBLISHABLE_KEY` live in Infisical `beta`. `STRIPE_WEBHOOK_SECRET` still missing.

</details>
