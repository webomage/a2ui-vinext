#!/usr/bin/env python3
"""T596 — Multi-host Orca instance and agent session orchestration across macOS and Linux boxes.

Provides:
1. Unified Cross-Host Session Discovery & Status Inventory (`list` / `just orca-sessions`):
   Discovers and correlates all live and dormant agent sessions (`agy`, `claude`, `codex`,
   `opencode`) across local (`darwin`) and remote SSH hosts (`linux-host`), combining:
   - Orca runtime Unix-socket RPC (`status.get`, `terminal.list`, `worktree.list`, `ssh.listTargets`)
   - Orca agent hook telemetry (`agent-hooks/last-status.json`)
   - Live OS process trees (`--conversation=<uuid>`, `ORCA_AGENT_PANE`, `ORCA_TERMINAL_HANDLE`)
   - Active w0m isolated agent trees (`~/.w0m/work/<tree>/w0m`) and ticket claims
   - Antigravity brain transcripts (`~/.gemini/antigravity-cli/brain/<uuid>/`)
2. Safe Programmatic Session Reattachment & Consolidation (`attach` / `just orca-attach`):
   Enforces a single-writer PID lock guard before attaching or launching `agy --conversation=<uuid>`
   in an Orca worktree tab, refusing duplicate writers and supporting controlled `--rebind-idle`
   migration from `global-floating-terminal` into a target project worktree tab.
3. Cross-Host Orca Daemon & Remote Environment Management (`hosts` / `just orca-hosts`):
   Verifies local and remote Orca daemon reachability and ensures `linux-host` is registered
   and connected in Orca's SSH target catalog (`ssh.addTarget` / `ssh.connect`).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

PRIMARY_CONTROL_PLANE_HOST = "linux-host"
DEFAULT_REMOTE_HOSTS: tuple[str, ...] = ("linux-host",)
DEFAULT_SSH_TARGET_CONFIG: dict[str, dict[str, Any]] = {
    "linux-host": {
        "label": "linux-host",
        "configHost": "linux-host",
        "host": "192.168.0.95",
        "port": 22,
        "username": "aleksei",
        "allowRemoteCliControl": True,
    }
}


def is_local_linux_control_plane(
    sys_platform: str | None = None,
    hostname: str | None = None,
) -> bool:
    """Return True when executing directly on the Linux primary control-plane host (`HP` / `linux-host`)."""
    plat = (sys_platform or sys.platform).lower()
    hname = (hostname or socket.gethostname()).lower()
    return plat.startswith("linux") or hname in {"hp", "linux-host", "w0m-linux"}


def get_default_remote_hosts(
    sys_platform: str | None = None,
    hostname: str | None = None,
) -> tuple[str, ...]:
    """Return default remote SSH hosts to poll alongside `local`.

    When running directly on the Linux primary control plane (`HP` / `linux-host`),
    `local` IS the primary host and macOS may be reset/offline, so no remote SSH
    host is polled by default.
    """
    if is_local_linux_control_plane(sys_platform=sys_platform, hostname=hostname):
        return ()
    return DEFAULT_REMOTE_HOSTS


def normalize_host_target(
    host: str,
    *,
    sys_platform: str | None = None,
    hostname: str | None = None,
) -> str:
    """Map `linux-host` to `local` when already executing on the Linux primary control plane."""
    if host == "linux-host" and is_local_linux_control_plane(sys_platform=sys_platform, hostname=hostname):
        return "local"
    return host


def resolve_local_orca_cli(home_dir: Path | None = None) -> str:
    """Resolve the local `orca` CLI binary across Linux (`~/.local/bin/orca`) and macOS."""
    found = shutil.which("orca")
    if found:
        return found
    home = home_dir or Path.home()
    linux_bin = home / ".local" / "bin" / "orca"
    if linux_bin.is_file():
        return str(linux_bin)
    mac_bin = Path("/Applications/Orca.app/Contents/Resources/bin/orca")
    if mac_bin.is_file():
        return str(mac_bin)
    return "orca"

IDLE_STATES: frozenset[str] = frozenset({"done", "tui-idle", "idle", "stopped", "dormant"})
ACTIVE_STATES: frozenset[str] = frozenset({"working", "running", "thinking", "tool-use"})

UUID_RE = re.compile(r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b", re.I)
CONV_FLAG_RE = re.compile(
    r"--conversation(?:=|\s+)([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.I,
)
ORCA_ENV_RE = re.compile(r"\b(ORCA_[A-Z0-9_]+)=([^\s]+)")


def get_orca_user_data_path(sys_platform: str | None = None, home_dir: Path | None = None) -> Path:
    """Resolve the platform-specific Orca userData directory."""
    env_override = os.environ.get("ORCA_USER_DATA_PATH")
    if env_override:
        return Path(env_override)
    plat = (sys_platform or sys.platform).lower()
    home = home_dir or Path.home()
    if plat.startswith("darwin"):
        return home / "Library" / "Application Support" / "orca"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else (home / ".config")
    lower = base / "orca"
    upper = base / "Orca"
    if lower.exists() or not upper.exists():
        return lower
    return upper


def orca_rpc_call(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    user_data_path: Path | None = None,
    timeout_s: float = 8.0,
) -> dict[str, Any]:
    """Send a single JSON-lines RPC request over the local Orca runtime Unix domain socket."""
    base = user_data_path or get_orca_user_data_path()
    meta_path = base / "orca-runtime.json"
    if not meta_path.is_file():
        return {"ok": False, "error": {"code": "runtime_unavailable", "message": f"Missing {meta_path}"}}
    try:
        meta: dict[str, Any] = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": {"code": "invalid_metadata", "message": str(exc)}}

    transports = meta.get("transports") or []
    sock_path: str | None = None
    for t in transports:
        if isinstance(t, dict) and t.get("kind") == "unix" and isinstance(t.get("endpoint"), str):
            sock_path = t["endpoint"]
            break
    if not sock_path:
        return {"ok": False, "error": {"code": "no_unix_socket", "message": "No unix transport in orca-runtime.json"}}

    req_id = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "id": req_id,
        "authToken": meta.get("authToken"),
        "method": method,
    }
    if params is not None:
        payload["params"] = params

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout_s)
    try:
        sock.connect(sock_path)
        sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        buf = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                frame: dict[str, Any] = json.loads(line.decode("utf-8", errors="replace"))
                if isinstance(frame, dict) and frame.get("_keepalive"):
                    continue
                if isinstance(frame, dict) and frame.get("id") == req_id:
                    return frame
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": {"code": "rpc_error", "message": str(exc)}}
    finally:
        try:
            sock.close()
        except OSError:
            pass
    return {"ok": False, "error": {"code": "empty_response", "message": "Socket closed without response"}}


def extract_transcript_summary(transcript_path: Path) -> dict[str, Any]:
    """Read the tail of a brain transcript.jsonl to extract last prompt and timestamp."""
    if not transcript_path.is_file():
        return {}
    try:
        size = transcript_path.stat().st_size
        mtime = int(transcript_path.stat().st_mtime * 1000)
        with transcript_path.open("rb") as fh:
            if size > 65536:
                fh.seek(size - 65536)
            tail = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return {}

    last_prompt = ""
    last_created_at = ""
    for line in reversed(tail.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj: dict[str, Any] = json.loads(line)
        except ValueError:
            continue
        if not last_created_at and isinstance(obj.get("created_at"), str):
            last_created_at = obj["created_at"]
        if obj.get("type") == "USER_INPUT" and isinstance(obj.get("content"), str):
            raw = obj["content"]
            if "<USER_REQUEST>" in raw and "</USER_REQUEST>" in raw:
                raw = raw.split("<USER_REQUEST>", 1)[1].split("</USER_REQUEST>", 1)[0]
            last_prompt = " ".join(raw.strip().split())[:160]
            break
    return {
        "lastPrompt": last_prompt,
        "lastCreatedAt": last_created_at,
        "updatedAtMs": mtime,
    }


def _discover_local_processes() -> list[dict[str, Any]]:
    """Inspect local OS processes for live `agy`, `claude`, `codex`, `opencode` instances."""
    procs: list[dict[str, Any]] = []
    try:
        ps_out = subprocess.check_output(
            ["ps", "-eo", "pid,ppid,stat,command"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return procs

    for line in ps_out.splitlines()[1:]:
        parts = line.strip().split(None, 3)
        if len(parts) < 4:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
        except ValueError:
            continue
        cmd = parts[3]
        first_bin = Path(cmd.split()[0]).name if cmd.split() else ""
        if first_bin not in {"agy", "claude", "codex", "opencode"}:
            continue

        conv_match = CONV_FLAG_RE.search(cmd)
        conv_id = conv_match.group(1) if conv_match else None
        orca_env: dict[str, str] = {}
        cwd = ""
        open_brains: list[str] = []

        if sys.platform.startswith("darwin"):
            try:
                ps_e = subprocess.run(
                    ["ps", "eww", "-p", str(pid)],
                    capture_output=True,
                    text=True,
                    timeout=2.0,
                ).stdout
                for k, v in ORCA_ENV_RE.findall(ps_e):
                    orca_env[k] = v
            except (OSError, subprocess.SubprocessError):
                pass
            try:
                lsof_out = subprocess.run(
                    ["lsof", "-a", "-p", str(pid), "-d", "cwd,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15"],
                    capture_output=True,
                    text=True,
                    timeout=2.0,
                ).stdout
                for l_line in lsof_out.splitlines():
                    if " cwd " in l_line:
                        cwd = l_line.split()[-1]
                    for b_match in re.findall(r"brain/([0-9a-f-]{36})", l_line):
                        if b_match not in open_brains:
                            open_brains.append(b_match)
            except (OSError, subprocess.SubprocessError):
                pass
        else:
            proc_dir = Path(f"/proc/{pid}")
            try:
                cwd = os.readlink(proc_dir / "cwd")
            except OSError:
                pass
            try:
                raw_env = (proc_dir / "environ").read_bytes().decode("utf-8", errors="replace")
                for item in raw_env.split("\0"):
                    if item.startswith("ORCA_") and "=" in item:
                        k, v = item.split("=", 1)
                        orca_env[k] = v
            except OSError:
                pass

        if not conv_id and len(open_brains) == 1:
            conv_id = open_brains[0]

        procs.append(
            {
                "pid": pid,
                "ppid": ppid,
                "agent": "antigravity" if first_bin == "agy" else first_bin,
                "command": cmd,
                "cwd": cwd,
                "conversation_id": conv_id,
                "open_brains": open_brains,
                "paneKey": orca_env.get("ORCA_AGENT_PANE") or orca_env.get("ORCA_PANE_KEY"),
                "tabId": orca_env.get("ORCA_TAB_ID"),
                "terminalHandle": orca_env.get("ORCA_TERMINAL_HANDLE"),
                "worktreeId": orca_env.get("ORCA_WORKTREE_ID"),
            }
        )
    return procs


def _discover_agent_trees(home_dir: Path) -> list[dict[str, Any]]:
    """Inspect `~/.w0m/work/*/w0m` isolated agent trees and `~/.w0m/agents/registry.json`."""
    trees: list[dict[str, Any]] = []
    work_dir = home_dir / ".w0m" / "work"
    claims_by_agent: dict[str, list[str]] = {}
    reg_path = home_dir / ".w0m" / "agents" / "registry.json"
    if reg_path.is_file():
        try:
            reg: dict[str, Any] = json.loads(reg_path.read_text(encoding="utf-8"))
            for tid, info in (reg.get("claims") or {}).items():
                if isinstance(info, dict) and isinstance(info.get("agent_id"), str):
                    claims_by_agent.setdefault(info["agent_id"], []).append(tid)
        except (OSError, ValueError):
            pass

    if work_dir.is_dir():
        for child in sorted(work_dir.iterdir()):
            w0m_root = child / "w0m"
            if not w0m_root.is_dir():
                continue
            agent_id_file = w0m_root / ".w0m" / "agent-id"
            agent_id = ""
            if agent_id_file.is_file():
                try:
                    agent_id = agent_id_file.read_text(encoding="utf-8").strip()
                except OSError:
                    pass
            if not agent_id:
                agent_id = f"agy:{child.name}"
            claimed = list(claims_by_agent.get(agent_id, []))
            for m_tid in re.findall(r"\bt(\d+)\b", child.name, re.I):
                tid_str = f"T{int(m_tid)}"
                if tid_str not in claimed:
                    claimed.append(tid_str)
            trees.append(
                {
                    "name": child.name,
                    "path": str(w0m_root),
                    "agent_id": agent_id,
                    "claimed_tickets": sorted(claimed),
                }
            )
    return trees


def collect_local_snapshot(
    *,
    host_label: str = "local",
    user_data_path: Path | None = None,
    home_dir: Path | None = None,
    dormant_limit: int = 10,
) -> dict[str, Any]:
    """Gather a complete telemetry snapshot from the local machine."""
    home = home_dir or Path.home()
    orca_dir = user_data_path or get_orca_user_data_path(home_dir=home)

    status_rpc = orca_rpc_call("status.get", user_data_path=orca_dir)
    terms_rpc = orca_rpc_call("terminal.list", {}, user_data_path=orca_dir)
    wts_rpc = orca_rpc_call("worktree.list", {}, user_data_path=orca_dir)
    ssh_rpc = orca_rpc_call("ssh.listTargets", user_data_path=orca_dir)

    last_status_path = orca_dir / "agent-hooks" / "last-status.json"
    hook_entries: dict[str, Any] = {}
    if last_status_path.is_file():
        try:
            raw_hooks: dict[str, Any] = json.loads(last_status_path.read_text(encoding="utf-8"))
            if isinstance(raw_hooks, dict) and isinstance(raw_hooks.get("entries"), dict):
                hook_entries = raw_hooks["entries"]
        except (OSError, ValueError):
            pass

    brains_dir = home / ".gemini" / "antigravity-cli" / "brain"
    transcripts: dict[str, dict[str, Any]] = {}
    if brains_dir.is_dir():
        brain_dirs = sorted(
            (d for d in brains_dir.iterdir() if d.is_dir() and UUID_RE.fullmatch(d.name)),
            key=lambda d: d.stat().st_mtime if d.exists() else 0,
            reverse=True,
        )
        for bdir in brain_dirs[: max(dormant_limit, 25)]:
            tpath = bdir / ".system_generated" / "logs" / "transcript.jsonl"
            summary = extract_transcript_summary(tpath)
            if summary:
                transcripts[bdir.name] = summary

    return {
        "host": host_label,
        "hostname": socket.gethostname(),
        "platform": f"{platform.system().lower()}-{platform.machine().lower()}",
        "reachable": True,
        "orcaRuntime": status_rpc.get("result") if status_rpc.get("ok") else None,
        "orcaError": status_rpc.get("error") if not status_rpc.get("ok") else None,
        "terminals": (terms_rpc.get("result") or {}).get("terminals", []) if terms_rpc.get("ok") else [],
        "worktrees": (wts_rpc.get("result") or {}).get("worktrees", []) if wts_rpc.get("ok") else [],
        "sshTargets": (ssh_rpc.get("result") or {}).get("targets", []) if ssh_rpc.get("ok") else [],
        "hookEntries": hook_entries,
        "processes": _discover_local_processes(),
        "agentTrees": _discover_agent_trees(home),
        "transcripts": transcripts,
    }


REMOTE_PROBE_SNIPPET = r"""
import json, os, platform, re, socket, uuid
from pathlib import Path

home = Path.home()
orca_dir = Path(os.environ.get("XDG_CONFIG_HOME") or (home / ".config")) / "orca"
if not orca_dir.exists() and (home / ".config" / "Orca").exists():
    orca_dir = home / ".config" / "Orca"

def rpc(method, params=None):
    meta_path = orca_dir / "orca-runtime.json"
    if not meta_path.is_file():
        return {"ok": False, "error": {"code": "runtime_unavailable", "message": f"Missing {meta_path}"}}
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        sock_path = next(t["endpoint"] for t in (meta.get("transports") or []) if t.get("kind") == "unix")
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(4.0)
        s.connect(sock_path)
        req_id = str(uuid.uuid4())
        req = {"id": req_id, "authToken": meta.get("authToken"), "method": method}
        if params is not None:
            req["params"] = params
        s.sendall((json.dumps(req) + "\n").encode("utf-8"))
        buf = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                frame = json.loads(line.decode("utf-8", errors="replace"))
                if frame.get("_keepalive"):
                    continue
                if frame.get("id") == req_id:
                    s.close()
                    return frame
        s.close()
    except Exception as e:
        return {"ok": False, "error": {"code": "rpc_error", "message": str(e)}}
    return {"ok": False, "error": {"code": "empty_response"}}

status_rpc = rpc("status.get")
terms_rpc = rpc("terminal.list", {})
wts_rpc = rpc("worktree.list", {})
ssh_rpc = rpc("ssh.listTargets")

hook_entries = {}
ls_path = orca_dir / "agent-hooks" / "last-status.json"
if ls_path.is_file():
    try:
        hook_entries = json.loads(ls_path.read_text(encoding="utf-8")).get("entries", {})
    except Exception:
        pass

conv_re = re.compile(r"--conversation(?:=|\s+)([0-9a-f-]{36})", re.I)
procs = []
for pdir in Path("/proc").iterdir():
    if not pdir.name.isdigit():
        continue
    pid = int(pdir.name)
    try:
        cmdline = (pdir / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
        if not cmdline:
            continue
        first_bin = Path(cmdline.split()[0]).name
        if first_bin not in ("agy", "claude", "codex", "opencode"):
            continue
        cwd = os.readlink(pdir / "cwd")
        raw_env = (pdir / "environ").read_bytes().decode("utf-8", errors="replace")
        orca_env = {}
        for item in raw_env.split("\x00"):
            if item.startswith("ORCA_") and "=" in item:
                k, v = item.split("=", 1)
                orca_env[k] = v
        m = conv_re.search(cmdline)
        conv_id = m.group(1) if m else None
        open_brains = []
        fd_dir = pdir / "fd"
        if fd_dir.is_dir():
            for fd in fd_dir.iterdir():
                try:
                    target = os.readlink(fd)
                    for bm in re.findall(r"brain/([0-9a-f-]{36})", target):
                        if bm not in open_brains:
                            open_brains.append(bm)
                except Exception:
                    pass
        if not conv_id and len(open_brains) == 1:
            conv_id = open_brains[0]
        procs.append({
            "pid": pid,
            "ppid": 0,
            "agent": "antigravity" if first_bin == "agy" else first_bin,
            "command": cmdline,
            "cwd": cwd,
            "conversation_id": conv_id,
            "open_brains": open_brains,
            "paneKey": orca_env.get("ORCA_AGENT_PANE") or orca_env.get("ORCA_PANE_KEY"),
            "tabId": orca_env.get("ORCA_TAB_ID"),
            "terminalHandle": orca_env.get("ORCA_TERMINAL_HANDLE"),
            "worktreeId": orca_env.get("ORCA_WORKTREE_ID"),
        })
    except Exception:
        continue

transcripts = {}
brains_dir = home / ".gemini" / "antigravity-cli" / "brain"
if brains_dir.is_dir():
    bdirs = sorted((d for d in brains_dir.iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime, reverse=True)
    for bdir in bdirs[:20]:
        tpath = bdir / ".system_generated" / "logs" / "transcript.jsonl"
        if not tpath.is_file():
            continue
        try:
            st = tpath.stat()
            with tpath.open("rb") as fh:
                if st.st_size > 65536:
                    fh.seek(st.st_size - 65536)
                tail = fh.read().decode("utf-8", errors="replace")
            last_prompt = ""
            last_created = ""
            for line in reversed(tail.splitlines()):
                if not line.strip().startswith("{"):
                    continue
                obj = json.loads(line)
                if not last_created and isinstance(obj.get("created_at"), str):
                    last_created = obj["created_at"]
                if obj.get("type") == "USER_INPUT" and isinstance(obj.get("content"), str):
                    raw = obj["content"]
                    if "<USER_REQUEST>" in raw and "</USER_REQUEST>" in raw:
                        raw = raw.split("<USER_REQUEST>", 1)[1].split("</USER_REQUEST>", 1)[0]
                    last_prompt = " ".join(raw.strip().split())[:160]
                    break
            transcripts[bdir.name] = {
                "lastPrompt": last_prompt,
                "lastCreatedAt": last_created,
                "updatedAtMs": int(st.st_mtime * 1000),
            }
        except Exception:
            pass

trees = []
work_dir = home / ".w0m" / "work"
if work_dir.is_dir():
    for child in sorted(work_dir.iterdir()):
        if (child / "w0m").is_dir():
            trees.append({"name": child.name, "path": str(child / "w0m"), "agent_id": f"agy:{child.name}", "claimed_tickets": []})

print(json.dumps({
    "hostname": socket.gethostname(),
    "platform": f"{platform.system().lower()}-{platform.machine().lower()}",
    "orcaRuntime": status_rpc.get("result") if status_rpc.get("ok") else None,
    "orcaError": status_rpc.get("error") if not status_rpc.get("ok") else None,
    "terminals": (terms_rpc.get("result") or {}).get("terminals", []) if terms_rpc.get("ok") else [],
    "worktrees": (wts_rpc.get("result") or {}).get("worktrees", []) if wts_rpc.get("ok") else [],
    "sshTargets": (ssh_rpc.get("result") or {}).get("targets", []) if ssh_rpc.get("ok") else [],
    "hookEntries": hook_entries,
    "processes": procs,
    "agentTrees": trees,
    "transcripts": transcripts,
}))
"""


def collect_remote_snapshot(ssh_host: str, *, timeout_s: float = 8.0) -> dict[str, Any]:
    """Gather a complete telemetry snapshot from a remote SSH host (`linux-host`)."""
    try:
        res = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", ssh_host, "python3", "-"],
            input=REMOTE_PROBE_SNIPPET,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if res.returncode != 0:
            return {
                "host": ssh_host,
                "hostname": ssh_host,
                "platform": "unknown",
                "reachable": False,
                "sshError": (res.stderr or res.stdout).strip()[:240],
                "orcaRuntime": None,
                "terminals": [],
                "worktrees": [],
                "sshTargets": [],
                "hookEntries": {},
                "processes": [],
                "agentTrees": [],
                "transcripts": {},
            }
        payload: dict[str, Any] = json.loads(res.stdout.strip().splitlines()[-1])
        payload["host"] = ssh_host
        payload["reachable"] = True
        return payload
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as exc:
        return {
            "host": ssh_host,
            "hostname": ssh_host,
            "platform": "unknown",
            "reachable": False,
            "sshError": str(exc)[:240],
            "orcaRuntime": None,
            "terminals": [],
            "worktrees": [],
            "sshTargets": [],
            "hookEntries": {},
            "processes": [],
            "agentTrees": [],
            "transcripts": {},
        }


def _extract_worktree_path(worktree_id: str | None, fallback_cwd: str = "") -> str:
    if worktree_id and "::" in worktree_id:
        return worktree_id.split("::", 1)[1]
    if worktree_id == "global-floating-terminal":
        return "global-floating-terminal"
    return fallback_cwd or (worktree_id or "")


def correlate_host_sessions(
    snapshot: dict[str, Any],
    *,
    include_dormant: bool = False,
    dormant_limit: int = 10,
) -> list[dict[str, Any]]:
    """Correlate terminals, hook entries, OS processes, agent trees, and transcripts for one host."""
    host = str(snapshot.get("host") or "local")
    terminals: list[dict[str, Any]] = snapshot.get("terminals") or []
    hook_entries: dict[str, dict[str, Any]] = snapshot.get("hookEntries") or {}
    processes: list[dict[str, Any]] = snapshot.get("processes") or []
    agent_trees: list[dict[str, Any]] = snapshot.get("agentTrees") or []
    transcripts: dict[str, dict[str, Any]] = snapshot.get("transcripts") or {}

    term_by_pane: dict[str, dict[str, Any]] = {}
    term_by_handle: dict[str, dict[str, Any]] = {}
    for t in terminals:
        tab_id = t.get("tabId")
        leaf_id = t.get("leafId")
        handle = t.get("handle")
        if tab_id and leaf_id:
            term_by_pane[f"{tab_id}:{leaf_id}"] = t
        if handle:
            term_by_handle[str(handle)] = t

    proc_by_pane: dict[str, dict[str, Any]] = {}
    proc_by_conv: dict[str, dict[str, Any]] = {}
    unmatched_procs: list[dict[str, Any]] = []
    for p in processes:
        pk = p.get("paneKey")
        cid = p.get("conversation_id")
        if pk:
            proc_by_pane[str(pk)] = p
        if cid:
            proc_by_conv[str(cid)] = p
        if not pk and not cid:
            unmatched_procs.append(p)

    # Map agent trees by path and recent ticket references
    tree_names = [t["name"] for t in agent_trees if isinstance(t.get("name"), str)]

    sessions_by_key: dict[str, dict[str, Any]] = {}
    seen_convs: set[str] = set()
    seen_pids: set[int] = set()

    # 1. Start from Orca hook entries (richest state + paneKey + providerSession.id)
    for pane_key, entry in hook_entries.items():
        prov = entry.get("providerSession") or {}
        conv_id = str(prov.get("id") or "")
        payload = entry.get("payload") or {}
        proc = proc_by_pane.get(pane_key) or (proc_by_conv.get(conv_id) if conv_id else None)
        term = term_by_pane.get(pane_key)
        if not term and proc and proc.get("terminalHandle"):
            term = term_by_handle.get(str(proc["terminalHandle"]))

        pid = int(proc["pid"]) if proc and proc.get("pid") else None
        if pid is not None:
            seen_pids.add(pid)
        if conv_id:
            seen_convs.add(conv_id)

        raw_state = str(payload.get("state") or "unknown")
        if pid is None and term is None:
            effective_state = "dormant"
        elif raw_state == "done" and pid is not None:
            effective_state = "tui-idle"
        else:
            effective_state = raw_state

        wt_id = str(entry.get("worktreeId") or (term or {}).get("worktreeId") or (proc or {}).get("worktreeId") or "")
        wt_path = str((term or {}).get("worktreePath") or _extract_worktree_path(wt_id, (proc or {}).get("cwd", "")))
        prompt = str(payload.get("prompt") or "")
        if not prompt and conv_id and conv_id in transcripts:
            prompt = str(transcripts[conv_id].get("lastPrompt") or "")

        matched_tree = ""
        for tree_obj in agent_trees:
            tname = str(tree_obj.get("name") or "")
            if not tname:
                continue
            if tname in prompt or tname in wt_path:
                matched_tree = tname
                break
            for c_tid in tree_obj.get("claimed_tickets") or []:
                if re.search(rf"\b{re.escape(str(c_tid))}\b", prompt, re.I):
                    matched_tree = tname
                    break
            if matched_tree:
                break

        record_key = conv_id or f"pane:{pane_key}"
        sessions_by_key[record_key] = {
            "host": host,
            "conversation_id": conv_id or None,
            "agent": str(payload.get("agentType") or entry.get("source") or (proc or {}).get("agent") or "antigravity"),
            "state": effective_state,
            "hookState": raw_state,
            "pid": pid,
            "worktreeId": wt_id or None,
            "worktreePath": wt_path or None,
            "tabId": str(entry.get("tabId") or (term or {}).get("tabId") or (proc or {}).get("tabId") or "") or None,
            "paneKey": pane_key,
            "terminalHandle": str((term or {}).get("handle") or (proc or {}).get("terminalHandle") or "") or None,
            "terminalTitle": str((term or {}).get("title") or "") or None,
            "agentTree": matched_tree or None,
            "prompt": " ".join(prompt.split())[:140],
            "updatedAtMs": int(entry.get("evidenceObservedAt") or entry.get("receivedAt") or 0),
        }

    # 2. Add any live processes that were not in hook_entries
    for proc in processes:
        pid = int(proc["pid"])
        if pid in seen_pids:
            continue
        seen_pids.add(pid)
        conv_id = str(proc.get("conversation_id") or "")
        if conv_id:
            seen_convs.add(conv_id)
        pane_key = str(proc.get("paneKey") or "")
        term = term_by_pane.get(pane_key) if pane_key else None
        if not term and proc.get("terminalHandle"):
            term = term_by_handle.get(str(proc["terminalHandle"]))
        wt_id = str(proc.get("worktreeId") or (term or {}).get("worktreeId") or "")
        wt_path = str((term or {}).get("worktreePath") or _extract_worktree_path(wt_id, str(proc.get("cwd") or "")))
        t_info = transcripts.get(conv_id, {}) if conv_id else {}
        prompt = str(t_info.get("lastPrompt") or "")

        matched_tree = ""
        for tree_obj in agent_trees:
            tname = str(tree_obj.get("name") or "")
            if not tname:
                continue
            if tname in prompt or tname in wt_path:
                matched_tree = tname
                break
            for c_tid in tree_obj.get("claimed_tickets") or []:
                if re.search(rf"\b{re.escape(str(c_tid))}\b", prompt, re.I):
                    matched_tree = tname
                    break
            if matched_tree:
                break

        record_key = conv_id or f"pid:{pid}"
        sessions_by_key[record_key] = {
            "host": host,
            "conversation_id": conv_id or None,
            "agent": str(proc.get("agent") or "antigravity"),
            "state": "tui-idle",
            "hookState": None,
            "pid": pid,
            "worktreeId": wt_id or None,
            "worktreePath": wt_path or None,
            "tabId": str(proc.get("tabId") or (term or {}).get("tabId") or "") or None,
            "paneKey": pane_key or None,
            "terminalHandle": str(proc.get("terminalHandle") or (term or {}).get("handle") or "") or None,
            "terminalTitle": str((term or {}).get("title") or "") or None,
            "agentTree": matched_tree or None,
            "prompt": prompt[:140],
            "updatedAtMs": int(t_info.get("updatedAtMs") or 0),
        }

    # 3. Optionally include dormant transcripts from ~/.gemini/antigravity-cli/brain/<uuid>/
    if include_dormant:
        dormant_added = 0
        for conv_id, t_info in transcripts.items():
            if conv_id in seen_convs:
                continue
            if dormant_added >= dormant_limit:
                break
            dormant_added += 1
            prompt = str(t_info.get("lastPrompt") or "")
            sessions_by_key[conv_id] = {
                "host": host,
                "conversation_id": conv_id,
                "agent": "antigravity",
                "state": "dormant",
                "hookState": None,
                "pid": None,
                "worktreeId": None,
                "worktreePath": None,
                "tabId": None,
                "paneKey": None,
                "terminalHandle": None,
                "terminalTitle": None,
                "agentTree": None,
                "prompt": prompt[:140],
                "updatedAtMs": int(t_info.get("updatedAtMs") or 0),
            }

    def _sort_key(item: dict[str, Any]) -> tuple[int, int]:
        st = str(item.get("state") or "")
        rank = 0 if st in ACTIVE_STATES else (1 if item.get("pid") is not None else 2)
        return (rank, -int(item.get("updatedAtMs") or 0))

    return sorted(sessions_by_key.values(), key=_sort_key)


def check_single_writer_guard(
    sessions: list[dict[str, Any]],
    conversation_id: str,
    *,
    rebind_idle: bool = False,
) -> dict[str, Any]:
    """Verify single-writer PID lock before attaching `conversation_id` (`T596` AC2).

    Returns:
      {
        "allowed": bool,
        "action": "attach_dormant" | "rebind_idle" | "refuse_active_writer" | "refuse_working",
        "existing": dict | None,
        "reason": str,
      }
    """
    existing = next(
        (s for s in sessions if s.get("conversation_id") == conversation_id and s.get("pid") is not None),
        None,
    )
    if existing is None:
        return {
            "allowed": True,
            "action": "attach_dormant",
            "existing": None,
            "reason": f"No active writer PID holds conversation {conversation_id}; safe to attach.",
        }

    pid = existing.get("pid")
    state = str(existing.get("state") or "unknown")
    pane = existing.get("paneKey") or existing.get("terminalHandle") or "unknown-pane"
    wt = existing.get("worktreePath") or existing.get("worktreeId") or "unknown-worktree"

    if not rebind_idle:
        return {
            "allowed": False,
            "action": "refuse_active_writer",
            "existing": existing,
            "reason": (
                f"Single-writer lock guard refused attach: conversation {conversation_id} "
                f"is already held by live PID {pid} (state={state}, worktree={wt}, pane={pane}). "
                f"Pass --rebind-idle to gracefully stop an idle session and rebind it."
            ),
        }

    if state in ACTIVE_STATES:
        return {
            "allowed": False,
            "action": "refuse_working",
            "existing": existing,
            "reason": (
                f"Single-writer lock guard refused --rebind-idle: conversation {conversation_id} "
                f"is actively {state} on PID {pid} (worktree={wt}, pane={pane}). Wait for turn completion."
            ),
        }

    return {
        "allowed": True,
        "action": "rebind_idle",
        "existing": existing,
        "reason": (
            f"Session {conversation_id} is idle (state={state}, PID={pid}, worktree={wt}); "
            f"graceful stop + rebind permitted."
        ),
    }


def _resolve_worktree_path(worktree_arg: str, snapshot: dict[str, Any]) -> str:
    """Resolve a tree short name (`agy-orca`), `root`/`beta`, or path into an absolute filesystem path."""
    raw = worktree_arg.strip()
    if raw.startswith("path:"):
        raw = raw[5:]
    # Check agentTrees by name first (e.g. `agy-orca` or `agent/agy-orca`)
    short_name = raw.removeprefix("agent/")
    for tree in snapshot.get("agentTrees") or []:
        if tree.get("name") == short_name and isinstance(tree.get("path"), str):
            return str(tree["path"])
    # Check `root` / `main` / `beta`
    if raw in ("root", "main", "beta"):
        for wt in snapshot.get("worktrees") or []:
            if wt.get("isMainWorktree") and isinstance(wt.get("path"), str) and wt["path"].endswith("/w0m"):
                return str(wt["path"])
    # Check registered Orca worktrees by displayName or branch
    for wt in snapshot.get("worktrees") or []:
        if (
            wt.get("displayName") == raw
            or wt.get("branch") in (raw, f"refs/heads/{raw}", f"refs/heads/agent/{short_name}")
            or wt.get("id") == raw
        ) and isinstance(wt.get("path"), str):
            return str(wt["path"])
    return str(Path(raw).expanduser())


def _resolve_worktree_selector(worktree_arg: str, snapshot: dict[str, Any]) -> str:
    """Resolve a tree short name (`agy-orca`), `root`/`beta`, path, or selector into an Orca worktreeId or path."""
    if worktree_arg in ("active", "current") or worktree_arg.startswith(("id:", "path:", "name:", "branch:")):
        return worktree_arg
    norm_path = _resolve_worktree_path(worktree_arg, snapshot)
    for wt in snapshot.get("worktrees") or []:
        if wt.get("path") == norm_path and isinstance(wt.get("id"), str):
            return str(wt["id"])
    return norm_path


def spawn_session(
    worktree_target: str,
    *,
    host: str = "local",
    ticket: str | None = None,
    track: str | None = None,
    title: str | None = None,
    command: str | None = None,
    focus: bool = True,
    dry_run: bool = False,
    snapshot_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Spawn a new Orca terminal/agent session targeted at `worktree_target` (`agy-orca`, `root`, or path)."""
    eff_host = normalize_host_target(host)
    snapshot = snapshot_override or (
        collect_local_snapshot(host_label="local")
        if eff_host == "local"
        else collect_remote_snapshot(eff_host)
    )
    if not snapshot.get("reachable"):
        return {
            "ok": False,
            "host": host,
            "worktree": worktree_target,
            "error": f"Host {host} is unreachable: {snapshot.get('sshError') or 'unknown error'}",
        }

    wt_path = _resolve_worktree_path(worktree_target, snapshot)
    wt_selector = _resolve_worktree_selector(worktree_target, snapshot)
    short_handle = Path(wt_path).parent.name if "/.w0m/work/" in wt_path else Path(wt_path).name

    parts: list[str] = []
    if track and track.strip():
        parts.append(track.strip())
    if ticket and ticket.strip():
        parts.append(ticket.strip().upper())
    parts.append((title or f"Session {short_handle}").strip())
    formatted_title = f"{' · '.join(parts)} [{short_handle}]"

    if dry_run:
        return {
            "ok": True,
            "dryRun": True,
            "host": host,
            "worktree": wt_selector,
            "worktreePath": wt_path,
            "title": formatted_title,
            "command": command,
        }

    if eff_host == "local":
        cli_bin = resolve_local_orca_cli()
        cmd_list = [cli_bin, "terminal", "create", "--worktree", f"path:{wt_path}", "--title", formatted_title]
        if command:
            cmd_list.extend(["--command", command])
        if focus:
            cmd_list.append("--focus")
        cmd_list.append("--json")
        proc_res = subprocess.run(cmd_list, capture_output=True, text=True, timeout=10.0)
        if proc_res.returncode == 0:
            try:
                create_res = json.loads(proc_res.stdout)
            except ValueError:
                create_res = {"ok": True, "result": {"raw": proc_res.stdout.strip()}}
        else:
            create_res = {"ok": False, "error": (proc_res.stderr or proc_res.stdout).strip()}
    else:
        cmd_flag = f" --command '{command}'" if command else ""
        focus_flag = " --focus" if focus else ""
        remote_cmd = (
            f"~/.local/bin/orca terminal create --worktree path:{wt_path} "
            f"--title '{formatted_title}'{cmd_flag}{focus_flag} --json"
        )
        proc_res = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", host, remote_cmd],
            capture_output=True,
            text=True,
            timeout=10.0,
        )
        if proc_res.returncode == 0:
            try:
                create_res = json.loads(proc_res.stdout)
            except ValueError:
                create_res = {"ok": True, "result": {"raw": proc_res.stdout.strip()}}
        else:
            create_res = {"ok": False, "error": (proc_res.stderr or proc_res.stdout).strip()}

    return {
        "ok": bool(create_res.get("ok")),
        "host": host,
        "worktree": wt_selector,
        "worktreePath": wt_path,
        "title": formatted_title,
        "command": command,
        "terminal": create_res.get("result"),
        "error": create_res.get("error") if not create_res.get("ok") else None,
    }


def attach_session(
    conversation_id: str,
    worktree_target: str,
    *,
    host: str = "local",
    rebind_idle: bool = False,
    dry_run: bool = False,
    snapshot_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Safely attach or rebind `conversation_id` into `worktree_target` on `host` (`T596` AC2)."""
    eff_host = normalize_host_target(host)
    snapshot = snapshot_override or (
        collect_local_snapshot(host_label="local")
        if eff_host == "local"
        else collect_remote_snapshot(eff_host)
    )
    if not snapshot.get("reachable"):
        return {
            "ok": False,
            "host": host,
            "conversation_id": conversation_id,
            "error": f"Host {host} is unreachable: {snapshot.get('sshError') or 'unknown error'}",
        }

    sessions = correlate_host_sessions(snapshot, include_dormant=True, dormant_limit=50)
    verdict = check_single_writer_guard(sessions, conversation_id, rebind_idle=rebind_idle)
    if not verdict["allowed"]:
        return {
            "ok": False,
            "host": host,
            "conversation_id": conversation_id,
            "guard": verdict,
            "error": verdict["reason"],
        }

    resolved_wt = _resolve_worktree_selector(worktree_target, snapshot)
    attach_cmd = f"agy --conversation={conversation_id} --dangerously-skip-permissions"

    if dry_run:
        return {
            "ok": True,
            "dryRun": True,
            "host": host,
            "conversation_id": conversation_id,
            "worktree": resolved_wt,
            "command": attach_cmd,
            "guard": verdict,
        }

    existing = verdict.get("existing")
    if verdict["action"] == "rebind_idle" and isinstance(existing, dict):
        old_pid = existing.get("pid")
        old_handle = existing.get("terminalHandle")
        if eff_host == "local":
            if isinstance(old_pid, int):
                try:
                    os.kill(old_pid, signal.SIGTERM)
                except OSError:
                    pass
                for _ in range(20):
                    try:
                        os.kill(old_pid, 0)
                        time.sleep(0.1)
                    except OSError:
                        break
            if isinstance(old_handle, str) and old_handle and existing.get("worktreeId") == "global-floating-terminal":
                orca_rpc_call("terminal.close", {"handle": old_handle})
        else:
            if isinstance(old_pid, int):
                subprocess.run(
                    ["ssh", "-o", "BatchMode=yes", eff_host, f"kill -TERM {old_pid} 2>/dev/null || true"],
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                )

    if eff_host == "local":
        create_res = orca_rpc_call(
            "terminal.create",
            {
                "worktree": resolved_wt,
                "title": f"agy:{conversation_id[:8]}",
                "command": attach_cmd,
            },
        )
        if not create_res.get("ok"):
            cli_bin = resolve_local_orca_cli()
            proc_res = subprocess.run(
                [cli_bin, "terminal", "create", "--worktree", f"path:{worktree_target}", "--command", attach_cmd, "--json"],
                capture_output=True,
                text=True,
                timeout=10.0,
            )
            if proc_res.returncode == 0:
                try:
                    parsed_local: dict[str, Any] = json.loads(proc_res.stdout)
                    create_res = parsed_local
                except ValueError:
                    create_res = {"ok": True, "result": {"raw": proc_res.stdout.strip()}}
    else:
        remote_cmd = (
            f"~/.local/bin/orca terminal create --worktree path:{worktree_target} "
            f"--command '{attach_cmd}' --json"
        )
        proc_res = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", eff_host, remote_cmd],
            capture_output=True,
            text=True,
            timeout=10.0,
        )
        try:
            if proc_res.returncode == 0:
                parsed_remote: dict[str, Any] = json.loads(proc_res.stdout)
                create_res = parsed_remote
            else:
                create_res = {
                    "ok": False,
                    "error": (proc_res.stderr or proc_res.stdout).strip(),
                }
        except ValueError:
            create_res = {"ok": proc_res.returncode == 0, "result": {"raw": proc_res.stdout.strip()}}

    return {
        "ok": bool(create_res.get("ok")),
        "host": host,
        "conversation_id": conversation_id,
        "worktree": resolved_wt,
        "command": attach_cmd,
        "guard": verdict,
        "terminal": create_res.get("result"),
        "error": create_res.get("error") if not create_res.get("ok") else None,
    }


def ensure_ssh_target(
    alias: str = "linux-host",
    *,
    user_data_path: Path | None = None,
    connect: bool = True,
) -> dict[str, Any]:
    """Ensure `alias` is registered in the local Orca runtime's SSH target catalog (`T596` AC3)."""
    list_res = orca_rpc_call("ssh.listTargets", user_data_path=user_data_path)
    if not list_res.get("ok"):
        return {"ok": False, "alias": alias, "error": list_res.get("error")}

    targets: list[dict[str, Any]] = (list_res.get("result") or {}).get("targets", [])
    existing = next(
        (t for t in targets if t.get("configHost") == alias or t.get("label") == alias),
        None,
    )
    created = False
    if existing is None:
        cfg = DEFAULT_SSH_TARGET_CONFIG.get(
            alias,
            {
                "label": alias,
                "configHost": alias,
                "host": alias,
                "port": 22,
                "username": os.environ.get("USER", "aleksei"),
                "allowRemoteCliControl": True,
            },
        )
        add_res = orca_rpc_call("ssh.addTarget", {"target": cfg}, user_data_path=user_data_path)
        if not add_res.get("ok"):
            return {"ok": False, "alias": alias, "error": add_res.get("error")}
        existing = (add_res.get("result") or {}).get("target")
        created = True

    if connect and isinstance(existing, dict) and existing.get("id") and not existing.get("connected"):
        orca_rpc_call(
            "ssh.connect",
            {"targetId": existing["id"]},
            user_data_path=user_data_path,
            timeout_s=5.0,
        )
        refreshed = orca_rpc_call("ssh.listTargets", user_data_path=user_data_path)
        if refreshed.get("ok"):
            for t in (refreshed.get("result") or {}).get("targets", []):
                if t.get("id") == existing["id"]:
                    existing = t
                    break

    return {
        "ok": True,
        "alias": alias,
        "created": created,
        "target": existing,
    }


def format_sessions_table(sessions: list[dict[str, Any]]) -> str:
    """Format correlated multi-host sessions as an aligned Markdown/CLI table."""
    if not sessions:
        return "No agent sessions discovered."
    lines = [
        "| Host | Conversation ID | Agent | State | PID | Worktree / Scope | Tree | Pane / Handle | Last Prompt |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in sessions:
        host = str(s.get("host") or "local")
        cid = str(s.get("conversation_id") or "(untracked)")
        agent = str(s.get("agent") or "antigravity")
        state = str(s.get("state") or "unknown")
        pid = str(s.get("pid") if s.get("pid") is not None else "-")
        wt = str(s.get("worktreePath") or s.get("worktreeId") or "-")
        wt_short = wt.replace("/Users/proto/Projects/", "~/Projects/").replace(
            "/home/aleksei/Projects/", "~/Projects/"
        )
        tree = str(s.get("agentTree") or "-")
        handle = str(s.get("terminalHandle") or s.get("paneKey") or "-")
        if len(handle) > 22:
            handle = handle[:22] + "…"
        prompt = str(s.get("prompt") or "").replace("|", "\\|").replace("\n", " ")
        if len(prompt) > 64:
            prompt = prompt[:61] + "..."
        lines.append(
            f"| `{host}` | `{cid}` | `{agent}` | `{state}` | `{pid}` | `{wt_short}` | `{tree}` | `{handle}` | {prompt} |"
        )
    return "\n".join(lines)


EXPECTED_ORCA_VERSION_PREFIX = "1.4."


def verify_orca_runtime_service_and_version(
    rt: dict[str, Any] | None,
    expected_prefix: str = EXPECTED_ORCA_VERSION_PREFIX,
) -> tuple[bool, bool, str]:
    """Verify that the replying Orca RPC daemon reports expected service identity (`runtimeId` + `ready`) and expected version."""
    if not isinstance(rt, dict) or not rt.get("runtimeId"):
        return False, False, "offline"
    service_ok = bool(rt.get("runtimeId")) and rt.get("ready", True) is not False
    actual_version = str(rt.get("appVersion") or "")
    version_ok = actual_version.startswith(expected_prefix) if actual_version else False
    return service_ok, version_ok, actual_version or "unknown"


def format_hosts_table(snapshots: list[dict[str, Any]], sessions_by_host: dict[str, list[dict[str, Any]]]) -> str:
    """Format multi-host Orca runtime and SSH connectivity summary."""
    lines = [
        "| Host | Hostname (`platform`) | Reachable | Orca Runtime (`version`) | Service+Version OK | Terminals | Live Sessions | SSH Targets |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for snap in snapshots:
        host = str(snap.get("host") or "local")
        hname = f"{snap.get('hostname', host)} ({snap.get('platform', 'unknown')})"
        reachable = "yes" if snap.get("reachable") else "no"
        rt = snap.get("orcaRuntime") or {}
        svc_ok, ver_ok, actual_ver = verify_orca_runtime_service_and_version(rt)
        if svc_ok:
            rt_str = f"ready ({str(rt.get('runtimeId'))[:8]} / {actual_ver})"
            probe_ok_str = f"yes (orca {actual_ver})" if ver_ok else f"version-mismatch ({actual_ver} != {EXPECTED_ORCA_VERSION_PREFIX}*)"
        else:
            rt_str = "offline"
            probe_ok_str = "no"
        terms_count = len(snap.get("terminals") or [])
        host_sessions = sessions_by_host.get(host, [])
        live_count = sum(1 for s in host_sessions if s.get("pid") is not None)
        ssh_targets = snap.get("sshTargets") or []
        ssh_desc = ", ".join(
            f"{t.get('label', t.get('id'))}:{'connected' if t.get('connected') else 'idle'}"
            for t in ssh_targets[:4]
        ) or "-"
        lines.append(
            f"| `{host}` | `{hname}` | `{reachable}` | `{rt_str}` | `{probe_ok_str}` | `{terms_count}` | `{live_count}` | {ssh_desc} |"
        )
    return "\n".join(lines)


def format_worktrees_table(snapshots: list[dict[str, Any]]) -> str:
    """Format Orca worktree targets and active agent trees across hosts."""
    lines = [
        "| Host | Display Name | Branch | Status | Main / Child | Path |",
        "|---|---|---|---|---|---|",
    ]
    count = 0
    for snap in snapshots:
        host = str(snap.get("host") or "local")
        for wt in snap.get("worktrees") or []:
            count += 1
            dname = str(wt.get("displayName") or "-")
            branch = str(wt.get("branch") or "-").replace("refs/heads/", "")
            status = str(wt.get("workspaceStatus") or "-")
            lineage = "main" if wt.get("isMainWorktree") else ("child" if wt.get("parentWorktreeId") else "external")
            path = str(wt.get("path") or "-")
            lines.append(f"| `{host}` | `{dname}` | `{branch}` | `{status}` | `{lineage}` | `{path}` |")
    return "\n".join(lines) if count > 0 else "No Orca worktrees discovered."


def _select_hosts(
    host_arg: str,
    *,
    sys_platform: str | None = None,
    hostname: str | None = None,
) -> list[str]:
    if host_arg == "all":
        return ["local", *get_default_remote_hosts(sys_platform=sys_platform, hostname=hostname)]
    selected: list[str] = []
    for raw_h in host_arg.split(","):
        h = raw_h.strip()
        if not h:
            continue
        norm = normalize_host_target(h, sys_platform=sys_platform, hostname=hostname)
        if norm not in selected:
            selected.append(norm)
    return selected


def _collect_local_projects_status(home_dir: Path | None = None) -> list[dict[str, Any]]:
    """Inspect local project repositories under `~/Projects/!self/w0m` and `~/Projects/!proj/*`."""
    home = home_dir or Path.home()
    projects: list[dict[str, Any]] = []
    candidates: list[tuple[str, Path]] = [("w0m", home / "Projects" / "!self" / "w0m")]
    proj_root = home / "Projects" / "!proj"
    if proj_root.is_dir():
        for child in sorted(proj_root.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                candidates.append((child.name, child))

    for pid, pdir in candidates:
        if not pdir.is_dir():
            continue
        git_dir = pdir / ".git"
        branch = "-"
        dirty = 0
        head = ""
        if git_dir.exists():
            try:
                branch = subprocess.run(
                    ["git", "-C", str(pdir), "branch", "--show-current"],
                    capture_output=True,
                    text=True,
                    timeout=3.0,
                ).stdout.strip() or "HEAD"
                head = subprocess.run(
                    ["git", "-C", str(pdir), "rev-parse", "--short", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=3.0,
                ).stdout.strip()
                st = subprocess.run(
                    ["git", "-C", str(pdir), "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                    timeout=3.0,
                ).stdout.splitlines()
                dirty = sum(1 for line in st if line.strip())
            except (OSError, subprocess.SubprocessError):
                pass
        projects.append(
            {
                "id": pid,
                "path": str(pdir),
                "branch": branch,
                "head": head,
                "dirtyCount": dirty,
            }
        )
    return projects


def format_workload_markdown(payload: dict[str, Any]) -> str:
    """Render a private Markdown dashboard for cross-host project and agent workload state (`T599` AC1)."""
    lines = [
        f"# Private Cross-Host Project & Agent Workload Snapshot (`{payload.get('generatedAt', '')}`)",
        "",
        "> **Private State (`~/.w0m/state/workload/`) — mode `0700`/`0600`, excluded from public Git.**",
        "",
        "## 1. Orca Hosts & Runtime Summary",
        "",
        "| Host | Hostname (`platform`) | Reachable | Terminals | Live Sessions | Worktrees | Agent Trees |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for h in payload.get("hosts") or []:
        lines.append(
            f"| `{h.get('host')}` | `{h.get('hostname')} ({h.get('platform')})` | "
            f"`{'yes' if h.get('reachable') else 'no'}` | {h.get('terminalCount', 0)} | "
            f"{h.get('liveSessionCount', 0)} | {h.get('worktreeCount', 0)} | {len(h.get('agentTrees') or [])} |"
        )

    lines.extend(
        [
            "",
            "## 2. Active & Dormant Agent Sessions Across Hosts",
            "",
            format_sessions_table(payload.get("sessions") or []),
            "",
            "## 3. Local Projects & Worktree Hygiene",
            "",
            "| Project | Path | Branch | HEAD | Dirty Files |",
            "|---|---|---|---|---:|",
        ]
    )
    for proj in payload.get("localProjects") or []:
        lines.append(
            f"| `{proj.get('id')}` | `{proj.get('path')}` | `{proj.get('branch')}` | "
            f"`{proj.get('head') or '-'}` | {proj.get('dirtyCount', 0)} |"
        )

    claims = payload.get("agentClaims") or {}
    lines.extend(
        [
            "",
            f"## 4. Virtual Agent Claims (`{len(claims)}` recorded)",
            "",
            "| Ticket | Agent ID | Track | Session Title | Terminal Handle |",
            "|---|---|---|---|---|",
        ]
    )
    for tid, info in sorted(claims.items()):
        if not isinstance(info, dict):
            continue
        lines.append(
            f"| `{tid}` | `{info.get('agent_id', '-')}` | `{info.get('track') or '-'}` | "
            f"{info.get('session_title') or '-'} | `{info.get('orca_terminal_handle') or '-'}` |"
        )

    archived = payload.get("archivedSessions") or []
    if archived:
        lines.extend(
            [
                "",
                "## 5. Privately Archived Session Artifacts (`~/.w0m/state/sessions/`)",
                "",
                "| Host | Conversation ID | Artifact Count | Path |",
                "|---|---|---:|---|",
            ]
        )
        for item in archived:
            lines.append(
                f"| `{item.get('host')}` | `{item.get('conversation_id')}` | "
                f"{item.get('artifactCount', 0)} | `{item.get('path')}` |"
            )

    return "\n".join(lines) + "\n"


def save_private_workload_state(
    *,
    hosts: list[str] | None = None,
    state_dir: Path | None = None,
    home_dir: Path | None = None,
    include_dormant: bool = True,
    dormant_limit: int = 15,
    sync_hosts: bool = False,
    snapshots_override: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Persist cross-host project and agent workload state privately to `~/.w0m/state/workload/` (`T599` AC1)."""
    home = home_dir or Path.home()
    base_state = home / ".w0m" / "state"
    target_dir = state_dir or (base_state / "workload")
    base_state.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(base_state, 0o700)
        os.chmod(target_dir, 0o700)
    except OSError:
        pass

    target_hosts = hosts or ["local", *get_default_remote_hosts()]
    snapshots: list[dict[str, Any]] = []
    sessions_by_host: dict[str, list[dict[str, Any]]] = {}
    all_sessions: list[dict[str, Any]] = []

    if snapshots_override is not None:
        snapshots = list(snapshots_override)
        for snap in snapshots:
            h = str(snap.get("host") or "local")
            hs = correlate_host_sessions(snap, include_dormant=include_dormant, dormant_limit=dormant_limit)
            sessions_by_host[h] = hs
            all_sessions.extend(hs)
    else:
        for h in target_hosts:
            snap = (
                collect_local_snapshot(host_label="local", home_dir=home, dormant_limit=dormant_limit)
                if h == "local"
                else collect_remote_snapshot(h)
            )
            snapshots.append(snap)
            hs = correlate_host_sessions(snap, include_dormant=include_dormant, dormant_limit=dormant_limit)
            sessions_by_host[h] = hs
            all_sessions.extend(hs)

    reg_path = home / ".w0m" / "agents" / "registry.json"
    agent_claims: dict[str, Any] = {}
    if reg_path.is_file():
        try:
            raw_reg = json.loads(reg_path.read_text(encoding="utf-8"))
            if isinstance(raw_reg, dict) and isinstance(raw_reg.get("claims"), dict):
                agent_claims = raw_reg["claims"]
        except (OSError, ValueError):
            pass

    archived_sessions: list[dict[str, Any]] = []
    sess_archive_root = base_state / "sessions"
    if sess_archive_root.is_dir():
        for host_dir in sorted(sess_archive_root.iterdir()):
            if not host_dir.is_dir():
                continue
            for conv_dir in sorted(host_dir.iterdir()):
                if not conv_dir.is_dir():
                    continue
                md_files = sorted(p.name for p in conv_dir.glob("*.md"))
                archived_sessions.append(
                    {
                        "host": host_dir.name,
                        "conversation_id": conv_dir.name,
                        "artifactCount": len(md_files),
                        "artifacts": md_files,
                        "path": str(conv_dir),
                    }
                )

    ts_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ts_slug = time.strftime("%Y%m%d-%H%M%S", time.gmtime())

    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "generatedAt": ts_iso,
        "private": True,
        "hosts": [
            {
                "host": s.get("host"),
                "hostname": s.get("hostname"),
                "platform": s.get("platform"),
                "reachable": s.get("reachable"),
                "orcaRuntime": s.get("orcaRuntime"),
                "terminalCount": len(s.get("terminals") or []),
                "worktreeCount": len(s.get("worktrees") or []),
                "liveSessionCount": sum(
                    1 for sess in sessions_by_host.get(str(s.get("host")), []) if sess.get("pid") is not None
                ),
                "agentTrees": s.get("agentTrees") or [],
            }
            for s in snapshots
        ],
        "sessions": all_sessions,
        "localProjects": _collect_local_projects_status(home),
        "agentClaims": agent_claims,
        "archivedSessions": archived_sessions,
    }

    latest_json = target_dir / "latest.json"
    history_json = target_dir / f"workload-{ts_slug}.json"
    latest_md = target_dir / "latest.md"

    json_text = json.dumps(payload, indent=2) + "\n"
    md_text = format_workload_markdown(payload)

    latest_json.write_text(json_text, encoding="utf-8")
    history_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    for fpath in (latest_json, history_json, latest_md):
        try:
            os.chmod(fpath, 0o600)
        except OSError:
            pass

    synced_remotes: list[str] = []
    if sync_hosts:
        for rh in target_hosts:
            if rh == "local":
                continue
            try:
                remote_script = (
                    "mkdir -p ~/.w0m/state/workload && chmod 700 ~/.w0m/state ~/.w0m/state/workload && "
                    "cat > ~/.w0m/state/workload/latest.json && chmod 600 ~/.w0m/state/workload/latest.json"
                )
                cp = subprocess.run(
                    ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", rh, remote_script],
                    input=json_text,
                    capture_output=True,
                    text=True,
                    timeout=8.0,
                )
                if cp.returncode == 0:
                    synced_remotes.append(rh)
            except (OSError, subprocess.SubprocessError):
                pass

    return {
        "ok": True,
        "generatedAt": ts_iso,
        "latestJson": str(latest_json),
        "historyJson": str(history_json),
        "latestMd": str(latest_md),
        "hostCount": len(payload["hosts"]),
        "sessionCount": len(all_sessions),
        "archivedSessionCount": len(archived_sessions),
        "syncedRemotes": synced_remotes,
        "payload": payload,
    }


def load_private_workload_state(*, state_dir: Path | None = None, home_dir: Path | None = None) -> dict[str, Any]:
    """Load the latest saved private cross-host workload snapshot (`T599` AC1)."""
    home = home_dir or Path.home()
    target_dir = state_dir or (home / ".w0m" / "state" / "workload")
    latest_json = target_dir / "latest.json"
    if not latest_json.is_file():
        return {"ok": False, "error": f"No saved workload state at {latest_json}"}
    try:
        data: dict[str, Any] = json.loads(latest_json.read_text(encoding="utf-8"))
        return {"ok": True, "path": str(latest_json), "payload": data}
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}


def archive_host_sessions(
    host: str = "linux-host",
    *,
    conversation_ids: list[str] | None = None,
    close_terminals: bool = False,
    dest_root: Path | None = None,
    home_dir: Path | None = None,
) -> dict[str, Any]:
    """Collect brain Markdown artifacts from `host` into `~/.w0m/state/sessions/<host>/` and optionally close tabs (`T599` AC1/AC2)."""
    home = home_dir or Path.home()
    base_dest = dest_root or (home / ".w0m" / "state" / "sessions" / host)
    base_dest.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(base_dest.parent, 0o700)
        os.chmod(base_dest, 0o700)
    except OSError:
        pass

    eff_host = normalize_host_target(host)
    snap = collect_local_snapshot(host_label="local", home_dir=home) if eff_host == "local" else collect_remote_snapshot(eff_host)
    sessions = correlate_host_sessions(snap, include_dormant=True, dormant_limit=25)
    target_cids = conversation_ids or [
        str(s["conversation_id"])
        for s in sessions
        if s.get("conversation_id") and ("w0m" in str(s.get("worktreePath") or "") or s.get("state") != "working")
    ]

    collected: list[dict[str, Any]] = []
    for cid in target_cids:
        if not UUID_RE.fullmatch(cid):
            continue
        cdir = base_dest / cid
        cdir.mkdir(parents=True, exist_ok=True)
        if eff_host == "local":
            src_dir = home / ".gemini" / "antigravity-cli" / "brain" / cid
            if src_dir.is_dir():
                for md in src_dir.glob("*.md"):
                    (cdir / md.name).write_bytes(md.read_bytes())
        else:
            cmd = f"cd ~/.gemini/antigravity-cli/brain/{cid} && tar -cf - *.md 2>/dev/null || true"
            try:
                p1 = subprocess.Popen(["ssh", "-o", "BatchMode=yes", eff_host, cmd], stdout=subprocess.PIPE)
                p2 = subprocess.Popen(["tar", "-xf", "-", "-C", str(cdir)], stdin=p1.stdout)
                if p1.stdout:
                    p1.stdout.close()
                p2.communicate(timeout=15.0)
            except (OSError, subprocess.SubprocessError):
                pass
        files = sorted(p.name for p in cdir.glob("*.md"))
        collected.append({"conversation_id": cid, "artifactCount": len(files), "artifacts": files, "path": str(cdir)})

    closed_handles: list[str] = []
    if close_terminals:
        cli_bin = resolve_local_orca_cli(home)
        for term in snap.get("terminals") or []:
            wt_path = str(term.get("worktreePath") or "")
            handle = str(term.get("handle") or "")
            if not handle or "w0m" not in wt_path:
                continue
            cmd_list = [cli_bin, "terminal", "close", "--terminal", handle, "--tab", "--json"]
            if eff_host != "local":
                cmd_list.extend(["--environment", eff_host])
            try:
                res = subprocess.run(cmd_list, capture_output=True, text=True, timeout=10.0)
                if res.returncode == 0:
                    closed_handles.append(handle)
            except (OSError, subprocess.SubprocessError):
                pass

    return {
        "ok": True,
        "host": host,
        "collected": collected,
        "closedTerminals": closed_handles,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Multi-host Orca instance and agent session orchestration (T596 / T599)."
    )
    sub = parser.add_subparsers(dest="subcommand")

    # list (also default)
    p_list = sub.add_parser("list", help="Discover and tabulate agent sessions across hosts")
    p_list.add_argument("--host", default="all", help="Host selector: all, local, linux-host (default: all)")
    p_list.add_argument("--include-dormant", action="store_true", help="Include dormant brain transcripts")
    p_list.add_argument("--dormant-limit", type=int, default=10, help="Max dormant transcripts per host")
    p_list.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    # attach
    p_attach = sub.add_parser("attach", help="Safely attach or consolidate a session into a target worktree")
    p_attach.add_argument("conversation_id", help="Conversation UUID to attach")
    p_attach.add_argument("--worktree", required=True, help="Target worktree tree name (`agy-orca`), `root`, or path")
    p_attach.add_argument("--host", default="local", help="Target host (local or linux-host)")
    p_attach.add_argument(
        "--rebind-idle",
        action="store_true",
        help="Gracefully stop an idle session (e.g. in global-floating-terminal) and rebind into target worktree",
    )
    p_attach.add_argument("--dry-run", action="store_true", help="Verify single-writer guard without spawning")
    p_attach.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    # spawn
    p_spawn = sub.add_parser("spawn", help="Spawn a new Orca terminal/agent session directly inside a target worktree")
    p_spawn.add_argument("--worktree", required=True, help="Target worktree tree name (`agy-orca`), `root`, or path")
    p_spawn.add_argument("--host", default="local", help="Target host (local or linux-host)")
    p_spawn.add_argument("--ticket", default=None, help="Optional ticket ID (T##) for session title")
    p_spawn.add_argument("--track", default=None, help="Optional Quest Track label (e.g. 'Track C')")
    p_spawn.add_argument("--title", default=None, help="Optional short session title")
    p_spawn.add_argument("--command", default=None, help="Optional shell/agent command to execute in the terminal")
    p_spawn.add_argument("--no-focus", action="store_true", help="Do not focus the newly created terminal tab")
    p_spawn.add_argument("--dry-run", action="store_true", help="Resolve worktree target and title without spawning")
    p_spawn.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    # worktrees
    p_wts = sub.add_parser("worktrees", help="List selectable Orca worktree targets and agent trees across hosts")
    p_wts.add_argument("--host", default="all", help="Host selector: all, local, linux-host (default: all)")
    p_wts.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    # hosts
    p_hosts = sub.add_parser("hosts", help="Inspect and ensure multi-host Orca runtime & SSH connectivity")
    p_hosts.add_argument("--host", default="all", help="Host selector: all, local, linux-host (default: all)")
    p_hosts.add_argument("--ensure-ssh", action="store_true", help="Ensure linux-host is registered and connected in Orca")
    p_hosts.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    # save-state (T599 AC1)
    p_save = sub.add_parser("save-state", help="Privately persist cross-host project and agent workload state")
    p_save.add_argument("--host", default="all", help="Host selector: all, local, linux-host (default: all)")
    p_save.add_argument("--sync-hosts", action="store_true", help="Mirror private snapshot to remote SSH hosts")
    p_save.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    # load-state (T599 AC1)
    p_load = sub.add_parser("load-state", help="Load latest privately persisted cross-host workload state")
    p_load.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    # archive (T599 AC1/AC2)
    p_arch = sub.add_parser("archive", help="Collect session brain artifacts into private archive and optionally close tabs")
    p_arch.add_argument("--host", default="linux-host", help="Target host (default: linux-host)")
    p_arch.add_argument("--conversation", action="append", default=None, help="Specific conversation UUID(s) to collect")
    p_arch.add_argument("--close-terminals", action="store_true", help="Close completed w0m Orca terminal tabs on host")
    p_arch.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    # Support top-level flags when invoked without subcommand (`just orca-sessions --json`)
    parser.add_argument("--host", default="all", help="Host selector: all, local, linux-host (default: all)")
    parser.add_argument("--include-dormant", action="store_true", help="Include dormant brain transcripts")
    parser.add_argument("--dormant-limit", type=int, default=10, help="Max dormant transcripts per host")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    args = parser.parse_args(argv)
    cmd = args.subcommand or "list"

    if cmd == "save-state":
        res = save_private_workload_state(
            hosts=_select_hosts(args.host),
            sync_hosts=bool(getattr(args, "sync_hosts", False)),
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(
                f"[SAVED PRIVATE STATE] {res['latestJson']} & {res['latestMd']} "
                f"(hosts={res['hostCount']}, sessions={res['sessionCount']}, "
                f"archivedSessions={res['archivedSessionCount']}, syncedRemotes={res['syncedRemotes']})"
            )
        return 0

    if cmd == "load-state":
        res = load_private_workload_state()
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            if not res.get("ok"):
                print(f"[ERROR] {res.get('error')}", file=sys.stderr)
                return 1
            print(format_workload_markdown(res["payload"]))
        return 0 if res.get("ok") else 1

    if cmd == "archive":
        res = archive_host_sessions(
            args.host,
            conversation_ids=args.conversation,
            close_terminals=bool(args.close_terminals),
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(
                f"[ARCHIVED] host={res['host']} conversations={len(res['collected'])} "
                f"closedTerminals={len(res['closedTerminals'])}"
            )
        return 0

    if cmd == "attach":
        res = attach_session(
            args.conversation_id,
            args.worktree,
            host=args.host,
            rebind_idle=args.rebind_idle,
            dry_run=args.dry_run,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            if res.get("ok"):
                mode = "DRY-RUN" if res.get("dryRun") else "ATTACHED"
                print(
                    f"[{mode}] conversation={res['conversation_id']} -> host={res['host']} "
                    f"worktree={res['worktree']} ({res['guard']['reason']})"
                )
            else:
                print(f"[REFUSED] {res.get('error')}", file=sys.stderr)
        return 0 if res.get("ok") else 1

    if cmd == "spawn":
        res = spawn_session(
            args.worktree,
            host=args.host,
            ticket=args.ticket,
            track=args.track,
            title=args.title,
            command=args.command,
            focus=not args.no_focus,
            dry_run=args.dry_run,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            if res.get("ok"):
                mode = "DRY-RUN" if res.get("dryRun") else "SPAWNED"
                print(
                    f"[{mode}] host={res['host']} worktree={res['worktreePath']} "
                    f"title=\"{res['title']}\""
                )
            else:
                print(f"[ERR] {res.get('error')}", file=sys.stderr)
        return 0 if res.get("ok") else 1

    hosts = _select_hosts(args.host)
    if cmd == "hosts" and getattr(args, "ensure_ssh", False) and "local" in hosts:
        ensure_ssh_target("linux-host", connect=True)

    snapshots: list[dict[str, Any]] = []
    sessions_by_host: dict[str, list[dict[str, Any]]] = {}
    all_sessions: list[dict[str, Any]] = []

    include_dormant = bool(getattr(args, "include_dormant", False))
    dormant_limit = int(getattr(args, "dormant_limit", 10))

    for h in hosts:
        snap = (
            collect_local_snapshot(host_label="local", dormant_limit=dormant_limit)
            if h == "local"
            else collect_remote_snapshot(h)
        )
        snapshots.append(snap)
        hs = correlate_host_sessions(snap, include_dormant=include_dormant, dormant_limit=dormant_limit)
        sessions_by_host[h] = hs
        all_sessions.extend(hs)

    if cmd == "worktrees":
        if args.json:
            print(
                json.dumps(
                    {
                        "hosts": [
                            {
                                "host": s.get("host"),
                                "worktrees": s.get("worktrees") or [],
                                "agentTrees": s.get("agentTrees") or [],
                            }
                            for s in snapshots
                        ]
                    },
                    indent=2,
                )
            )
        else:
            print(format_worktrees_table(snapshots))
        return 0

    if cmd == "hosts":
        if args.json:
            print(
                json.dumps(
                    {
                        "hosts": [
                            {
                                "host": s.get("host"),
                                "hostname": s.get("hostname"),
                                "platform": s.get("platform"),
                                "reachable": s.get("reachable"),
                                "orcaRuntime": s.get("orcaRuntime"),
                                "terminalCount": len(s.get("terminals") or []),
                                "worktreeCount": len(s.get("worktrees") or []),
                                "sshTargets": s.get("sshTargets") or [],
                                "liveSessionCount": sum(
                                    1 for sess in sessions_by_host.get(str(s.get("host")), []) if sess.get("pid") is not None
                                ),
                            }
                            for s in snapshots
                        ]
                    },
                    indent=2,
                )
            )
        else:
            print(format_hosts_table(snapshots, sessions_by_host))
        return 0 if all(s.get("reachable") for s in snapshots) else 1

    # Default: `list`
    if args.json:
        print(
            json.dumps(
                {
                    "hosts": [
                        {
                            "host": s.get("host"),
                            "hostname": s.get("hostname"),
                            "platform": s.get("platform"),
                            "reachable": s.get("reachable"),
                            "terminalCount": len(s.get("terminals") or []),
                        }
                        for s in snapshots
                    ],
                    "sessions": all_sessions,
                },
                indent=2,
            )
        )
    else:
        print(format_hosts_table(snapshots, sessions_by_host))
        print()
        print(format_sessions_table(all_sessions))
    return 0


if __name__ == "__main__":
    sys.exit(main())
