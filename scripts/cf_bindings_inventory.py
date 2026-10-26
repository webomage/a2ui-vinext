#!/usr/bin/env python3
"""T271 AC8 — Re-measurable Cloudflare Wrangler binding inventory across the w0m estate.

Scans `w0m-api/wrangler.jsonc`, `w0m-cf/wrangler.jsonc`, and `w0m-web/apps/*/wrangler.*`,
strips JSONC comments (`//` and `/* ... */`) and trailing commas safely without corrupting
URLs inside string literals, and emits either a deterministic Markdown table (default) or
`--json` report of all configured and unconfigured Cloudflare bindings.

Usage:
    python3 scripts/cf_bindings_inventory.py
    python3 scripts/cf_bindings_inventory.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ESTATE_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_WRANGLER_GLOBS: tuple[str, ...] = (
    "w0m-api/wrangler.jsonc",
    "w0m-cf/wrangler.jsonc",
    "w0m-web/apps/*/wrangler.jsonc",
    "w0m-web/apps/*/wrangler.json",
)

CATALOGUE_BINDING_KEYS: tuple[str, ...] = (
    "ai",
    "browser",
    "workflows",
    "durable_objects",
    "kv_namespaces",
    "r2_buckets",
    "services",
    "assets",
    "d1_databases",
    "hyperdrive",
    "queues",
    "vectorize",
    "images",
    "send_email",
    "turnstile",
    "analytics_engine_datasets",
    "containers",
    "pipelines",
    "mtls_certificates",
    "dispatch_namespaces",
)


def strip_jsonc(raw: str) -> str:
    """Strip // and /* */ comments and trailing commas from JSONC while preserving strings."""
    out: list[str] = []
    i = 0
    n = len(raw)
    in_str = False
    escape = False

    while i < n:
        ch = raw[i]
        if in_str:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            i += 1
            continue

        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue

        # Single-line comment
        if ch == "/" and i + 1 < n and raw[i + 1] == "/":
            i += 2
            while i < n and raw[i] not in ("\n", "\r"):
                i += 1
            continue

        # Multi-line comment
        if ch == "/" and i + 1 < n and raw[i + 1] == "*":
            i += 2
            while i + 1 < n and not (raw[i] == "*" and raw[i + 1] == "/"):
                if raw[i] == "\n":
                    out.append("\n")
                i += 1
            i += 2
            continue

        out.append(ch)
        i += 1

    cleaned = "".join(out)
    # Remove trailing commas before } or ] (outside strings; string contents have no raw }, ] after comma issues
    # if we match `,` followed only by whitespace and `}` or `]`, but let's do a token-aware pass).
    return _strip_trailing_commas(cleaned)


def _strip_trailing_commas(text: str) -> str:
    """Remove trailing commas before closing `}` or `]` outside string literals."""
    result: list[str] = []
    i = 0
    n = len(text)
    in_str = False
    escape = False

    while i < n:
        ch = text[i]
        if in_str:
            result.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            i += 1
            continue

        if ch == '"':
            in_str = True
            result.append(ch)
            i += 1
            continue

        if ch == ",":
            j = i + 1
            while j < n and text[j] in (" ", "\t", "\r", "\n"):
                j += 1
            if j < n and text[j] in ("}", "]"):
                i += 1
                continue

        result.append(ch)
        i += 1

    return "".join(result)


def parse_wrangler_config(path: Path, root: Path = ESTATE_ROOT) -> dict[str, Any]:
    """Parse a single wrangler.jsonc / wrangler.json file and summarize its bindings."""
    raw = path.read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(strip_jsonc(raw))
    rel_path = str(path.resolve().relative_to(root.resolve()))

    bindings: dict[str, list[str]] = {}

    # 1. Single-object bindings (ai, browser, assets, images)
    for single_key in ("ai", "browser", "assets", "images"):
        val = data.get(single_key)
        if isinstance(val, dict) and val:
            bname = val.get("binding") or val.get("directory") or single_key
            bindings[single_key] = [str(bname)]

    # 2. Array bindings (workflows, kv_namespaces, r2_buckets, services, d1_databases, hyperdrive, etc.)
    for list_key in (
        "workflows",
        "kv_namespaces",
        "r2_buckets",
        "services",
        "d1_databases",
        "hyperdrive",
        "vectorize",
        "send_email",
        "turnstile",
        "analytics_engine_datasets",
        "containers",
        "pipelines",
        "mtls_certificates",
        "dispatch_namespaces",
    ):
        val = data.get(list_key)
        if isinstance(val, list) and val:
            items: list[str] = []
            for entry in val:
                if isinstance(entry, dict):
                    label = (
                        entry.get("binding")
                        or entry.get("name")
                        or entry.get("bucket_name")
                        or entry.get("service")
                        or "unnamed"
                    )
                    target = (
                        entry.get("service")
                        or entry.get("bucket_name")
                        or entry.get("class_name")
                        or entry.get("id")
                    )
                    if target and target != label:
                        items.append(f"{label}->{target}")
                    else:
                        items.append(str(label))
            bindings[list_key] = items

    # 3. Durable Objects (`durable_objects.bindings`)
    do_val = data.get("durable_objects")
    if isinstance(do_val, dict):
        do_bindings = do_val.get("bindings", [])
        if isinstance(do_bindings, list) and do_bindings:
            bindings["durable_objects"] = [
                f"{b.get('name', 'DO')}->{b.get('class_name', '')}"
                for b in do_bindings
                if isinstance(b, dict)
            ]

    # 4. Queues (`queues.producers` / `queues.consumers`)
    q_val = data.get("queues")
    if isinstance(q_val, dict):
        producers = q_val.get("producers", []) or []
        consumers = q_val.get("consumers", []) or []
        q_items = [
            f"producer:{p.get('binding') or p.get('queue')}"
            for p in producers
            if isinstance(p, dict)
        ] + [
            f"consumer:{c.get('queue')}"
            for c in consumers
            if isinstance(c, dict)
        ]
        if q_items:
            bindings["queues"] = q_items

    # 5. Triggers / Crons
    triggers = data.get("triggers")
    crons: list[str] = []
    if isinstance(triggers, dict) and isinstance(triggers.get("crons"), list):
        crons = [str(c) for c in triggers["crons"]]

    # 6. Routes
    routes_val = data.get("routes")
    routes: list[str] = []
    if isinstance(routes_val, list):
        for r in routes_val:
            if isinstance(r, dict) and r.get("pattern"):
                routes.append(str(r["pattern"]))
            elif isinstance(r, str):
                routes.append(r)

    obs = data.get("observability")
    observability_enabled = bool(isinstance(obs, dict) and obs.get("enabled") is True)
    upload_source_maps = bool(data.get("upload_source_maps") is True)

    return {
        "config_path": rel_path,
        "worker_name": data.get("name", path.parent.name),
        "compatibility_date": data.get("compatibility_date", ""),
        "observability": observability_enabled,
        "upload_source_maps": upload_source_maps,
        "crons": crons,
        "routes": routes,
        "bindings": bindings,
    }


def discover_wrangler_configs(root: Path = ESTATE_ROOT) -> list[Path]:
    """Return sorted list of wrangler config files across the estate."""
    found: set[Path] = set()
    for pattern in DEFAULT_WRANGLER_GLOBS:
        for p in root.glob(pattern):
            if p.is_file():
                found.add(p.resolve())
    return sorted(found, key=lambda p: str(p.relative_to(root.resolve())))


def build_estate_inventory(root: Path = ESTATE_ROOT) -> dict[str, Any]:
    """Scan all wrangler configs and compute per-worker and estate-wide binding summaries."""
    configs = [parse_wrangler_config(p, root=root) for p in discover_wrangler_configs(root)]

    active_by_type: dict[str, list[str]] = {}
    for cfg in configs:
        wname = cfg["worker_name"]
        for btype, items in cfg["bindings"].items():
            active_by_type.setdefault(btype, []).extend(f"{wname}:{item}" for item in items)

    unconfigured_types = [
        k for k in CATALOGUE_BINDING_KEYS if k not in active_by_type
    ]

    total_crons = sum(len(c["crons"]) for c in configs)

    return {
        "config_count": len(configs),
        "total_cron_triggers": total_crons,
        "workers": configs,
        "active_bindings_by_type": active_by_type,
        "unconfigured_binding_types": unconfigured_types,
    }


def format_markdown_table(inventory: dict[str, Any]) -> str:
    """Format the inventory as a deterministic Markdown report."""
    lines: list[str] = [
        "# Cloudflare Wrangler Binding Inventory (`T271` AC8)",
        "",
        f"- **Configs scanned:** `{inventory['config_count']}`",
        f"- **Account cron triggers used:** `{inventory['total_cron_triggers']} / 5` (Workers Free cap)",
        "",
        "| Config Path | Worker Name | Bindings Summary | Crons | Observability | Routes |",
        "|---|---|---|---|---|---|",
    ]
    for w in inventory["workers"]:
        b_parts: list[str] = []
        for btype, items in sorted(w["bindings"].items()):
            if btype == "workflows":
                b_parts.append(f"`workflows` ({len(items)})")
            else:
                b_parts.append(f"`{btype}`: {', '.join(items)}")
        b_summary = "; ".join(b_parts) if b_parts else "—"
        cron_summary = f"`{len(w['crons'])}` ({', '.join(w['crons'])})" if w["crons"] else "`0`"
        obs_summary = "on" if w["observability"] else "off"
        route_summary = ", ".join(f"`{r}`" for r in w["routes"]) if w["routes"] else "—"
        lines.append(
            f"| `{w['config_path']}` | `{w['worker_name']}` | {b_summary} | {cron_summary} | {obs_summary} | {route_summary} |"
        )

    lines.extend(
        [
            "",
            "## Declared in Zero Wrangler Configs",
            "",
            ", ".join(f"`{k}`" for k in inventory["unconfigured_binding_types"]),
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit deterministic JSON instead of Markdown table.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ESTATE_ROOT,
        help="Estate root directory to scan.",
    )
    args = parser.parse_args(argv)

    inventory = build_estate_inventory(args.root)
    if args.json:
        print(json.dumps(inventory, indent=2, sort_keys=True))
    else:
        print(format_markdown_table(inventory))
    return 0


if __name__ == "__main__":
    sys.exit(main())
