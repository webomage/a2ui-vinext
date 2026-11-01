from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import host_service_probe  # noqa: E402
import oci_sandbox  # noqa: E402


def test_discover_all_engines_returns_local_sandboxes() -> None:
    sandboxes = oci_sandbox.discover_all_engines(include_remote=False)
    names = {s.name for s in sandboxes}
    assert "colima" in names
    assert "apple-container" in names
    assert "docker-native" in names
    assert "podman" in names
    assert all(s.scope == "local" for s in sandboxes)


def test_resolve_docker_host_prefers_running_colima_socket() -> None:
    fake = [
        oci_sandbox.SandboxEngineStatus(
            name="colima",
            kind="oci-docker-api",
            scope="local",
            installed=True,
            running=True,
            version="0.10.3",
            endpoint="unix:///Users/test/.colima/default/docker.sock",
            docker_api_compatible=True,
            details={"server_version": "29.5.2"},
        ),
        oci_sandbox.SandboxEngineStatus(
            name="apple-container",
            kind="oci-native",
            scope="local",
            installed=True,
            running=True,
            version="1.6.1",
            endpoint="xpc://com.apple.container.apiserver",
            docker_api_compatible=False,
        ),
    ]
    endpoint, eng = oci_sandbox.resolve_docker_host("auto", engines=fake)
    assert eng.name == "colima"
    assert endpoint == "unix:///Users/test/.colima/default/docker.sock"


def test_build_remote_ssh_tunnel_command_forwards_supabase_ports() -> None:
    cmd = oci_sandbox.build_remote_ssh_tunnel_command("linux-host")
    assert cmd[0] == "ssh"
    assert "127.0.0.1:54321:127.0.0.1:54321" in cmd
    assert "127.0.0.1:8791:127.0.0.1:8791" in cmd
    assert cmd[-1] == "linux-host"


def test_cmd_status_json_output(capsys) -> None:
    rc = oci_sandbox.main(["status", "--json", "--no-remote"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert any(item["name"] == "colima" for item in payload)


def test_cmd_env_prints_colima_socket_when_running(capsys) -> None:
    fake_colima = oci_sandbox.SandboxEngineStatus(
        name="colima",
        kind="oci-docker-api",
        scope="local",
        installed=True,
        running=True,
        version="0.10.3",
        endpoint="unix:///Users/test/.colima/default/docker.sock",
        docker_api_compatible=True,
    )
    with patch.object(oci_sandbox, "discover_all_engines", return_value=[fake_colima]):
        rc = oci_sandbox.main(["env"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "unix:///Users/test/.colima/default/docker.sock"


def test_verify_engine_service_and_version_checks_both_identity_and_version() -> None:
    svc, ver, ok = oci_sandbox.verify_engine_service_and_version("colima", "colima version v0.10.3")
    assert svc == "colima"
    assert ok is True

    _, _, wrong_svc = oci_sandbox.verify_engine_service_and_version("colima", "podman version v0.10.3")
    assert wrong_svc is False

    _, _, wrong_ver = oci_sandbox.verify_engine_service_and_version("colima", "colima version v0.5.0")
    assert wrong_ver is False


def test_host_service_probe_verifies_replying_service_and_expected_version() -> None:
    target = host_service_probe.ServiceProbeTarget(
        name="app:cp",
        url="http://127.0.0.1:4325/api/health",
        service_field="service",
        expected_service="cp",
        expected_version="local-abc1234",
        version_match="exact",
    )
    good = host_service_probe.verify_probe_payload(
        target,
        200,
        {"service": "cp", "status": "ok", "version": "local-abc1234"},
    )
    assert good.ok is True
    assert good.service_ok is True
    assert good.version_ok is True

    wrong_service = host_service_probe.verify_probe_payload(
        target,
        200,
        {"service": "web", "status": "ok", "version": "local-abc1234"},
    )
    assert wrong_service.ok is False
    assert wrong_service.service_ok is False
    assert "service mismatch" in wrong_service.error

    wrong_version = host_service_probe.verify_probe_payload(
        target,
        200,
        {"service": "cp", "status": "ok", "version": "stale-old-version"},
    )
    assert wrong_version.ok is False
    assert wrong_version.version_ok is False
    assert "version mismatch" in wrong_version.error
