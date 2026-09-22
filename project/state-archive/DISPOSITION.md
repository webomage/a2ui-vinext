# STATE.md disposition record (T174 AC2)

**Every editorial section of `STATE.md` is accounted for here, exactly once.** This is not
documentation — it is **executable**: `just state-rotate` moves a *judged* section only because a row
below says `archived`, and `just state-check` **fails** when a section in `STATE.md` has no row here.

🔴 **Why an unaccounted section is a hard failure rather than a default-archive.** The risk in this
change was never a slow triage — it was **a lesson quietly dropped with nobody able to tell**.
`STATE.md` was the only record of several expensive findings, and the triage proved that concretely:
the section *"Gotchas from the earlier 2026-07-24 session"* held the **only standing reminder of a
live security gap** (`get-admin-metrics` comparing a service key with `!==`, flagged 🟡 in T124 —
which then closed as `done` while the code still carries it). A default-archive would have buried it.
It became **T175** before that section was allowed to move.

🔑 **Section ids survive into archive filenames on purpose.** Ten files carry **fourteen** inbound
references of the form ``STATE.md`` §0t (T126, T127, T135, T136 ×2, T137, T138 ×2, T139, T147, T172,
TASKS.md). Rewriting all of them would be churn with a real chance of error, so the id is preserved
in this table and in the archive filename instead — *"§0t"* still resolves. **A reference that no
longer resolves is the same failure as a deleted section.**

## Dispositions

**63 sections · 323,760 B accounted for**
· **archived** 56 · **kept-live** 7

⚠️ **`promoted-to-auto-memory` is ZERO, and that is the considered answer, not an omission.**
`MEMORY.md` loads on **every** session (~4k tok, unconditional); `STATE.md` is read **once**, and
only when an agent chooses to. So promoting content there converts an occasional cost into a
permanent one (T174 AC5). Every durable fact in the triaged sections was checked and found either
already homed — `UnicodeDecodeError`≠`OSError` in `stack-registry-discovery`, the skill-name-collision
lesson in `wom-skills-governance-gap`, the dead vitest suite in **TECH-DEBT D7**, the osv
advisory-refresh trap in `deps-toolchain-alignment` — or better placed in the **live §4**, which is
in the same repo and costs nothing until read. **The honest split promoted almost nothing.**

## Reconciliation — the arithmetic, not the assurance (AC2 · tasks §3.6)

Measured against `f9ea0ec1`, the last commit before rotation. **The `≥` is the whole point:**
nothing may be *lost*, and anything *gained* must be attributable to text the tool added.

| | bytes |
|---|---|
| old `STATE.md` | 339,508 (4,140 lines) |
| new `STATE.md` | 48,213 (449 lines) |
| 56 archive files | 319,994 |
| **new + archive** | **368,207** → **≥ old, by 28,699** ✅ |

**All 28,699 accounted for, none of it duplicated content:**

| addition | bytes | what it is |
|---|---|---|
| rotation headers | 12,231 | the 2-line provenance banner `state-rotate` prepends to each of the 56 files |
| 🗄️ archive index | 13,478 | the generated index table in `STATE.md` — the whole point of rotating |
| new prose | 2,990 | the still-true gotchas **condensed** into the live §4 before their dated sections moved |
| **total** | **28,699** | ✅ reconciles exactly |

⚠️ **That last row is the one to read sceptically, so state it plainly:** the live §4 keeps a
*condensed* form of gotchas whose full dated sections were archived. That is 2,990 B live against
~68 KB archived — a summary, not a second copy — but it is the only place this change put related
content in two files, and AC3's "one fact, one home" is about *facts*, not about a pointer to where
the long version lives.

**Verbatim, proven rather than asserted** (tasks §2.4): each archive's body, with its header
stripped, was matched as an exact substring of the pre-change file — **56 of 56 PASS**. This matters
because several archived sections are the only record of credential incidents; a tool that
"helpfully" reflowed one would be an unreviewed edit to a security record.

## The two surfaces — pre/post token cost (AC5 · tasks §4.3)

Counted with `tiktoken` `cl100k_base`. ⚠️ **Not Claude's tokenizer** — it is a *reproducible proxy*,
so read the ratio and not the absolute figure.

| surface | loaded | before | after | delta |
|---|---|---|---|---|
| `STATE.md` | once, if an agent chooses to | 97,988 | **15,237** | **−82,751** |
| `MEMORY.md` | **EVERY session, unconditionally** | 4,399 | **4,399** | **0** |
| **combined** | | **102,387** | **19,636** | **−82,751 (−80.8%)** |

🔑 **The second row is the result, not the first.** §4.3 carries an explicit STOP condition: if the
*combined* cost rose, the split was wrong and §3.2 had to be re-triaged rather than shipped. It
could easily have risen — draining 82k tokens of history into auto-memory would have cut `STATE.md`
just as hard while making the estate pay for it on **every** session forever. The always-on surface
did not move by a single token, because **nothing was promoted into it**. The 80.8% is real
because the row above it is zero.

| Section | Disposition | Bytes | Reason |
|---|---|---|---|
| `0-orient-2-min` | kept-live | 507 | The 3-step orientation a new agent needs before anything else. 507 B. |
| `pickup-session-start-preflight-is-live-t147` | kept-live | 8,655 | **The handoff itself** — job (b), the one thing this file exists for. Replaced each session; the previous one rotates out. |
| `pickup-evening-t165-phase-1-done-ac1b-closed` | archived | 25,159 | Superseded pickup block — matched **mechanically** by shape, no judgement involved. It was the current handoff once and was explicitly replaced. |
| `pickup-later-two-tickets-archived-t163-adopted-not` | archived | 4,686 | Superseded pickup block — matched **mechanically** by shape, no judgement involved. It was the current handoff once and was explicitly replaced. |
| `pickup-ast-grep-now-has-a-job` | archived | 3,350 | Superseded pickup block — matched **mechanically** by shape, no judgement involved. It was the current handoff once and was explicitly replaced. |
| `pickup-four-parsers-were-blind-to-the` | archived | 14,854 | Superseded pickup block — matched **mechanically** by shape, no judgement involved. It was the current handoff once and was explicitly replaced. |
| `pickup-t156-the-whole-cloudflare-workflow-layer` | archived | 4,845 | Superseded pickup block — matched **mechanically** by shape, no judgement involved. It was the current handoff once and was explicitly replaced. |
| `pickup-later session-t154-is-8-of-9-acs` | archived | 3,818 | Superseded pickup block — matched **mechanically** by shape, no judgement involved. It was the current handoff once and was explicitly replaced. |
| `pickup-t127-closed-for-real-ac5-s` | archived | 5,371 | Superseded pickup block — matched **mechanically** by shape, no judgement involved. It was the current handoff once and was explicitly replaced. |
| `0y12` | archived | 15,521 | Superseded pickup block — matched **mechanically** by shape, no judgement involved. It was the current handoff once and was explicitly replaced. |
| `0y11` | archived | 11,151 | Superseded pickup block — matched **mechanically** by shape, no judgement involved. It was the current handoff once and was explicitly replaced. |
| `0y10` | archived | 10,869 | Superseded pickup block — matched **mechanically** by shape, no judgement involved. It was the current handoff once and was explicitly replaced. |
| `0y9` | archived | 16,554 | Superseded pickup block — matched **mechanically** by shape, no judgement involved. It was the current handoff once and was explicitly replaced. |
| `0y8` | archived | 10,560 | Superseded pickup block — matched **mechanically** by shape, no judgement involved. It was the current handoff once and was explicitly replaced. |
| `0y7` | archived | 6,275 | Superseded pickup block — matched **mechanically** by shape, no judgement involved. It was the current handoff once and was explicitly replaced. |
| `0y6` | archived | 11,964 | Superseded pickup block — matched **mechanically** by shape, no judgement involved. It was the current handoff once and was explicitly replaced. |
| `0y5` | archived | 7,119 | Superseded pickup block — matched **mechanically** by shape, no judgement involved. It was the current handoff once and was explicitly replaced. |
| `0y4` | archived | 9,236 | Superseded pickup block — matched **mechanically** by shape, no judgement involved. It was the current handoff once and was explicitly replaced. |
| `0y3` | archived | 8,877 | Superseded pickup block — matched **mechanically** by shape, no judgement involved. It was the current handoff once and was explicitly replaced. |
| `0z` | archived | 5,989 | Dated validation of the 2026-07-25 hot-10 (7 confirmed / 3 corrected). The hot-10 is now GENERATED by `just tasks hot` and compared by `state-check`, so a hand-validated snapshot of it is superseded by construction. Its durable lesson — *a confident measurement is a claim with a method* — is already in the live header and in auto-memory `measurement-traps-w0m`. ⚠️ Referenced as `§0z` by T147, T172; resolvable via this record. |
| `0y2` | archived | 4,978 | Superseded pickup block — matched **mechanically** by shape, no judgement involved. It was the current handoff once and was explicitly replaced. |
| `0w` | archived | 5,386 | T135 start-gate findings. Already folded into T135's own ticket and spec, which is where grounding for an in-progress ticket belongs. |
| `0x` | archived | 3,914 | A filing record for two tickets that now exist with their own files and board rows. |
| `0y` | archived | 12,721 | Superseded pickup block — matched **mechanically** by shape, no judgement involved. It was the current handoff once and was explicitly replaced. |
| `0j` | archived | 3,578 | Completed work, dated. |
| `0k` | archived | 3,329 | Completed work, dated. T99 carries it. |
| `0l` | archived | 1,485 | Filing record; T134 exists. |
| `0v` | archived | 5,115 | Filing record; T135 exists and is in-progress with a full spec. ⚠️ Referenced as `§0v` by T137. |
| `0s` | archived | 4,865 | Completed work, dated. |
| `0p` | archived | 1,781 | Owner ask, since bundled into T135 (its strand B) and largely delivered — `docs-check` went 46 → 0 and is a live pre-push gate. ⚠️ Cited by TASKS.md's T135 row as *do not re-derive*; resolvable via this record. |
| `0q` | archived | 2,424 | 🔑 **This section is T174's own origin.** Its four deliverables: 1, 2 and 4 shipped under T145; deliverable 3 (*retention/pruning of resolved sections*) is what this change built. Archived because it is now fully discharged — quoted verbatim in T174's proposal, so the ask survives where the work is recorded. |
| `0m` | archived | 1,584 | Owner ask, bundled into T135 strand D. ⚠️ Cited by TASKS.md's T135 row and by `sdlc.json`'s T119 comment; resolvable via this record. |
| `0n` | archived | 6,693 | All four gaps approved and folded into T135 (1 of 4 built at the time; more since). ⚠️ Cited by T135 (`§0n gap 3`) and T172; resolvable via this record. |
| `0t` | archived | 4,291 | The original identifier-integrity sweep. ⚠️ **The most-referenced section in the file** — T138 and T139 both cite `§0t` as grounding and warn that it was CORRECTED THREE TIMES by a live-DB check. Archived rather than deleted precisely because those corrections only make sense against the original; the id survives in the archive filename. |
| `0u` | archived | 3,251 | Answered yes and folded into T135 strand C. ⚠️ Cited by T135 and T172. |
| `0g` | archived | 1,365 | Filing record; T132 exists. |
| `0h` | archived | 1,259 | Filing record; T133 exists. |
| `0i` | archived | 1,584 | A hand-ranked hot-10 from 2026-07-25. Superseded by the generated block at the top of this file — which exists *because* hand-ranking drifted, so keeping this alongside it would reintroduce the second copy T146 removed. |
| `0r` | archived | 5,966 | All 4 findings applied; a resolved record. ⚠️ Cited as `§0r` by T127. |
| `0` | archived | 5,875 | Completed build record, dated. T127 is archived. |
| `0a` | archived | 5,869 | The `mcp-builder` name-collision decision. Its durable lesson — *a shared skill name may mean two DIFFERENT skills; resolve by content diff, never by name* — is **already in auto-memory** (`wom-skills-governance-gap`), so promoting it again would create the two-copies drift AC3 forbids. |
| `0b` | archived | 2,322 | Completed. The *standing* half (`just discovery` gates stack drift) is already a rule in `CLAUDE.md`, so only the dated build record moves. |
| `0c` | archived | 839 | A recorded decision, dated; T64 carries it. |
| `0d` | archived | 1,847 | A 2026-07-25 list of scratch paths not to commit. Dated by nature and unverifiable now — `.gitignore` is the mechanism for this, not a prose list. |
| `0e` | archived | 2,845 | Filing record; T131 exists. |
| `0f` | archived | 1,796 | A different project, done there. ⚠️ Cited as `§0f` twice by T136. |
| `status-truth-t99-c-shipped-t134` | archived | 1,533 | Session log — history by definition. |
| `review-archive-t132-all-pushed-to` | archived | 1,897 | Session log — history by definition. |
| `2026-07-25-all-pushed-to` | archived | 2,931 | Session log — history by definition. |
| `gotchas-that-bit-the-r4-increment` | archived | 1,846 | Consolidated into the live `## 4. Gotchas the next agent MUST know` (still-true items only: the vendored-`git mv` re-stage trap and the unanchored-count regex time bomb). Archived after the merge, not before. |
| `gotchas-that-bit-the-2026-07` | archived | 2,915 | Consolidated into live §4 (the `cd`-reset, missing-file-hash, `grep -c` short-circuit and `just skill` cwd traps). Archived after the merge. |
| `2026-07-24-later-session-all` | archived | 1,067 | Session log — history by definition. |
| `2026-07-24-earlier-session` | archived | 1,870 | Session log — history by definition. |
| `gotchas-that-bit-the-later-2026` | archived | 2,294 | Consolidated into live §4 where not already homed — `UnicodeDecodeError`≠`OSError` is already in auto-memory `stack-registry-discovery`, and the dead vitest suite is already TECH-DEBT D7, so only the un-homed items moved. |
| `gotchas-from-the-earlier-2026-07` | archived | 1,047 | 🔴 **Held the only standing reminder of a LIVE security gap** — `get-admin-metrics` compares the service key with `!==` (non-constant-time), flagged 🟡 in T124 which then closed as `done` while `index.ts:21` still carries it. Filed as **T175** before archiving. This section is the reason AC2 refuses a default-archive. |
| `1a` | archived | 2,525 | T120 is `done` (verified in its frontmatter), so its blocked-on-Google state is history. |
| `1b` | archived | 3,089 | Shipped and verified 2026-07-24. ⚠️ Cited as `§1b` by T126. |
| `1-standing-thread-was-the-active` | kept-live | 435 | Names the standing thread (T117). Pointer, not content. |
| `1c` | archived | 6,011 | Explicitly *now folded into the spec* (validated 53/0), so the spec is the single home. |
| `done` | kept-live | 967 | Short trace of what is already on `origin/beta`. |
| `3-other-open-threads-in-tasks` | kept-live | 399 | Points at `TASKS.md`, which is the live queue. |
| `4-gotchas-the-next-agent-must` | kept-live | 7,666 | 🔑 The standing-gotcha home. **The four dated `Gotchas that BIT …` blocks were consolidated INTO here** rather than promoted to auto-memory — same repo, same git history, no always-on cost. This is the AC5-correct destination for a durable working gotcha. |
| `5-how-to-continue` | kept-live | 2,946 | The continuation protocol. Instruction, not history. |

## Key → heading

The full heading each key refers to, so a key can be resolved without opening the archive.

| Key | Heading |
|---|---|
| `0-orient-2-min` | 0. Orient (2 min) |
| `pickup-session-start-preflight-is-live-t147` | ⭐ PICK UP HERE — 2026-08-07 — **Session-start preflight is LIVE (T147 AC5/AC6/AC7, AC1 half) · both Obsidian vaults now reachable over MCP with the declaration corrected  |
| `pickup-evening-t165-phase-1-done-ac1b-closed` | ⭐ (was) PICK UP HERE — 2026-08-06 (evening) — **T165 Phase 1 DONE (AC1b closed: two CV schemas, one gate, 20 probes across three layers) · T166 + T169 ARCHIVED · T172/T17 |
| `pickup-later-two-tickets-archived-t163-adopted-not` | ⭐ (was) PICK UP HERE — 2026-08-06 (later) — **TWO tickets ARCHIVED (T163 adopted-not-proven, T168 with the schema salvaged), T166+T169 built to 100%, T170 reframed to "ma |
| `pickup-ast-grep-now-has-a-job` | ⭐ (was) PICK UP HERE — 2026-08-06 — **ast-grep now has a job and found 4 unpinned Deno specifiers nothing was enforcing; serena had TWO boot failures, both caused by the  |
| `pickup-four-parsers-were-blind-to-the` | ⭐ (was) PICK UP HERE — 2026-08-05 — **FOUR parsers were blind to the board at once (a formatting change broke `state-check`, `sdlc-doctor`, `backfill-tickets` AND `just g |
| `pickup-t156-the-whole-cloudflare-workflow-layer` | ⭐ (was) PICK UP HERE — 2026-08-01 — **T156: the whole Cloudflare Workflow layer was DEAD — two repos deployed to one script name, all 19 Workflows orphaned since 2026-07- |
| `pickup-later session-t154-is-8-of-9-acs` | ⭐ (was) PICK UP HERE — 2026-07-31 (later session) — **T154 is 8 of 9 ACs: the exposure RATCHET is live (`just mcp-ratchet`), its cadence is `just audit` outside `--quick` |
| `pickup-t127-closed-for-real-ac5-s` | ⭐ (was) PICK UP HERE — 2026-07-31 — **T127 CLOSED for real (AC5's resolver only ever worked from wom7web); TWO canonical skills were verbatim upstream copies mislabelled  |
| `0y12` | 0y12. superseded pickup block — 2026-07-28 — **T151 AC1 DONE (the graphify/codegraph call-site map) and T107 CLOSED as not-reproducible. T151's AC6 was resolved by measur |
| `0y11` | 0y11. superseded pickup block — 2026-07-27 — **T131 AC3 AND AC4 are DONE and PUSHED: the canonical skill library has a provenance record, 39 skills carry a version that M |
| `0y10` | 0y10. superseded pickup block — 2026-07-26 (LATE) — **T149's first blocker is CLEARED (`skills.ts` no longer selects on the `w0m` prefix) and T131 AC1 is DONE (one declar |
| `0y9` | 0y9. superseded pickup block — 2026-07-26 (QUOTA PAUSE #2) — **T135 §6 DONE, GATE LIVE AT PRE-COMMIT · the 36-issue sync RAN · 3 new owner directives filed (T142/T143/T14 |
| `0y8` | 0y8. superseded pickup block — 2026-07-26 (QUOTA PAUSE #1) — **T135 §4 + backfill.** ✅ **Its §4 content is still accurate. 🛑 Its "ONE UNPUSHED COMMIT NEEDS AN OWNER DECIS |
| `0y7` | 0y7. superseded pickup block — 2026-07-26 (LATEST) — **T135 §4 done.** ✅ **Still accurate on §4; superseded on repo state, the hot-10 and the unpushed commit — use the ⭐  |
| `0y6` | 0y6. superseded pickup block — 2026-07-26 (LATE) — **T135 build: sections 0–3 DONE.** ✅ **§4 IS NOW ALSO DONE — see the ⭐ block above. Its "next action: §4" is COMPLETE;  |
| `0y5` | 0y5. superseded pickup block — 2026-07-26 (DAY) — **T135 sections 0/1/2 done.** ✅ **§3 IS NOW ALSO DONE — see the ⭐ block above. Its "next action: task 3.1" is COMPLETE;  |
| `0y4` | 0y4. superseded pickup block — 2026-07-26 (EARLY HOURS) — **Session ended on QUOTA, not on a problem. All 3 tracking fixes APPLIED. T135's spec is WRITTEN and strict-vali |
| `0y3` | 0y3. superseded pickup block — 2026-07-25 (LATE NIGHT) — **Session ended on QUOTA, not on a problem. Tree clean, everything pushed. Next action: apply 3 evidence-backed t |
| `0z` | 0z. 🔎 TRUTH-VALIDATION PASS — 2026-07-25 (late night). Owner asked to validate the hot 10. **7 confirmed, 3 corrected.** DO NOT RE-DERIVE. |
| `0y2` | 0y2. superseded pickup block — 2026-07-25 (NIGHT) — **T135 is UNBLOCKED and STARTED: all 7 open owner questions are ANSWERED. Two business tickets filed (T136/T137). The  |
| `0w` | 0w. 🔎 MEASURED 2026-07-25 (night) at T135's start gate — four findings that changed the ticket's scope. DO NOT RE-DERIVE. |
| `0x` | 0x. 🆕 FILED 2026-07-25 (night) — T136 + T137, the two owner BUSINESS asks. New board section. |
| `0y` | 0y. superseded pickup block — 2026-07-25 (LATE EVENING) — **T99(d) 3.2–3.4 BUILT & PUSHED. `wom7md` is now gated. SIX owner asks are open; five arrived this session and a |
| `0j` | 0j. ✅ DONE 2026-07-25 (later) — the status-truth cleanup. Verified, not assumed. |
| `0k` | 0k. ✅ DONE 2026-07-25 (evening) — T99 (c): the orphaned identity subsystem is GONE from prod |
| `0l` | 0l. 🆕 FILED 2026-07-25 — T134: unified service & connection registry (owner ask) |
| `0v` | 0v. 🆕 FILED 2026-07-25 — T135: repo-hygiene gates (**bundles §0n + §0p + §0u + §0m**). Needs a spec. |
| `0s` | 0s. ✅ BUILT 2026-07-25 (late) — T99 (d) sections 3.2–3.4: the crypto helper is real and tested |
| `0p` | 0p. 🆕 OWNER ASK 2026-07-25 (late) — README + standard human-facing files, enforced by SDLC. GROUNDED, unbuilt. |
| `0q` | 0q. 🆕 OWNER ASK 2026-07-25 (late) — two new SDLC skills + a STATE.md schema + STATE settings in `sdlc.json`. GROUNDED, unbuilt. |
| `0m` | 0m. 🆕 OWNER ASK 2026-07-25 (evening) — enforce Infisical for secrets in w0m skills + tools. **Owner said FILE AND BUILD.** Unstarted. |
| `0n` | 0n. OWNER ASK 2026-07-25 — per-repo SDLC check gaps. **ASKED & ANSWERED: all four approved. 1 of 4 BUILT.** |
| `0t` | 0t. 🆕 OWNER ASK 2026-07-25 (late) — DB relations on indexed identifiers. **DEEPLY GROUNDED — DO NOT FILE AS ASKED.** |
| `0u` | 0u. 🆕 OWNER QUESTION 2026-07-25 (late) — should the SDLC audit package/lib licenses? **ANSWER: yes. Grounded, unbuilt.** |
| `0g` | 0g. 🆕 FILED 2026-07-25 — T132: `w0m-pixel-clone` (lightweight pixel-perfect parse & copy) |
| `0h` | 0h. 🆕 FILED 2026-07-25 — T133: recover temporary DS proposals from the Claude Design exports |
| `0i` | 0i. 🔥 The ranked "hot 10" (owner asked 2026-07-25) — grounded against the live queue |
| `0r` | 0r. ✅ RESOLVED: the `review` gate — all 4 findings APPLIED (was: verified, unapplied) |
| `0` | 0. T127 Phase 2 — **BUILD DONE 2026-07-25** (spec + all 4 requirements) |
| `0a` | 0a. 🔴 The one owner decision taken mid-build — `mcp-builder` was a NAME COLLISION, not drift |
| `0b` | 0b. ✅ DONE 2026-07-24 — T130 (per-stack registry + `just discovery`) — **STANDING GATE** |
| `0c` | 0c. DONE & PUSHED 2026-07-24 — T64 SDLC/DevOps framework DECISION |
| `0d` | 0d. Disposable scratch (do NOT commit) |
| `0e` | 0e. 🆕 FILED 2026-07-25 — T131: the w0m version schema is enforced NOWHERE |
| `0f` | 0f. 1945 (separate project) — DONE there, **continues in its OWN session** |
| `status-truth-t99-c-shipped-t134` | Session log — 2026-07-25 (EVENING session — status-truth, T99(c) shipped, T134 filed; all pushed) |
| `review-archive-t132-all-pushed-to` | Session log — 2026-07-25 (LATER session — review→archive + T132; all pushed to `beta`) |
| `2026-07-25-all-pushed-to` | Session log — 2026-07-25 (all pushed to `beta`) |
| `gotchas-that-bit-the-r4-increment` | 🔴 Gotchas that BIT the R4 increment (2026-07-25, later) |
| `gotchas-that-bit-the-2026-07` | 🔴 Gotchas that BIT the 2026-07-25 session (read these first) |
| `2026-07-24-later-session-all` | Session log — 2026-07-24 (later session; all pushed to `beta`) |
| `2026-07-24-earlier-session` | Session log — 2026-07-24 (earlier session) |
| `gotchas-that-bit-the-later-2026` | 🔴 Gotchas that BIT the LATER 2026-07-24 session (read these first) |
| `gotchas-from-the-earlier-2026-07` | 🔴 Gotchas from the earlier 2026-07-24 session (still true) |
| `1a` | 1a. T120 Safe Browsing sweep — ✅ DONE 2026-07-24 (agent side); now **blocked** on Google + owner |
| `1b` | 1b. Shipped + LIVE (T123 / T49 / T124) — ✅ committed **and pushed** (verified 2026-07-24) |
| `1-standing-thread-was-the-active` | 1. Standing thread (was the active one): T117 (RBAC redesign) |
| `1c` | 1c. Owner schema additions — 2026-07-23 (✅ NOW FOLDED INTO THE SPEC — validated 53/0) |
| `done` | 2. Shipped earlier (all on origin/beta — done) |
| `3-other-open-threads-in-tasks` | 3. Other open threads (in TASKS.md) |
| `4-gotchas-the-next-agent-must` | 4. Gotchas the next agent MUST know |
| `5-how-to-continue` | 5. How to continue |
