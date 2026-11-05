#!/usr/bin/env python3
"""Unit tests for scripts/retire_cf_worker_domains.py (T648)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from retire_cf_worker_domains import retire_worker_domains  # noqa: E402


class TestRetireCfWorkerDomains(unittest.TestCase):
    def test_detaches_only_matching_retired_hostnames(self) -> None:
        calls: list[tuple[str, str]] = []

        def fake_req(method: str, url: str, token: str) -> dict[str, object]:
            self.assertEqual(token, "tok-test")
            calls.append((method, url))
            if method == "GET":
                return {
                    "success": True,
                    "result": [
                        {"id": "dom-cp", "hostname": "cp.webomage.com", "service": "webomage-cp"},
                        {"id": "dom-join", "hostname": "join.webomage.com", "service": "webomage-join"},
                        {"id": "dom-job", "hostname": "job.webomage.com", "service": "webomage-job"},
                    ],
                }
            return {"success": True, "result": None}

        detached = retire_worker_domains(
            "acct-1",
            "tok-test",
            ["join.webomage.com", "job.webomage.com"],
            requester=fake_req,
        )
        self.assertEqual(
            detached,
            [
                {"id": "dom-join", "hostname": "join.webomage.com", "service": "webomage-join"},
                {"id": "dom-job", "hostname": "job.webomage.com", "service": "webomage-job"},
            ],
        )
        self.assertEqual(
            calls,
            [
                ("GET", "https://api.cloudflare.com/client/v4/accounts/acct-1/workers/domains"),
                ("DELETE", "https://api.cloudflare.com/client/v4/accounts/acct-1/workers/domains/dom-join"),
                ("DELETE", "https://api.cloudflare.com/client/v4/accounts/acct-1/workers/domains/dom-job"),
            ],
        )

    def test_dry_run_lists_matches_without_issuing_delete(self) -> None:
        calls: list[tuple[str, str]] = []

        def fake_req(method: str, url: str, _token: str) -> dict[str, object]:
            calls.append((method, url))
            return {
                "success": True,
                "result": [
                    {"id": "dom-join", "hostname": "join.webomage.com", "service": "webomage-join"},
                ],
            }

        detached = retire_worker_domains(
            "acct-1",
            "tok-test",
            ["join.webomage.com"],
            dry_run=True,
            requester=fake_req,
        )
        self.assertEqual(len(detached), 1)
        self.assertEqual(calls, [("GET", "https://api.cloudflare.com/client/v4/accounts/acct-1/workers/domains")])


if __name__ == "__main__":
    unittest.main()
