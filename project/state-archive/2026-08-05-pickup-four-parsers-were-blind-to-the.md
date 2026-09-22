<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### ⭐ (was) PICK UP HERE — 2026-08-05 — **FOUR parsers were blind to the board at once (a formatting change broke `state -->

<details><summary>Previous pickup block (2026-08-05) — superseded, kept for trace</summary>

### ⭐ (was) PICK UP HERE — 2026-08-05 — **FOUR parsers were blind to the board at once (a formatting change broke `state-check`, `sdlc-doctor`, `backfill-tickets` AND `just gate`), and the CV corpus turned out to be ~37 artefacts across 4 delivery mechanisms, not 7 files. T164/T165/T166/T167 filed. T165 Phase 0.4/AC6 DONE — the sample role proved the corpus is a content-RECOVERY problem (11 claims across 6 docs, 3 in none) and that a JSON-Resume-only gate would be vacuous. Next: T165 Phase 1, with tasks 1.1/1.2 both rewritten by that finding.**

> **Written for an agent with none of my context. Everything below was measured live 2026-08-05.**
>
> ### 📍 STATE — clean; the T167 board-link edit landed in `54f6df80`
> `wom7web` and `wom7api` are on `beta`, working trees clean. `wom7api` still shows an untracked
> `.serena/` — see the hazard below.
>
> ### ✅ 2026-08-05 (later session) — **T165 Phase 0.4 / AC6 DONE** (`11419f14`)
> EventCartel converted to JSON Resume, schema-valid, editorial loss recorded at
> `openspec/changes/2026-08-05-cv-canonical-source/fidelity/` with **three reproducible scripts**
> (build · red probe · claim-matrix verifier). **Verdict: the structured form is adequate** —
> losses are presentational (no `highlights[].label`, bold flattens) and structural (one `work[]`
> entry cannot hold 7 contracts → custom `x_engagements[]`). One gain: `iso8601` **rejects**
> `"2018 - 2024"`, so vague ranges can no longer persist quietly.
>
> **The conversion was never the risk. Four findings that change later phases:**
> 1. 🔴 **It is a content-recovery problem, not a reformat.** **11 distinct claims for ONE role
>    across 6 documents**; richest holds **8**; **3 live in no single document**. The Ant Media /
>    WebSocket-per-ticket / API-scanner material is in **one private file and on no public
>    surface**; `Heroku→EKS`, `99.99% uptime` and `WAF+IAM` are **live on the site and in no private
>    source**. An importer reading the private CV alone would silently **delete** the latter.
> 2. 🔴 **AC1b's premise was WRONG — a content schema exists.** `apps/{web,cp}/src/content.config.ts`
>    (Astro **5** path) validates `cv_experience`. The original check looked at
>    `src/content/config.ts`, the Astro **4** path. **Sixth instance of the signature error: a
>    confident measurement whose method looked in the wrong place.** Task 1.2 shrinks to *extend*.
> 3. 🔴 **JSON Resume alone is a near-vacuous gate — measured, not assumed.** `x_*` fields
>    unvalidated (`additionalProperties: true`), **no** field `required`, and `format: uri` never
>    fires without *both* a `FormatChecker` *and* the optional `rfc3987` package. Task 1.1 grows to
>    "vendor a **second** w0m-owned schema". The red probe **failed against its own written
>    expectation** — which is the only reason this is known.
> 4. 🔴 **Two blocking date conflicts on a role nobody had flagged.** Evidence:
>    **2017-12-05 → 2022-05-04**. The live site says **2018 - 2024** — shortening the start by a
>    year and extending the end by two. Featherglass was **not** the outlier; the five recorded
>    owner blockers are an **undercount**. Also: **"~3,400 h" and "$85k+ Earned" are lower bounds
>    published as totals** — 5 of 7 contracts record neither, while carrying a full 5.0.
>
> ⛔ **Bulk conversion of the other 26 roles is BLOCKED** on 3 owner decisions (fidelity README §4):
> the `x_highlights[].{label,text}` shape · the EventCartel dates · how to present partial totals.
> **Decisions 2 and 3 are NEW owner blockers.**
>
> 📋 **Filed, not fixed (out of T165 scope):** `content.config.ts:267` exports only
> `{ cases, pages, tracks }` — the `proposals` and `contracts` collections (~90 lines of zod, the
> entire Upwork vault) are **defined but never exported**, in both apps.
>
> ### 🔴 THE FINDING — a board formatting change silently blinded FOUR parsers
> `TASKS.md` rows moved from a bare `| T123 |` to a markdown link
> `| [T123](project/tickets/T123.md) · [#9](url) |`. Four independent parsers anchored on the bare
> id, and **each matched 0 of ~155 rows**:
>
> | Parser | Symptom | Fix |
> |---|---|---|
> | `state_doctor.py` | `rows` reported **0**; `rowless_open` held **every** open ticket. STATE.md published *"121 open · 0 TASKS.md rows · 121 OPEN ticket(s) with no row"* **as fact** | `c3bd0e61` |
> | `sdlc_doctor.py::check_ticket_parity` | same blindness; its docstring claimed parity with a twin it had **already drifted from** | wom7api `9147134` |
> | `backfill_tickets.py` | reported nothing to backfill **regardless of the real gap** | `c3bd0e61` |
> | `gate_advance.py` | `just gate` died with *"not queued"*. **4th copy — missed by the first sweep because its regex is built with an f-string, so grepping the literal pattern never reached it** | wom7api `c1ebe61` |
>
> `gate_advance.py` had a second, worse defect: **it was not atomic despite its own comment saying
> so.** It wrote the ticket frontmatter and *then* looked up the board row, so the failure left T165
> at `in-progress` with a `⚪ queued` glyph — the exact partial transition the comment forbids. Row
> lookup is now `find_tasks_row()`, resolved **before** any mutation.
>
> ### 🔬 THE LESSON — a passing test scoped one layer from the defect
> **`just state-doctor-test` passed the entire time, and it was not wrong.** It rigorously proves the
> *comparison* fails on drift — mutated fixture, lying exit code, absent block, missing file. It
> never asserts the fact is **collected** correctly. That is harder to notice than no test at all.
> **T164 AC6 and T165 R8 both carry this requirement explicitly. Do not repeat the shape.**
>
> ### ✅ WHAT LANDED
> 1. **T164 #161** (queued) — govern the full host CLI surface; surface toolchain health in the health
>    report. `tools-policy.json` governs **17** tools and works; ~20 more are ungoverned and must be
>    filtered by **real usage**, not by what is installed. ⚠️ **TWO health surfaces already exist**
>    (`just health` = endpoint latency; `just health-check` = deployed `/api/health`, owned by T22
>    AC3) — **do not add a third**.
> 2. **T165 #162** (**in-progress**) — canonical CV source of truth. **Spec written and
>    `openspec validate` green**: `openspec/changes/2026-08-05-cv-canonical-source`, **11
>    requirements ↔ 9 ACs, traceable both directions**.
> 3. **T166 #163** (queued) — govern serena or remove it. It is **already running, undeclared**.
>    Owner-confirmed provenance: **part of the Headroom install** (`~/.claude.json →
>    mcpServers.serena`, global scope; already partly checked by
>    `headroom_bootstrap.py::check_serena()`). 🔴 **AC1b is the sharp one**: it launches
>    `uvx --from git+https://github.com/oraios/serena` with **no ref** — the one tool that can
>    rewrite source at symbol granularity is unpinned, unlocked, integrity-unchecked, so
>    `min`/`known_good` are unenforceable. AC1b **gates** AC1's policy half.
> 4. **T167 #164** (queued) — internal JSON Resume registry, a profile per user. **Platform
>    generalisation of T165; SEQUENCE T165 FIRST.** 🔴 RLS gap found: **there is no self-UPDATE
>    policy on `profiles`** (only view-own + admins-update-all), so self-service cannot work until
>    AC3 adds it.
>
> ### 📄 CV WORK — the drift is measured, not theoretical
> Correcting **one** fact (VXG ran **Nov 2025 – Feb 2026**, ~50 h, **not current**) took **three
> incomplete passes**:
> 1. branding + `public/cv` — missed two files because the list named `AT resume.md`, which
>    **predates VXG and never mentioned it**;
> 2. discovered `apps/{web,cp}/src/content/pages/cv*.md` is what **`CVPage.astro` actually renders**
>    — a **4th delivery mechanism**, 10 files, none of them touched by pass 1;
> 3. fixing `date:` had left `company: "VXG Inc (Active Engagement)"`, present-tense descriptions,
>    and **5 more** instances of the stale `4,000+ hours`. **22 replacements across 6 files.**
>
> Root cause every time: **reasoning about filenames instead of enumerating delivery mechanisms.**
>
> **Real census — 4 mechanisms, ~37 artefacts:** content collection (10, *what the site renders*) ·
> raw `.md` downloads (10) · public PDFs (10) · Supabase Storage `cv/` bucket, where
> `CVPage.astro:206` links **`Aleksei_CV_2025.pdf`** (2025 vintage) and `cv-pdf/index.ts:8` hardcodes
> **`Aleksei-Tcelishchev-CV.pdf`**, a *third* name matching neither · plus 3 branding md + 4 PDFs.
>
> - **No `apps/*/src/content/config.ts` exists** → the `cv_*` frontmatter the site renders is
>   **entirely unvalidated**.
> - Still stale and **invisible to a claim-grep** (they never mentioned VXG at all): `ru/cv.md`,
>   `es/cv.md`, `public/cv/aleksei-tcelishchev-cv-standard.md` — all 2026-03-06, **zero** 2026-role
>   mentions. Translations drift silently.
> - Standard chosen: **JSON Resume** (MIT) on the verified `additionalProperties: true`. Survey with
>   rejections: `docs/backend/branding/CV-DATA-STANDARDS-2026-08-05.md`.
> - New CV: `docs/backend/branding/Aleksei_CV_2026-08_Private.md` — **27 roles** (was 18),
>   35-engagement table, and an internal revision-notes block that **must be stripped** on export.
>
> ### 🔎 UPWORK — three findings that change T165's importer
> 1. 🔴 **A MISSING ENGAGEMENT.** **Scribely — "AWS Audio Description Automation (Polly &
>    MediaConvert)", 2026-01-24 → 2026-02-07, CLOSED.** Absent from all 27 CV roles because it
>    started **after** the 2026-01-11 export. Media-pipeline work, on-theme.
>    ⛔ **Needs an owner description** — dates/client/title are known, what was done is not.
> 2. **The vault is a month fresher than the export.** `apps/*/src/data/upwork_vault/` was exported
>    **2026-02-10** (93 contracts); `all_contracts_enriched_2026-01-11.json` is **2026-01-11** (92) —
>    **and the CV engagement table was built from the older one.** T165's importer spec names only
>    the export; **correct it.**
> 3. 🔑 **`contractId` is NOT a stable join key — use `offerId`.** The EventCartel Django engagement
>    is `contractId 28190425` in the export and `id 24007208` in the vault: **same `offerId`
>    12623263**, same dates, same title, same contract. Joining on `contractId` shows a false 2-way
>    delta; joining on `offerId` gives 84 shared and **exactly one** genuine vault-only record
>    (Scribely). **An importer that joins on `contractId` will silently double-count and inflate the
>    hours total.** This is the "dedupe contracts" problem [[T155]] names.
> 4. **541 proposals, 346 mentioning webrtc/livekit/ant media/streaming/video** — the largest
>    untapped narrative source in the estate. The AgilityFeat evidence base was built from
>    **contracts only**, which is why the Ant Media story was buried in a generic Django description.
> 5. **`freelancer_profile.md` still claims ZERO** WebRTC/video/streaming/voice/LiveKit/Ant Media
>    (Kubernetes 4, Terraform 2, AI 12) — so the Upwork profile **contradicts** the CV's Real-Time
>    Media section and the AgilityFeat answers. Flagged in `skills-matrix.md` since 2026-08-03.
> - **Boundary NOT YET RECORDED in either ticket:** T155 (in-progress) owns getting the Upwork corpus
>   complete + deduped; T165/T167 **consume** it. T165's importer should depend on T155's output
>   rather than re-parsing raw exports.
>
> ### 🎯 NEXT ACTION
> ~~T165 Phase 0.4~~ — **DONE `11419f14`** (see the ✅ block above).
>
> **T165 Phase 1 — schema and validation (R1/R4), tasks 1.1–1.4.** Needs no owner input; Phase 0.4
> rewrote both halves of it, so **read the revised task text before starting**:
> - **1.1 grew** — vendoring the JSON Resume schema is *not sufficient*. Also author a **second,
>   w0m-owned schema** for the `x_*` custom fields and our own required-ness, and enable format
>   checking with its dependency declared (ties **T164**). A JSON-Resume-only gate is vacuous, and
>   `fidelity/probe_validation.py` is the fixture that proves it.
> - **1.2 shrank** — a content-collection schema already exists and is live. **Extend it, do not
>   rewrite it.** Known gaps to close: `cv_experience` is `.optional()` (an absent array passes) and
>   `date` is a free string that accepts `"2018 - 2024"`.
> - `fidelity/jsonresume.schema.json` is the vendored copy to promote into `project/schemas/`.
> ⚠️ **Do NOT start Phase 2's bulk conversion** — R11 gates it on the 3 owner decisions above.
> Phase 0.2/0.3 also need the owner (below).
>
> ### ⛔ OWNER ACTIONS BLOCKING PROGRESS
> 1. 🔴 **DEPLOY — nothing corrected today is live.** Verified:
>    `webomage.com/cv/aleksei-tcelishchev-cv-full.md` still serves *"Nov 2025 - Present (Active
>    Engagement)"*. **T161 AC3 denies `deploy*`/`db-migrate*`/`release*` to the agent** — this is not
>    an oversight, it is the policy.
> 2. **Five CV data blockers, not inventable:** Kayse dates (no evidence anywhere) · **Featherglass
>    end date — FOUR variants** (CV `2025–2026` / AgilityFeat doc *"ended"* / Jan-2026 export **still
>    active 404.7 h** / content collection `Jun 2025 - Dec 2025`) · Evercred (no contract) · Romantic
>    Robot **434 h** + AMZ Tracker **164 h** at **$0.00** recorded earnings but **both 5.0/5** · one
>    concrete result each for W AI/Waltz, Renowned Marketing, Data Sleek, Openmart (currently
>    described from **agreed contract scope only**).
> 3. **Scribely description** (above).
> 3b. 🆕 **THREE more from Phase 0.4, and they gate bulk conversion of 26 roles:**
>    (a) **`x_highlights[].{label,text}` shape?** — recommended, keeps bullet labels as data while
>    still emitting standard `highlights[]`. Cheapest to decide before 27 roles are converted.
>    (b) **EventCartel dates** — Upwork evidence says 2017-12-05 → 2022-05-04; the CV and the live
>    site say 2018 – 2024. Was there off-platform work after May 2022, or is 2024 stale?
>    (c) **Partial totals** — publish `3,401.8 h` with the "5 of 7 contracts record no hours"
>    caveat, or publish only what is fully evidenced? Same question applies to the estate-wide
>    **10,600+ hours** headline.
> 4. **Two editorial calls on public pages:** `company: "Ben Israel ($18k+ Earned)"` — Ben Israel is
>    the Upwork **payer**, the client/project is **Featherglass**; and **10 instances** of
>    `$Nk+ Earned` baked into public company strings.
> 5. **T166 AC1b** — pin the serena `uvx` launch to a ref, or accept the risk in writing in
>    `TECH-DEBT.md`.
> 6. ⚠️ **LIVE HAZARD: `.serena/` is not gitignored** in `wom7api/` or the monorepo root, and holds
>    `cache/` + `memories/`. **One `git add -A` commits a cache and a memory store.** It is T166 AC2,
>    but it is a hazard now — every `git add` this session was deliberately scoped because of it.
>    ✅ **CLOSED 2026-08-05** (T166 AC2, all 7 repos). The hazard was also overstated — `.serena/`
>    ships its own `.gitignore` and held no `memories/`.

</details>
