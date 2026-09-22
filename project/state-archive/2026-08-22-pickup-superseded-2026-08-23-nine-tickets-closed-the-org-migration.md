<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ## ⭐ PICK UP HERE — 2026-08-22 (SUPERSEDED 2026-08-23) — **Nine tickets closed. The org migration is scoped and has THRE -->

## ⭐ PICK UP HERE — 2026-08-22 (SUPERSEDED 2026-08-23) — **Nine tickets closed. The org migration is scoped and has THREE silent breaks that all exit 0. Emoji output is at zero. Two things are filed and unstarted: the layout matrix and the migration itself.**

**Closed today:** [[T248]] · [[T249]] · [[T250]] · [[T251]] · [[T255]] · [[T256]] · [[T258]] ·
[[T260]] · [[T2]]. **[[T257]]** AC1 done, rest open.
**Filed:** [[T252]] [[T253]] [[T254]] (#257) · [[T257]] (#260) · [[T259]] (#262) · [[T260]] ·
**[[T261]]** (layout, unstarted).
**State:** `just test` → **all blocking suites pass**, 1,900 checks / 103 suites. 4 advisory
failures are declared debt (**D53**). `suites-drift` 127/0.
🔴 **Unpushed at time of writing** — `just push-cadence` names the repos. Push first.

**THE ONE THING TO CARRY FORWARD**

Every defect this session was the same shape: **a measurement existed and changed no verdict.**
Nine instances now. The sharpest three:

| | the thing that measured nothing |
|---|---|
| [[T256]] | obeying *"remove emoji from logs"* literally → **126 suites report 0 checks and pass** |
| [[T258]] | a correct generator, a correct table, a correct wrapper, **and no caller** |
| [[T242]] | three migration paths that each **exit 0 while writing to the wrong place** |

⇒ **What is worth gating is almost never the component. It is whether anything invokes it, and
whether the answer changes anything.**

**NEXT, IN ORDER**

1. **Push.** `just push-cadence` names the repos.
2. **[[T261]] — the layout matrix.** Owner gave a `/services` screenshot showing **three distinct
   defects**: side padding eating width (H1 wraps to two lines beside wide empty gutters),
   orphaned last words, and 🔴 **body text CLIPPED by the footer** — unreachable, not merely
   wrapped. ⚠️ Widening the container fixes the first two and **will not** fix the third.
   **Measure first**: 10 viewport/orientation pairs, computed values via `javascript_tool`, not
   eyeballed. Mobile **landscape** is most likely broken and least likely to be checked.
3. **[[T242]] — the org migration.** Read its 2026-08-22 status notes **before touching anything**;
   the three silent breaks are written up there with file:line. Summary of the danger: three
   different board-resolution strategies exist for one board, `OWNER = ACCOUNT` collapses the
   acting identity with the board owner, and `gh_issue` is the sync's idempotency key so
   re-creation must rewrite all 262 in the same change or the mirror edits unrelated issues.
   **First fix, before any migration step:** give the board ONE declared identity in
   `.w0m/sdlc.json` and make all three scripts read it.
   `just org-migrate-plan` is the dry run and mutates nothing. It currently **exits 1** on a real
   blocker: **T16a/T16b/T16c all claim #16** (AC3) — a decision, not something the plan may pick.
4. **[[T257]] — the rest of the emoji work.** `script_output` is at **0**. Remaining: **3,012**
   heading occurrences and the **9 protocol couplings**. 🔴 Reader-first, always: teach each parser
   the text form while it still accepts the glyph, then convert producers, then drop the glyph
   branch. Producers-first is the one order where every intermediate state is green and wrong.
5. **[[T259]]** — today's deploys are in **no** record. `deploy-all` self-wraps; a direct
   `supabase functions deploy` does not.

**EMOJI ARE PROTOCOL HERE — read before "cleaning up" any output**

`project/emoji-policy.json` declares three tiers and the gate **discovers** couplings rather than
trusting the list — because the hand-written list was wrong. A sweep found **45 matcher sites, 18
undeclared, 3 real readers**, including `run_suites.py`'s other **three** dialects (`✓✗×` for four
suites, `ℹ` for node:test). `run_suites` now also accepts a **text** dialect (`[OK]`/`[PASS]`/
`[FAIL]`) — that is [[T257]] step 1 and the only safe first step.
⚠️ **Never raise a ratchet baseline.** The policy carries four dated baseline moves **with their
causes**, because a number that falls from work done and one that falls from better classification
are different events.

**OWNER DECISIONS PENDING — nothing below should be guessed**

- **T16a/T16b/T16c → #16.** Merge them, or renumber two above T260? Blocks `T<n> == #<n>`.
- **Q0: can an ORG board track issues in USER-owned repos?** **Not a documented yes** — the docs
  are ambiguous and the research agent correctly refused to guess. `AddProjectV2ItemByIdInput` has
  no owner/repo argument, which argues *for* it without documenting it. 🔑 Even if items work, the
  **field topology does not**: `repository(casualuser/webomage.com).issueFields` is **`null`**
  because the repo is User-owned, so linking user repos buys **columns but not
  `priority`/`area`/`epic`**. A reversible 2-mutation probe is specified in T242; **not yet run**.
- **Which identity performs each migration step.** Owner said the org is held via a **separate
  admin account**; `casualuser` is only a **member**. `org-migrate-plan` prints the acting identity
  for exactly this reason.
- **Cleanup owed:** `webomage/wom7xfer-probe-DELETEME` (6 issues) and `webomage/w0m-probe-DELETEME`
  (archived) still need deleting — no token here has `delete_repo`.

**TRAPS FOUND TODAY, so nobody re-finds them**

- ⚠️ **Two namespace traps make find-and-replace dangerous.** `api.webomage.com` is *both* the
  wom7api repo name *and* the production API hostname. And the org is literally named `webomage`,
  colliding with the npm scope `@webomage` — **361 lines across 205 files**. Anchor every
  substitution on `casualuser/` or `github.com`, never on `webomage`.
- 🔴 **`TASKS.md` has NO writer** and holds **158 hardcoded
  `github.com/casualuser/webomage.com/issues/N` URLs** that will not regenerate. T242's own line 60
  claims it is generated; it is not. STATUS-DASHBOARD.html also has 2 literals outside AUTOGEN.
- 🔴 **A capability flag that lies:** on an **archived** repo, `viewerCanSetFields=false` —
  correct, and easily misread as *"members cannot set fields"*. Never probe capability on an
  archived target.
- ⚠️ **`plan.seats = 1` while `filled_seats = 2`** — `seats` is not a member cap on the free plan.
- ⚠️ **Branch protection and rulesets are unavailable** for private repos on this plan (403).
- 🔬 **Three wrong-corpus errors in one day**, and they are the session's real lesson: `wom7mlx/`
  looked unversioned (the repo is at **`wom7mlx/wom7mlx`**, exactly where `.w0m/sdlc.json` says);
  `## 🚪 33.` defeated a heading grep; and the first emoji baselines counted generated
  `graphify-out/` as authored text, so the gate **claimed a 754-heading improvement it had not
  earned**. ⇒ *A survey that starts at the wrong root describes a different system accurately.*
- ⚠️ **A parse failure can degrade into believable information.** `org-migrate-plan`'s JSONC reader
  could not handle trailing commas, so it printed *"PRIORITY MAP MISSING — the plan cannot project
  priority"* — which is a **real state** until the tracker is org-owned. Worse than a crash.
- ⚠️ **Ruling out four wrong causes does not make the fifth guess right** ([[T260]]). One
  instrumented run beat a four-row table of eliminated hypotheses.
- 📌 **`git worktree add --detach <path> HEAD`** is the cheap way to prove a failure predates your
  work. That is how T260 was established as pre-existing rather than argued about.
- 📌 **TASKS.md is over its declared bounds** (590 KB / 405 lines vs 409 KB / 400). `tasks-bounds`
  reports rather than fails, by design — rotation is a deliberate act with a disposition record.

**IN-FLIGHT WORK TO RESUME, not restart**

The org-migration scoping workflow completed **5 of 8** agents; `refute:coupling`,
`refute:data-loss` and `design:migration-plan` died on a usage limit. So **the coupling inventory
in T242 is unrefuted and there is no synthesised stage plan yet.** Resume with cached replay:

```
Workflow({scriptPath: '/Users/proto/.claude/projects/-Users-proto-Projects--self--wom/35b31254-3f4d-4481-bc20-c1926904a4ab/workflows/scripts/org-migration-scope-wf_2abf29ab-016.js', resumeFromRunId: 'wf_2abf29ab-016'})
```

---
