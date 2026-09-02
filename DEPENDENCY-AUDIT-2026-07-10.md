# Cross-Project Dependency Audit — 2026-07-10

Scope: wom7api, wom7cfworkers, wom7ext, wom7web (monorepo), wom7swarm, wom7mlx, wom7sec, wom7skills.
Method: parsed every dependency manifest (17 package.json, requirements.txt, Cargo.toml, setup.py); findings spot-checked against source files.

## Inventory

| Project | Stack | Manifest(s) | Lockfile |
|---|---|---|---|
| wom7api | TS / Hono / Drizzle / Wrangler | package.json | pnpm-lock (in sync, 06-23) |
| wom7cfworkers | TS / Hono / Wrangler | package.json | pnpm-lock (in sync, 07-08) |
| wom7ext | TS browser extension ×2 (`extension`, `extension-ff`) | 3 package.json | pnpm-lock (in sync, 06-02) |
| wom7web | pnpm@10.32.0 + turbo monorepo: 4 apps, 6 packages, 2 tooling pkgs | 13 package.json | pnpm-lock (in sync, 07-09) |
| wom7swarm | Python / FastAPI | requirements.txt | none |
| wom7mlx | Rust (`wom7-mlx-rs`) + vendored upstream repos | Cargo.toml | — |
| wom7sec | Python via uv | scripts/setup.py wrapper | none found |
| wom7skills | Skills/plugin bundle | plugin.json only | n/a |

Vendored third-party clones under `wom7mlx/` (mlx, mlx-lm, candle, mlx-rs, …) excluded from cross-project comparison.

## Version mismatches across repos

21 dependencies are shared across ≥2 repos; 14 have version drift. The ones that matter:

| Dependency | Spread | Risk |
|---|---|---|
| **typescript** | ^5.5.2 (cfworkers) → ^5.6.3 (ext) → ^5.9.3 (api, crawler) → ^6.0.3 (web root) | Major-version split; TS6 vs TS5 behavior/emit differences across repos |
| **zod** | ^4.2.1 → ^4.4.3 across 9 consumers | Schema types passed between api/workers/web may diverge |
| **@supabase/supabase-js** | ^2.87.1 (ext) → ^2.105.3 (cfworkers); 7 distinct specs in 10 consumers | Widest drift in the estate; auth/client behavior differs by consumer |
| **@modelcontextprotocol/sdk** | ^1.0.1 (ext/extension!) vs ^1.27–1.29 elsewhere | ^1.0.1 is drastically stale — likely predates current MCP spec |
| **marked** | ^17.0.6 (web apps) vs ^18.0.x (api, cfworkers) | Major-version split in rendered output paths |
| **wrangler** | ^4.87 / ^4.88 / ^4.98 | Deploy toolchain drift across the 3 CF repos |
| **hono** | ^4.12.18 (web apps) vs ^4.12.25 (api, cfworkers) | Minor; easy align |
| **@playwright/test** | ^1.57 (web) vs ^1.58.2 (api) | Minor |
| **vitest** | ^4.1.5 (^) vs ~4.1.8 (cfworkers, tilde) | Range-style inconsistency too |
| **dotenv, tsx, ws, fast-xml-parser, @tinybirdco/sdk, @types/node** | minor/patch drift | Low |

Already consistent (good): @hono/zod-validator, esbuild, ts-node, gauge-ts, undici, @vitest/ui.

## Intra-monorepo drift (wom7web)

Same package, different versions *inside one pnpm workspace*: supabase-js (5 specs), zod (3), typescript (2, incl. 5.x vs 6.x), svelte (^5.53.7 vs ^5.56.4), @modelcontextprotocol/sdk, @types/node, csv-parse. A monorepo should pin these once — use pnpm `catalog:` or root-level `overrides`.

## Other findings

1. **`google-antigravity` in wom7swarm/requirements.txt** — unknown package name alongside fastapi/uvicorn/pydantic; verify it's the intended package (name pattern is typosquat-prone). All 4 entries are also completely unpinned — no versions, no lockfile.
2. **wom7ext/extension vs extension-ff** — both named `wom7ext-extension`, manifests have diverged (ff missing esbuild/patch-package/postinstall, older build script). If ff is a port, consider a shared base; also `OBSOLETE_WARNING.md` sits in this repo.
3. **wom7ext MCP SDK ^1.0.1** — the single most stale pin found; the extension talks MCP to repos running ^1.29.
4. **wom7mlx Cargo** — deps pinned to crates.io versions but `[patch.crates-io]` redirects mlx-rs/mlx-sys to local paths; version numbers there are decorative. Fine, just be aware.
5. **No Node version pinning** — no `.nvmrc`/`engines` anywhere except `@webomage/openclaw` (node >=22.12). `packageManager` set only in wom7web root.
6. **Hygiene** — all 4 pnpm lockfiles in sync with their manifests (mtime check). `.env.bak` present in wom7ext.

## Recommended actions (ordered)

1. ~~Verify/pin wom7swarm requirements; confirm `google-antigravity` is legit.~~ — **RESOLVED 2026-07-11: wom7swarm DECOMMISSIONED** (moved out of workspace, Cloud Run dead, no cost). CVEs moot. See [`DECOMMISSIONED.md`](DECOMMISSIONED.md).
2. Upgrade wom7ext `@modelcontextprotocol/sdk` ^1.0.1 → ^1.29.
3. Adopt pnpm `catalog:` in wom7web for supabase-js, zod, typescript, svelte.
4. Decide TS 6.x estate-wide or hold at 5.9 — currently split.
5. Align supabase-js + wrangler across wom7api/wom7cfworkers/wom7web.
6. Add `engines.node` + `packageManager` to wom7api, wom7cfworkers, wom7ext.
