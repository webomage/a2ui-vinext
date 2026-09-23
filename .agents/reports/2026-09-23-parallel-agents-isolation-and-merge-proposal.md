# Proposal — parallel agents: isolation, collection & merge (w0m estate)

**Date:** 2026-09-23 · **Status:** ACCEPTED plan, tickets T423–T428 created · **rev 4**, owner decisions applied (rev 3 = §0 re-measure + root-repo design; rev 4 = §4 plan, §6 decisions, §7 tickets) · **Author:** Claude Code (Desktop, Opus 5.5)
**Input:** `claude/parallel-agents-isolation-and-merge.md` — Claude **Cowork** research, 2026-09-23, done
without web access (the file lives in the Cowork project, not on this machine). Re-verified against live
docs and **measured against the estate today**.
**Toolchain:** Orca CLI (`/opt/homebrew/bin/orca`, source `wom7pr/orca` @ `d5fa54ecde`) · git 2.49.0 ·
Claude Code 2.1.278.

### Owner constraints (2026-09-23) — this revision is built on them
1. **Orca is the main agent orchestrator** → the solution must be **agent-agnostic** (Claude, Codex,
   Antigravity, OpenCode … all equal). Nothing in the core may depend on a Claude Code feature.
2. **No PRs.** Solo operator, no collaboration expected → a **local merge queue** that lands on `beta`.
3. **2–3 concurrent agents**, not dozens → optimise for simplicity, not throughput.

---

## TL;DR

- **Root cause, measured:** Orca knows the w0m repos, but every Orca worktree for them is the **main
  checkout on `beta`** (`orca worktree list --json` → `isMainWorktree: true` for wom7web, wom7api,
  wom7ext, wom7sec, wom7skills, wom7mlx). Across the estate Orca has created exactly **one** linked
  worktree (`~/orca/workspaces/wom7mlx/eval-gemma4`). Agents collide because they are all started in
  the same directory — not because isolation is missing, but because it is **not used**.
- **Orca already provides the agent-agnostic factory:** `orca worktree create --repo … --base-branch …
  --agent <any> --prompt …` + a per-repo, committed **`orca.yaml`** with `scripts.setup` /
  `scripts.archive` hooks and `worktree.sharedDirectories`. **No w0m repo has an `orca.yaml`.**
- **Proposal in one line:** *every writing agent gets an Orca worktree (bootstrapped by `orca.yaml`);
  work lands on `beta` one unit at a time through `just land` (rebase → gates → fast-forward), the only
  writer to `beta`; main checkouts become land-only.*
- **Hard prerequisite: T408** — commits from a fresh worktree run **zero hooks** today. Fix it
  *agent-agnostically in git itself*, before any of this becomes routine.
- At 2–3 agents most of the heavy machinery from the research (integration branches, plan-time
  file-ownership DAGs, PreToolUse guards, mergiraf) is **not worth it**. Kept as "later, if measured".
- **Rev 4, decisions applied (§6):**
  - The main-checkout commit gate is **observe first, then land-only**.
  - Generated files are **discarded, regenerated, and a notice is printed**, with the skills updated
    in the same ticket.
  - **`worktree_agent.py` is deleted.**
  - **Parent shims come first**; the symlink cutover comes later.
  - **Critical path: T408 → T424 → T425 → T426** (§7).

---

## 0. Rev 3 — re-measure after the T422 commits (2026-09-23, later the same day)

### 0.1 Repo state at re-measure
| Repo | local HEAD | `origin/beta` (ls-remote) | unpushed | dirty |
|---|---|---|---|---|
| `@wom` root | `84290c1` chore(state): refresh STATE.md … post-T422 | `b66b82c` | **5** | 0 |
| wom7web | `75671256` chore(tickets): sync ticket hash for T422 | `7cd76feb` | **5** | 0 |
| wom7api / wom7func | `a025489` / `ecf30db` | same | 0 | 0 |

The T422 commits are local; the remote hadn't moved yet at re-measure. A parallel Orca agent was still
working (owner, 2026-09-23), so this is in-flight, not a failed push. The 303-file dirty tree from rev 2 is
now committed, so wom7web is clean enough to pilot on once pushed.

### 0.2 🔴 New finding — member repos only work at their estate-relative position
Member repos contain **30 tracked symlinks that point outside the repo** (measured, `git ls-files -s`
mode `120000` + `readlink`): **wom7web 25**, **wom7api 4**, **wom7func 1**, others 0.

| From | Points to | Count |
|---|---|---|
| `wom7web/project/*-policy.json`, `*.schema.json`, `templates/*.md` | `../../project/policies/…` (root repo) | 22 |
| `wom7web/.w0m/sdlc.json` | `../../.w0m/sdlc.json` (root) | 1 |
| `wom7web/TASKS.md` | `../TASKS.md` (root) | 1 |
| `wom7web/justfile`, `wom7func/justfile` | `../wom7api/justfile` (sibling) | 2 |
| `wom7api/.agent`, `.codex`, `.gemini`, `.kilocode` | `../wom7web/…` (sibling) | 4 |

Add untracked `wom7web/.tasks → ../.tasks`, which isn't in any worktree at all. The 22 policy links were
added by **T412** (`ae22a0ef`, 2026-09-20, "root symlinks and forwarding shims"). A day later
**AgDR-0025** (2026-09-21) banned "shadow symlinks in legacy locations", so these are un-cut-over
AgDR-0025 debt. The policies are read by live gates (`deps_sync.py`, `hooks_check.py`,
`coverage_scan.py`, the emoji pre-commit, …).

**Layout test** (a scratchpad simulation of the exact `../../project/policies/x` link):

| Worktree layout | Link resolves? |
|---|---|
| T411 `worktree_agent.py`: member worktree at `<repo>/.worktrees/<id>`, **symlinked** into the root worktree | ❌ dangling. The kernel resolves `..` physically, from inside `<repo>/.worktrees/` |
| Orca default: `~/orca/workspaces/wom7web/<name>` | ❌ dangling |
| Orca + **parent shims** (`~/orca/workspaces/wom7web/project → @wom/project` …) | ✅ resolves to the **live** root |
| Physical estate shadow: member worktree **physically** at `<root-wt>/wom7web` | ✅ resolves to the shadow's root copy |

This explains the one-off `~/orca/workspaces/wom7web/wom7api → @wom/wom7api` symlink: someone hit
exactly this for the justfile and patched it by hand. It also means a wom7web worktree without shims
would **fail its pre-commit hooks**, since they read the policy files. Orca's own layout can't produce
an estate-shaped tree: `worktreeBasePath` is per repo, but the worktree name is always the last path
segment (`src/main/ipc/worktree-logic.ts:240-285`).

**Decision this forces:**
- **Short term: parent shims.** `worktree_setup.py` computes the escaping links, ensures one shim per
  target at the worktree's parent directory, and fails closed if a target is missing. The shims are
  generated from the measurement, not a hand-kept list. Shims point to the *live* root, which is
  consistent with §0.4 below: the root is one shared checkout by design.
- **Long term: the AgDR-0025 cutover.** Readers resolve the estate root explicitly (`W0M_ROOT`, fail
  closed if unset). The 30 links are deleted, and member repos stop depending on where they sit on
  disk. After that, no shims are needed.

### 0.3 T411 re-measured against the research

| T411 deliverable / spec requirement | Built? | Used? | Matches the research? |
|---|---|---|---|
| R1 root `.tasks/` as the only ticket store | ✅ (424 files) | ✅ 52 of 70 root commits since 09-20 | ✅ Per-ticket files are the right grain for parallel work (disjoint by construction). "Backwards compat via symlink/resolver" (AC1) contradicts AgDR-0025, so it's correctly *not* built. |
| R2 `TASKS.md` 100 % generated | ✅ `tasks_render.py`, `--check` exit 0 now | ⚠️ rendered **by hand and committed**: 35 of 70 root commits touch it | ❌ A generated file that every unit commits is the "hot file" the research warns about: two tickets means two renders means a conflict. It must be rendered **only at land time**. |
| R3 SDLC trace on per-ticket files | ✅ | ✅ | ✅ neutral |
| R4 pre-push `--scope-diff origin/beta` | ✅ in wom7web `.husky/pre-push:394-415` | ✅ | ✅ Right idea: a gate must judge *your* change, not others' in-flight work. ⚠️ The root repo has **no pre-push at all**, so root commits aren't gated by it. |
| R5 `just worktree-agent` coordinated worktrees | ✅ 226 lines | ❌ never run: no `.worktrees/`, no `agent/*` branch | ❌ on four counts. (1) The symlinked layout breaks 25 wom7web links (§0.2). (2) No bootstrap and no T408 fix, so hooks don't run. (3) No merge-back, which is the "collect" half of the research. (4) It's a second factory beside Orca's (dual SSOT). |
| (implicit) collection / merge | ❌ | — | ❌ absent. This is the part rev 2's `just land` adds. |
| Tests | 5 tests, none on `worktree_agent.py`; two divergent copies | — | ❌ |

**Verdict:** T411 fixed the **data model** for parallel work (per-ticket files, scoped gates), and
those parts should stay. Its **isolation** half is unusable as built and has no **merge** half. The
proposal replaces R5 with Orca + shims + `just land` and turns R2 into "render at land time only".
T411 stays `done` as a ticket. The gaps belong to T408 and the new tickets in §7, not to a reopened T411.

### 0.4 The `@wom` root repo, and what `just land root` does

**What the root holds** (tracked, by top-level path): `.tasks/` 424 · `project/` 104 (policies 19,
state-archive 82, templates) · `scripts/` 54 (estate tooling) · `.agents/` 35 (rules, skills, reports) ·
`.claude` / `.opencode` / `.serena` / `.w0m` (agent + SDLC config) · the registers `TASKS.md`,
`STATE.md`, `CHANGELOG.md`, `ROADMAP.md`, `LESSONS.md`, `TECH-DEBT.md`, `AGENTS.md` · `justfile`.
Churn since T411: 70 commits, of which `.tasks/` 52, `TASKS.md` 35, `STATE.md` 13.

**Why the root is not worktree'd** (answers rev 2 Q2):
1. A root worktree contains no member repos (the members are excluded via `.git/info/exclude`), so
   agents can't do code work from it.
2. Member worktrees already reach the root **live** through the shims (§0.2), and through the root
   `justfile` / `scripts/` that every recipe calls. The root works like a shared ledger plus toolbox,
   read and appended by everyone. Isolating it would mean N copies of the ledger to reconcile.
3. Its writes are small and mostly disjoint by construction: one agent writes one `.tasks/T<id>.md`.
   The contention is almost entirely in the **generated** files and **append-mostly registers**, and
   serialisation fixes that more cheaply than isolation does.

So the root stays **one checkout, many writers, one committer**. `just land root` is that committer.

**`just land root [--ticket T<id>]`**, run under the same land lock as member landings:

1. **Collect, don't sweep.** Stage only paths the unit owns:
   - its own `.tasks/T<id>.md`;
   - `.agents/reports/*t<id>*`;
   - a register append it declared.

   It never runs `git add -A`. Uncommitted changes to *other* tickets' files are listed and left
   alone. That directly fixes the swept-in-other-agents'-files incidents (`LESSONS.md:299-318`, memory
   `background-sessions-invisible-ticket-work`).
2. **Regenerate derived files, never accept them from agents.** It runs `just tasks-render` (TASKS.md),
   the `just state-save` mechanical block (STATE.md), and the changelog if due. Agent edits to these
   files are discarded and regenerated. They are views, and only the lander writes views.
3. **Registers** (`LESSONS.md`, `TECH-DEBT.md`, `ROADMAP.md`, `docs/DECISIONS.md`): accept
   **additions-only** hunks automatically. A hunk that rewrites or deletes existing lines stops the land
   and names the file. This catches the read-modify-write race where an agent's Write clobbers another
   agent's fresh append. Later: `just lesson-add`-style atomic append helpers.
4. **Policies and tooling** (`project/policies/*`, `scripts/*`, `justfile`, `.agents/rules/*`): these
   change behaviour for **every** agent the moment they're saved, because everyone runs them live.
   Land them only with an explicit `--include` plus a green `just verify`-level check. Never land them
   implicitly as part of a ticket.
5. **Gate and commit.** Run the root pre-commit set, then add the state-check the root is missing today
   (R4 gap). Commit with a Conventional Commit message that references the ticket, offer the push, and
   release the lock.

**Ordering with member landings.** For a unit touching wom7web plus its ticket, `just land <unit>` lands
the member branch(es) first, then calls `land root --ticket` so the ticket's status change lands only
after the code it describes. Status never runs ahead of the code on `beta`.

---

## 1. The research, re-read under the constraints

| Research recommendation | Keep? | Why / adaptation |
|---|---|---|
| Isolate every *writing* agent in its own worktree | ✅ core | Via **Orca** worktrees, not Claude `isolation:` flags. Read-only agents (review/explore) stay in the main checkout. |
| Structured hand-off instead of prose | ✅ light | Orca metadata (`comment`, `linkedIssue`, lineage) + a small `land` report. No JSON schema ceremony for 3 agents. |
| Serial integration, tests after each merge | ✅ core | As **rebase-and-fast-forward, one unit at a time** (a merge queue of batch size 1). |
| Integration branch + separate resolver agent | ❌ drop | At 2–3 units the owning agent rebases in its own worktree and resolves its own conflicts — it has the intent; a resolver doesn't. |
| `git merge-tree --write-tree` pre-check | ✅ | Cheap early warning in `just land --check` / `just land-status`. |
| `rerere` | ✅ | Free; shared across worktrees (same `.git`). Off in every repo today. |
| Lockfiles: regenerate, never hand-merge | ✅ | `wom7web/pnpm-lock.yaml`, `wom7func/pnpm-lock.yaml`, `wom7api/deno.lock`. |
| Hot files owned by the integrator | ✅ light | Generated files (`TASKS.md`, `STATE.md`, `CHANGELOG.md`, dashboards) are **regenerated at land time**, never hand-edited by units. Other hot files: advisory list, conflicts resolved on rebase. |
| Plan-time disjoint file ownership + PreToolUse edit guard | ⏸ later | Claude-only (PreToolUse) and overkill for 3 agents. Revisit only if pilot shows repeated same-file collisions. |
| `mergiraf` | ⏸ later | Can't parse Astro, Svelte, SQL, Markdown (mergiraf.org/languages) — most of wom7web. |
| Claude `isolation: 'worktree'`, `worktree.baseRef`, `.worktreeinclude`, agent teams | ➖ adapter only | Claude-specific. Documented as an optional adapter (§5), never load-bearing. ⚠️ Note: a Claude worktree made at the `@wom` root contains **no `wom7*` repos** (root excludes them via `.git/info/exclude`) — T411's "Root-Only Worktree Illusion". Orca registers the member repos individually, so it doesn't have this problem. |

---

## 2. Estate reality (measured 2026-09-23)

### 2.1 Orca
- **Registered repos** (`orca repo list`): wom7api, wom7web, wom7ext, wom7sec, wom7skills, wom7mlx
  (+ `_ext/*`). **Not registered:** `@wom` root, **wom7func**. **Stale:** `wom7cfworkers` (dir no longer
  exists); `orca` registered via the `_in/orca` symlink rather than `wom7pr/orca`.
- **Worktree layout:** `~/orca/workspaces/<repo>/<name>`, branch `<git-user-prefix>/<name>`
  (e.g. `casualuser/eval-gemma4`). Lineage via `--parent-worktree`, notes via `--comment`, issue link via `--issue`.
- **Hooks** (`src/shared/orca-yaml-hook-types.ts`): `orca.yaml` at repo root →
  `scripts.setup` (runs after create), `scripts.archive` (runs before archive), `setupAgentStartupPolicy`
  (`wait-for-setup` | `start-immediately`), `defaultTabs`, `issueCommand`, `worktree.sharedDirectories`
  (symlinked, not copied). Hook content is trust-gated per content hash.
- **Cross-repo symlinks resolve to live siblings:** `~/orca/workspaces/wom7web/wom7api → @wom/wom7api`.
  It exists because wom7web's tracked relative symlinks (e.g. `justfile → ../wom7api/justfile`) must
  resolve from inside a worktree. Consequence: **in a wom7web worktree, the justfile *is* the live
  wom7api justfile** — fine for running recipes, but it's a shared hot file, not an isolated one.
- **No merge-back feature** for local-only flows (Orca's merge/conflict code is PR/remote-oriented).

### 2.2 Existing w0m machinery
| Item | State | Evidence |
|---|---|---|
| T411 `just worktree-agent` (`scripts/worktree_agent.py`) | built, **never used**; no merge, no bootstrap, no tests; parallel worktree tree (`<repo>/.worktrees/`) un-ignored | `justfile:126-134`, no `.worktrees/` or `agent/*` branch anywhere |
| **T408** worktree commits skip all hooks | **P1, queued** | `core.hooksPath=.husky/_` is untracked → absent in any fresh worktree → git runs nothing, silently |
| `_in/active-work.json` claim + `active-work-heads-up` hook | advisory, fails open, file = `{}` since Sep 3 | `wom7web/.pre-commit-config.yaml:41-47` |
| `stage-guard` (T235 AC9) | registry empty (`co-tenancy.json` `paths: []`) | passed while other agents' files were swept into commits (`LESSONS.md:299-318`) |
| T274 AC6 (agent handoff on one machine) | queued | "an agent that just writes files declares nothing" |
| Root repo hooks | pre-commit + commit-msg only; **no pre-push** | root `.pre-commit-config.yaml` |
| `rerere` | off in all repos | `git config rerere.enabled` empty |
| Live in-flight example | wom7web main checkout: **303 dirty files**, 3 unpushed (`apps/cp` 79, `packages/ui` 53, `design-system` 48 …) | `git status` — exactly the state a second agent would trample |

### 2.3 Shared singletons (worktrees do **not** isolate these)
| Singleton | Rule under this proposal |
|---|---|
| `beta` in every repo | written **only** by `just land` |
| `TASKS.md`, `STATE.md`, `CHANGELOG.md`, status dashboard | generated; `just land` regenerates, units never commit them |
| `@wom/.tasks/T<id>.md` (root repo, not in Orca) | a unit edits **only its own** ticket file; root commits go through `just land root` |
| Lockfiles | on rebase conflict: take `beta`'s, re-run install, commit the regenerated file |
| `wom7api/justfile` (≈4.3 k lines, symlinked into wom7web) | hot; edits land like any other file, conflicts resolved on rebase |
| Supabase migrations (`<timestamp>_t<id>_*.sql`) | timestamps avoid numbering clashes; `land` checks ordering vs `beta`; `db-migrate` stays human/TTY-gated |
| Live DB (Infisical `beta` = live) | not isolatable; worktree agents never apply migrations |
| Port 4321 (`redev` kills the listener) | worktree agents don't run `redev` (existing rule, `ORCA_INTEGRATION.md:15-17`); if they must: `PORT=4321+N` |
| graphify / `.codegraph` / prepush cache | rebuilt from `beta` after landing (post-commit graphify already skips linked worktrees) |

---

## 3. Target model

```
 you (or an orchestrating agent) ──► orca worktree create --repo name:wom7web --base-branch beta \
                                       --name T422-tokens --comment "T422" --agent <any> --prompt "…"
                                          │
                     orca.yaml scripts.setup  →  scripts/worktree_setup.py
                     (hooks live, deps installed, env files copied, fail closed)
                                          │
   agent A (Claude)        agent B (Codex)        agent C (Antigravity)      ← 2–3 at a time, each in its
   ~/orca/workspaces/      ~/orca/workspaces/     ~/orca/workspaces/            own worktree + branch;
   wom7web/T422-tokens     wom7api/T430-rls       wom7web/T431-copy             commits locally, hooks run
            │                      │                      │
            └──────── just land <worktree> ───────────────┘   ← serialised by a lock; one unit at a time
                 1. main checkout clean? (fail closed)
                 2. fetch; rebase unit onto beta *in the unit's worktree* (its agent resolves conflicts)
                 3. regenerate lockfile if touched; full gates in the worktree (pre-push set)
                 4. fast-forward beta in the main checkout (--ff-only), regenerate TASKS/STATE
                 5. offer push (push-cadence rule); archive worktree via Orca (scripts.archive)
```

**Why rebase-then-fast-forward rather than an integration branch:** with 2–3 units, batching buys
nothing; landing one unit at a time on the *current* `beta` is exactly a merge queue of batch size 1,
keeps `beta` linear, and puts conflict resolution with the agent that wrote the change.

**Cross-repo units** (e.g. wom7api migration + wom7web UI): one Orca worktree per repo, same `--name`,
the second created with `--parent-worktree` the first. `just land` lands a lineage group as a set, in
dependency order `wom7api → wom7func → wom7web → root`, and stops the set on the first red step.

**The main-checkout rule (agent-agnostic, enforced in git, staged per decision Q1 = B then C):** only
`just land` and the owner commit in a main checkout. Git hooks are the one thing every agent passes
through, so that's where it lives. Rollout has two stages:
1. **Observe (from Phase 0 through the pilot):** a pre-commit *observer* in every main checkout logs each
   commit made there, and **never blocks**. It records: repo, cwd, `/dev/tty` openable?,
   `stdin.isatty()`?, parent-process chain, `W0M_LAND` / `W0M_OWNER_COMMIT` markers. The log is the
   per-agent TTY measurement we don't have.
2. **Enforce C (after the pilot):** a main checkout accepts a commit **only** when `just land` made it
   (`W0M_LAND` set by the lander) or the owner set `W0M_OWNER_COMMIT=1`. There's no TTY guessing, so it
   works identically for Claude, Codex, Antigravity, OpenCode and GUI commits. The owner override is
   recorded in the observer log, **not** as a commit trailer (the estate rule is no attribution
   trailers). It's a guardrail against accidents, not a security boundary: an agent *could* set the
   variable, and the log would show it.

(Git can't block edits in the main checkout. The commit gate is what makes those edits pointless.)

**Who is working on what = derived, not declared:** `orca worktree ps` / `orca worktree list --json`
(comment = ticket id) plus `git worktree list` for anything created outside Orca. This replaces
`_in/active-work.json` as a self-reported second SSOT and answers T274 AC6 structurally.

---

## 4. Plan — phased, sized for 2–3 agents (rev 4: owner decisions applied)

**Decisions applied (owner, 2026-09-23):**
- **Q1:** commit gate is observe-first, then enforce the land-only rule (C).
- **Q2:** generated files are discarded, regenerated, and a one-line notice is printed; the SDLC skills
  stop rendering them.
- **Q3:** delete `worktree_agent.py`.
- **Q4:** parent shims first; the AgDR-0025 symlink cutover comes later.

### Phase 0 — prerequisites (blocking)
1. **T408, agent-agnostic fix:** make `core.hooksPath` point at a **tracked** hook directory in every
   repo, or have the tracked `.husky/` shims self-install. Then *any* worktree (Orca, `git worktree add`,
   Claude, Codex) runs the full hook set.
   - AC: a commit from a fresh `git worktree add` runs the same hook log as the main checkout.
   - AC: missing hooks **fail the commit** instead of passing it.
2. **Orca registry hygiene + `rerere`:**
   - register `wom7func`;
   - drop the stale `wom7cfworkers`;
   - re-point `orca` at `wom7pr/orca`;
   - enable `rerere` in every repo via a versioned installer (same pattern as `install_hooks.py`).
3. **Main-checkout commit observer** (Q1 stage 1): a warn-only pre-commit hook in the main checkouts of
   the root, wom7web, wom7api and wom7func.
   - It appends one JSONL line per commit to `~/.cache/w0m/main-checkout-commits.jsonl`.
   - If the log write fails, it prints a warning and still never blocks. Advisory by design, stated in
     the hook header, so it isn't a silent fallback.
   - It ships **before** the pilot, so the log already holds a baseline of today's agents committing in
     main checkouts.

### Phase 1 — Orca as the one worktree factory (Q3, Q4)
1. Add a committed **`orca.yaml`** to each writing repo (wom7web, wom7api, wom7func first):
   ```yaml
   scripts:
     setup: python3 <W0M_ROOT>/scripts/worktree_setup.py          # absolute path finalised in impl
     archive: python3 <W0M_ROOT>/scripts/worktree_archive_check.py
   setupAgentStartupPolicy: wait-for-setup     # agent starts only after bootstrap succeeded
   ```
   - **`worktree_setup.py`** (fail closed on every step):
     1. **Parent shims (Q4):** compute every tracked symlink that escapes the repo (`git ls-files -s`
        mode `120000` + resolve), then ensure one shim per distinct target in the worktree's parent
        directory. Refuse if a target doesn't exist. Today that means about 6 shims:
        `…/wom7web/{project,.w0m,TASKS.md,wom7api}`, `…/wom7api/wom7web`, `…/wom7func/wom7api`.
     2. Verify that every one of the repo's escaping links now resolves; stop and name any that don't.
     3. Verify hooks resolve (Phase 0).
     4. Run `pnpm install --frozen-lockfile`; the shared pnpm store keeps it cheap.
     5. Copy the gitignored allowlist (`.infisical.json`, `.env*` if any).
     6. Print a banner: worktree, branch, "land with `just land`".
   - **`worktree_archive_check.py`:** refuse to archive while the branch has commits not on `beta`,
     unless forced.
   - **`worktree.sharedDirectories`:** **not** for `node_modules`, which differs per branch.
2. **Delete T411's parallel factory (Q3).** It's a clean cutover under AgDR-0025, and its layout is
   broken by construction (§0.2).
   - Remove `scripts/worktree_agent.py` and the `worktree-agent*` recipes in the root and `wom7api` justfiles.
   - Collapse the two divergent `test_agent_concurrency.py` copies into one.
   - After this there is **one** worktree location: `~/orca/workspaces/`.
3. Document the launch command in `AGENTS.md`: `orca worktree create --repo … --base-branch beta
   --comment T<id> --agent <any>`. One line covers every agent kind.

### Phase 2 — `just land` + `just land root` (Q2)
- **`scripts/land.py`** (Python, per the "no fragile nested bash" principle):
  - recipes `land <worktree|name>`, `land root [--ticket T<id>]`, `land --check` (merge-tree dry run
    against the current `beta`), and `land-status` (queue, plus which units would conflict);
  - one lock file under the root `.git/`, so no two landings ever race;
  - member steps as in §3, root steps as in §0.4; lineage groups land as a set in repo-dependency
    order, and the ticket status lands after the code;
  - every failure is **reported and stops**; nothing is skipped silently.
- **Generated files (Q2):**
  - Agent edits to `TASKS.md` and to `STATE.md`'s `W0M-STATE:BEGIN/END` and archive blocks are
    **discarded and regenerated**.
  - `land` prints one line per discarded file (`discarded agent edit to TASKS.md — regenerated from
    .tasks/`) and records it in the land log.
  - Hand-written `STATE.md` sections follow the register rule (additions-only, otherwise stop).
- **Atomic caller update (AgDR-0025 "100 % of callers"), shipped in the same ticket:**
  - edit `w0m-sdlc-start` / `-new` / `-archive` / `w0m-state-save` in **`wom7skills`** (canonical), then
    stamp, `relock` and sync to `.agents/skills` and the `@wom` root copy, so agents stop running
    `tasks-render` and stop committing `state-save`;
  - replace the pre-push "STATE.md blocked your push → `just state-save`, commit, push" instruction in
    `AGENTS.md` with "`just land` regenerates it";
  - `land root` runs the state-check the root repo is missing today.
- `land` sets `W0M_LAND=1` for its own commits, which the observer logs (Phase 0.3).

### Phase 3 — pilot, then enforce and default (Q1 stage 2)
- **Pilot:** 2 agents of **different kinds** (e.g. Claude + Codex, both via Orca) on two real tickets
  for about a week. wom7web is clean now that T422 is committed; start after it's pushed.
- **Measure:**
  - conflicts per land and time-to-land;
  - hook runs per worktree commit;
  - worktrees left behind;
  - discarded-generated-file notices (should fall to 0 once the skills are updated);
  - from the observer log, which agent kinds committed in main checkouts and whether each had a TTY.
- **Then:**
  - switch the observer to **enforce C** (land-only, `W0M_OWNER_COMMIT=1` override);
  - make the flow the default in `AGENTS.md`;
  - retire `_in/active-work.json` and the `active-work-heads-up` hook (Orca/git is the registry now);
  - close T274 AC6.

### Later — only if needed
- **T427, AgDR-0025 symlink cutover:** the 30 escaping links; about 62 wom7web code readers plus 28 root
  scripts resolve `W0M_ROOT` and fail closed; includes the Antigravity `wom7api/.agent` surface.
  After it, **delete the shims**.
- **T428, STATE handoff restructure (separate decision):** each session writes its handoff to its
  ticket's Status notes, and "PICK UP HERE" is generated from them. This removes the last hand-written
  hot spot in `STATE.md`.
- **Only if the pilot measures a need:** plan-time file ownership, a hot-file edit guard, `mergiraf` for
  TS/JSON/YAML, `merge=union` for `LESSONS.md`, batch integration branches.

---

## 5. Claude Code — optional adapter (not load-bearing)
For Claude sessions started **outside** Orca (Desktop/CLI at the `@wom` root):
- Don't rely on `claude -w`, subagent/workflow `isolation: worktree`, or Desktop background-session
  auto-isolation — all make **root-only** worktrees here.
- If ever wanted: a `WorktreeCreate`/`WorktreeRemove` hook in root `.claude/settings.json` that calls the
  same `orca worktree create`. (Docs: `.worktreeinclude` is then not processed and hook-made worktrees
  are not swept — `worktree_setup.py`/`just land` already own both. Hook `${CLAUDE_PROJECT_DIR}` stays at
  the launch root; `cwd` in hook input follows the worktree.)
- Until then the main-checkout commit gate (§3) is what keeps Claude honest too.

---

## 6. Decisions (owner, 2026-09-23)

| # | Question | Decision | Where it lands |
|---|---|---|---|
| — | PRs vs local queue | **Local merge queue, no PRs** (solo operator) | §3, Phase 2 |
| — | Concurrency | **2–3 agents** | whole plan |
| — | Orchestrator | **Orca; agent-agnostic core** | §3, Phase 1 |
| Q1 | Main-checkout commit gate | **Observe first (B), then enforce land-only (C)**; owner override logged, no trailer | Phase 0.3 → Phase 3 |
| Q2 | Agent edits to generated files | **Discard + regenerate + one-line notice**; skills updated atomically; handoff restructure deferred (T428) | Phase 2 |
| Q3 | `worktree_agent.py` | **Delete** (no wrapper) | Phase 1.2 |
| Q4 | Shims vs symlink cutover | **Parent shims first**, cutover later (T427) | Phase 1.1 → Later |
| — | `@wom` root | **One shared checkout, single committer `just land root`** | §0.4 |

Still open: **T428**, whether to move session handoffs from STATE.md into ticket Status notes. That
decision isn't needed for the pilot.

### 6.1 Context behind Q1, Q2, Q4 (measured 2026-09-23; kept for the record)

**Q1 — main-checkout commit gate: enforce from day one, or warn first?**
- Git can't tell agent commits from human ones. All of the last 70 root commits and the last 100
  wom7web commits carry one identity (`casualuser@gmail.com`), so the gate needs a *proxy*.
- The proposed proxy is "has a TTY", borrowed from `confirm_step.py`. That behaviour was **measured only
  for Claude Code** (no `/dev/tty`, `stdin.isatty()` False; `wom7web/project/scripts/confirm_step.py:15-19`).
  - Orca runs every agent inside a real PTY. Whether Codex, Antigravity or OpenCode shell tools hand
    that TTY to their subprocesses is **unmeasured**. If one does, the gate doesn't stop it.
  - GUI commits (Orca source-control panel, VS Code) have **no** TTY, so the gate would block the owner
    there. The deploy gate already shipped this bug once (`/dev/tty`-only, blocked the owner, fixed
    with the stdin fallback; `DEPLOY-CONFIRM.md:21-23,220-226`).
- No script auto-commits (checked `scripts/`, `wom7web/project/scripts/`, husky), so the gate affects
  only agents and the owner, not tooling.
- **Options:**
  - **A. Enforce on day one.** Fastest proof, but it rests on an unmeasured proxy.
  - **B. Warn for the pilot week.** Log every main-checkout commit to JSONL (tty? cwd, parent process
    name), then enforce. The log *is* the per-agent TTY measurement.
  - **C. No proxy.** Main checkouts accept **only** `just land` commits. The owner uses `just land` too,
    or an explicit `W0M_OWNER_COMMIT=1` recorded in the observer log (not a commit trailer; the estate bans attribution trailers). Fully agent-agnostic, at the cost
    of a habit change.
- *Recommendation:* **B, then C.** Go to A instead only if the log shows every agent kind is TTY-less.

**Q2 — agent edits to generated files at land: discard + regenerate, or refuse?**
- `TASKS.md` is **fully** generated (`tasks_render.py --check` exits 0). It is touched by 35 of 70 root
  commits since T411, because the SDLC skills tell agents to render it (`w0m-sdlc-start/SKILL.md:138`,
  `w0m-state-save`, `-new`, `-archive`; the canonical copies live in `wom7skills`).
- `STATE.md` is **mixed**:
  - lines 3-77: generated mechanical block (`W0M-STATE:BEGIN/END`, `state_doctor.py`);
  - lines 113-354: **hand-written** handoff (`⭐ PICK UP HERE — LATEST`, gotchas, how-to);
  - lines 355-448: generated archive.

  Agents commit `state-save` (13 commits since T411) because pre-push `state-check` fails when the
  mechanical block is stale.
- The question therefore splits in two.
  - **Generated regions** (all of `TASKS.md`, STATE's BEGIN/END and archive blocks): **discard +
    regenerate** is lossless, because the content is a pure function of `.tasks/` and repo state.
    *Refuse* would fail every land until the skills are changed in `wom7skills` and re-synced (a flag
    day). The "one line naming what was discarded" is what keeps it non-silent under AgDR-0025.
  - **Narrative STATE sections** are a register, so the additions-only rule applies. The `PICK UP HERE —
    LATEST` section is rewritten by every session, a true hot spot that regeneration can't fix.
    Structural option (follow-up): write the per-session handoff into the ticket's *Status notes*
    (disjoint per ticket) and **generate** "PICK UP HERE" from the most recent ones. That changes the
    `w0m-state-save` skill.
- *Recommendation:* discard + regenerate + one-line notice for generated regions. Update the skills to
  stop rendering, so the discard becomes a no-op. Decide the handoff restructure separately.

**Q4 — parent shims first, or the AgDR-0025 symlink cutover first?**
- **Cutover size:** 30 tracked links. In wom7web, 293 files mention the linked paths (905 refs, many of
  them docs). About **62 code files** are in `project/scripts` (+ tests), plus **28 root scripts**.
  - Each code reader must resolve the estate root explicitly (`W0M_ROOT`, fail closed), then the links
    are deleted and the docs updated.
  - It also covers the 4 `wom7api/{.agent,.codex,.gemini,.kilocode}` links. `.agent/` is Antigravity's
    live surface, so removing them changes Antigravity's config inside wom7api.
- **Shim size:** about 6 links, *outside every repo*, generated by the setup script from the measured
  list, with no repo change: `~/orca/workspaces/wom7web/{project,.w0m,TASKS.md,wom7api}`,
  `…/wom7api/wom7web`, `…/wom7func/wom7api`.
- **AgDR-0025 tension:** it bans "shadow symlinks in legacy locations". The shims are not in a legacy
  location and live in no repo; they are generated, verified and temporary, with removal ticket T427.
  That arguably complies, but it's the owner's call.
- **Live-root semantics are the same either way.** Shims point at the live root, and `W0M_ROOT` would
  too. Both are consistent with §0.4 (root = one shared checkout).
- *Recommendation:* **shims first.** Cutover-first would block the pilot behind a roughly 90-file
  refactor of the very gates the pilot depends on.

## 7. Tickets

| Ticket | Phase | Title | Depends on |
|---|---|---|---|
| **T408** (existing, P1) | 0 | Worktree commits must run the full hook set: tracked hooksPath, fail closed | — |
| T423 (new) | 0 | Orca registry hygiene + `rerere` installer + main-checkout commit **observer** (warn-only JSONL) | — |
| T424 (new) | 1 | `orca.yaml` + `worktree_setup.py` (computed parent shims, link verification, hooks, deps, env) + `worktree_archive_check.py` for wom7web/api/func; **delete** `worktree_agent.py` and its recipes; one `test_agent_concurrency.py` | T408 |
| T425 (new) | 2 | `just land` / `land root` / `land --check` / `land-status`; discard-and-regenerate views; additions-only registers; root state-check; **atomic skills + AGENTS.md update** (wom7skills → sync) | T424 |
| T426 (new) | 3 | Two-agent-kind pilot, metrics from land log + observer log; switch observer to **enforce C**; AGENTS.md default; retire claim file and heads-up hook; close T274 AC6 | T425, T423 |
| T427 (new) | later | AgDR-0025 cutover of the 30 escaping tracked symlinks (`W0M_ROOT`, fail closed), then delete the parent shims | T426 |
| T428 (new, decision pending) | later | Move session handoffs from STATE.md into ticket Status notes; generate "PICK UP HERE" | T425 |

Critical path: **T408 → T424 → T425 → T426** (T423 runs in parallel with T408). One agent can take
T408 + T423 at the same time as another starts T424's design, which dogfoods the 2-agent shape early
(still in main checkouts, so keep their files disjoint).

Also in passing: close **T241** (implemented at `scripts/w0m_audit.py:207-234`, commit `7414aea0`, ticket
still open); fix doc drift `wom7web/docs/flows/orca-parallel-agents.mmd:9` ("agy") vs
`ORCA_INTEGRATION.md:56` ("opencode") — and redraw that flow to match this model (it still shows an
"Orca Merge Strategy (Compare & Diff)" step that doesn't exist).

---

## Sources
- Orca: `orca worktree create --help`, `orca worktree list --json`, `orca repo list` (run 2026-09-23);
  source `wom7pr/orca`: `src/shared/orca-yaml-hook-types.ts`, `src/main/hooks.ts:117-150`,
  `src/main/worktree-runner-script.ts`, `src/main/git/worktree-shared-directories.ts`.
- git: [git-worktree](https://git-scm.com/docs/git-worktree) · [git-rerere](https://git-scm.com/docs/git-rerere) ·
  [git-merge-tree](https://git-scm.com/docs/git-merge-tree)
- [GitHub merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue) (concept only) ·
  [Anthropic — C compiler with parallel Claudes](https://www.anthropic.com/engineering/building-c-compiler) ·
  [Mergiraf languages](https://mergiraf.org/languages.html)
- Claude Code (adapter section only, fetched 2026-09-23): [Worktrees](https://code.claude.com/docs/en/worktrees) ·
  [Workflows](https://code.claude.com/docs/en/workflows) · [Agent teams](https://code.claude.com/docs/en/agent-teams) ·
  [Agent view](https://code.claude.com/docs/en/agent-view)
- Estate: `wom7web/openspec/changes/archive/2026-09-20-parallel-agents-concurrency-architecture/`,
  `scripts/worktree_agent.py`, `justfile:126-134`, `.tasks/T408.md`, `.tasks/T274.md`, `.tasks/T411.md`,
  `wom7web/.pre-commit-config.yaml:41-47,171-177`, `wom7web/ORCA_INTEGRATION.md:15-17,44-74`,
  `wom7web/docs/superpowers/specs/2026-09-03-agent-coordination-claim-file-design.md`,
  `LESSONS.md:299-318,850-856`, `docs/DEPLOY-CONFIRM.md`.
