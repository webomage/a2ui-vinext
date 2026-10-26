#!/usr/bin/env python3
"""Offline unit & red-probe suite for `scripts/upwork_poller_status.py` (T517 AC5)."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import upwork_poller_status as ups  # noqa: E402


def _check(name: str, ok: bool, detail: str = "") -> bool:
    tag = "[PASS]" if ok else "[FAIL]"
    suffix = f" ({detail})" if detail else ""
    print(f"  {tag} {name}{suffix}")
    return ok


def main() -> int:
    print("T517 AC5 — upwork_poller_status offline unit & red-probe suite\n")
    failures = 0

    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "upwork_poller_status.py"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    if not _check(
        "CLI --help exits 0 and exposes --prefix / --limit / --json",
        proc.returncode == 0 and "--prefix" in proc.stdout and "--limit" in proc.stdout,
    ):
        failures += 1

    # Green probe
    def fake_ok(
        method: str, url: str, headers: dict[str, str], body: bytes | None
    ) -> tuple[int, str]:
        if "/rest/v1/upwork_poller_state" in url:
            return 200, json.dumps([{"id": "upwork-main", "last_status": "ok"}])
        if "/storage/v1/object/list/upwork" in url:
            return 200, json.dumps([{"name": "contract-alpha"}, {"name": "contract-beta"}])
        return 404, "{}"

    ok_g, res_g = ups.fetch_poller_status(
        supabase_url="https://example.supabase.co",
        service_key="fake-service-role-key",
        prefix="contracts",
        limit=10,
        requester=fake_ok,
    )
    if not _check(
        "fetch_poller_status returns poller_state and storage_objects without hardcoded contract path",
        ok_g
        and len(res_g.get("poller_state", [])) == 1
        and res_g.get("storage_objects") == ["contract-alpha", "contract-beta"],
    ):
        failures += 1

    # Red probe 1: missing service key
    ok_r1, res_r1 = ups.fetch_poller_status(
        supabase_url="https://example.supabase.co",
        service_key="",
        requester=fake_ok,
    )
    if not _check(
        "RED PROBE: fetch_poller_status fails when SUPABASE_SERVICE_ROLE_KEY is missing",
        not ok_r1 and "Missing SUPABASE_SERVICE_ROLE_KEY" in str(res_r1.get("error", "")),
    ):
        failures += 1

    # Red probe 2: HTTP 500 on poller state
    def fake_err(
        method: str, url: str, headers: dict[str, str], body: bytes | None
    ) -> tuple[int, str]:
        return 500, "internal error"

    ok_r2, res_r2 = ups.fetch_poller_status(
        supabase_url="https://example.supabase.co",
        service_key="fake-service-role-key",
        requester=fake_err,
    )
    if not _check(
        "RED PROBE: fetch_poller_status fails when upwork_poller_state returns HTTP 500",
        not ok_r2 and "HTTP 500" in str(res_r2.get("error", "")),
    ):
        failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
