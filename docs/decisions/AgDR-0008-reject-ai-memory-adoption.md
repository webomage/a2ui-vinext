---
id: AgDR-0008
title: "Do not adopt ai-memory — its store does not travel with the repo, which was the reason to want it"
timestamp: 2026-08-19T00:00:00Z
agent: claude-code
model: claude-opus-5
trigger: user-prompt
status: superseded
superseded_by: AgDR-0009
supersedes: AgDR-0007
ticket: T234
---

# AgDR-0008 — Do not adopt ai-memory

## Y-statement

> In the context of **auto-memory being the one non-portable state surface**, facing **an evaluation
> that found ai-memory's wiki lives in its own git root outside the project**, we decided **not to
> adopt it**, to achieve **no new daemon, binary or register for a portability gain that does not
> exist**, accepting **that per-session recall stays Claude-only and 24 genuinely-unique memories
> stay unportable**.

## Context

Owner asked to research deeply and **proceed with adding it if evaluated**. The evaluation says no,
and the reason is that **a claim made in [[AgDR-0007]] was wrong**.

🔴 **The correction.** AgDR-0007 recorded ai-memory as *"the only candidate whose store is markdown
in git"* and treated that as the deciding advantage. Reading the docs: the wiki lives at
**`~/.local/share/ai-memory/wiki/<workspace>/<project>/`** — git-versioned in **its own repo**, not
inside `wom7web`. ⇒ **It does not clone with the project.** A teammate, a second machine, or CI gets
nothing, exactly like the 62 auto-memory files it would replace. **The portability it buys is across
AGENTS on one machine — not across machines or people**, which is a materially smaller claim than
the one that motivated the trial.

**T234 AC1, classified by reading all 62 memories:**

| Class | Count | Meaning |
|---|---|---|
| **pointer** | **34 (55%)** | a live ticket already carries the record |
| **recall** | **24 (39%)** | exists nowhere else — the real candidate set |
| **duplicate** | 4 | the rule is already in `CLAUDE.md` / `AGENTS.md` / `LESSONS.md` |

⇒ AC2's stop condition (*recall is a small minority*) **did not fire** — 39% is substantial. The
trial stops for a different reason: **the thing it would buy is not what was claimed.**

**What adoption would additionally cost**, from the docs rather than assumption: a **daemon** (Docker
container or systemd unit on :49374) on a host the audit already found running **five container
runtimes**; a **prebuilt binary** plus **lifecycle hooks** installed into agent runtimes, on a
machine holding production credentials, with [[fake-interview-malware-2026-06]] in this estate's
history; **no documented locking**, while a parallel **Antigravity** agent writes here; and
consolidation that calls an **LLM provider** per session.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Adopt ai-memory** | cross-agent recall on this machine; MCP; markdown pages; `memory_handoff_accept` | store outside the repo, so **no cross-machine portability**; daemon + binary + hooks; undocumented concurrency; LLM cost | **rejected** |
| Adopt Ogham instead | Postgres+pgvector, **already run on Supabase** — no new datastore | memory in a database, not a diff; 113 ★; still not in the repo | rejected |
| Prune the 34 pointers, keep auto-memory | 🔑 **the deprecation is available with NO tool** — over half the corpus duplicates a ticket | leaves the 24 recall files Claude-only | **ACCEPTED as the next step** |
| Do nothing | zero cost | leaves 297 KB where 55% duplicates git-tracked records | rejected |

## Decision

**ai-memory is not adopted.** The available win is the one the measurement found: **34 of 62
memories are pointers to tickets that already hold the record**, and pruning those to one-line hooks
removes duplication **without any tool at all**.

## Consequences

**Positive.** No daemon, no binary, no hooks, no ninth register, no LLM cost per session. The real
duplication — 55% of the corpus — becomes actionable immediately, and the estate keeps state that a
`git clone` reproduces.

**Negative, stated plainly.** **Per-session recall stays Claude-only.** The 24 genuinely-unique
memories — `openspec-cli`, `gh-identity-isolation`, `scheduler-surface-split`, `upwork-graphql-contract`
and the rest — remain invisible to Gemini, opencode, CI, a teammate and a second machine. **This
decision does not fix that; it declines a fix that would not have fixed it either.** ⚠️ If those 24
matter cross-agent, the honest route is to move them into a **git-tracked register in the repo** —
which is work, not a purchase.

## What this does NOT decide

Not that a memory layer is refused forever — a candidate storing **inside the project repo** would
answer the objection that killed this one. Not the fate of the 34 pointers, which is [[T234]]'s
remaining work. Not Ogham, which is rejected here on the same repo-locality grounds rather than on
capability.
