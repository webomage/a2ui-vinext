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
ROOT = ESTATE / "w0m-web"  # w0m-web
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

    # Required subdirectories (T371 + T634 audience-separated guides/ and tech/)
    subdirs = ["inbox", "sources", "claims", "notes", "guides", "mocs", "tech", "assets", ".obsidian"]
    for sub in subdirs:
        d = target / sub
        d.mkdir(parents=True, exist_ok=True)

    today = datetime.date.today().isoformat()
    audience_default = "public" if project_id == "w0m" else "client"

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
                        {"query": "path:guides", "color": {"a": 1, "rgb": 2596065}},
                        {"query": "path:notes", "color": {"a": 1, "rgb": 5793268}},
                        {"query": "path:claims", "color": {"a": 1, "rgb": 14720619}},
                        {"query": "path:sources", "color": {"a": 1, "rgb": 15047814}},
                        {"query": "path:tech", "color": {"a": 1, "rgb": 11184895}},
                    ],
                },
                indent=2,
            )
            + "\n"
        )

    eng_id = project.get("knowledge_hub", {}).get("engagement_public_id", f"eg-{project_id}")
    org_slug = project.get("org_slug", project_id)

    # Master Map of Content (index.md)
    index_md = target / "index.md"
    if not index_md.exists():
        index_content = f"""---
id: MOC-{project_id}
title: "{project_id.capitalize()} Knowledge Base & Map of Content"
project: {project_id}
type: moc
audience: {audience_default}
created: {today}
tags: [moc, project-vault, karpathy-wiki]
---

# {project_id.capitalize()} Knowledge Base

Welcome to the **{project_id}** project knowledge base. This vault separates operational guides (`guides/`), executive Maps of Content (`mocs/`), and staff-only engineering specifications (`tech/`).

## Operational Guides & Maps of Content
- [[guides/user-guide|Operational User Guide & Daily Workflows]]
- [[guides/obsidian-sync-guide|Obsidian Desktop & Mobile Sync Guide]]
- [[mocs/architecture|System Overview & Capability Map]]
- [[mocs/requirements|Client Requirements & Scope]]
- [[mocs/deliverables|Deliverables & Milestones]]
- [[mocs/roadmap-and-progress|Live Roadmap & Progress]]

## Directory Architecture
| Directory | Audience | Purpose |
|---|---|---|
| `guides/` | `{audience_default}` | Step-by-step operational instructions and Obsidian sync onboarding |
| `mocs/` | `{audience_default}` | High-level capability overviews, requirements, and milestone summaries |
| `notes/` | `{audience_default}` | Curated domain notes and agreed decisions |
| `claims/` | `{audience_default}` | Atomic verified domain facts |
| `sources/` | `{audience_default}` | Approved briefs and stakeholder reference documents |
| `tech/` | `tech` | Staff-only engineering stack, API contracts, and delivery gates |
| `inbox/` | denied | Raw unprocessed drops (never synced to portal or R2) |
| `assets/` | `{audience_default}` | Diagrams and visual workflow guides |

## Portal, Desktop & Mobile Access
- **Client Portal Knowledge Hub**: `https://cp.webomage.com/o/{org_slug}/projects/vault`
- **Cloudflare R2 Sync Endpoint**: `https://cp.webomage.com/api/vault/r2/{eng_id}`
- **Native Desktop Obsidian** *(requires downloading the **Ready Vault (`.zip`)** and opening that folder in Obsidian first)*: `obsidian://open?vault={project_id}`
"""
        index_md.write_text(index_content)

    # Populate MOC stubs if missing
    arch_moc = target / "mocs" / "architecture.md"
    if not arch_moc.exists():
        arch_moc.write_text(f"""---
id: MOC-{project_id}-architecture
title: "{project_id.capitalize()} System Overview"
project: {project_id}
type: moc
audience: {audience_default}
created: {today}
tags: [moc, architecture]
---

# {project_id.capitalize()} System Overview

- Customer-facing capabilities, service boundaries, and operational touchpoints.
""")

    reqs_moc = target / "mocs" / "requirements.md"
    if not reqs_moc.exists():
        reqs_moc.write_text(f"""---
id: MOC-{project_id}-requirements
title: "{project_id.capitalize()} Requirements & Specifications"
project: {project_id}
type: moc
audience: {audience_default}
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
audience: {audience_default}
created: {today}
tags: [moc, deliverables]
---

# {project_id.capitalize()} Deliverables MOC

- Milestones, client sprint releases, and verified deliverables.
""")

    user_guide = target / "guides" / "user-guide.md"
    if not user_guide.exists():
        user_guide.write_text(f"""---
id: GUIDE-{project_id}-user-guide
title: "{project_id.capitalize()} Operational User Guide"
project: {project_id}
type: guide
audience: {audience_default}
created: {today}
tags: [guide, user-guide, workflows]
---

# {project_id.capitalize()} Operational User Guide

Step-by-step instructions for operating **{project_id}** day to day and collaborating in the Client Portal (`/o/{org_slug}/projects/vault`).

## Quick Navigation
- Review project milestones in [[mocs/deliverables|Deliverables & Milestones]].
- Connect Obsidian on desktop or mobile via [[guides/obsidian-sync-guide|Obsidian Sync Guide]].
""")

    obsidian_guide = target / "guides" / "obsidian-sync-guide.md"
    if not obsidian_guide.exists():
        obsidian_guide.write_text(f"""---
id: GUIDE-{project_id}-obsidian-sync
title: "Obsidian Desktop & Mobile Sync Guide ({eng_id})"
project: {project_id}
type: guide
audience: {audience_default}
created: {today}
tags: [guide, obsidian, sync, cloudflare-r2]
---

# Obsidian Desktop & Mobile Sync Guide ({eng_id})

Sync your **{project_id}** vault (`{eng_id}`) across Obsidian Desktop and Mobile using the **Webomage Vault Sync (`w0m-obsidian-sync`)** plugin and a revocable sync token (`w0m_vst_...`).

## Step 1 — Download the Ready Vault Starter `.zip`
1. Open `https://cp.webomage.com/o/{org_slug}/projects/vault` and click **Connect Obsidian**.
2. Click **Download Ready Vault (`.zip`)**, unzip it into your Obsidian folder, and open that folder as a vault in Obsidian (`obsidian://open?vault={project_id}` works once registered).

## Step 2 — Mint & Connect Your Revocable Sync Token
1. In the **Connect Obsidian** modal, mint a per-device token (`w0m_vst_...`).
2. Click **1-Click Connect (`obsidian://w0m-connect`)** or paste the Sync Endpoint (`https://cp.webomage.com/api/vault/r2/{eng_id}`) and Sync Token into **Settings → Webomage Vault Sync**.
3. Run **Sync Now** to pull the latest guides and Maps of Content.

## Audience & Security Boundaries
- **Per-Engagement Isolation:** Tokens are SHA-256 hashed at rest, revocable per device, and scoped strictly to `{eng_id}`.
- **Audience Separation:** Client sync tokens sync operational `guides/` and `mocs/`; internal `tech/` engineering runbooks remain restricted to authorized delivery staff.
""")

    tech_arch = target / "tech" / "architecture-and-stack.md"
    if not tech_arch.exists():
        tech_arch.write_text(f"""---
id: TECH-{project_id}-architecture
title: "{project_id.capitalize()} Engineering Stack & Architecture"
project: {project_id}
type: tech
audience: tech
created: {today}
tags: [tech, architecture, internal]
---

# {project_id.capitalize()} Engineering Stack & Architecture

Internal delivery reference (`audience: tech`) covering runtime topology, repository layout, bindings, and deployment verification gates for **{project_id}**.
""")

    # Place .gitkeep in empty subdirectories
    for d_name in ["inbox", "sources", "claims", "notes", "guides", "tech", "assets"]:
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
