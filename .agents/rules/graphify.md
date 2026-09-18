---
trigger: always_on
description: Consult the graphify and code-review-graph knowledge indexes for fast codebase and architecture queries.
---

## Fast Knowledge & Code Graph Retrieval

This project maintains pre-built, high-performance AST and semantic knowledge graphs (`codegraph`, `graphify`, `code-review-graph`).
**Entrypoint for graph tools: `docs/KNOWLEDGE-GRAPH.md` (or run `just ask "<question>"`).**

Rules & Fast Query Commands:
- **Default first action before Grep:** Run `just ask "<symbols>"` to query `codegraph` across all repos + `graphify` in `wom7web`.
- **Semantic entity search:** Run `just graph-query "<query>" [repo|global]` to query graph nodes and relationships (defaults to `wom7web`, or pass `global` for all 7 estate repos).
- **Concept explanations:** Run `just graph-explain "<concept>" [repo|global]` to inspect community, degrees, and immediate incoming/outgoing edges.
- **Relationship paths:** Run `just graph-path "<A>" "<B>" [repo|global]` to find direct connection paths between symbols/concepts.
- **Blast radius & impact analysis:** Run `just graph-affected "<symbol>" [depth] [repo|global]` to inspect upstream dependents before refactoring.
- **Visual tree explorer:** Run `just graph-tree [repo|global]` to generate and open an interactive D3 v7 collapsible hierarchy view in your browser.
- **Call flow diagrams:** Run `just graph-callflow [repo]` to generate and view multi-section Mermaid callflow diagrams with zoom/pan controls.
- **AST code review graph:** Run `just crg-open [repo]` to open pre-generated D3 AST graph, or `just crg-serve [repo]` for interactive live server on `http://localhost:8765`.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review or when query/path/explain do not surface enough context.
- ⚠️ Do NOT rely on `graphify update .` at a repo root — it is a ~40s no-op there (T107); it never rewrites graph.json. `codegraph sync` runs per-commit and is the refresh that works.
