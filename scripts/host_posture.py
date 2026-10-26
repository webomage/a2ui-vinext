#!/usr/bin/env python3
"""
macOS Host Security Posture and Startup Baseline Audit — T233.

Evaluates host security controls, network listener exposure (specifically ensuring
local PostgreSQL binds strictly to loopback), verifies the startup surface against
a declared baseline, audits TCC permissions (failing closed to NOT MEASURED when
Full Disk Access is absent), and explicitly records unmeasured blind spots per T96 AC3.

Usage:
  python3 project/scripts/host_posture.py             # Human-readable report
  python3 project/scripts/host_posture.py --enforce   # Exit 1 on any FAIL
  python3 project/scripts/host_posture.py --json      # Structured JSON output
  python3 project/scripts/host_posture.py --test      # Run offline test suite
"""
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

PASS = "✅ PASS"
WARN = "⚠️  WARN"
FAIL = "❌ FAIL"
NOT_MEASURED = "⏭️  NOT MEASURED"
INFO = "ℹ️  INFO"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = ROOT / "project" / "host-startup-baseline.json"


# ── Host Controls Inspection (AC2) ───────────────────────────────────────────

def check_firewall() -> Dict[str, Any]:
    """Inspect macOS Application Firewall and stealth mode."""
    enabled = False
    stealth = False
    detail = []

    try:
        proc1 = subprocess.run(
            ["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"],
            capture_output=True, text=True, check=False
        )
        if "enabled" in proc1.stdout.lower():
            enabled = True
            detail.append("Application Firewall enabled")
        else:
            detail.append("Application Firewall disabled")

        proc2 = subprocess.run(
            ["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getstealthmode"],
            capture_output=True, text=True, check=False
        )
        if "on" in proc2.stdout.lower() and "off" not in proc2.stdout.lower():
            stealth = True
            detail.append("stealth mode on")
        else:
            detail.append("stealth mode off")

    except Exception as e:
        status = NOT_MEASURED if (isinstance(e, FileNotFoundError) and sys.platform != "darwin") else FAIL
        detail_msg = "NOT MEASURED — socketfilterfw not available on Linux host" if status == NOT_MEASURED else f"Error running socketfilterfw: {e}"
        return {
            "name": "Firewall & Stealth",
            "status": status,
            "enabled": False,
            "stealth": False,
            "detail": detail_msg
        }

    status = PASS if (enabled and stealth) else FAIL
    return {
        "name": "Firewall & Stealth",
        "status": status,
        "enabled": enabled,
        "stealth": stealth,
        "detail": ", ".join(detail)
    }


def check_filevault() -> Dict[str, Any]:
    """Inspect FileVault full disk encryption status."""
    try:
        proc = subprocess.run(["fdesetup", "status"], capture_output=True, text=True, check=False)
        enabled = "filevault is on" in proc.stdout.lower()
        return {
            "name": "FileVault",
            "status": PASS if enabled else FAIL,
            "enabled": enabled,
            "detail": proc.stdout.strip() or ("FileVault is On." if enabled else "FileVault is Off.")
        }
    except Exception as e:
        status = NOT_MEASURED if (isinstance(e, FileNotFoundError) and sys.platform != "darwin") else FAIL
        detail = "NOT MEASURED — fdesetup not available on Linux host" if status == NOT_MEASURED else f"Error querying fdesetup: {e}"
        return {
            "name": "FileVault",
            "status": status,
            "enabled": False,
            "detail": detail
        }


def check_sip() -> Dict[str, Any]:
    """Inspect System Integrity Protection (SIP) status."""
    try:
        proc = subprocess.run(["csrutil", "status"], capture_output=True, text=True, check=False)
        enabled = "status: enabled" in proc.stdout.lower()
        return {
            "name": "SIP",
            "status": PASS if enabled else FAIL,
            "enabled": enabled,
            "detail": proc.stdout.strip()
        }
    except Exception as e:
        status = NOT_MEASURED if (isinstance(e, FileNotFoundError) and sys.platform != "darwin") else FAIL
        detail = "NOT MEASURED — csrutil not available on Linux host" if status == NOT_MEASURED else f"Error querying csrutil: {e}"
        return {
            "name": "SIP",
            "status": status,
            "enabled": False,
            "detail": detail
        }


def check_gatekeeper() -> Dict[str, Any]:
    """Inspect macOS Gatekeeper status."""
    try:
        proc = subprocess.run(["spctl", "--status"], capture_output=True, text=True, check=False)
        enabled = "assessments enabled" in proc.stdout.lower()
        return {
            "name": "Gatekeeper",
            "status": PASS if enabled else FAIL,
            "enabled": enabled,
            "detail": proc.stdout.strip()
        }
    except Exception as e:
        status = NOT_MEASURED if (isinstance(e, FileNotFoundError) and sys.platform != "darwin") else FAIL
        detail = "NOT MEASURED — spctl not available on Linux host" if status == NOT_MEASURED else f"Error querying spctl: {e}"
        return {
            "name": "Gatekeeper",
            "status": status,
            "enabled": False,
            "detail": detail
        }


# ── Network Exposure: PostgreSQL Loopback Binding (AC2) ──────────────────────

def check_postgres_binding() -> Dict[str, Any]:
    """
    Ensure PostgreSQL (which holds the restore-verification copy of production)
    binds strictly to loopback (127.0.0.1 or ::1) and is not reachable from LAN.
    """
    try:
        proc = subprocess.run(
            ["lsof", "-nP", "-iTCP:5432", "-sTCP:LISTEN"],
            capture_output=True, text=True, check=False
        )
    except Exception as e:
        return {
            "name": "Postgres Loopback Binding",
            "status": FAIL,
            "is_loopback_only": False,
            "listeners": [],
            "detail": f"Error running lsof: {e}"
        }

    lines = [ln.strip() for ln in proc.stdout.strip().splitlines() if ln.strip()]
    if len(lines) <= 1:
        # Header only or empty output — postgres is not running
        return {
            "name": "Postgres Loopback Binding",
            "status": PASS,
            "is_loopback_only": True,
            "listeners": [],
            "detail": "Postgres not running on port 5432 (safe: 0 external exposure)"
        }

    listeners = []
    is_loopback_only = True
    loopback_patterns = [r"127\.0\.0\.1:5432", r"\[::1\]:5432", r"localhost:5432"]

    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 9:
            address = parts[8]
            listeners.append(address)
            if not any(re.search(pat, address) for pat in loopback_patterns):
                is_loopback_only = False

    status = PASS if is_loopback_only else FAIL
    detail = (
        f"Postgres listening exclusively on loopback ({', '.join(listeners)})"
        if is_loopback_only
        else f"CRITICAL: Postgres bound to non-loopback interface ({', '.join(listeners)})"
    )

    return {
        "name": "Postgres Loopback Binding",
        "status": status,
        "is_loopback_only": is_loopback_only,
        "listeners": listeners,
        "detail": detail
    }


# ── Startup Surface Scanner (AC3) ─────────────────────────────────────────────

def scan_login_items() -> List[str]:
    """Scan macOS login items via AppleScript."""
    try:
        cmd = 'tell application "System Events" to get name of every login item'
        proc = subprocess.run(["osascript", "-e", cmd], capture_output=True, text=True, check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            return [item.strip() for item in proc.stdout.strip().split(",") if item.strip()]
    except Exception:
        pass
    return []


def scan_root_daemons() -> List[str]:
    """Scan /Library/LaunchDaemons."""
    p = Path("/Library/LaunchDaemons")
    if p.exists() and p.is_dir():
        return sorted([f.stem for f in p.glob("*.plist")])
    return []


def scan_user_launch_agents() -> List[str]:
    """Scan ~/Library/LaunchAgents."""
    p = Path.home() / "Library" / "LaunchAgents"
    if p.exists() and p.is_dir():
        return sorted([f.stem for f in p.glob("*.plist")])
    return []


def get_loaded_launch_labels() -> Set[str]:
    """Query launchctl list to get currently loaded labels."""
    try:
        proc = subprocess.run(["launchctl", "list"], capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            labels = set()
            for line in proc.stdout.splitlines()[1:]:
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    labels.add(parts[2].strip())
            return labels
    except Exception:
        pass
    return set()


def check_startup_surface(baseline_path: Path = DEFAULT_BASELINE) -> Dict[str, Any]:
    """
    Audit login items, user LaunchAgents, and root LaunchDaemons against baseline.
    Separates loaded vs dead-but-present plists and flags any unregistered daemons.
    """
    if not baseline_path.exists():
        return {
            "name": "Startup Surface Ratchet",
            "status": FAIL,
            "detail": f"Missing baseline file: {baseline_path}",
            "unregistered_daemons": [],
            "unregistered_login_items": [],
            "unregistered_agents": [],
            "dead_but_present_agents": []
        }

    try:
        with open(baseline_path, "r", encoding="utf-8") as f:
            baseline = json.load(f)
    except Exception as e:
        return {
            "name": "Startup Surface Ratchet",
            "status": FAIL,
            "detail": f"Failed to parse baseline: {e}",
            "unregistered_daemons": [],
            "unregistered_login_items": [],
            "unregistered_agents": [],
            "dead_but_present_agents": []
        }

    expected_daemons = baseline.get("root_daemons", {})
    expected_login = baseline.get("login_items", {})
    expected_agents = baseline.get("user_launch_agents", {})
    limits = baseline.get("limits", {})

    live_daemons = scan_root_daemons()
    live_login = scan_login_items()
    live_agents = scan_user_launch_agents()
    loaded_labels = get_loaded_launch_labels()

    unregistered_daemons = [d for d in live_daemons if d not in expected_daemons]
    unregistered_login = [l for l in live_login if l not in expected_login]
    unregistered_agents = [a for a in live_agents if a not in expected_agents]

    # Distinguish loaded vs dead-but-present in user LaunchAgents
    dead_but_present_agents = [a for a in live_agents if a not in loaded_labels]

    max_daemons = limits.get("unregistered_daemons_max", 0)
    max_login = limits.get("unregistered_login_items_max", 0)
    max_agents = limits.get("unregistered_agents_max", 0)

    violations = []
    if len(unregistered_daemons) > max_daemons:
        violations.append(f"{len(unregistered_daemons)} unregistered root daemon(s): {', '.join(unregistered_daemons)}")
    if len(unregistered_login) > max_login:
        violations.append(f"{len(unregistered_login)} unregistered login item(s): {', '.join(unregistered_login)}")
    if len(unregistered_agents) > max_agents:
        violations.append(f"{len(unregistered_agents)} unregistered user agent(s): {', '.join(unregistered_agents)}")

    status = FAIL if violations else PASS
    detail = (
        "; ".join(violations)
        if violations
        else f"{len(live_daemons)} root daemons, {len(live_login)} login items, {len(live_agents)} agents (all registered; {len(dead_but_present_agents)} dead-but-present)"
    )

    return {
        "name": "Startup Surface Ratchet",
        "status": status,
        "detail": detail,
        "unregistered_daemons": unregistered_daemons,
        "unregistered_login_items": unregistered_login,
        "unregistered_agents": unregistered_agents,
        "dead_but_present_agents": dead_but_present_agents,
        "live_daemons_count": len(live_daemons),
        "live_login_count": len(live_login),
        "live_agents_count": len(live_agents)
    }


# ── TCC Grants Inspection (AC4) ───────────────────────────────────────────────

def check_tcc_grants(db_path: Path = Path("/Library/Application Support/com.apple.TCC/TCC.db")) -> Dict[str, Any]:
    """
    Enumerate TCC grants (Camera, Mic, Screen Recording, Full Disk Access).
    FAIL-CLOSED rule: If TCC.db cannot be read (requires FDA), it must report
    NOT MEASURED, never 'clean'.
    """
    if not db_path.exists():
        return {
            "name": "TCC Grants",
            "status": NOT_MEASURED,
            "detail": "NOT MEASURED — TCC.db does not exist at specified path",
            "grants": {},
            "is_clean_claim": False
        }

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute("SELECT service, client, allowed FROM access WHERE allowed = 1;")
        rows = cursor.fetchall()
        conn.close()

        grants: Dict[str, List[str]] = {}
        for service, client, allowed in rows:
            grants.setdefault(service, []).append(client)

        return {
            "name": "TCC Grants",
            "status": PASS,
            "detail": f"Successfully enumerated {len(rows)} active TCC privilege grant(s)",
            "grants": grants,
            "is_clean_claim": True
        }
    except Exception as e:
        # Authorization denied / Permission denied is the standard non-FDA response
        return {
            "name": "TCC Grants",
            "status": NOT_MEASURED,
            "detail": f"NOT MEASURED — Full Disk Access (FDA required to read TCC.db: {e})",
            "grants": {},
            "is_clean_claim": False
        }


# ── Unmeasured Dimensions (AC6) ───────────────────────────────────────────────

def check_unmeasured_dimensions() -> Dict[str, Dict[str, str]]:
    """
    Explicitly list dimensions that are out of scope for v1 as NOT MEASURED
    with stated technical rationale (per T96 AC3).
    """
    return {
        "outbound_network_traffic": {
            "name": "Outbound Network Traffic",
            "status": NOT_MEASURED,
            "reason": "Host outbound network connections and background telemetry not captured in v1 (requires kernel/eBPF network packet inspection)."
        },
        "browser_extensions": {
            "name": "Browser Extensions",
            "status": NOT_MEASURED,
            "reason": "Browser extension manifests and permissions are not enumerated in v1 (requires per-browser profile directory traversal)."
        }
    }


# ── Posture Evaluation & Runner ───────────────────────────────────────────────

def evaluate_host_posture(baseline_path: Path = DEFAULT_BASELINE, enforce: bool = False) -> Dict[str, Any]:
    """Run all host checks and return aggregated posture report."""
    checks = [
        check_firewall(),
        check_filevault(),
        check_sip(),
        check_gatekeeper(),
        check_postgres_binding(),
        check_startup_surface(baseline_path),
        check_tcc_grants(),
    ]

    unmeasured = check_unmeasured_dimensions()

    has_fail = any(c["status"] == FAIL for c in checks)
    has_warn = any(c["status"] == WARN for c in checks)

    if has_fail:
        overall_status = FAIL
    elif has_warn:
        overall_status = WARN
    else:
        overall_status = PASS

    report = {
        "overall_status": overall_status,
        "checks": checks,
        "unmeasured": unmeasured
    }

    return report


def print_report(report: Dict[str, Any]) -> None:
    """Format and print human-readable posture report."""
    print("▶ macOS Host Security Posture — T233 (Host & Startup Controls)")
    print()
    print("  ── Core Host Controls & Network Exposure")
    for c in report["checks"]:
        print(f"  {c['status']:<16} {c['name']:<28} {c['detail']}")

    print()
    print("  ── Unmeasured Dimensions (T96 AC3 / T233 AC6)")
    for key, item in report["unmeasured"].items():
        print(f"  {item['status']:<16} {item['name']:<28} {item['reason']}")

    print()
    print(f"Overall Posture: {report['overall_status']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit macOS host security controls and startup baseline.")
    parser.add_argument("--enforce", action="store_true", help="Exit 1 on any check FAIL")
    parser.add_argument("--json", action="store_true", help="Output JSON formatted report")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE, help="Path to startup baseline JSON")
    parser.add_argument("--test", action="store_true", help="Run offline unit tests")
    args = parser.parse_args()

    if args.test:
        test_file = ROOT / "wom7web" / "project" / "scripts" / "tests" / "test_host_posture.py"
        proc = subprocess.run([sys.executable, str(test_file)])
        return proc.returncode

    report = evaluate_host_posture(baseline_path=args.baseline, enforce=args.enforce)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)

    if args.enforce and report["overall_status"] == FAIL:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
