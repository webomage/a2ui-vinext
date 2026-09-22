<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### ⭐ (was) PICK UP HERE — 2026-08-06 — **ast-grep now has a job and found 4 unpinned Deno specifiers nothing was enforc -->

### ⭐ (was) PICK UP HERE — 2026-08-06 — **ast-grep now has a job and found 4 unpinned Deno specifiers nothing was enforcing; serena had TWO boot failures, both caused by the T166 pin, both invisible to the checks that "verified" it. 8 commits local across wom7web + wom7api.**

> **Written for an agent with none of my context. Measured live 2026-08-06.**
>
> ### 📍 STATE — clean trees, **8 commits UNPUSHED** (wom7web 5, wom7api 3), all from this session
>
> ### ⚠️ SERENA NEEDS ONE MORE APP RESTART
> Its config was fixed twice today; a running stdio server holds config in memory, so the second fix
> is not live yet. **Verify with a real tool call before trusting it** — `serena --version` and even
> a successful MCP handshake both pass while the tools are dead (see below).
>
> ### ✅ WHAT LANDED
> 1. **T164 — ast-grep given a real job.** `just sg-scan` (gates on exit code) · `just sg-test`
>    (proves rules fire; **a rule with no test case FAILS**) · `just tools-usage` (the evidence probe
>    for policy membership). `tools-policy.json` 18 → **21** (`jq`, `uv` required; `ast-grep` optional
>    with a note saying its usage is zero). ast-grep moved pip/pyenv → brew.
> 2. **4 unpinned Deno `npm:` specifiers pinned** — the class that caused the 2026-07-10 chat outage.
>    `zod`, `opik`, `nodemailer`, `@google/stitch-sdk`. **Nothing enforced this rule before today.**
> 3. **Dead `_shared/linkedin_types.ts` deleted**, confirmed by serena's `find_referencing_symbols`
>    (all refs internal), not by grep alone.
>
> ### 🔴 THE FINDINGS — three "verifications" that each sat one layer from the defect
> | Claim | Why it was false |
> |---|---|
> | T166 AC1b: *"pin verified working"* | the check was `serena --version`, which **never loads a project config**. 1.6.2.dev0 had renamed `languages:` → `language_servers:`; pinned 1.6.1 died at `initialize` with `KeyError`. A restart would NOT have fixed it. |
> | *"four zero-file language servers = startup cost"* (my own note, 2026-08-05) | not cost — an **outage**. `go`/`java` failed to start and serena's failure is **all-or-nothing**: every tool errored, including diagnostics on TypeScript. |
> | my ast-grep rule scanning clean | it matched **double quotes only** → caught **1 of 4** violations and rendered that as green. Second miss: `inside: import_statement` cannot see `deno.json` import maps. |
> ⇒ **Check what a gate did NOT flag.** All three were found by looking at the negative space, not by
> the passing check.
>
> ### ⚠️ TWO HAZARDS WORTH CARRYING
> 1. **The pre-commit `deno-check` hook regenerates `deno.lock` from STAGED FILES ONLY** — it pruned
>    **554 lines / 98 packages** and produced a lock missing the specifier being pinned. Use
>    `just deno-check` (all entry points) and diff before committing a lock the hook rewrote.
> 2. **Both serena boot failures live in gitignored per-machine config**, so neither fix travels to
>    another machine. Standing cost of T166 AC2.
>
> ### 🎯 NEXT ACTION
> Unchanged from below: **T165 Phase 1 — schema and validation (R1/R4), tasks 1.1–1.4.** Phase 0.4
> rewrote both halves; read the revised task text first. Do NOT start Phase 2 (owner-gated).
> Also open: **T164 AC1/AC6 stay unticked** — only 11 CLIs were probed, not the full surface, and
> AC6 wants a committed `tools-check-test`, which does not exist yet.
