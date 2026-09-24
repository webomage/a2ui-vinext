# Source research — parallel agents: isolation, collection & merge (Claude Cowork, 2026-09-23)

> **Provenance:** produced in a Claude **Cowork** session without web access. It was saved there as
> `claude/parallel-agents-isolation-and-merge.md`, which is not on this machine, and pasted by the
> owner into a Claude Code session on 2026-09-23. It is preserved verbatim-in-substance as the input
> to [the accepted plan](2026-09-23-parallel-agents-isolation-and-merge-proposal.md).
> **Superseded by that plan** wherever they differ. The plan's §1 grades each claim against the live
> docs and the estate. This file is a record, not instructions.
> **Tickets:** the plan became T423–T428 (T428 owns the session-handoff part).

## Problem
Workflow agents share one working tree, so concurrent Edit/Write calls clobber each other. One agent's
`git add -A` / `checkout` / `stash` sweeps up another's half-done edits, and tests run against mixed state.

## Model: isolate → hand off → integrate serially → verify

### 1. Isolate every *writing* agent
- Workflow script: `agent(prompt, { isolation: 'worktree' })`. Custom subagents: `isolation: worktree`
  in frontmatter. Read-only agents don't need it (~200–500 ms + disk per worktree).
- Claude Code blocks Edit/Write into the main checkout, bash cwd in the main checkout, and git redirects.
- Worktrees land in `.claude/worktrees/<name>/` on branch `worktree-<name>`, so add that directory to `.gitignore`.
- Base-ref gotcha: the default `worktree.baseRef: "fresh"` branches from origin/HEAD, not from the
  current branch and not from uncommitted work. Use `"head"` for in-progress work.
- Fresh checkout means no gitignored files. Use `.worktreeinclude`, install deps per worktree, and give
  each agent distinct ports and DBs. Run `git lfs pull` inside the worktree.
- Cleanup: unchanged worktrees are auto-removed. Changed ones stay until the periodic sweep, so the
  orchestrator should remove them after merge.
- Agent teams do NOT isolate teammates, so partition by file there.

### 2. Hand-off contract
Each worker commits on its own branch, never merges or pushes to main, and runs its scoped tests. It returns
`{ unit_id, branch, base_sha, head_sha, files_changed[], tests_passed, shared_requests[], summary }`.

### 3. Collect & merge in ONE serialized integration step
- Record the base SHA before fan-out, then create `integrate/<run>` from it.
- Merge one branch at a time and run the tests after each (a local merge queue).
- On a conflict, the resolver gets both intents plus both diffs. On red tests, rebase and re-run that
  worker, or drop it and report it.
- Tooling: `git merge-tree --write-tree` (git ≥ 2.38), `rerere`, `mergiraf`.
- Never merge lockfiles; regenerate them.
- In human-reviewed repos, use one PR per unit plus the GitHub merge queue.

### 4. Prevent conflicts upfront
Give each unit disjoint file ownership. The integrator owns the hot shared files (package.json,
lockfiles, registries, barrels, migration numbering, CHANGELOG, i18n) and workers emit
`shared_requests` instead of editing them. Optionally, a PreToolUse hook blocks out-of-scope edits.

### 5. Verify
Run the full suite and build on the integration branch, with the tests as arbiter. Anthropic's C
compiler experiment is the example: subdivide the work against an oracle.

## Sources (as given)
code.claude.com/docs/en/{worktrees,sub-agents,workflows,agents,agent-teams,agent-view,hooks} ·
git-scm.com/docs/{git-worktree,git-rerere} · mergiraf.org · GitHub merge queue docs ·
anthropic.com/engineering/building-c-compiler · github.com/dagger/container-use
