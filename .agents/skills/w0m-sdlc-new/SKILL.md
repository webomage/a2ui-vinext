---
name: w0m-sdlc-new
description: >
  Task-creation gate of the w0m SDLC lifecycle. Trigger when turning a request/idea/audit-finding
  into a tracked ticket — "create a ticket for X", "file this as a task", "add T## for …". Drafts
  a well-formed ticket from the template, then IMMEDIATELY runs w0m-sdlc-research to ground it
  against knowledge + code state before it enters the queue — so nothing is filed that's already
  done, duplicated, or based on wrong assumptions. Project-agnostic via `.w0m/sdlc.json`.
metadata:
  author: w0m
  namespace: w0m-sdlc
  gate: new
  version: "2026.11.22-1795386861"
---

# w0m-sdlc-new — the task-creation gate

Turn a request into a **grounded, well-formed ticket**. A ticket is not created until it has been
researched against reality — this is where "verify after task creation" lives.

## Step 0 — Load config
Read `.w0m/sdlc.json` (walk up from cwd; if none, check one level down into child repos). Use
`tickets` (source/board/dir/pattern/template/id_prefix/sync), `specs`, `repos`, `vcs`,
`conventions`.

## Steps
1. **Capture the request.** What outcome is wanted, and why. Note the originating source (audit
   finding, roadmap epic, owner ask, bug).
2. **Allocate the id & scaffold the ticket.**
   - Check if an eligible duplicate ticket can be recycled: `just ticket-recycle --list`.
   - If not recycling, allocate atomically:
     `just ticket-new "<Title in imperative mood>" --epic <epic> --area <area> --priority <P1|P2|P3>`
     (or query the next free ID via `just ticket-next`).
   - **NEVER manually guess or calculate next ticket numbers.** `just ticket-new` atomically queries `origin/beta`, local `.tasks/`, and active worktrees with file-locking to prevent ID collisions (`ticket_collision`) and gaps (`ticket_gap`).
   - In an agent worktree, `just ticket-new` creates `.tasks/DRAFT-<slug>.md` (or `--immediate` for immediate `T<N>`), promoted and compacted on `session-complete` offload.
3. **Refine ticket sections** in `{tickets.dir}/{pattern}`: frontmatter (`id`, `title` imperative, `status:
   queued`, `queue`, `priority`, `repos`, `epic`, `spec`, `tags`, `created`), then `## Summary`,
   `## Acceptance criteria` (observable/testable checkboxes — required), `## Definition of Done`
   (per `specs.standard`), `## Links` (epic/spec/related `[[T..]]`).
4. **Ground it — pre-flight duplicate check & invoke `w0m-sdlc-research`** on the draft:
   - Run automated duplicate check: `just ticket-dups --check-draft <draft-file>`. If a high match ($\ge 0.50$) is reported, evaluate if the scope is already tracked.
   - Invoke `w0m-sdlc-research` on the draft.
   - Act on its verdict:
     - **already-done / obsolete** → do NOT create; report the evidence and stop (or file as done).
     - **duplicate / merge** → fold into the existing ticket instead; don't create a second.
     - **revise** → apply its edits (right-size scope, fix claims, add prior-art + dependency links).
     - **proceed** → continue.
5. **Finalize & Sync (same commit).** Write/save the ticket to `{tickets.dir}/{pattern}`. Run
   `just tasks-render` to refresh `TASKS.md`. Run `just sync-tickets` to mirror the ticket to GitHub
   Issues + Projects v2 and record `gh_issue` frontmatter. Commit ticket and board together:
   `git add .tasks/T##.md TASKS.md w0m-web/project/tickets*.json && git commit -m "chore(T##): create <title>"`.

## Conventions
From config `conventions`: conventional commits w/ id, never skip hooks, no coauthor trailer, tool
ladder. Ticket + board (+ GH) created together, one commit. Absolute dates.

## Next gate
The ticket now sits in the queue. When it's picked up, `w0m-sdlc-start` begins it (and re-runs
`w0m-sdlc-research` before work, catching anything that changed since creation).
