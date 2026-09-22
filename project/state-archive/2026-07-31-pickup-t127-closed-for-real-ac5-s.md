<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### ⭐ (was) PICK UP HERE — 2026-07-31 — **T127 CLOSED for real (AC5's resolver only ever worked from wom7web); TWO canon -->

<details><summary>Previous pickup block (2026-07-31, earlier session) — superseded, kept for trace</summary>

### ⭐ (was) PICK UP HERE — 2026-07-31 — **T127 CLOSED for real (AC5's resolver only ever worked from wom7web); TWO canonical skills were verbatim upstream copies mislabelled `w0m-native`; the vendoring sweep T128 deferred is DONE (16 skills / 140 dangling links); T155 filed for the Upwork corpus. Next: owner decision on T50, then T154 (P0) or T151 AC2.**

> **Written for an agent with none of my context. Everything below was measured this session, 2026-07-31.**
>
> ### 📍 STATE — pushed through `2d308b2`/`1cbc5288`/`5e86a38`; 4 wom7web commits after that are LOCAL
> Pushed earlier: `wom7skills 2d308b2` · `wom7web 1cbc5288` · `wom7api 5e86a38`.
> **Unpushed (wom7web):** `2232f172` `3bdad134` `cd6de7e1` (T155 create + gh backfill + index resync) and this STATE/ROADMAP commit.
>
> ### ✅ WHAT LANDED
> 1. **T127 AC5 — `just skill match` only ever worked from `wom7web`.** It hardcoded
>    `<target>/project/stacks-policy.json`, which is the per-project model; T130's registry is
>    **estate-wide**. Now resolved like `discovery.py` (`.w0m/sdlc.json → stacks.policy`, relative to
>    the **config's** repo, found by walk-up-then-one-level-down). Running it estate-wide then exposed
>    a **third vacuous-green** — `wom7ext` reported a clean match off **0** detected techs — now exit 2.
>    Tests 90 → 94. `cloudflare-workers` installed (audit → declare → sync → **`relock-all`**, not
>    `relock`; that doc bug is fixed in `wom7skills/CLAUDE.md`).
> 2. **🔴 PROVENANCE: two `w0m-native` skills were verbatim `addyosmani/agent-skills`.**
>    `doubt-driven-development` (**1.000** body match) and `observability-instrumentation` (**0.994**,
>    now renamed to upstream's `observability-and-instrumentation`). Third-highest across the corpus is
>    **0.061**, so nothing else is close — the personas, `cloudflare-workers` and `rbac-auditor` are
>    provably ours. **T131 AC3 wrote this trap** (*"do not stamp blind"*) then cleared the 13 unknowns on
>    **headings and a commit message** — both artefacts of the import — instead of a byte diff. Cost:
>    w0m stamps on upstream bytes, and **461 lines of `references/` never vendored**. Fixed, `NOTICE.md`
>    added, `version.ts` now gates both (tests 96, each red first).
> 3. **T128 AC8 — the vendoring sweep is DONE**, and "at least two" was a large understatement:
>    **16 of 74 installed skills / 140 dangling companion links** (class A) + **11 short of upstream**
>    (class B). Worst: `playwright-best-practices` ships **1 of 59 files, all 58 links dead**. Tool:
>    **`just skills-vendor-audit`** (`--upstream` for class B). Tests 103.
> 4. **T155 filed** (GH #152) — the Upwork corpus is an **index, not a record**: `contracts` 189 rows but
>    **~94 real** (89 duplicate groups), `proposals` 539 with **no cover-letter body**,
>    `platform_messages` **129 in 10 of 50 rooms** dated **2026-02→06 only** against a history from **2012**.
>    T89 closed on those exact numbers because it verified *idempotency*, which a 5% sample passes.
>
> ### 🔴 VERIFIED THIS SESSION — two ranker/ticket truths worth acting on
> - **T125 reads 100% and is NOT.** `tasks_query.py:145-146` matches only `- [x] **AC` and `- [ ] **AC`,
>   so the `[N/A]` (AC4) and `[~]` (AC5) markers vanish from **numerator AND denominator**. Real state:
>   **4 of 5 applicable, with AC5 hard-blocked** — `cloudflare/versions.tf:11-20` has `backend "remote"`
>   **commented out**, so git is the ONLY durable copy of state for 24 live CF resources (**12** tfstate
>   files tracked; 0 provider binaries — all three claims re-verified). Untracking before the backend is
>   enabled loses the config↔production DNS mapping. **Fix the ranker, not the ticket.**
> - **T150 reads 7/12 and is really ~9/12.** AC3 and AC3b are **satisfied but unticked**: `--dry-run`
>   and `--all` both exist (`sync_github.py:63-64`), the index decides the work set (live proof from this
>   session: TASKS.md changed and the run reported **`created=1 updated=0 skipped=150`**), and the mirror
>   **stays** in `.husky/pre-push:153` which is what rewritten-AC3b asks for. AC1/AC2/AC2b/AC3c/AC4/AC6
>   all verified in code (`find_issue` is *gone*, not merely guarded; `reconcile_labels` returns add+remove;
>   truncated issue-list **refuses to sync**; `return 1 if failed else 0`). Genuinely open: **AC7** (MCP
>   boundary in `.w0m/sdlc.json`), **AC8**, **AC9** — and AC8/AC9 are research sequenced behind T144/T21.
>
> ### ▶ NEXT
> 1. **Owner decision on [[T50]]** — stale on both halves of its premise (targets the script T89 retired;
>    cites a *20 room* cap when the live ceiling is **50**). Recommend folding its pagination half into
>    T155 AC1, keeping T50 for the unrelated `searchJobs()` CLI half.
> 2. **Tick T150 AC3 + AC3b** (evidence above) — then it is 9/12 and AC7 is a small config edit.
> 3. **Fix `tasks_query.py`** to count `[N/A]`/`[~]` explicitly. Today a conditional-branch-not-taken AC
>    silently inflates a ticket to 100%.
> 4. Then **[[T154]] (P0, MCP exposure)** or **T151 AC2** (the united graph, the owner's stated priority).
>
> ### ⚠️ DO NOT
> - Re-open [[T89]] — its pipeline work is genuinely done and verified; T155 is its child.
> - Re-measure the T127/T128/T131 findings above — each has a reproduce command
>   (`just skills-vendor-audit`, `just skills-version-check`, `just skill match`).

</details>
