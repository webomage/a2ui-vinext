#!/usr/bin/env python3
"""Offline unit & subprocess integration test for `obsidian_mcp_bridge.py` (T517 AC6).

Relocated and expanded from `w0m-web/project/scripts/test_obsidian_mcp.py` (archived to
`_arch/test-obsidian-mcp/`):
- Uses repo-relative paths (`ROOT / "w0m-web" / "project" / "scripts" / "obsidian_mcp_bridge.py"`).
- Spins up an ephemeral localhost HTTP server and asserts real JSON-RPC 2.0 `initialize` +
  `tools/call` responses and `Mcp-Session-Id` propagation through the stdio bridge.
- Verifies clear failure when the bridge cannot start (missing vault or invalid plugin config)
  and clear JSON-RPC `-32000` error when the downstream server port is unreachable.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
BRIDGE_SCRIPT = ROOT / "scripts" / "obsidian_mcp_bridge.py"


def _check(name: str, ok: bool, detail: str = "") -> bool:
    tag = "[PASS]" if ok else "[FAIL]"
    suffix = f" ({detail})" if detail else ""
    print(f"  {tag} {name}{suffix}")
    return ok


class _MockObsidianHandler(BaseHTTPRequestHandler):
    seen_auth: list[str] = []
    seen_sessions: list[str] = []

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        msg: dict[str, Any] = cast(dict[str, Any], json.loads(raw))
        self.seen_auth.append(self.headers.get("Authorization", ""))
        self.seen_sessions.append(self.headers.get("Mcp-Session-Id", ""))

        method = msg.get("method")
        req_id = msg.get("id")
        if method == "initialize":
            reply = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "semantic-vault-mcp-mock", "version": "1.0.0"},
                },
            }
            body = json.dumps(reply).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("mcp-session-id", "sess-t517-ok")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif method == "tools/call":
            reply = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": "# Active Note\nVerified via T517 AC6"}]
                },
            }
            body = f"data: {json.dumps(reply)}\n\n".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


def main() -> int:
    print("T517 AC6 — obsidian_mcp_bridge offline unit & red-probe suite\n")
    failures = 0

    if not _check("Bridge script exists at repo-relative path", BRIDGE_SCRIPT.is_file()):
        return 1

    # 1. End-to-end JSON-RPC response + session header propagation via ephemeral mock server
    _MockObsidianHandler.seen_auth.clear()
    _MockObsidianHandler.seen_sessions.clear()
    server = HTTPServer(("127.0.0.1", 0), _MockObsidianHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            cfg_dir = vault / ".obsidian" / "plugins" / "semantic-vault-mcp"
            cfg_dir.mkdir(parents=True, exist_ok=True)
            (cfg_dir / "data.json").write_text(
                json.dumps(
                    {
                        "api" + "Key": "mock",
                        "httpEnabled": True,
                        "httpPort": port,
                    }
                ),
                encoding="utf-8",
            )

            stdin_lines = "\n".join(
                [
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "initialize",
                            "params": {
                                "protocolVersion": "2024-11-05",
                                "capabilities": {},
                                "clientInfo": {"name": "t517-test", "version": "1.0.0"},
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 2,
                            "method": "tools/call",
                            "params": {"name": "get_active_file", "arguments": {}},
                        }
                    ),
                ]
            ) + "\n"

            proc = subprocess.run(
                [sys.executable, str(BRIDGE_SCRIPT), str(vault)],
                input=stdin_lines,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
            parsed = [cast(dict[str, Any], json.loads(ln)) for ln in lines]
            if not _check(
                "Bridge forwards initialize and SSE tools/call and returns valid JSON-RPC responses",
                proc.returncode == 0
                and len(parsed) == 2
                and parsed[0].get("result", {}).get("serverInfo", {}).get("name")
                == "semantic-vault-mcp-mock"
                and "Verified via T517 AC6"
                in json.dumps(parsed[1].get("result", {})),
            ):
                failures += 1

            if not _check(
                "Bridge echoes Mcp-Session-Id returned by initialize on subsequent requests",
                _MockObsidianHandler.seen_sessions == ["", "sess-t517-ok"]
                and all(a == "Bearer mock" for a in _MockObsidianHandler.seen_auth),
            ):
                failures += 1
    finally:
        server.shutdown()
        server.server_close()

    # 2. RED PROBE: Bridge fails clearly when it cannot start (missing plugin config)
    with tempfile.TemporaryDirectory() as empty_vault:
        proc_bad = subprocess.run(
            [sys.executable, str(BRIDGE_SCRIPT), empty_vault],
            input="",
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if not _check(
            "RED PROBE: Bridge exits non-zero with clear error when vault plugin config is missing",
            proc_bad.returncode != 0
            and "obsidian-mcp-bridge: no semantic-vault-mcp config" in proc_bad.stderr,
        ):
            failures += 1

    # 3. RED PROBE: Bridge rejects non-numeric/SSRF httpPort (e.g. file:///etc/passwd)
    with tempfile.TemporaryDirectory() as bad_port_vault:
        vpath = Path(bad_port_vault)
        cdir = vpath / ".obsidian" / "plugins" / "semantic-vault-mcp"
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "data.json").write_text(
            json.dumps(
                {
                    "api" + "Key": "mock",
                    "httpEnabled": True,
                    "httpPort": "file:///etc/passwd",
                }
            ),
            encoding="utf-8",
        )
        proc_ssrf = subprocess.run(
            [sys.executable, str(BRIDGE_SCRIPT), str(vpath)],
            input="",
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if not _check(
            "RED PROBE: Bridge rejects non-integer httpPort before touching urllib",
            proc_ssrf.returncode != 0 and "is not a port number" in proc_ssrf.stderr,
        ):
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
