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
sys.path.insert(0, str(ROOT / "w0m-web" / "project" / "scripts"))
sys.path.insert(0, str(ROOT / "w0m-api" / "scripts"))

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
        ROOT / "w0m-web" / "project" / "scripts" / "ds_inventory.py",
        ROOT / "scripts" / "infisical_set_prod.py",
        ROOT / "scripts" / "get_keys.py",
        ROOT / "scripts" / "graph_callsites.py",
        ROOT / "w0m-api" / "scripts" / "init_tinybird_schemas.py",
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
            ROOT / "w0m-api" / "scripts" / "ai-eval.ts",
            ROOT / "w0m-api" / "scripts" / "resume-assist-eval.ts",
            ROOT / "w0m-api" / "scripts" / "get_upwork_auth.ts",
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

    # 10. init_tinybird_schemas: dry-run default (8 datasources + 6 pipes), check mode, token redaction, and red probes
    posted_tb: list[tuple[str, str]] = []

    def fake_tb_poster(url: str, data: bytes, headers: dict[str, str]) -> tuple[int, str]:
        posted_tb.append((url, data.decode("utf-8")))
        return 200, "{}"

    ok_tb_dry, count_tb_dry = init_tinybird_schemas.init_schemas(
        base_url=init_tinybird_schemas.DEFAULT_TINYBIRD_URL,
        token="",
        apply=False,
        poster=fake_tb_poster,
    )
    if not _check(
        "init_tinybird_schemas dry-run previews 8 NDJSON datasources + 6 pipes without POSTing to Tinybird",
        ok_tb_dry and count_tb_dry == 8 and len(init_tinybird_schemas.PIPES) == 6 and len(posted_tb) == 0,
    ):
        failures += 1

    ok_tb_rest, count_tb_rest = init_tinybird_schemas.init_schemas(
        base_url=init_tinybird_schemas.DEFAULT_TINYBIRD_URL,
        token="fake-token",
        apply=True,
        poster=fake_tb_poster,
        use_forward=False,
    )
    if not _check(
        "init_tinybird_schemas REST fallback POSTs all 8 NDJSON datasources with engine_ttl on observability_logs",
        ok_tb_rest
        and count_tb_rest == 8
        and len(posted_tb) == 8
        and all("format=ndjson" in body for _, body in posted_tb)
        and any("name=observability_logs" in body and "engine_ttl=" in body for _, body in posted_tb),
    ):
        failures += 1

    tb_probe_marker = "unit-test-marker-" + ("x" * 12)

    def fake_tb_getter(url: str, headers: dict[str, str]) -> tuple[int, str]:
        if "/v0/datasources" in url:
            return 200, json.dumps({"datasources": [{"name": d["name"]} for d in init_tinybird_schemas.DATASOURCES]})
        return 200, json.dumps({"pipes": [{"name": p["name"], "type": "endpoint"} for p in init_tinybird_schemas.PIPES]})

    ok_tb_chk, summary_tb_chk = init_tinybird_schemas.check_live_schemas(
        base_url=init_tinybird_schemas.DEFAULT_TINYBIRD_URL,
        token=tb_probe_marker,
        getter=fake_tb_getter,
        run_forward_check=False,
    )
    redacted_sample = init_tinybird_schemas._redact_secret(f"header: {tb_probe_marker}", tb_probe_marker)
    if not _check(
        "init_tinybird_schemas check_live_schemas verifies all 8 datasources + 6 pipes and redacts tokens",
        ok_tb_chk
        and summary_tb_chk["missing_datasources"] == []
        and summary_tb_chk["missing_endpoint_pipes"] == []
        and tb_probe_marker not in redacted_sample,
    ):
        failures += 1

    ok_tb_http, _ = init_tinybird_schemas.init_schemas(
        base_url="http://api.northamerica-northeast2.gcp.tinybird.co",
        token="fake-token",
        apply=True,
        poster=fake_tb_poster,
        use_forward=False,
    )
    ok_tb_notok, _ = init_tinybird_schemas.init_schemas(
        base_url=init_tinybird_schemas.DEFAULT_TINYBIRD_URL,
        token="",
        apply=True,
        poster=fake_tb_poster,
        use_forward=False,
    )
    if not _check(
        "RED PROBE: init_tinybird_schemas rejects non-https URL and missing token on --apply",
        not ok_tb_http and not ok_tb_notok,
    ):
        failures += 1

    # 11. resource_monitor (T343 AC1-AC4): audit subsystems, 10% free-disk threshold guard, and AC4 unmanaged VM protection
    import resource_monitor

    disk_ok = resource_monitor.check_host_disk_headroom(usage_override=(1000, 500, 500))
    disk_low = resource_monitor.check_host_disk_headroom(usage_override=(1000, 950, 50))
    if not _check(
        "T343 AC3: check_host_disk_headroom triggers low_disk_warning below 10% threshold",
        disk_ok["low_disk_warning"] is False
        and disk_low["low_disk_warning"] is True
        and "LOW DISK WARNING" in disk_low["headline"],
    ):
        failures += 1

    prune_dry = resource_monitor.prune_resources(apply=False)
    if not _check(
        "T343 AC2: prune_resources defaults to dry_run=True and lists protected unmanaged VMs",
        prune_dry["ok"] is True
        and prune_dry["dry_run"] is True
        and "evercred" in prune_dry["protected_unmanaged_vms"],
    ):
        failures += 1

    unmanaged_refused = False
    try:
        resource_monitor.prune_resources(apply=True, target_vm="evercred")
    except PermissionError:
        unmanaged_refused = True
    if not _check(
        "RED PROBE (T343 AC4): prune_resources refuses to touch unmanaged VM 'evercred'",
        unmanaged_refused,
    ):
        failures += 1

    # 12. tart_sandbox.verify_host_substrates (T368 AC5) + GUI workstation profile (T181 AC1-AC8)
    import tart_sandbox

    substrates = tart_sandbox.verify_host_substrates()
    if not _check(
        "T368 AC5: verify_host_substrates reports apple_container, tart, disk_budget, and 8 routing tiers",
        "apple_container" in substrates
        and "tart" in substrates
        and "disk_budget" in substrates
        and substrates.get("routing_tiers") == 8,
    ):
        failures += 1

    gui_cmd = tart_sandbox.build_gui_workstation_command("w0m-gui-linux", guest_os="linux", vnc=True)
    if not _check(
        "T181 AC1/AC5: GUI workstation profile is distinct from agent sandbox (keeps clipboard & display, uses --vnc)",
        "--no-clipboard" not in gui_cmd
        and "--no-graphics" not in gui_cmd
        and "--vnc" in gui_cmd
        and tart_sandbox.AGENT_SANDBOX_PROFILE["clipboard"] is False
        and tart_sandbox.GUI_WORKSTATION_PROFILE["clipboard"] is True,
    ):
        failures += 1

    quota_blocked = False
    try:
        tart_sandbox.build_gui_workstation_command("w0m-gui-macos", guest_os="macos", active_macos_vms=2)
    except RuntimeError:
        quota_blocked = True
    evercred_blocked = False
    try:
        tart_sandbox.build_gui_workstation_command("evercred")
    except PermissionError:
        evercred_blocked = True
    clone_blocked = False
    try:
        tart_sandbox.build_gui_workstation_command("w0m-gui-linux", cloning_signed_in_session=True)
    except PermissionError:
        clone_blocked = True
    if not _check(
        "RED PROBE (T181 AC4/AC6/AC8): enforces 2-VM macOS quota, forbids cloning signed-in sessions, and protects 'evercred'",
        quota_blocked and evercred_blocked and clone_blocked,
    ):
        failures += 1

    # 13. T179 AC1-AC4: DevPod Tart provider 7-verb lifecycle & macOS rejection
    devpod_res = tart_sandbox.verify_devpod_tart_provider_lifecycle()
    if not _check(
        "T179 AC1-AC4: verify_devpod_tart_provider_lifecycle exercises all 7 verbs, stdio agent pipe, and macOS rejection",
        bool(devpod_res.get("ok"))
        and devpod_res.get("lifecycle_states") == ["Running", "Stopped", "Running", "NotFound"],
    ):
        failures += 1

    # 14. T180 AC3/AC4: Egress CIDR red-probe & deny-by-default sandbox command
    egress_res = tart_sandbox.probe_egress(["10.0.0.0/8", "192.168.64.0/24"], probe_blocked_ip="1.1.1.1")
    sbx_cmd = tart_sandbox.build_tart_run_command("w0m-agent-sandbox")
    if not _check(
        "T180 AC3/AC4: probe_egress blocks 1.1.1.1 outside CIDR allowlist and build_tart_run_command defaults to --no-clipboard --no-audio --net-host",
        bool(egress_res.get("ok"))
        and "--no-clipboard" in sbx_cmd
        and "--no-audio" in sbx_cmd
        and "--net-host" in sbx_cmd,
    ):
        failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
