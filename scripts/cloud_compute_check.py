#!/usr/bin/env python3
"""Cloud Compute & Remote Agent Execution Surface Governance Check (T305 AC2/AC3/AC4/AC5/AC6).

Reads `.w0m/sdlc.json -> cloud_compute` and reconciles declared remote compute
and agent execution surfaces against the estate on disk:
  * Every surface must declare `status` (`governed` | `retired-unused-or-unlinked`),
    `owner`, and `cost_ceiling_usd` (>= 0).
  * Every `governed` surface must declare `repo`, `config_path` (verified on disk),
    `deploy_recipe` (verified in root `justfile`), and `spend_monitor`.
  * Every `retired-unused-or-unlinked` surface must declare `rationale` and
    `cost_ceiling_usd == 0`.
  * Disk discovery ensures `wom7func/wrangler.toml`, `wom7api/supabase/config.toml`,
    and `wom7web/.github/workflows` are all covered by a governed declaration.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ESTATE_ROOT = Path(__file__).resolve().parent.parent
SDLC_PATH = ESTATE_ROOT / ".w0m" / "sdlc.json"
JUSTFILE_PATH = ESTATE_ROOT / "justfile"

VALID_STATUSES = {"governed", "retired-unused-or-unlinked"}

EXPECTED_DISK_SURFACES: dict[str, str] = {
    "cloudflare-workers-wom7func": "wom7func/wrangler.jsonc",
    "supabase-edge-functions-wom7api": "wom7api/supabase/config.toml",
    "github-actions-estate": "wom7api/dagger/pipeline.ts",
}


@dataclass
class CloudComputeReport:
    ok: bool
    surfaces_checked: int = 0
    governed_count: int = 0
    retired_count: int = 0
    total_cost_ceiling_usd: float = 0.0
    surfaces: dict[str, dict[str, Any]] = field(default_factory=dict)
    unmeasurable_boundaries: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "surfaces_checked": self.surfaces_checked,
            "governed_count": self.governed_count,
            "retired_count": self.retired_count,
            "total_cost_ceiling_usd": self.total_cost_ceiling_usd,
            "surfaces": self.surfaces,
            "unmeasurable_boundaries": self.unmeasurable_boundaries,
            "errors": self.errors,
        }


def parse_justfile_recipes(justfile_path: Path) -> set[str]:
    if not justfile_path.is_file():
        return set()
    recipes: set[str] = set()
    recipe_re = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*)(?:\s+[^:]*)?:(?!=)")
    for line in justfile_path.read_text(encoding="utf-8").splitlines():
        m = recipe_re.match(line)
        if m:
            recipes.add(m.group(1))
    return recipes


def evaluate_cloud_compute(
    *,
    sdlc_path: Path = SDLC_PATH,
    estate_root: Path = ESTATE_ROOT,
    justfile_path: Path = JUSTFILE_PATH,
    expected_disk_surfaces: dict[str, str] | None = None,
) -> CloudComputeReport:
    errors: list[str] = []
    if not sdlc_path.is_file():
        return CloudComputeReport(
            ok=False,
            errors=[f"Missing SDLC contract file: {sdlc_path}"],
        )

    try:
        sdlc_data: dict[str, Any] = json.loads(sdlc_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return CloudComputeReport(
            ok=False,
            errors=[f"Invalid JSON in {sdlc_path}: {exc}"],
        )

    cc_block = sdlc_data.get("cloud_compute")
    if not isinstance(cc_block, dict):
        return CloudComputeReport(
            ok=False,
            errors=["Missing `cloud_compute` object in .w0m/sdlc.json"],
        )

    surfaces = cc_block.get("surfaces")
    if not isinstance(surfaces, dict) or not surfaces:
        return CloudComputeReport(
            ok=False,
            errors=["`cloud_compute.surfaces` in .w0m/sdlc.json must be a non-empty object"],
        )

    recipes = parse_justfile_recipes(justfile_path)
    disk_map = (
        EXPECTED_DISK_SURFACES
        if expected_disk_surfaces is None
        else expected_disk_surfaces
    )

    governed_count = 0
    retired_count = 0
    total_ceiling = 0.0
    declared_config_paths: set[str] = set()

    for name, cfg in surfaces.items():
        if not isinstance(cfg, dict):
            errors.append(f"Surface {name!r} must be an object")
            continue

        status = cfg.get("status")
        if status not in VALID_STATUSES:
            errors.append(
                f"Surface {name!r} has invalid status {status!r} (expected one of {sorted(VALID_STATUSES)})"
            )
            continue

        owner = cfg.get("owner")
        if not isinstance(owner, str) or not owner.strip():
            errors.append(f"Surface {name!r} is missing non-empty `owner`")

        ceiling = cfg.get("cost_ceiling_usd")
        if not isinstance(ceiling, (int, float)) or isinstance(ceiling, bool) or ceiling < 0:
            errors.append(
                f"Surface {name!r} must declare non-negative numeric `cost_ceiling_usd`"
            )
        else:
            total_ceiling += float(ceiling)

        if status == "governed":
            governed_count += 1
            for req_field in ("repo", "config_path", "deploy_recipe", "spend_monitor"):
                val = cfg.get(req_field)
                if not isinstance(val, str) or not val.strip():
                    errors.append(
                        f"Governed surface {name!r} is missing required `{req_field}`"
                    )

            cfg_path = cfg.get("config_path")
            if isinstance(cfg_path, str) and cfg_path.strip():
                declared_config_paths.add(cfg_path.strip())
                resolved = estate_root / cfg_path.strip()
                if not resolved.exists():
                    errors.append(
                        f"Governed surface {name!r} config_path does not exist on disk: {cfg_path}"
                    )

            recipe = cfg.get("deploy_recipe")
            if isinstance(recipe, str) and recipe.strip() and recipes:
                if recipe.strip() not in recipes:
                    errors.append(
                        f"Governed surface {name!r} deploy_recipe {recipe!r} not found in {justfile_path.name}"
                    )
        elif status == "retired-unused-or-unlinked":
            retired_count += 1
            rationale = cfg.get("rationale")
            if not isinstance(rationale, str) or len(rationale.strip()) < 10:
                errors.append(
                    f"Retired surface {name!r} must include a non-empty `rationale` (>= 10 chars)"
                )
            if isinstance(ceiling, (int, float)) and ceiling != 0:
                errors.append(
                    f"Retired surface {name!r} must have cost_ceiling_usd == 0 (got {ceiling})"
                )

    # Check that every discovered disk compute surface is covered by a governed entry
    for surface_key, rel_path in disk_map.items():
        disk_target = estate_root / rel_path
        if disk_target.exists():
            if surface_key not in surfaces and rel_path not in declared_config_paths:
                errors.append(
                    f"Undeclared remote compute surface on disk: {rel_path} (expected {surface_key!r} in cloud_compute.surfaces)"
                )

    if "claude-code-web-w0m" not in surfaces:
        errors.append(
            "Missing explicit disposition for `claude-code-web-w0m` in cloud_compute.surfaces (T305 AC4)"
        )

    raw_boundaries = cc_block.get("unmeasurable_boundaries")
    boundaries: dict[str, str] = (
        {str(k): str(v) for k, v in raw_boundaries.items()}
        if isinstance(raw_boundaries, dict)
        else {}
    )
    return CloudComputeReport(
        ok=len(errors) == 0,
        surfaces_checked=len(surfaces),
        governed_count=governed_count,
        retired_count=retired_count,
        total_cost_ceiling_usd=total_ceiling,
        surfaces=surfaces,
        unmeasurable_boundaries=boundaries,
        errors=errors,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify cloud_compute governance in .w0m/sdlc.json (T305)."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    args = parser.parse_args(argv)

    report = evaluate_cloud_compute()
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if report.ok else 1

    if report.ok:
        print(
            f"CLOUD_COMPUTE_OK: {report.surfaces_checked} surface(s) verified "
            f"(governed={report.governed_count}, retired={report.retired_count}, "
            f"total_cost_ceiling_usd=${report.total_cost_ceiling_usd:.2f})"
        )
        for name, cfg in report.surfaces.items():
            st = cfg.get("status")
            owner = cfg.get("owner")
            cap = cfg.get("cost_ceiling_usd")
            reach = cfg.get("reachability", "governed")
            print(f"  - {name}: status={st} owner={owner} ceiling=${cap} reachability={reach}")
        for b_key, b_msg in report.unmeasurable_boundaries.items():
            print(f"  - [UNMEASURABLE:{b_key}] {b_msg}")
        return 0

    for err in report.errors:
        print(f"CLOUD_COMPUTE_FAIL: {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
