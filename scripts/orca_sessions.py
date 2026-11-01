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
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

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


def _resolve_worktree_selector(worktree_arg: str, snapshot: dict[str, Any]) -> str:
    """Resolve a path or selector into an Orca worktreeId or path selector."""
    if worktree_arg in ("active", "current") or worktree_arg.startswith(("id:", "path:", "name:", "branch:")):
        return worktree_arg
    norm_path = str(Path(worktree_arg).expanduser())
    for wt in snapshot.get("worktrees") or []:
        if wt.get("path") == norm_path and isinstance(wt.get("id"), str):
            return str(wt["id"])
    return norm_path


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
    snapshot = snapshot_override or (
        collect_local_snapshot(host_label="local")
        if host == "local"
        else collect_remote_snapshot(host)
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
        if host == "local":
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
                    ["ssh", "-o", "BatchMode=yes", host, f"kill -TERM {old_pid} 2>/dev/null || true"],
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                )

    if host == "local":
        create_res = orca_rpc_call(
            "terminal.create",
            {
                "worktree": resolved_wt,
                "title": f"agy:{conversation_id[:8]}",
                "command": attach_cmd,
            },
        )
        if not create_res.get("ok"):
            cli_bin = "/Applications/Orca.app/Contents/Resources/bin/orca"
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
            ["ssh", "-o", "BatchMode=yes", host, remote_cmd],
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


def format_hosts_table(snapshots: list[dict[str, Any]], sessions_by_host: dict[str, list[dict[str, Any]]]) -> str:
    """Format multi-host Orca runtime and SSH connectivity summary."""
    lines = [
        "| Host | Hostname (`platform`) | Reachable | Orca Runtime (`version`) | Terminals | Live Sessions | SSH Targets |",
        "|---|---|---|---|---|---|---|",
    ]
    for snap in snapshots:
        host = str(snap.get("host") or "local")
        hname = f"{snap.get('hostname', host)} ({snap.get('platform', 'unknown')})"
        reachable = "yes" if snap.get("reachable") else "no"
        rt = snap.get("orcaRuntime") or {}
        if isinstance(rt, dict) and rt.get("runtimeId"):
            rt_str = f"ready ({str(rt.get('runtimeId'))[:8]} / {rt.get('appVersion', '1.4.x')})"
        else:
            rt_str = "offline"
        terms_count = len(snap.get("terminals") or [])
        host_sessions = sessions_by_host.get(host, [])
        live_count = sum(1 for s in host_sessions if s.get("pid") is not None)
        ssh_targets = snap.get("sshTargets") or []
        ssh_desc = ", ".join(
            f"{t.get('label', t.get('id'))}:{'connected' if t.get('connected') else 'idle'}"
            for t in ssh_targets[:4]
        ) or "-"
        lines.append(
            f"| `{host}` | `{hname}` | `{reachable}` | `{rt_str}` | `{terms_count}` | `{live_count}` | {ssh_desc} |"
        )
    return "\n".join(lines)


def _select_hosts(host_arg: str) -> list[str]:
    if host_arg == "all":
        return ["local", *DEFAULT_REMOTE_HOSTS]
    return [h.strip() for h in host_arg.split(",") if h.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Multi-host Orca instance and agent session orchestration (T596)."
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
    p_attach.add_argument("--worktree", required=True, help="Target worktree path or selector")
    p_attach.add_argument("--host", default="local", help="Target host (local or linux-host)")
    p_attach.add_argument(
        "--rebind-idle",
        action="store_true",
        help="Gracefully stop an idle session (e.g. in global-floating-terminal) and rebind into target worktree",
    )
    p_attach.add_argument("--dry-run", action="store_true", help="Verify single-writer guard without spawning")
    p_attach.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    # hosts
    p_hosts = sub.add_parser("hosts", help="Inspect and ensure multi-host Orca runtime & SSH connectivity")
    p_hosts.add_argument("--host", default="all", help="Host selector: all, local, linux-host (default: all)")
    p_hosts.add_argument("--ensure-ssh", action="store_true", help="Ensure linux-host is registered and connected in Orca")
    p_hosts.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    # Support top-level flags when invoked without subcommand (`just orca-sessions --json`)
    parser.add_argument("--host", default="all", help="Host selector: all, local, linux-host (default: all)")
    parser.add_argument("--include-dormant", action="store_true", help="Include dormant brain transcripts")
    parser.add_argument("--dormant-limit", type=int, default=10, help="Max dormant transcripts per host")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    args = parser.parse_args(argv)
    cmd = args.subcommand or "list"

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
