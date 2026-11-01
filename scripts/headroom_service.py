#!/usr/bin/env python3
"""Unified Headroom Process & Service Lifecycle Manager (T456).

Handles status, start, stop, restart, and log inspection across:
1. Homebrew service (webomage/tap/headroom -> homebrew.mxcl.headroom) on port 8787
2. Legacy LaunchAgents (com.headroom.default, sh.brew.headroom-local)
3. Direct process & port arbitration (8787 primary, 8788 legacy)
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HEADROOM_PORT = 8787
LEGACY_PORT = 8788
HEADROOM_HOST = "127.0.0.1"
HEADROOM_URL = f"http://{HEADROOM_HOST}:{HEADROOM_PORT}"
BREW_FORMULA = "webomage/tap/headroom"
BREW_SERVICE_LABELS = ["sh.brew.headroom", "homebrew.mxcl.headroom"]
BREW_SERVICE_LABEL = "sh.brew.headroom"
PRIMARY_LOG_PATH = Path("/opt/homebrew/var/log/headroom.log")
LEGACY_LABELS = ["com.headroom.default", "sh.brew.headroom-local"]
LEGACY_PLISTS = [
    Path.home() / "Library/LaunchAgents/com.headroom.default.plist",
    Path.home() / "Library/LaunchAgents/sh.brew.headroom-local.plist",
]


def get_port_listeners(port: int = HEADROOM_PORT) -> list[dict[str, str]]:
    """Return processes actively listening on specified TCP port."""
    listeners = []
    try:
        cmd = ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        lines = res.stdout.strip().splitlines()
        if len(lines) > 1:
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 2:
                    listeners.append({"command": parts[0], "pid": parts[1]})
    except Exception as e:
        sys.stderr.write(f"Error inspecting port {port}: {e}\n")
    return listeners


def get_headroom_processes() -> list[dict[str, str]]:
    """Return all running Headroom daemon/proxy processes via ps."""
    processes = []
    try:
        cmd = ["ps", "-eo", "pid,ppid,command"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        for line in res.stdout.splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith("PID"):
                continue
            parts = line_str.split(None, 2)
            if len(parts) < 3:
                continue
            pid, ppid, command = parts[0], parts[1], parts[2]
            if "grep" in command or "headroom_service.py" in command or "test_headroom_service" in command:
                continue
            # Match headroom proxy or daemon
            if "headroom.cli proxy" in command or "headroom proxy" in command or "headroom install agent" in command:
                mode = "Standalone CLI"
                if ppid == "1":
                    if "opt/homebrew" in command:
                        mode = "Homebrew Daemon"
                    elif "com.headroom.default" in command or "run-headroom.sh" in command:
                        mode = "Legacy LaunchAgent (default)"
                    elif "headroom-local" in command:
                        mode = "Legacy LaunchAgent (headroom-local)"
                    else:
                        mode = "LaunchAgent Daemon"
                elif ".headroom/deploy" in command:
                    mode = "Managed Agent Profile"
                processes.append({"pid": pid, "ppid": ppid, "command": command, "mode": mode})
    except Exception as e:
        sys.stderr.write(f"Error inspecting processes: {e}\n")
    return processes


def is_brew_service_loaded() -> bool:
    """Check if Homebrew headroom service is loaded in launchctl."""
    try:
        res = subprocess.run(["launchctl", "list"], capture_output=True, text=True, check=False)
        return any(label in res.stdout for label in BREW_SERVICE_LABELS)
    except Exception:
        return False


def get_loaded_legacy_services() -> list[str]:
    """Check which legacy LaunchAgents are currently loaded in launchctl."""
    loaded = []
    try:
        res = subprocess.run(["launchctl", "list"], capture_output=True, text=True, check=False)
        for label in LEGACY_LABELS:
            if label in res.stdout:
                loaded.append(label)
    except Exception:
        pass
    return loaded


def probe_http_health(port: int = HEADROOM_PORT) -> dict | None:
    """Probe Headroom /health endpoint for status, version, and upstream URL."""
    conn = None
    try:
        conn = http.client.HTTPConnection(HEADROOM_HOST, port, timeout=1.5)
        conn.request("GET", "/health", headers={"User-Agent": "w0m-headroom-service-probe"})
        resp = conn.getresponse()
        if resp.status == 200:
            data = json.loads(resp.read().decode("utf-8"))
            upstream_url = data.get("checks", {}).get("upstream", {}).get("url")
            return {
                "status": data.get("status", "unknown"),
                "ready": data.get("ready", False),
                "version": data.get("version", "unknown"),
                "uptime_seconds": data.get("uptime_seconds", 0.0),
                "upstream_url": upstream_url,
                "backend": data.get("config", {}).get("backend"),
            }
    except Exception:
        pass
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return None


def cmd_status() -> int:
    """Print detailed status of Headroom service, listeners, and upstream routing."""
    listeners_8787 = get_port_listeners(HEADROOM_PORT)
    listeners_8788 = get_port_listeners(LEGACY_PORT)
    procs = get_headroom_processes()
    brew_loaded = is_brew_service_loaded()
    legacy_loaded = get_loaded_legacy_services()
    health = probe_http_health(HEADROOM_PORT)

    print("=== Headroom Service Status (T456) ===")
    print(f"Primary Target: {HEADROOM_URL}")
    print(f"Homebrew Service ({BREW_SERVICE_LABEL}): {'Loaded' if brew_loaded else 'Not Loaded'}")

    if legacy_loaded:
        print(f"Legacy LaunchAgents: {', '.join(legacy_loaded)} (Action: unload recommended via `headroom-stop`)")
    else:
        print("Legacy LaunchAgents: None (Clean)")

    if listeners_8787:
        print(f"\nPort {HEADROOM_PORT} (Primary Proxy):")
        for l in listeners_8787:
            print(f"  • PID {l['pid']} ({l['command']})")
    else:
        print(f"\nPort {HEADROOM_PORT} (Primary Proxy): Idle (No listener)")

    if listeners_8788:
        print(f"\nPort {LEGACY_PORT} (Legacy oMLX Proxy):")
        for l in listeners_8788:
            print(f"  • PID {l['pid']} ({l['command']}) [Legacy]")
    else:
        print(f"\nPort {LEGACY_PORT} (Legacy oMLX Proxy): Free (No listener)")

    if procs:
        print("\nRunning Headroom Processes:")
        for p in procs:
            print(f"  • PID {p['pid']} [Mode: {p['mode']}] (PPID: {p['ppid']})")
            print(f"    Command: {p['command'][:110]}")
    else:
        print("\nRunning Headroom Processes: None")

    if health:
        print("\nHTTP API Health (8787): ONLINE")
        print(f"  Status: {health['status']} (Ready: {health['ready']})")
        print(f"  Version: {health['version']}")
        print(f"  Upstream: {health.get('upstream_url') or 'default'}")
        print(f"  Uptime: {health.get('uptime_seconds', 0.0):.1f}s")
    else:
        print("\nHTTP API Health (8787): OFFLINE")

    if listeners_8787 and health and health["status"] == "healthy":
        print(f"\nVerdict: HEALTHY (Headroom is actively serving on port {HEADROOM_PORT})")
        return 0
    elif listeners_8787 and not health:
        print(f"\nVerdict: WARNING (Port {HEADROOM_PORT} bound but /health endpoint not responding)")
        return 1
    else:
        print("\nVerdict: STOPPED")
        return 0


def cmd_stop() -> int:
    """Stop all Headroom instances, unload legacy launchagents, and free ports 8787 & 8788."""
    print("Stopping Headroom services and clearing ports 8787 & 8788...")

    if is_brew_service_loaded():
        print(f"Stopping Homebrew service ({BREW_FORMULA})...")
        subprocess.run(["brew", "services", "stop", BREW_FORMULA], capture_output=True, check=False)

    # Unload legacy launchagents if loaded
    for plist in LEGACY_PLISTS:
        if plist.exists():
            print(f"Unloading LaunchAgent: {plist.name}...")
            subprocess.run(["launchctl", "unload", str(plist)], capture_output=True, check=False)

    # Find all PIDs binding ports or running headroom
    pids_to_kill = set()
    for l in get_port_listeners(HEADROOM_PORT):
        pids_to_kill.add(int(l["pid"]))
    for l in get_port_listeners(LEGACY_PORT):
        pids_to_kill.add(int(l["pid"]))
    for p in get_headroom_processes():
        pids_to_kill.add(int(p["pid"]))

    if pids_to_kill:
        print(f"Terminating running PIDs: {sorted(list(pids_to_kill))}...")
        for pid in pids_to_kill:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception as e:
                print(f"Error sending SIGTERM to PID {pid}: {e}")

        # Wait up to 5s for graceful exit
        deadline = time.time() + 5.0
        while time.time() < deadline:
            l1 = get_port_listeners(HEADROOM_PORT)
            l2 = get_port_listeners(LEGACY_PORT)
            if not l1 and not l2:
                break
            time.sleep(0.3)

        # Force kill if still holding ports
        remaining_pids = set()
        for l in get_port_listeners(HEADROOM_PORT):
            remaining_pids.add(int(l["pid"]))
        for l in get_port_listeners(LEGACY_PORT):
            remaining_pids.add(int(l["pid"]))

        if remaining_pids:
            print(f"Ports still busy by PIDs {sorted(list(remaining_pids))}. Force killing (SIGKILL)...")
            for pid in remaining_pids:
                try:
                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass
            time.sleep(0.5)

    l8787 = get_port_listeners(HEADROOM_PORT)
    l8788 = get_port_listeners(LEGACY_PORT)
    if l8787 or l8788:
        print(f"ERROR: Ports still in use — 8787: {l8787}, 8788: {l8788}")
        return 1
    print("SUCCESS: Ports 8787 and 8788 are completely free.")
    return 0


def cmd_start() -> int:
    """Start Headroom managed daemon via Homebrew services on port 8787."""
    l8787 = get_port_listeners(HEADROOM_PORT)
    if l8787:
        print(f"ERROR: Port {HEADROOM_PORT} is already bound by: {l8787}")
        print("Run `just headroom-stop` or `just headroom-restart` to clear port first.")
        return 1

    # Ensure conflicting legacy launchagents are unloaded
    for plist in LEGACY_PLISTS:
        if plist.exists():
            subprocess.run(["launchctl", "unload", str(plist)], capture_output=True, check=False)

    print(f"Starting Headroom via Homebrew services ({BREW_FORMULA})...")
    res = subprocess.run(["brew", "services", "start", BREW_FORMULA], capture_output=True, text=True, check=False)
    if res.returncode != 0:
        print(f"Failed to start brew service: {res.stderr}")
        return 1

    print("Waiting for Headroom to initialize on port 8787...")
    deadline = time.time() + 20.0
    while time.time() < deadline:
        health = probe_http_health(HEADROOM_PORT)
        if health and health.get("status") == "healthy":
            print(f"SUCCESS: Headroom v{health.get('version')} is up and healthy on port {HEADROOM_PORT}")
            return 0
        time.sleep(0.5)

    print("WARNING: Service launched but API did not become healthy within 20 seconds.")
    return 1


def cmd_restart() -> int:
    """Clean restart: stop any existing instances and legacy agents, then start."""
    stop_rc = cmd_stop()
    if stop_rc != 0:
        return stop_rc
    time.sleep(0.5)
    return cmd_start()


def cmd_logs(lines: int = 50) -> int:
    """Display recent log entries from Homebrew Headroom log."""
    log_file = PRIMARY_LOG_PATH
    if not log_file.exists():
        # Fall back to legacy log if primary doesn't exist yet
        legacy_log = Path.home() / ".headroom/deploy/default/logs/headroom.log"
        if legacy_log.exists():
            log_file = legacy_log
        else:
            print(f"Log file not found at {PRIMARY_LOG_PATH} or {legacy_log}")
            return 1

    print(f"=== Last {lines} lines from {log_file} ===")
    try:
        res = subprocess.run(["tail", "-n", str(lines), str(log_file)], capture_output=True, text=True, check=False)
        print(res.stdout)
        return 0
    except Exception as e:
        print(f"Error reading log file: {e}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Headroom Process & Service Manager (T456)")
    parser.add_argument("action", choices=["status", "start", "stop", "restart", "logs"], help="Action to execute")
    parser.add_argument("-n", "--lines", type=int, default=50, help="Number of log lines to show (for logs)")
    args = parser.parse_args()

    if args.action == "status":
        return cmd_status()
    elif args.action == "stop":
        return cmd_stop()
    elif args.action == "start":
        return cmd_start()
    elif args.action == "restart":
        return cmd_restart()
    elif args.action == "logs":
        return cmd_logs(lines=args.lines)
    return 0


if __name__ == "__main__":
    sys.exit(main())
