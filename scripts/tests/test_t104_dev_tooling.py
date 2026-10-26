#!/usr/bin/env python3
"""Regression and verification suite for T104 — Dev-tooling that silently doesn't run.

Verifies:
- AC1: `w0m-web/scripts/` and root script files (`migrate_svelte.mjs`, `apps/web/scripts/snapshot-blueprints.mjs`)
  pass `npx oxlint` with 0 errors and 0 rule suppressions in the repaired scripts.
- AC2: `oxlint` is wired in `w0m-web/.pre-commit-config.yaml` on staged JS/TS/Svelte/Astro files.
- AC3: `w0m-web/package.json` pins the `undici` override (`>=7.29.1 <8`) so `jsdom` resolves internal
  `lib/handler/wrap-handler.js` cleanly under Vitest without runner aborts.
- AC4: `w0m-web/apps/join/tsconfig.json` and `w0m-web/apps/job/tsconfig.json` declare explicit
  `include` (`src/**/*`) and `exclude` (`../cp`, `node_modules`, `dist`, `.astro`) scopes.
- AC5: All 5 workspace apps (`web`, `cp`, `demo`, `job`, `join`) are gated in `w0m-web/package.json`
  `scripts.typecheck`, and `.svelte` script blocks are gated by `svelte-typecheck-ratchet` (T278).
- AC6: `python3 scripts/discovery.py --enforce` exits 0 across all declared stacks and recipes.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "w0m-web"


def test_ac1_scripts_pass_oxlint_with_zero_errors() -> None:
    """AC1: `npx oxlint scripts migrate_svelte.mjs apps/web/scripts/snapshot-blueprints.mjs` exits 0."""
    res = subprocess.run(
        ["npx", "oxlint", "scripts", "migrate_svelte.mjs", "apps/web/scripts/snapshot-blueprints.mjs"],
        cwd=WEB,
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (res.stdout or "") + (res.stderr or "")
    assert res.returncode == 0, f"oxlint on scripts failed (exit {res.returncode}):\n{out}"
    assert "0 errors" in out, f"Expected 0 errors in oxlint output:\n{out}"

    # Verify repaired scripts were fixed cleanly, not suppressed via eslint-disable / oxlint-disable
    for rel in (
        "scripts/fix_db_data.mjs",
        "scripts/upheld-eval.mjs",
        "scripts/upload_local_to_storage.js",
        "scripts/generate_og_images.js",
        "scripts/sync_upwork_from_storage.js",
        "scripts/lint_mermaid.js",
        "migrate_svelte.mjs",
    ):
        text = (WEB / rel).read_text(encoding="utf-8")
        assert "eslint-disable" not in text and "oxlint-disable" not in text, (
            f"{rel} contains a linter disable suppression"
        )


def test_ac2_oxlint_wired_in_precommit() -> None:
    """AC2: `oxlint` hook is wired in `w0m-web/.pre-commit-config.yaml`."""
    precommit = (WEB / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "- id: oxlint" in precommit
    assert "entry: just lint-staged" in precommit
    assert r"files: \.(js|cjs|mjs|jsx|ts|tsx|svelte|astro|vue)$" in precommit


def test_ac3_undici_override_and_vitest_jsdom_resolution() -> None:
    """AC3: `undici` override is bounded `<8` for jsdom 29 and Vitest dom runner executes cleanly."""
    pkg = json.loads((WEB / "package.json").read_text(encoding="utf-8"))
    overrides = pkg.get("pnpm", {}).get("overrides", {})
    undici_range = overrides.get("undici", "")
    assert "<8" in undici_range and (">=7.29.1" in undici_range or ">=7.30.1" in undici_range), (
        f"Expected undici override '>=7.29.1 <8' or '>=7.30.1 <8', got {undici_range!r}"
    )

    res = subprocess.run(
        [
            "pnpm",
            "exec",
            "vitest",
            "run",
            "--project",
            "dom",
            "packages/authz/src/authz.spec.ts",
        ],
        cwd=WEB,
        capture_output=True,
        text=True,
        timeout=90,
    )
    out = (res.stdout or "") + (res.stderr or "")
    assert res.returncode == 0, f"Vitest dom project failed (exit {res.returncode}):\n{out}"
    assert "wrap-handler.js" not in out


def test_ac4_join_and_job_tsconfig_scopes() -> None:
    """AC4: `apps/join/tsconfig.json` and `apps/job/tsconfig.json` have explicit include/exclude boundaries."""
    for app in ("join", "job"):
        tsconfig_path = WEB / "apps" / app / "tsconfig.json"
        data = json.loads(tsconfig_path.read_text(encoding="utf-8"))
        include = data.get("include", [])
        exclude = data.get("exclude", [])
        assert "src/**/*" in include, f"apps/{app}/tsconfig.json missing 'src/**/*' in include"
        for required_excl in ("node_modules", "dist", ".astro", "../cp"):
            assert required_excl in exclude, (
                f"apps/{app}/tsconfig.json missing {required_excl!r} in exclude: {exclude!r}"
            )


def test_ac5_all_five_apps_in_typecheck_and_svelte_ratchet() -> None:
    """AC5: All 5 workspace apps are in `scripts.typecheck` and `svelte-typecheck-ratchet` baseline."""
    pkg = json.loads((WEB / "package.json").read_text(encoding="utf-8"))
    tc_script = pkg.get("scripts", {}).get("typecheck", "")
    gated_apps = set(re.findall(r"--filter\s+(\S+)\s+exec\s+astro\s+check", tc_script))
    assert gated_apps == {"cp", "demo", "job", "join", "web"}, (
        f"Expected all 5 apps in scripts.typecheck, got {sorted(gated_apps)}"
    )

    svelte_baseline = json.loads(
        (WEB / "project" / "svelte-typecheck-baseline.json").read_text(encoding="utf-8")
    )
    assert set(svelte_baseline.get("apps", {}).keys()) == {"cp", "demo", "job", "join", "web"}


def test_ac6_discovery_enforce_passes() -> None:
    """AC6: `python3 scripts/discovery.py --enforce` exits 0."""
    res = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "discovery.py"), "--enforce"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (res.stdout or "") + (res.stderr or "")
    assert res.returncode == 0, f"discovery.py --enforce failed (exit {res.returncode}):\n{out}"
    assert "stacks registry conformant" in out
