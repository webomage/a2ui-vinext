#!/usr/bin/env python3
"""stdio -> Streamable-HTTP bridge for the Obsidian `semantic-vault-mcp` servers (T144).

Why this exists rather than a plain `type: "http"` entry in the MCP client config:
the servers require `Authorization: Bearer <apiKey>`, and CLAUDE.md makes "secrets via
infisical, never a file" a non-negotiable. A literal key in `~/.claude.json` or in the
estate-root `.mcp.json` would put a live credential in an unversioned dotfile, and an
`${ENV}` expansion would need the variable set in whatever shell launches Claude Code —
which for the desktop app is not a shell anyone controls.

So the bridge reads the key at launch from the file the plugin already keeps it in:
`<vault>/.obsidian/plugins/semantic-vault-mcp/data.json`, which is gitignored in every
vault (verified 2026-08-07). One fact, one home — the key is never copied anywhere.

The port is read from the same file rather than passed in, because the two vaults have
swapped ports before and a hardcoded port would silently talk to the wrong vault. The
port<->vault mapping is a property of the plugin config, so read it from there.

⚠️ These servers live inside an Obsidian renderer process, so they exist only while that
vault's window is open. A closed vault is the normal case, not an error — the bridge exits
with a clear message rather than hanging the client.

Usage:  obsidian_mcp_bridge.py <vault-path>
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

PLUGIN_REL = Path(".obsidian/plugins/semantic-vault-mcp/data.json")
TIMEOUT = 30


def die(msg: str) -> None:
    print(f"obsidian-mcp-bridge: {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_config(vault: Path) -> tuple[str, int]:
    cfg_path = vault / PLUGIN_REL
    if not cfg_path.is_file():
        die(f"no semantic-vault-mcp config at {cfg_path} — is the plugin installed in this vault?")
    cfg = json.loads(cfg_path.read_text())
    key = cfg.get("apiKey")
    port = cfg.get("httpPort")
    if not key:
        die(f"{cfg_path} has no apiKey")
    if not cfg.get("httpEnabled"):
        die(f"{cfg_path} has httpEnabled=false — enable the HTTP server in the plugin settings")
    if not port:
        die(f"{cfg_path} has no httpPort")
    # The port is the only part of the URL that comes from a file, so bound it here rather
    # than letting a malformed config reach urllib as something other than a port number.
    if not isinstance(port, int) or isinstance(port, bool) or not (1 <= port <= 65535):
        die(f"{cfg_path} has httpPort={port!r}, which is not a port number")
    return key, port


# The server answers either `application/json` or an SSE frame; both carry one JSON-RPC
# message. Accepting only one of the two is how this class of bridge usually breaks.
SSE_DATA = re.compile(r"^data: (.*)$", re.MULTILINE)


def extract(body: str) -> dict | None:
    body = body.strip()
    if not body:
        return None
    if body.startswith("{"):
        return json.loads(body)
    frames = SSE_DATA.findall(body)
    if not frames:
        return None
    return json.loads(frames[-1])


# The server is session-ful: everything after `initialize` is rejected with
# "a session is required" unless the id it handed back is echoed. It returns the header
# lower-cased, so read it case-insensitively via HTTPMessage.get rather than off a dict()
# copy — that copy keeps the server's casing and a `Mcp-Session-Id` lookup silently misses.
SESSION: dict[str, str] = {}


def forward(url: str, key: str, message: dict) -> dict | None:
    req = urllib.request.Request(url, method="POST", data=json.dumps(message).encode())
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    req.add_header("Authorization", f"Bearer {key}")
    if sid := SESSION.get("id"):
        req.add_header("Mcp-Session-Id", sid)
    try:
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected -- the scheme and host are literals in the one f-string that builds this URL (`http://127.0.0.1:{port}/mcp`), and `port` is validated as an int in 1..65535 in load_config, so no value in the plugin config can change the scheme; file:// cannot reach here. Verified: setting httpPort to "file:///etc/passwd" exits at the load_config check without ever calling urlopen.
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            if returned := resp.headers.get("Mcp-Session-Id"):
                SESSION["id"] = returned
            return extract(resp.read().decode("utf8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf8", "replace")[:200]
        # A request carries an id and MUST get a reply; a notification must not.
        if message.get("id") is None:
            return None
        return {
            "jsonrpc": "2.0",
            "id": message["id"],
            "error": {"code": -32000, "message": f"HTTP {exc.code} from Obsidian: {detail}"},
        }
    except OSError as exc:
        if message.get("id") is None:
            return None
        return {
            "jsonrpc": "2.0",
            "id": message["id"],
            "error": {
                "code": -32000,
                "message": f"cannot reach the Obsidian MCP server at {url} ({exc}) — "
                "the vault window is probably closed",
            },
        }


def main() -> None:
    if len(sys.argv) != 2:
        die("usage: obsidian_mcp_bridge.py <vault-path>")
    vault = Path(sys.argv[1]).expanduser().resolve()
    if not vault.is_dir():
        die(f"{vault} is not a directory")
    key, port = load_config(vault)
    url = f"http://127.0.0.1:{port}/mcp"

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            print(
                json.dumps(
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
                ),
                flush=True,
            )
            continue
        reply = forward(url, key, message)
        if reply is not None:
            print(json.dumps(reply), flush=True)


if __name__ == "__main__":
    main()
