<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0r. ✅ RESOLVED: the `review` gate — all 4 findings APPLIED (was: verified, unapplied) -->

### 0r. ✅ RESOLVED: the `review` gate — all 4 findings APPLIED (was: verified, unapplied)

> ✅ **ALL FOUR APPLIED 2026-07-25** (commits: wom7skills `fix(T127): close 4 review-gate findings`;
> wom7web ticket/spec docs + archive). F1/F2/F3/F4 fixed in `w0m_skill.ts` + `skills.ts`, regression
> assertions added (`just skill-test` **32 → 37**), gate + drift both green. The detail below is the
> record of what was found and how it was fixed — not a to-do. Security + verify + archive gates then
> ran green (see the ⭐ block). Live repro `<scratchpad>/repro-prov/` is **no longer needed** — the
> behaviour is now a permanent regression test; delete it.

Scope was confirmed first and **matches the intended blast radius**: `wom7skills` logic
(`w0m_skill.ts` +326, `skills.ts` +104, tests +534, schema +15) · generated data
(`.w0m/skills.json` +413, `.w0m/skills.lock.json` +552) · config (`.pre-commit-config.yaml`,
`wom7api/justfile`) · the skill tree (**exactly 18 deletions, all under `.agent/skills`**, all
intended — the 3,806-line figure is line count, the pptx scripts are large — plus 55 renames, no
content edits) · docs/prose.

**F1 🔴 CONFIRMED (correctness) — `relock-all` can never correct a stale `resolved`.**
`wom7skills/w0m_skill.ts` → `relockAll()`: `resolved: existing?.resolved ?? entry.version`
unconditionally prefers whatever the lockfile already held, so changing a skill's declared provenance
in the manifest leaves `resolved` stale forever. **This bit me during the build** — it is why
`mcp-builder`'s lock entry had to be **hand-deleted** before `relock-all` would record
`resolved: unknown`. Reproduced from scratch: declare `skills.sh`/`acme/original` → relock → switch the
manifest to `w0m-native`/`canonical` → relock again → `provider` updates and `source` drops correctly,
but `resolved` stays `"unknown"` instead of becoming `"canonical"`.
*Proposed fix:* recompute `resolved` from `entry.version` when the manifest's provenance intent
changed, e.g. keep `existing.resolved` only if `existing.provider === entry.provider && existing.source
=== entry.source`.

**F2 🔴 CONFIRMED (gate coverage) — `check` never verifies manifest↔lock provenance, so a FALSE
provenance stays green.** `cmdCheck()` validates integrity (content), declared-not-locked, orphan-lock
and not-installed — but never compares the lock's `provider`/`source`, nor `resolved` against the
manifest's `version`. In the same repro the gate printed `1 managed skill(s) match the lockfile ✓`
while the two files disagreed. **This is the gap that let increment 2's false `w0m-native`/`canonical`
record for `mcp-builder` survive undetected** — I caught it by hand, not by the gate, which is exactly
the class of hole R1 exists to close.
*Proposed fix:* add a **blocking** finding for provider/source mismatch and for `resolved` ≠ declared
`version`. Verified safe to make blocking: the live tree currently has **0** mismatches on both checks,
so the gate stays green. Blocking is the right severity — this is lockfile incoherence, the same class
as the existing orphan-lock finding, not pre-existing debt (D2 keeps debt non-blocking).

**F3 🟡 LATENT, verified 0 occurrences (integrity blind spot) — the active-only drift check applies the
sibling exclusion to the copy it is policing.** `wom7skills/skills.ts`:
`activeRels = syncUnit(join(dest, name), name)`. `syncUnit` skips a top-level `<skill>-*`
subdirectory, so content smuggled into e.g. `.agents/skills/w0m/w0m-anything/` is invisible to the
"present in the active copy, absent from canonical" check — blind in precisely the region that check
exists to watch. Verified no active skill dir contains a `<skill>-*` subdir today. Severity is only 🟡
because `hashSkillDir` walks **everything**, so `w0m skill check` would still block on it — real
defense in depth.
*Proposed fix:* scan the active copy **without** the exclusion (walk it plainly). Cannot cause false
drift: after a sync no active dir contains a `<skill>-*` subdir.

**F4 🟡 LATENT, verified 0 occurrences (integrity gap, ALSO for the security gate) — symlinks inside a
skill directory escape the integrity hash entirely.** `hashSkillDir()` does
`if (st.isDirectory()) … else if (st.isFile()) …` on an **`lstat`**, so a symlink is neither and is
skipped — meaning a symlinked file inside a skill dir is content an agent can load through progressive
disclosure that the hash does not cover. `syncUnit` skips symlinks the same way. Verified the only
symlinks inside skill dirs today are 13 under `mmd-validate/node_modules/.bin/`, and `node_modules` is
excluded anyway → latent, not active. Note the skill dir *itself* is `realpath`'d on purpose (a
symlinked skill dir is followed, and that is tested).
*Proposed fix:* treat a symlink as content — hash its target string (e.g. `<rel>@-><link target>`)
rather than ignoring it. **Raise this at `w0m-sdlc-security` too**: an unhashed load-bearing path is an
agent-instruction integrity concern, the same family as the second-resolution-path R4 removed.

**Low, judged NOT worth changing** (recorded so they are not re-litigated): `enumerateInstalled`'s
`viaLegacyPath` only inspects the **first** `readlink` hop, so a symlink *chain* through
`.agent/skills` would evade it — impossible today (the directory does not exist) and the
reappearance warning covers it returning · `cmdAdopt` rewrites manifest+lock even when it adopts 0,
churning `generatedAt` · `readObservedVersion`'s regex can match a `version:` under a different key
within its 2000-char window (observed-only data) · an `exclude` entry for a skill that is not installed
is silently dead config.

**DONE in this gate (all of F1–F4 applied):** regression assertions added for **all four** (not just
F1/F2 — F3 smuggled-sibling-content, F4 symlink-in-hash too), `just skill-test` **37/37**,
`just skills-typecheck` clean, fixed-vs-filed recorded under T127's `## Status notes`. Nothing filed to
`TECH-DEBT.md` — all four were in-scope for R1/R2.
