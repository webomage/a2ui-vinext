---
id: AgDR-0007
title: "Do not adopt an agent-memory framework; fix the bound, and scope Memorix to the recall layer only"
timestamp: 2026-08-19T00:00:00Z
agent: claude-code
model: claude-opus-5
trigger: user-prompt
status: superseded
superseded_by: AgDR-0008
supersedes:
ticket: T232
---

# AgDR-0007 — Cross-agent state: fix the bound, do not adopt a framework

## Y-statement

> In the context of **an estate whose durable state is already git-tracked, gated and probed**,
> facing **one non-portable surface and a state file that had grown to 94% of its cap with rotation
> unable to fire**, we decided **to fix the bound and NOT adopt an agent-memory framework**, to
> achieve **cross-agent state that stays versioned and reviewable**, accepting **that per-session
> recall remains Claude-only until the recall layer is replaced deliberately**.

## Context

Measured 2026-08-19:

| Surface | Portable? |
|---|---|
| `STATE.md` (676 ln / 76,961 B) | ✅ git-tracked, **bounded** |
| `LESSONS.md` (21 rules) | ✅ |
| `docs/DECISIONS.md` (160 / 6 AgDR) | ✅ generated |
| `TECH-DEBT.md` (52 rows) · tickets (229) | ✅ schema-gated |
| graphify / codegraph | ✅ MCP |
| **auto-memory (63 files)** | 🔴 **Claude-only, unversioned, per-machine** |

⇒ **Six of seven are already portable.** The estate has *more* durable state than these frameworks
provide, with bounds and red probes they do not offer.

🔴 **And the live pain was not storage.** `STATE.md` sat at **94% of an enforced cap** while
`state-rotate` reported an empty candidate set — its patterns expected a `### ⭐ (was) PICK UP HERE`
heading that something used to write (17 archived files carry it; the file carried **zero**), while
`never_rotate` shielded `^## ⭐ PICK UP HERE` and so protected the superseded blocks too. **Four
pickup blocks, two both claiming "(LATEST)".** No framework would have touched that.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Mem0** | 48k stars; +26% accuracy vs native memory on LOCOMO | external service; personalization-shaped; unversioned | rejected |
| **Zep** | best temporal reasoning — **63.8% vs Mem0's 49.0%** on LongMemEval | hosted; a temporal graph is not this estate's gap | rejected |
| **Letta** (MemGPT) | context-as-RAM / archival-as-disk, self-managing | it is a **runtime**, not a layer — would own the agent loop | rejected |
| **Memorix / Ogham / ai-memory** | MCP, cross-agent, name Antigravity + Gemini + opencode explicitly | ⚠️ **SQLite, NOT git-tracked**; multi-agent coordination *"actively developed"*; conflict semantics for simultaneous edits **undescribed** | **deferred to the recall layer only** |
| **Fix the bound; keep the surfaces** | addresses the actual blocker; keeps everything reviewable | leaves auto-memory Claude-only | **ACCEPTED** |

## Decision

**Fixed the bound.** Rotation now identifies a superseded pickup block **by the date in its
heading** — the newest is current, every older one is dead by definition, because writing a new one
is what supersedes it. Mechanical, needing no human rename step. **3 sections archived, 24,864 B
out, 94% → 64% of the cap**, idempotent on a second run.

**No framework is adopted.** If one ever is, it is scoped to **replacing auto-memory** — the single
non-portable surface — and never to duplicating a register that is already versioned.

## Consequences

**Positive.** The cap is enforceable again rather than nominally enforced. Every durable surface
stays in git, reviewable in a diff, and readable by any agent that can read the repo — which is what
[[T232]] needs and what a SQLite store beside it would not give.

**Negative, plainly.** **Per-session recall stays Claude-only.** Gemini, opencode, CI, a teammate
and a second machine cannot read those 63 files, so the fastest layer is also the least portable —
and this decision does nothing about that today. ⚠️ It also leaves the estate carrying **eight
registers** whose coordination is convention rather than mechanism.

## What this does NOT decide

Not that Memorix is rejected — it is **deferred**, and the recall layer is exactly where it would
fit. ⚠️ Adopting it would mean a third-party binary holding session state with **undescribed
conflict semantics**, and a parallel Antigravity agent already writes into this estate — which is
precisely the case where that would bite. That is an owner decision, and it is why this record is
`proposed`, not `accepted`.


## 2026-08-19 — evaluated against MCP · `.md`/`.mmd` · extensibility

Owner asked the three axes that actually decide this. Measured from the repositories, not the
marketing.

| | MCP | Storage | `.md` native | `.mmd` | Extensible | License / lang | Maturity |
|---|---|---|---|---|---|---|---|
| **ai-memory** | ✅ 6 tools incl. **`memory_handoff_accept`** | markdown on disk, **git-versioned** — `wiki/<workspace>/<project>/*.md` + YAML frontmatter; SQLite FTS5 index | ✅ **yes** | ❌ | ✅ companion crates, HTTP/MCP, `.ai-memory.toml` routing | MIT · **Rust** | **3.2k ★ · 1,300+ commits** · prebuilt binaries |
| **Ogham** | ✅ ~25 tools, incl. a **wiki layer** (`compile_wiki`, `lint_wiki`) | **Postgres + pgvector** (Supabase or self-hosted) | ❌ rows; **exports** to markdown/OKF | ❌ | ✅ pluggable embeddings (OpenAI/Mistral/Voyage/Gemini/Ollama/ONNX) + DB backends | MIT · Python 3.13 | 113 ★ · 236 commits |
| **Memorix** | ✅ profiles: micro/lite/team/full | **SQLite**, local-first; Orama index | ❌ | ❌ | ✅ 14+ agent integrations, hooks, skills | Apache-2.0 · TS | 664 ★ · 740 commits |
| Mem0 / Zep / Letta | ✅/service | vector + graph, hosted or SDK | ❌ | ❌ | ✅ SDKs | mixed | largest |

### 🔴 `.mmd` — nothing supports it, and that is the right answer

**No memory layer stores or serves mermaid.** Mermaid MCP servers exist — rendering and *validation*
servers — but they are a **separate concern** from memory, and correctly so.

⇒ **This estate already has that concern solved**: **163 `.mmd` files in git**, `just mmd-validate`
gated at pre-commit, and `just mmd-validate-test` proving the validator can fail. A memory layer
holding diagrams would be a *second* home for something already versioned and gated. **Not a gap.**

### What the axes actually change

**ai-memory is the only candidate whose store is markdown-in-git** — the same property that makes
this estate's six portable surfaces work, and it is 3.2k ★ against Ogham's 113. It also names
**Antigravity, opencode, Gemini CLI and Claude Code** explicitly, and `memory_handoff_accept` is
literally the handoff-between-vendors problem [[T232]] exists for.

⚠️ **Ogham's fit is different and worth noting**: it stores in **Postgres + pgvector**, which this
estate **already runs on Supabase** — so it would add no new datastore, at the cost of memory living
in a database rather than a diff.

### ⚠️ What this evaluation does NOT change

**The decision stands: none of them is adopted yet, and the reason is unchanged.** They were never
rejected on capability — they were deferred because **six of seven surfaces are already portable and
the live blocker was a broken bound**, which has since been fixed (94% → 64%).

🔴 **And a markdown-native store is not automatically a fit here.** `STATE.md` (451), `LESSONS.md`
(291), `TECH-DEBT.md` (103), `DECISIONS.md` (199), **229 tickets and 7 AgDRs** are already markdown
in git with **bounds, schema gates and red probes**. ai-memory's wiki would be a **ninth register**
unless it strictly replaces **auto-memory** — the one non-portable surface — which remains the scope
this record allows and nothing wider.
