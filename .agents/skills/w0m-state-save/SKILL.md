---
name: w0m-state-save
description: >
  Write the session handoff into the estate-root STATE.md before ending a session or archiving a ticket.
  Regenerates the mechanical managed block via `just state-save`, then interviews for the
  EDITORIAL sections only — pickup block, gotchas, owner actions. Trigger on "save state",
  "write the handoff", "end of session", or from w0m-sdlc-archive step 6.
metadata:
  author: w0m
  namespace: w0m
  version: "2026.09.24-1790232259"
---

# w0m-state-save — write the handoff

`STATE.md` is the first thing the next session reads. It has two halves and they are maintained by
completely different means. Confusing them is the failure this skill exists to prevent.

| Half | Bounded by | Who writes it | How it goes wrong |
|---|---|---|---|
| **mechanical** | `W0M-STATE:BEGIN` … `W0M-STATE:END` | `just state-save`, never a human | hand-edited, then it *certifies* a stale number |
| **editorial** | everything outside those markers | you, with the user | left describing a thread that finished two sessions ago |

## Step 1 — regenerate the mechanical block

```bash
just state-save
```

That is the whole of the mechanical half. **Do not hand-edit anything between the markers** — the
block carries a `W0M-STATE-DATA` JSON payload (gate exit codes, the hot list, per-repo
branch/dirty/unpushed, ticket counts) which `just state-check` re-derives and compares at every
push. A hand-edited value there does not become true; it becomes a lie the gate then has to catch.

### Step 1b — rotate the history you just superseded

```bash
just state-rotate
```

**Run this whenever you write a new ⭐ PICK UP HERE block**, because writing one is what makes the
previous one dead. It moves superseded sections into `project/state-archive/` **verbatim** and
refreshes the 🗄️ Archived history index. It is idempotent, so running it when there is nothing to
move is free and it will tell you the candidate set was empty.

**Why this is not optional housekeeping** ([[T174]]): without it, `STATE.md` grew **5 KB → 333 KB in
16 days** and reached **~83k tokens, 93.9% of it dated history**. Every session paid that to orient.
`state-check` now enforces a budget (900 lines / 80 KiB) at pre-push, so skipping rotation does not
quietly degrade the file — **it blocks your push**, and the fix it names is this recipe.

⚠️ **Two things rotation will not do for you:**
- **It only moves what is mechanically dead** — a superseded pickup block announces itself by shape.
  Anything needing a *reading* is a judgement call and needs a row in
  `project/state-archive/DISPOSITION.md` first; `state-check` **fails** on a section with no row
  rather than defaulting it to archived. That rule is not bureaucracy: on its first use it caught a
  section that held the only standing reminder of a live security gap ([[T175]]).
- **It cannot tell you the prose is now wrong.** If your new pickup block contradicts a section that
  is still live, that is Step 2's job.

## Step 2 — read what changed, and reconcile the prose against it

`state-save` deliberately does **not** touch the editorial sections. So the moment it rewrites the
numbers, the prose around them may contradict them. Check the diff:

```bash
git diff STATE.md    # from the estate root
```

Then walk the editorial sections and fix what the new numbers just falsified:

- **⭐ PICK UP HERE** — one paragraph: what was just finished, what is genuinely next, and *why*.
  This is the single highest-value line in the repo. If the ticket you worked is now done, it must
  no longer say "next: that ticket".
- **Standing thread / other open threads** — a thread that closed this session moves out.
- **Gotchas the next agent MUST know** — add anything that cost you time today. A gotcha that was
  paid down (the code now prevents it) gets **deleted**, not left as folklore.
- **Owner actions** — things only the human can do (rotate a credential, click a dashboard).

Ask the user about anything you cannot determine from the diff. Do **not** invent a pickup
paragraph from the ticket title alone — a confident-sounding wrong handoff is worse than a terse
right one.

## Step 3 — verify, then commit

```bash
just state-check
```

Must exit 0. If it fails it prints the exact drift; re-run `just state-save` rather than editing
by hand. This gate is proven able to fail (`just state-doctor-test`, T145 AC9) — a block from it
is a real finding.

**Read the headroom line it prints on success** — e.g.
`ℹ STATE.md 450/900 lines (50%) · 48,213/81,920 bytes (59%)`. That is your writing budget for the
block you just added, stated **before** it bites rather than as a rejected push. At **≥80%** the
line says so and names `just state-rotate`; do not hand the next session a surface with no room to
write its own handoff.

Commit STATE.md **in the same commit as the work it describes**. A handoff that lands a commit
later describes a tree that no longer exists.

> ⚠️ **`--no-verify` is prohibited here and pointless.** The pre-push `state-check` is the gate;
> skipping it leaves the drift in place for the next session to trip over.

## Related

- [[w0m-state-load]] — the other end of this handshake; it re-measures rather than trusting what
  you wrote here.
- [[w0m-sdlc-archive]] — runs this as step 6.
