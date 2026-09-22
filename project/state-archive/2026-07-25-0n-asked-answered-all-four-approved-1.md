<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0n. OWNER ASK 2026-07-25 — per-repo SDLC check gaps. **ASKED & ANSWERED: all four approved. 1 of 4 BUILT.** -->

### 0n. OWNER ASK 2026-07-25 — per-repo SDLC check gaps. **ASKED & ANSWERED: all four approved. 1 of 4 BUILT.**

> *"we should look what's not enable for repo on checks from sdlc and ask what to enable"*

**Still not ticketed** (see the ⭐ block — it needs `w0m-sdlc-new`). The owner was asked and
**approved all four gaps** on 2026-07-25. **Gap 1 is built and pushed; gaps 2–4 are open.**

#### 🔴 THE EARLIER MATRIX IN THIS FILE WAS WRONG. Corrected 2026-07-25, re-measured from scratch.

The previous version of §0n claimed **"`wom7mlx` has ZERO hooks"** and ranked it the #1 🔴 finding.
**That is false, and the error is instructive:** it measured the **outer** `wom7mlx/` directory, which
**is not a git repo at all** (`git rev-parse` → *not a git repository*). It is a workspace holding
**14 independent clones**, 13 of them vendored upstream projects (`mlx`, `mlx-lm`, `mlx-rs`, `candle`,
`mlx-vlm`, …). w0m's own repo is the **inner** `wom7mlx/wom7mlx` — which the file *itself* already
said is how `stacks-policy.json` models the mlx stack. So the measurement contradicted the project's
own model of that stack, and "no config in a non-repo" was read as "a repo with no gates".

**`wom7mlx/wom7mlx` in fact has the full security floor installed** via the pre-commit framework:
`gitleaks · osv-scanner · semgrep · conventional-commit · ruff`. Nothing was missing.

⚠️ **Two lessons for whoever audits gates next.** (1) Establish the git boundary *before* measuring
coverage — `git rev-parse --show-toplevel` first. (2) **A `.pre-commit-config.yaml` is not a gate.**
Check that a hook is *installed*, and check `core.hooksPath`: `wom7web` redirects it to `.husky/_`, so
its `.git/hooks/pre-commit` is **inert** and the live hooks are `.husky/{pre-commit,commit-msg,pre-push}`.
Reading either location alone gives a wrong answer for some repo. This is the same vacuous-gate family
as T127's `0 managed` / `70 managed` prefix bug and T130's `enforce_raw`.

#### The corrected matrix (verified 2026-07-25: config present **and** hook installed **and** hooksPath resolved)

| Repo | security floor | extra gates | pre-push | hook mechanism |
|---|---|---|---|---|
| `wom7web` | ✅ | oxlint · prettier-astro · oxfmt · skills-drift · guard-test-admin · mmd-validate · lexicon-lint · status-dashboard | ✅ **husky** | `core.hooksPath=.husky/_` |
| `wom7api` | ✅ | mmd-validate · oxlint · oxfmt · codegraph-sync · **deno-check** · **typecheck-worker** | — | `.git/hooks` |
| `wom7cfworkers` | ✅ | **tsc** · oxlint · oxfmt · codegraph-sync | — | `.git/hooks` |
| `wom7ext` | ✅ | **none** 🟡 | — | `.git/hooks` |
| `wom7skills` | ✅ | ruff (Python — wrong stack 🟡) | — | `.git/hooks` |
| `wom7mlx/wom7mlx` | ✅ | ruff (Python — repo is **Rust** 🟡) | — | `.git/hooks` |
| `wom7md` | ✅ **as of `38fbbf7`** | semgrep (near-inert by design) | — | `.git/hooks` |

`wom7sec` is not currently present as a working tree at the repo root — the earlier matrix listed it;
it could not be re-verified this session. **Treat that row as unconfirmed, not as fact.**

#### Gap 1 — ✅ BUILT 2026-07-25: `wom7md` secret scanning (wom7md `38fbbf7`)

It was the one genuinely ungated repo — **no config and no installed hook**. Prose-only justified
exempting it from *build* gates; it never justified skipping secret scanning, since the 2026-07-12 DB
superuser password re-leaked through a **markdown walkthrough**.
- `.gitleaks.toml` copied **byte-identical** from `wom7web`/`wom7api`, so the three custom w0m rules
  now cover it. **This also closes a known-open propagation item** from
  `[[leaked-db-superuser-2026-07-12]]`.
- **Proven, not assumed, in both directions:** `gitleaks detect` over all **14 commits** of history
  found **zero** leaks *before* the gate existed → it starts green and walls off no pre-existing debt
  (the T127/T130 principle). Then a planted probe containing a bare-word password **and** a
  `postgres://` URI was caught by **`wom-db-password-in-prose`** and
  **`wom-postgres-uri-inline-password`** before removal.
- 🔎 **`osv-scanner` is deliberately OMITTED here — the one intentional divergence from the siblings.**
  Measured: with no lockfile in the tree it exits **128** (*"No package sources found"*), so including
  it would make the gate fail on **every** commit for a structural reason. In a project whose hard rule
  is **never `--no-verify`**, a permanently-red hook trains people to bypass the entire stack. The
  config says to add it the moment a manifest lands. **Generalise this:** do not paste the standard
  stack into a repo without running it first.

#### Gaps 2–4 — approved by the owner, NOT built

2. 🟡 **Correct the stack-mismatched linters.** `wom7skills` is **TypeScript** but gated only by
   `ruff` (Python); its real checks exist as `just skills-typecheck` / `just skill-test` in
   **wom7api's** justfile and are run when someone remembers. `wom7mlx/wom7mlx` is **Rust** and also
   carries `ruff`, with **no `cargo check`/`clippy`** — the owner approved adding a Rust gate and
   retiring the wrong-stack linter.
3. 🟡 ~~**`wom7ext` has no lint/format/typecheck at all** despite being a TS browser extension.~~
   🔴 **WRONG — corrected 2026-07-25 (late night). Do not act on the struck line.** That measured
   `wom7ext/package.json`, the near-empty **repo-root** manifest. The real packages are one level
   down: **`wom7ext/extension/` has 9 devDeps, 7 scripts including a `type-check`, and a
   `tsconfig.json`**; `wom7ext/extension-ff/` (a **second**, Firefox surface, same package name) has 5
   devDeps and its own tsconfig. **The gap is that none of it is wired into a hook** ⇒ T135 AC3 is
   *"wire up what exists"*, not *"build a toolchain"* — materially smaller than filed.
   ⚠️ **This is the SAME wrong-directory-level error this very section documents two paragraphs above
   for `wom7mlx`** — made again, in the same estate, on the same day, by the correction pass itself.
   The lesson that keeps not sticking: **"no config at this path" ≠ "no config in this repo."** Locate
   every `package.json` (excluding `node_modules`) before scoping, and resolve the git boundary first.
   ✅ Start-green premise still holds: `oxlint` over `extension/src` exits **0** (warnings only) — but
   much of that noise is the vendored `mcp-sdk` tree, which should be **excluded from lint** while
   staying in scope for the license audit.
4. 🟡 **Extend husky/pre-push beyond `wom7web`.** Every pre-push gate (astro check, `deps-check`,
   `discovery`, ticket-sync, tech-debt advisory) runs **only** there; the other repos are gated by
   pre-commit alone.

Ties [[T112]] / [[T119]] / [[T130]], §0m, and §0p (same mechanism, same repos — **build them together**).
