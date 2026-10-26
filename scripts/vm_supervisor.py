#!/usr/bin/env python3
"""Host supervision and health probing for Tart micro VMs (T296).

Provides single-command visibility into running Tart VMs, verifies guest agent
reachability via virtio-serial RPC (immune to host network/VPN lease drops),
and detects runaway/stuck in-guest CPU processes (e.g. hung IDEs/daemons).

Usage:
  python3 scripts/vm_supervisor.py [--status] [--json]
  python3 scripts/vm_supervisor.py --doctor [--json]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any



def sh(*args: str, timeout: int = 10) -> tuple[int, str]:
    """Execute command directly without shell interpolation."""
    try:
        r = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
        return r.returncode, (r.stdout or r.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, f"command timed out after {timeout}s"
    except FileNotFoundError:
        return 127, f"binary {args[0]!r} not found on PATH"
    except Exception as e:
        return 1, str(e)


def parse_tart_list(raw_output: str) -> list[dict]:
    """Parse output of `tart list` into structured dictionaries."""
    vms: list[dict] = []
    lines = [line.strip() for line in raw_output.splitlines() if line.strip()]
    if not lines:
        return vms

    header = lines[0].lower()
    is_real_tart = "accessed" in header and "state" in header

    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        status = parts[-1]
        source = parts[0]
        name = parts[1]

        if is_real_tart and len(parts) >= 6:
            disk = f"{parts[2]} GB"
            size = f"{parts[3]} GB"
            memory = "—"
            cpu = "—"
            os_type = "linux"
        else:
            disk = f"{parts[2]} {parts[3]}" if len(parts) > 3 else "—"
            memory = f"{parts[4]} {parts[5]}" if len(parts) > 5 else "—"
            cpu = str(parts[6]) if len(parts) > 6 else "—"
            os_type = parts[7] if len(parts) > 7 else "—"

        vms.append({
            "source": source,
            "name": name,
            "disk": disk,
            "memory": memory,
            "cpu": cpu,
            "os": os_type,
            "status": status,
        })
    return vms


def parse_guest_probe_output(raw_output: str) -> dict[str, Any]:
    """Parse probe script output from guest into structured health metrics."""
    procs: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "reachable": True,
        "error": None,
        "uptime": "",
        "loadavg": (0.0, 0.0, 0.0),
        "mem_total_mb": 0,
        "mem_used_mb": 0,
        "procs": procs,
    }

    sections: dict[str, list[str]] = {}
    current_section = None
    section_lines: list[str] = []

    for line in raw_output.splitlines():
        if line.startswith("---") and line.endswith("---"):
            if current_section:
                sections[current_section] = section_lines
            current_section = line.strip("-")
            section_lines = []
        elif current_section:
            section_lines.append(line)
    if current_section:
        sections[current_section] = section_lines

    # Parse UPTIME
    if "UPTIME" in sections and sections["UPTIME"]:
        result["uptime"] = sections["UPTIME"][0].strip()

    # Parse LOADAVG
    if "LOADAVG" in sections and sections["LOADAVG"]:
        load_parts = sections["LOADAVG"][0].split()
        if len(load_parts) >= 3:
            try:
                result["loadavg"] = (
                    float(load_parts[0]),
                    float(load_parts[1]),
                    float(load_parts[2]),
                )
            except ValueError:
                pass

    # Parse MEM
    if "MEM" in sections:
        for mline in sections["MEM"]:
            if mline.startswith("Mem:"):
                mparts = mline.split()
                if len(mparts) >= 3:
                    try:
                        result["mem_total_mb"] = int(mparts[1])
                        result["mem_used_mb"] = int(mparts[2])
                    except ValueError:
                        pass

    # Parse PROCS
    if "PROCS" in sections and len(sections["PROCS"]) > 1:
        # First line is header: PID PPID USER %CPU %MEM STAT COMM
        for pline in sections["PROCS"][1:]:
            pparts = pline.split(maxsplit=6)
            if len(pparts) >= 7:
                try:
                    procs.append({
                        "pid": int(pparts[0]),
                        "ppid": int(pparts[1]),
                        "user": pparts[2],
                        "cpu": float(pparts[3]),
                        "mem": float(pparts[4]),
                        "stat": pparts[5],
                        "comm": pparts[6].strip(),
                    })
                except ValueError:
                    continue

    return result



def probe_guest_vm(vm_name: str, timeout: int = 5) -> dict:
    """Run read-only health probe script inside guest using virtio-serial tart exec."""
    cfg_path = Path.home() / ".tart" / "vms" / vm_name / "config.json"
    is_darwin = False
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                is_darwin = cfg.get("os") == "darwin"
        except Exception:
            pass

    if is_darwin:
        darwin_probe = (
            "printf -- '---UPTIME---\\n' && uptime && "
            "printf -- '---LOADAVG---\\n' && uptime | sed -E 's/.*load averages?: //; s/,//g' && "
            "printf -- '---MEM---\\n' && echo \"Mem: $(($(sysctl -n hw.memsize) / 1048576)) 0\" && "
            "printf -- '---PROCS---\\n' && ps -A -o pid,ppid,user,%cpu,%mem,state,comm -r | head -10"
        )
        code, out = sh("tart", "exec", vm_name, "sh", "-c", darwin_probe, timeout=timeout)
        if code == 0:
            return parse_guest_probe_output(out)
        # Fallback if guest agent is not running inside macOS VM
        code_ip, ip_out = sh("tart", "ip", vm_name, timeout=3)
        ip_str = ip_out if code_ip == 0 and ip_out else "active"
        mem_mb = cfg.get("memorySize", 0) // (1024 * 1024) if cfg else 0
        return {
            "reachable": True,
            "error": None,
            "uptime": f"GUI (IP: {ip_str})",
            "loadavg": (0.0, 0.0, 0.0),
            "mem_total_mb": mem_mb,
            "mem_used_mb": 0,
            "procs": [],
        }

    probe_cmd = (
        "printf -- '---UPTIME---\\n' && uptime && "
        "printf -- '---LOADAVG---\\n' && cat /proc/loadavg && "
        "printf -- '---MEM---\\n' && free -m && "
        "printf -- '---PROCS---\\n' && ps -eo pid,ppid,user,%cpu,%mem,stat,comm --sort=-%cpu | head -10"
    )
    code, out = sh("tart", "exec", vm_name, "sh", "-c", probe_cmd, timeout=timeout)
    if code != 0:
        return {
            "reachable": False,
            "error": out or f"tart exec exited with code {code}",
            "uptime": "",
            "loadavg": (0.0, 0.0, 0.0),
            "mem_total_mb": 0,
            "mem_used_mb": 0,
            "procs": [],
        }
    parsed = parse_guest_probe_output(out)
    return parsed


def diagnose_vm(vm_name: str, health: dict) -> list[dict]:
    """Diagnose VM health metrics and return list of warning/error findings."""
    findings: list[dict] = []
    if not health.get("reachable", True):
        findings.append({
            "vm": vm_name,
            "severity": "error",
            "message": f"[{vm_name}] guest agent unreachable: {health.get('error', 'unknown error')}",
        })
        return findings

    # Check for runaway CPU (>80%), excluding probe commands (ps, head)
    for p in health.get("procs", []):
        comm = p.get("comm", "")
        if comm in ("ps", "head"):
            continue
        if p.get("cpu", 0.0) >= 80.0:
            findings.append({
                "vm": vm_name,
                "severity": "warn",
                "message": f"[{vm_name}] runaway CPU detected on PID {p['pid']} ({p['comm']}): {p['cpu']}% CPU",
            })
        if "Z" in p.get("stat", ""):
            findings.append({
                "vm": vm_name,
                "severity": "warn",
                "message": f"[{vm_name}] zombie/defunct process detected: PID {p['pid']} ({p['comm']})",
            })

    # Check for critical memory pressure (>90%)
    tot = health.get("mem_total_mb", 0)
    usd = health.get("mem_used_mb", 0)
    if tot > 0 and (usd / tot) >= 0.90:
        pct = round((usd / tot) * 100, 1)
        findings.append({
            "vm": vm_name,
            "severity": "warn",
            "message": f"[{vm_name}] critical memory pressure: {usd}MB / {tot}MB used ({pct}%)",
        })

    return findings


def format_status_table(vms: list[dict], health_map: dict | None = None) -> str:
    """Format VMs and their probed health into an aligned summary table."""
    health_map = health_map or {}
    hdr = f"  {'Virtual Machine':22} {'Status':10} {'Disk':10} {'Memory':10} {'Agent':10} {'Load Avg':18} {'Top Process':22}"
    divider = "  " + "─" * (len(hdr) - 2)
    lines = [hdr, divider]

    for vm in vms:
        name = vm["name"]
        status = vm["status"]
        disk = vm.get("disk", "—")
        mem = vm.get("memory", "—")
        h = health_map.get(name)

        if status != "running":
            agent_str = "stopped"
            load_str = "—"
            top_proc = "—"
        elif not h:
            agent_str = "unprobed"
            load_str = "—"
            top_proc = "—"
        elif not h.get("reachable"):
            agent_str = "UNREACH"
            load_str = "—"
            top_proc = "agent offline"
        elif h.get("uptime", "").startswith("GUI"):
            agent_str = "native-gui"
            load_str = "—"
            top_proc = h.get("uptime", "running")
        else:
            agent_str = "healthy"
            lavg = h.get("loadavg", (0.0, 0.0, 0.0))
            load_str = f"{lavg[0]:.2f}, {lavg[1]:.2f}, {lavg[2]:.2f}"
            procs = h.get("procs", [])
            if procs:
                proc_name = Path(procs[0]['comm']).name
                top_proc = f"{proc_name} ({procs[0]['cpu']}%)"
            else:
                top_proc = "idle"

        lines.append(
            f"  {name:22} {status:10} {disk:10} {mem:10} {agent_str:10} {load_str:18} {top_proc:22}"
        )

    return "\n".join(lines)


def run_supervisor(doctor: bool = False, json_mode: bool = False) -> int:
    """Run supervisor discovery and probing across all local Tart VMs."""
    code, out = sh("tart", "list")
    if code != 0:
        if json_mode:
            print(json.dumps({"error": f"tart CLI failed: {out}", "code": 2}))
        else:
            print(f"Error: Failed to execute `tart list` (exit {code}): {out}", file=sys.stderr)
        return 2

    vms = parse_tart_list(out)
    health_map: dict[str, dict] = {}
    findings: list[dict[str, Any]] = []

    for vm in vms:
        if vm["status"] == "running":
            h = probe_guest_vm(vm["name"])
            health_map[vm["name"]] = h
            diag = diagnose_vm(vm["name"], h)
            findings.extend(diag)

    if json_mode:
        print(json.dumps({"vms": vms, "health": health_map, "findings": findings}, indent=2))
        return 1 if (doctor and findings) else 0

    print("\n  Tart Micro VM Host Supervision (T296)\n")
    print(format_status_table(vms, health_map))
    print()

    if doctor:
        if not findings:
            print("  [OK] All running Tart VMs are healthy — zero runaway processes, healthy agents.")
            return 0
        else:
            print(f"  [WARN] Found {len(findings)} VM health issue(s):")
            for finding in findings:
                icon = "[ERROR]" if finding["severity"] == "error" else "[WARN]"
                print(f"     {icon} {finding['message']}")
            print()
            return 1


    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Tart VM host supervisor and health probe")
    parser.add_argument("mode", nargs="?", default="status", choices=["status", "doctor"], help="Mode: status or doctor")
    parser.add_argument("--doctor", action="store_true", help="Run health diagnostics and flag wedged/hung processes")
    parser.add_argument("--json", action="store_true", help="Output JSON results")
    args = parser.parse_args()

    is_doctor = args.doctor or args.mode == "doctor"
    sys.exit(run_supervisor(doctor=is_doctor, json_mode=args.json))


if __name__ == "__main__":
    main()

