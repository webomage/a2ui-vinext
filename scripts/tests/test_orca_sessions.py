#!/usr/bin/env python3
"""T596 AC4 — Unit tests for multi-host Orca instance and agent session orchestration (`scripts/orca_sessions.py`)."""

from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import orca_sessions as osess  # noqa: E402


def _make_sample_snapshot(host: str = "local") -> dict[str, Any]:
    return {
        "host": host,
        "hostname": "MacBook-Pro.local" if host == "local" else "HP",
        "platform": "darwin-arm64" if host == "local" else "linux-x86_64",
        "reachable": True,
        "orcaRuntime": {
            "runtimeId": "c599735e-f600-4953-9f44-a4102f70e081",
            "appVersion": "1.4.245",
            "graphStatus": "ready",
        },
        "terminals": [
            {
                "handle": "term_active_w0m",
                "worktreeId": "dc43c8a8::/Users/proto/Projects/!self/w0m",
                "worktreePath": "/Users/proto/Projects/!self/w0m",
                "tabId": "tab-active-1",
                "leafId": "leaf-active-1",
                "title": "Terminal 2",
            },
            {
                "handle": "term_floating_idle",
                "worktreeId": "global-floating-terminal",
                "worktreePath": "",
                "tabId": "tab-float-1",
                "leafId": "leaf-float-1",
                "title": "Terminal 1",
            },
        ],
        "worktrees": [
            {
                "id": "dc43c8a8::/Users/proto/Projects/!self/w0m",
                "path": "/Users/proto/Projects/!self/w0m",
                "branch": "refs/heads/beta",
            }
        ],
        "sshTargets": [
            {
                "id": "ssh-linux-1",
                "label": "linux-host",
                "configHost": "linux-host",
                "connected": True,
            }
        ],
        "hookEntries": {
            "tab-active-1:leaf-active-1": {
                "paneKey": "tab-active-1:leaf-active-1",
                "source": "antigravity",
                "tabId": "tab-active-1",
                "worktreeId": "dc43c8a8::/Users/proto/Projects/!self/w0m",
                "providerSession": {
                    "key": "conversation_id",
                    "id": "339a6a52-1dea-4955-823c-2e4b1bb87977",
                },
                "payload": {
                    "state": "working",
                    "prompt": "Implement T596 multi-host Orca orchestration",
                    "agentType": "antigravity",
                },
                "evidenceObservedAt": 1793529214806,
            },
            "tab-float-1:leaf-float-1": {
                "paneKey": "tab-float-1:leaf-float-1",
                "source": "antigravity",
                "tabId": "tab-float-1",
                "worktreeId": "global-floating-terminal",
                "providerSession": {
                    "key": "conversation_id",
                    "id": "5d7aab3a-0da8-4afa-8b57-54bba3e338ad",
                },
                "payload": {
                    "state": "done",
                    "prompt": "migrate pandatransfer from linux-host",
                    "agentType": "antigravity",
                },
                "evidenceObservedAt": 1793524794693,
            },
        },
        "processes": [
            {
                "pid": 31102,
                "ppid": 31006,
                "agent": "antigravity",
                "command": "agy --conversation=339a6a52-1dea-4955-823c-2e4b1bb87977 --dangerously-skip-permissions",
                "cwd": "/Users/proto/Projects/!self/w0m",
                "conversation_id": "339a6a52-1dea-4955-823c-2e4b1bb87977",
                "open_brains": ["339a6a52-1dea-4955-823c-2e4b1bb87977"],
                "paneKey": "tab-active-1:leaf-active-1",
                "tabId": "tab-active-1",
                "terminalHandle": "term_active_w0m",
                "worktreeId": "dc43c8a8::/Users/proto/Projects/!self/w0m",
            },
            {
                "pid": 50452,
                "ppid": 50409,
                "agent": "antigravity",
                "command": "agy --dangerously-skip-permissions",
                "cwd": "/Users/proto",
                "conversation_id": "5d7aab3a-0da8-4afa-8b57-54bba3e338ad",
                "open_brains": ["5d7aab3a-0da8-4afa-8b57-54bba3e338ad"],
                "paneKey": "tab-float-1:leaf-float-1",
                "tabId": "tab-float-1",
                "terminalHandle": "term_floating_idle",
                "worktreeId": "global-floating-terminal",
            },
        ],
        "agentTrees": [
            {
                "name": "agy-t596",
                "path": "/Users/proto/.w0m/work/agy-t596/w0m",
                "agent_id": "agy:agy-t596",
                "claimed_tickets": ["T596"],
            }
        ],
        "transcripts": {
            "339a6a52-1dea-4955-823c-2e4b1bb87977": {
                "lastPrompt": "Implement T596 multi-host Orca orchestration",
                "lastCreatedAt": "2026-11-01T10:33:00Z",
                "updatedAtMs": 1793529214806,
            },
            "5d7aab3a-0da8-4afa-8b57-54bba3e338ad": {
                "lastPrompt": "migrate pandatransfer from linux-host",
                "lastCreatedAt": "2026-11-01T09:15:00Z",
                "updatedAtMs": 1793524794693,
            },
            "3023b754-8224-49a4-b6e8-f902f6f53dba": {
                "lastPrompt": "resume dormant session",
                "lastCreatedAt": "2026-10-31T20:00:00Z",
                "updatedAtMs": 1793480000000,
            },
        },
    }


class TestOrcaSessions(unittest.TestCase):
    def test_correlate_host_sessions_live_and_dormant(self) -> None:
        snap = _make_sample_snapshot("local")
        live_only = osess.correlate_host_sessions(snap, include_dormant=False)
        self.assertEqual(len(live_only), 2)

        by_conv = {s["conversation_id"]: s for s in live_only}
        active = by_conv["339a6a52-1dea-4955-823c-2e4b1bb87977"]
        self.assertEqual(active["state"], "working")
        self.assertEqual(active["pid"], 31102)
        self.assertEqual(active["terminalHandle"], "term_active_w0m")
        self.assertEqual(active["worktreePath"], "/Users/proto/Projects/!self/w0m")
        self.assertEqual(active["agentTree"], "agy-t596")

        floating = by_conv["5d7aab3a-0da8-4afa-8b57-54bba3e338ad"]
        self.assertEqual(floating["state"], "tui-idle")
        self.assertEqual(floating["pid"], 50452)
        self.assertEqual(floating["worktreeId"], "global-floating-terminal")

        with_dormant = osess.correlate_host_sessions(snap, include_dormant=True)
        self.assertEqual(len(with_dormant), 3)
        dormant = next(s for s in with_dormant if s["conversation_id"] == "3023b754-8224-49a4-b6e8-f902f6f53dba")
        self.assertEqual(dormant["state"], "dormant")
        self.assertIsNone(dormant["pid"])
        self.assertEqual(dormant["prompt"], "resume dormant session")
        print("  [PASS] correlate_host_sessions correlates live, floating-idle, and dormant sessions")

    def test_single_writer_guard_refuses_active_writer(self) -> None:
        snap = _make_sample_snapshot("local")
        sessions = osess.correlate_host_sessions(snap, include_dormant=True)

        # Active working session refused without --rebind-idle
        v1 = osess.check_single_writer_guard(sessions, "339a6a52-1dea-4955-823c-2e4b1bb87977", rebind_idle=False)
        self.assertFalse(v1["allowed"])
        self.assertEqual(v1["action"], "refuse_active_writer")
        self.assertIn("31102", v1["reason"])

        # Active working session STILL refused even with --rebind-idle
        v2 = osess.check_single_writer_guard(sessions, "339a6a52-1dea-4955-823c-2e4b1bb87977", rebind_idle=True)
        self.assertFalse(v2["allowed"])
        self.assertEqual(v2["action"], "refuse_working")

        # Idle floating session refused without --rebind-idle, allowed WITH --rebind-idle
        v3 = osess.check_single_writer_guard(sessions, "5d7aab3a-0da8-4afa-8b57-54bba3e338ad", rebind_idle=False)
        self.assertFalse(v3["allowed"])
        self.assertEqual(v3["action"], "refuse_active_writer")

        v4 = osess.check_single_writer_guard(sessions, "5d7aab3a-0da8-4afa-8b57-54bba3e338ad", rebind_idle=True)
        self.assertTrue(v4["allowed"])
        self.assertEqual(v4["action"], "rebind_idle")

        # Dormant session allowed without --rebind-idle
        v5 = osess.check_single_writer_guard(sessions, "3023b754-8224-49a4-b6e8-f902f6f53dba", rebind_idle=False)
        self.assertTrue(v5["allowed"])
        self.assertEqual(v5["action"], "attach_dormant")
        print("  [PASS] check_single_writer_guard enforces single-writer PID lock across working, idle, and dormant states")

    def test_attach_session_dry_run_and_refusal(self) -> None:
        snap = _make_sample_snapshot("local")

        refused = osess.attach_session(
            "339a6a52-1dea-4955-823c-2e4b1bb87977",
            "/Users/proto/Projects/!self/w0m",
            host="local",
            rebind_idle=False,
            dry_run=True,
            snapshot_override=snap,
        )
        self.assertFalse(refused["ok"])
        self.assertIn("Single-writer lock guard refused attach", str(refused.get("error")))

        rebound = osess.attach_session(
            "5d7aab3a-0da8-4afa-8b57-54bba3e338ad",
            "/Users/proto/Projects/!self/w0m",
            host="local",
            rebind_idle=True,
            dry_run=True,
            snapshot_override=snap,
        )
        self.assertTrue(rebound["ok"])
        self.assertTrue(rebound["dryRun"])
        self.assertEqual(rebound["worktree"], "dc43c8a8::/Users/proto/Projects/!self/w0m")
        self.assertIn("--conversation=5d7aab3a-0da8-4afa-8b57-54bba3e338ad", rebound["command"])
        print("  [PASS] attach_session enforces single-writer refusal and resolves target worktree on rebind")

    def test_extract_transcript_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp) / "transcript.jsonl"
            lines = [
                json.dumps({"step_index": 0, "type": "SYSTEM", "created_at": "2026-11-01T10:00:00Z"}),
                json.dumps(
                    {
                        "step_index": 1,
                        "type": "USER_INPUT",
                        "created_at": "2026-11-01T10:05:00Z",
                        "content": "<USER_REQUEST>\nConsolidate sessions into w0m\n</USER_REQUEST>",
                    }
                ),
                json.dumps({"step_index": 2, "type": "PLANNER_RESPONSE", "created_at": "2026-11-01T10:06:00Z"}),
            ]
            tpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
            summary = osess.extract_transcript_summary(tpath)
            self.assertEqual(summary["lastPrompt"], "Consolidate sessions into w0m")
            self.assertEqual(summary["lastCreatedAt"], "2026-11-01T10:06:00Z")
            self.assertTrue(summary["updatedAtMs"] > 0)
        print("  [PASS] extract_transcript_summary parses USER_REQUEST and timestamps from transcript.jsonl")

    def test_orca_rpc_call_and_ensure_ssh_target(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            user_data = Path(tmp)
            sock_path = user_data / "rt.sock"
            meta_path = user_data / "orca-runtime.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "runtimeId": "rt-test-1",
                        "pid": 12345,
                        "authToken": "secret-token-1",
                        "transports": [{"kind": "unix", "endpoint": str(sock_path)}],
                        "startedAt": 1793520000000,
                    }
                ),
                encoding="utf-8",
            )

            targets_store: list[dict[str, Any]] = []
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(str(sock_path))
            srv.listen(5)

            def _serve() -> None:
                for _ in range(4):
                    conn, _ = srv.accept()
                    data = conn.recv(65536).decode("utf-8")
                    req = json.loads(data.strip())
                    method = req.get("method")
                    if method == "ssh.listTargets":
                        resp = {"id": req["id"], "ok": True, "result": {"targets": list(targets_store)}}
                    elif method == "ssh.addTarget":
                        t = dict(req["params"]["target"])
                        t["id"] = "ssh-added-1"
                        t["connected"] = False
                        targets_store.append(t)
                        resp = {"id": req["id"], "ok": True, "result": {"target": t, "repoReadoptions": []}}
                    elif method == "ssh.connect":
                        for t in targets_store:
                            if t["id"] == req["params"]["targetId"]:
                                t["connected"] = True
                        resp = {"id": req["id"], "ok": True, "result": {"connected": True}}
                    else:
                        resp = {"id": req["id"], "ok": False, "error": {"code": "unknown_method"}}
                    conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
                    conn.close()
                srv.close()

            th = threading.Thread(target=_serve, daemon=True)
            th.start()

            ensured = osess.ensure_ssh_target("linux-host", user_data_path=user_data, connect=True)
            th.join(timeout=3.0)

            self.assertTrue(ensured["ok"])
            self.assertTrue(ensured["created"])
            self.assertEqual(ensured["target"]["id"], "ssh-added-1")
            self.assertTrue(ensured["target"]["connected"])
        print("  [PASS] ensure_ssh_target registers and connects missing SSH host via Orca Unix socket RPC")

    def test_format_tables_multi_host(self) -> None:
        snap_local = _make_sample_snapshot("local")
        snap_remote = _make_sample_snapshot("linux-host")
        sess_local = osess.correlate_host_sessions(snap_local)
        sess_remote = osess.correlate_host_sessions(snap_remote)

        hosts_md = osess.format_hosts_table(
            [snap_local, snap_remote],
            {"local": sess_local, "linux-host": sess_remote},
        )
        self.assertIn("`local`", hosts_md)
        self.assertIn("`linux-host`", hosts_md)
        self.assertIn("linux-host:connected", hosts_md)

        sessions_md = osess.format_sessions_table([*sess_local, *sess_remote])
        self.assertIn("339a6a52-1dea-4955-823c-2e4b1bb87977", sessions_md)
        self.assertIn("5d7aab3a-0da8-4afa-8b57-54bba3e338ad", sessions_md)
        self.assertIn("`agy-t596`", sessions_md)
        print("  [PASS] format_hosts_table and format_sessions_table render multi-host inventory tables")

    def test_save_and_load_private_workload_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            state_dir = home / ".w0m" / "state" / "workload"
            sess_arch = home / ".w0m" / "state" / "sessions" / "linux-host" / "40410adb-a034-4a71-8a83-98907b5e3a7f"
            sess_arch.mkdir(parents=True, exist_ok=True)
            (sess_arch / "summary.md").write_text("# Archived\n", encoding="utf-8")

            reg_dir = home / ".w0m" / "agents"
            reg_dir.mkdir(parents=True, exist_ok=True)
            (reg_dir / "registry.json").write_text(
                json.dumps(
                    {
                        "claims": {
                            "T599": {
                                "agent_id": "agy:agy-t599",
                                "track": "Track C",
                                "session_title": "Track C · T599 · Workload State [agy-t599]",
                                "orca_terminal_handle": "term_active_w0m",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            snap_local = _make_sample_snapshot("local")
            snap_remote = _make_sample_snapshot("linux-host")
            saved = osess.save_private_workload_state(
                state_dir=state_dir,
                home_dir=home,
                sync_hosts=False,
                snapshots_override=[snap_local, snap_remote],
            )
            self.assertTrue(saved["ok"])
            self.assertEqual(saved["hostCount"], 2)
            self.assertEqual(saved["archivedSessionCount"], 1)
            self.assertTrue(Path(saved["latestJson"]).is_file())
            self.assertTrue(Path(saved["latestMd"]).is_file())

            loaded = osess.load_private_workload_state(state_dir=state_dir, home_dir=home)
            self.assertTrue(loaded["ok"])
            self.assertTrue(loaded["payload"]["private"])
            self.assertIn("T599", loaded["payload"]["agentClaims"])

            md = Path(saved["latestMd"]).read_text(encoding="utf-8")
            self.assertIn("Private Cross-Host Project & Agent Workload Snapshot", md)
            self.assertIn("`40410adb-a034-4a71-8a83-98907b5e3a7f`", md)
        print("  [PASS] save_private_workload_state and load_private_workload_state persist private state and artifacts")


if __name__ == "__main__":
    unittest.main()
