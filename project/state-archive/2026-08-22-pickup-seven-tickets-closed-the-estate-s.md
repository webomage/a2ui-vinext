<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### ⭐ (was) PICK UP HERE — 2026-08-22 — **Seven tickets closed. The estate's own instruction to remove emoji would have  -->

### ⭐ (was) PICK UP HERE — 2026-08-22 — **Seven tickets closed. The estate's own instruction to remove emoji would have made all 126 suites pass while measuring nothing — and the changelog had been six weeks stale behind machinery that worked perfectly.**

**Closed:** [[T248]] 6/6 · [[T249]] 6/6 · [[T250]] 5/5 · [[T251]] 6/6 · [[T255]] 5/5 · [[T256]] 7/7 ·
[[T258]] 5/5 · [[T2]] → done.
**Filed:** [[T252]] [[T253]] [[T254]] (#257) · [[T257]] (#260) · [[T259]] (#262) · [[T260]].
🔴 **Unpushed at the time of writing — `just push-cadence` says so.** Push both repos first.

**THE ONE THING TO CARRY FORWARD**

**Every defect this session was the same defect: a measurement existed and changed no verdict.**
Seven instances, and the last one is the sharpest:

| ticket | the thing that measured nothing |
|---|---|
| [[T248]] | `just db-migrate` applied nothing and reported success |
| [[T250]] | a TASKS row claimed a status nothing compared to the ticket |
| [[T255]] | a **ticked** AC cited `just suites` — not a recipe. Mine, written the day before |
| [[T256]] | obeying *"remove emoji from logs"* literally → **126 suites report 0 checks and pass** |
| [[T258]] | a correct generator, a correct table, a correct wrapper, **and no caller** |
| [[T260]] | a blocking suite red since before today, invisible because nothing ran the aggregate |

⇒ **The thing worth gating is almost never the component. It is whether anything invokes it, and
whether the answer changes anything.**

**EMOJI ARE PROTOCOL HERE, NOT DECORATION — read this before "cleaning up" any output**

Owner instruction 2026-08-22: prohibit emoji in logs/reports, use `.md`/`.mmd` by default, add gates.
It was earned the same day — a grep for `ROADMAP` section 33 returned **no match** because the
heading read `## <pictograph> 33.`, and I concluded [[T254]]'s epic did not exist. It does; seven
tickets cite it correctly.

🔴 **But SEVEN parsers read emoji as values**, and `run_suites.py:44` counts every probe's pass/fail
by matching them. Convert producers before readers and the whole aggregate goes green measuring
nothing. So `project/emoji-policy.json` declares three tiers:

- **HARD** — governance-doc headings, zero. 61 cleaned; all 33 ROADMAP sections still resolve.
- **PROTOCOL** — 7 declared couplings, **asserted and printed every run**. The 7th (`state_doctor.py`
  reads `⭐` for `PICK UP HERE` — this very heading) was found *after* the first six, so treat the
  list as discovered, not complete.
- **RATCHET** — 3,451 headings + 223 decorative output lines. **Never raise a baseline.**

**`just run_suites` now accepts a TEXT dialect (`[OK]`/`[PASS]`/`[FAIL]`) alongside the glyphs** —
that is step 1 of [[T257]], and the only safe first step.

**NEXT, IN ORDER**

1. **Push.** Two repos, `just push-cadence` names them.
2. **[[T260]]** — `sync-tickets` is red and blocking, so `just test` exits 1 on every run. Until it
   is fixed the aggregate is a gate people will learn to skip.
3. **[[T254]]** — the device-identity parent. Its review addendum
   (`docs/reports/DEVICE_IDENTITY_REVIEW_ADDENDUM_2026-08-22.md`, A1–A8) reorders the phases:
   **decide → hardened cookie → proof-of-possession → replay+quota → fingerprint SHADOW ONLY**.
   ⚠️ Two of its gates do not exist yet (`quota-failclosed-check`, `fingerprint-entropy`) and
   `just ac-recipe-check` now reports that rather than letting it pass on a code read.
4. **[[T259]]** — today's two deploys are in **no** record. `deploy-all` self-wraps; a direct
   `supabase functions deploy` does not.

**TRAPS FOUND TODAY, so nobody re-finds them**

- 🔬 **Three wrong-corpus errors in one day.** `wom7mlx/` looked unversioned (it is at
  **`wom7mlx/wom7mlx`**, exactly where `.w0m/sdlc.json → repos.mlx` says); `## 🚪 33.` defeated a
  heading grep; and the first emoji baselines counted generated `graphify-out/` reports as authored
  text, so the gate **congratulated itself on a 754-heading improvement it had not earned.**
  ⇒ *A survey that starts at the wrong root describes a different system accurately.*
- ⚠️ **A ratchet must not count the protocol it protects.** Writing [[T256]]'s probe raised the number
  that probe measures (801 → 805), because probes print the glyphs the runner parses.
- ⚠️ **`spec-standard-check` wants `**Acceptance criteria**:` and `**Verify with**:` with the colon
  OUTSIDE the bold, but `**Feature:**` with it INSIDE.** The standard's own example file uses the
  rejected form, which is likely part of why 92 requirements are non-conforming.
- ⚠️ **`git worktree add --detach <path> HEAD`** is the cheap way to prove a failure predates your
  work. That is how [[T260]] was established as pre-existing rather than argued about.
- 📌 **TASKS.md is over its declared bounds** (590 KB / 405 lines vs 409 KB / 400). `just tasks-bounds`
  reports rather than fails, by design — rotation is a deliberate act with a disposition record.

---
