#!/usr/bin/env python3
"""Initialize a standardized Karpathy LLM Wiki Obsidian vault for a client project (T371 AC2).

Usage:
    python3 scripts/init_project_vault.py <project-id> [--policy <path>] [--vault-dir <path>]
    just project-vault-init <project-id>
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
ESTATE = HERE.parent
ROOT = ESTATE / "wom7web"  # wom7web
DEFAULT_POLICY = ESTATE / "project" / "policies" / "clients-policy.json"


def init_vault(
    project_id: str,
    policy_file: Optional[Path] = None,
    vault_dir: Optional[Path] = None,
) -> int:
    policy_path = policy_file or DEFAULT_POLICY
    if not policy_path.is_file():
        print(f"❌ Policy file not found: {policy_path}", file=sys.stderr)
        return 1

    try:
        data = json.loads(policy_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ Failed to parse {policy_path}: {e}", file=sys.stderr)
        return 1

    projects = data.get("projects", [])
    project = next((p for p in projects if p.get("id") == project_id), None)
    if not project:
        print(f"❌ Project '{project_id}' not found in {policy_path.name}", file=sys.stderr)
        known = [p.get("id") for p in projects if "id" in p]
        print(f"   Known projects: {', '.join(sorted(known))}", file=sys.stderr)
        return 1

    # Resolve vault target directory
    if vault_dir:
        target = Path(vault_dir).resolve()
    else:
        # Default target location
        target = (ROOT / "projects" / project_id / "vault").resolve()

    target.mkdir(parents=True, exist_ok=True)

    # Required subdirectories
    subdirs = ["inbox", "sources", "claims", "notes", "mocs", "assets", ".obsidian"]
    for sub in subdirs:
        d = target / sub
        d.mkdir(parents=True, exist_ok=True)

    today = datetime.date.today().isoformat()

    # Default .obsidian/ configuration
    app_json = target / ".obsidian" / "app.json"
    if not app_json.exists():
        app_json.write_text(
            json.dumps(
                {
                    "attachmentFolderPath": "assets",
                    "livePreview": True,
                    "spellcheck": True,
                    "useMarkdownLinks": False,
                    "showLineNumber": True,
                },
                indent=2,
            )
            + "\n"
        )

    graph_json = target / ".obsidian" / "graph.json"
    if not graph_json.exists():
        graph_json.write_text(
            json.dumps(
                {
                    "collapse-filter": False,
                    "search": "",
                    "showTags": True,
                    "showAttachments": False,
                    "hideUnresolved": False,
                    "showOrphans": True,
                    "colorGroups": [
                        {"query": "path:mocs", "color": {"a": 1, "rgb": 3717112}},
                        {"query": "path:notes", "color": {"a": 1, "rgb": 5793268}},
                        {"query": "path:claims", "color": {"a": 1, "rgb": 14720619}},
                        {"query": "path:sources", "color": {"a": 1, "rgb": 15047814}},
                    ],
                },
                indent=2,
            )
            + "\n"
        )

    # Master Map of Content (index.md)
    index_md = target / "index.md"
    if not index_md.exists():
        index_content = f"""---
id: MOC-{project_id}
title: "{project_id.capitalize()} Knowledge Base & Map of Content"
project: {project_id}
type: moc
created: {today}
tags: [moc, project-vault, karpathy-wiki]
---

# {project_id.capitalize()} Knowledge Base

Welcome to the **{project_id}** project knowledge base. This vault implements the **Karpathy LLM Wiki pattern**:
every piece of intelligence has an explicit lifecycle from raw intake to verified atomic claims, synthesized domain models, and navigational Maps of Content.

## Primary Maps of Content (MOCs)
- [[mocs/architecture|System Architecture & Components]]
- [[mocs/requirements|Client Requirements & Specs]]
- [[mocs/deliverables|Deliverables & Milestones]]

## Directory Architecture
| Directory | Role | Lifecycle Stage |
|---|---|---|
| `inbox/` | Unprocessed meeting transcripts, chat dumps, agent drops | Raw & transient |
| `sources/` | Immutable client briefs, PRDs, contracts, external documentation | Immutable truth |
| `claims/` | Atomic verified facts extracted from sources | Verified claims |
| `notes/` | Synthesized system models, technical guides, decisions | Living knowledge |
| `mocs/` | Thematic navigation indices and high-level summaries | Navigation |
| `assets/` | Architecture diagrams, mockups, images | Attachments |

## Desktop & Web Access
- **Native Desktop Obsidian**: `obsidian://open?vault={target.name}`
- **Client Portal Web UI**: [cp.webomage.com](https://cp.webomage.com/client/vault)
- **Admin Control Panel**: [cp.w0m.xyz](https://cp.w0m.xyz/admin/vaults)
"""
        index_md.write_text(index_content)

    # Populate MOC stubs if missing
    arch_moc = target / "mocs" / "architecture.md"
    if not arch_moc.exists():
        arch_moc.write_text(f"""---
id: MOC-{project_id}-architecture
title: "{project_id.capitalize()} System Architecture"
project: {project_id}
type: moc
created: {today}
tags: [moc, architecture]
---

# {project_id.capitalize()} Architecture MOC

- Core stack components, API boundaries, and database models.
""")

    reqs_moc = target / "mocs" / "requirements.md"
    if not reqs_moc.exists():
        reqs_moc.write_text(f"""---
id: MOC-{project_id}-requirements
title: "{project_id.capitalize()} Requirements & Specifications"
project: {project_id}
type: moc
created: {today}
tags: [moc, requirements]
---

# {project_id.capitalize()} Requirements MOC

- Active client user stories, acceptance criteria, and project boundaries.
""")

    deliv_moc = target / "mocs" / "deliverables.md"
    if not deliv_moc.exists():
        deliv_moc.write_text(f"""---
id: MOC-{project_id}-deliverables
title: "{project_id.capitalize()} Deliverables & Milestones"
project: {project_id}
type: moc
created: {today}
tags: [moc, deliverables]
---

# {project_id.capitalize()} Deliverables MOC

- Milestones, client sprint releases, and verified deliverables.
""")

    # Place .gitkeep or READMEs in subdirectories
    for d_name in ["inbox", "sources", "claims", "notes", "assets"]:
        keep = target / d_name / ".gitkeep"
        if not keep.exists() and not any((target / d_name).iterdir()):
            keep.touch()

    print(f"✅ Initialized project vault for '{project_id}' at {target}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize standardized project Obsidian vault.")
    parser.add_argument("project_id", help="Project identifier defined in clients-policy.json")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY, help="Path to clients-policy.json")
    parser.add_argument("--vault-dir", type=Path, default=None, help="Explicit target directory for vault")
    args = parser.parse_args()

    return init_vault(args.project_id, args.policy, args.vault_dir)


if __name__ == "__main__":
    sys.exit(main())
