<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0a. 🔴 The one owner decision taken mid-build — `mcp-builder` was a NAME COLLISION, not drift -->

### 0a. 🔴 The one owner decision taken mid-build — `mcp-builder` was a NAME COLLISION, not drift

**Read this; it changed what agents load, and it amended the spec.** R4 as written said "single-source
the dual-sourced pair onto canonical". Measurement disproved the premise: `mcp-builder` was **two
different skills sharing one name**, not one skill with two copies.

- **Installed** = Anthropic's official `mcp-builder`, 236 lines, `license: LICENSE.txt` — **byte-identical
  to `anthropics/skills`**, pinned by **content diff against a fetched upstream** (per D6, never by
  name; same repo already established for `webapp-testing`). It references 4 `./reference/*.md` files
  that are **all missing** — it was vendored `SKILL.md`-only (1 of the 10 files upstream ships).
- **Canonical** = an unrelated **18-line** w0m note whose own H1 already read `# w0m-mcp-builder`.
- The lockfile claimed `provider: w0m-native`, `resolved: canonical` for it — **false**, written by
  increment 2.

Following the spec literally would have destroyed 218 lines of third-party content to satisfy a
mis-measured premise. **Owner decision:** rename canonical → **`w0m-mcp-builder`** (directory *and*
frontmatter `name:`), correct the installed skill's provenance to `skills.sh` / `anthropics/skills` /
`resolved: unknown`, keep both skills. Zero content loss, collision gone. Its **integrity hash is
unchanged**, which is itself the proof no content was swapped. `rbac-auditor` was byte-identical to
canonical, so single-sourcing it was a true no-op.

⚠️ **Forced consequence, not a preference:** `w0m-mcp-builder` matches the `w0m*` prefix `skills.ts`
deploys unconditionally, so `--check` reports it as drift until synced — and hooks are never bypassed.
It is therefore installed and declared `w0m-native`, taking the tree **79 → 80**.

R4's requirement text, one scenario and its ACs were **amended** to state the general rule (no name
shared by two *different* skills; where canonical vendors an external skill under the same name the
two must be held byte-identical) instead of naming a pair measurement disproved. That amendment is
recorded in the spec itself and in `tasks.md` → *Deviations from the plan as written*.

**What the spec RESOLVED — do not re-derive, and do not re-open these:**

- 🟢 **The blocker dissolved. Provenance already existed on disk.** `wom7web/skills-lock.json` is
  **tracked in git**, committed *accidentally* 2026-07-04 inside an unrelated CP commit
  (`8d9ecf65 fix(cp): unified fixes for UI, Auth, and Deletions`) — which is why no earlier session
  found it. It is upstream `npx skills` output (`source`/`sourceType`/`skillPath`/`computedHash`)
  covering **all 49** vendored skills, tally **46** `coreyhaines31/marketingskills` · **2**
  `supabase/agent-skills` · **1** `currents-dev/playwright-best-practices-skill` · **1**
  `obra/superpowers`. So AC8 never needed name-matching. Treat that file as **read-only input**.
- 🔴 **Name-matching is now PROHIBITED (D6), and the risk is confirmed live:**
  `npx skills find playwright-best-practices` returns **three different owners publishing that exact
  skill name** (`currents-dev` 64.5K · `0xbigboss/claude-code` 329 · `midudev/autoskills` 45). `find`
  is a **fuzzy search, not a resolver** — a query for `ab-testing` returns hits matching only
  "testing". `w0m skill add` therefore rejects a bare name outright.
- 🔴 **Upstream's hash is NOT enough (D4).** `computedHash` covers a single `SKILL.md`, but **48 of
  49** skills carry extra files (up to 15, e.g. `marketing-plan`) that are loaded by progressive
  disclosure. Hence: **upstream for provenance, w0m directory-wide hash for integrity.**
- 🔴 **Refs cannot be honestly pinned (D7).** Upstream records **no** ref/sha/commit field and the
  original commit is unrecoverable, so `version`/`resolved` = `"unknown"`; `metadata.version` is
  recorded separately as **`observed_version`** (58 of 69). **Never backfill a ref from a source
  repo's current HEAD** — that asserts a provenance never installed. This partially defers AC8's
  "pinned ref"; it is flagged in the ticket, not dropped.
- **The 6 previously-unprovenanced skills were resolved BY CONTENT DIFF** against fetched upstreams
  (never by name): `webapp-testing` → `anthropics/skills` (SKILL.md byte-identical; our copy omits
  `LICENSE.txt` + `examples/`) · `tinybird-{cli,python-sdk,typescript-sdk}-guidelines` →
  `tinybirdco/tinybird-agent-skills` (all byte-identical) · `tinybird-best-practices` → same repo but
  **upstream names it `tinybird`** (our dir was locally renamed) and ours is one upstream addition
  stale · `fact-checker` → **`local`**: it references w0m Gauge user stories, so it is ours.
- **Full accounting — now 80, not 79** (R3 requires managed-or-excluded): 50 adopted (49 + the
  re-provenanced `mcp-builder`) · 13 `w0m-native` (`w0m` + 10 `w0m-sdlc-*` + `rbac-auditor` +
  `w0m-mcp-builder`) · 6 individually resolved (one of which, `mcp-builder`, moved into the adopted
  count when §0a pinned it to `anthropics/skills`) · 10 `openspec-*` **excluded with a recorded
  reason** (tool-generated; `wom7skills/CLAUDE.md` forbids vendoring; an unreasoned exclusion is a
  *blocking* finding so exclusion can't hide a skill). The 80th is `w0m-mcp-builder` — §0a explains
  why its deployment was forced rather than chosen.
- **Owner decisions (locked 2026-07-24, both honored):** sourcing = re-source via `npx skills`;
  gate = **warn on unmanaged, block on integrity tamper** (mirrors T130's `enforce_raw` — pre-existing
  debt must never wall off a gate). ⚠️ On the first: **re-sourcing was never exercised** and that is
  recorded on AC8 as a carve-out, not silently met — the vendored content proved byte-identical to its
  pinned upstream everywhere it was checked, so re-sourcing would have changed nothing while risking a
  silent content swap.
