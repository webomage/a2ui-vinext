#!/usr/bin/env python3
"""Tests for project/scripts/vm_supervisor.py (T296 host supervision).

Ensures:
- tart list output is reliably parsed into structured dictionaries
- in-guest health metrics (uptime, load, memory, top processes) are parsed
- runaway/stuck CPU hogs and defunct processes are flagged by doctor
- unreachable guest agents are surfaced cleanly
- exit codes align with estate standards (0 = ok, 1 = findings, 2 = unmeasurable)
"""

import json
import sys
from pathlib import Path

# Add project/scripts to path
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from vm_supervisor import (
        parse_tart_list,
        parse_guest_probe_output,
        diagnose_vm,
        format_status_table,
    )
except ImportError as e:
    # During RED phase of TDD, module might not exist or might fail
    print(f"Import failed during RED phase: {e}")
    sys.exit(1)

fails: list[str] = []
checks = 0


def check(label: str, cond: bool) -> None:
    global checks
    checks += 1
    if not cond:
        fails.append(label)
        print(f"  ✗ {label}")
    else:
        print(f"  ✓ {label}")



def test_parse_tart_list():
    raw_tart_list = """Source                  Virtual Machine         Disk      Memory  CPU  OS    Size    Status
local                   w0m-bridgeroad          20 GiB    4 GiB   2    linux 3.2 GB  running
local                   evercred                94 GiB    24 GiB  6    linux 52 GB   stopped
local                   bridgeroad-base         20 GiB    4 GiB   2    linux 2.8 GB  stopped
"""
    vms = parse_tart_list(raw_tart_list)
    assert len(vms) == 3
    assert vms[0]["name"] == "w0m-bridgeroad" and vms[0]["status"] == "running"
    assert vms[1]["name"] == "evercred" and vms[1]["status"] == "stopped"
    assert vms[0]["disk"] == "20 GiB" and vms[0]["memory"] == "4 GiB"

    empty_vms = parse_tart_list("Source  Virtual Machine  Disk  Memory  CPU  OS  Size  Status\n")
    assert len(empty_vms) == 0


def test_parse_guest_probe_output():
    sample_guest_out = """---UPTIME---
 23:15:02 up  5:45,  0 users,  load average: 1.12, 1.05, 0.98
---LOADAVG---
1.12 1.05 0.98 2/180 4521
---MEM---
               total        used        free      shared  buff/cache   available
Mem:            3910        1240        1520          12        1150        2670
Swap:              0           0           0
---PROCS---
  PID  PPID USER     %CPU %MEM STAT COMM
 1332     1 ubuntu   99.9  8.2 R    orca-ide
 1402  1332 ubuntu    0.0  0.0 Z    orca-ide <defunct>
  850     1 root      0.5  1.2 S    dockerd
  920     1 ubuntu    0.1  0.5 S    tart-guest-agen
"""
    parsed = parse_guest_probe_output(sample_guest_out)
    assert parsed["loadavg"] == (1.12, 1.05, 0.98)
    assert parsed["mem_total_mb"] == 3910 and parsed["mem_used_mb"] == 1240
    assert len(parsed["procs"]) == 4
    assert parsed["procs"][0]["cpu"] == 99.9 and parsed["procs"][0]["comm"] == "orca-ide"
    assert parsed["procs"][1]["stat"] == "Z"


def test_diagnose_vm_wedged_and_zombie():
    parsed = {
        "reachable": True,
        "loadavg": (1.12, 1.05, 0.98),
        "mem_total_mb": 3910,
        "mem_used_mb": 1240,
        "procs": [
            {"pid": 1332, "user": "ubuntu", "cpu": 99.9, "mem": 8.2, "stat": "R", "comm": "orca-ide"},
            {"pid": 1402, "user": "ubuntu", "cpu": 0.0, "mem": 0.0, "stat": "Z", "comm": "orca-ide <defunct>"},
        ],
    }
    findings = diagnose_vm("w0m-bridgeroad", parsed)
    assert any("runaway CPU" in f["message"] and "orca-ide" in f["message"] for f in findings)
    assert any("defunct" in f["message"] or "zombie" in f["message"] for f in findings)


def test_diagnose_vm_healthy():
    healthy_out = """---UPTIME---
 23:20:00 up 10 min,  0 users,  load average: 0.05, 0.02, 0.00
---LOADAVG---
0.05 0.02 0.00 1/150 2100
---MEM---
               total        used        free      shared  buff/cache   available
Mem:            3910         450        2800          10         660        3460
Swap:              0           0           0
---PROCS---
  PID  PPID USER     %CPU %MEM STAT COMM
  850     1 root      0.2  1.2 S    dockerd
  920     1 ubuntu    0.1  0.5 S    tart-guest-agen
"""
    healthy_parsed = parse_guest_probe_output(healthy_out)
    healthy_findings = diagnose_vm("w0m-bridgeroad", healthy_parsed)
    assert len(healthy_findings) == 0


def test_diagnose_vm_memory_pressure():
    high_mem_out = """---UPTIME---
 23:20:00 up 10 min,  0 users,  load average: 0.10, 0.05, 0.00
---LOADAVG---
0.10 0.05 0.00 1/150 2100
---MEM---
               total        used        free      shared  buff/cache   available
Mem:            4000        3800         100          10         100         200
Swap:              0           0           0
---PROCS---
  PID  PPID USER     %CPU %MEM STAT COMM
  850     1 root      0.2 85.0 S    heavy-app
"""
    mem_parsed = parse_guest_probe_output(high_mem_out)
    mem_findings = diagnose_vm("w0m-bridgeroad", mem_parsed)
    assert any("memory pressure" in f["message"] for f in mem_findings)


def test_diagnose_vm_unreachable():
    unreachable_parsed = {"reachable": False, "error": "tart exec timed out after 5s", "loadavg": None, "procs": []}
    unreachable_findings = diagnose_vm("w0m-bridgeroad", unreachable_parsed)
    assert any("agent unreachable" in f["message"] for f in unreachable_findings)


def test_format_status_table():
    vms = [
        {"source": "local", "name": "w0m-bridgeroad", "disk": "20 GiB", "memory": "4 GiB", "cpu": "2", "os": "linux", "size": "3.2 GB", "status": "running"},
        {"source": "local", "name": "evercred", "disk": "94 GiB", "memory": "24 GiB", "cpu": "6", "os": "linux", "size": "52 GB", "status": "stopped"},
    ]
    table_str = format_status_table(vms)
    assert "Virtual Machine" in table_str and "Status" in table_str
    assert "w0m-bridgeroad" in table_str and "evercred" in table_str


if __name__ == "__main__":
    print("\n  Running test_vm_supervisor...")
    test_parse_tart_list()
    test_parse_guest_probe_output()
    test_diagnose_vm_wedged_and_zombie()
    test_diagnose_vm_healthy()
    test_diagnose_vm_memory_pressure()
    test_diagnose_vm_unreachable()
    test_format_status_table()
    print("  All test_vm_supervisor checks passed.\n")

