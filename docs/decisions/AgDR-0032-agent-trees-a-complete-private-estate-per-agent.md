---
id: AgDR-0032
title: "Agent trees: each agent works in its own complete copy of the estate on a local-only branch, landed by rebase and push, with no pull requests"
timestamp: 2026-10-04T07:20:00-05:00
agent: claude-code
model: claude-sonnet-5-5
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T531
---

# AgDR-0032 — Agent trees: a complete private estate per agent

## Y-statement

> In the context of **several agents and one person editing the same working tree of a nine-repository estate that commits to a single branch (`beta`)**, facing **one agent's
> uncommitted files reaching another agent's commit, hooks and push**, we decided **to give each agent its own complete copy of the estate (the umbrella repo with every member repo
> nested inside it) on a local-only branch `agent/<name>` cut from `origin/beta`, landed with fetch, rebase and `git push origin HEAD:beta`, with no pull requests and no remote
> branches** to achieve **isolation of working state without leaving the one-branch model the owner wants**, accepting **that derived files and ticket ids still collide at landing
> and need their own guards, and that the live checkout stops being an agent's workspace**.

## Context

Measured on 2026-10-03, in one working session in the shared live tree:

- three pushes blocked by another agent's uncommitted files (the pre-push gates read the working tree);
- two commits where the tickets hook added another agent's untracked ticket to a commit made by pathspec;
- 21 files of another agent's work in the shared staging area during one commit;
- a ratchet baseline lowered to a value read from the live tree that a clean checkout did not reproduce, which failed the release-shaped test tier;
- a second blocking failure caused by two agents taking "the next free ticket id" from their own views (T541 held unpushed in one tree while T542 landed from another).

Piloted the same day: a worktree of `wom7web` and of the umbrella on a local branch, landing with `git push origin HEAD:beta`. Both landed through every hook with nothing of another
agent's in the commit. Two layout mistakes were measured: a root worktree without its member repos fails the root hooks on broken couplings, and one missing a single member
regenerated `docs/DECISIONS.md` one entry short and the freshness hook accepted it. With all nine repos nested, the regenerated file was byte-identical to `origin/beta`.
A full set measured 341 MB without dependencies and took seconds to create (the 2026-10-01 design assumed 3 GB per set).

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Keep one shared tree, commit by pathspec, fingerprint neighbours (what was done through 2026-10-03) | no new tooling | every incident above happened under it; relies on each agent's discipline and on hooks that read the whole tree | rejected as the primary fix, kept as the fallback for the live tree |
| Feature branches and pull requests per agent | the standard answer to this problem | the owner does not want multiple remote branches and PRs; adds a review step nobody performs here | rejected by the owner (2026-10-03) |
| A per-agent tree on a local-only branch, landed to `beta` by rebase and push | isolation; no remote branches; one integration branch | disk (341 MB per set), derived files still collide at landing, ticket ids need a guard | **chosen** |
| Build on Orca's own worktree root and its manager | reuses an existing UI | Orca manages worktrees of one repo, not a nine-repo estate; the layout and the ticket-id guard are estate rules | rejected: stands alone, reusing `release.py` for the repo list and the fixture provisioning |

## Decision

1. A set is `~/.w0m/work/<name>/w0m`: the umbrella worktree with every repo `release.estate_repos` finds nested inside it, each on local branch `agent/<name>` created from `origin/beta`
   after a fresh fetch. Creation refuses unless every repo has an `origin/beta`, is atomic (a failure part-way removes everything it made), and the live estate is never modified.
2. At most 3 sets. A set is removed with a command that refuses unpushed commits and modified tracked files unless forced. No automatic pruning.
3. `land` runs from inside a set: it refuses a repo that is not on an `agent/` branch and any modified tracked file, fetches, rebases onto `origin/beta`, aborts a conflicting rebase
   with nothing pushed and the files named, checks ticket ids against the fresh `origin/beta` (a collision or a gap is refused), and pushes `HEAD:beta`, members first and the umbrella last. It never forces. A push that
   loses a race is fetched, re-checked, rebased and retried, up to 3 attempts.
4. Nothing is ever pushed under an `agent/<name>` branch name.
5. The live checkout is the owner's and the deploy's. Agents do not edit it.

## Consequences

**Positive:** none of the five incident classes above can occur through shared working state; every hook and gate judges only the agent's own change; no pull requests and no remote branches.

**Negative:**
- About 341 MB per set (more once dependencies are installed, which this does not do).
- Derived files (`TASKS.md`, `STATE.md`, `docs/DECISIONS.md`) are rewritten by most commits, so two agents landing close together will conflict in them until T531 AC3 (derive at landing) exists. Today the rebase aborts cleanly and the agent regenerates.
- The ticket-id guard only sees `origin/beta`. Two trees that both create "the next id" and land one after the other are caught at the second landing, after the renumbering cost; the durable fix is T531 AC2 (atomic id allocation).
- A tree has its own code-graph index; whether `just ask` needs a per-tree index was not measured.
- Moving an agent into its own tree is a start-up change for that agent, outside this repository.

## What this does NOT decide

- Regenerating derived files at landing, a landing lock, and snapshot-based gates (T531 AC3 to AC5).
- Installing dependencies per set, and automatic pruning of old sets.
- Whether the live checkout should also be protected from agent edits by a hook.
- Anything about releases: `release.py` still cuts from `origin/beta`.
