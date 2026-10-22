# T148 — SDLC Branch Hygiene and wom7api main-vs-beta Commit Classification

- **Ticket:** [[T148]]
- **Date:** 2026-10-22
- **Status:** Complete (Read-only monitoring live; zero refs mutated per AC7)
- **Contract Surface:** `wom7web/.w0m/sdlc.json` (`branch_model`), `scripts/branch_hygiene.py` (`just branch-hygiene`), `wom7web/project/scripts/tests/test_branch_hygiene.py` (`just branch-hygiene-test`)

## 1. Executive Summary

Per [[T148]] (AC1–AC7), we implemented a strictly read-only SDLC branch hygiene monitor (`just branch-hygiene`) using explicit Git plumbing refs (`refs/heads/*`, `refs/remotes/origin/*`) via `git for-each-ref` and `git rev-list --left-right --count` (never `git log @{u}..`), recorded the estate's stage-branch contract in `.w0m/sdlc.json` (`branch_model`), and performed a commit-by-commit forensic classification of the 180 `main`-only commits in `wom7api`.

Key findings:

1. **Zero unique work exists on `wom7api` `origin/main` (`1fbcb1c`).** All 180 commits reachable from `refs/remotes/origin/main` after the common merge-base `dfd3d4b240dbbc4f3073030f3e13114b841d3f9d` (2025-12-21) have an **exact 1-to-1 positional counterpart** in the first 180 commits on `refs/remotes/origin/beta` (`dfd3d4b..f70d0ca`, 180/180 matching commit subjects).
2. **The root tree of `wom7api` `origin/main` tip (`1fbcb1c`) and `origin/beta`'s 180th post-merge-base commit (`f70d0ca`) is byte-identical** (`1b6bf2ffb84abaa697263e78e7422e5027d7b587`, `git diff 1fbcb1c f70d0ca` is empty).
3. **Why the 180 SHAs diverged:** During the 2026-07-12 credential-leak history rewrite, `beta` was scrubbed to remove `.env` from commits #1 through #52 after `dfd3d4b` (`98095b1..8a59ca7` on `main` vs `d150572..2dada8e` on `beta`). Commits #53 through #180 have byte-identical trees on both branches, and their commit SHAs differ solely because Git commit hashes form a Merkle DAG chaining parent commit SHAs.
4. **Why merging `origin/main` into `beta` is dangerous and prohibited:** Running `git merge origin/main` into `beta` would re-parent `beta` onto the pre-rewrite commit chain (`98095b1..8a59ca7`), **resurrecting the scrubbed `.env` objects** back into `beta`'s reachable history.

---

## 2. Estate Branch Inventory (Measured 2026-10-22)

Measured via `just branch-hygiene` across the 7 governed repositories plus 1 excluded repository (`wom7mlx/wom7mlx`):

| Repository | Governance | Canonical Ref | `origin/main` Ref | `beta` Ahead of `main` | `main` Ahead of `beta` | Stage Status | Stale Refs (>=14d) |
|---|---|---|---|---:|---:|---|---:|
| `@wom` (root) | Governed | `refs/remotes/origin/beta` (`f9145df`) | None | — | — | `SINGLE_BRANCH_BY_DESIGN` | 0 |
| `wom7web` | Governed | `refs/remotes/origin/beta` (`16f8b182`) | `52f687cb` (2026-03-16) | 3096 | 0 | `TRAILS_BETA_CLEANLY` | 1 (`origin/main`) |
| `wom7api` | Governed | `refs/remotes/origin/beta` (`2461195`) | `1fbcb1c` (2026-03-16) | 1056 | 180 | `DIVERGED_PRE_REWRITE_DO_NOT_MERGE` | 1 (`origin/main`) |
| `wom7func` | Governed | `refs/remotes/origin/beta` (`33d8a91`) | None | — | — | `SINGLE_BRANCH_BY_DESIGN` | 0 |
| `wom7skills` | Governed | `refs/remotes/origin/beta` (`7ee7b8e`) | None | — | — | `SINGLE_BRANCH_BY_DESIGN` | 0 |
| `wom7ext` | Governed | `refs/remotes/origin/beta` (`2631b1f`) | `9ff31b1` (2026-03-16) | 60 | 0 | `TRAILS_BETA_CLEANLY` | 1 (`origin/main`) |
| `wom7sec` | Governed | `refs/remotes/origin/beta` (`227646b`) | `089632e` (2026-03-05) | 31 | 0 | `TRAILS_BETA_CLEANLY` | 1 (`origin/main`) |
| `wom7mlx/wom7mlx` | Excluded (T148 Note) | `refs/remotes/origin/beta` (`cebe5c6`) | `18557bc` (2026-05-04) | 19 | 0 | `TRAILS_BETA_CLEANLY` | 1 (`origin/main`) |

---

## 3. Forensic Classification of `wom7api`'s 180 `main`-Only Commits (AC2)

### 3.1 Common Ancestor and Branch Geometry

- **Merge-base (`git merge-base refs/remotes/origin/beta refs/remotes/origin/main`):**
  `dfd3d4b240dbbc4f3073030f3e13114b841d3f9d` (`2025-12-21 02:05:47 -0500`, `"chore: configure dns and pages domain for beta and legacy"`).
- **Commits on `refs/remotes/origin/main` since `dfd3d4b`:** `180` (`98095b1..1fbcb1c`, last commit `2026-03-16 14:14:45 -0500`).
- **Commits on `refs/remotes/origin/beta` since `dfd3d4b`:** `1056` (`d150572..2461195`).

### 3.2 1-to-1 Positional and Tree Equivalence Proof

Comparing the 180 commits on `origin/main` (`dfd3d4b..1fbcb1c`) against the first 180 commits on `origin/beta` (`dfd3d4b..f70d0ca`):

| Segment (Post-Merge-Base Index) | `origin/main` Range | `origin/beta` Range | Subject Match | Tree Comparison (`git diff <main_sha> <beta_sha>`) | Cause of SHA Difference |
|---|---|---|---|---|---|
| Commits `#1` .. `#52` (52 commits) | `98095b1` .. `8a59ca7` | `d150572` .. `2dada8e` | 52 / 52 identical | Differs **only** in `M .env` (scrubbed on `beta` during the 2026-07-12 credential-leak rewrite) | `.env` blob scrubbed from `beta` history; `origin/main` was never rewritten |
| Commits `#53` .. `#180` (128 commits) | `66c7e05` .. `1fbcb1c` | `c852968` .. `f70d0ca` | 128 / 128 identical | **0 files differ** — every single tree SHA in `#53..#180` is byte-identical between `main` and `beta` | Merkle parent-hash propagation from rewritten ancestor `#52` |

At commit `#180` (the tip of `origin/main`):
- `refs/remotes/origin/main` commit `1fbcb1c` (`"fix(ci): rewrite sync-railway-env into valid bash shebang and add graceful fallback"`) has tree SHA `1b6bf2ffb84abaa697263e78e7422e5027d7b587`.
- `refs/remotes/origin/beta` commit `f70d0ca` (same subject, same author timestamp) has tree SHA `1b6bf2ffb84abaa697263e78e7422e5027d7b587`.
- `git cherry -v refs/remotes/origin/beta refs/remotes/origin/main` reports `171 -` (patch-id identical) and `9 +` (the 9 commits inside `#1..#53` that touched `.env` or its removal boundary).

### 3.3 Verdict on `wom7api` `origin/main`

- **Are the 180 commits wanted on `beta`?** **No.** 100% of their code is already present on `origin/beta` (`dfd3d4b..f70d0ca`), and `origin/beta` is 876 commits ahead of `f70d0ca`. Worse, commits `#1..#52` on `origin/main` retain the pre-rewrite `.env` blob that the 2026-07-12 history rewrite purged from `beta`.
- **Why naive consolidation fails:**
  - `git merge origin/main` into `beta` would re-introduce the 52 pre-rewrite commits containing `.env` into `beta`'s reachable commit graph, undoing the 2026-07-12 security scrub.
  - `git push origin main:beta` or pushing any local pre-rewrite branch would re-upload or preserve leaked objects.

---

## 4. Stage-Branch Contract (`.w0m/sdlc.json` -> `branch_model`, AC3)

Per [[AgDR-0032]] and `AGENTS.md`, the estate operates on a single canonical stage branch (`beta`) with isolated per-agent trees (`agent/<name>`) and release tags (`release/<version>`):

- **`canonical_branch`:** `"beta"`
- **`agent_branch_prefix`:** `"agent/"`
- **`release_tag_prefix`:** `"release/"`
- **`stale_days`:** `14`
- **`single_branch_by_design`:** `["@wom", "wom7func", "wom7skills"]` — created on `beta` from inception; no `main` branch needed.
- **`legacy_main_repos`:** `["wom7web", "wom7api", "wom7ext", "wom7sec"]` — retain frozen March 2026 `origin/main` refs (`wom7api` marked `diverged_pre_rewrite_do_not_merge: true`).
- **`excluded_repos`:** `["wom7mlx/wom7mlx"]` — excluded from uniformity enforcement per T148 Note; reported as `[EXCLUDED]` informational.

---

## 5. Safe Consolidation Options for Owner Decision (AC2 & AC7)

Per AC7, **no branch was mutated, fast-forwarded, force-pushed, or deleted** by this ticket. Two owner-approved options exist to resolve the legacy `origin/main` refs across `wom7web`, `wom7api`, `wom7ext`, and `wom7sec`:

| Option | Action (Owner-Executed Only) | Cost | Risk | What It Unblocks | Recommendation |
|---|---|---|---|---|---|
| **Option A (Recommended): Retire legacy `origin/main` refs (`git push origin --delete main`) after verifying default branch is `beta` on GitHub** | Confirm GitHub default branch is `beta` on `wom7web`, `wom7api`, `wom7ext`, `wom7sec`, then delete the unused `origin/main` ref in those 4 repos. | Low (~2 min) | Low — `origin/beta` already holds 100% of `main` trees, and deleting `origin/main` in `wom7api` finally makes the 52 pre-rewrite `.env` commits unreachable on `origin`. | Makes all 7 governed repos uniformly single-branch (`beta` + `release/*` tags) per AgDR-0032 and purges unreachable pre-rewrite commits on `wom7api`. | **Recommended** |
| **Option B: Repoint `origin/main` to `origin/beta` (`git push --force-with-lease origin refs/remotes/origin/beta:refs/heads/main`)** | Fast-forward `origin/main` in `wom7web`, `wom7ext`, `wom7sec`, and reset `origin/main` in `wom7api` to `refs/remotes/origin/beta` (or `f70d0ca`). | Low (~2 min) | Low (pushes clean `beta` SHA to `main`, never `main` to `beta`), but leaves a second stage branch that nothing in `just deploy-all` promotes automatically. | Preserves a `main` ref on the 4 legacy repos while eliminating the pre-rewrite history on `wom7api`. | Secondary if a `main` ref is still desired for external viewers. |
