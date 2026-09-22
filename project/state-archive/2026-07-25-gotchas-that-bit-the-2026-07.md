<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 🔴 Gotchas that BIT the 2026-07-25 session (read these first) -->

### 🔴 Gotchas that BIT the 2026-07-25 session (read these first)

- **🔴 A shell `cd` is silently RESET by `npx skills` (and other pnpm/npx calls).** After such a
  command the Bash cwd jumped back to `/Users/proto/Projects/@self/@wom`, so the *next* relative-path
  command silently measured the wrong tree. This produced a **false all-DIFFERS result** in the
  tinybird content diffs — every file "differed" only because our side didn't exist at that path.
  **Use absolute paths for any comparison that a conclusion depends on**, and be suspicious of a
  uniform result.
- **`shasum`/`diff` on a MISSING file yields an empty hash, not an error** — which reads as "differs"
  in a naive comparison. Assert the input exists (`[ -z "$a" ] && echo MISSING`) before concluding.
- **`grep -c` returning 0 SHORT-CIRCUITS a `&&` chain** (grep exits 1 on no matches), so the rest of
  the command never runs and you get a half-answer that looks complete. Same trap with
  `cmd | tail` + `$?` — the pipe's exit status is `tail`'s, **not** the command's, so a failing
  recipe can look like it passed. Capture status explicitly.
- **`just` recipes do NOT live in `wom7skills`** — it has no justfile; the skills recipes
  (`skill`, `skill-test`, `skills-typecheck`, `skills-sync`, …) are in **`wom7api/justfile`**. Running
  `just` from wom7skills fails with "no justfile found".
- **🔴 `just skill …` targets the directory you RUN it from** (the recipe passes
  `--project {{ invocation_directory() }}`). Run it from **`wom7web`**, or it silently audits a
  different project and reports `0 managed` — which looks exactly like a regression. Same class of
  cwd trap as the `npx` reset above: I hit it verifying this handoff. `just skill-test` and
  `just sdlc-doctor` are cwd-independent; `just skill check` is not.
- **`openspec status --change <dated-name>` is unusable** ("must start with a letter") — the known
  T119 AC4 tradeoff. Positional works: `openspec validate <name> --type change --strict`.
- **The marketing pack's website count ≠ the repo's count.** `skills.sh` lists **68** skills for
  `coreyhaines31/marketingskills`; `npx skills add <repo> --list` on the actual git HEAD reports
  **48**. The CLI is authoritative — do not enumerate a pack from its web page.
- **`npx skills add <repo> --list` still CLONES** (network) but installs nothing — that is the safe
  enumeration/diff primitive. Useful flags found: `--owner` (disambiguate a name across owners),
  `-s <skill>|'*'`, `--copy`, `-y`.
- **Upstream `npx skills` HAS a lockfile now** (`skills-lock.json` + `experimental_install`), which
  T127's ticket predates and contradicts. Ours is not redundant — see D4/D7 in §0 for why (single-file
  hash, no ref field). CLI version seen: **1.5.20**.
- **`timeout` is still a Python script on this machine** (documented below and it bit again) — use the
  Bash tool's own timeout, never `timeout <n> <cmd>`.
