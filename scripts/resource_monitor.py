#!/usr/bin/env python3
"""Unified Estate Resource Governance — Audit, Threshold Guard & Safe Reclaim (`T343` AC1-AC4).

Reports combined storage consumption and reclaimable footprint across the estate's disk-consuming
subsystems on both macOS Apple Silicon (`darwin`) and Linux (`linux`):
1. **iOS Simulators (`simctl`)**: `xcrun simctl list` & `~/Library/Developer/CoreSimulator/Devices` (macOS-only)
2. **Local LLM Weights & Caches**: `~/.cache/huggingface`, `~/.cache/w0m-mlx`, `~/.ollama`, `~/Library/Application Support/oMLX`
3. **Virtual Machines & MicroVMs**: `tart list` (`~/.tart/vms`, `~/.tart/cache`), UTM (`~/Library/Containers/com.utmapp.UTM`), Apple `container` (`~/Library/Application Support/com.apple.container`)
4. **Docker Storage**: `docker system df` (Images, Containers, Local Volumes, Build Cache)
5. **Estate Worktrees**: `~/.w0m/work/*` (active agent worktrees) & `~/.w0m/releases/*` (release worktrees)

Invariants:
- **AC3 (10% Free-Disk Threshold Guard)**: Warns non-blockingly when host free disk drops below `10.0%`
  (`DEFAULT_WARN_FREE_PCT = 10.0`), surfaced in both `just resources` and `just preflight`.
- **AC4 (Managed vs Unmanaged VM Boundary)**: Deliberately-unmanaged VMs (`evercred`, `bridgeroad`) are
  reported with `[UNMANAGED — PROTECTED]` visibility in `audit_resources()` and are strictly refused
  by `prune_resources()` — the tool never crosses the managed/unmanaged boundary.
- **Safe-by-Default Reclaim (`just resources-prune`)**: Defaults to `--dry-run`; passing `--apply`
  reclaims only safe, reversible caches (`xcrun simctl delete unavailable`, `docker system prune -f`,
  stale Tart OCI cache entries) and never deletes a named VM.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Callable

DEFAULT_WARN_FREE_PCT = 10.0
UNMANAGED_PROTECTED_VMS: frozenset[str] = frozenset({"evercred", "bridgeroad"})


def format_bytes(num_bytes: int | float) -> str:
    """Format byte count into human-readable units (B, KB, MB, GB)."""
    val = float(max(0, num_bytes))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if val < 1024.0 or unit == "TB":
            return f"{val:.1f} {unit}" if unit != "B" else f"{int(val)} B"
        val /= 1024.0
    return f"{val:.1f} TB"


def dir_size_bytes(path: Path) -> int:
    """Compute recursive byte size of a directory without following symlinks."""
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    try:
        for root, _dirs, files in os.walk(path, followlinks=False):
            root_p = Path(root)
            for fname in files:
                fpath = root_p / fname
                try:
                    if not fpath.is_symlink():
                        total += fpath.stat().st_size
                except OSError:
                    continue
    except OSError:
        pass
    return total


def check_host_disk_headroom(
    target_path: Path = Path("/"),
    warn_below_pct: float = DEFAULT_WARN_FREE_PCT,
    usage_override: tuple[int, int, int] | None = None,
) -> dict[str, Any]:
    """Measure host disk usage and evaluate the AC3 10% free-space threshold guard."""
    if usage_override is not None:
        total_b, used_b, free_b = usage_override
    else:
        usage = shutil.disk_usage(target_path)
        total_b, used_b, free_b = usage.total, usage.used, usage.free

    free_pct = round((free_b * 100.0 / total_b), 2) if total_b > 0 else 0.0
    low_disk_warning = free_pct < warn_below_pct
    headline = (
        f"LOW DISK WARNING: {free_pct:.1f}% free ({format_bytes(free_b)} free of {format_bytes(total_b)}) "
        f"< {warn_below_pct:.1f}% threshold — run `just resources` / `just resources-prune`"
        if low_disk_warning
        else f"{free_pct:.1f}% free ({format_bytes(free_b)} free of {format_bytes(total_b)}, threshold >= {warn_below_pct:.1f}%)"
    )
    return {
        "path": str(target_path),
        "total_bytes": total_b,
        "used_bytes": used_b,
        "free_bytes": free_b,
        "total_human": format_bytes(total_b),
        "used_human": format_bytes(used_b),
        "free_human": format_bytes(free_b),
        "free_pct": free_pct,
        "warn_below_pct": warn_below_pct,
        "low_disk_warning": low_disk_warning,
        "headline": headline,
    }


def probe_simulators(
    home: Path | None = None,
    platform_name: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Probe iOS Simulator storage (`simctl` + CoreSimulator data dir on macOS)."""
    plat = platform_name or sys.platform
    h = home or Path.home()
    sim_dir = h / "Library" / "Developer" / "CoreSimulator" / "Devices"
    if plat != "darwin":
        return {
            "subsystem": "simulators",
            "supported": False,
            "size_bytes": 0,
            "size_human": "0 B (non-darwin host)",
            "items": [],
        }

    size_b = dir_size_bytes(sim_dir)
    devices_summary = "simctl unavailable"
    try:
        proc = runner(
            ["xcrun", "simctl", "list", "devices"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0:
            booted = proc.stdout.count("(Booted)")
            shutdown = proc.stdout.count("(Shutdown)")
            devices_summary = f"{booted} booted, {shutdown} shutdown"
    except (OSError, subprocess.SubprocessError):
        pass

    return {
        "subsystem": "simulators",
        "supported": True,
        "size_bytes": size_b,
        "size_human": format_bytes(size_b),
        "items": [
            {
                "name": "CoreSimulator/Devices",
                "path": str(sim_dir),
                "size_bytes": size_b,
                "size_human": format_bytes(size_b),
                "detail": devices_summary,
                "managed": True,
            }
        ],
    }


def probe_llm_caches(home: Path | None = None) -> dict[str, Any]:
    """Probe local LLM weight caches (Hugging Face, w0m-mlx 4-bit weights, Ollama, oMLX)."""
    h = home or Path.home()
    candidates = [
        ("huggingface", h / ".cache" / "huggingface"),
        ("w0m-mlx", h / ".cache" / "w0m-mlx"),
        ("ollama", h / ".ollama"),
        ("omlx-app-support", h / "Library" / "Application Support" / "oMLX"),
    ]
    items: list[dict[str, Any]] = []
    total_b = 0
    for name, path in candidates:
        sb = dir_size_bytes(path)
        total_b += sb
        items.append(
            {
                "name": name,
                "path": str(path),
                "exists": path.exists(),
                "size_bytes": sb,
                "size_human": format_bytes(sb),
                "managed": True,
            }
        )
    return {
        "subsystem": "llm_weights",
        "size_bytes": total_b,
        "size_human": format_bytes(total_b),
        "items": items,
    }


def is_unmanaged_vm(vm_name: str) -> bool:
    """Return True if a VM name matches a protected unmanaged VM (`evercred`, `bridgeroad`, AC4)."""
    lowered = vm_name.strip().lower()
    return any(u in lowered for u in UNMANAGED_PROTECTED_VMS)


def probe_vms_and_microvms(
    home: Path | None = None,
    platform_name: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Probe Tart VMs, Tart OCI cache, UTM containers, and Apple `container` microVMs (AC1, AC4)."""
    plat = platform_name or sys.platform
    h = home or Path.home()
    items: list[dict[str, Any]] = []
    total_b = 0

    tart_vms_dir = h / ".tart" / "vms"
    tart_cache_dir = h / ".tart" / "cache"
    utm_dir = h / "Library" / "Containers" / "com.utmapp.UTM" / "Data" / "Documents"
    apple_container_dir = h / "Library" / "Application Support" / "com.apple.container"

    # 1. Tart VMs via `tart list` or `~/.tart/vms`
    seen_tart_vms: set[str] = set()
    if plat == "darwin":
        tart_bin = shutil.which("tart") or "/opt/homebrew/bin/tart"
        if Path(tart_bin).is_file():
            try:
                proc = runner(
                    [tart_bin, "list"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if proc.returncode == 0:
                    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
                    for ln in lines[1:]:
                        parts = ln.split()
                        if len(parts) >= 2:
                            vname = parts[1]
                            seen_tart_vms.add(vname)
                            vpath = tart_vms_dir / vname
                            sb = dir_size_bytes(vpath)
                            total_b += sb
                            unmanaged = is_unmanaged_vm(vname)
                            items.append(
                                {
                                    "name": f"tart:{vname}",
                                    "vm_name": vname,
                                    "path": str(vpath),
                                    "size_bytes": sb,
                                    "size_human": format_bytes(sb),
                                    "managed": not unmanaged,
                                    "governance": "UNMANAGED — PROTECTED (AC4)" if unmanaged else "MANAGED",
                                }
                            )
            except (OSError, subprocess.SubprocessError):
                pass

    if tart_vms_dir.is_dir():
        for child in sorted(tart_vms_dir.iterdir()):
            if not child.is_dir() or child.name in seen_tart_vms:
                continue
            sb = dir_size_bytes(child)
            total_b += sb
            unmanaged = is_unmanaged_vm(child.name)
            items.append(
                {
                    "name": f"tart:{child.name}",
                    "vm_name": child.name,
                    "path": str(child),
                    "size_bytes": sb,
                    "size_human": format_bytes(sb),
                    "managed": not unmanaged,
                    "governance": "UNMANAGED — PROTECTED (AC4)" if unmanaged else "MANAGED",
                }
            )

    # 2. Tart OCI cache
    cache_b = dir_size_bytes(tart_cache_dir)
    total_b += cache_b
    items.append(
        {
            "name": "tart-oci-cache",
            "path": str(tart_cache_dir),
            "size_bytes": cache_b,
            "size_human": format_bytes(cache_b),
            "managed": True,
            "governance": "MANAGED_CACHE",
        }
    )

    # 3. UTM VMs (`evercred`, `bridgeroad`, etc.)
    if utm_dir.is_dir():
        for child in sorted(utm_dir.iterdir()):
            if child.suffix == ".utm" or child.is_dir():
                vname = child.stem
                sb = dir_size_bytes(child)
                total_b += sb
                unmanaged = is_unmanaged_vm(vname)
                items.append(
                    {
                        "name": f"utm:{vname}",
                        "vm_name": vname,
                        "path": str(child),
                        "size_bytes": sb,
                        "size_human": format_bytes(sb),
                        "managed": not unmanaged,
                        "governance": "UNMANAGED — PROTECTED (AC4)" if unmanaged else "MANAGED",
                    }
                )

    # 4. Apple `container` microVM runtime data
    ac_b = dir_size_bytes(apple_container_dir)
    total_b += ac_b
    items.append(
        {
            "name": "apple-container-microvms",
            "path": str(apple_container_dir),
            "size_bytes": ac_b,
            "size_human": format_bytes(ac_b),
            "managed": True,
            "governance": "MANAGED",
        }
    )

    return {
        "subsystem": "vms",
        "size_bytes": total_b,
        "size_human": format_bytes(total_b),
        "items": items,
    }


def probe_docker(
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Probe Docker storage consumption via `docker system df`."""
    docker_bin = shutil.which("docker") or "/opt/homebrew/bin/docker"
    rows: list[dict[str, str]] = []
    reachable = False
    if Path(docker_bin).is_file():
        try:
            proc = runner(
                [docker_bin, "system", "df", "--format", "{{json .}}"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                reachable = True
                for line in proc.stdout.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        rows.append(
                            {
                                "type": str(obj.get("Type", "")),
                                "total_count": str(obj.get("TotalCount", "0")),
                                "active": str(obj.get("Active", "0")),
                                "size": str(obj.get("Size", "0B")),
                                "reclaimable": str(obj.get("Reclaimable", "0B")),
                            }
                        )
                    except ValueError:
                        continue
        except (OSError, subprocess.SubprocessError):
            pass

    return {
        "subsystem": "docker",
        "reachable": reachable,
        "rows": rows,
    }


def probe_worktrees(home: Path | None = None) -> dict[str, Any]:
    """Probe `~/.w0m/work/*` agent worktrees and `~/.w0m/releases/*` release worktrees."""
    h = home or Path.home()
    work_dir = h / ".w0m" / "work"
    rel_dir = h / ".w0m" / "releases"
    items: list[dict[str, Any]] = []
    total_b = 0

    for label, base in (("agent-worktree", work_dir), ("release-worktree", rel_dir)):
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            sb = dir_size_bytes(child)
            total_b += sb
            items.append(
                {
                    "name": f"{label}:{child.name}",
                    "path": str(child),
                    "size_bytes": sb,
                    "size_human": format_bytes(sb),
                }
            )
    return {
        "subsystem": "worktrees",
        "size_bytes": total_b,
        "size_human": format_bytes(total_b),
        "items": items,
    }


def audit_resources(
    home: Path | None = None,
    warn_below_pct: float = DEFAULT_WARN_FREE_PCT,
    usage_override: tuple[int, int, int] | None = None,
) -> dict[str, Any]:
    """Compile the unified estate resource audit across all subsystems (`T343` AC1, AC3, AC4)."""
    disk = check_host_disk_headroom(
        target_path=Path("/"),
        warn_below_pct=warn_below_pct,
        usage_override=usage_override,
    )
    sims = probe_simulators(home=home)
    llms = probe_llm_caches(home=home)
    vms = probe_vms_and_microvms(home=home)
    docker = probe_docker()
    worktrees = probe_worktrees(home=home)

    return {
        "disk": disk,
        "subsystems": {
            "simulators": sims,
            "llm_weights": llms,
            "vms": vms,
            "docker": docker,
            "worktrees": worktrees,
        },
        "protected_unmanaged_vms": sorted(UNMANAGED_PROTECTED_VMS),
    }


def prune_resources(
    *,
    apply: bool = False,
    target_vm: str | None = None,
    home: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Reclaim safe caches (`simctl delete unavailable`, `docker system prune -f`, Tart OCI cache).

    Enforces AC4: refuses outright if `target_vm` names an unmanaged VM (`evercred`, `bridgeroad`),
    and never prunes or reconfigures any unmanaged VM during global cache reclaim.
    """
    if target_vm and is_unmanaged_vm(target_vm):
        raise PermissionError(
            f"Refusing to prune or modify unmanaged VM {target_vm!r} (T343 AC4). "
            f"Protected unmanaged VMs ({', '.join(sorted(UNMANAGED_PROTECTED_VMS))}) are reported for "
            "visibility only and must never be touched by resources-prune."
        )

    h = home or Path.home()
    actions: list[dict[str, Any]] = []

    # 1. Simulator unavailable runtimes (macOS)
    if sys.platform == "darwin":
        sim_cmd = ["xcrun", "simctl", "delete", "unavailable"]
        if apply:
            proc = runner(sim_cmd, capture_output=True, text=True, timeout=30, check=False)
            actions.append(
                {
                    "subsystem": "simulators",
                    "command": " ".join(sim_cmd),
                    "status": "APPLIED" if proc.returncode == 0 else "SKIPPED",
                }
            )
        else:
            actions.append({"subsystem": "simulators", "command": " ".join(sim_cmd), "status": "DRY_RUN"})

    # 2. Dangling Docker images/containers/build cache (never volumes with data)
    docker_bin = shutil.which("docker") or "/opt/homebrew/bin/docker"
    docker_cmd = [docker_bin, "system", "prune", "-f"]
    if apply and Path(docker_bin).is_file():
        proc = runner(docker_cmd, capture_output=True, text=True, timeout=60, check=False)
        actions.append(
            {
                "subsystem": "docker",
                "command": "docker system prune -f",
                "status": "APPLIED" if proc.returncode == 0 else "SKIPPED",
            }
        )
    else:
        actions.append({"subsystem": "docker", "command": "docker system prune -f", "status": "DRY_RUN"})

    # 3. Tart OCI cache (`~/.tart/cache`) — safe cache only, never `~/.tart/vms` or UTM VMs
    tart_cache = h / ".tart" / "cache"
    cache_bytes = dir_size_bytes(tart_cache)
    if apply and tart_cache.is_dir():
        shutil.rmtree(tart_cache, ignore_errors=True)
        tart_cache.mkdir(parents=True, exist_ok=True)
        actions.append(
            {
                "subsystem": "tart-oci-cache",
                "path": str(tart_cache),
                "reclaimed_bytes": cache_bytes,
                "status": "APPLIED",
            }
        )
    else:
        actions.append(
            {
                "subsystem": "tart-oci-cache",
                "path": str(tart_cache),
                "reclaimable_bytes": cache_bytes,
                "status": "DRY_RUN",
            }
        )

    return {
        "ok": True,
        "apply": apply,
        "dry_run": not apply,
        "protected_unmanaged_vms": sorted(UNMANAGED_PROTECTED_VMS),
        "actions": actions,
    }


def print_audit_report(report: dict[str, Any]) -> None:
    disk = report["disk"]
    status_badge = "[WARN: LOW DISK]" if disk["low_disk_warning"] else "[OK]"
    print("=== w0m Unified Estate Resource Governance Audit (T343) ===")
    print(f"Host Disk ({disk['path']}): {status_badge} {disk['headline']}\n")

    subs = report["subsystems"]
    sim = subs["simulators"]
    print(f"1. iOS Simulators (`simctl`): {sim['size_human']}")
    for item in sim["items"]:
        print(f"   - {item['name']}: {item['size_human']} ({item.get('detail', '')})")

    llm = subs["llm_weights"]
    print(f"\n2. Local LLM Weights & Caches: {llm['size_human']}")
    for item in llm["items"]:
        print(f"   - {item['name']}: {item['size_human']} ({item['path']})")

    vms = subs["vms"]
    print(f"\n3. Virtual Machines & MicroVMs (Tart / UTM / Apple Container): {vms['size_human']}")
    for item in vms["items"]:
        gov = item.get("governance", "MANAGED")
        print(f"   - {item['name']}: {item['size_human']} [{gov}] ({item['path']})")
    print(f"   * Protected Unmanaged VMs (AC4 — visibility only, never pruned): {', '.join(report['protected_unmanaged_vms'])}")

    docker = subs["docker"]
    print(f"\n4. Docker Storage (`docker system df`): {'reachable' if docker['reachable'] else 'offline'}")
    for row in docker["rows"]:
        print(
            f"   - {row['type']:14s}: total={row['total_count']} active={row['active']} "
            f"size={row['size']} reclaimable={row['reclaimable']}"
        )

    wt = subs["worktrees"]
    print(f"\n5. Estate Agent & Release Worktrees (`~/.w0m/work`, `~/.w0m/releases`): {wt['size_human']}")
    for item in wt["items"]:
        print(f"   - {item['name']}: {item['size_human']} ({item['path']})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Unified Estate Resource Governance — Audit & Safe Reclaim (T343)."
    )
    parser.add_argument("--prune", action="store_true", help="Run safe cache reclaim (dry-run by default; pass --apply to execute)")
    parser.add_argument("--apply", action="store_true", help="Execute safe cache reclaim when paired with --prune")
    parser.add_argument("--target-vm", default=None, help="Optional VM target (refuses unmanaged VMs per AC4)")
    parser.add_argument("--warn-below-pct", type=float, default=DEFAULT_WARN_FREE_PCT, help="Low-disk warning threshold percentage (default: 10.0)")
    parser.add_argument("--json", action="store_true", help="Output structured JSON")
    args = parser.parse_args(argv)

    try:
        if args.prune:
            res = prune_resources(apply=bool(args.apply), target_vm=args.target_vm)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                mode = "APPLIED" if res["apply"] else "DRY-RUN (pass --apply to reclaim)"
                print(f"=== w0m Resource Prune ({mode}) ===")
                for act in res["actions"]:
                    print(f"  [{act['status']}] {act['subsystem']}: {act.get('command') or act.get('path')}")
                print(f"  [PROTECTED] Unmanaged VMs untouched (AC4): {', '.join(res['protected_unmanaged_vms'])}")
            return 0

        report = audit_resources(warn_below_pct=args.warn_below_pct)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print_audit_report(report)
        return 0
    except PermissionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
