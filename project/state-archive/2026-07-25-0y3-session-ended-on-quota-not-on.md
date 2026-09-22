<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0y3. superseded pickup block — 2026-07-25 (LATE NIGHT) — **Session ended on QUOTA, not on a problem. Tree clean, eve -->

### 0y3. superseded pickup block — 2026-07-25 (LATE NIGHT) — **Session ended on QUOTA, not on a problem. Tree clean, everything pushed. Next action: apply 3 evidence-backed tracking fixes, then write T135's spec.** ✅ **ALL THREE FIXES ARE NOW APPLIED — see the ⭐ block above.**

> **Handoff state, verified at write time:** `wom7web` · `wom7api` · `wom7cfworkers` · `wom7md` ·
> `wom7skills` · `wom7ext` — **all on `beta`, 0 dirty, 0 unpushed.** wom7web HEAD is **the commit that
> carries this file** (`git log -1 --format=%h -- STATE.md`); the last *code/ticket* commit before it is
> **`d2aab309`**.
> `git pull` first — a parallel Antigravity agent also commits to `beta`.
>
> **Two trees are dirty and NEITHER is mine** (another agent's in-flight logits-mismatch work):
> `wom7mlx/wom7mlx` **10 dirty / 0 unpushed**, and the vendored `wom7mlx/mlx-rs` **10 dirty** (branch
> `main`). **Do not touch, do not reformat, do not "fix" them** — see §0w item 1 for why they matter to
> T135 and why they are *not* a blocker for the gate that ships.
>
> ### ▶ START HERE — in this order
> 1. `git pull` everywhere.
> 2. **Apply the 3 tracking fixes below.** All three are *already evidenced* (§0z) — this is 15 minutes
>    of tracking-surface work that stops the board lying, and the evidence is in hand so you do not need
>    to re-measure. Do it before ranking or picking work.
> 3. **Then: `w0m-sdlc-spec` for T135.** Start gate is DONE, **all 7 owner questions answered**, 0 open
>    questions. Nothing blocks the spec.
> 4. **Do NOT re-derive the measurements in §0w and §0z.** Each is a real command run against the live
>    DB / live tree. They are marked with what was measured and how.
>
> ### 🔧 THREE TRACKING FIXES — evidence gathered, not yet applied
> | Fix | Evidence (measured 2026-07-25 live) | Action |
> |---|---|---|
> | ~~**Close T49**~~ ✅ **APPLIED** | **0** SECURITY DEFINER functions in `public` lack a pinned `search_path`; **32** are pinned; stamp `20260723101000` present. Closed by T123's sweep — the "one ticket closed by another" pattern. | ✅ Done — gated to `done`, AC4 verified (`deno-test` 18/18, `vitest` 1/1), board prose rewritten. ⚠️ **Ticking AC4 uncovered a live breakage → [[T140]]** (see the new pickup block) |
> | ~~**Drop T32 off P0**~~ ✅ **APPLIED** | 3 of 4 ACs satisfied: gitleaks rules `wom-db-password-in-prose` + `wom-postgres-uri-inline-password` present in **all six** repos ✅ · `OPENROUTER_API_KEY` **absent** from the store ✅ · rotation done per the 2026-07-14 record. **Remaining = git-history purge, which is already [[T17]]'s scope.** | ✅ Done — P0→P2, `blocked`→`paused`, AC1/AC3/AC4 ticked, AC2 pointed at T17, ticket + TASKS + tickets.json in sync. Deliberately **not closed** |
> | ~~**Correct T131**~~ ✅ **APPLIED** | ⚠️ This row's own numbers were wrong — see the correction in §0z item 2. Actual: **11 of 40** `SKILL.md` files declare an *indented* `metadata.version`, so *"16 of 27"* was right per top-level dir and **29 of 40** per the real corpus. `.w0m/skills.json` has **two** fields: `version` = provenance label, `observed_version` = the real version (58/70). | ✅ Done — T131 board row + ticket rewritten around the denominator-free statement: **zero canonical skills carry a *conforming* version** |
>
> ⚠️ **Do not close T32 outright** — it is not done, only mis-prioritised. And **do not re-test the
> leaked DB credential** to confirm the rotation; that is a login attempt with a leaked secret. The
> 2026-07-14 record is the evidence.
>
> ### 🔴 OWNER ACTIONS OUTSTANDING — now THREE (one was completed this session)
> 1. **Revoke the `casualuser` GitHub token** — GitHub → Settings → Applications / PATs. Dropping the DB
>    row did **not** revoke it (ciphertext, no recoverable key ⇒ not validatable or revocable
>    programmatically). Identity `casualuser`, GitHub id `1243074`.
> 2. **T99(d) task 3.1 — provision the key.** ✅ **Re-verified ABSENT this session** (presence-checked
>    through `infisical run`, values never printed): both `CONNECTOR_TOKEN_KEY_V1` and
>    `CONNECTOR_TOKEN_KEY_VERSION` are **not set**. Needs `openssl rand -base64 32` → Infisical, version
>    `1`, exposed to the edge runtime as Supabase secrets. **Do not let an agent invent key material.**
> 3. **T99(d) task 3.5 — apply `20260725180000`.** ✅ **Re-verified NOT applied**: stamp absent and **0**
>    `%ciphertext%` columns exist live. Deliberate — it is outward-facing and pointless before 3.1.
> - ✅ **DONE this session: the Xcode Metal toolchain was installed by the owner.** It fixed the failure
>   it was meant to fix, but **did not unblock the Rust compile gate** — the blocker moved. §0w item 1.
>
> ### 🔥 THE VALIDATED HOT 10 (owner asked 2026-07-25; every row checked against evidence — §0z)
> Ranked by *ready-to-workness*, with the verdict of the validation pass on each.
>
> | # | Item | Verdict | Why it's here / next action |
> |---|---|---|---|
> | 1 | **T135** repo-hygiene gates | ✅ confirmed | 🟡 in-progress, **0 open questions**, no spec dir. `w0m-sdlc-spec`. All grounding paid for (§0v, §0w). |
> | 2 | **T120** Safe Browsing (P0) | 🟡 **unverifiable from here** | Review was requested 2026-07-22; blocked on Google's verdict + owner Search Console. **Cannot be checked without Search Console or a Safe Browsing API key — so it may already be cleared and nobody looked.** A 5-minute check could close a P0. |
> | 3 | **T99(d)** connector tokens (P0) | ✅ confirmed, strongly | `validate --all --strict` **56/56** · `just deno-test` **18 passed / 0 failed** · migration unapplied · **both keys absent**. Needs only owner actions 2+3. |
> | 4 | **T117** unified RBAC axes | ✅ confirmed w/ nuance | **17** commits with T117 in the *subject*, but only **2 of 10 ACs** done → genuinely mid-flight. ⚠️ `git log --grep T117` returns **25**; eight are other tickets citing it in the body. **Don't rank off that number.** |
> | 5 | **Fileless tickets** | ⚠️ **worse than filed** | **SIX** have no file: T111, T87, T90, T94, **T96** *and* T112 — and **T112 has no board row either** (its 6 `TASKS.md` hits are wikilink citations from other rows). Cited by T135/§0m/§0n but unfindable. **Blocks [[T137]]'s AC0.** |
> | 6 | **T138** identifier integrity | ✅ confirmed live | 🆕 P1 and **time-decaying**: `clients.email`/`leads.email` have **0** duplicate groups *today*, so `UNIQUE (lower(email))` is one migration now vs a reconciliation project later. |
> | 7 | **T137** audit service | ✅ confirmed | 🆕 P1 revenue. **Fast tier sellable well before full** (§30 puts deep mode last). Blocked on what *"register"* means. |
> | 8 | **T21 / T35 / T29 / T30** | ✅ confirmed | Four P1s whose **specs already exist** in `openspec/changes` (not archived) and pass strict validation — the expensive part is paid. T21 is explicitly *"awaiting approval"*: one decision converts spec → buildable. |
> | 9 | **§0q** 2 SDLC skills + STATE schema | ✅ confirmed, premise strengthened | Unticketed, **needs zero owner input**. This file is the argument for it. ⚠️ And per §0z, "versioned skills" is currently a **fiction** — don't add two more. |
> | 10 | **T136** WP → vinext | ✅ confirmed | 🆕 P1, blocked on one answer: **which WordPress sites?** Zero WP anywhere in the estate; Hostinger has **zero** WP installs. |
>
> **Dropped out of the top 10 vs the previous list (§0i)** — none by being resolved: T88, T91–T93,
> T131–T133. **Genuinely resolved since §0i:** T99(c), T121/T123/T124 (status-truth), T127 Phase 2.
>
> ### What landed this session
> - **T135 start gate** (`9dea5eda`) — all 5 owner questions answered and recorded as **binding spec
>   inputs**; AC2 re-scoped and **AC2a** added; board prose corrected. §0w has the four measurements.
> - **T136 + T137 filed** (GH **#97** / **#98**) — the two owner *business* asks, in a new
>   `💼 BUSINESS / SERVICE OFFERINGS` board section. **T137 was right-sized at the gate** — ROADMAP §30
>   already specifies both audit depths almost verbatim, so filing it as worded would have duplicated a
>   P1 epic. §0x.
> - **T138 + T139 filed** (GH **#99** / **#100**) — the DB-relations ask, split P1/P2 per owner. Grounded
>   **against the live database**, which corrected §0t **three times**. §0z.
> - **A full truth-validation pass over the hot 10** — 7 confirmed, 3 corrected. §0z.
> - `sync_github.py` exit 0 twice (`created=2 reused=95`, then `created=2 reused=97`). It takes several
>   minutes and prints nothing until it exits — **not a hang**.
>
> ### ❓ OPEN OWNER QUESTIONS (asked, unanswered — do not guess these)
> 1. **T136:** which WordPress sites? (estate unidentified — AC1 cannot start)
> 2. **T137:** what does *"register"* mean — signup surface · external marketplace listing · legally
>    registering an entity? AC5 assumes the first two.
> 3. **T137:** first paying customer profile, and whether the full tier is sold before deep mode exists.
