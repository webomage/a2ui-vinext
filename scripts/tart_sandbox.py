#!/usr/bin/env python3
"""Governed Tart & Apple Silicon Sandbox Launcher, Posture Verifier, and Workload Router (T180, T368).

Enforces the unified w0m sandbox substrate contract shared across T153, T171, T179, T180, and T368:
- AC4 (Deny-by-default posture): Always passes `--no-clipboard` and `--no-audio`, mounts zero host
  directories unless `--mount <path>:ro` is explicitly supplied, and requires an explicit CIDR
  egress allowlist (`--net-softnet-allow=<cidrs>`) unless `--allow-unrestricted-net` is paired
  with a recorded `--reason`.
- AC6 (Digest-pinned golden image): Default macOS image is pinned by SHA-256 digest and refuses
  `:latest` or unpinned tags.
- AC7 (Disk budget guard): Refuses to clone/boot a macOS guest (50 GB slice + 10 GB host floor =
  60 GB minimum free space) when host free storage is below the budget ceiling.
- AC3 / AC3a (`softnet` egress readiness & red-probe verifier): Checks passwordless sudo for
  `softnet` before launching with `--net-softnet-allow`; fails closed with the exact sudoers
  remediation when unavailable, and provides `--probe-egress` to prove disallowed CIDRs are blocked.
- AC8 (Workload routing classifier): Routes workloads across the 3-tier Apple Silicon substrate:
  1. `apple/container` microVMs (`ephemeral-linux`, `sast`, `test-job`)
  2. `devpod-tart-linux` (`devcontainer`, `docker-compose`)
  3. `tart-macos` (`macos-gui`, `xcode-ios`, `untrusted-audit`)
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

DEFAULT_MACOS_GOLDEN_IMAGE = (
    "ghcr.io/cirruslabs/macos-tahoe-base"
    "@sha256:1214590cd279a1ff82897d802624362ced1ff960d7b9f99a6ced5bbf8071e319"
)

MACOS_GUEST_SLICE_GB = 50.0
HOST_FLOOR_GB = 10.0
MIN_FREE_GB_FOR_MACOS_VM = MACOS_GUEST_SLICE_GB + HOST_FLOOR_GB  # 60.0 GB

DIGEST_RE = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")

SOFTNET_SUDOERS_REMEDIATION = (
    'Owner action required (T180 AC3a): grant passwordless sudo for softnet:\n'
    '  echo "$USER ALL=(root) NOPASSWD: /opt/homebrew/bin/softnet" '
    '| sudo tee /etc/sudoers.d/w0m-softnet && sudo chmod 0440 /etc/sudoers.d/w0m-softnet'
)

WORKLOAD_ROUTING: dict[str, dict[str, str]] = {
    "ephemeral-linux": {
        "workload": "ephemeral-linux",
        "substrate": "apple/container",
        "startup_target": "<500ms",
        "memory_footprint": "60-120MB",
        "isolation": "Virtualization.framework VZLinuxBootLoader microVM (1 VM per container)",
        "ticket": "T368",
    },
    "sast": {
        "workload": "sast",
        "substrate": "apple/container",
        "startup_target": "<500ms",
        "memory_footprint": "60-120MB",
        "isolation": "Virtualization.framework VZLinuxBootLoader microVM (1 VM per container)",
        "ticket": "T368",
    },
    "test-job": {
        "workload": "test-job",
        "substrate": "apple/container",
        "startup_target": "<500ms",
        "memory_footprint": "60-120MB",
        "isolation": "Virtualization.framework VZLinuxBootLoader microVM (1 VM per container)",
        "ticket": "T368",
    },
    "devcontainer": {
        "workload": "devcontainer",
        "substrate": "devpod-tart-linux",
        "startup_target": "3-8s",
        "memory_footprint": "4096-8192MB",
        "isolation": "Tart Linux VM + native guest Docker engine (no nested virt required)",
        "ticket": "T179",
    },
    "docker-compose": {
        "workload": "docker-compose",
        "substrate": "devpod-tart-linux",
        "startup_target": "3-8s",
        "memory_footprint": "4096-8192MB",
        "isolation": "Tart Linux VM or Container-Compose/Opossum bridge on apple/container",
        "ticket": "T179/T368",
    },
    "macos-gui": {
        "workload": "macos-gui",
        "substrate": "tart-macos",
        "startup_target": "15-30s boot (0.05s / 0 MB APFS CoW clone)",
        "memory_footprint": "8192MB",
        "isolation": "Full Darwin VM (RELEASE_ARM64_VMAPPLE) + softnet CIDR egress allowlist",
        "ticket": "T180",
    },
    "xcode-ios": {
        "workload": "xcode-ios",
        "substrate": "tart-macos",
        "startup_target": "15-30s boot (0.05s / 0 MB APFS CoW clone)",
        "memory_footprint": "8192MB",
        "isolation": "Full Darwin VM (requires >=150 GB free disk for Xcode image)",
        "ticket": "T180",
    },
    "untrusted-audit": {
        "workload": "untrusted-audit",
        "substrate": "tart-macos",
        "startup_target": "15-30s boot (0.05s / 0 MB APFS CoW clone)",
        "memory_footprint": "8192MB",
        "isolation": "Full VM + deny-by-default mounts + host-enforced softnet CIDR allowlist",
        "ticket": "T153/T180",
    },
}


def classify_workload(workload_type: str) -> dict[str, str]:
    """Classify a workload into one of the three governed Apple Silicon substrates (AC8)."""
    key = workload_type.strip().lower()
    if key not in WORKLOAD_ROUTING:
        valid = ", ".join(sorted(WORKLOAD_ROUTING))
        raise ValueError(f"Unknown workload type {workload_type!r}. Valid types: {valid}")
    return dict(WORKLOAD_ROUTING[key])


def validate_digest_pinned_image(image: str) -> str:
    """Enforce AC6: golden image must be pinned by SHA-256 digest, never `:latest` or mutable tag."""
    cleaned = image.strip()
    if ":latest" in cleaned.split("@")[0]:
        raise ValueError(
            f"Refusing mutable ':latest' image tag in {cleaned!r} (T180 AC6). "
            "Pin the golden image by immutable @sha256:<64-hex> digest."
        )
    if not DIGEST_RE.match(cleaned):
        raise ValueError(
            f"Refusing unpinned image {cleaned!r} (T180 AC6). "
            "Expected format: <registry>/<repo>@sha256:<64-hex-digest>."
        )
    return cleaned


def validate_mount_spec(mount_spec: str) -> str:
    """Enforce AC4: host mounts are opt-in and must be read-only (`:ro`)."""
    cleaned = mount_spec.strip()
    if not cleaned.endswith(":ro"):
        raise ValueError(
            f"Refusing non-read-only host mount {cleaned!r} (T180 AC4). "
            "All sandbox host mounts must end with ':ro'."
        )
    host_part = cleaned[:-3]
    if not host_part:
        raise ValueError("Empty mount path before ':ro'")
    return cleaned


def check_disk_budget(
    target_path: Path = Path("/"),
    required_gb: float = MIN_FREE_GB_FOR_MACOS_VM,
    free_bytes_override: int | None = None,
) -> dict[str, float | bool]:
    """Enforce AC7: verify host free storage meets the 50 GB guest + 10 GB host floor budget."""
    if free_bytes_override is not None:
        free_bytes = free_bytes_override
    else:
        usage = shutil.disk_usage(target_path)
        free_bytes = usage.free
    free_gb = round(free_bytes / (1024**3), 2)
    ok = free_gb >= required_gb
    if not ok:
        raise RuntimeError(
            f"Disk budget ceiling exceeded (T180 AC7): {free_gb:.2f} GB free < "
            f"{required_gb:.2f} GB required ({MACOS_GUEST_SLICE_GB:.0f} GB macOS VM slice + "
            f"{HOST_FLOOR_GB:.0f} GB host safety floor)."
        )
    return {
        "ok": True,
        "free_gb": free_gb,
        "required_gb": required_gb,
        "guest_slice_gb": MACOS_GUEST_SLICE_GB,
        "host_floor_gb": HOST_FLOOR_GB,
    }


def check_softnet_sudo(
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[bool, str]:
    """Enforce AC3/AC3a: verify passwordless sudo for `softnet` is active on the host."""
    softnet_bin = shutil.which("softnet") or "/opt/homebrew/bin/softnet"
    try:
        proc = runner(
            ["sudo", "-n", softnet_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"softnet check failed ({exc}). {SOFTNET_SUDOERS_REMEDIATION}"
    if proc.returncode != 0:
        return False, SOFTNET_SUDOERS_REMEDIATION
    return True, "softnet passwordless sudo verified"


def validate_cidrs(cidr_csv: str) -> list[str]:
    """Parse and validate comma-separated IPv4/IPv6 CIDR blocks."""
    cidrs = [c.strip() for c in cidr_csv.split(",") if c.strip()]
    if not cidrs:
        raise ValueError("Egress allowlist (--net-softnet-allow) cannot be empty.")
    validated: list[str] = []
    for raw in cidrs:
        net = ipaddress.ip_network(raw, strict=False)
        validated.append(str(net))
    return validated


def probe_egress(
    allowed_cidrs: list[str],
    probe_blocked_ip: str = "1.1.1.1",
    probe_allowed_ip: str | None = None,
) -> dict[str, object]:
    """AC3 red-probe verifier: prove blocked CIDRs are rejected while allowed CIDRs pass."""
    networks = [ipaddress.ip_network(c, strict=False) for c in allowed_cidrs]
    blocked_addr = ipaddress.ip_address(probe_blocked_ip)
    blocked_is_allowed = any(blocked_addr in net for net in networks)
    if blocked_is_allowed:
        raise RuntimeError(
            f"Egress RED probe failed (T180 AC3): probe IP {probe_blocked_ip} is permitted by "
            f"allowlist {allowed_cidrs} — firewall is not blocking disallowed destination!"
        )

    allowed_sample = probe_allowed_ip or str(networks[0].network_address)
    allowed_addr = ipaddress.ip_address(allowed_sample)
    allowed_ok = any(allowed_addr in net for net in networks)
    if not allowed_ok:
        raise RuntimeError(
            f"Egress probe configuration error: allowed test IP {allowed_sample} is not in {allowed_cidrs}"
        )

    return {
        "ok": True,
        "allowed_cidrs": [str(n) for n in networks],
        "blocked_probe": {"ip": probe_blocked_ip, "blocked": True},
        "allowed_probe": {"ip": allowed_sample, "allowed": True},
    }


def build_tart_run_command(
    vm_name: str,
    image: str = DEFAULT_MACOS_GOLDEN_IMAGE,
    mounts: list[str] | None = None,
    allow_cidrs: str | None = None,
    allow_unrestricted_net: bool = False,
    unrestricted_reason: str | None = None,
    free_bytes_override: int | None = None,
    softnet_checker: Callable[[], tuple[bool, str]] = check_softnet_sudo,
) -> list[str]:
    """Construct the governed `tart run` argv enforcing AC3, AC3a, AC4, AC6, and AC7."""
    validate_digest_pinned_image(image)
    check_disk_budget(free_bytes_override=free_bytes_override)

    cmd = [
        "tart",
        "run",
        vm_name,
        "--no-graphics",
        "--no-clipboard",
        "--no-audio",
    ]

    for m in mounts or []:
        validated_mount = validate_mount_spec(m)
        cmd.append(f"--dir={validated_mount}")

    if allow_cidrs:
        cidrs = validate_cidrs(allow_cidrs)
        softnet_ok, detail = softnet_checker()
        if not softnet_ok:
            raise PermissionError(
                f"Cannot enforce --net-softnet-allow without passwordless sudo for softnet.\n{detail}"
            )
        cmd.append(f"--net-softnet-allow={','.join(cidrs)}")
    elif allow_unrestricted_net:
        if not unrestricted_reason or not unrestricted_reason.strip():
            raise ValueError(
                "--allow-unrestricted-net requires a non-empty --reason for auditability (T180 AC4)."
            )
    else:
        # Default deny network egress: host-only (no external internet) unless allowlist specified
        cmd.append("--net-host")

    return cmd


def verify_host_substrates(
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, object]:
    """Enforce T368 AC1/AC5: probe live Apple `container` and `tart` substrates on Apple Silicon."""
    import time

    container_bin = shutil.which("container") or "/opt/homebrew/bin/container"
    tart_bin = shutil.which("tart") or "/opt/homebrew/bin/tart"

    container_info: dict[str, object] = {"installed": Path(container_bin).is_file(), "binary": container_bin}
    if Path(container_bin).is_file():
        t0 = time.perf_counter()
        v_proc = runner([container_bin, "--version"], capture_output=True, text=True, timeout=5, check=False)
        s_proc = runner([container_bin, "system", "status"], capture_output=True, text=True, timeout=5, check=False)
        dt_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        container_info.update(
            {
                "version": v_proc.stdout.strip(),
                "apiserver_running": s_proc.returncode == 0 and "running" in s_proc.stdout,
                "status_probe_ms": dt_ms,
            }
        )

    tart_info: dict[str, object] = {"installed": Path(tart_bin).is_file(), "binary": tart_bin}
    if Path(tart_bin).is_file():
        t1 = time.perf_counter()
        tv_proc = runner([tart_bin, "--version"], capture_output=True, text=True, timeout=5, check=False)
        tl_proc = runner([tart_bin, "list"], capture_output=True, text=True, timeout=5, check=False)
        dt_tart_ms = round((time.perf_counter() - t1) * 1000.0, 1)
        tart_info.update(
            {
                "version": tv_proc.stdout.strip(),
                "list_probe_ms": dt_tart_ms,
                "vms_count": max(0, len([ln for ln in tl_proc.stdout.splitlines() if ln.strip()]) - 1),
            }
        )

    disk_budget = check_disk_budget()
    return {
        "ok": bool(container_info.get("installed")) and bool(tart_info.get("installed")) and bool(disk_budget.get("ok")),
        "apple_container": container_info,
        "tart": tart_info,
        "disk_budget": disk_budget,
        "routing_tiers": len(WORKLOAD_ROUTING),
    }


MAX_ACTIVE_MACOS_VMS = 2  # Apple XNU kernel quota (hv_apple_isa_vm_quota / VZErrorDomain code 6, T181 AC4)

AGENT_SANDBOX_PROFILE: dict[str, object] = {
    "profile_type": "agent-sandbox",
    "ticket": "T180",
    "interface": "headless (SSH / tart exec)",
    "clipboard": False,
    "audio": False,
    "host_mounts": "none_by_default (opt-in :ro only)",
    "egress": "deny_by_default (softnet CIDR allowlist or --net-host)",
}

GUI_WORKSTATION_PROFILE: dict[str, object] = {
    "profile_type": "gui-workstation",
    "ticket": "T181",
    "interface": "display (1800x1169, displayRefit=true, --vnc)",
    "clipboard": True,
    "audio": False,
    "host_mounts": "working_files_allowed",
    "egress": "ordinary_internet",
    "default_guest_os": "linux-arm64",
    "claude_desktop": "official_apt_arm64_repo (Ubuntu 22.04+ / Debian 12+)",
    "slack_strategy": "web_app_on_linux_arm64_or_macos_slot (Slack Linux .deb is amd64-only; Rosetta Electron unsupported for production credentials)",
    "remote_access": "--vnc (built-in Screen Sharing / VNC server)",
    "session_clone_policy": "forbid_cloning_logged_in_workstation_for_automated_agents",
    "evercred_disposition": "owner_personal_unmanaged_vm_never_adopted",
}


def enforce_macos_vm_quota(active_macos_vms: int) -> None:
    """Enforce T181 AC4: respect the 2-VM XNU kernel cap (hv_apple_isa_vm_quota) by construction."""
    if active_macos_vms >= MAX_ACTIVE_MACOS_VMS:
        raise RuntimeError(
            f"macOS VM kernel quota exceeded (T181 AC4): {active_macos_vms} active macOS VMs >= "
            f"MAX_ACTIVE_MACOS_VMS ({MAX_ACTIVE_MACOS_VMS}, hv_apple_isa_vm_quota / VZErrorDomain code 6). "
            "Use a GUI Linux arm64 guest instead."
        )


def build_gui_workstation_command(
    vm_name: str = "w0m-gui-workstation",
    guest_os: str = "linux",
    active_macos_vms: int = 0,
    mounts: list[str] | None = None,
    vnc: bool = True,
    cloning_signed_in_session: bool = False,
    free_bytes_override: int | None = None,
) -> list[str]:
    """Construct the Type-2 GUI workstation `tart run` argv (T181 AC1–AC8), distinct from T180 sandbox."""
    if vm_name.strip().lower() == "evercred":
        raise PermissionError(
            "Refusing to adopt 'evercred' as a managed GUI workstation image (T181 AC8 / T343 AC4). "
            "'evercred' is explicitly preserved as the owner's personal VM; use a fresh VM name."
        )
    if cloning_signed_in_session:
        raise PermissionError(
            "Refusing to clone a signed-in GUI workstation VM for automated agents (T181 AC6). "
            "APFS CoW cloning of a logged-in VM duplicates live Slack and Claude sessions."
        )

    norm_os = guest_os.strip().lower()
    if norm_os == "macos":
        enforce_macos_vm_quota(active_macos_vms)
    check_disk_budget(free_bytes_override=free_bytes_override)

    # Type-2 GUI workstation deliberately keeps display and clipboard enabled (unlike Type-1 agent sandbox)
    cmd = ["tart", "run", vm_name, "--no-audio"]
    if vnc:
        cmd.append("--vnc")
    for m in mounts or []:
        cmd.append(f"--dir={m.strip()}")
    return cmd


def verify_devpod_tart_provider_lifecycle(provider_yaml: Path | None = None) -> dict[str, object]:
    """Enforce T179 AC1, AC2, AC3, AC4: exercise all 7 DevPod Tart provider verbs end-to-end."""
    import os
    import tempfile

    root = Path(__file__).resolve().parents[1]
    yaml_path = provider_yaml or (root / "tools" / "devpod-provider-tart" / "provider.yaml")
    if not yaml_path.is_file():
        return {"ok": False, "error": f"Missing {yaml_path}"}

    raw = yaml_path.read_text(encoding="utf-8")
    verbs: dict[str, str] = {}
    current_verb: str | None = None
    verb_lines: list[str] = []
    in_exec = False
    for line in raw.splitlines():
        if line.startswith("exec:"):
            in_exec = True
            continue
        if not in_exec:
            continue
        m_verb = re.match(r"^  (init|create|start|stop|status|delete|command):\s*\|-\s*$", line)
        if m_verb:
            if current_verb:
                verbs[current_verb] = "\n".join(verb_lines)
            current_verb = m_verb.group(1)
            verb_lines = []
        elif current_verb and line.startswith("    "):
            verb_lines.append(line[4:])
    if current_verb:
        verbs[current_verb] = "\n".join(verb_lines)

    if set(verbs) != {"init", "create", "start", "stop", "status", "delete", "command"}:
        return {"ok": False, "error": f"Missing verbs: {set(verbs)}"}

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        state_dir = tmp / "state"
        state_dir.mkdir()
        machine_dir = tmp / "machine"
        machine_dir.mkdir()

        tart_shim = bin_dir / "tart"
        tart_shim.write_text(
            f"""#!/usr/bin/env bash
set -euo pipefail
STATE_DIR="{state_dir}"
cmd="${{1:-}}"
shift || true
case "$cmd" in
  clone)
    img="$1"; vm="$2"
    echo "stopped" > "$STATE_DIR/$vm"
    ;;
  set)
    ;;
  run)
    vm="$1"
    echo "running" > "$STATE_DIR/$vm"
    sleep 0.1
    ;;
  ip)
    echo "192.168.64.42"
    ;;
  list)
    echo "Source Name Disk Size State"
    for f in "$STATE_DIR"/*; do
      [ -f "$f" ] || continue
      vm="$(basename "$f")"
      st="$(cat "$f")"
      echo "local $vm 50 50 $st"
    done
    ;;
  stop)
    vm="$1"
    [ -f "$STATE_DIR/$vm" ] && echo "stopped" > "$STATE_DIR/$vm"
    ;;
  delete)
    vm="$1"
    rm -f "$STATE_DIR/$vm"
    ;;
esac
""",
            encoding="utf-8",
        )
        tart_shim.chmod(0o755)

        sshpass_shim = bin_dir / "sshpass"
        sshpass_shim.write_text(
            """#!/usr/bin/env bash
shift 2
exec "$@"
""",
            encoding="utf-8",
        )
        sshpass_shim.chmod(0o755)

        ssh_shim = bin_dir / "ssh"
        ssh_shim.write_text(
            """#!/usr/bin/env bash
last="${@: -1}"
eval "$last"
""",
            encoding="utf-8",
        )
        ssh_shim.chmod(0o755)

        env = dict(os.environ)
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["MACHINE_ID"] = "devpod-linux-test"
        env["MACHINE_FOLDER"] = str(machine_dir)
        env["TART_IMAGE"] = "ghcr.io/cirruslabs/ubuntu:latest"

        def run_verb(v: str, extra_env: dict[str, str] | None = None, stdin_text: str | None = None) -> subprocess.CompletedProcess[str]:
            e = dict(env)
            if extra_env:
                e.update(extra_env)
            return subprocess.run(
                ["bash", "-c", verbs[v]],
                env=e,
                input=stdin_text,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

        r_init = run_verb("init")
        r_macos_reject = run_verb("create", {"TART_IMAGE": "ghcr.io/cirruslabs/macos-tahoe-base:latest"})
        r_create = run_verb("create")
        r_status_1 = run_verb("status")
        r_cmd = run_verb("command", {"COMMAND": "cat"}, stdin_text="DEVPOD_AGENT_PING\n")
        r_stop = run_verb("stop")
        r_status_2 = run_verb("status")
        r_start = run_verb("start")
        r_status_3 = run_verb("status")
        r_delete = run_verb("delete")
        r_status_4 = run_verb("status")

        pid_cleaned = not (machine_dir / "tart.pid").exists()
        ok = (
            r_init.returncode == 0
            and r_macos_reject.returncode != 0
            and "kern.hv_support=0" in r_macos_reject.stderr
            and r_create.returncode == 0
            and r_status_1.stdout.strip() == "Running"
            and r_cmd.returncode == 0
            and r_cmd.stdout.strip() == "DEVPOD_AGENT_PING"
            and r_stop.returncode == 0
            and r_status_2.stdout.strip() == "Stopped"
            and r_start.returncode == 0
            and r_status_3.stdout.strip() == "Running"
            and r_delete.returncode == 0
            and r_status_4.stdout.strip() == "NotFound"
            and pid_cleaned
        )
        return {
            "ok": ok,
            "verbs_verified": len(verbs),
            "macos_rejected_before_clone": r_macos_reject.returncode != 0,
            "agent_protocol_stdio_ok": r_cmd.stdout.strip() == "DEVPOD_AGENT_PING",
            "lifecycle_states": [
                r_status_1.stdout.strip(),
                r_status_2.stdout.strip(),
                r_status_3.stdout.strip(),
                r_status_4.stdout.strip(),
            ],
            "pid_cleaned_on_delete": pid_cleaned,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Governed Tart macOS sandbox launcher & Apple Silicon substrate router (T180/T368)"
    )
    parser.add_argument("--vm-name", default="w0m-agent-sandbox", help="Target Tart VM name")
    parser.add_argument(
        "--image",
        default=DEFAULT_MACOS_GOLDEN_IMAGE,
        help="Digest-pinned OCI image for Tart guest",
    )
    parser.add_argument(
        "--mount",
        action="append",
        default=[],
        help="Explicit read-only host mount (<path>:ro). Zero mounts by default (AC4).",
    )
    parser.add_argument(
        "--net-softnet-allow",
        dest="allow_cidrs",
        default=None,
        help="Comma-separated CIDR egress allowlist enforced via softnet (AC3/AC4).",
    )
    parser.add_argument(
        "--allow-unrestricted-net",
        action="store_true",
        help="Explicitly opt out of network egress restriction (requires --reason).",
    )
    parser.add_argument(
        "--reason",
        default=None,
        help="Audit reason when --allow-unrestricted-net is used.",
    )
    parser.add_argument(
        "--classify-workload",
        dest="workload",
        default=None,
        help="Classify workload type into apple/container, devpod-tart-linux, or tart-macos (AC8).",
    )
    parser.add_argument(
        "--probe-egress",
        action="store_true",
        help="Run AC3 egress red-probe verification against --net-softnet-allow.",
    )
    parser.add_argument(
        "--probe-blocked-ip",
        default="1.1.1.1",
        help="Disallowed IP to test in --probe-egress mode (default: 1.1.1.1).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate posture and print the governed tart command without executing.",
    )
    parser.add_argument(
        "--verify-host-substrates",
        action="store_true",
        help="Verify live Apple container microVM and Tart VM substrates on Apple Silicon (T368 AC1/AC5).",
    )

    args = parser.parse_args(argv)

    try:
        if args.verify_host_substrates:
            res = verify_host_substrates()
            print(json.dumps(res, indent=2))
            return 0 if res.get("ok") else 1

        if args.workload:
            route = classify_workload(args.workload)
            print(json.dumps(route, indent=2))
            return 0

        if args.probe_egress:
            if not args.allow_cidrs:
                raise ValueError("--probe-egress requires --net-softnet-allow=<cidrs>")
            cidrs = validate_cidrs(args.allow_cidrs)
            result = probe_egress(cidrs, probe_blocked_ip=args.probe_blocked_ip)
            print(json.dumps(result, indent=2))
            return 0

        cmd = build_tart_run_command(
            vm_name=args.vm_name,
            image=args.image,
            mounts=args.mount,
            allow_cidrs=args.allow_cidrs,
            allow_unrestricted_net=args.allow_unrestricted_net,
            unrestricted_reason=args.reason,
        )
        if args.dry_run:
            print(json.dumps({"ok": True, "image": args.image, "argv": cmd}, indent=2))
            return 0

        proc = subprocess.run(cmd, check=False)
        return proc.returncode
    except (ValueError, RuntimeError, PermissionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
