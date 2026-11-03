---
name: w0m-ticket-audit
description: Audit a w0m ticket's recorded state — status, acceptance criteria, claims in its body, and release delivery state — against current codebase/spec/deploy reality instead of trusting checkboxes. Trigger when asked to review/audit a ticket, verify whether completed tickets or specs match live state (`just reality-verify`), reconcile claims against the codebase or live infra, or explain why a ticket looks stale/contradictory. Read-only: produces evidence without editing `.tasks/` or `TASKS.md`.
metadata:
  version: "2026.11.03-1793683940"
---

# w0m-ticket-audit — verify tickets & specs against reality, not checkboxes

A ticket's `status:` and `[x]` boxes are a claim someone made at the moment work felt done. This
skill re-checks that claim against what is *currently* true across code, SQL migrations, OpenSpec
specifications, and `releases/*.json` deployment manifests (`scripts/ticket_audit.py`).

## 1. Run the deterministic reality auditor first

From the `@wom` workspace root (or your isolated `agent-tree`):

```bash
TICKET=T382   # substitute the requested id
just ticket-audit ${TICKET} --offline
# Corpus-wide completed tickets + canonical OpenSpec reality gate:
just reality-verify
```

Read `.tasks/${TICKET}.md` in full — frontmatter (`status`, `queue`, `closed_as`, `spec`,
`x_ac_done`, `x_ac_total`, `x_ac_pct`, `x_blocked_by`, `x_synced`) and body (`Summary`,
`Acceptance criteria`, `Definition of Done`, `Links`, `Status notes`).

## 2. Cross-check the four surfaces + release delivery state

A ticket's state is echoed across four tracking/delivery surfaces (`T616`):

```bash
grep -n "\[${TICKET}\b" TASKS.md .tasks/archive/TASKS-archive.md
python3 scripts/tickets_frontmatter_sync.py --check
just ticket-audit ${TICKET} --gh          # optional live GitHub issue check (webomage/w0m)
ls -1 releases/*.json | tail -n 3         # latest deployed release manifests
git status --short .tasks/${TICKET}.md TASKS.md
```

Report any mismatch (status, AC count, priority, uncommitted diff) across `.tasks/${TICKET}.md`,
`TASKS.md` (or `.tasks/archive/TASKS-archive.md` for rotated `done` rows), `tasks_query.py` AC
parity, GitHub issue state, and `delivery_state` (`deployed (<version>)`, `landed_pending_deploy`,
or `no_commit_trace`). Never collapse `landed_pending_deploy` into `"live in production"`.

## 3. Verify each acceptance criterion independently — don't trust the checkbox

For every AC, re-derive the answer from current state rather than reading the box:

| AC claims about... | How to actually check | Never do |
|---|---|---|
| A file/config/path exists or has a property | Read/inspect it directly across all 7 estate repos | Assume from the ticket's prose |
| Code/a symbol/a call path exists or was changed | `just ask "<symbol>"` / `just search "<pattern>"` | Trust a description of the diff |
| A SQL table/view/constraint/trigger exists | Verify in `w0m-api/supabase/{baseline,migrations}` + `supabase_surface_drift_check.py` | Trust `.from("...")` in TS alone |
| A secret was rotated, removed, or is dead | Compare digests or run a behavioral check — **never print secret values** | `infisical secrets get` and grep output |
| A gate/probe/test proves something | Find the named suite in `w0m-web/project/test-suites.json` and run it | Report "covered by X" without running X |
| Another ticket blocks/relates to this one | Read *that* ticket's current `.tasks/T##.md` frontmatter | Trust cached prose |
| Live deployment / DB migration state | Compare git commit ancestry against `releases/*.json` (`delivery_state`) and live probes | Assume `status: done` means deployed |

Classify each AC as one of:
- ✅ **confirmed** — independently verified true right now, with evidence shown
- 🔴 **contradicted** — the box's claim does not match current reality
- ⚠️ **stale** — was true when written, but the depended-on surface moved or retired
- ❔ **unmeasurable** — no offline tool/probe available from this environment

🔴 **Unmeasurable must never collapse into pass or fail.** Give it its own state (`exit 2` in gates)
and state what is needed to measure it.

## 4. Report

```markdown
# Ticket Reality Audit — T<id>

**Recorded**: status=`<x>`, `<done>/<total>` ACs (`<pct>%`) · **Cross-surface**: <agree | disagree> · **Delivery**: `delivery_state: <deployed (...) | landed_pending_deploy | no_commit_trace>`

| AC | Recorded | Verdict | Evidence |
|---|---|---|---|
| **AC1** | `[x]`/`[ ]` | ✅/🔴/⚠️/❔ | one line: what was checked, how, result |

**Bottom line**: is the recorded status trustworthy? Name any contradicted AC, surface disagreement,
pending deploy state, or ❔ item requiring owner credentials or a new probe.
```

Do not edit `.tasks/`, `TASKS.md`, or flip `status:` inside this read-only audit skill — remediation
belongs to an explicit ticket/archive workflow.
