<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### ⭐ (was) PICK UP HERE — 2026-08-22 — **The public chat was DOWN and is up. The command that fixes the database was in -->

### ⭐ (was) PICK UP HERE — 2026-08-22 — **The public chat was DOWN and is up. The command that fixes the database was inert and reported success. Three tickets closed 6/6, 7/7, 6/6.**

**Closed this session: [[T246]] 6/6, [[T247]] 7/7, [[T248]] 6/6, [[T243]].**
**Filed: [[T249]] (#252), [[T250]] (#253), [[T245]].** All pushed — `wom7web cf1cba26`,
`wom7api 1b945a8`, both clean.

🔴 **The two findings that matter more than the tickets.**

**① `just db-migrate` was a silent no-op for two days and printed *"Remote database is up to
date."*** ([[T248]]) It was **CONFIRMED six times** before anyone doubted it. Cause:
`[db.migrations] enabled = false`, added for a real local reason ([[T238]] AC2 — do not replay the
226 unreplayable migrations on `supabase start`), but Supabase's config has **no local/remote
split**, so it disabled `db push` against the **hosted** project too.
⇒ **The rule this bought, and it generalises: a mutating recipe that reports success must PROVE the
mutation happened.** `db-migrate` now reads the ledger before *and* after and exits non-zero when a
migration that was pending still is. **`deploy-*`, `sync-secrets` and `state-save` were NOT audited
against this rule** — that is the obvious next sweep.
⚠️ `[db.migrations] enabled` is now **per-invocation**: `env(W0M_DB_MIGRATIONS)`, justfile default
`true`, and **`db-local-up` is the only place that sets `false`**. Measured: `env()` has **no
default syntax**, so an **unset** variable is a hard `ProjectConfigParseError` on *every* supabase
command. That is deliberate — loud beats silent — but **a bare `supabase …` outside `just` now
fails until you set it.**

**② A gate found a second broken table nobody knew about.** ([[T249]]) The public chat has **no
conversation memory**: `chat-core.ts:109-114` reads its replay window with an **anon-role** client,
and anon reads **0 of ≥200** rows in `chats`. Nothing looks wrong — an empty history is
indistinguishable from *"this is the first turn"*, and the `error` is discarded. It was found by
[[T246]] AC5's role-aware reader census on its **first live run**, in a system nobody thought was
broken.

✅ **The outage, and what closing it actually cost.**

[[T246]] was filed as a one-line RLS fix. The public consultant was returning *"having trouble
connecting"* because a [[T198]] AC4 migration closed `ai_personas` to anon while an anon-role
reader still needed it. Closing it produced: a definer RPC (`wom_public_persona`, allowlisted to
`agent-consultant`), a probe that asserts an **answer** rather than a status — both pre-existing
anon scenarios asserted *rejections* — a sibling audit finding **8 of 9 closed catalogues were
never at risk** (which retired the ticket's own AC5 rule), the role-aware gate above, and finding
①. 🧪 Exit condition was a **live anon `POST` returning `ok: true` with a 1,937-char answer**, not a
green build.

🔑 **Gotchas that BIT this session — read these before touching the same surfaces.**

- **The deny-list is a GLOB and it shadowed its own probe.** `db-migrate*` refused
  `just db-migrate-test`; the suite had to be renamed **`migration-guard-test`**. A safety rule that
  also blocks the test of the thing it guards is how a gate goes unrun.
- **`git log --grep "\b"` is silently ignored** (POSIX regcomp) and returned a confident **0
  commits** for T39's history. Re-measured with `[^0-9]`: **56**. A zero from a malformed pattern
  looks exactly like a zero from an empty history.
- **zsh does not word-split unquoted parameters.** `supabase $cmd` with `cmd="functions list"`
  arrives as **one argument** — three probe results read as errors that were my own quoting.
- **`line.rpartition("|")` does NOT remove a table's last cell** — the line ends in `|`, so the old
  cell stays in `head` and the new one is appended. It silently gave three TASKS rows **three status
  columns**. Split on `|` and index, or rebuild the row.
- **`TASKS.md` tables do not share a column count** (NOW has 6, others fewer), so *"the last cell"*
  or *"cell −2"* reads the **Ref** column instead — that produced **4 false positives** in the audit
  that became [[T250]].
- **A probe that cannot reach its own code path reports on nothing.** `migration-guard-test` v1 used
  an empty migrations dir, so `db push` refused with the *orphan* error instead of the **skip** it
  was measuring. Caught only because a different assertion failed for the wrong reason.

▶️ **Next action.**

**[[T249]]** — P1, and its AC6 blocker is now gone ([[T248]] is closed, so a migration-based fix can
land). Start with **AC2's product decision**, because the fix shape depends on it: a definer RPC
scoped by `session_id`, a scoped SELECT policy, reading history with the service client, or **no
server-side memory for anonymous visitors**. ⚠️ Its status note names something to establish first:
whether the **writes** land at all — `_persistChats` uses the same anon client and its result is
unchecked, so *"reads are broken"* and *"reads and writes are both broken"* need different fixes.

Also open and cheap: **[[T250]]** (the TASKS row and the ticket file disagree about status on 8
tickets; **T74's row says ✅ over a ticket still `queued`**) and **[[T2]] sitting at 6/6 while its
`status:` still reads `in-progress`** — a finished ticket squatting rank 1 of the hot board.
