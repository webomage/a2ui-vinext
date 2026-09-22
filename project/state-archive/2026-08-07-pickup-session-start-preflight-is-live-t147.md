<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### ⭐ (was) PICK UP HERE — 2026-08-07 — **Session-start preflight is LIVE (T147 AC5/AC6/AC7, AC1 half) · both Obsidian v -->

### ⭐ (was) PICK UP HERE — 2026-08-07 — **Session-start preflight is LIVE (T147 AC5/AC6/AC7, AC1 half) · both Obsidian vaults now reachable over MCP with the declaration corrected twice (T144) · `sdlc.json` was missing 2 of 8 repos. The through-line: a thing can be declared, enabled AND listening and still not be CONNECTED.**

> **Written for an agent with none of my context. Measured live 2026-08-07.**
>
> ### 📍 STATE — all repos clean and pushed except `wom7mlx` (10 dirty / no upstream — **another agent's**, not yours)
> 8 commits pushed: **wom7web 6 · wom7api 2 · wom7ext 1**. `just preflight --fast` **1.6s**,
> `just preflight-test` **11/11**, `just mcp-ratchet` **green**, `sdlc-doctor` + `discovery` green.
> ⚠️ **RESTART REQUIRED** before the new wiring exists in a session: the two Obsidian MCP servers
> and the SessionStart preflight hook both load at startup. In *this* session they are configured
> but not connected — which is, fittingly, the exact distinction the session was about.
>
> ### ✅ WHAT LANDED
> 1. **[[T147]] preflight** — `project/scripts/preflight.py`, `just preflight` / `--fast` /
>    `preflight-test`, wired to **SessionStart** in the estate-root `.claude/settings.local.json`.
>    4 checks: **mcp · graph · repos · tools**. **AC5, AC6, AC7 done. AC1 is HALF** — the harness
>    runs it every session; `w0m` / `w0m-sdlc-start` do **not** invoke it, and AC1 names them.
>    Left unticked deliberately: half an AC is not an AC.
> 2. **[[T144]] Obsidian over MCP** — both vaults reachable, 8 tools each, via a **stdio bridge**
>    (`project/scripts/obsidian_mcp_bridge.py`). Declaration was wrong twice; see below.
> 3. **[[T154]]** — `python3.1:8899` (the 1945 project's static preview server) **accepted** by
>    owner decision, with the reason recorded. Ratchet green again.
> 4. **Obsidian vault hygiene** — `node_modules` excluded from the wom7web and wom7ext vaults.
>    37% and 84% of the markdown those vaults surfaced was vendored dependency READMEs.
> 5. **wom7mlx codegraph re-rooted** — it had been indexed at the OUTER `wom7mlx/`, which is not a
>    git repo at all. Re-indexed at `wom7mlx/wom7mlx`, orphan removed.
>
> ### 🔑 THE LESSON, IF YOU READ ONE THING
> **Declared ≠ configured ≠ listening ≠ CONNECTED — four states, and the estate had been treating
> the last two as one.** Both Obsidian servers were declared, enabled *and listening* for twelve
> days while **zero Obsidian tools existed in any session**; they were simply absent from the MCP
> client config. ⇒ Session-connectivity is a **harness fact**. No file read and no port scan can
> answer it, so `preflight` reports declared/configured/listening and **says outright that it cannot
> measure the fourth**. Do not add a check that claims otherwise.
>
> ### 🔴 GOTCHAS THAT COST ME TIME TODAY
> - **The repo enumerator was wrong TWICE, and neither time did reading the code reveal it.**
>   Top-level-only found **7** (`wom7mlx` is nested at `wom7mlx/wom7mlx`); one-level-down found
>   **28** (that directory holds ~20 vendored upstream clones — mlx, candle, mlx-rs …). Both were
>   caught only by **cross-checking against `graph_health`, which says 8**. ⇒ Fixed by *importing*
>   `graph_health.REPOS`, not by adding a third enumerator. **When you need "the list of our repos",
>   import that map.** Owner instruction 2026-08-07: for wom7mlx only **our** code is
>   monitored/graphed/indexed, i.e. the inner path.
> - **Two governed files disagreed about a fact, and the wrong one was the governance file.**
>   `sdlc.json` attributed both Obsidian ports to `obsidian-local-rest-api`; they are
>   **`semantic-vault-mcp` 0.11.42**, which `mcp-exposure-baseline.json` had named correctly since
>   07-31. The attribution had been *inferred from the plugin that was easy to find*. Proved by
>   elimination — both local-rest-api keys get 401 from both ports.
> - **"Unknown" was a search-location bug, not missing data.** Port↔vault was recorded unknown
>   because local-rest-api's config only holds 27123/27124. The port was in the *other* plugin's
>   config the whole time. **3001 = wom7md · 3007 = wom7web.**
> - **`enabledMcpjsonServers` is a SECOND gate on `.mcp.json`** — it was allowlisting `graphify`
>   only, so adding a server to `.mcp.json` alone would have done nothing.
> - **Streamable-HTTP MCP is session-ful and returns `Mcp-Session-Id` LOWER-CASED.**
>   `dict(resp.headers).get("Mcp-Session-Id")` silently misses it; `HTTPMessage.get` is
>   case-insensitive, a `dict()` copy of it is not. Everything after `initialize` 400s.
> - 🔴 **Estate-root config is UNVERSIONED and no gate can see it:** `@wom/.mcp.json` and
>   `@wom/.claude/settings.local.json` are in no git repo. The tracked record is
>   `.w0m/sdlc.json → mcp.servers` / `→ preflight`. Change the real file, and there is no diff.
> - **`just preflight` ≠ `hygiene_preflight.py`.** The latter is T135's one-shot hygiene
>   measurement. Same word, different question; both docstrings now say so.
>
> ### ▶️ NEXT, in order
> 1. ~~**[[T20]] — the one thing still unverified.** Its AC1/AC2 are ticked and claimed shipped in
>    `fc04bc5` (wom7cfworkers, `supabase/functions/_shared/chat-core.ts`), but **nobody has checked
>    them against the code**.~~ ✅ **DONE 2026-08-07 — AC1 + AC2 both VERIFIED, and the line above was
>    wrong about where the code lives.** It is **`wom7api`**, not `wom7cfworkers` (which contains no
>    `chat-core.ts` at all) — the wrong-surface error this file warns about, committed once more *in
>    the instruction to go check*. Evidence: `chat-core.ts:27` classifier · `:105` filter (fetch 16 →
>    drop poisoned → keep 10 newest) · `:239` tag · `:195` prompt §5. AC1 is **broader** than recorded:
>    `_persistChats` is shared by the buffered **and** streaming paths.
>    🔴 **The ticket's own note was FALSE where it mattered most:** *"unit-tested 9 cases"* — there is
>    **no test**. `isNonReplayableAssistant` appears in **exactly one file across all 8 repos**, its
>    own implementation, and `git log -S` shows one commit ever. **A 5-pattern substring blocklist
>    gates a live lead funnel with zero probes.** ⇒ The exposed work (test the 5 patterns, the
>    empty-answer case, and the *negative* case the comment claims to protect — a legitimate security
>    refusal must stay replayable) is recorded on the ticket and deliberately **not** folded into AC1,
>    which is genuinely met as written. That closes the top-10 SDLC AC-truth pass: **every row
>    verified.** ⚠️ [[T173]] AC6 still applies — T20's `priority:` is empty, so it ranks `—`.
> 2. **[[T147]] AC1's other half** — make `w0m` / `w0m-sdlc-start` invoke the preflight.
>    Then **AC3**, the coverage scan, which is the genuinely new part of that ticket.
>    AC2 stays blocked on [[T131]] comparable versions.
> 3. **[[D35]]** — the GDPR erasure workflow hard-throws at step 1 on `linkedin_tokens`, a table
>    [[T99]] dropped on 2026-07-25, so **PII anonymisation in steps 2+ is never reached**. Deployed
>    and bound. The fix is a few lines; it is a compliance path in a live Worker, so it was surfaced
>    rather than done silently — and `deploy*` is denied to the agent ([[T161]] AC3).
>
> ### 🙋 OWNER ACTIONS (only you can do these)
> 1. **`mailpit`** — still `known-open`: bound `0.0.0.0`, UI **and** `/api/v1/messages` answer
>    **200 with no credentials from the LAN**, holding password resets and magic links.
>    Fix: `mailpit --listen 127.0.0.1:8025 --smtp 127.0.0.1:1025`. Recorded is not fixed.
> 2. **Reload both Obsidian vaults** (Cmd+R) so the `node_modules` exclusion takes effect.
> 3. **`wom7web/graphify-out` is registered as a separate Obsidian vault** (4,755 files of graph
>    JSON). Looks accidental — unregister it or say it is deliberate.
> 4. Everything on the previous block's list that is still open — deploy, the T165 fidelity
>    decisions, Scribely, [[T171]] credentials.
>
> ### ✋ DECIDED THIS SESSION — do not re-litigate
> - **`readOnlyMode: false` stays on BOTH Obsidian MCP servers** (owner, 2026-08-07). Write access
>   is the point: the intended use is manual and Obsidian-tool analysis written back to `.md`
>   through MCP. ⚠️ Consequence to hold in mind, not to undo: an MCP `edit` in the **wom7web** vault
>   touches **this code repo** outside the Edit/git path — no diff you read first, and it can leave
>   the tree dirty with nothing announcing it. Prefer the `wom7md` vault for notes; after writing
>   into wom7web, check `git status`.
> - **`:8899` is accepted, not fixed** — public menu content, different project. If that port is
>   ever reused, the acceptance stops applying.
