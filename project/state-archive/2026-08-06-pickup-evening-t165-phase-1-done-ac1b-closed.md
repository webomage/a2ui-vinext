<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### ⭐ (was) PICK UP HERE — 2026-08-06 (evening) — **T165 Phase 1 DONE (AC1b closed: two CV schemas, one gate, 20 probes  -->

<details><summary>Previous pickup block (2026-08-06, evening) — superseded, kept for trace</summary>

### ⭐ (was) PICK UP HERE — 2026-08-06 (evening) — **T165 Phase 1 DONE (AC1b closed: two CV schemas, one gate, 20 probes across three layers) · T166 + T169 ARCHIVED · T172/T173 filed from the top-10 SDLC review. serena PROVEN by a real tool call — and that call is what exposed T172.**

> **Written for an agent with none of my context. Measured live 2026-08-06.**
>
> ### 📍 STATE — all 7 repos clean, **0 unpushed** (5 commits pushed: wom7web 3 · wom7api 2)
> `just typecheck` **0 errors** across 154+167+5 files · `just cv-validate` green ·
> `just cv-validate-test` **20/20**. `wom7mlx` 9 dirty / no upstream is still **another agent's**.
> ℹ️ The mechanical table above may render `unpushed=2` — that is **correct, not stale**.
> `state_doctor` renders dirty/unpushed/HEAD but deliberately **never compares** them: making them
> blocking would mean `state-save` → commit → push could never pass. Only the gate exit codes,
> rowless-OPEN set, repo set, hot-10 order and wom7web *ancestry* (>10 commits) block. I checked
> this expecting a sixth vacuous gate and found a documented decision instead — worth recording,
> because the next agent will notice the same mismatch and reach the same wrong conclusion.
>
> ### ✅ T165 PHASE 1 — tasks 1.1–1.4 all done, **AC1b ticked**
> New: `project/schemas/cv/{jsonresume,w0m-cv}.schema.json` + README ·
> `project/scripts/cv_validate.py` · `project/scripts/tests/test_cv_validate.py` ·
> `just cv-validate` / `just cv-validate-test` (recipes live in **wom7api/justfile** — wom7web's is
> a symlink to it, so an Edit through the symlink is refused).
>
> **Four things a summary would lose:**
> 1. **The format dependency was REMOVED, not declared.** Task 1.1 expected to add `rfc3987`.
>    Using `pattern` instead of `format` means none is needed. Re-measured on `jsonschema 4.25.0`:
>    `uri` is **absent** from `FormatChecker().checkers` but **`date` is present** — so `format: date`
>    *would* have worked, yet only when every caller remembers to pass a `FormatChecker()`. A
>    constraint that no-ops when an argument is forgotten is the same shape as the vacuous gates
>    this project keeps finding. `tools-policy.json` unchanged.
> 2. **The constraint that mattered in 1.2 was not the one the task named.** Measuring all **64**
>    live entries first showed the corpus split across **two separator characters** — English files
>    ASCII `-` (48), `es`/`ru` en dash `–` (16). **Each locale was internally consistent**, so no
>    per-file check could ever have surfaced it; only reading all ten files at once did. Normalised
>    to ASCII (the en dash is a *render* concern).
> 3. **`just cv-validate` extracts the date rule FROM `content.config.ts`** rather than restating
>    it, and **errors** if extraction fails — no fallback. On 2026-08-05 one TASKS.md formatting
>    change blinded **four** parsers that each held their own copy of an anchor. A Python copy of
>    this regex would have been the fifth.
> 4. **The new schema immediately caught a defect JSON Resume passed** — `feedback: "not_rated"`, a
>    string among numbers, live in the Phase 0.4 output. **Not overruled**: `build_eventcartel.py:72`
>    writes it deliberately. Encoded as a *narrow* union (`number 0..5 | "not_rated"`, explicitly
>    **not** `null` — three encodings of one idea is the drift this ticket exists to remove) and
>    filed as a **4th owner question** in `fidelity/README §4`.
>
> ### 🔴 THE MEASUREMENT TRAP I NEARLY SHIPPED
> The first proof that the Astro gate blocks read **`EXIT=0`** — that was **`tail`'s** exit code
> through a pipe, not `astro sync`'s. Re-measured without the pipe: `astro sync` **and**
> `just typecheck` both exit **1**. ⇒ **`$?` after a pipeline is the LAST command's.** One character
> of shell would have recorded "the gate is advisory" as a fact.
> Also: **`timeout` on this host is a pyenv shim** that dies with `ModuleNotFoundError: examples`,
> not coreutils. Don't wrap commands in it.
>
> ### ✅ SERENA IS PROVEN — T166's archive gate is cleared
> A **real tool call** (`find_symbol`) returned indexed symbols with live paths. That is what the
> previous block said T166 must not be archived without, since AC1b had closed on `serena --version`.
> ⚠️ **But the active project is the UNGOVERNED umbrella one.** Paths resolve as `@wom/wom7web/…`:
> serena activated **`@wom/.serena/project.yml`** (`project_name: "@wom"`), and `@wom` is **not a git
> repo**, so that config is versioned nowhere. T166 versioned the *per-repo* configs — which are not
> the ones this session actually used. Worth resolving before T166 is archived.
> ⚠️ **serena migrated all three `project.yml` files in place at 12:34** and stripped the T166
> governance headers (measured file counts, the `.astro`/`.sql` blind-spot warnings). Restored in
> `26e1368f`/`aed011d`. It left a `.bak-T166-schema`, so this looks **one-time**; if the header
> disappears again, serena rewrites on every start and T166 needs to know.
>
> ### 📋 TOP-10 SDLC REVIEW (same session) — **[[T172]] and [[T173]] filed, D32/D33 added**
> Reviewed the ten tickets closest to done. **The headline is not any one ticket — it is that 3 of
> the top 10 cannot be finished in place**, because a remaining AC is owned by a different,
> `queued`, unstarted ticket: **[[T22]] AC4 → [[T8]]** · **[[T110]] AC3 → [[D7]]/[[T104]]** ·
> **[[T20]] AC4, whose text reads *"= T7"* → [[T7]]**. `grep` for `blocked_by`/`depends_on` across
> all ticket files returns **zero** — whole-ticket blocking exists as a `status:` value, per-AC
> blocking does not. → **[[T173]]**.
> ✅ **[[T166]] and [[T169]] are now ARCHIVED** (same session, via `w0m-sdlc-archive`). They were
> 7/7 and 6/6 but still `in-progress`, squatting the top two ranked slots; their board cells also
> read `🟡 queued` while their tickets said `in-progress` — **three surfaces, three answers**, all
> reconciled to `done`. Both ACs were **re-verified live at the gate rather than trusted**:
> `tools-check` → `serena ✓ 1.6.1`, and `mcp-exposure` → **1 comparable declaration**
> (`127.0.0.1:8787 headroom-proxy`, declared + listening) where it once reconciled an empty set.
> Open count **127 → 125**; the SDLC board now starts at T22.
> ⚠️ **Fixed at the archive gate: `CLAUDE.md` still said all of `.serena/` was gitignored** — T166's
> own owner decision superseded that on 2026-08-05 (`project.yml` is versioned). **A rule file had
> drifted from the decision that changed it, inside the same ticket.** Also recorded there: the
> `.astro` count is **210 tracked / 220 on disk** — both correct, different methods, and this estate
> has already been bitten by globbing the filesystem instead of asking git.
> Corrected in place: **[[T77]] AC4 said "8 orphan WARNs"; live count is 4** — AC3 was updated
> 2026-08-02 and AC4 was not. Those 4 orphans *are* AC3's remaining work, and 2 of them are at
> 0 tasks done, so dropping them is a decision rather than cleanup.
> ⚠️ **T99 (4/9) and T131 (3/7) rank high on `sdlc` and are ABSENT from `hot`** — both P2, so the
> readiness heuristic scores them low. They are unblocked; nothing but priority keeps them off.
>
> ### ✅ T165 PHASE 2 — the importer is BUILT (same session)
> `just cv-import` · `just cv-import-test` (**27 checks**). `project/data/cv/resume.json` exists,
> is generated, holds **28 roles**, and passes `just cv-validate --require-canonical`.
> **Done: 2.1 · 2.5 · 2.6 · 2.7.** **2.2 partial** (frontmatter is the conflict-comparison surface,
> not yet a `work[]`/`skills[]` source). **2.3 and 2.4 deliberately NOT done** — 2.3's prose→
> `highlights[]` union would, on the Phase 0.4 evidence, *delete* the claims that live only on the
> live site; its strip-and-assert half **is** done.
>
> **Three things worth carrying:**
> 1. 🔑 **The join could not be name-based, and that was measured before it was designed.** Of the
>    13 distinct company strings in the corpus **exactly 1** matched an export company name
>    (`VXG Inc`); only 6 matched after stripping `($Nk+ Earned)`. So fuzzy matching would have been
>    the *primary* path, not a fallback. The join is `project/data/cv/company-aliases.json` —
>    explicit, committed, and its contract counts are **asserted every run**.
>    🔴 One entity (`TokensFarm / DcentraLab / 2key Network`) is written **three ways**, including
>    two different orderings of the same two names in different CV files.
> 2. 🔴 **The conflict detector was built wrong first.** It compared only `startDate` against the
>    evidence, so the corpus's loudest disagreement was invisible while the tool looked healthy:
>    **EventCartel is claimed to end 2024 by ELEVEN sources; the evidence ends 2022-05-04.**
>    Comparing both ends surfaced **two more nobody had recorded** — TokensFarm/DcentraLab ending
>    **2021-02-17** vs **2023** claimed, and the private CV's hand-typed **"93 contracts"** against
>    an export of **92**. 6 open conflicts now, all in `project/data/cv/conflicts.json`.
> 3. 🔴 **The role parser nearly shipped this ticket's own defect.** Anchored on a comma, it matched
>    **26 of 28** headings — two roles have no employer entity (`— independent consulting`,
>    `— Plesk / Parallels stack`) — and would have emitted a CV **missing two jobs** while reporting
>    success. It now asserts `parsed == total` and dies otherwise. ⚠️ **The corpus has 28 roles, not
>    the 27 recorded in AC1.**
>
> ### 🔑 THE RESUME IS ATTACHED TO `aleksei@webomage.com` — owner instruction 2026-08-06
> The **public person**, deliberately not `casualuser@gmail.com`, which is the w0m **institutional**
> persona. Enforced **twice, independently**: `cv_import.py` asserts the address it reads out of the
> corpus, and `w0m-cv.schema.json` pins it as a **`const`** — not a format check, because the
> requirement is not *"a valid email"* but *"this one"*.
> 🔒 The phone goes to **`x_private`**, ONE structural key, so the public projection (3.1) strips a
> single subtree and the R7 leak check (3.2) asserts one key — not a list of field names to remember.
> ⚠️ `basics.location` first used an invented `note` key and **validated clean**, because
> `additionalProperties` is true there. Now uses JSON Resume's own `city`/`region`/`countryCode`,
> with `countryCode` constrained to ISO alpha-2 — upstream declares **no pattern**, so `"Mexico"`
> would have passed unchallenged. **Passing validation with field names no consumer reads is the
> trap the second schema exists for.**
> **Phase 2 is now 6 of 7** — 2.2 and 2.4 closed (skills from the richest file, 11 projects with
> explicit associations). **38 checks** in `cv-import-test`.
>
> ### ✅ PHASE 3.1 + 3.2 DONE — the R7 leak gate exists BEFORE any writer
> `just cv-public` · `just cv-leak-check` · `just cv-leak-check-test` (**19 checks**).
> Built together and **first**, because 3.2's own wording is *"before any served-path write
> exists"* — so the projection **prints and writes nothing**, and 3.4/3.5 come after the gate that
> guards them. The projection strips every `x_` key **by prefix, at any depth** — a list of field
> names goes stale the first time someone adds one, and the failure is silent.
> 🔴 **Two things the first version got wrong, both now red-probed.** (1) **A phone number is not
> one string** — the gate matches canonical, digits-only, national and whitespace-squashed forms;
> a naive `if secret in body` clears a document that publishes the same fact formatted its own way.
> (2) **PDFs were listed "not scanned" with a caveat — but the served CV downloads ARE PDFs**, so
> the likeliest carrier was the one format the scan skipped. A gap *described* rather than closed.
> `pdftotext` is present, so all 10 are extracted; if it ever is not, they fall back to UNREADABLE,
> which **fails**.
> ✅ **Measured against reality: 410 served files (400 text + 10 PDF) are clean of the private
> value today.** 694 image/font files are reported unscanned and never counted as clean.
>
> ### ✅ 2.3 DONE — PHASE 2 IS COMPLETE (7/7)
> `just cv-claims` · `just cv-claims-test` (**21 checks**). **489 bullets → 220 distinct claims
> across 17 documents; 100 attested by exactly ONE document.** All **28** roles carry highlights.
> `x_highlights` stays **unwritten** — its shape is open owner decision 1.
> ✅ **Cross-checked against Phase 0.4's independently HAND-derived matrix and it reproduces the
> split exactly** — `Ant Media`/`WebSocket`/`API scanner` private-only, `Heroku → EKS`/`99.99%`/
> `WAF+IAM` public-only. Two unrelated methods agreeing is evidence, and those three public-only
> claims are the concrete proof that reading one document deletes material. Pinned as a test.
> 🔴 **The clustering was ORDER-DEPENDENT and its own assertion caught it on run one** — an
> identical string landed in two clusters because a later copy matched an earlier cluster that had
> grown a similar variant. Exact duplicates are merged **before** similarity now.
> 🔴 **Two defects found in work already marked DONE.** (1) `rsplit(",", 1)` made
> `Openmart, Inc.` → employer **`"Inc."`** and `Edgy Labs, LLC` → **`"LLC"`**. Nothing was
> *dropped*, so the count assertion stayed green — it was silently **wrong**, found only by reading
> the emitted list. ⇒ **A collection assertion does not catch a correctness bug.** (2) Only **7 of
> 28** roles got highlights: the alias table governs **two** joins, and a role absent from it
> silently got zero. Now 28/28.
> ⚠️ Still review material: **15 clusters hold >1 wording**, and the tool says so.
>
> ### 📊 T165 NOW: Phases 1 + 2 complete, 3.1/3.2 done · **98 checks across 4 suites**
> `cv-claims-test` 21 · `cv-import-test` 38 · `cv-validate-test` 20 · `cv-leak-check-test` 19.
>
> ### ✅ MOVED TO [[T131]] — now **5/7** (was 3/7). AC2 + AC7 done, AC6 half.
> 🔴 **The SDLC preflight CRASHED at the top of the gate, and that is the headline.**
> `just sdlc-doctor` died with `FileNotFoundError: 'serena'`. Two defects: it **re-probed tools**
> with its own `[name, --version]` default instead of delegating to `tools_check`, so it never
> learned T166's lesson that a `source: uvx` tool has **no binary on PATH** — the moment T166 added
> serena to the policy, the doctor stopped reporting and started crashing. Worse, `sh()` never
> caught `FileNotFoundError`, so **ANY absent optional tool** (aws, az, terraform, gcloud, ast-grep)
> would have killed it. ⇒ **A checker that dies on the condition it exists to report is not a
> checker.** Now delegates; all 21 tools probe, serena included.
> ✅ **AC7** — `openspec/specs/release-versioning/spec.md` (6 requirements, 8 scenarios, verbatim
> from the archive, `openspec validate` clean). Its Purpose carries an **enforced-by table** saying
> which requirements have a live gate and which do not.
> ✅ **AC2** — `just build` stamps `apps/*/dist/client/version.json` via `stamp_build.py`; the
> triple is **passed in** (justfile stays the single producer) and `deploy_commit` now sits beside
> `deploy_version`/`deploy_at`. ⚠️ The helper is a **script, never a nested `just`** — a nested call
> re-evaluates the backtick assignment and would stamp a *different* timestamp than the run is
> deploying. Red-probed 8 ways; rejects all three orphaned formats deleted 2026-07-26.
> 🔴 **A live drift instance found and removed:** `apps/{web,cp}/public/version.json` were
> **git-TRACKED**, frozen at `2026.02.26-1772088006` — **five months stale** — served publicly as a
> version claim, read by **zero** consumers. The archived spec already said these must be
> "build-only and git-ignored". Deleted + ignored; the endpoint still exists post-build, correct.
> ⛔ **AC6 left HALF on purpose** — 8 `deploy-*` recipes still inline the commit. The swap is
> trivial, but it changes the **deploy path**, which [[T161]] AC3 denies me, so I cannot run what I
> would change. Recorded rather than shipped untested.
>
> ✅ **AC5 also DONE — [[T131]] is now 6/7.** `sdlc-doctor` verifies version conformance by
> **delegating** to `just version-check` + `just skills-version-check` (both green today —
> measured before enforcing). Proven RED: `just sdlc-versioning-test`, **14 checks** — a failing
> gate becomes a problem naming the recipe and carrying its output; a **timeout becomes an explicit
> UNVERIFIED note**, never silence. ⚠️ That probe tests the **wiring**; what the gates *detect* is
> proven by `just version-test` (19/19) — saying so because a mocked test claiming to prove
> conformance is exactly the vacuous assertion this estate keeps finding.
> ⏱️ `just sdlc-doctor` now costs **~16s** (was ~5s) because it actually runs both gates.
>
> ### ✅ [[T131]] IS 7/7 — AC6 closed 2026-08-07, and it was never actually blocked
> 🔴 **I blocked AC6 on nothing and it cost a day.** I recorded it as needing `just deploy` because
> 8 deploy recipes inline `$(git rev-parse --short HEAD)`. The AC says `deploy-*`/`_log-deploy` are
> **"(already)"** satisfied — it asks whether every tool that should use the **version** does; the
> commit-inlining was *my own separate observation*. **A self-imposed blocker is still a blocker.**
> The inlining is real and now lives on **[[D34]]** (needs deploy, genuinely).
> ✅ The audit is **mechanical, not prose**: `just version-check` verifies every name in
> `.w0m/sdlc.json → producer.consumers` against the justfile, failing on a **dangling** declaration
> (no such recipe), a **stale** one (recipe exists, never interpolates `deploy_version`), and an
> **empty list** — a producer verified to emit a format nothing is checked to *use* is the same
> vacuous shape as an empty scan set.
> 🔴 **It found a real defect on its first run: `deploy-cfworkers` was DANGLING** — renamed
> `deploy-workers` in the 2026-08-01 worker split ([[T156]]), declaration never updated. The policy
> claimed a consumer that had not existed for six days, invisible because nothing checked the list.
> **This ticket's own thesis, landing on its own policy file.**
> `just version-test` 22 → **24/24**. ⚠️ One probe failed first and the **fixture** was wrong, not
> the code — it used `version` as the "does not stamp" recipe, and `version` echoes it.
>
> ### ✅ [[T131]] ARCHIVED 2026-08-07 (7/7) — open 125 → **124**
> Every AC re-verified by **running its gate**, not by reading its checkbox: `version-check`,
> `version-test` (24/24), `skills-version-check`, `sdlc-versioning-test` (14), `sdlc-doctor` — all
> exit 0; `openspec validate release-versioning` valid. No change-spec to archive (AC7 produced a
> **live** spec, not a change). Residue → **[[D34]]**.
> 🔴 **The lesson is a process one and it is about the agent.** AC6 was reported to the owner as
> blocked on `just deploy`. It was not — the AC says `deploy-*`/`_log-deploy` are *"(already)"*
> satisfied and asks about the **version**; the inlined *commit* was **my own observation**,
> promoted to an acceptance criterion and then declared blocked. ⇒ **A blocker must CITE the text
> that creates it.** *"I noticed X while doing Y"* is not *"Y requires X"*. Saved to auto-memory as
> [[agent-denied-operations]] alongside the two REAL denials (`deploy*`, `db-migrate*`).
>
> ### ✅ AC-TRUTH PASS DONE (5 tickets) — the toolchain cluster's numbers now mean something
> Owner 2026-08-07 put **[[T165]] on hold at P2** (top P2 task) and redirected to *"complete our own
> toolchain and code management functions"*. `just tasks overview` names that cluster exactly:
> **`sdlc` + ROADMAP §13, 15 tickets — the largest bundle in the queue.** Its reported **7%** was
> not trustworthy, so nothing was built until it was verified.
>
> | ticket | was | now | what changed |
> |---|---|---|---|
> | **[[T135]]** | 0/12 | **7/12** | ACs were never ticked as work landed; spec showed **42/61 tasks done** |
> | **[[T110]]** | 2/5 | **3/5** | AC3 met — its blocker was the stale [[D7]] retired the same day |
> | [[T96]] | 0/5 | 0/5 | a **verified** zero now, not an unmaintained one |
> | [[T22]] | 2/4 | 2/4 | both ticks re-backed by the recipe body, not the ticket's claim |
> | [[T77]] | 2/4 | 2/4 | already accurate — stamps added then **reverted** |
>
> 🔑 **Every tick now carries the command that proves it.** `discovery` exits 0 · `docs-check` 40
> checks · `secrets-check` live at pre-commit · every `hygiene-policy` exemption carries a reason.
> 🔴 **T135 AC11 — my own check was wrong and the estate's was right.** I measured 17/18 manifests
> and read the odd one as a violation; it is `@mcp-b/websocket-bridge`, third-party MIT with a
> retained LICENSE, and `extension/package/` is **already in `vendored_markers`**. Forcing
> `UNLICENSED` onto it would have **relicensed someone else's code as proprietary** — the exact trap
> this ticket's own §5.8 recorded. **Fourth time today an ad-hoc measurement lost to the project's
> own tool.**
> 🔴 **T135 AC7 has a precise gap:** 19 re-runnable `*-test` recipes exist, but **none for
> `docs-check`, `secrets-check` or `license-check`** — the three gates T135 itself added. Their red
> probes ran once and were written into prose, so a regression in their ability to FAIL is invisible.
> ⚠️ **T77 needed nothing, and I made it worse before fixing it** — the stamps only restated its own
> correct text. *A verification pass that adds noise to an accurate record has damaged it.*
> ⚠️ **[[T117]] is in this bundle by accident** (RBAC schema tagged `sdlc`/§13) and is inflating its
> stats at 2/10. Re-tag before reading the bundle as the toolchain.
>
> ### 🎯 NEXT ACTION
> **Board top is now [[T110]] 3/5 and [[T135]] 7/12** — both P1, both with named remaining work:
> T110 AC4 (nothing verifies a ticket passed its gates) + AC5 (install performed, not described);
> T135 AC7 (**three `*-test` recipes**) + AC3 typecheck + AC6 remediation (68 notice findings).
> Then [[T96]], whose three open ACs are now specified rather than guessed.
> Superseded: **The board's top is now genuinely owner-gated.** [[T22]] (2/4) and [[T110]] (2/5) lead the SDLC
> board; **T22 AC4 needs [[T8]]** and **T110 AC3 needs [[D7]]/[[T104]]** — both unstarted tickets,
> which is exactly what [[T173]] exists to make visible. Superseded:
> Superseded: **[[T131]] AC6 is the ONLY thing left (6/7) and it needs someone who can deploy** — 8 `deploy-*`
> recipes still inline `$(git rev-parse --short HEAD)`; the producer (`deploy_commit`) now exists,
> the swap is trivial, but it changes the deploy path that [[T161]] AC3 denies the agent.
> Then: **[[T99]] (4/9)** is the next unblocked ticket — though its remaining ACs (encryption at
> rest, migrations, Infisical key) need `db-migrate`, **also denied**. ⇒ **Most of what is left in
> this queue is owner-gated, not unstarted.**
> Superseded: **[[T131]] AC5** — `sdlc-doctor` verifies version conformance (unblocked; the doctor is now
> healthy enough to extend). Then **AC6** needs someone who can run `just deploy`.
> Superseded: **Everything unblocked in T165 is now built.** What remains is **3.3–3.7 + Phases 4–6, all
> owner-gated** on the 3 fidelity decisions (+ the 4th, `not_rated`) and on deploy. So the next
> action is **not** more T165 code — it is either an owner decision, or a different ticket:
> **[[T99]] (4/9, unblocked)** and **[[T131]] (3/7, unblocked)** are the two nearest-done tickets
> that need nobody's permission.
> Superseded: **Only 2.3 and 3.3–3.7 remain, and 3.3–3.7 are owner-gated.** So the one unblocked piece of real
> work is **2.3 — the claims union**, and `fidelity/verify_claim_matrix.py` already does it for ONE
> role: it re-derives an 11-claim × 6-document matrix from live files and fails if the table drifts.
> Generalising that to 28 roles IS 2.3. ⚠️ Do not write it as a prose parser — read
> `fidelity/README §0` first; 3 of the sampled role's claims live in **no single document**.
> Superseded next-action:
> **T165 Phase 3 — generation (3.1–3.7)** is the next buildable block, but ⛔ **it is owner-gated**
> on the 3 fidelity decisions. The unblocked work is **2.2's remaining half + 2.4** (`projects[]`,
> using the alias table as the pattern) and **AC1's gaps: `education`, `skills[]`**.
> ⚠️ **Do not attempt 2.3 as a parse** — read `fidelity/README §0` first; it is a content-recovery
> union across 6 documents, and 3 claims for the sampled role live in no single document.
> *(Superseded: the previous block said "next = Phase 2, start at 2.1 and 2.5, wire
> `--require-canonical` when 2.7 lands". All three are done — the switch is live and the validator
> now reports `canonical validated` instead of `ABSENT`.)*
>
> ### ⛔ OWNER ACTIONS — now FIVE
> 1. **DEPLOY** — nothing from the CV work is live; [[T161]] AC3 denies `deploy*` to the agent.
> 2. **3 T165 fidelity decisions** — `x_highlights[]` shape · EventCartel dates · partial totals.
> 3. **Scribely** — written from the job description only; confirm delivered vs scoped.
> 4. **[[T171]] credentials** — whether one personal Pro subscription may back N concurrent
>    sandboxed agents is a **terms question**, deliberately not guessed at.
> 5. **NEW — how `not rated` is encoded** (`fidelity/README §4` item 4): keep the string sentinel,
>    or move to `{score, state}`? Option (a) needs no work; the schema already accepts it.

</details>
