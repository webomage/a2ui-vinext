---
name: w0m-state-load
description: >
  Pick up a w0m session. Reads the estate-root STATE.md for INTENT, then RE-RUNS every measurement it
  records instead of trusting them, and reports where the file and reality disagree. Trigger at
  the start of any session on the w0m estate, or on "where were we", "pick up", "load state".
metadata:
  author: w0m
  namespace: w0m
  version: "2026.09.24-1790282807"
---

# w0m-state-load — the pickup gate

`STATE.md` opens with its own first instruction: **"Prefer re-running a measurement to reading
one."** That line is there because the recorded numbers in it have been wrong **at least five
times** — a ticket marked started that was actually finished, a gate recorded green that was red,
a count taken before a backfill. Every one of those was believed by the next session because it
was written down.

So the rule of this skill is blunt:

> **Read STATE.md for INTENT. Re-derive every FACT.**
>
> The prose tells you what someone *meant* to do next. The numbers are a snapshot with a
> timestamp on it and no guarantee. Where they disagree, **reality wins and the file is wrong** —
> say so out loud rather than quietly reconciling.

## Step 1 — read for intent only

Run **`just state-brief`** from the estate root. It reads live in-flight ticket notes from `.tasks/T*.md`
and prints the synthesized **⭐ PICK UP HERE** block (0.2s):
- **in-flight tickets**: every `in-progress` ticket and its newest status note — the single source of
  truth for where each session stopped ([[T428]]).
- **completed today**: tickets closed today.

Then read the root `STATE.md` (it moved out of `wom7web/` under [[T421]]) only for standing editorial context:
- **Gotchas the next agent MUST know** — the expensive lessons
- **Owner actions** — what is waiting on the human

Do not look for handwritten narrative session paragraphs in `STATE.md` — they live in ticket Status notes.
Do not yet accept a single number, count, gate result, or branch state from the file.

### Read the file. Do NOT read the archive.

`STATE.md` is **bounded** as of 2026-08-07 ([[T174]]) — ~450 lines, budgeted at 900 lines / 80 KiB
and gated at pre-push. Before that it was **4,141 lines / ~83k tokens**, of which **93.9% was dated
history**, and this skill's instruction to *"read `wom7web/STATE.md`"* was therefore an instruction
to spend 83k tokens before doing any work. It no longer is. Keep it that way:

- **Superseded history lives in `project/state-archive/`** (estate root), indexed by the generated
  **🗄️ Archived history** table at the bottom of `STATE.md`. **Do not read those files as part of
  orientation** — there are 56 of them and they total ~300 KB. The index exists so you can see that
  history *exists*, not so you can load it.
- **Open exactly one archive, on purpose**, when you need to know *why* a past decision was taken —
  and say which one and why. An entry in that index is **dated history by definition**: it was
  current once and is not now, so it can never tell you what to do next.
- **`§0t`-style references still resolve.** Ten files cite `STATE.md` sections by id (`§0t`, `§0z`,
  `§1b`, …). Section ids survive in the archive filenames and in
  `project/state-archive/DISPOSITION.md`, which maps every id to its file and records why it moved.
  Look there rather than concluding a reference is dangling.

## Step 2 — re-run the measurements

Each of these re-derives something the file *also* claims. Run them; do not read the answer off
the page.

```bash
just state-check
```

The one command that does the whole comparison: it re-derives the managed block and exits 1 on
material drift, naming what moved. **Exit 0 means the recorded facts were true as of now.**

If it fails — that is not an error to route around, it is the finding. It means the file's numbers
are stale, and everything you were about to believe from it is suspect. Note what drifted, then
continue with the re-measured values, not the written ones.

```bash
just tasks          # the live queue — HOT + SDLC ranking, with links
```

The hot list in the payload is a snapshot; this is current. If a ticket the pickup paragraph calls
"next" is no longer near the top, the paragraph is stale — surface that to the user rather than
starting on it because the file said so.

```bash
just test                     # what is actually green right now (from the estate root)
git status --short && git -C wom7web status --short && git -C wom7api status --short
```

Uncommitted work in a repo means a previous session ended mid-flight. Read that diff **before**
starting anything new — it is the most common way two sessions collide.

## Step 3 — report the delta, then propose

Tell the user, in this order:

1. **What the file says is next** (intent — quoted from the pickup block).
2. **Where the file and reality disagree**, if anywhere — each drift named with both values.
   Say nothing here if `state-check` was green; do not manufacture reassurance.
3. **What you propose to do**, given the re-measured state rather than the recorded one.

If a drift is material, offer to run [[w0m-state-save]] to correct the file **before** starting
work — otherwise the next session inherits the same stale snapshot you just had to work around.

## Why this is not just "read the file"

A handoff file is a cache. Caches go stale silently and are trusted precisely because they are
convenient. The only thing that makes this one safe is that its facts are **re-derivable in one
command** — so re-deriving them is not diligence, it is the cheapest available option, and
skipping it buys nothing.

## Related

- [[w0m-state-save]] — the writing end of the handshake.
