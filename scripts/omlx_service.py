#!/usr/bin/env python3
"""Unified oMLX Process & Service Lifecycle Manager (T374).

Handles detection, status, start, stop, and restart across:
1. Homebrew LaunchAgent (sh.brew.omlx)
2. macOS Desktop GUI application (/Applications/oMLX.app)
3. Standalone CLI / Python runner (omlx server)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time

OMLX_PORT = 8888
OMLX_HOST = "127.0.0.1"
OMLX_URL = f"http://{OMLX_HOST}:{OMLX_PORT}"
BREW_LABEL = "sh.brew.omlx"


def get_port_listeners(port: int = OMLX_PORT) -> list[dict[str, str]]:
    """Return processes actively listening on port."""
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


def get_omlx_processes() -> list[dict[str, str]]:
    """Return all running oMLX processes via ps."""
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
            if "grep" in command or "omlx_service.py" in command:
                continue
            if "omlx-server" in command or "oMLX.app" in command or "omlx.server" in command:
                mode = "unknown"
                if "oMLX.app" in command:
                    mode = "macOS GUI App"
                elif ppid == "1":
                    mode = "Homebrew Daemon"
                else:
                    mode = "Standalone CLI"
                processes.append({"pid": pid, "ppid": ppid, "command": command, "mode": mode})
    except Exception as e:
        sys.stderr.write(f"Error inspecting processes: {e}\n")
    return processes


def is_brew_service_loaded() -> bool:
    """Check if sh.brew.omlx is loaded in launchctl."""
    try:
        res = subprocess.run(["launchctl", "list"], capture_output=True, text=True, check=False)
        return BREW_LABEL in res.stdout
    except Exception:
        return False


def probe_http_health() -> dict | None:
    """Probe oMLX HTTP models endpoint for live metadata."""
    conn = None
    try:
        import http.client

        conn = http.client.HTTPConnection(OMLX_HOST, OMLX_PORT, timeout=1.5)
        conn.request("GET", "/v1/models", headers={"User-Agent": "omlx-service-probe"})
        resp = conn.getresponse()
        if resp.status == 200:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("id") for m in data.get("data", []) if m.get("id")]
            return {"models": models}
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
    """Print detailed status of oMLX services and ports."""
    listeners = get_port_listeners(OMLX_PORT)
    procs = get_omlx_processes()
    brew_loaded = is_brew_service_loaded()
    health = probe_http_health()

    print(f"=== oMLX Service Status ===")
    print(f"Target URL: {OMLX_URL}")
    print(f"Homebrew LaunchAgent ({BREW_LABEL}): {'Loaded' if brew_loaded else 'Not Loaded'}")

    if listeners:
        print(f"\nPort {OMLX_PORT} Listeners:")
        for l in listeners:
            print(f"  • PID {l['pid']} ({l['command']})")
    else:
        print(f"\nPort {OMLX_PORT}: Idle (No listener)")

    if procs:
        print(f"\nRunning oMLX Processes:")
        for p in procs:
            print(f"  • PID {p['pid']} [Mode: {p['mode']}] (PPID: {p['ppid']})")
            print(f"    Command: {p['command'][:100]}")
    else:
        print(f"\nRunning oMLX Processes: None")

    if health:
        print(f"\nHTTP API Health: ONLINE")
        print(f"Exposed Models: {', '.join(health.get('models', []))}")
    else:
        print(f"\nHTTP API Health: OFFLINE")

    if listeners and health:
        print(f"\nVerdict: HEALTHY (oMLX is actively serving on port {OMLX_PORT})")
        return 0
    elif listeners and not health:
        print(f"\nVerdict: WARNING (Port {OMLX_PORT} bound but API not responding)")
        return 1
    else:
        print(f"\nVerdict: STOPPED")
        return 0


def cmd_stop() -> int:
    """Stop all oMLX processes and free port 8888."""
    print("Stopping oMLX services and clearing port 8888...")
    if is_brew_service_loaded():
        print(f"Stopping Homebrew service ({BREW_LABEL})...")
        subprocess.run(["brew", "services", "stop", "omlx"], capture_output=True, check=False)

    # Find all PIDs binding port or running oMLX
    pids_to_kill = set()
    for l in get_port_listeners(OMLX_PORT):
        pids_to_kill.add(int(l["pid"]))
    for p in get_omlx_processes():
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
            listeners = get_port_listeners(OMLX_PORT)
            if not listeners:
                break
            time.sleep(0.3)

        # Force kill if still holding port
        remaining = get_port_listeners(OMLX_PORT)
        if remaining:
            print(f"Port {OMLX_PORT} still busy. Force killing (SIGKILL)...")
            for r in remaining:
                try:
                    os.kill(int(r["pid"]), signal.SIGKILL)
                except Exception:
                    pass
            time.sleep(0.5)

    listeners = get_port_listeners(OMLX_PORT)
    if listeners:
        print(f"ERROR: Port {OMLX_PORT} still in use by: {listeners}")
        return 1
    print(f"SUCCESS: Port {OMLX_PORT} is completely free.")
    return 0


def cmd_start() -> int:
    """Start oMLX managed daemon, ensuring port is not already occupied."""
    listeners = get_port_listeners(OMLX_PORT)
    if listeners:
        print(f"ERROR: Port {OMLX_PORT} is already bound by: {listeners}")
        print("Run `just omlx-stop` or `just omlx-restart` to clear port first.")
        return 1

    print("Starting oMLX via Homebrew services...")
    res = subprocess.run(["brew", "services", "start", "omlx"], capture_output=True, text=True, check=False)
    if res.returncode != 0:
        print(f"Failed to start brew service: {res.stderr}")
        return 1

    print("Waiting for oMLX to initialize on port 8888...")
    deadline = time.time() + 8.0
    while time.time() < deadline:
        health = probe_http_health()
        if health:
            print(f"SUCCESS: oMLX is up and serving models: {', '.join(health.get('models', []))}")
            return 0
        time.sleep(0.5)

    print("WARNING: Service launched but API did not respond within 8 seconds.")
    return 1


def cmd_restart() -> int:
    """Clean restart: stop any existing instances, then start."""
    stop_rc = cmd_stop()
    if stop_rc != 0:
        return stop_rc
    time.sleep(0.5)
    return cmd_start()


def main() -> int:
    parser = argparse.ArgumentParser(description="oMLX Process & Service Manager")
    parser.add_argument("action", choices=["status", "start", "stop", "restart"], help="Action to execute")
    args = parser.parse_args()

    if args.action == "status":
        return cmd_status()
    elif args.action == "stop":
        return cmd_stop()
    elif args.action == "start":
        return cmd_start()
    elif args.action == "restart":
        return cmd_restart()
    return 0


if __name__ == "__main__":
    sys.exit(main())
