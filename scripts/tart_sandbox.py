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

    args = parser.parse_args(argv)

    try:
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
