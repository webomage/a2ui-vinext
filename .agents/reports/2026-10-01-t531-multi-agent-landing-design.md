# T531 design: how several agents change, commit and push in one estate

Ticket: [[T531]] (per-agent workspace sets). Related: [[T527]] (state-check blind at push), [[T235]] (stage guard), [[T481]] (stable and release worktrees).
Date: 2026-10-01. Status: proposal for the owner's decision, nothing built. Evidence is from one day of two agents in one working tree, measured, not assumed.

## 1. The question

Owner, 2026-10-01: how can several agents make careful simultaneous edits in one shared tree, and what makes commits and pushes succeed while the tree already holds someone else's uncommitted changes?

The short answer is that "dirty tree" is five separate problems with five separate fixes, and only one of them needs a second working tree.

## 2. What went wrong today, by mechanism

| # | Incident (measured 2026-10-01) | Mechanism | Fix class |
|---|---|---|---|
| 1 | The other agent staged T529 and T530 while I prepared a commit; mine would have carried them | One index shared by every agent | commit by path |
| 2 | Every commit runs `pre-commit`, which stashes unstaged files into `~/.cache/pre-commit/patch*` (1,038 patches on disk); the memory note records two cases where the restore failed and files vanished | Hooks run against a tree that is temporarily rewritten under a concurrent writer | run hooks on a snapshot |
| 3 | Two of my commits were blocked until I regenerated `docs/DECISIONS.md`; the deploy preflight failed on a missing board row; the epic vocabulary file held the other agent's `roots-epic` hunks beside my `hero-epic` ones | Derived files (board, STATE, decisions index, vocabulary, feature index, dashboard) are whole-tree functions that every commit must keep fresh | derive at landing only |
| 4 | Pushes of `wom7web` passed `state-check` for weeks because its trigger paths no longer exist in that repo; the deploy, which runs on a clean release worktree, was the first gate to see the truth | Push gates read the working tree, or skip; only the deploy gate evaluates a snapshot | gate the commit, not the tree |
| 5 | I had "T529" in mind; the other agent filed T529 and T530 first; I re-checked and took T531 by exclusive create. Both agents also edited the same hand-kept `SECTION_SLUGS` dict and the end of `LESSONS.md` | Identifiers allocated by "look at the max"; registries that are append-at-the-end | atomic allocation, one source |

Not an incident but the same family: the stage guard (T235) is a static registry plus a live `lsof` probe. Its registry holds no paths today, and the probe only sees a file while a process has it open.

## 3. What was verified, and what was not

Verified today:

- **Snapshot cost.** `git archive HEAD` of all 10 repos is 334 MB and 1.2 s (wom7web 274 MB, 0.87 s; root 11.8 MB). The "about 3 GB" in [[T531]] is a full worktree with `node_modules`, not what a gate that reads files needs.
- **Pathspec commit.** In a throwaway repo, `git commit -m msg -- b.txt` landed only `b.txt`, left another agent's staged `a.txt` staged, and left their unstaged `c.txt` intact. The hook saw a temporary index containing only `b.txt`. During the hook run pre-commit had reverted both other files on disk, then restored them.
- **Generation from a snapshot.** The decisions index regenerated correctly from a `git archive` of the root with member repos linked in (impure: the members were the live trees).

Not verified, and to be tested before relying on it:

- Whether the `oxfmt` hook (`oxfmt --write && git add`) behaves under the temporary index of a pathspec commit.
- Whether the heavy gates (vitest, typecheck, deno) can run on a snapshot with `node_modules` linked read-only from the stable worktree.
- Whether pre-push can be pointed at a snapshot directory without reimplementing its 26 steps.

## 4. Proposed architecture

Five layers, cheapest and highest leverage first. Each layer removes one row of the table above and does not depend on the layers after it.

**L1. Commit by path.** `just commit -m <msg> -- <paths>` is `git commit -- <paths>` plus a refusal when no path is named. It removes row 1 and needs no new infrastructure. It does not remove row 2.

**L2. Derived files are produced at landing, not at every commit.** Today each commit must leave the board, STATE, decisions index, vocabulary and feature index current, so each commit reads the other agent's work. Instead:

- Per-commit hooks on derived files become advisory.
- A single `just land` regenerates them once, from the merged result, and commits them as one `chore(derived)` commit.
- The deploy preflight stays the backstop, as it is today.

This removes the largest class (row 3). The cost is that STATE and the board can lag HEAD between landings; STATE already calls itself recorded, not measured.

**L3. Gates evaluate the commit, not the tree.** A gate runs in a snapshot of what is being committed or pushed (1.2 s, no dependencies for the cheap gates). This answers "how do commits and pushes succeed while the tree is dirty": a dirty file can neither fail the gate nor rescue a bad commit, and no stash is needed, so the window in row 2 disappears. It also generalises the one gate that already works this way, the deploy preflight, to push time. Heavy gates need dependencies; link them from the stable worktree, read-only.

**L4. Atomic identifiers and one source per fact.**

- `just ticket-new` allocates the next id with exclusive create in a loop (the same primitive I used by hand today), and does the board render in the same step so a new ticket cannot be rowless.
- Delete the hand-kept `SECTION_SLUGS` dictionary and read epic slugs from the `> **Epic slug:**` lines in `ROADMAP.md`. The sync script today checks one copy against the other, which is a dual source of truth and a hot file for two agents.
- Put each lesson in its own file, or sort the file by key, so two appends do not share an anchor.

**L5. Workspace sets for long parallel work.** A worktree of every member repo, own index, own `node_modules`, branch `agent/<name>`, landed by `just land`. About 3 GB each, so capped. After L1 to L4 this is only needed for work that runs for hours and touches many files; it is no longer the first thing to build.

Optional, alongside L1: dynamic claims. `.agents/claims/<agent>.json` lists tickets and paths with a time to live, and `stage-guard` reads it. This turns the static co-tenancy registry into something that reflects who is working where now.

## 5. The landing protocol

`just land` in the shared repo:

1. Take the land lock (same mechanism as the stable lock, which refuses re-entry).
2. Fetch, then rebase local commits onto `origin/beta`.
3. Regenerate every derived file once from the merged tree.
4. Snapshot the result and run the blocking gates on the snapshot.
5. Commit the derived files as one commit, push, release the lock.

Two agents landing at once queue on the lock; neither sees the other's half-finished state, because gates read snapshots.

## 6. Residual risks

- **Same-file edits.** Path granularity cannot separate two agents' edits to one file. The hot files are append-only registries (L4) and generated files (L2); both are addressed structurally. Anything else needs hunk-level staging (`git add -p`), which is a human or agent discipline, not a tool.
- **A snapshot gate is only as honest as its inputs.** A gate that reads a path outside the snapshot (a sibling repo, `~/.w0m`) silently reads the live tree again. Each gate that does needs a test, as [[T527]] AC3 proposes.
- **Lock starvation** if a landing hangs. The lock needs a time limit and a visible holder, as the stable lock has.

## 7. Order of work and cost

| Step | Content | Removes | Cost |
|---|---|---|---|
| 1 | L1 plus the three untested items in section 3 | row 1 | small |
| 2 | L4: atomic ticket creation with render, vocabulary from ROADMAP | row 5, part of row 3 | small |
| 3 | L2: derived files at landing, hooks advisory per commit | row 3 | medium |
| 4 | L3: snapshot gates in `land` and pre-push | rows 2 and 4 | medium |
| 5 | L5 and claims, only if a real need remains | residual | large |

[[T531]] currently orders the workspace sets first and assumes 3 GB per set. This design reverses that order; the ticket should be amended once the owner has decided.
