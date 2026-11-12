#!/usr/bin/env python3
"""Fail-closed Infisical dead-environment-variable prune helper (T730 AC1).

Security & Operational Invariants:
- NEVER reads, hashes, logs, or prints any secret value (`os.environ[k]` / `os.getenv(k)`).
- Cross-validates every candidate key against `scripts/env_usage_audit.py`: a key is eligible
  for deletion ONLY if `status == "DEAD_UNUSED"` (`0` executable runtime, CLI/sync, or test readers).
- Runs in `dry-run` mode by default; mutates Infisical ONLY when the human operator explicitly passes `--apply`.
- Fails closed (`ValueError` / exit `1`) if `--key` names any variable that still has `>= 1` executable reader.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from env_usage_audit import (  # noqa: E402
    DEFAULT_ESTATE_REPOS,
    DEFAULT_INFISICAL_PROJECT_ID,
    HISTORICAL_DIGEST_LEAK_KEYS,
    audit_env_keys,
    discover_infisical_key_names,
    discover_static_candidate_keys,
)


def classify_dead_key_group(key: str) -> str:
    if key in HISTORICAL_DIGEST_LEAK_KEYS:
        return "historical_leak_dead"
    if key.startswith(("SIGNOZ_", "PUBLIC_SIGNOZ_", "POSTHOG_PROJECT_", "PUBLIC_POSTHOG_", "HONEYCOMB_MANAGEMENT_")):
        return "retired_observability"
    if key.startswith("OCI_"):
        return "retired_oci_provisioning"
    if key in {
        "COHERE_API_KEY",
        "GROQ_API_KEY",
        "HATCHET_CLIENT_TOKEN",
        "HUGGINGFACE_API_TOKEN",
        "MISTRAL_TEST_MODEL",
        "GEMINI_TEST_MODEL",
        "CF_RUNTIME_API_TOKEN",
        "OPIK_API_KEY",
    }:
        return "retired_ai_or_queue"
    return "retired_qa_demo_or_metadata"


def prune_dead_infisical_keys(
    root: Path,
    candidate_keys: Sequence[str],
    explicit_targets: Sequence[str] | None = None,
    repos: Sequence[str] = DEFAULT_ESTATE_REPOS,
    infisical_env: str = "beta",
    project_id: str = DEFAULT_INFISICAL_PROJECT_ID,
    apply: bool = False,
) -> dict[str, Any]:
    report = audit_env_keys(root, candidate_keys, repos=repos)
    by_key = {row["key"]: row for row in report["keys"]}

    if explicit_targets:
        requested = sorted({k.strip() for k in explicit_targets if k and k.strip()})
        unsafe = [k for k in requested if by_key.get(k, {}).get("status") != "DEAD_UNUSED"]
        if unsafe:
            details = ", ".join(
                f"{k} ({by_key.get(k, {}).get('status', 'UNAUDITED')})" for k in unsafe
            )
            raise ValueError(
                f"Refusing to prune active/non-dead environment variable(s): {details}"
            )
        dead_keys = requested
    else:
        dead_keys = sorted(
            row["key"] for row in report["keys"] if row["status"] == "DEAD_UNUSED"
        )

    protected_active = sorted(
        row["key"] for row in report["keys"] if row["status"] != "DEAD_UNUSED"
    )

    groups: dict[str, list[str]] = {}
    for key in dead_keys:
        grp = classify_dead_key_group(key)
        groups.setdefault(grp, []).append(key)

    deleted_keys: list[str] = []
    if apply:
        for key in dead_keys:
            subprocess.run(
                [
                    "infisical",
                    "secrets",
                    "delete",
                    key,
                    f"--env={infisical_env}",
                    f"--projectId={project_id}",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            deleted_keys.append(key)

    return {
        "mode": "applied" if apply else "dry-run",
        "infisical_env": infisical_env,
        "project_id": project_id,
        "total_audited": report["total_keys"],
        "dead_count": len(dead_keys),
        "dead_keys": dead_keys,
        "deleted_keys": deleted_keys,
        "protected_active_count": len(protected_active),
        "protected_active_keys": protected_active,
        "groups": groups,
    }


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Estate root path",
    )
    ap.add_argument(
        "--infisical",
        action="store_true",
        help="Discover candidate key names live from Infisical (key names only)",
    )
    ap.add_argument(
        "--infisical-env",
        default="beta",
        help="Infisical environment slug (default: beta)",
    )
    ap.add_argument(
        "--project-id",
        default=DEFAULT_INFISICAL_PROJECT_ID,
        help="Infisical project ID",
    )
    ap.add_argument(
        "--key",
        action="append",
        default=[],
        help="Restrict prune to specific key name(s) (fails closed if any still has readers)",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Owner-only: execute `infisical secrets delete` on verified DEAD_UNUSED keys",
    )
    ap.add_argument("--json", action="store_true", help="Emit JSON summary")
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()

    if args.infisical:
        candidates = discover_infisical_key_names(
            root,
            project_id=args.project_id,
            infisical_env=args.infisical_env,
        )
    else:
        candidates = discover_static_candidate_keys(root)

    if args.key:
        candidates = sorted(set(candidates) | {k.strip() for k in args.key if k.strip()})

    try:
        summary = prune_dead_infisical_keys(
            root=root,
            candidate_keys=candidates,
            explicit_targets=args.key or None,
            infisical_env=args.infisical_env,
            project_id=args.project_id,
            apply=args.apply,
        )
    except ValueError as exc:
        print(f"[FAIL] env-prune-dead: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    mode_banner = "APPLIED" if args.apply else "DRY-RUN"
    print(
        f"[{mode_banner}] env-prune-dead ({summary['infisical_env']}): "
        f"{summary['dead_count']} DEAD_UNUSED key(s) eligible "
        f"({summary['protected_active_count']} active key(s) protected)"
    )
    for grp, items in sorted(summary["groups"].items()):
        print(f"  - {grp} ({len(items)}): {', '.join(items)}")
    if not args.apply and summary["dead_keys"]:
        print("  -> Pass `--infisical --apply` from an owner terminal to delete these dead keys.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
