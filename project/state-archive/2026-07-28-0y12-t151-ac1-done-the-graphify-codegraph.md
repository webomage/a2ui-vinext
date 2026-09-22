<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0y12. superseded pickup block — 2026-07-28 — **T151 AC1 DONE (the graphify/codegraph call-site map) and T107 CLOSED  -->

### 0y12. superseded pickup block — 2026-07-28 — **T151 AC1 DONE (the graphify/codegraph call-site map) and T107 CLOSED as not-reproducible. T151's AC6 was resolved by measurement, its AC9 gained a hard dependency on AC8, and a defect the estate had carried as current fact for a week turned out to be already fixed. Next: T151 AC2 (the united multi-repo graph — the owner's stated priority), now unblocked.**

> **Written for an agent with none of my context. Everything below was measured this session.**
>
> ### 📍 STATE — 4 local commits in 3 repos, NOTHING PUSHED YET
> `wom7web e8f703d5 · 25903d99 · d90f0d84` · `wom7api 2b0ef20` · `wom7cfworkers ada20d6`.
> All pre-commit gates green on every one. `wom7web`'s only dirty paths are the owner's untracked
> `.obsidian/` and `.smart-env/`. ⚠️ Pushing fires the detached `sync_github.py` — **check
> `.git/w0m-ticket-sync.log`, do not assume it finished.** `just state-check` and `just discovery`
> are green; `just sdlc-doctor` exits 0 with its two standing advisories (license-check 208, and the
> 6 rowless tickets).
>
> ### ✅ WHAT LANDED
> | Commit | Repo | What |
> |---|---|---|
> | `e8f703d5` | wom7web | sync writebacks (T146 `gh_issue`, ticket index) |
> | `25903d99` | wom7web | **T151 AC1** — call-site enumeration + `project/scripts/graph_callsites.py`; AC6 resolved |
> | `2b0ef20` | wom7api | stale freshness claim in the codegraph-sync hook comment |
> | `ada20d6` | wom7cfworkers | same comment fix |
> | `d90f0d84` | wom7web | **T107 closed** not-reproducible; T151 unblocked; `.husky/pre-push` comment corrected |
>
> ### ✅ T151 AC1 — what actually calls each tool, and the asymmetry that reorders the ticket
> Corpus: **8,378 tracked files + 32 live hook files + 14 out-of-repo surfaces**, 3 deduped as
> symlinks. **87 hits — 31 graphify / 56 codegraph.** Reproduce:
> `python3 project/scripts/graph_callsites.py --corpus`.
> 🔑 **The finding that matters: codegraph is a LIVE MCP server registered in `~/.claude.json`,
> reaching every session in every directory. graphify has NO MCP registration at all.** So AC9's
> "succession" is not a doc edit — editing `~/.claude/CLAUDE.md` would delete the instruction while
> leaving codegraph's real reach intact and giving graphify none. **AC8 (a graphify MCP surface) is
> now a hard prerequisite of AC9**, and AC8 sits behind [[T144]]/[[T21]].
>
> ### 🔴 FOUR CORRECTIONS AC1 MADE — three change what the ticket must do
> 1. 🔴 **The "three justfiles" are ONE file.** `wom7web/justfile` and `wom7cfworkers/justfile` are
>    **symlinks to `wom7api/justfile`**. `git ls-files` lists all three and reading them follows the
>    link. **My own audit script committed this estate's signature error while hunting it** — the
>    first pass reported 3 call sites where there is 1. It now dedupes by **resolved** path and
>    prints `justfile -> wom7api/justfile`. ⇒ **Dedupe by resolved path, never by tracked path.**
> 2. 🔴 **AC1's own wording carried the blind spot it warns about.** It says check
>    `.w0m/sdlc.json → mcp` — but that file is a **declaration**; the registration is
>    `~/.claude.json`. The config admits it: *"Live availability is a harness fact, not a file fact."*
> 3. 🔴 **`.w0m/sdlc.json` recorded codegraph as indexed in 3 repos; measured, 6** (+skills, ext,
>    sec). Corrected in place, with the date and the two repos that genuinely lack it.
> 4. 🔴 **`just ask` already treats graphify as secondary, and silently** — `justfile:1135` falls
>    through to `graphify query … 2>/dev/null || true`. Until today that served a **274-commit-stale**
>    graph with every error suppressed. Still worth fixing the error suppression.
>
> ### ✅ AC6 — resolved by MEASUREMENT, not by a decision. The premise was false
> `graphify-out/` is **already gitignored** (`.gitignore:104`). An untracked file cannot conflict, so
> "a guaranteed conflict source given the parallel Antigravity agent" was wrong and the union
> **merge driver is unnecessary — do not install it.** ⇒ **Read the tree's existing answer before
> asking the question.**
>
> ### 🔴 T107 WAS ALREADY FIXED — and this is the lesson worth carrying
> The recorded defect — *"`graphify update .` is a ~40s no-op at the repo root that prints success"* —
> **does not reproduce on graphify 0.9.15.** Measured: `graph.json` 24.0MB → 54.9MB, mtime
> 2026-07-21 → 2026-07-28, nodes **27,467 → 48,727**, and **`built_at_commit` advanced `fe8b072` →
> `25903d99`, exactly the HEAD recorded before the run.** That last figure is the evidence; the
> "Code graph updated" message printed in the broken case too.
> - **Closed as *not reproducible*, not as *fixed*** — the version in use on 2026-07-21 was never
>   recorded, so "an upgrade fixed it" is likely but unproven. Don't upgrade that to a claim.
> - 🔴 **The defect was carried as current fact by the ticket, by STATE.md, and by TWO pre-commit
>   configs for a week after it stopped being true.** Had AC3 been built on the record, it would
>   have been designed around a constraint that no longer existed. ⇒ **A recorded DEFECT is a claim
>   with a date, exactly like a recorded MEASUREMENT. Re-run it before building around it.** This is
>   the same rule this file already states for measurements — now proven for bugs too.
> - ⚠️ **The ~40s figure is dead: the rebuild is now ~4 MINUTES** on the bigger graph. Full graphify
>   still must not go on pre-push — freshness belongs on **post-commit/async** (T151 AC3).
> - ⚠️ Two non-blocking warnings appeared and belong in AC4's health report rather than scrolling
>   past: **130 files produced zero nodes** (upstream #1666) and **1 stale node kept fail-closed**.
>
> ### ✅ SECOND HALF OF THE SESSION — AC2, AC3 AND AC4 ARE ALSO DONE. **5 of T151's 9 ACs.**
> **The united graph exists: 7 of 8 repos, 54,903 nodes / 96,702 links** at
> `~/.graphify/global-graph.json`. Eviction proven (removing `wom7sec` pruned exactly 5 nodes and
> left every other count byte-identical). **`just graph-global`** refreshes it; **`just graph-health`**
> reports coverage/staleness/hooks/union-sync and **names all 8 repos it enumerated**; both are
> declared `manual` in `stacks-policy.json` with reasons. Freshness hooks are installed in the 7
> union repos and **proven to fire** — a commit moved `built_at_commit` to exactly the new HEAD.
> Current: **7/8 graphs · 7/8 in union · 0 commits stale · hooks `both` on all 7 · `--strict` exit 0.**
>
> ### 🔴 THE FINDING TO CARRY: THE TWO TOOLS WERE BREAKING EACH OTHER
> `graphify extract` found **0 code files and exited 1** in every repo except wom7web. Cause:
> **`.codegraph/.gitignore` contains `*`** — correct for git, which scopes patterns to the file's own
> directory — while **graphify applies nested `.gitignore` patterns tree-wide**, so that one `*`
> excluded every file in the repo. **codegraph was silently blinding graphify.** And
> `wom7web/.graphifyignore` has always listed `.codegraph/`: **being the only repo with that file
> and the only repo where graphify worked were the same fact**, unconnected until now. Fixed by
> giving the other 7 repos a `.graphifyignore`. ⇒ **This is a first-class input to AC9, not a
> footnote** — and it is why graphify was never rolled out.
>
> ### 🔴 THREE DEFECTS IN MY OWN TOOLING — all this estate's signature shape
> 1. **A false green inside the tool built to detect false greens.** Hook state was parsed as
>    `"installed" in line`; graphify prints **`post-commit: not installed`**, which *contains*
>    `installed`. It reported **`hooks: both` for all 8 repos when none had a hook.** ⇒ **A substring
>    test whose negative case contains its positive case is a false green.** 8 cases now pinned in
>    `project/scripts/tests/test_graph_health.py`.
> 2. **Union staleness compared NODE COUNTS, which cannot work** — `global add` deduplicates, so
>    wom7api's 1,665-node graph merged as 1,657 and that gap read as `STALE`. ⇒ **Never infer
>    freshness from a count that crosses a dedup boundary.** Now compares the merge commit via
>    `~/.graphify/w0m-union-manifest.json`.
> 3. 🔴 **`graphify extract` does NOT stamp `built_at_commit` — only `update` does.** So the signal
>    AC3 depends on was absent in 6 of 7 repos. Manifest records the repo HEAD at merge time as a
>    **labelled** fallback, and unmeasurable staleness prints `—`, **never `0`** (which reads as fresh).
>
> ### ⚠️ FACTS THAT CORRECT EARLIER RECORDS IN THIS FILE
> - **The ~4-minute rebuild is the COLD FULL `graphify update .`.** The post-commit hook path is
>   **incremental, ~30–40s**. Two operations, two budgets — don't carry one number to the other.
> - **`wom7mlx` DOES have an upstream on `beta`** (pushed `ab86b8d..b9877ce`). This file's repeated
>   "no upstream, `git log @{u}..` lies here" warning is **stale**.
> - **`just discovery-test` is 26/28, not the recorded 28/28.** The 2 failures
>   (`clean --enforce still REPORTS the real raw-invocation`, `enforce_raw=true … BLOCKS`) are
>   **pre-existing** — proven by stashing every change of mine and re-running. Not investigated.
> - **`sync_github.py --dry` is SILENTLY IGNORED** — the log still prints `dry=False`. Nothing
>   mutated because there was nothing to sync, but anyone trusting it for a dry run gets real writes.
> - **Only wom7web's graphify hook is tracked/shared** (`.husky/post-commit`). The other 6 live in
>   `.git/hooks/` — **local to this machine.** "Freshness is mechanical" is machine-local for 6 of 7.
>
> ### ✅ AC5 AND AC7 ALSO DECIDED — **7 of T151's 9 ACs. Only AC8/AC9 remain.**
> 🔴 **The global Claude install was ALREADY DONE on 2026-07-16** — `~/.claude/skills/graphify/` +
> a registration in `~/.claude/CLAUDE.md`. That is why AC1 found graphify's biggest agent surface
> outside every repo. **AC5's installers were run in a SCRATCH DIR and read, then deliberately NOT
> applied** (`~/.claude/CLAUDE.md` verified byte-identical after). `graphify claude install` would
> (a) append a section telling agents to call `graphify` **directly**, violating T130's
> all-tools-via-`just` rule, (b) instruct `graphify update .` after edits — which AC3's hook already
> does incrementally, ~30–40s vs ~4 min by hand, and (c) register **PreToolUse hooks on every
> Bash/Read/Glob**, the strongest possible agent-instruction change, which **AC9 says must come LAST**.
> ⇒ Instead, `CLAUDE.md`'s existing knowledge-graph row was extended by hand to name both graphs and
> point at `just graph-global` / `just graph-health`. **The PreToolUse hooks are deferred to AC9**,
> where they are the natural succession mechanism. **`opencode install` deferred to [[T152]]**
> (OpenCode is P2 by owner decision; and `.opencode/` plugins are [[T127]]-governed — declare them).
> **AC7: `watch` NOT adopted** — the post-commit hook covers freshness at a better granularity, and
> `watch` is a long-running detached process that would also graph half-written code on every save.
>
> ### ✅ AC8 DONE — **graphify is LIVE over MCP. 8 of 9 ACs. Only AC9 (the succession) is left.**
> Owner-directed 2026-07-28, ahead of the [[T144]]/[[T21]] sequencing AC8 originally assumed.
> Config **`@wom/.mcp.json`** → `graphify-mcp` (absolute path) serving
> **`~/.graphify/global-graph.json`**, declared in tracked `.w0m/sdlc.json → mcp.servers.graphify`,
> install line pinned in `project/tools-policy.json`. Verified with the exact command the client
> runs: **10 tools**, `graph_stats` = **54,921 nodes / 96,665 edges** (the union, not one repo),
> `query_graph "auth"` = 67 nodes with `file:line`. ⚠️ **Needs a session restart** to appear.
> **`stdio`, never HTTP** — the server offers `127.0.0.1:8080` and [[T154]] is an open P0 about
> unauthenticated MCP listeners on this machine.
>
> 🔴 **The popular setup snippet is WRONG in four ways; taken at face value it yields a server that
> never starts, silently:** `python -m graphify.serve` cannot import graphify (isolated **uv tool** —
> use the `graphify-mcp` launcher); the package is **`graphifyy`**, not `graphify`; the `[mcp]` extra
> is required *and* **`mcp<2` must be pinned** (0.9.15 imports `AnyUrl` from `mcp.types`, dropped in
> mcp 2.x); and **`graphify claude install` does NOT register MCP** — it writes a CLAUDE.md section
> and PreToolUse hooks (measured under AC5).
> 🔴 **A regression I caused and caught: `uv tool install "graphifyy[mcp]"` REPLACES the extras set**
> and silently dropped **`tree-sitter-sql`**, losing SQL parsing for `wom7api/supabase/migrations`.
> Restored with `[mcp,sql]`. ⇒ **Adding a uv-tool extra is a replace, not an append.** The exact
> install line is now in `tools-policy.json`, with the warning that `uv tool upgrade` can move off
> 0.9.15 and re-break the MCP import.
> 🟡 **Honest gap:** `@wom/.mcp.json` is at the estate root, which is **not a git repo** — the runtime
> config is **unversioned**. The `sdlc.json` declaration is the mitigation (same pattern that file
> already uses for codegraph). **A fresh clone gets the declaration, not the config.**
>
> ### 🗣️ AC9 IS THE ONLY THING LEFT, AND IT IS AN OWNER DECISION — do not take it unilaterally
> graphify now has **parity**: 7 repos + a union codegraph structurally cannot offer (6 separate
> per-repo indexes), fresh via post-commit hooks, and an MCP surface with 10 tools. AC9's
> precondition is therefore **met** — but AC9 means editing the **global `~/.claude/CLAUDE.md`**,
> which governs **every project on this machine, not just w0m**, and deciding codegraph's fate
> (retire vs a stated division of labour). **That is the owner's call.** The mechanism is already
> identified and waiting: the **PreToolUse hooks AC5 deliberately withheld**.
>
> ### ▶ START HERE
> 1. `git pull` everywhere (a parallel Antigravity agent also commits to `beta`).
> 2. **Re-run, don't re-read:** `just graph-health --strict` (exit 0) · `just discovery` (8 stacks) ·
>    `python3 project/scripts/graph_callsites.py --corpus` (87 hits) ·
>    `python3 project/scripts/tests/test_graph_health.py` (8/8) · `just state-check`.
> 3. **Then pick one:**
>    - **[[T151]] AC8 → AC9 — all that is left of this ticket.** AC8 is the graphify **MCP surface**
>      (a `graphify-mcp` binary is already installed); AC1 proved it is a **hard prerequisite** for
>      the succession, because codegraph's reach is a live MCP registration and graphify has none.
>      ⚠️ AC8 is sequenced behind [[T144]]/[[T21]], so **T151 cannot finish until those move** —
>      that is the honest blocker, not a missing decision.
>    - **AC9's mechanism is already identified:** the PreToolUse hooks AC5 deliberately withheld.
>    - **[[T135]] §5 license** (208 findings, last hygiene strand, lets T135 archive) ·
>      **[[T154]]** AC1b/AC3–AC8 (P0 security; the live exposure is closed, the rest is inventory).
>
> ### 🔴 OWNER ACTIONS — still FOUR, none actionable from here
> 1. **Delete `wom7api/dev_secrets.json`** (83 plaintext secret values on disk, untracked, nothing
>    reads it — so an agent must not delete it for you).
> 2. **Revoke the `casualuser` GitHub token** (id `1243074`) — dropping the DB row did not revoke it.
> 3. **T99(d) 3.1 — provision `CONNECTOR_TOKEN_KEY_V1`** (`openssl rand -base64 32` → Infisical, v1).
>    **Do not let an agent invent key material.**
> 4. **T99(d) 3.5 — apply migration `20260725180000`** (pointless before 3).
> **Plus:** place the **6 rowless tickets** (T2, T25, T32, T35, T48, T66) · T136/T137's three open
> questions · **T120** (`SAFE_BROWSING_API_KEY` is absent, which is why it can't be checked here).
