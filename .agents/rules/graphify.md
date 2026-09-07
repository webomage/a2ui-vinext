---
trigger: always_on
description: Consult the graphify knowledge graph at graphify-out/ for codebase and architecture questions.
---

## graphify

This project has a graphify knowledge graph at graphify-out/.
**Entrypoint for both graph tools: `docs/KNOWLEDGE-GRAPH.md` (or just run `just ask "<question>"`).**

Rules:
- For codebase or architecture questions, when `graphify-out/graph.json` exists, first run `graphify query "<question>"`. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. (There is **no graphify MCP server** — CLI only. `codegraph` is the one with an MCP.) These return a scoped subgraph, usually much smaller than `GRAPH_REPORT.md` or raw grep output.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context
- ⚠️ Do NOT rely on `graphify update .` at a repo root — it is a ~40s no-op there (T107); it never rewrites graph.json. `codegraph sync` runs per-commit and is the refresh that works.
