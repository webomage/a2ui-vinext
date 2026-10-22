---
description: "Execute opsx lifecycle gate in OpenCode (generated from .w0m/skills.json)"
---

# OpenSpec (`opsx`) Command Bridge for OpenCode (`T152` AC4 / AC5c)

Generated from `.w0m/skills.json` and `wom7web/openspec/SPEC-AUTHORING-STANDARD.md`.

1. Load authoring standard: `wom7web/openspec/SPEC-AUTHORING-STANDARD.md`
2. Validate change strictly: `cd wom7web && pnpm exec openspec validate $ARGUMENTS --type change --strict`
3. Invoke skill when needed: `skill({ name: "w0m-sdlc-spec" })`
