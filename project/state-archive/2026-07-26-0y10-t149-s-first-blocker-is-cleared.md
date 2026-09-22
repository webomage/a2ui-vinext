<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0y10. superseded pickup block — 2026-07-26 (LATE) — **T149's first blocker is CLEARED (`skills.ts` no longer selects -->

### 0y10. superseded pickup block — 2026-07-26 (LATE) — **T149's first blocker is CLEARED (`skills.ts` no longer selects on the `w0m` prefix) and T131 AC1 is DONE (one declared version format, one producer, gated at pre-push — it found 3 orphaned producers where the audit recorded 1). Next: T131 AC3's prerequisite — `wom7skills` has no provenance record of its own — or T135 §5 license.** ✅ **Its T149-narrowing and T131-AC1 content is still accurate. 🛑 Its headline next action — "T131 AC3's prerequisite" — is DONE; use the ⭐ block above. 🔴 Its AC3 section says several of the 13 unknown-origin skills "read as vendored": resolving them by CONTENT proved all 13 NATIVE. Its repo table is superseded.**

> **Written for an agent with none of my context. Everything below was measured this session.**
>
> ### 📍 STATE — all repos clean and pushed except the owner's own work
> `wom7web` `wom7skills` `wom7api` all committed and pushed on `beta`. `wom7md`'s 5 dirty paths are
> **the OWNER's Obsidian work — do not commit them.** `wom7mlx/wom7mlx` has no upstream on `beta`, so
> `git log @{u}..` reports 0 **spuriously**; use `git log origin/beta..HEAD`. The generated
> MECHANICAL STATE block at the top of this file is the authority on counts — and re-run
> `just state-check` rather than trusting it.
>
> ### ✅ WHAT LANDED THIS SESSION
> | Commit | Repo | What |
> |---|---|---|
> | `fbf95910` | wom7web | T149's registry entry + GH issue #145 — **writebacks the T149 commit missed** |
> | `4634253` | wom7skills | **the narrowing** — manifest decides which skills install, +10 tests |
> | `8bd8cba` | wom7api | justfile recipe comments follow the new rule (wom7web's justfile is a symlink to it) |
>
> ### 🔴 THE BUG IN THE PREVIOUS COMMIT — read this before trusting a "landed" claim
> `9d0318f1` filed T149 and reported it done. **`project/tickets.json` was `git add`-ed after the
> T127 priority edit and BEFORE the T149 entry was appended**, so the commit captured the index, not
> the worktree: T149 existed as a ticket file and a `TASKS.md` row but was **absent from the
> machine-readable registry the ranker reads.** The hot-10 recorded in that same commit's `STATE.md`
> was generated from a file state that was never committed — a fresh checkout would have ranked
> without T149 at all. **`just state-check` does not compare the hot list, so nothing caught it.**
> ⇒ The measured thing and the committed thing were different objects. **Verify with
> `git diff --cached`, or stage last.** Fixed in `fbf95910`; 144 tickets now parse.
>
> ### ✅ T149's FIRST BLOCKER IS CLEARED — skill promotion is unblocked
> `skills.ts` selected with `name.startsWith("w0m") || alreadyInstalled`. **A prefix was doing policy
> work:** every future top-level `w0m*` name was auto-enrolled into every consumer, so *promoting* a
> skill — [[T128]] has **11** waiting under `skills/w0m/` — would have changed what every project
> receives with **no declaration step anywhere**. `w0m-ui-expert` would have landed in Tailwind-free
> projects. Now the **target's `.w0m/skills.json` decides**, with a new `wom7skills/bootstrap.json`
> for a project that has no manifest at all, plus (unchanged) any canonical skill already installed.
> - **This makes [[T149]] AC5's two-repo rule a MECHANISM, not a paragraph** — forget the consumer
>   manifest entry and the skill is simply not installed, *loudly*, instead of appearing everywhere
>   quietly. AC5 is ticked because the doc and the enforcement landed together.
> - ⚠️ **Zero behaviour change on the live estate, by design.** `bootstrap.json` lists the same 15
>   names the prefix matched; `just skills-sync` selects **17 of 30** for wom7web before and after,
>   and a real sync left wom7web's tree byte-identical. **That is exactly why the live tree cannot
>   distinguish the two rules** — the 10 new tests drive fixture canonical trees through a
>   `W0M_SKILLS_SRC` seam, or they would prove nothing.
> - **Proven RED, not merely green:** restoring the old prefix line fails exactly the **3** selection
>   tests and passes the **6** guards — the correct signature, not just "some tests went red".
>   (Probe removed by restoring from a copy; `git checkout --` on a dirty file is a recorded trap.)
> - Every wrong-set path now **fails instead of degrading**: unreadable manifest does *not* fall back
>   to bootstrap (a typo in a project's JSON would have installed skills it declined), missing/empty
>   `bootstrap.json` does *not* fall back to the prefix, a bootstrap name matching no canonical skill
>   is an error rather than one silent install fewer, and an empty canonical source is refused rather
>   than reported as `0 skills in sync ✓`. The sync now prints **which set it enumerated**.
>
> ### 🔴 INSTANCE 6 OF THE ORGANISING FAILURE MODE — found in the test runner, while building the fix
> `--test tests/` **will not resolve under tsx at all**, and `--test "tests/*.test.ts"` **exits 0
> having run ZERO tests** when the glob matches nothing. The gate proving the anti-vacuity fix was
> itself capable of a vacuous pass. Both test files are now **named explicitly** in `skill-test`, and
> a **meta-test fails if a `tests/*.test.ts` file on disk is not wired into the script**.
> ⇒ T149's count of instances keeps rising because the shape is now being *looked for*, not because
> the estate is getting worse. Suite: **47/47**, wired at `wom7skills`' pre-commit.
>
> ### 🟡 T131 STARTED — AC1 DONE, and the audit it was built on was wrong
> `.w0m/sdlc.json → versioning` now declares the format, regex, **one** producer (`just version`),
> the scan set and the exemptions-with-reasons. **`just version-check` gates it, BLOCKING at
> pre-push** (~0.45s, beside `docs-check`/`state-check`); `just version-test` is 19/19 with every
> check proven RED. Policy is **data** — a test feeds an impossible regex to prove the checker
> carries none of its own.
> - 🔴 **T131's recorded audit said "3 formats, 1 orphan" and was marked *measured, do not
>   re-derive*. It had searched ONE repo and reported an estate total.** There were **three**
>   orphaned producers in **three** formats: `wom7api/scripts/bump_version.js` (the one it saw),
>   `wom7web/scripts/bump_version.js` (writes an **invalid-semver** version into `package.json` —
>   the exact constraint T131 itself flags as the hard blocker), and `wom7web/scripts/deploy_web.py`
>   (a **fourth**, hyphenated format used as a deploy identity, writing to the retired singular
>   `.agent/`). **All three had zero callers estate-wide; all three deleted** in their own commit.
> - 🔴 **The gate's first draft had the same defect.** Detection needed the word "version" in a
>   file's **body**, so it could not see `bump_version.js`, whose body never says it — only its
>   filename does. **The check written to find under-enumeration under-enumerated.** The path is a
>   signal now. That is instances **7 and 8** in T149's table, both found inside this epic's own work.
> - The tests also caught a contract bug by asserting the **documented** exit codes rather than the
>   observed ones: `raise SystemExit("msg")` exits **1**, so a broken policy was indistinguishable
>   from a real finding. Config errors exit **2** now.
>
> ### 🔴 T131 AC3 IS BLOCKED ON A PREREQUISITE — this is the next action on that strand
> AC3 says *"external skills are exempt"*, and **the canonical repo cannot tell which of its own
> skills are external.** The only provenance record is the **consumer's** `.w0m/skills.json`, which
> covers **17 of 30** canonical top-level skills. The other **13** are in no manifest, carry no
> upstream marker, and **11 arrived in a single 2026-06-11 commit**, so git history does not separate
> them either. Several read as vendored (*"official Cloudflare best practices"*, *"Trail of Bits"*)
> but T127's own rule forbids settling it by name — **resolve by content diff against the candidate
> upstream**, as `mcp-builder` was. ⇒ **Do not stamp blind:** overwriting an imported skill's
> `metadata.version` destroys the only handle on comparing it with upstream. Safe to stamp now
> without the pass: the **25 `w0m`-namespace files** (15 top-level + 10 nested). ⚠️ Note this is
> *namespace ownership*, a different question from the *installation* policy T149 just took away
> from that same prefix — the distinction is deliberate, not a reversal.
>
> ### ▶ START HERE
> 1. `git pull` everywhere (a parallel Antigravity agent also commits to `beta`).
> 2. **Re-run, don't re-read:** `just state-check` · `just skill-test` (47) · `just skills-sync check`
>    (17 of 30) · `just version-check` · `just version-test` (19/19) ·
>    `python3 project/scripts/hygiene_preflight.py` (~2s).
> 3. **Then pick one, in this order** — all recorded in [[T149]]'s sequencing:
>    - **[[T131]] AC3's prerequisite** — give `wom7skills` a provenance record of its own, resolving
>      the 13 unknown-origin skills by content diff. That is what actually unblocks [[T147]] AC2.
>      Stamping the 25 `w0m`-namespace files can land before it and does not wait on the pass.
>    - **[[T135]] §5 license** — 233 findings, the last hygiene strand, lets T135 archive.
> 4. 🔴 **[[T149]] AC2 is still the epic's open headline** (instance 4): drift detection is
>    **repo-scope only**, so "0 unmanaged" silently omits `~/.claude/skills`' 12 skills and every
>    plugin-provided skill. Tracked as [[T147]] AC4.
>
> ### 🗣️ THE ONE QUESTION LEFT WITH THE OWNER — unanswered, do not re-derive
> T149 ranks **#2 at 125**, behind T99 at 140, because T99 has a live spec and T149's `spec:` is
> empty. The ranker reflects recorded fields; it cannot be told to put something first. **The honest
> levers are: write T149's spec, or state explicitly that consolidation precedes the credential
> hardening P0.** Do not put a path in `spec:` to move the number — that games the score rather than
> earning it. ⚠️ **P0 now means two things in this queue** — owner priority (T149) and
> production/security emergency (T99, T120). Recorded in both the ticket and the row; do not let T149
> displace T99/T120 in triage.
>
> ### 🔴 OWNER ACTIONS — still FOUR, none actionable from here
> 1. **Delete `wom7api/dev_secrets.json`** (83 plaintext secret values on disk, untracked, nothing
>    reads it — so an agent must not delete it for you).
> 2. **Revoke the `casualuser` GitHub token** (id `1243074`) — dropping the DB row did not revoke it.
> 3. **T99(d) 3.1 — provision `CONNECTOR_TOKEN_KEY_V1`** (`openssl rand -base64 32` → Infisical, v1).
>    Verified absent. **Do not let an agent invent key material.**
> 4. **T99(d) 3.5 — apply migration `20260725180000`** (pointless before 3).
> **Plus:** place the **6 rowless tickets** (T2, T25, T32, T35, T48, T66) · T136/T137's three open
> questions · **T120** (`SAFE_BROWSING_API_KEY` is absent, which is why it can't be checked here).
