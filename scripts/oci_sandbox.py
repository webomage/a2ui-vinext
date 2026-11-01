#!/usr/bin/env python3
"""Multi-engine OCI & VM Sandbox Orchestrator across local (macOS) and remote (Linux SSH) hosts (`T480`).

Supports discovering, starting, and resolving `DOCKER_HOST` / sandbox endpoints across:
  1. `colima`          — Local macOS VZ + virtiofs Docker Engine (`unix://$HOME/.colima/default/docker.sock`)
  2. `apple-container` — Local macOS 26 native `container` (`container-apiserver` + Kata arm64 microVMs)
  3. `docker-native`   — Native local Docker socket (`/var/run/docker.sock` or `~/.docker/run/docker.sock`)
  4. `podman`          — Local or remote rootless Podman Docker-compatible socket
  5. `tart` / `devpod` — Local full VM sandboxes
  6. `remote-ssh`      — Remote Linux SSH host (`linux-host`, `ssh://linux-host`) with automatic
                         SSH local port-forwarding for Supabase ports (`54321`–`54324`, `8791`).

Usage:
  python3 scripts/oci_sandbox.py status [--json]
  python3 scripts/oci_sandbox.py env [--provider <auto|colima|docker-native|podman|remote-ssh>]
  python3 scripts/oci_sandbox.py up [--provider <auto|colima|apple-container|remote-ssh>] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SUPABASE_PORTS: tuple[int, ...] = (54321, 54322, 54323, 54324, 8791)
DEFAULT_REMOTE_HOST = "linux-host"

EXPECTED_ENGINE_VERSIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "colima": ("colima", ("v0.10.", "0.10.")),
    "apple-container": ("container CLI", ("1.6.", "1.")),
    "docker-native": ("Docker", ("29.", "28.", "27.")),
    "podman": ("podman", ("5.", "4.")),
    "tart": ("tart", ("3.", "2.")),
    "devpod": ("devpod", ("v0.16.", "0.16.", "v0.")),
    "remote-ssh": ("Docker", ("29.", "28.", "27.")),
}


def verify_engine_service_and_version(engine_key: str, raw_version_output: str) -> tuple[str, str, bool]:
    """Verify that the probed binary/daemon identifies as the expected service and matches expected version prefixes."""
    expected_service, prefixes = EXPECTED_ENGINE_VERSIONS.get(engine_key, (engine_key, ()))
    expected_ver_label = "/".join(prefixes) if prefixes else "any"
    text = raw_version_output.strip()
    if not text or text == "-":
        return expected_service, expected_ver_label, False
    service_ok = expected_service.lower() in text.lower() or engine_key.split("-")[0].lower() in text.lower()
    version_ok = any(p in text for p in prefixes) if prefixes else True
    return expected_service, expected_ver_label, (service_ok and version_ok)


@dataclass
class SandboxEngineStatus:
    name: str
    kind: str  # "oci-docker-api" | "oci-native" | "vm-sandbox" | "remote-oci"
    scope: str  # "local" | "remote"
    installed: bool
    running: bool
    version: str
    endpoint: str
    docker_api_compatible: bool
    expected_service: str = ""
    expected_version: str = ""
    version_ok: bool = False
    details: dict[str, Any] = field(default_factory=dict)


def _run(
    cmd: list[str],
    timeout: float = 8.0,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = dict(os.environ)
    merged_env["PATH"] = (
        f"/opt/homebrew/opt/rustup/bin:{Path.home() / '.local/bin'}:/opt/homebrew/bin:"
        f"/usr/local/bin:/usr/bin:/bin:{merged_env.get('PATH', '')}"
    )
    if env:
        merged_env.update(env)
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=merged_env,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return subprocess.CompletedProcess(cmd, returncode=124, stdout="", stderr=str(exc))


def probe_colima(home: Path | None = None) -> SandboxEngineStatus:
    h = home or Path.home()
    sock = h / ".colima" / "default" / "docker.sock"
    colima_bin = shutil.which("colima") or (
        "/opt/homebrew/bin/colima" if Path("/opt/homebrew/bin/colima").exists() else None
    )
    installed = colima_bin is not None
    version = "-"
    running = False
    details: dict[str, Any] = {}

    if installed and colima_bin:
        ver_res = _run([colima_bin, "version"], timeout=4.0)
        for line in ver_res.stdout.splitlines():
            if "colima version" in line.lower():
                version = line.strip().split()[-1]
                break
        if sock.exists():
            docker_bin = shutil.which("docker") or "/opt/homebrew/bin/docker"
            info_res = _run(
                [
                    docker_bin,
                    "info",
                    "--format",
                    "{{.ServerVersion}}|{{.Architecture}}|{{.NCPU}}|{{.MemTotal}}",
                ],
                timeout=5.0,
                env={"DOCKER_HOST": f"unix://{sock}"},
            )
            if info_res.returncode == 0 and info_res.stdout.strip():
                running = True
                parts = info_res.stdout.strip().split("|")
                if len(parts) == 4:
                    details = {
                        "server_version": parts[0],
                        "arch": parts[1],
                        "cpus": parts[2],
                        "mem_bytes": parts[3],
                    }

    exp_svc, exp_ver, ver_ok = verify_engine_service_and_version("colima", f"colima {version}")
    return SandboxEngineStatus(
        name="colima",
        kind="oci-docker-api",
        scope="local",
        installed=installed,
        running=running,
        version=version,
        endpoint=f"unix://{sock}" if sock.exists() else f"unix://{sock} (stopped)",
        docker_api_compatible=True,
        expected_service=exp_svc,
        expected_version=exp_ver,
        version_ok=ver_ok,
        details=details,
    )


def probe_apple_container() -> SandboxEngineStatus:
    container_bin = shutil.which("container") or (
        "/opt/homebrew/bin/container" if Path("/opt/homebrew/bin/container").exists() else None
    )
    installed = container_bin is not None
    version = "-"
    running = False
    details: dict[str, Any] = {}

    if installed and container_bin:
        ver_res = _run([container_bin, "--version"], timeout=4.0)
        if ver_res.returncode == 0 and ver_res.stdout.strip():
            version = ver_res.stdout.strip()
        st_res = _run([container_bin, "system", "status"], timeout=5.0)
        if st_res.returncode == 0:
            for line in st_res.stdout.splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2 and parts[0] != "FIELD":
                    details[parts[0]] = parts[1].strip()
            running = details.get("status") == "running"

    exp_svc, exp_ver, ver_ok = verify_engine_service_and_version("apple-container", version)
    return SandboxEngineStatus(
        name="apple-container",
        kind="oci-native",
        scope="local",
        installed=installed,
        running=running,
        version=version,
        endpoint="xpc://com.apple.container.apiserver",
        docker_api_compatible=False,
        expected_service=exp_svc,
        expected_version=exp_ver,
        version_ok=ver_ok,
        details=details,
    )


def probe_docker_native(home: Path | None = None) -> SandboxEngineStatus:
    h = home or Path.home()
    candidates = [
        Path("/var/run/docker.sock"),
        h / ".docker" / "run" / "docker.sock",
    ]
    sock = next((p for p in candidates if p.exists()), candidates[0])
    docker_bin = shutil.which("docker") or (
        "/opt/homebrew/bin/docker" if Path("/opt/homebrew/bin/docker").exists() else None
    )
    installed = docker_bin is not None
    version = "-"
    running = False

    if installed and docker_bin:
        ver_res = _run([docker_bin, "--version"], timeout=4.0)
        if ver_res.returncode == 0 and ver_res.stdout.strip():
            version = ver_res.stdout.strip()
        if sock.exists():
            info_res = _run(
                [docker_bin, "info", "--format", "{{.ServerVersion}}"],
                timeout=4.0,
                env={"DOCKER_HOST": f"unix://{sock}"},
            )
            running = info_res.returncode == 0 and bool(info_res.stdout.strip())

    exp_svc, exp_ver, ver_ok = verify_engine_service_and_version("docker-native", version)
    return SandboxEngineStatus(
        name="docker-native",
        kind="oci-docker-api",
        scope="local",
        installed=installed,
        running=running,
        version=version,
        endpoint=f"unix://{sock}",
        docker_api_compatible=True,
        expected_service=exp_svc,
        expected_version=exp_ver,
        version_ok=ver_ok,
    )


def probe_podman(home: Path | None = None) -> SandboxEngineStatus:
    h = home or Path.home()
    podman_bin = shutil.which("podman") or (
        "/opt/homebrew/bin/podman" if Path("/opt/homebrew/bin/podman").exists() else None
    )
    installed = podman_bin is not None
    version = "-"
    running = False
    sock = h / ".local" / "share" / "containers" / "podman" / "machine" / "podman.sock"

    if installed and podman_bin:
        ver_res = _run([podman_bin, "--version"], timeout=4.0)
        if ver_res.returncode == 0 and ver_res.stdout.strip():
            version = ver_res.stdout.strip()
        info_res = _run([podman_bin, "info", "--format", "{{.Host.RemoteSocket.Exists}}"], timeout=4.0)
        running = info_res.returncode == 0 and "true" in info_res.stdout.lower()

    exp_svc, exp_ver, ver_ok = verify_engine_service_and_version("podman", version)
    return SandboxEngineStatus(
        name="podman",
        kind="oci-docker-api",
        scope="local",
        installed=installed,
        running=running,
        version=version,
        endpoint=f"unix://{sock}",
        docker_api_compatible=True,
        expected_service=exp_svc,
        expected_version=exp_ver,
        version_ok=ver_ok,
    )


def probe_tart_and_devpod() -> list[SandboxEngineStatus]:
    results: list[SandboxEngineStatus] = []
    tart_bin = shutil.which("tart") or (
        "/opt/homebrew/bin/tart" if Path("/opt/homebrew/bin/tart").exists() else None
    )
    if tart_bin:
        ver = _run([tart_bin, "--version"], timeout=4.0).stdout.strip() or "-"
        ls_res = _run([tart_bin, "list", "--format", "json"], timeout=4.0)
        vms: list[dict[str, Any]] = []
        if ls_res.returncode == 0 and ls_res.stdout.strip():
            try:
                parsed: list[dict[str, Any]] = json.loads(ls_res.stdout)
                vms = parsed
            except json.JSONDecodeError:
                pass
        running_vms = [v for v in vms if v.get("State") == "running" or v.get("Running") is True]
        exp_svc, exp_ver, ver_ok = verify_engine_service_and_version("tart", f"tart {ver}")
        results.append(
            SandboxEngineStatus(
                name="tart",
                kind="vm-sandbox",
                scope="local",
                installed=True,
                running=len(running_vms) > 0,
                version=ver,
                endpoint=f"tart://local ({len(vms)} VMs, {len(running_vms)} running)",
                docker_api_compatible=False,
                expected_service=exp_svc,
                expected_version=exp_ver,
                version_ok=ver_ok,
                details={"vms_total": len(vms), "vms_running": len(running_vms)},
            )
        )

    devpod_bin = shutil.which("devpod") or (
        "/opt/homebrew/bin/devpod" if Path("/opt/homebrew/bin/devpod").exists() else None
    )
    if devpod_bin:
        ver = _run([devpod_bin, "version"], timeout=4.0).stdout.strip() or "-"
        exp_svc, exp_ver, ver_ok = verify_engine_service_and_version("devpod", f"devpod {ver}")
        results.append(
            SandboxEngineStatus(
                name="devpod",
                kind="vm-sandbox",
                scope="local",
                installed=True,
                running=True,
                version=ver,
                endpoint="devpod://local",
                docker_api_compatible=False,
                expected_service=exp_svc,
                expected_version=exp_ver,
                version_ok=ver_ok,
            )
        )
    return results


def probe_remote_ssh(ssh_host: str = DEFAULT_REMOTE_HOST) -> SandboxEngineStatus:
    remote_cmd = (
        "export PATH=/home/linuxbrew/.linuxbrew/sbin:/home/linuxbrew/.linuxbrew/bin:"
        "/usr/local/bin:/usr/bin:/bin:$PATH; "
        "docker_bin=$(which docker 2>/dev/null || true); "
        "supa_bin=$(which supabase 2>/dev/null || true); "
        "ver=$($docker_bin --version 2>/dev/null || echo '-'); "
        "sock_ok=0; "
        "if [ -S /var/run/docker.sock ] || [ -S /run/user/$(id -u)/docker.sock ]; then sock_ok=1; fi; "
        "printf '%s|%s|%s|%s\\n' \"$docker_bin\" \"$supa_bin\" \"$ver\" \"$sock_ok\""
    )
    res = _run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=4", ssh_host, remote_cmd],
        timeout=7.0,
    )
    if res.returncode != 0 or not res.stdout.strip():
        exp_svc, exp_ver, _ = verify_engine_service_and_version("remote-ssh", "")
        return SandboxEngineStatus(
            name=f"remote-ssh:{ssh_host}",
            kind="remote-oci",
            scope="remote",
            installed=False,
            running=False,
            version="-",
            endpoint=f"ssh://{ssh_host}",
            docker_api_compatible=True,
            expected_service=exp_svc,
            expected_version=exp_ver,
            version_ok=False,
            details={"reachable": False},
        )

    parts = res.stdout.strip().splitlines()[-1].split("|")
    docker_bin = parts[0] if len(parts) > 0 else ""
    supa_bin = parts[1] if len(parts) > 1 else ""
    ver = parts[2] if len(parts) > 2 else "-"
    sock_ok = (parts[3] == "1") if len(parts) > 3 else False
    exp_svc, exp_ver, ver_ok = verify_engine_service_and_version("remote-ssh", ver)

    return SandboxEngineStatus(
        name=f"remote-ssh:{ssh_host}",
        kind="remote-oci",
        scope="remote",
        installed=bool(docker_bin),
        running=sock_ok,
        version=ver,
        endpoint=f"ssh://{ssh_host}",
        docker_api_compatible=True,
        expected_service=exp_svc,
        expected_version=exp_ver,
        version_ok=ver_ok,
        details={
            "reachable": True,
            "docker_bin": docker_bin,
            "supabase_bin": supa_bin,
            "forwarded_ports": list(SUPABASE_PORTS),
        },
    )


def discover_all_engines(
    home: Path | None = None,
    remote_host: str = DEFAULT_REMOTE_HOST,
    include_remote: bool = True,
) -> list[SandboxEngineStatus]:
    engines: list[SandboxEngineStatus] = [
        probe_colima(home),
        probe_apple_container(),
        probe_docker_native(home),
        probe_podman(home),
        *probe_tart_and_devpod(),
    ]
    if include_remote:
        engines.append(probe_remote_ssh(remote_host))
    return engines


def resolve_docker_host(
    preferred: str = "auto",
    engines: list[SandboxEngineStatus] | None = None,
) -> tuple[str, SandboxEngineStatus]:
    """Resolve the active `DOCKER_HOST` URI for tools that speak the Docker Engine REST API (`supabase`, `db_baseline.py`)."""
    pool = engines if engines is not None else discover_all_engines(include_remote=preferred == "remote-ssh")
    docker_capable = [e for e in pool if e.docker_api_compatible]

    if preferred != "auto":
        for eng in docker_capable:
            if eng.name == preferred or eng.name.startswith(f"{preferred}:"):
                if not eng.running:
                    raise RuntimeError(
                        f"Requested OCI provider '{preferred}' is installed={eng.installed} but not running ({eng.endpoint})."
                    )
                return eng.endpoint, eng
        raise RuntimeError(f"Unknown or non-Docker-compatible OCI provider '{preferred}'.")

    # Auto priority order: running local Colima -> running local docker-native -> running local podman -> running remote-ssh
    for eng in docker_capable:
        if eng.running:
            return eng.endpoint, eng

    raise RuntimeError(
        "No running Docker-API compatible OCI engine found (checked colima, docker-native, podman, remote-ssh). "
        "Run `just oci-up` to start one."
    )


def build_remote_ssh_tunnel_command(
    ssh_host: str = DEFAULT_REMOTE_HOST,
    ports: tuple[int, ...] = SUPABASE_PORTS,
) -> list[str]:
    cmd = ["ssh", "-N", "-f", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=30"]
    for p in ports:
        cmd.extend(["-L", f"127.0.0.1:{p}:127.0.0.1:{p}"])
    cmd.append(ssh_host)
    return cmd


def ensure_engine_up(
    provider: str = "auto",
    dry_run: bool = False,
) -> dict[str, Any]:
    target = "colima" if provider == "auto" else provider
    if target == "colima":
        status = probe_colima()
        if status.running:
            return {"ok": True, "provider": "colima", "action": "already-running", "DOCKER_HOST": status.endpoint}
        cmd = ["colima", "start", "--vm-type", "vz", "--mount-type", "virtiofs", "--cpu", "4", "--memory", "8"]
        if dry_run:
            return {"ok": True, "provider": "colima", "action": "dry-run", "command": cmd}
        res = _run(cmd, timeout=180.0)
        after = probe_colima()
        return {
            "ok": res.returncode == 0 and after.running,
            "provider": "colima",
            "action": "started",
            "DOCKER_HOST": after.endpoint,
        }

    if target == "apple-container":
        status = probe_apple_container()
        if status.running:
            return {"ok": True, "provider": "apple-container", "action": "already-running", "endpoint": status.endpoint}
        cmd = ["container", "system", "start"]
        if dry_run:
            return {"ok": True, "provider": "apple-container", "action": "dry-run", "command": cmd}
        res = _run(cmd, timeout=120.0)
        after = probe_apple_container()
        return {
            "ok": res.returncode == 0 and after.running,
            "provider": "apple-container",
            "action": "started",
            "endpoint": after.endpoint,
        }

    if target.startswith("remote-ssh"):
        ssh_host = target.split(":", 1)[1] if ":" in target else DEFAULT_REMOTE_HOST
        tunnel_cmd = build_remote_ssh_tunnel_command(ssh_host)
        if dry_run:
            return {
                "ok": True,
                "provider": f"remote-ssh:{ssh_host}",
                "action": "dry-run",
                "DOCKER_HOST": f"ssh://{ssh_host}",
                "tunnel_command": tunnel_cmd,
            }
        _run(tunnel_cmd, timeout=10.0)
        return {
            "ok": True,
            "provider": f"remote-ssh:{ssh_host}",
            "action": "tunnel-established",
            "DOCKER_HOST": f"ssh://{ssh_host}",
            "tunnel_command": tunnel_cmd,
        }

    raise RuntimeError(f"Unsupported provider '{provider}' for `up`.")


def format_status_table(engines: list[SandboxEngineStatus]) -> str:
    lines = [
        "| Engine | Kind | Scope | Installed | Running | Docker API | Version | Endpoint |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for e in engines:
        lines.append(
            f"| `{e.name}` | `{e.kind}` | `{e.scope}` | "
            f"{'yes' if e.installed else 'no'} | {'yes' if e.running else 'no'} | "
            f"{'yes' if e.docker_api_compatible else 'no'} | `{e.version}` | `{e.endpoint}` |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Multi-engine OCI & VM Sandbox Orchestrator (T480)")
    sub = parser.add_subparsers(dest="command")

    p_status = sub.add_parser("status", help="Show status of all local and remote OCI/VM sandbox engines")
    p_status.add_argument("--json", action="store_true", help="Output JSON")
    p_status.add_argument("--no-remote", action="store_true", help="Skip remote SSH probe")

    p_env = sub.add_parser("env", help="Print resolved DOCKER_HOST for shell export")
    p_env.add_argument("--provider", default="auto", help="Preferred provider (auto|colima|docker-native|podman|remote-ssh)")

    p_up = sub.add_parser("up", help="Start the requested OCI/sandbox engine")
    p_up.add_argument("--provider", default="auto", help="Provider to start (auto|colima|apple-container|remote-ssh)")
    p_up.add_argument("--dry-run", action="store_true", help="Print command without executing")

    args = parser.parse_args(argv)
    cmd = args.command or "status"

    if cmd == "status":
        engines = discover_all_engines(include_remote=not getattr(args, "no_remote", False))
        if getattr(args, "json", False):
            print(json.dumps([asdict(e) for e in engines], indent=2))
        else:
            print(format_status_table(engines))
        return 0

    if cmd == "env":
        try:
            endpoint, _ = resolve_docker_host(preferred=args.provider)
            print(endpoint)
            return 0
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    if cmd == "up":
        try:
            result = ensure_engine_up(provider=args.provider, dry_run=args.dry_run)
            print(json.dumps(result, indent=2))
            return 0 if result.get("ok") else 1
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
