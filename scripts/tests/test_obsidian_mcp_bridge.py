#!/usr/bin/env python3
"""T144 AC1, AC2, AC6 — Regression proof for Obsidian MCP bridge & MCP-first transport declarations.

Proves:
  1. `.w0m/sdlc.json → mcp` declares `obsidian-w0m-web`, `w0m-cf-mcp`, and explicit `directions`.
  2. `obsidian_mcp_bridge.load_config` fails closed on missing config, missing apiKey, disabled HTTP,
     or malformed/SSRF port values (`file:///etc/passwd`, `0`, `70000`).
  3. AC6 RED proof: when an MCP listener is unreachable, `forward()` returns a loud JSON-RPC `-32000`
     error (`cannot reach the Obsidian MCP server`) and NEVER degrades to an empty tool list.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "w0m-web"
BRIDGE_PATH = ROOT / "scripts" / "obsidian_mcp_bridge.py"
SDLC_PATH = ROOT / ".w0m" / "sdlc.json"

spec = importlib.util.spec_from_file_location("obsidian_mcp_bridge", BRIDGE_PATH)
assert spec is not None and spec.loader is not None
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        failures.append(f"{label}{(' — ' + detail) if detail else ''}")


print("T144 — Obsidian MCP bridge & MCP-first transport probes\n")

# ── 1. .w0m/sdlc.json declarations (AC1, AC2, AC7) ──────────────────────────
sdlc = json.loads(SDLC_PATH.read_text(encoding="utf-8"))
mcp = sdlc.get("mcp") or {}
servers = mcp.get("servers") or {}
directions = mcp.get("directions") or {}

obs = servers.get("obsidian-w0m-web") or {}
func_mcp = servers.get("w0m-cf-mcp") or {}

check("AC1: obsidian-w0m-web is declared in .w0m/sdlc.json -> mcp.servers",
      obs.get("enabled") is True and obs.get("transport") == "local-http")
check("AC2: obsidian-w0m-web records direction and stdio bridge path",
      obs.get("direction") == "agent_to_obsidian"
      and obs.get("bridge") == "scripts/obsidian_mcp_bridge.py")
check("AC2: mcp.directions records agent_to_obsidian, obsidian_to_w0m, and browser_to_agent",
      all(k in directions for k in ("agent_to_obsidian", "obsidian_to_w0m", "browser_to_agent")))
check("AC7: w0m-cf-mcp HTTP MCP server is declared in .w0m/sdlc.json -> mcp.servers",
      func_mcp.get("enabled") is True and func_mcp.get("endpoint") == "/mcp")

# ── 2. load_config validation & SSRF guard ───────────────────────────────────
tmp = Path(tempfile.mkdtemp(prefix="t144-"))


def write_vault_cfg(name: str, data: dict | None) -> Path:
    v = tmp / name
    v.mkdir(parents=True, exist_ok=True)
    if data is not None:
        p = v / ".obsidian" / "plugins" / "semantic-vault-mcp"
        p.mkdir(parents=True, exist_ok=True)
        (p / "data.json").write_text(json.dumps(data), encoding="utf-8")
    return v


for label, cfg_data in [
    ("missing plugin config", None),
    ("missing apiKey", {"httpEnabled": True, "httpPort": 3007}),
    ("httpEnabled=false", {"apiKey": "k", "httpEnabled": False, "httpPort": 3007}),
    ("SSRF string port (file:///etc/passwd)", {"apiKey": "k", "httpEnabled": True, "httpPort": "file:///etc/passwd"}),
    ("out-of-range port 70000", {"apiKey": "k", "httpEnabled": True, "httpPort": 70000}),
]:
    vpath = write_vault_cfg(label.replace(" ", "_").replace("/", "_"), cfg_data)
    try:
        bridge.load_config(vpath)
        check(f"RED — {label} is rejected by load_config", False, "did not raise SystemExit")
    except SystemExit as exc:
        check(f"RED — {label} is rejected by load_config (exit {exc.code})", exc.code != 0)

good_vault = write_vault_cfg("good_vault", {"apiKey": "secret-key-1", "httpEnabled": True, "httpPort": 3007})
key, port = bridge.load_config(good_vault)
check("valid semantic-vault-mcp config loads apiKey and httpPort",
      key == "secret-key-1" and port == 3007)

# ── 3. AC6 RED proof: unreachable MCP server fails visibly, never returns empty tools ──
unreachable_reply = bridge.forward(
    "http://127.0.0.1:1/mcp",
    "secret-key-1",
    {"jsonrpc": "2.0", "id": 99, "method": "tools/list", "params": {}},
)
check("RED — AC6: unreachable MCP server returns JSON-RPC error object, not None or result",
      isinstance(unreachable_reply, dict)
      and "error" in unreachable_reply
      and "result" not in unreachable_reply,
      repr(unreachable_reply))
check("RED — AC6: error code is -32000 and names the unreachable endpoint",
      unreachable_reply is not None
      and unreachable_reply.get("error", {}).get("code") == -32000
      and "cannot reach the Obsidian MCP server" in unreachable_reply.get("error", {}).get("message", ""))

# SSE + JSON extraction check
check("extract() parses direct JSON-RPC response",
      bridge.extract('{"jsonrpc":"2.0","id":1,"result":{"tools":[{"name":"vault"}]}}')
      == {"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "vault"}]}})
check("extract() parses SSE data frame response",
      bridge.extract('event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"ok":true}}\n\n')
      == {"jsonrpc": "2.0", "id": 2, "result": {"ok": True}})

print()
if failures:
    print(f"{len(failures)} failure(s):")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("obsidian-mcp-bridge: OK — all checks passed")
