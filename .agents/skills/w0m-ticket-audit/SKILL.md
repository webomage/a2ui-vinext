---
name: w0m-ticket-audit
description: Audit a w0m ticket's recorded state — status, acceptance criteria, claims in its body — against current reality instead of trusting its checkboxes. Trigger when asked to review/audit a ticket, verify whether a ticket is "really" done, reconcile a ticket's claims against the codebase or live infra, or explain why a ticket looks stale/contradictory. Read-only: it produces evidence, it never edits the ticket, TASKS.md, or flips status.
metadata:
  version: "2026.10.26-1793009642"
---

# w0m-ticket-audit — verify a ticket against reality, not its own checkboxes

A ticket's `status:` and `[x]` boxes are a claim someone made, usually at the moment the work
felt done. This skill re-checks that claim against what is *currently* true — the same exercise
that found T201 mid-session with a staged-but-uncommitted status flip, and that a background
session can independently complete without the foreground session noticing.

## 1. Load the ticket

```bash
TICKET=T196   # substitute the requested id
cat /Users/proto/Projects/@self/@wom/.tasks/${TICKET}.md
```

Read the full frontmatter (`status`, `x_ac_done`, `x_ac_total`, `x_ac_pct`, `x_blocked_by`,
`x_synced`) and the full body — Summary, Acceptance Criteria, Definition of Done, Links, Status
notes. The status notes are the ticket's own history; don't skip them.

## 2. Cross-check the four surfaces that are supposed to agree

A ticket's true state lives in one place, but it is *echoed* in three others. Disagreement
between them is itself a finding — report it before doing anything else, the way the T201
in-progress/done split was found by diffing exactly these surfaces:

```bash
cd /Users/proto/Projects/@self/@wom
grep -n "${TICKET}\b" TASKS.md
gh issue view <gh_issue-from-frontmatter> --repo webomage/wom7board
python3 -c "import json; d=json.load(open('w0m-web/project/tickets.json')); print(d.get('${TICKET}'))"
git log -3 -- .tasks/${TICKET}.md
git status --short .tasks/${TICKET}.md TASKS.md   # staged-but-uncommitted flips hide here
```

Report any mismatch (status, AC count, priority) between frontmatter / `TASKS.md` / GitHub issue /
`tickets.json` cache by name — don't silently pick one as authoritative.

## 3. Verify each acceptance criterion independently — don't trust the checkbox

For every AC, re-derive the answer from current state rather than reading the box. Which method
applies depends on what the AC claims:

| AC claims about... | How to actually check | Never do |
|---|---|---|
| A file/config/path exists or has a property | `Read`/`Glob`/`grep` it directly | Assume from the ticket's prose |
| Code/a symbol/a call path exists or was changed | `codegraph_explore` / `graphify` on the named symbols | Trust a description of the diff |
| A secret was rotated, removed, or is dead | Compare digests or run a behavioral check (401/200 against the issuer) — **never print or reproduce the value**, per existing secret-hygiene convention | `infisical secrets get`/`list` and grep the output |
| A gate/probe/test proves something | Find the named probe (`test-suites.json`, `project/scripts/`) and actually run it; if it doesn't exist, say so explicitly | Report "should be covered by X" without running X |
| Another ticket blocks/relates to this one (`x_blocked_by`, `## Links`) | Open *that* ticket's current frontmatter — it may have moved since this ticket last synced | Trust this ticket's cached description of the other one's state |
| A host/infra surface (secrets store, launchd, cron, a deployed service) | Query it live (`infisical`, `launchctl`, `crontab -l`, `gh`, `supabase`, etc.) | Assume the containment/rotation note is still current |

Classify each AC as one of:
- ✅ **confirmed** — independently verified true right now, with the evidence shown
- 🔴 **contradicted** — the box's claim does not match current reality
- ⚠️ **stale** — was true when written/checked, but the thing it depended on has since changed (e.g. a "dead" secret whose issuer wasn't re-queried, a linked ticket that reopened)
- ❔ **unmeasurable** — no tool/probe available to check it from here

🔴 **Unmeasurable must never collapse into pass or fail.** Give it its own state and say what
would be needed to measure it (a probe to write, an owner-only credential, host access). Reporting
"could not measure" as "found a violation" — or worse, as a pass — is the exact failure this
estate's own measurement tooling was built to avoid.

## 4. Report

```markdown
# Ticket Reality Audit — T<id>

**Recorded**: status=<x>, <done>/<total> ACs (<pct>%) · **Cross-surface**: <agree | disagree: name which>

| AC | Recorded | Verdict | Evidence |
|---|---|---|---|
| AC1 | [x]/[ ] | ✅/🔴/⚠️/❔ | one line: what was checked, how, result |
| ... |

**Bottom line**: is the recorded status trustworthy? Name any AC where the box and reality
disagree, any surface that disagrees with another, and any ❔ that needs an owner or a new probe
to resolve.
```

Do not edit the ticket, `TASKS.md`, `tickets.json`, or flip `status:` yourself — this skill's job
ends at evidence. Acting on the findings (ticking a box, reopening a ticket, filing a new one) is
the owner's or another gate's call, made with the report in hand.
