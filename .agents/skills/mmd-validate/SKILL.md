---
name: mmd-validate
description: Validate Mermaid diagrams render correctly — standalone .mmd files AND ```mermaid fences embedded in .md/.mdx docs & specs. Use when adding/editing diagrams, wiring a pre-commit/CI gate, or validating diagrams server-side (CP) or via a WebMCP agent tool. Headless, browser-free engine (no playwright/chromium) so the same check runs locally, in CI, server-side, and in-browser.
trigger: Adding or editing Mermaid diagrams (.mmd or ```mermaid fences in .md/.mdx), wiring a pre-commit/CI Mermaid lint gate, or validating diagrams headlessly.
license: MIT
provenance:
  origin: w0m
metadata:
  version: "2026.10.26-1793055094"
---

# mmd-validate

## Overview
A broken Mermaid diagram fails silently — it renders as an error box in the browser, or nothing.
This skill validates `.mmd` files and embedded ```` ```mermaid ```` fences **deterministically and headlessly** — no browser, no
playwright, no chromium — so the same check runs in a git hook, in CI, and server-side (Node) in
the CP. A parse failure is the real cause of "won't render," so `mermaid.parse()` is the gate.

**Why not `@mermaid-js/mermaid-cli` (`mmdc`)?** It renders via puppeteer/chromium — heavy
(~150 MB browser), local-only, and can't run in a serverless CP runtime. We only need to know if a
diagram is *valid*, not to produce a PNG, so we parse instead of render.

## Engine
`mermaid.parse(text)` over a **jsdom** DOM shim (mermaid + its bundled DOMPurify need a `window`;
jsdom provides one without a browser). Auto-detects every diagram type (flowchart, sequence, ER,
class, state, gantt, …). `validate.mjs` resolves its own installed directory via
`dirname(fileURLToPath(import.meta.url))` and accepts any `--root <dir>` (default `.`) or explicit file list.

## Installing Dependencies (`mermaid` + `jsdom`)
In any project where this skill is installed (`.agents/skills/mmd-validate`), provide `mermaid` and `jsdom` via either:
1. **Skill-local one-command install (recommended for client & polyglot projects):**
   ```bash
   cd .agents/skills/mmd-validate && npm install
   ```
2. **Project `package.json` `devDependencies` (for Node/TS workspaces):**
   Add `"mermaid": "^11.14.0"` and `"jsdom": "^29.0.2"` to your project's `devDependencies` and run `npm install` / `pnpm install`.

If `jsdom` or `mermaid` is missing at runtime, `validate.mjs` fails fast (exit code `2`) and prints the exact `cd <skill-dir> && npm install` command needed to fix it.

## Usage
```bash
# one-time dependency install inside the installed skill directory
cd .agents/skills/mmd-validate && npm install

# validate specific files (this is what the git hook calls, on staged .mmd/.md/.mdx)
node .agents/skills/mmd-validate/validate.mjs path/to/a.mmd path/to/b.mmd

# validate every .mmd/.md/.mdx under a directory tree (defaults to --root .)
node .agents/skills/mmd-validate/validate.mjs --root .
```
Exit `0` = all valid; exit `1` = ≥1 invalid diagram (prints each file/fence label + the first parse-error line); exit `2` = missing `mermaid`/`jsdom` runtime dependencies.

## Git-hook & `justfile` wiring
Add a local hook to the repo's `.pre-commit-config.yaml` (no bash — invoke node directly):
```yaml
  - id: mmd-validate
    name: Validate Mermaid diagrams
    language: system
    entry: node .agents/skills/mmd-validate/validate.mjs
    files: \.mmd$
```
And in a project `justfile`:
```just
# Validate all Mermaid diagrams (.mmd and ```mermaid fences in .md/.mdx)
lint-mmd *files:
    node .agents/skills/mmd-validate/validate.mjs {{ if files == "" { "--root ." } else { files } }}
```
`pre-commit` passes the staged `.mmd` paths as args, so only changed diagrams are checked (fast).
The skill's `node_modules` must be installed once (`npm install` above).

## Where it runs (one engine, three contexts — deployed code is TypeScript-only)
The core is `mermaid.parse(text)`. Only the DOM setup differs by context:
- **Node (git hook / CI):** `mermaid.parse` + **jsdom** shim (this `validate.mjs`). Deterministic gate.
- **Browser — WebMCP agent tool (CP/app, T21):** the apps already ship `mermaid@11` client-side
  (`apps/{web,cp}`, `Mermaid.astro`), so a `validate_mermaid(source)` **WebMCP tool**
  (`navigator.modelContext`) can call the browser's own `mermaid.parse` — **no jsdom, no extra deps**,
  agent-callable, runs right in the admin CP. This is the preferred CP path (reuses the app's mermaid).
  Register it as a role-gated WebMCP tool when T21 lands; share this file's parse logic (TS).
- **Serverless edge (no DOM) — AI fallback:** where neither jsdom nor a browser mermaid is available,
  send the source to a **lightweight model** via `routeChat` (e.g. a small Cloudflare Workers AI model)
  to validate syntax + flag **semantic** issues (orphan nodes, unclear flow) a parser can't judge.
  Fuzzier; use for quality review, not as the hard gate.

**Stack rule:** deployed validation (CP edge fn / WebMCP tool) is **TypeScript only** — don't split
the deployed stack with Python. Python is for *local* skills + `justfile` automation; this validator
is TS/JS (mermaid is JS-native), which runs both locally and deployed.

## Diagram authoring convention — external-first, then source/embed
- **The canonical diagram lives in a standalone `.mmd` file** (the source of truth, git-tracked,
  independently validated). Docs/specs should **source/embed it from the file** rather than paste
  Mermaid inline — so a diagram has one home and can't drift between copies.
- The validator covers **both** forms (standalone `.mmd` + embedded ```mermaid in `.md`/`.mdx`), so
  legacy inline blocks are still gated while the codebase migrates toward external-first. Corpus at
  2026-07-15: 120 `.mmd` + 73 embedded = **193 diagrams, all valid**.

## Notes
- Prohibited in portable skills: bash. This validator is TypeScript/JS (mermaid is JS-native) + node only.
- Keep diagram source as real newlines (never escaped `\n` in one line — that fails to parse; see the
  `docs/test_fa.mmd` fix, 2026-07-15).
