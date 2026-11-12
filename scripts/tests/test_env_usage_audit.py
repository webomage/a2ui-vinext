#!/usr/bin/env python3
"""Unit & zero-secret-leakage tests for scripts/env_usage_audit.py (T729 AC1)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import env_usage_audit as eua  # noqa: E402


def test_env_usage_audit_classifies_all_four_buckets_and_ignores_comments_and_dts() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        root = Path(tmp_str)
        # Runtime reader
        runtime_file = root / "w0m-web" / "apps" / "web" / "src" / "server.ts"
        runtime_file.parent.mkdir(parents=True, exist_ok=True)
        runtime_file.write_text(
            "// DEAD_COMMENTED_KEY should be ignored\n"
            "export const url = process.env.RUNTIME_ONLY_KEY;\n",
            encoding="utf-8",
        )

        # TypeScript .d.ts and inline property signature should NOT count as runtime readers
        dts_file = root / "w0m-cf" / "worker-configuration.d.ts"
        dts_file.parent.mkdir(parents=True, exist_ok=True)
        dts_file.write_text("interface Env { DTS_ONLY_KEY: string; }\n", encoding="utf-8")

        # CLI / sync script reader
        cli_file = root / "w0m-api" / "scripts" / "sync_helper.py"
        cli_file.parent.mkdir(parents=True, exist_ok=True)
        cli_file.write_text('val = os.environ.get("CLI_SYNC_KEY")\n', encoding="utf-8")

        # E2E test-only reader
        test_file = root / "w0m-web" / "tests" / "auth.spec.ts"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("const pw = process.env.E2E_ONLY_KEY;\n", encoding="utf-8")

        # Config declaration residue only -> still DEAD_UNUSED for executable code
        turbo_file = root / "w0m-web" / "turbo.json"
        turbo_file.write_text(json.dumps({"globalEnv": ["CONFIG_DEAD_KEY"]}), encoding="utf-8")

        report = eua.audit_env_keys(
            root,
            [
                "RUNTIME_ONLY_KEY",
                "CLI_SYNC_KEY",
                "E2E_ONLY_KEY",
                "CONFIG_DEAD_KEY",
                "DTS_ONLY_KEY",
                "DEAD_COMMENTED_KEY",
                "CRON_SECRET",
            ],
            repos=(".", "w0m-web", "w0m-api", "w0m-cf"),
        )
        by_key = {row["key"]: row for row in report["keys"]}
        assert by_key["RUNTIME_ONLY_KEY"]["status"] == "ACTIVE_RUNTIME"
        assert by_key["CLI_SYNC_KEY"]["status"] == "ACTIVE_CLI_OR_SYNC"
        assert by_key["E2E_ONLY_KEY"]["status"] == "TESTS_E2E_ONLY"
        assert by_key["CONFIG_DEAD_KEY"]["status"] == "DEAD_UNUSED"
        assert by_key["CONFIG_DEAD_KEY"]["config_decl_only"] == ["w0m-web/turbo.json"]
        assert by_key["DTS_ONLY_KEY"]["status"] == "DEAD_UNUSED"
        assert by_key["DEAD_COMMENTED_KEY"]["status"] == "DEAD_UNUSED"
        assert by_key["CRON_SECRET"]["status"] == "DEAD_UNUSED"
        assert "CRON_SECRET" in report["dead_historical_leak_keys"]


def test_env_usage_audit_never_emits_secret_values() -> None:
    canary_value = "ULTRA_SENSITIVE_CANARY_VALUE_DO_NOT_PRINT_84729"
    with tempfile.TemporaryDirectory() as tmp_str:
        root = Path(tmp_str)
        (root / "w0m-web" / "apps" / "me" / "src").mkdir(parents=True, exist_ok=True)
        (root / "w0m-web" / "apps" / "me" / "src" / "index.ts").write_text(
            "export const x = import.meta.env.CANARY_TEST_SECRET;\n",
            encoding="utf-8",
        )
        env = {**os.environ, "CANARY_TEST_SECRET": canary_value}
        proc_json = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "env_usage_audit.py"),
                "--root",
                str(root),
                "--key",
                "CANARY_TEST_SECRET",
                "--json",
            ],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        assert canary_value not in proc_json.stdout
        assert canary_value not in proc_json.stderr
        parsed = json.loads(proc_json.stdout)
        assert parsed["keys"][0]["status"] == "ACTIVE_RUNTIME"
