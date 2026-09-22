<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0y9. superseded pickup block — 2026-07-26 (QUOTA PAUSE #2) — **T135 §6 DONE, GATE LIVE AT PRE-COMMIT · the 36-issue  -->

### 0y9. superseded pickup block — 2026-07-26 (QUOTA PAUSE #2) — **T135 §6 DONE, GATE LIVE AT PRE-COMMIT · the 36-issue sync RAN · 3 new owner directives filed (T142/T143/T144).** ✅ **Still accurate on §6 and on T142/T143/T144. 🛑 Its "next build action: `tasks.md` §5" is still true but no longer the FIRST action — use the ⭐ block above. Its repo table and hot-10 are superseded.**

> **Written for an agent with none of my context. Paused on QUOTA, not on a problem.**
> **Everything is pushed.** The only dirty file in `wom7web` is a one-line `gh_issue:` writeback the
> ticket-sync just made — `git add -A && git commit -m "chore: record GH issue number for T144"`.
>
> ### ✅ THE PUSH DECISION FROM THE LAST BLOCK IS RESOLVED — do not re-ask it
> The owner chose **"push and let it sync"**. It ran: **`created=36 reused=101 project=#2`**, no
> crash. The `1838518f` parsing fix held and the ticket mirror is healthy. Nothing is held back any
> more. **The previous block's 🛑 warning is HISTORY — ignore it.**
>
> ### 📍 STATE
> | Repo | dirty | unpushed | HEAD |
> |---|---|---|---|
> | `wom7web` | **1 (trivial — see above)** | 0 | `16fe1719` |
> | `wom7api` | 0 | 0 | `7befe06` |
> | `wom7cfworkers` | 0 | 0 | `1721db5` |
> | `wom7md` | **3 — THE OWNER'S, NOT YOURS** | 0 | `37a5a63` |
> | `wom7skills` | 0 | 0 | `af3752d` |
> | `wom7ext` | 0 | 0 | `49035a9` |
> | `wom7sec` | 0 | 0 | `6d954d5` |
> | `wom7mlx/wom7mlx` | **10 (NOT MINE)** | **3 — `git log @{u}..` LIES here** | `0d70046` |
>
> ⚠️ **`wom7md`'s 3 dirty paths are the OWNER's Obsidian work** (`.gitignore`,
> `.obsidian/community-plugins.json`, `.obsidian/plugins/`) — they installed plugins this session.
> **Do not commit them for them**, and note `.obsidian/plugins/` is untracked vendor content.
> ⚠️ **`wom7mlx/wom7mlx` still has NO UPSTREAM on `beta`**, so `git log @{u}..` returns **0
> spuriously**. Real figure via `git log origin/beta..HEAD` is **3**, one (`bd70433`) not mine. Its 10
> dirty paths are another agent's logits-mismatch work — **do not touch or reformat.**
>
> ### ▶ START HERE
> 1. `git pull` everywhere (a parallel Antigravity agent also commits to `beta`).
> 2. Commit the one trivial writeback above.
> 3. **Build: `openspec/changes/2026-07-25-repo-hygiene-gates/tasks.md` §5 (license).** It is the
>    **last** T135 strand — §0–4 and §6 are all ticked with observed exit codes. Then §7/§8 close-out.
> 4. **Re-run, don't re-read:** `python3 project/scripts/hygiene_preflight.py` (~2s, exit 0).
>
> ### ✅ WHAT LANDED THIS SESSION
> | Commit | Repo | What |
> |---|---|---|
> | `d6afbbad` | wom7web | **§6 green + gate promoted to pre-commit & wired** |
> | `7befe06` | wom7api | stop reading secrets from files; retire 2 dead `.env` tools |
> | `af3752d` | wom7skills | name the manager in `sourcing-integration` |
> | `49035a9` | wom7ext | gitignore `.infisical.json`; exemption lapsed |
> | `64a98787` `16fe1719` | wom7web | **T144 filed** (+AC8) |
> | `743955ab` | wom7web | GH issue numbers for T142/T143 |
>
> **`secrets-check` exits 0 and is PROMOTED `manual` → `pre-commit` AND wired in `.husky/pre-commit`**
> (~0.9s). It ran green on its own commit. Final: `scanned_files=143, corpus_total=40,
> corpus_consuming=7, corpus_prose_only=4, corpus_offenders=0`.
>
> ### 🔴 §6's HEADLINE — the gate was UNDER-DETECTING BY 8×, and one pattern could never fire
> **1. The recorded "11 findings / 2 real leaks" baseline was really 16 offending files.** Two causes,
> both the *same unguarded-collection shape* as §4:
> - **`scan_globs` omitted `*.mjs`, `*.cjs`, `*.ts` and every subdirectory** — 14 scripts were never
>   handed to the patterns. `scanned_files` **103 → 143** on widening it. ⇒ **A pattern that matches
>   nothing because no file reached it is indistinguishable from a clean estate. The glob set is half
>   the gate.**
> - **No pattern matched a dotenv LIBRARY load** (`dotenv-source` is shell-shaped). And a dotenv load
>   **fails silently** when the file is absent — so 14 scripts read as working while supplying nothing.
>
> **2. 🔴 `wom7api/dev_secrets.json` — 21KB plaintext dump of 83 LIVE secret values in the working
> tree**, read by two tracked scripts. Gitignored, **never committed** (checked against all refs), and
> **fully redundant** (all 83 names present in Infisical's 96). mtime 2026-06-03 ⇒ predates the July
> rotations ⇒ probably **stale** credentials. Both readers were also broken (looked for
> `secretKey`/`secretValue`; the file uses `key`/`value`) inside a bare `except: pass`. And
> `sync_supabase_secrets.py:63` printed **`val[:12]`** — 12 chars of a live `SERVICE_ROLE_KEY` — to
> stdout. ⇒ **OWNER ACTION: delete the file.** Nothing reads it now; it is untracked, so an agent must
> not delete it for them.
>
> **3. 🔴 `secret-file-read` was STRUCTURALLY VACUOUS — it could not fire in ANY file, ever.** Its red
> probe returned **exit 0** where 1 was expected. `code_match` skips a match lying wholly inside one
> quoted span (so `add(SKIP, "infisical export failed")` prose isn't read as a call) — but **a filename
> in real code is always a string literal.** ⇒ **Whether a literal is prose or is itself the offence is
> a PER-PATTERN fact**, hence the new `match_in_string` flag. **Second time in this change that the
> thing built to catch a vacuous pass was itself vacuous** (§4's `docs-check` was the first).
> ⇒ **A green gate is not evidence. A red probe is.**
>
> **4. 🔴 8 of 9 skills findings were FALSE POSITIVES, and the obvious fix was HARMFUL.** The check
> demanded the literal `infisical`, flagging all five `w0m-sdlc-*` skills — which correctly reference
> **`{secrets.run}`**, the `.w0m/sdlc.json` indirection resolving to `infisical run --env=dev --`.
> **CLAUDE.md requires** those skills to read the command from config, so **an agent appeasing this
> gate would have made the project-agnostic skills project-specific.** It also flagged a skill for the
> *rule* **"never log secrets"** and another for "Invalid Credentials" in an example scenario. Now
> two-tier: **consumption** obliges naming the manager, a **prose mention** does not. Real offender: 1.
> ⚠️ `corpus_consuming` (**7**) is recorded in policy as the number to watch — an earlier candidate
> signal cut it to **1 of 40**, which would have been near-vacuous. **If it drifts toward 1, the signal
> over-narrowed; the estate did not improve.**
>
> ### 🆕 §6.3 — `wom7ext`'s SECRETS EXEMPTION HAS LAPSED (its own trigger fired)
> `extension/build.js:38` injects `process.env.SUPABASE_PUBLISHABLE_KEY` **at build time** and
> `extension/tests/e2e/steps/world.js` reads `GEMINI_API_KEY`/`MISTRAL_API_KEY` — each with `|| ""`, so
> a **missing secret degrades to an empty string instead of failing.** Done: `.infisical.json` created
> (same workspace as web/api/cf) + the ignore rule that repo lacked. **STILL OPEN:** run its
> build/test through `infisical run` and make the `|| ""` fallbacks fail loudly.
> ✅ `wom7sec` re-confirmed by measurement (3 code files, **zero** secret refs). Same condition,
> opposite verdict — that is why 6.3 says *decide*, not *re-assert*.
>
> ### 🗣️ THREE NEW OWNER DIRECTIVES — filed, grounded, NOT started
> | Ticket | GH | What, and the measured fact that shapes it |
> |---|---|---|
> | **T142** P1 | **#139** | **Gherkin → Gauge, completely.** Gherkin stays ONLY as a customer-project SDLC tool. Measured: `wom7web` **0 `.feature` / 363 `.spec`** ✅ and `wom7api` **0 / 12** ✅ are already fully Gauge. Targets: **`wom7ext` 7** + their Cucumber `*.steps.js`, **`wom7mlx` 2**. ⚠️ **Size by STEP files, not feature files.** 🔴 wom7mlx holds a 3rd, untracked `.feature` from the parallel agent — coordinate. |
> | **T143** P2 | **#140** | **Cross-browser `wom7ext`.** `extension-ff` measured **abandoned**: **0 tracked files** (fully gitignored), **0 files touched since Jan 2026**, **Manifest V2** vs `extension/`'s MV3, different name, `0.1.0` vs `2026.12.25.495632`. **Do not resurrect it** — derive from the live MV3 source via a build-time target switch, not a second fork. |
> | **T144** P1 | **#141** | **Obsidian over MCP/WebMCP + MCP-first transport everywhere.** Survey: w0m exposes MCP in **exactly two** places — `wom7ext` (real: `McpServer` over WS, **25 tools** in 8 modules, wired from `background.ts`) and `packages/mcp-aws-fundamentals` (stdio, not a platform surface). 🔴 **No `/api/mcp` anywhere**; `wom7cfworkers` declares the MCP SDK with **zero `src/` references**; **T21's WebMCP spec is strict-valid but UNBUILT**; the vault has **zero** MCP refs. **No Obsidian MCP server was connected to the session** ⇒ that is AC1. AC8: **128 tracked `.mmd`**; the vault already renders Mermaid in **38 notes via fences but holds zero `.mmd`** — pick the canonical form first. |
>
> 🔴 **T144 COLLIDES WITH T51** (P1, queued): *"Implement Obsidian Vault ZIP import in Resource
> Library"* is a **file-based** vault import that the MCP-first directive reframes. **Resolve T51
> before building either.** T144 may belong as an epic sequencing T21/T26/T51.
>
> ### 🔨 IN FLIGHT, DECIDED BUT UNBUILT — STATE.md self-maintenance (needs a T-id, use **T145**)
> The owner asked for **SDLC + git-hook triggers to update STATE.md**, plus **save/load STATE skills**.
> I surveyed and designed it but ran out of quota before building. **Do not re-derive this:**
> - **There is NO save/load STATE skill.** `wom7skills/skills/w0m/w0m-handoff` looks like it but is
>   **not** it: it emits a copy-pasteable *prompt* for a new context window, is **interactive** (asks
>   5 questions, so it can never run from a hook), **never reads or writes `STATE.md`**, and is **not
>   in the T127 registry**.
> - **Zero mechanical enforcement exists today** — `STATE.md` appears in **no** hook, no
>   `.pre-commit-config.yaml` entry, no justfile recipe, no `sdlc.json` stage. It is maintained purely
>   by convention, which is exactly why it went stale *within this session*.
> - **The load-bearing design constraint:** STATE.md is mostly **editorial judgement** (the hot-10
>   ranking, "lessons worth carrying") which a hook cannot author. But the parts that actually went
>   stale — **the repo/dirty/unpushed table, gate exit codes, counts** — are **purely mechanical and
>   should never be hand-written.** Split it on that line.
> - **TWO OWNER DECISIONS ALREADY MADE — do not re-ask:**
>   1. **`pre-push`, BLOCKING** (matches where `docs-check` lives; pushes are the handoff boundary).
>   2. **VERIFY-ONLY — the skills do the writing.** The hook measures, compares, and fails with the
>      exact diff telling you to run `just state-save`. **It must NOT rewrite/re-stage `STATE.md`
>      itself** — a hook mutating a tracked file mid-commit needs re-staging and can fight the commit.
> - **Planned shape:** `project/scripts/state_doctor.py` with `--render` / `--check` / `--write`;
>   a marker-delimited managed block inside STATE.md; `just state-check` + `just state-save` declared
>   in `project/stacks-policy.json` (T130 `commands` contract); wired into `.husky/pre-push`; two new
>   skills `w0m-state-save` / `w0m-state-load` in `wom7skills/skills/w0m/` **added to
>   `.w0m/skills.json`** (⚠️ §0z: "versioned skills" is currently a fiction — don't add two more
>   unversioned ones).
> - **Staleness rule must be STABLE, or it blocks every push.** Do **not** compare raw HEADs. Fail on:
>   no managed block · recorded **gate exit codes** ≠ measured · recorded **rowless-ticket set** ≠
>   measured · recorded **dirty-repo set** ≠ measured · wom7web's recorded head **not an ancestor** of
>   HEAD (diverged/rewritten) or **>10 commits** behind. That blocks on material drift, not on a typo
>   fix. **`w0m-state-load` must RE-RUN the measurements rather than trust them** — that is this
>   file's own first instruction.
> - 🔴 **AC7 applies to itself:** prove the staleness gate RED (hand-edit a recorded exit code → exit 1)
>   before believing it, and prove it fails on an **empty/absent** block rather than passing.
>
> ### 🔥 THE HOT 10 — re-measured 2026-07-26
> | # | Item | State / next action |
> |---|---|---|
> | 1 | **T135 §5 license** | 🟡 **Last strand blocking T135 close-out.** 233 findings measured. Includes a **live compliance defect**: `wom7ext/extension/src/vendor/mcp-sdk` ships in the bundle with **no retained MIT notice** — and it now matters more, being the SDK behind the MCP surface the owner just made preferred transport. One open design call: ~114 vendored skills → a central `license` field in `.w0m/skills.json`, **not** 114 `LICENSE` files. |
> | 2 | **Delete `wom7api/dev_secrets.json`** | 🔴 **Owner, one command.** 83 plaintext secret values, proven redundant, nothing reads it. |
> | 3 | **T120 Safe Browsing (P0)** | 🔵 `blocked`, review requested 2026-07-22, verdict pending. 🆕 **Cheap unblock found: `SAFE_BROWSING_API_KEY` is ABSENT**, so the audit only emits a *staleness nudge*. Provisioning it turns a guess into an authoritative check on a P0. |
> | 4 | **T99(d) connector tokens (P0)** | 🟡 **Verified still blocked today: `CONNECTOR_TOKEN_KEY_V1` is ABSENT.** Migration `20260725180000_t99_add_encrypted_token_columns.sql` present, unapplied (pointless before the key). Sections 4–7 unblock immediately after. |
> | 5 | **T144** Obsidian/MCP | ⚪ Filed today. **Collides with T51** — resolve that first. AC1 (get the Obsidian MCP server actually connected) gates the rest. |
> | 6 | **T142** Gherkin→Gauge | ⚪ Filed today, scope measured, zero open questions except the wom7mlx collision. |
> | 7 | **The 6 rowless tickets** | 🔴 Still flagged: **T2 (`in-progress`!), T25, T32, T35, T48, T66.** Invisible in the queue humans read. **Editorial call on placement — ask, don't place.** |
> | 8 | **T117 unified RBAC axes** | 🟡 2 of 10 ACs, live spec `2026-07-22-rbac-unified-axes`. Biggest remaining product piece. |
> | 9 | **T21 WebMCP** | ⚪ Spec strict-valid, unbuilt; **elevated by the MCP-first directive** and a prerequisite for T144 AC3. Needs one approval. **T26** would give the cfworkers SDK dep an implementation. |
> | 10 | **T140 dep upper bounds** / **T143** | ⚪ All 9 floors share the unbounded shape that silently took the web test suite offline. T143 sequenced after T142. |
> **Plus unticketed:** **T145** above (STATE self-maintenance) · debt **D24** (3 committed `tsc` outputs in `scripts/` with no build script).
>
> ### ⚠️ TOOLING TRAPS BANKED — each cost real work
> - 🔴 **`git checkout -- <file>` to undo a red probe DESTROYED MY OWN UNCOMMITTED FIXES.** The tree
>   looked restored while the leak was silently back; only the final GREEN run (exit 1) caught it.
>   ⇒ **Never `git checkout --` a dirty file to remove a probe. Copy it aside and restore from the
>   copy, or commit first.** Same family as the recorded *"commit before a bulk delete-and-regenerate"*.
> - 🔴 **`cmd | tail -N` HID A FAILED COMMIT** — the commit was rejected by a hook, the pipeline
>   reported success, and I nearly reported work as landed. **This file already warns about this for
>   `tee` and `${pipestatus[1]}`; I hit it anyway.** ⇒ Redirect to a file and check the real `$?`.
> - 🔴 **Writing prose ABOUT a mermaid fence created a real one.** A literal triple-backtick
>   `mermaid` opener inside T144's text was parsed by the `mmd-validate` hook as a diagram and failed
>   the commit. ⇒ **Documenting a fence and opening one are the same bytes.** Use inline code. Same
>   class as a gate firing on the comments that document its own fix.
> - **oxlint rejects unknown keys in `.oxlintrc.json`** — you cannot leave a `_note` field there;
>   rationale must go in the commit/TECH-DEBT instead.
> - **Editing a compiled `.js` stages machine-generated code into the lint gates.** Three
>   `scripts/*.js` are committed `tsc` output with **no build script** (debt **D24**); their `__awaiter`
>   helper trips `no-unused-expressions`. **Don't edit generated code to satisfy a linter.**
>
> ### 🔴 OWNER ACTIONS — now FOUR
> 1. **Delete `wom7api/dev_secrets.json`** (new — 83 plaintext secret values on disk).
> 2. **Revoke the `casualuser` GitHub token** (id `1243074`) — dropping the DB row did not revoke it.
> 3. **T99(d) 3.1 — provision `CONNECTOR_TOKEN_KEY_V1`** (`openssl rand -base64 32` → Infisical, v1).
>    **Verified absent today. Do not let an agent invent key material.**
> 4. **T99(d) 3.5 — apply migration `20260725180000`** (pointless before 3).
> **Plus:** place the **6 rowless tickets** · T136/T137's three open questions · **T120** (P0 —
> and note `SAFE_BROWSING_API_KEY` is absent, which is why it can't be checked from here).
