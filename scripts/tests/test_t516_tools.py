#!/usr/bin/env python3
"""Offline unit & red-probe suite for T516 Group A tools (`scripts/tests/test_t516_tools.py`).

Verifies:
1. Every T516 tool (`zeroclaw_manage.py`, `write_hygiene_docs.py`, `status_truth.py`,
   `zc_compression_measure.py`, `ds_inventory.py`, `infisical_set_prod.py`, `get_keys.py`,
   `graph_callsites.py`, `init_tinybird_schemas.py`, `ai-eval.ts`, `resume-assist-eval.ts`,
   `get_upwork_auth.ts`) responds to `--help` with exit code 0.
2. Mutating tools (`write_hygiene_docs.py`, `infisical_set_prod.py`, `init_tinybird_schemas.py`)
   default to `--dry-run` unless `--apply` is passed, and fail on red probes.
3. `get_keys.py` (`keys-verify`) prints ONLY key name, type, and SHA-256 hash — never raw key
   values (even when a synthetic API key value is injected).
4. `status_truth.py`, `graph_callsites.py`, `zc_compression_measure.py`, and `ds_inventory.py`
   pass green and fail on red probes.
"""
from __future__ import annotations

from datetime import date
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "wom7web" / "project" / "scripts"))
sys.path.insert(0, str(ROOT / "wom7api" / "scripts"))

import ds_inventory  # noqa: E402
import get_keys  # noqa: E402
import graph_callsites  # noqa: E402
import infisical_set_prod  # noqa: E402
import init_tinybird_schemas  # noqa: E402
import status_truth  # noqa: E402
import write_hygiene_docs  # noqa: E402
import zc_compression_measure  # noqa: E402


def _check(name: str, ok: bool, detail: str = "") -> bool:
    tag = "[PASS]" if ok else "[FAIL]"
    suffix = f" ({detail})" if detail else ""
    print(f"  {tag} {name}{suffix}")
    return ok


def main() -> int:
    print("T516 — Group A tools offline unit & red-probe suite\n")
    failures = 0

    # 1. --help exit 0 across Python tools
    py_tools = [
        ROOT / "scripts" / "zeroclaw_manage.py",
        ROOT / "scripts" / "write_hygiene_docs.py",
        ROOT / "scripts" / "status_truth.py",
        ROOT / "scripts" / "zc_compression_measure.py",
        ROOT / "wom7web" / "project" / "scripts" / "ds_inventory.py",
        ROOT / "scripts" / "infisical_set_prod.py",
        ROOT / "scripts" / "get_keys.py",
        ROOT / "scripts" / "graph_callsites.py",
        ROOT / "wom7api" / "scripts" / "init_tinybird_schemas.py",
    ]
    for pt in py_tools:
        proc = subprocess.run(
            [sys.executable, str(pt), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        if not _check(f"{pt.name} --help exits 0", proc.returncode == 0):
            failures += 1

    # 2. --help exit 0 across Deno / TS tools (when deno is on PATH)
    if shutil.which("deno"):
        deno_tools = [
            ROOT / "wom7api" / "scripts" / "ai-eval.ts",
            ROOT / "wom7api" / "scripts" / "resume-assist-eval.ts",
            ROOT / "wom7api" / "scripts" / "get_upwork_auth.ts",
        ]
        for dt in deno_tools:
            proc_d = subprocess.run(
                ["deno", "run", "--no-check", "--allow-env", "--allow-read", str(dt), "--help"],
                capture_output=True,
                text=True,
                check=False,
            )
            if not _check(f"{dt.name} --help exits 0", proc_d.returncode == 0):
                failures += 1

    # 3. write_hygiene_docs: --check passes on live estate + red probe on missing repo
    rc_whd_ok = write_hygiene_docs.main(["--check"])
    if not _check("write_hygiene_docs --check passes on live estate", rc_whd_ok == 0):
        failures += 1

    with tempfile.TemporaryDirectory() as tmp_whd:
        bad_pol = Path(tmp_whd) / "bad-policy.json"
        bad_pol.write_text(
            json.dumps({"repos": [{"path": "nonexistent_repo_xyz"}]}),
            encoding="utf-8",
        )
        rc_whd_bad = write_hygiene_docs.main(
            ["--check", "--estate-root", tmp_whd, "--policy", str(bad_pol)]
        )
        if not _check(
            "RED PROBE: write_hygiene_docs fails when a declared policy repo is absent on disk",
            rc_whd_bad != 0,
        ):
            failures += 1

    # 4. status_truth: offline measurement + red probe on unrankable ticket without ACs
    with tempfile.TemporaryDirectory() as tmp_st:
        tdir = Path(tmp_st)
        (tdir / "T901.md").write_text(
            '---\ntitle: "Sample Active Ticket"\nstatus: in-progress\npriority: P1\n---\n'
            "- [x] **AC1:** Done\n- [ ] **AC2:** Todo\n",
            encoding="utf-8",
        )
        (tdir / "T902.md").write_text(
            '---\ntitle: "Unrankable Ticket"\nstatus: in-progress\npriority: P2\n---\n'
            "No AC checkboxes here.\n",
            encoding="utf-8",
        )
        rows = status_truth.measure_status_truth(
            tickets_dir=tdir,
            code_repo=Path(tmp_st),
            tickets_repo=Path(tmp_st),
            today=date(2026, 10, 25),
        )
        by_id = {r["id"]: r for r in rows}
        if not _check(
            "status_truth computes AC completion percentage accurately",
            len(rows) == 2 and by_id["T901"]["pct"] == 50.0,
        ):
            failures += 1
        if not _check(
            "RED PROBE: status_truth flags in-progress ticket with 0 parseable ACs (total=0, pct=None)",
            by_id["T902"]["total"] == 0 and by_id["T902"]["pct"] is None,
        ):
            failures += 1

    # 5. zc_compression_measure: conversation generator + _ctx_values parser
    conv = zc_compression_measure.conversation(turns=3, filler_reps=2)
    ctx_vals = zc_compression_measure._ctx_values("turn 1 ctx: 1,240 / 8192\nturn 2 ctx: 980 / 8192")
    if not _check(
        "zc_compression_measure builds deterministic multi-turn prompt without trailing 'exit' and parses ctx markers",
        conv.count("Context block") == 3
        and not conv.strip().endswith("exit")
        and ctx_vals == ["1,240", "980"],
    ):
        failures += 1

    # 6. ds_inventory: read-only summary + --out writes inventory.json/inventory.md
    with tempfile.TemporaryDirectory() as tmp_ds:
        rc_ds = ds_inventory.main(["--out", tmp_ds])
        inv_json = Path(tmp_ds) / "inventory.json"
        if not _check(
            "ds_inventory writes inventory.json and inventory.md with spec & runtime component maps",
            rc_ds == 0 and inv_json.is_file() and (Path(tmp_ds) / "inventory.md").is_file(),
        ):
            failures += 1

    # 7. infisical_set_prod: dry-run default + never prints secret values + red probe on invalid env
    with tempfile.TemporaryDirectory() as tmp_inf:
        env_f = Path(tmp_inf) / "rotate.env"
        secret_sentinel = "SUPER_SECRET_SENTINEL_VALUE_DO_NOT_PRINT_999"
        env_f.write_text(f"ROTATED_TEST_KEY={secret_sentinel}\n", encoding="utf-8")

        calls_inf: list[tuple[str, str]] = []

        def fake_inf_api(
            token: str, method: str, url: str, body: dict[str, Any] | None = None
        ) -> tuple[int, str]:
            calls_inf.append((method, url))
            if method == "GET":
                return 200, json.dumps({"secrets": []})
            return 200, "{}"

        buf = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = buf
            ok_inf, stats_inf = infisical_set_prod.sync_infisical_secrets(
                env_file=env_f,
                token="fake-infisical-token",
                target_env="prod",
                apply=False,
                api_caller=fake_inf_api,
                skip_git_check=True,
            )
        finally:
            sys.stdout = old_stdout
        out_inf = buf.getvalue()
        if not _check(
            "infisical_set_prod dry-run never sends POST/PATCH and never prints secret values",
            ok_inf
            and stats_inf["created"] == 1
            and len(calls_inf) == 1
            and secret_sentinel not in out_inf,
        ):
            failures += 1

        ok_bad_env, _ = infisical_set_prod.sync_infisical_secrets(
            env_file=env_f,
            token="fake-infisical-token",
            target_env="staging-invalid",
            apply=False,
            api_caller=fake_inf_api,
            skip_git_check=True,
        )
        if not _check(
            "RED PROBE: infisical_set_prod rejects unapproved target environment",
            not ok_bad_env,
        ):
            failures += 1

    # 8. get_keys (keys-verify): prints ONLY name, type, sha256 — never plaintext key value
    raw_secret_key = "sb_secret_NEVER_PRINT_THIS_RAW_VALUE_12345"

    def fake_keys_req(url: str, headers: dict[str, str]) -> tuple[int, str]:
        return 200, json.dumps(
            [
                {"name": "anon", "type": "publishable", "api_key": "sb_publishable_demo"},
                {"name": "service_role", "type": "secret", "api_key": raw_secret_key},
            ]
        )

    ok_k, rows_k, _ = get_keys.verify_supabase_keys(
        access_token="fake-pat",
        project_ref="pqbbjgeapylcengbuvee",
        requester=fake_keys_req,
    )
    serialized_k = json.dumps(rows_k)
    if not _check(
        "get_keys (keys-verify) returns name, type, and sha256 fingerprint without plaintext key values",
        ok_k
        and len(rows_k) == 2
        and raw_secret_key not in serialized_k
        and all(r["sha256"].startswith("sha256:") for r in rows_k),
    ):
        failures += 1

    ok_k_red, _, err_k_red = get_keys.verify_supabase_keys(
        access_token="",
        requester=fake_keys_req,
    )
    if not _check(
        "RED PROBE: get_keys fails closed when SUPABASE_ACCESS_TOKEN is missing",
        not ok_k_red and "SUPABASE_ACCESS_TOKEN is not set" in err_k_red,
    ):
        failures += 1

    # 9. graph_callsites: supports --target CLI argument + red probe on missing estate root
    rc_gc = graph_callsites.main(["--target", "codegraph"])
    if not _check("graph_callsites --target codegraph exits 0", rc_gc == 0):
        failures += 1

    with tempfile.TemporaryDirectory() as empty_est:
        rc_gc_bad = graph_callsites.main(["--estate-root", empty_est])
        if not _check(
            "RED PROBE: graph_callsites exits 2 when estate root is invalid",
            rc_gc_bad == 2,
        ):
            failures += 1

    # 10. init_tinybird_schemas: dry-run default + red probe on non-HTTPS URL or missing token on --apply
    posted_tb: list[str] = []

    def fake_tb_poster(url: str, data: bytes, headers: dict[str, str]) -> tuple[int, str]:
        posted_tb.append(url)
        return 200, "{}"

    ok_tb_dry, count_tb_dry = init_tinybird_schemas.init_schemas(
        base_url="https://api.tinybird.co",
        token="",
        apply=False,
        poster=fake_tb_poster,
    )
    if not _check(
        "init_tinybird_schemas dry-run previews 3 datasources without POSTing to Tinybird",
        ok_tb_dry and count_tb_dry == 3 and len(posted_tb) == 0,
    ):
        failures += 1

    ok_tb_http, _ = init_tinybird_schemas.init_schemas(
        base_url="http://api.tinybird.co",
        token="fake-token",
        apply=True,
        poster=fake_tb_poster,
    )
    ok_tb_notok, _ = init_tinybird_schemas.init_schemas(
        base_url="https://api.tinybird.co",
        token="",
        apply=True,
        poster=fake_tb_poster,
    )
    if not _check(
        "RED PROBE: init_tinybird_schemas rejects non-https URL and missing token on --apply",
        not ok_tb_http and not ok_tb_notok,
    ):
        failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
