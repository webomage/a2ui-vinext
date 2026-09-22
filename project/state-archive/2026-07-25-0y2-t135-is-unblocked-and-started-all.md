<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0y2. superseded pickup block — 2026-07-25 (NIGHT) — **T135 is UNBLOCKED and STARTED: all 7 open owner questions are  -->

### 0y2. superseded pickup block — 2026-07-25 (NIGHT) — **T135 is UNBLOCKED and STARTED: all 7 open owner questions are ANSWERED. Two business tickets filed (T136/T137). The next action is T135's spec.**

> **Nothing is half-finished in the tree.** wom7web clean, pushed (`ef8e3b7e`). `git pull` first — a
> parallel Antigravity agent also commits to `beta`.
>
> ### ▶ START HERE — the shortest path back into useful work
> 1. `git pull` in all repos.
> 2. **`w0m-sdlc-spec` for T135.** The start gate is DONE (`9dea5eda`) and **every owner question that
>    blocked it is answered and recorded in the ticket as a binding spec input.** There is nothing left
>    to ask before writing the spec — go straight to it.
> 3. **Do not re-measure what this session measured.** Four measurements changed T135's scope and are
>    recorded in the ticket *and* the board row. They are marked "do not re-derive" because each cost a
>    real command run: the Metal-toolchain blocker, the `wom7ext` toolchain vacuum, the vendored MCP-SDK
>    license defect, and the `wom7skills` green baseline. §0w below.
> 4. **Tracking is in sync.** `sync_github.py` exit 0, `created=2 reused=95`: **T136 → GH #97**,
>    **T137 → GH #98**. It takes several minutes and prints nothing until it exits — not a hang.
>
> ### ✅ WHAT THE OWNER ANSWERED THIS SESSION (7 questions — all of T135's five, plus two more)
> These are **decisions, not suggestions.** Full text in `project/tickets/T135.md` → "Owner decisions".
>
> | # | Question | Answer |
> |---|---|---|
> | 1 | README substantive bar | **Required sections** — the *what-is / how-to-run / where-are-docs* triple, as detectable headings. **Not** a length rule (padding), **not** file-exists (vacuous). |
> | 2 | Which human-facing files | **Universal, all four families, all 7 repos**: `README` + `LICENSE` + `SECURITY.md` + `CONTRIBUTING`/`CoC`. Baseline for the last three is **zero**. |
> | 3 | Which license | **Proprietary / `UNLICENSED`.** These repos are **not** being opened. Pairs with AC11's `private: true`. |
> | 4 | pre-push scope | **Per-stack subset** — each repo gets only what its stack warrants. Not wom7web-only, not uniform. |
> | 5 | Retire `ruff` from TS/Rust repos | **Yes, from both.** A wrong-stack linter reads as coverage while checking nothing. |
> | 6 | wom7mlx dirty tree vs the Rust gate | **"Measure first, then decide"** — done, see §0w. The dirty tree was **not** the blocker. |
> | 7 | §0t "fast calculated indexes" | **B-tree + functional indexes now**; generated columns + materialized views as a **separate P2 ticket**. ⚠️ **NOT YET FILED — see the queue table.** |
>
> ### 🔴 OWNER ACTIONS OUTSTANDING (only you can do these — now FOUR)
> 1. **Revoke the `casualuser` GitHub token** at GitHub → Settings → Applications / PATs. Dropping the
>    DB row did **not** revoke it; it was ciphertext with no recoverable key, so it could be neither
>    validated nor revoked programmatically. Identity: `casualuser`, GitHub id `1243074`.
> 2. **T99(d) task 3.1 — provision the key.** `CONNECTOR_TOKEN_KEY_V1` = `openssl rand -base64 32` and
>    `CONNECTOR_TOKEN_KEY_VERSION` = `1`, into Infisical and exposed to the edge runtime as Supabase
>    secrets. The helper validates length and base64 and refuses to run without them, so a wrong value
>    fails loudly. **Do not let an agent invent key material.**
> 3. **T99(d) task 3.5 — apply `20260725180000`.** Deliberately not applied: it is outward-facing and
>    landing the columns before 3.1 buys nothing.
> 4. 🆕 **Install the Xcode Metal toolchain** if you want a real Rust *compile* gate:
>    `xcodebuild -downloadComponent MetalToolchain`. Until then `cargo check`/`clippy` **cannot** run in
>    `wom7mlx/wom7mlx` at all (§0w) and T135 ships `cargo fmt --check` only. It is a large download, so
>    it was not started unprompted.
>
> ### THE QUEUE — ranked by ready-to-buildness
>
> | # | Item | State | Next action | Where |
> |---|---|---|---|---|
> | 1 | **T135** — repo-hygiene gates (4 asks bundled) | 🟡 **in-progress, start gate done, 0 open questions** | **`w0m-sdlc-spec`** | §0w, §0v |
> | 2 | **DB relations, B-tree strand** (owner answer 7) | answered, **NOT filed** | `w0m-sdlc-new` — feed §0t grounding, **do not re-derive**; file the matview/generated-column half as a **separate P2** | §0t |
> | 3 | **T136 / T137** — the two business asks | ⚪ filed, GH #97/#98, no spec | T136 is **blocked on 1 owner question** (which WP estate); T137's AC0 = reconstruct T111 | §0x |
> | 4 | **2 new SDLC skills + STATE.md schema** | grounded, **unticketed** | `w0m-sdlc-new`. Needs no owner input — the honest fallback if the owner is away | §0q |
> | 5 | **T99(d) sections 4–7** | blocked | needs owner actions 2+3 above | §0s |
>
> ⚠️ **T135's four strands were bundled deliberately** — they need the same plumbing (a `just` recipe +
> a `stacks-policy.json` role + a pre-commit hook + `sdlc-doctor`) over the same repos. **Do not
> re-split them.**
