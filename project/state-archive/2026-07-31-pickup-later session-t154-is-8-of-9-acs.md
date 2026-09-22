<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### ⭐ (was) PICK UP HERE — 2026-07-31 (later session) — **T154 is 8 of 9 ACs: the exposure RATCHET is live (`just mcp-ra -->

<details><summary>Previous pickup block (2026-07-31, later session) — superseded, kept for trace</summary>

### ⭐ (was) PICK UP HERE — 2026-07-31 (later session) — **T154 is 8 of 9 ACs: the exposure RATCHET is live (`just mcp-ratchet`), its cadence is `just audit` outside `--quick`, and a SECOND live finding surfaced — a Postgres on `0.0.0.0`. Next: T154 AC8 (declared-vs-listening reconcile), the last AC.**

> **Written for an agent with none of my context. Measured 2026-07-31, after the quota pause.**
>
> ### 📍 STATE — measured, not assumed: **wom7web is 5 ahead, wom7api 2 ahead**; nothing pushed
> All four T154 commits are local (`204b9b0b` `ec34cbaf` `b014eeed` `32bcdfa8`) plus this
> STATE commit; `wom7api 78dd185` on top of `17c3caf`. The previous block's *'4 wom7web commits
> are LOCAL'* named the T155 trio — **those are pushed now**, so do not go looking for them.
> **Push is an owner call**: a wom7web push triggers the ticket mirror.
>
> ### ✅ WHAT LANDED (this session)
> 1. **`just mcp-ratchet` — the exposure may shrink, never grow** (`project/scripts/mcp_ratchet.py`,
>    baseline `project/mcp-exposure-baseline.json`, `just mcp-ratchet-test`, 35 checks). Live: **15
>    tracked surfaces vs 15 declared**, exit 0. It is a SEPARATE recipe from `mcp-exposure` on
>    purpose: that one answers *'is anything open now?'*, which is permanently red for a container
>    that is not ours, and **a permanently red gate gets muted**.
> 2. **AC6's cadence is `just audit` (T96), outside `--quick`** — and the placement IS the
>    enforcement, because `--quick` is the pre-push subset, so AC6's *'never a push gate'* is a
>    property of the call site rather than a comment. A scheduled task was **rejected, with
>    reasons recorded** so it is not re-litigated.
> 3. **A second live finding: `com.docke:4004` is `evercred-0-postgres-1` — a POSTGRES bound to
>    `0.0.0.0` and confirmed reachable from the LAN.** Not w0m's (same compose stack as the
>    unauthenticated inngest MCP). Both are recorded `known-open`: pinned so they cannot get
>    worse, printed red on every audit run. **Two owner actions in someone else's repo.**
>
> ### 🔬 THREE MEASUREMENT TRAPS, all caught by testing rather than by reading
> - **Mutation testing found a hole the green suite hid.** 5 mutants planted, 4 died; the survivor
>   was the address-family merge — **a `401` on `::1` masking a `200` on `127.0.0.1`**. The test
>   passed only because `None` was falsy in the right places. ⇒ **A green suite is a hypothesis
>   until a mutant has died in each rule.**
> - **Running it live found a bug the fixtures could not.** Several ephemeral ports fold onto one
>   `command:*` entry, so per-port comparison reported a **phantom improvement on every run,
>   forever** — and `--save` would have written whichever port came last. ⇒ **A gate that always
>   says 'you improved!' is a gate nobody reads.**
> - **'Never asked' is not 'asked and clean'.** The inventory left `probe` absent for a surface
>   that does not speak HTTP and `null` for one that does but is not MCP. **I misread my own
>   output** and nearly filed the LAN-reachable Postgres as 'not MCP'. `probed` is now recorded
>   explicitly. ⇒ **A blind spot must look different from a clean result.**
>
> ### ⚠️ FOUND IN PASSING, NOT MINE — `just discovery-test` is 26/28 and was before I started
> Verified by stashing every local change and re-running. Both failures anchor on a hardcoded
> `pre-push:25` raw invocation that **T149 AC3 already removed** (`.husky/pre-push:25` is now
> `just typecheck`), so `raw_invocations` is legitimately `[]`. The real cost is not two red
> checks: **the raw-invocation detector's positive path is now covered by nothing**, which is this
> estate's recurring vacuous-gate shape. Fix with a synthetic fixture hook, not by deleting the
> checks. `.husky/pre-push:70`'s comment is stale for the same reason.

</details>
