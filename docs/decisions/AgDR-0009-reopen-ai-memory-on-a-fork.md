---
id: AgDR-0009
title: "Reopen ai-memory on a fork — AgDR-0008's decisive objection was factually wrong"
timestamp: 2026-08-19T00:00:00Z
agent: claude-code
model: claude-opus-5
trigger: user-prompt
status: accepted
superseded_by:
supersedes: AgDR-0008
ticket: T234
---

# AgDR-0009 — Reopen ai-memory on a fork

## Y-statement

> In the context of **an owner fork and a re-read of the upstream architecture**, facing **an earlier
> rejection whose decisive reason turns out to be false**, we decided **to reopen adoption on a
> self-built fork**, to achieve **cross-agent recall that is versioned, pushable and supply-chain
> controlled**, accepting **a daemon, an owned Rust dependency, and concurrency semantics that are
> still undocumented**.

## Context

🔴 **[[AgDR-0008]] rejected ai-memory because *"its store does not travel with the repo"*. That
reason is wrong.** Read directly from `docs/ARCHITECTURE.md`:

> `<data_dir>/wiki/` — markdown **source of truth**. Owned by a `git2` repo so every consolidation
> pass + every session-end produces a durable commit.
> Backups: … **Or: `git push` the wiki dir** + `rsync` the data dir.
> `<data_dir>/db/memory.sqlite` — **derived index**.

⇒ The wiki **is a real git repository that can be pushed and cloned**, and SQLite is *derived* and
rebuildable. It does not clone with `wom7web`, which is what I observed — but I concluded from that
observation that it *does not travel at all*, and that does not follow. **A separate pushable repo is
portable across machines and teammates**, which was the property being sought.

⚠️ **`--data-dir` is also a first-class CLI flag** (`ai-memory --data-dir <path> …`), so the store
location was configurable the whole time. **No fork was ever needed for that.**

📌 **How the error was made:** I read *"git-versioned in its own data dir"*, checked that
`~/.local/share/…` is outside the repo, and stopped. **I verified the location and inferred the
consequence** instead of reading the two lines that state the consequence directly.

**Fork status, measured 2026-08-19:** `casualuser/ai-memory` **does not exist** — searched all
**1,791** owned repos with a `repo`-scoped token; the five most recent pushes do not include it.
This record therefore describes the intent, not an existing artefact.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Keep AgDR-0008's rejection | no work | 🔴 **rests on a false premise** — leaving it would misinform every future reader | rejected |
| Adopt upstream binaries as-is | zero build effort | prebuilt binary + lifecycle hooks on a machine holding prod credentials, with [[fake-interview-malware-2026-06]] in this estate's history | rejected |
| **Adopt from a self-built fork** | **building from source is the answer to the supply-chain objection**; a fork can carry w0m-specific changes; upstream is MIT, 3.2k ★, Rust, pushed today | an owned Rust dependency to maintain; daemon still required; concurrency still undocumented | **PROPOSED** |
| Wait for a repo-local competitor | none identified | indefinite | rejected |

## Decision

**Reopen [[T234]].** The rejection stands down; the remaining costs — a daemon on `:49374`, an owned
Rust fork, and **undocumented locking while a parallel Antigravity agent writes here** — become the
actual decision basis rather than a premise that was never true.

⚠️ **This is `proposed`, not `accepted`.** Nothing is installed. T234's ACs — a pre-registered kill
criterion, one-repo scope, a tested concurrency case, token cost measured both ways, and *deprecate
exactly one thing or nothing* — all still gate the install, and **AC2's classification (34 pointer ·
24 recall · 4 duplicate) is unaffected**: 34 memories duplicate a ticket whether or not a tool is
adopted.

## Consequences

**Positive.** The record now says something true. Building from a controlled fork removes the
supply-chain objection outright — the strongest argument for forking, independent of any feature.
`--data-dir` means the wiki can live in a repo the estate owns and pushes, so the 24 recall memories
could become cross-agent **and** cross-machine.

**Negative, plainly.** This is the **second** AgDR in one day superseded because my own reasoning was
wrong (after AgDR-0001 → 0002), and both times the error was **inferring a consequence instead of
reading the sentence that states it**. A fork is a **dependency the estate then owns**: upstream
moves (pushed today), and a fork that drifts is worse than no fork. The daemon, the hooks and the
undocumented concurrency are unchanged — **none of those was ever the reason for rejection, and none
of them has improved.**

## What this does NOT decide

Not that ai-memory is adopted — [[T234]] still gates that, and every AC stands. Not that a fork gets
created; it does not exist yet. Not what enhancement it would carry: **`--data-dir` already solves
the repo-locality question**, so a fork's justification is supply-chain control first, and any code
change must be argued separately on its own merits.


## 2026-08-19 — the fork exists; reading the SOURCE removes two more of my objections

`casualuser/ai-memory` is live, in sync with upstream (identical `pushed_at`), **7.2 MB / 213 `.rs`
files / 10 crates**. Cloned and read rather than inferred from docs.

⚠️ **Appended, not superseded** — this record is still `proposed`, so refining it before acceptance
is not the same as overturning an accepted decision. Superseding an unaccepted proposal would churn
the chain without preserving anything anyone relied on.

### 🔴 Concurrency: locking EXISTS, and I had implied it did not

Measured in source: **`Mutex` in 30 files · `RwLock` in 2 · `fs2` exclusive file locks in the hook
spool · "advisory" in 5**.

- `crates/ai-memory-cli/src/commands/hook_spool.rs` — `fs2::FileExt`, `acquire_drain_lock`,
  `try_lock_exclusive`, **with tests** (`drain_lock_is_exclusive_and_released_on_drop`, plus Windows
  lock-violation handling). That is the **cross-process** path — exactly the concurrent-agent case.
- `crates/ai-memory-wiki/src/wiki.rs` — `tokio::sync::RwLock`.
- `crates/ai-memory-store` — the single-writer actor is real and asserted in code:
  *"writer actor owns that connection, so the single-writer invariant holds."*

⇒ My objection was that locking was **undocumented**, which is true — the docs do not describe it.
**I then let "undocumented" carry the weight of "absent" in every risk framing since.** T234 AC6
should now test a *known* mechanism rather than probe for a missing one.

📌 **The GitHub code-search API returned 0 hits for `lock`, `Mutex` and `advisory`** on the fresh
fork — uniformly zero across three terms, which is the *too-extreme-to-be-true* signal this session
has hit four times. Cloning gave the real answer. **A search index is not the code.**

### Page limits are a non-issue

Upstream caps a page at **16 KiB**. Of 62 memories: **median 3,190 B**, and **exactly one** exceeds
it (`auth-rbac-audit-2026-07-14`, 25,286 B) — a file that arguably wants splitting regardless.

### ⇒ What is actually left to enhance: almost nothing

| Objection | Status |
|---|---|
| store not portable | ❌ **wrong** — `--data-dir` + pushable `git2` wiki |
| no locking | ❌ **wrong** — exists, with tests |
| page size incompatible | ❌ non-issue — 1 of 62 |
| prebuilt binary / supply chain | ✅ **answered by building from the fork — no code change** |
| **daemon on `:49374`** | ✅ **stands** — architectural; `ai-memory-mcp` is a server crate |

**The fork needs no enhancement to be adoptable.** Its value is **build-from-source**, and the
decision reduces to one honest question: *is cross-agent recall for 24 memories worth running a
daemon and owning a Rust dependency?* That is an owner call, not a technical blocker.


## 2026-10-23 — Accepted & Reconciled (T234 / T178 / AgDR-0032)

This record is promoted from `proposed` to `accepted` to reconcile the internal drift between
`T234.md` (§"Adoption — 2026-08-19: ADOPTED, pinned to v1.29.0"), the live pin in
`wom7web/project/ai-memory-pin.json`, and the estate's settled knowledge architecture:

1. **4-Home Knowledge Split (`T178`, `AC8`) & Worktree Isolation (`AgDR-0032`, `AC6`).**
   `T178` formally ratified the 4-Home Knowledge Split (`CLAUDE.md` / `AGENTS.md`, `MEMORY.md`,
   `.tasks/T##.md`, and `@wom/LESSONS.md`), deprecating duplicate pointer memories in favor of
   canonical git-tracked registers without introducing a ninth unmanaged surface. Separately,
   `AgDR-0032` (`just agent-tree`) eliminated the shared-worktree `git add -A` race (`AC6`) by
   giving every concurrent agent an isolated copy of the estate (`~/.w0m/work/<name>/w0m`).
2. **Pinned Fork & Supply-Chain Gate (`v1.29.0`, `AC3`–`AC5`, `AC7`).**
   The self-built fork checkout at `_ext/ai-memory` remains pinned to `v1.29.0` (commit
   `805fa4b17d575dadcd9cc9064aad42975e59e04e`, freeze tag `w0m-validated-2026-08-19`,
   `auto_update: false`) in `wom7web/project/ai-memory-pin.json`, enforced by
   `wom7web/project/scripts/ai_memory_pin_check.py` (`just ai-memory-check`) and offline red/green
   unit tests in `wom7web/project/scripts/tests/test_ai_memory_pin_check.py`. No background daemon
   or unmanaged global lifecycle hook is enabled on the host.

