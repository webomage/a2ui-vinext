#!/usr/bin/env python3
"""Offline unit and red-probe tests for scripts/live_verify_helper.py (T517 AC1, T518 AC4)."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import live_verify_helper as lvh  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(f"{label}: {detail}")


def main() -> int:
    print("T517 AC1 / T518 AC4 — live_verify_helper offline unit & red-probe suite\n")

    # 1. --help exits 0
    help_proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "live_verify_helper.py"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    check("CLI --help exits 0 and documents subcommands", help_proc.returncode == 0 and "t440" in help_proc.stdout)

    # 2. Check specs cover t440, t443, t444
    specs = lvh.build_check_specs()
    check("Declarative check registry includes t440, t443, t444", set(specs.keys()) == {"t440", "t443", "t444"})

    # 3. T440 green & red probe
    def stub_t440_green(sql: str) -> str:
        if "SET LOCAL ROLE authenticated" in sql:
            return "95|1782"
        if lvh.CASUALUSER_ID in sql:
            return "0|0|0|0|0"
        if lvh.HOST_ORG_ID in sql:
            return "95"
        return "95|1782|55|170|3"

    rc_ok, res_ok = lvh.run_suite("t440", run_sql_fn=stub_t440_green)
    check("T440 suite passes when live counts and RLS match", rc_ok == 0 and len(res_ok) == 4)

    def stub_t440_red(sql: str) -> str:
        if lvh.CASUALUSER_ID in sql:
            return "1|0|0|0|0"  # RED mutation: leftover row on old profile
        return stub_t440_green(sql)

    rc_red, _ = lvh.run_suite("t440", run_sql_fn=stub_t440_red)
    check("RED PROBE: T440 suite fails when old casualuser profile retains a contract row", rc_red == 1)

    # 4. T443 green & red probe
    def stub_t443_green(sql: str) -> str:
        if lvh.ELENA_UNIT_ID in sql and "team_members" not in sql:
            return f"Co-founder, CFO & COO|Leadership|{lvh.LEADERSHIP_ID}|20|active"
        if lvh.ALEKSEI_UNIT_ID in sql and "team_members" not in sql:
            return f"Co-founder, CEO & CTO|Leadership|{lvh.LEADERSHIP_ID}|10|active"
        if lvh.ENGINEERING_ID in sql:
            return f"Senior Fullstack Specialist (Hybrid) I|{lvh.ENGINEERING_ID}|100|open"
        return "Aleksei Tcelishchev|Elena Shatalova"

    rc_443_ok, _ = lvh.run_suite("t443", run_sql_fn=stub_t443_green)
    check("T443 suite passes when co-founder units and engineering slot match", rc_443_ok == 0)

    rc_443_red, _ = lvh.run_suite("t443", run_sql_fn=lambda _: "wrong|output")
    check("RED PROBE: T443 suite fails on mismatched unit titles/sort_order", rc_443_red == 1)

    # 5. T444 green & red probe
    valid_links = json.dumps({k: "https://example.com" for k in lvh.EXTERNAL_LINKS_REQUIRED_KEYS})

    def stub_t444_green(sql: str) -> str:
        if "SET LOCAL ROLE anon" in sql:
            return "1"
        return valid_links

    rc_444_ok, _ = lvh.run_suite("t444", run_sql_fn=stub_t444_green)
    check("T444 suite passes when external_links JSON and anon RLS read succeed", rc_444_ok == 0)

    rc_444_red, _ = lvh.run_suite("t444", run_sql_fn=lambda sql: "0" if "SET LOCAL ROLE anon" in sql else "{}")
    check("RED PROBE: T444 suite fails when external_links keys are missing or anon read returns 0", rc_444_red == 1)

    # 6. T518 AC4 crawler-smoke green & red probe
    ok_smoke, detail_smoke = lvh.run_crawler_smoke(
        worker_url="https://crawler.example.workers.dev",
        post_fn=lambda url, payload: (200, '{"queued":2}'),
    )
    check("T518 AC4: crawler-smoke passes on HTTP 200 from configurable worker URL", ok_smoke, detail_smoke)

    bad_smoke, _ = lvh.run_crawler_smoke(
        worker_url="https://crawler.example.workers.dev",
        post_fn=lambda url, payload: (500, "internal error"),
    )
    check("RED PROBE: crawler-smoke fails on non-200 status", not bad_smoke)

    # 7. T666 AC2: urllib Request carries explicit User-Agent so Cloudflare BIC never rejects with 403/1010
    from unittest import mock

    captured_headers: dict[str, str] = {}

    class _FakeResp:
        def __enter__(self) -> "_FakeResp":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def getcode(self) -> int:
            return 200

        def read(self) -> bytes:
            return b'{"queued":2}'

    def _fake_urlopen(req: object, timeout: int = 15) -> _FakeResp:
        hdrs = getattr(req, "headers", {}) or {}
        for k, v in hdrs.items():
            captured_headers[k.lower()] = str(v)
        return _FakeResp()

    with mock.patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        ua_ok, _ = lvh.run_crawler_smoke(worker_url="https://crawler.example.workers.dev")
    ua_val = captured_headers.get("user-agent", "")
    check(
        "T666 AC2: crawler-smoke sends explicit non-Python-urllib User-Agent header",
        ua_ok and bool(ua_val) and "python-urllib" not in ua_val.lower(),
        f"user-agent={ua_val!r}",
    )

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
