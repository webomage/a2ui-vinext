<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0w. 🔎 MEASURED 2026-07-25 (night) at T135's start gate — four findings that changed the ticket's scope. DO NOT RE-DE -->

### 0w. 🔎 MEASURED 2026-07-25 (night) at T135's start gate — four findings that changed the ticket's scope. DO NOT RE-DERIVE.

Recorded here as well as in the ticket because each one is a command run, and three of them contradict
what the ticket assumed when it was filed.

1. 🔴 **`cargo check`/`clippy` are UNADDABLE in `wom7mlx/wom7mlx` — still true, but ⚠️ THE CAUSE BELOW IS
   SUPERSEDED. Read this note first.**
   > **Stage 1 (below) was RESOLVED the same day:** the owner ran `xcodebuild -downloadComponent
   > MetalToolchain` and the cmake/`metal` failure is **gone** — the build now reaches real Rust
   > compilation.
   > **Stage 2 is the current blocker:** `cargo check` now exits **101 with 25 errors, all inside the
   > vendored `mlx-rs` crate**, none in w0m code — `error[E0425]: cannot find function
   > mlx_fast_rope_dynamic / mlx_fft_fftshift / mlx_linalg_eig / mlx_segmented_mm in crate mlx_sys`, plus
   > an `E0061` arity mismatch on `mlx_gather_qmm`. Cause: `wom7mlx/Cargo.toml:31-32` **path-overrides
   > `mlx-rs` and `mlx-sys` to the sibling clone `../mlx-rs`**, and **that clone is itself mid-surgery**
   > (10 dirty paths incl. `mlx-sys/build.rs` and the `mlx-c` submodule) — so the vendored Rust bindings
   > and the vendored C API are **version-skewed against each other**.
   > ⇒ Under **AC8** the verdict is unchanged: still a permanently-red hook, now for a **dependency-skew**
   > reason instead of a host one. **Re-measure once the `../mlx-rs` work lands.** This is the one place
   > the in-flight work genuinely *does* block a gate — unlike `cargo fmt --check`, where it does not.
   > **The full two-stage record is in `project/tickets/T135.md` AC2a.**

   *(Original stage-1 measurement, kept for the diagnostic technique:)*
   `cargo check --all-targets` dies during **dependency** compilation, before reaching any w0m code: the
   `mlx-sys` build script drives cmake to build MLX's Metal kernels, and `metal` aborts with *"cannot
   execute tool 'metal' due to missing Metal Toolchain; use: `xcodebuild -downloadComponent
   MetalToolchain`"* — Xcode **26.6** ships it as a separately-downloaded component. `xcrun -f metal`
   *does* resolve a path, so the shim exists while the component does not; checking `xcrun` alone gives
   the wrong answer. Under **AC8** this is exactly the class of hook that must not be added.
   ✅ **`cargo fmt --check` is the gate instead, proven both ways:** **green at HEAD** (exit 0, measured
   in a `git worktree add --detach` at HEAD so the in-flight work was excluded, then removed) and **red
   on real violations** (exit 1). It needs no compilation, so the Metal component is irrelevant to it.
   ⚠️ The 10 uncommitted paths (another agent's logits-mismatch work) *do* make it fail on the working
   tree — that is the gate working correctly. **Nothing needs to land first, and their code must not be
   reformatted to make a gate green.** Their tree was left byte-identical (verified: still 10 paths).
2. 🔴 **AC3 is much bigger than "add a hook": `wom7ext` has NO toolchain at all.** Its `package.json` is
   **four lines** — one runtime dep (`ws`), **zero devDependencies, zero scripts** — and there is **no
   `tsconfig.json`**, despite 96 tracked `.ts` files. So "gains lint/format/typecheck" means installing
   and configuring a toolchain, not wiring a hook. Measured baseline with wom7web's oxlint:
   **100 warnings, 0 errors** → an *error-blocking* lint gate **starts green**, but a typecheck baseline
   cannot be assumed green until a tsconfig exists. **Precedent for the shape:** debt rows D12/D20 settled
   this project on **staged-file ratchets** — a ratchet starts green on an empty diff while the backlog
   stays visible and advisory, which satisfies AC7 without a big-bang cleanup.
   ℹ️ Also note `wom7ext/OBSOLETE_WARNING.md`: its **Upwork** half is deprecated (API-only now), and it is
   "primarily focused on specific LinkedIn operations" pending refactor. Gate the live half; don't invest
   in the dead half.
3. 🔴 **A THIRD vendored tree exists that AC6 did not list — and it is a live license defect.**
   `wom7ext/extension/src/vendor/mcp-sdk/` — **63 tracked files**, and **no `LICENSE`, no provenance
   note, no `Copyright` string anywhere in it** (grep found zero). The MCP TypeScript SDK is **MIT**,
   which requires the notice be retained in copies, and this is **shipped inside the extension bundle**.
   This is the **second instance of the same pattern** — the board already records that `mcp-builder`
   declares `license: LICENSE.txt`, a file our copy omits. So AC6's vendored surface is
   `.agents/skills/` (~50) **+ wom7mlx's 13 upstream clones + this**, and the ticket now says so.
4. ✅ **AC2's TypeScript half starts green** — `just skills-typecheck` exit **0** (`tsc --noEmit`) and
   `just skill-test` exit **0** (37 tests, 0 fail). That gate can be added with no cleanup first. It is
   the only one of the four measurements that was good news.

ℹ️ **Two host gotchas found while measuring, worth not rediscovering.** (a) **`timeout` on this machine
is a pyenv shim, not GNU `timeout`** — it fails with `ModuleNotFoundError: No module named 'examples'`.
Use the tool-level timeout instead of wrapping a command. (b) **This shell is zsh: `$PIPESTATUS` is
bash-only** and silently yields empty; use `${pipestatus[1]}` (1-indexed). Both cost a wasted run.
