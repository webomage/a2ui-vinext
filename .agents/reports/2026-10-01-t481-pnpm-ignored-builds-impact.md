# pnpm "Ignored build scripts": measured impact (T481)

Ticket: [[T481]]. Earlier note (same ticket, 2026-10-01) covered `esbuild`, `workerd` and `core-js-pure` and named its own gaps: the other packages, and whether a full build and deploy works with the scripts skipped. This report closes both. Date: 2026-10-01. Method: read-only; nothing installed, allowlisted or changed.

## What the warning is

pnpm 10 and later skips a dependency's install scripts unless the project lists the package in `pnpm.onlyBuiltDependencies`. No repo sets either that list or `pnpm.ignoredBuiltDependencies`, so every fresh install prints the box. Fresh installs happen in the stable worktree and in every release worktree, which is what deploys build from. The live checkouts were installed earlier and record no ignored builds, so **the environment that ships differs from the one tested by hand**. That difference was the part worth measuring.

## What each skipped script does, and what happens without it

| Package | Repos | Script | Does the product need it? | Measured without it |
|---|---|---|---|---|
| `esbuild` 0.28.1 | web, func, skills | `postinstall: node install.js` | No. The binary arrives as an optional dependency; the script only verifies it and swaps in a faster shim. | Real TypeScript transform and a real bundle succeed in `wom7web` and `wom7func` |
| `workerd` 2026-08-11 | web, func | `postinstall: node install.js` | No. Same pattern: the platform binary is an optional dependency. | `workerd --version` runs; `wrangler --version` is 4.123.0 |
| `@parcel/watcher` 2.5.6 | web | `install: build-from-source.js` | No. Prebuilt binaries ship as optional dependencies. | Native binding loads and exports `subscribe`, `getEventsSince` |
| `bufferutil` 4.1.0 | web | `install: node-gyp-build` | No. Prebuilds for four platforms are in the package, and `ws` falls back to plain JavaScript without it. | Loads and exports `mask`, `unmask` |
| `@fission-ai/openspec` 1.6.0 | web | `postinstall.js` | No. Prints a one-line tip about shell completions and never fails. | `openspec --version` is 1.6.0; `openspec validate --strict` ran today |
| `core-js-pure` 3.49.0 | func | `postinstall`, wrapped in try/catch | No. It prints a donation notice. | Cosmetic only |
| `taiko` 1.5.0 | web | `install: lib/install.js` | **Only if** `BROWSER_ENGINE=taiko`. It downloads a Chromium. | See below |

Two of my own checks failed first (`esbuild` and `@parcel/watcher` from the `wom7web` root). The cause was my check, not the packages: both are transitive dependencies, which a bare `require` from the root cannot see. Run against the exact installed copy, both work.

## The one that could matter: taiko

`taiko` is real code in the Gauge step files and `tests/support/hooks.ts`, and its install script downloads a Chromium. It is skipped in every fresh install, and no taiko Chromium exists in the live, stable or any release install. But `hooks.ts` line 78 sets `state.engine = process.env.BROWSER_ENGINE || "playwright"`, and nothing in `wom7web`, `wom7api` or `.w0m/sdlc.json` sets `BROWSER_ENGINE`. Playwright takes its browser from its own cache (`~/Library/Caches/ms-playwright`, five Chromium builds present), not from taiko. So taiko's missing download affects the tests only for someone who sets `BROWSER_ENGINE=taiko` by hand, and that would fail with a missing browser, not corrupt anything.

## The proof that matters: what shipped

| Release | Deployed | wom7web ignored | wom7func ignored |
|---|---|---|---|
| 2026.10.01-1790853122 | yes | all six | esbuild, workerd, core-js-pure |
| 2026.10.01-1790863675 | yes | all six | same |
| 2026.10.01-1790865449 | yes | all six | same |

Each was built from a worktree with the scripts skipped, passed its blocking suites and 7 of 7 golden checks, deployed with exit 0, and serves its version from `/api/health` (checked earlier for the first two). The golden run logs "0 build warnings (Vite, Rollup, LightningCSS, Astro clean)". The stable run of 4,765 checks over 215 suites also ran on a skipped-scripts install.

**Conclusion: measured impact is nil.** Six of seven skipped scripts are verification, optimisation or a notice for binaries that arrive another way. The seventh matters only for an engine nothing selects.

## What the warning does cost

1. **Noise hides a real signal.** pnpm prints the same box for a harmless `esbuild` and for a new package that wants to run code at install. With the box on every run, nobody reads it.
2. **Nothing records that ignoring is deliberate.** No list says "reviewed and refused", so a new install-script package is silently skipped today and would be silently allowed if someone ran `pnpm approve-builds` without reading.
3. **A separate toolchain finding:** `wom7ext` and the root declare no `packageManager`, so their installs use the host's pnpm 12.0.0, while `wom7web`, `wom7api`, `wom7func` and `wom7skills` pin 10.32.0. Its recorded install is `by pnpm@12.0.0`. Not measured for impact; ticket it.

## Options, with what each changes

| Option | Effect | Risk |
|---|---|---|
| A. Do nothing | Warning stays | Items 1 and 2 above |
| B. List all seven under `pnpm.ignoredBuiltDependencies` in each repo | Warning disappears; the refusal becomes reviewed and visible in a diff | None measured: it records what already happens |
| C. B plus `strictDepBuilds: true` (fails an install on an unreviewed script) | A new package with an install script stops the install until someone decides | An install fails on the first new one; needs a test on a throwaway repo first, which I have not run |
| D. Allow esbuild and workerd to run their scripts | Runs `install.js` at every install | Adds install-time code execution for no measured gain |

Recommendation: B now, C after a test, never D, and never allow `taiko` (an install-time download of an unpinned browser from outside the lockfile).
