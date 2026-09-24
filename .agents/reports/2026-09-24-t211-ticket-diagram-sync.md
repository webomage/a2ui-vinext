# T211 Architecture Report — Ticket Diagram Co-location, GitHub Sync & Zero-Width Browser Viewer

**Ticket**: [`.tasks/T211.md`](file:///Users/proto/Projects/@self/@wom/.tasks/T211.md) · **Status**: `done` (6/6 ACs verified) · **Reality Audit**: ✅ 4/4 agree  
**Spec**: [`wom7web/openspec/changes/archive/2026-09-24-ticket-diagram-colocation-and-sync`](file:///Users/proto/Projects/@self/@wom/wom7web/openspec/changes/archive/2026-09-24-ticket-diagram-colocation-and-sync/proposal.md)  
**Commits**: Root monorepo `fb4cb17`, `wom7web` `7e69e374` & `e96c592e`

---

## 1. Problem Solved

In terminal and TUI coding agents (Orca, Claude Code CLI, AGY terminal), narrow column limits (<100 columns) truncate Mermaid diagrams into degraded ASCII art or unreadable wraps. Furthermore, generating diagrams only at the end of sessions in post-session reports risked losing them if sessions exhausted quota or disconnected mid-flight, and detached diagrams from the ticket single source of truth.

## 2. Delivered Architecture & Capabilities

```mermaid
flowchart TD
  subgraph Local [Local Estate Source of Truth]
    T[".tasks/T211.md<br/>(Ticket Spec & ACs)"]
    D1[".tasks/T211.mmd<br/>(Primary Arch Diagram)"]
    D2[".tasks/T211-arch.mmd<br/>(Sub-System Flow)"]
    T ~~~ D1
    T ~~~ D2
  end

  subgraph SyncEngine [GitHub Sync Engine]
    SG["scripts/sync_github.py<br/>(just sync-tickets)"]
    Disc["ticket_diagrams(ticket_id)<br/>Sibling Auto-Discovery"]
    Hash["projection_hash()<br/>SHA-256 Stability Gate"]
    Body["build_body()<br/>Collapsible details Fences"]
    
    SG --> Disc
    Disc --> Body
    Body --> Hash
  end

  subgraph BrowserViewer [Zero-Width Browser Viewer]
    DV["scripts/diagram_view.py<br/>(just diagram T##)"]
    HTML["/tmp/w0m-diagram-preview.html<br/>(Slate-950 Dark Theme)"]
    PanZoom["Interactive SVG Pan/Zoom<br/>(Wheel, Drag, Controls, Tabs)"]
    
    DV --> HTML
    HTML --> PanZoom
  end

  subgraph Remote [GitHub Remote Mirror]
    GH["GitHub Issues<br/>(webomage/wom7board)"]
    SVG["Native SVG Mermaid Renderer<br/>(Zero Column Limit)"]
    
    GH --> SVG
  end

  Local --> SG
  Local --> DV
  Hash -->|"Only if hash changes (AC2)"| GH
  PanZoom -->|"Default macOS Browser"| User([Developer / Agent Inspection])
  SVG -->|"Web Browser / Team"| Team([Team Collaboration])

  classDef box fill:#0f172a,stroke:#1e293b,stroke-width:1px,color:#f8fafc;
  classDef accent fill:#1e293b,stroke:#38bdf8,stroke-width:2px,color:#38bdf8;
  classDef actor fill:#020617,stroke:#94a3b8,stroke-dasharray: 4 4,color:#f8fafc;

  class T,D1,D2,SG,Disc,Hash,Body,DV,HTML,PanZoom,GH,SVG box;
  class Local,SyncEngine,BrowserViewer,Remote accent;
  class User,Team actor;
```

### Key Components

1. **Sibling Co-location (`.tasks/T{id}*.mmd`)**:
   - Tickets can carry any number of sibling diagrams named `T{id}.mmd` (primary) or `T{id}-*.mmd` (specific subsystems).
   - Co-located diagram for this ticket created at [`.tasks/T211-arch.mmd`](file:///Users/proto/Projects/@self/@wom/.tasks/T211-arch.mmd).

2. **GitHub Issue Projection (`scripts/sync_github.py`)**:
   - [`ticket_diagrams(ticket_id)`](file:///Users/proto/Projects/@self/@wom/scripts/sync_github.py#L259-L300): Discovers sibling diagrams, sorts primary `T{id}.mmd` first, and strips accidental markdown code fences.
   - [`build_body()`](file:///Users/proto/Projects/@self/@wom/scripts/sync_github.py#L302-L330): Appends diagrams in collapsible `<details open><summary>📊 {Title}</summary>` blocks with native GitHub Mermaid fences.
   - **Byte-Identical Hash Stability (AC2)**: Tickets without `.mmd` files produce byte-identical bodies and hashes (`skipped=421`, zero unwanted GitHub API calls).

3. **Zero-Width Browser Viewer (`scripts/diagram_view.py` & `just diagram`)**:
   - Compiles diagrams into standalone HTML (`/tmp/w0m-diagram-preview.html`) styled in Webomage dark theme (`slate-950` canvas `#020617`, text `#f8fafc`).
   - Full interactive pan/zoom (wheel zoom towards mouse pointer, drag to pan, keyboard shortcuts `+`/`-`/`0`, reset button).
   - Multi-diagram tab navigation when a ticket has multiple diagrams.
   - Fails closed with exit code 1 and explicit diagnostics on missing tickets or empty diagram files.

---

## 3. Verification & Quality Gates

| Gate / Suite | Command | Result |
|---|---|---|
| **Sync Regression Suite** | `just sync-tickets-test` | ✅ 59/59 checks passed |
| **Diagram Viewer Suite** | `just diagram-test` | ✅ 7/7 tests passed |
| **Ticket Schema Check** | `just ticket-schema-check` | ✅ 0 error(s) |
| **DoD Enforcement** | `just dod-check --ticket T211` | ✅ Clean DoD ownership |
| **Ticket Reality Audit** | `just ticket-audit T211` | ✅ 4/4 agree, 6/6 ACs confirmed |
| **State Consistency** | `just state-check` | ✅ Green (193 open tickets, 5 gates) |
