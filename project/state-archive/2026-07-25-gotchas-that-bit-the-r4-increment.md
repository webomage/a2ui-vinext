<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 🔴 Gotchas that BIT the R4 increment (2026-07-25, later) -->

### 🔴 Gotchas that BIT the R4 increment (2026-07-25, later)

- **🔴 `git mv` on a vendored dir re-stages the WHOLE file → pre-existing lint findings block your
  commit.** R4's moves re-staged `webapp-testing/scripts/with_server.py` (`subprocess shell=True`,
  tracked since `41b65152`) and semgrep blocked. **You cannot fix it the usual way:** an inline
  `# nosemgrep` edits vendored content, which breaks its lockfile integrity hash *and* its
  byte-identity with the pinned upstream — the two things T127 exists to protect. The resolution was
  to exclude `^\.(agents|claude)/skills/` from the semgrep hook and record that auditing skill scripts
  is **AC7**'s job. Generalises the older "staging a test file re-runs semgrep on the whole file"
  gotcha below: for *vendored* files the escape hatches are unavailable, so the hook's scope is the
  only lever.
- **🔴 An unanchored count in a regex assertion is a time bomb.** `assert.doesNotMatch(out, /0
  managed/)` guarded against a vacuous gate — and silently became a false failure the moment the
  managed count hit **70**, because "70 managed" contains "0 managed". Use `\b`. Any assertion that
  matches a number as a *substring* will eventually fire on a different number.
- **A pipe masks the real exit status** (already noted below, and it bit again): `tsx skills.ts
  --check … | tail` printed `exit=0` while the command had genuinely returned 1. Redirect to a file
  and check `$?`, or capture the status explicitly, whenever the exit code *is* the finding.
- **Replicating a hash function for a baseline? Validate the replica first.** The R4 before/after
  comparison used a Python replica of `hashSkillDir`; it was trustworthy only because it reproduced
  all **69** already-locked integrity values exactly. An unvalidated replica turns "0 changed" into a
  meaningless statement.
