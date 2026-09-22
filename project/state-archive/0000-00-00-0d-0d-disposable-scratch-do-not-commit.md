<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0d. Disposable scratch (do NOT commit) -->

### 0d. Disposable scratch (do NOT commit)

- `<scratchpad>/declare_rest.py` — one-shot that declared the 29 non-adopted skills into the T127
  manifest. Already applied and committed (wom7web `6066ca39`); the **manifest is the artifact**, the
  script is disposable.
- `<scratchpad>/provcheck/` + `tb/` — throwaway projects used to fetch `anthropics/skills` and
  `tinybirdco/tinybird-agent-skills` for the R1 content diffs. Delete.
- `<scratchpad>/tp/` — fake project used to prove the T127 drift classes. Ignore/delete.
- `<scratchpad>/prove_t130.py` + `t130-fix/` — **superseded**: promoted into the repo as
  `project/scripts/tests/test_discovery.py` (`just discovery-test`). Use the repo copy.
- `<scratchpad>/hash_skills.py` + `baseline.json`/`after_*.json` — the R4 before/after hash baseline.
  Disposable: it replicates `hashSkillDir` in Python purely to compare, and **self-validated by
  reproducing all 69 locked integrity values**. The durable artifacts are the lockfile and the live
  assertions in `just skill-test`. If you ever need this again, the self-check (compare against the
  lockfile before trusting the diff) is the part worth copying.
- `<scratchpad>/anthropics-skills/` — shallow clone used for the `mcp-builder` content diff (§0a).
  Delete. `<scratchpad>/migrate_r4.sh` — one-shot `git mv` migration, already applied and committed.
- ⚠️ **`<scratchpad>/repro-prov/` — KEEP until F1/F2 are fixed.** The live reproduction for the two
  confirmed review findings (§0r): a 1-skill fixture project whose manifest provenance is changed
  between two `relock-all` runs, showing `resolved` going stale and `check` still printing green. Turn
  it into the regression assertion in `wom7skills/tests/w0m_skill.test.ts`, then delete. If the
  scratchpad is gone, rebuilding it takes ~10 lines — §0r describes the exact sequence.
