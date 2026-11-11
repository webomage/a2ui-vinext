#!/usr/bin/env python3
"""Regression tests for T720 — w0m-api Deno lockfile parity & frozen-lockfile enforcement."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "w0m-api"
SCRIPT_PATH = API_ROOT / "scripts" / "deno_lock_parity_check.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("deno_lock_parity_check", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _seed_api_fixture(tmp_path: Path, *, pkg_version: str) -> Path:
    api = tmp_path / "w0m-api"
    fn_dir = api / "supabase" / "functions"
    fn_dir.mkdir(parents=True, exist_ok=True)

    (api / "package.json").write_text(
        json.dumps(
            {
                "name": "fixture-api",
                "version": "1.0.0",
                "dependencies": {
                    "@hono/zod-validator": "^0.7.6",
                    "@tinybirdco/sdk": "^0.0.76",
                    "fast-xml-parser": pkg_version,
                },
                "devDependencies": {
                    "oxlint": "1.74.0",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    (api / "deno.lock").write_text(
        json.dumps(
            {
                "version": "5",
                "specifiers": {
                    "jsr:@std/assert@1.0.11": "1.0.11",
                    "npm:fast-xml-parser@^5.10.1": "5.10.1",
                },
                "jsr": {
                    "@std/assert@1.0.11": {
                        "integrity": "2461ef3c368fe88bc60e186e7744a93112f16fd110022e113a0849e94d1c83c1",
                    }
                },
                "workspace": {
                    "packageJson": {
                        "dependencies": [
                            "npm:@hono/zod-validator@~0.7.6",
                            "npm:@tinybirdco/sdk@^0.0.76",
                            "npm:fast-xml-parser@^5.10.1",
                            "npm:oxlint@1.74.0",
                        ]
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    (fn_dir / "deno.json").write_text(
        json.dumps({"imports": {}}, indent=2) + "\n",
        encoding="utf-8",
    )
    (fn_dir / "deno.lock").write_text(
        json.dumps({"version": "5"}, indent=2) + "\n",
        encoding="utf-8",
    )
    return api


def test_clean_fixture_passes_without_mutation(tmp_path: Path) -> None:
    mod = _load_module()
    api = _seed_api_fixture(tmp_path, pkg_version="^5.10.1")
    before = (api / "deno.lock").read_bytes()

    res = mod.check_or_sync(api, sync=False)
    assert res.ok is True
    assert res.pkg_dep_count == 4
    assert res.functions_lock_checked is True
    assert res.changed_root_lock is False
    assert (api / "deno.lock").read_bytes() == before


def test_drifted_package_json_fails_red_without_mutating_lockfile(tmp_path: Path) -> None:
    mod = _load_module()
    api = _seed_api_fixture(tmp_path, pkg_version="^5.12.0")
    before = (api / "deno.lock").read_bytes()

    res = mod.check_or_sync(api, sync=False)
    assert res.ok is False
    assert any("fast-xml-parser" in err for err in res.errors)
    assert (api / "deno.lock").read_bytes() == before, "check mode must never mutate deno.lock"


def test_sync_reconciles_workspace_deps_without_pruning_unrelated_specifiers(tmp_path: Path) -> None:
    mod = _load_module()
    api = _seed_api_fixture(tmp_path, pkg_version="^5.12.0")

    sync_res = mod.check_or_sync(api, sync=True)
    assert sync_res.ok is True
    assert sync_res.changed_root_lock is True

    updated = json.loads((api / "deno.lock").read_text(encoding="utf-8"))
    assert "npm:fast-xml-parser@^5.12.0" in updated["workspace"]["packageJson"]["dependencies"]
    assert "npm:fast-xml-parser@^5.10.1" not in updated["specifiers"]
    assert updated["specifiers"].get("jsr:@std/assert@1.0.11") == "1.0.11"

    recheck = mod.check_or_sync(api, sync=False)
    assert recheck.ok is True
    assert recheck.changed_root_lock is False


def test_live_estate_wiring_and_frozen_flags() -> None:
    mod = _load_module()
    live_res = mod.check_or_sync(API_ROOT, sync=False)
    assert live_res.ok is True, f"live w0m-api deno.lock parity failed: {live_res.errors}"

    estate_just = (ROOT / "just" / "estate.just").read_text(encoding="utf-8")
    assert "deno check --frozen=true */index.ts" in estate_just
    assert 'deno test --frozen=true --allow-env "${suites[@]}"' in estate_just
    assert "deno-lock-parity:" in estate_just
    assert "deno-lock-sync:" in estate_just

    api_precommit = (API_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "deno check --frozen=true --config supabase/functions/deno.json" in api_precommit
    assert "id: deno-lock-parity" in api_precommit
    assert "just deno-lock-parity" in api_precommit


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
