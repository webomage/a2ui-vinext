# User stories vs Gauge UI tests vs Jam walkthroughs — coverage measured 2026-09-26

**Ticket:** [[T466]] · **Sources:** `wom7web/docs/manuals/CLIENT-MANUAL.md` (21 stories), `wom7web/docs/flows/multi-role-user-stories.md`
(15 stories), `wom7web/specs/` (104 UI specs; `gauge_specs_dir = specs`), Jam team workspace (12 Jams, 2 folders).

## Headline

| Layer | State |
|---|---|
| Story → UI spec link | **None exists.** No story carries an id; no spec names the story it proves. Mapping below is by title and reading, not by a recorded link. |
| Stories with a plausible UI spec | 11 of 21 client-manual stories fully, 4 partially, 6 none. Multi-role: the 6 target-model stories (AgDR-0027/0028) are unbuilt, so untestable yet; of the 9 guild stories, 3 have specs. |
| Specs actually run | Only a smoke spec runs inside `just deploy` (1 spec, 1-2 scenarios). The rest run only when someone calls `just e2e`; pass/fail today is unmeasured. |
| Jam walkthroughs of w0m's own guides | **0.** All 12 Jams are client proof videos (BridgeRoad, artemio), recorded with the Jam CLI (`native_cli`), so CLI recording works on this machine. |
| Duplicate spec tree | `apps/cp/specs/` is a tracked stale copy of `specs/` (173 files, 15 differ or are missing): two sources of truth. |

## Client manual (21)

| # | Story (short) | UI spec(s) | Coverage |
|---|---|---|---|
| C1 | Describe project to AI chat consultant | `web/chat_page`, `web/agent_ui_integration` | yes |
| C2 | Structured form instead of chat | `web/contact_form`, `web/public_contact_thanks` | yes |
| C3 | Offered an account only after a real record | `web/client_registration_handoff` | yes |
| C4 | Exactly one onboarding email on retry | `web/client_registration_handoff` (single-send not asserted) | partial |
| C5 | Magic link or Google/LinkedIn/GitHub sign-in | `web/client_magic_link_portal`, `web/auth_flow` (OAuth providers not driven) | partial |
| C6 | One panel: proposals, contracts, account | `ui/client_portal`, `web/client_proposal_accept` | yes |
| C7 | Stripe checkout and billing portal | none | **gap** |
| C8 | Apply without an account | `web/cross_portal_onboarding`, `live/live_join_*` | yes |
| C9 | Resume parsed automatically | `ui/088-resume-parser-ui` | yes |
| C10 | Sign in later with the apply email | `web/cross_portal_onboarding` | partial |
| C11 | Wallet/XP panel from the moment of applying | none | **gap** |
| C12 | Auto-graded skill challenge | none (edge fn `grade-challenge` has no UI spec) | **gap** |
| C13 | Live AI-run interview | `web/candidate_interview`, `web/admin_interview_session` | yes |
| C14 | Clear final decision, invited or not | none | **gap** |
| C15 | Browse aggregated remote listings | `live/live_job_smoke`, `live/live_job_extended`, `job/goldens` | yes |
| C16 | Trainee sees XP accumulate | none | **gap** |
| C17 | Browse and claim bounties | `web/guild_bounty_flow` | yes |
| C18 | Certification enrollments and readiness | none | **gap** |
| C19 | Told plainly when a reward is not live | none | gap (copy check) |
| C20 | No-signup guided demo tour | `demo/demo_client_funnel`, `demo/demo_candidate_funnel` | yes |
| C21 | Demo cannot send real email or move money | demo funnels (side-effect guard not asserted) | partial |

## Multi-role stories (15)

- **Target model (6: platform staff, engagement PM, talent, trainee, buyer, founder claim):** describe AgDR-0027/0028 and T461,
  which are not built yet. Specs follow the build (T458 S4/S6/S7, T461), not before.
- **Guild stories (9):** visitor (covered by C1), client portal (covered by C6), admin governance (`web/admin_*`, 30+
  specs) have UI specs; recruit trial task, gladiator ledger, legioner allocation, manager squads, tribune budget and
  trainer vetting have none.

## What "interactive go-through" needs

1. **Stable story ids** in the guides (`C1`…, `M1`…) and a manifest `story-coverage.json`: id → spec file(s) → Jam URL.
2. **A gate** (`just story-coverage`): every story has a spec or an explicit `planned`/`manual-only` reason; every spec
   named exists; advisory first, blocking once gaps are closed.
3. **Jam walkthroughs recorded from the Gauge run itself** (Jam CLI around the Playwright browser), one Jam per story,
   in a `w0m user guide` folder, linked from the guide next to the story. Recording from the spec keeps the video true
   to the tested flow; hand recordings drift.
4. **Retire `apps/cp/specs/`** (one spec tree).

## Open questions (weighted)

| # | Question | Recommendation | Weight |
|---|---|---|---|
| Q1 | Who can see the Jams? | Team-only by default; public links only for client-facing guides after review | Public links leak internal UI; costs a review step |
| Q2 | Record from Gauge (automated) or by hand? | Automated from Gauge via Jam CLI; hand only for flows needing a real inbox or card | Automated stays current on every release; needs one CLI wrapper |
| Q3 | Which environment? | Beta with the non-real test accounts (T439 AC10); never real client data | Real data in a shared video is a leak |
| Q4 | Drop `apps/cp/specs/`? | Yes, after diffing the 15 differing files into `specs/` | Low cost; removes a dual source of truth |
