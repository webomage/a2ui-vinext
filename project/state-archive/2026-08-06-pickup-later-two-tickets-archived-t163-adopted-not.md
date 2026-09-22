<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### ⭐ (was) PICK UP HERE — 2026-08-06 (later) — **TWO tickets ARCHIVED (T163 adopted-not-proven, T168 with the schema sa -->

<details><summary>Previous pickup block (2026-08-06, later) — superseded, kept for trace</summary>

### ⭐ (was) PICK UP HERE — 2026-08-06 (later) — **TWO tickets ARCHIVED (T163 adopted-not-proven, T168 with the schema salvaged), T166+T169 built to 100%, T170 reframed to "managed serena", T171 filed with the owner's VM topology. All 7 repos clean, 0 unpushed. The through-line: THREE gates were found reporting green over nothing.**

> **Written for an agent with none of my context. Measured live 2026-08-06.**
>
> ### 📍 STATE — all 7 repos clean, **0 unpushed**
> ⚠️ Supersedes the block below, which said *"8 commits UNPUSHED"* — those are pushed.
> `wom7mlx` still shows 9 dirty / no upstream; **that is another agent's, not yours.**
> ✅ `tools-check` **21 tools, 0 required-problems** (1 informational drift: infisical patch).
> ✅ `skill check` **86 installed · 76 managed · 10 excluded · 0 unmanaged**, lockfile matches.
> ⚠️ Run `just skill check` **from `wom7web`** — from any other repo it reports `0 installed` and
> then errors, which reads like a broken manifest and is just the wrong cwd.
>
> ### 🔴 THE THROUGH-LINE — three gates reporting green over nothing, in one day
> | Gate | What it was actually doing |
> |---|---|
> | `state_doctor` (morning) | matched **0 of 155** board rows; published *"121 tickets with no row"* as fact while its own test passed — the test asserted the *comparison*, never the *collection* |
> | `mcp-exposure` ([[T169]]) | reconciled an **empty set** and exited green — all 12 declarations were stdio/remote, so the one local-http listener it existed to catch was invisible |
> | `headroom audit-reads` ([[T163]] AC5) | audits **Read-tool traffic only**; Read fell −0.7 pp while **Bash rose +0.9 pp** — the work routed around the metric |
> ⇒ **Ask what a gate did NOT enumerate before believing its number.** All three were green.
>
> ### ✅ WHAT LANDED
> 1. **[[T163]] ARCHIVED — deliberately NOT as a success.** 7/7 ACs, but AC5's outcome was
>    **adverse**: stale-read share **46.7% → 47.4%** over 9 post-change sessions, **~71% marginal
>    rate** on new Read bytes. AC5 was worded to close on movement *in either direction*, which is
>    why an unwelcome result could close honestly instead of holding a P0 open until the number
>    improved — **copy that AC wording**. Residue → **D29** (benefit unproven) + **D30** (the metric
>    cannot settle it).
> 2. **[[T168]] ARCHIVED.** Retired the dead Upwork collections + both `lib/vault.ts`. On owner
>    instruction the zod was **SALVAGED, not merely recoverable** → `project/schemas/upwork-vault/`
>    (`.txt`, outside typecheck/lint) with the field-alias sets, enum-collapse rules and a **recorded
>    large-number YAML precision bug — read ids as STRINGS**.
> 3. **[[T166]] 7/7 · [[T169]] 6/6 — both at 100%, both still `in-progress`.** serena declared +
>    pinned `serena-agent==1.6.1`; headroom + headroom-proxy declared with transport/bind/auth;
>    `mcp_declared.reconcile` fixed to separate **presence** from **protocol**.
> 4. **[[T170]] reframed** (owner): *"more about our managed and extended serena"* — astro is the
>    first extension, **maintenance is the centre of gravity**, SQL is the named second consumer.
> 5. **[[T171]] filed** with the owner's topology: **proxy per sandbox, both `claude` and `headroom`
>    inside the VM.** That dissolves the loopback conflict; the hard problem moved to **credentials**.
>
> ### 🧭 THE ASYMMETRY THAT WILL BE "FIXED" BY MISTAKE
> **Host: serena is w0m-owned** (pinning broke Headroom's ledger fingerprint, so its `PreToolUse`
> hooks now leave it alone — `wrap.py:1938` *"never a user-managed Serena"*).
> **Sandboxes: serena stays Headroom-owned, as-is.** Deliberate. **[[T166]] is host-scoped, not
> global** — a design that "corrects" the sandbox has misread it.
>
> ### 🎯 NEXT ACTION
> **Unchanged: [[T165]] Phase 1 — schema and validation (tasks 1.1–1.4).** Phase 0.4 rewrote both
> halves; read the revised text first. **Do NOT start Phase 2** — owner-gated on 3 decisions.
> Also ready to close: **[[T166]]/[[T169]] need archiving** — but ⚠️ **do not archive T166 until
> serena is proven by a REAL TOOL CALL.** Its AC1b closed on `serena --version`, which **never loads
> a project config**; corrected in place 2026-08-06.
>
> ### ⛔ OWNER ACTIONS
> 1. **DEPLOY** — nothing from the CV work is live; [[T161]] AC3 denies `deploy*` to the agent.
> 2. **3 T165 fidelity decisions** — `x_highlights[]` shape · EventCartel dates · partial totals.
> 3. **Scribely** — written from the job description only; confirm delivered vs scoped.
> 4. **[[T171]] credentials** — whether one personal Pro subscription may back N concurrent
>    sandboxed agents is a **terms question**, deliberately not guessed at.

</details>
