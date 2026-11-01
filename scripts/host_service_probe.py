#!/usr/bin/env python3
"""Host & Service Identity + Expected Version Probe (`T480`).

Ensures every local or remote host endpoint replies with BOTH:
  1. The expected service identity (`service` / `name` field in JSON health payload)
  2. The expected service version (`version` exact match or expected prefix)

Probed services:
  - `web`              (`http://127.0.0.1:4321/api/health`) -> `service == "web"`, `status == "ok"`
  - `job`              (`http://127.0.0.1:4322/api/health`) -> `service == "job"`, `status == "ok"`
  - `join`             (`http://127.0.0.1:4323/api/health`) -> `service == "join"`, `status == "ok"`
  - `demo`             (`http://127.0.0.1:4324/api/health`) -> `service == "demo"`, `status == "ok"`
  - `cp`               (`http://127.0.0.1:4325/api/health`) -> `service == "cp"`, `status == "ok"`
  - `supabase-auth`    (`http://127.0.0.1:54321/auth/v1/health`) -> `name == "GoTrue"`, `version` prefix `"v2."`
  - `edge-local-proxy` (`http://127.0.0.1:8791/health`, when `--include-edge-proxy`) -> `service == "w0m-edge-local-proxy"`
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

ASTRO_APP_SPECS: tuple[tuple[str, int], ...] = (
    ("web", 4321),
    ("job", 4322),
    ("join", 4323),
    ("demo", 4324),
    ("cp", 4325),
)


@dataclass
class ServiceProbeTarget:
    name: str
    url: str
    service_field: str
    expected_service: str
    expected_version: str
    version_match: str = "exact"  # "exact" | "prefix" | "nonempty"


@dataclass
class ServiceProbeResult:
    name: str
    url: str
    reachable: bool
    http_status: int
    expected_service: str
    actual_service: str
    service_ok: bool
    expected_version: str
    actual_version: str
    version_ok: bool
    ok: bool
    error: str = ""


def verify_probe_payload(
    target: ServiceProbeTarget,
    http_status: int,
    payload: dict[str, Any],
) -> ServiceProbeResult:
    actual_service = str(payload.get(target.service_field, "")).strip()
    actual_version = str(payload.get("version", "")).strip()
    status_field = str(payload.get("status", "ok")).strip()

    service_ok = actual_service == target.expected_service and status_field in ("ok", "healthy", "")
    if target.version_match == "exact":
        version_ok = actual_version == target.expected_version
    elif target.version_match == "prefix":
        version_ok = actual_version.startswith(target.expected_version)
    else:
        version_ok = bool(actual_version) and actual_version != "unknown"

    ok = (200 <= http_status < 300) and service_ok and version_ok
    err_parts: list[str] = []
    if not (200 <= http_status < 300):
        err_parts.append(f"HTTP {http_status}")
    if not service_ok:
        err_parts.append(
            f"service mismatch (expected '{target.expected_service}', got '{actual_service}', status='{status_field}')"
        )
    if not version_ok:
        err_parts.append(
            f"version mismatch (expected {target.version_match} '{target.expected_version}', got '{actual_version}')"
        )

    return ServiceProbeResult(
        name=target.name,
        url=target.url,
        reachable=True,
        http_status=http_status,
        expected_service=target.expected_service,
        actual_service=actual_service,
        service_ok=service_ok,
        expected_version=target.expected_version,
        actual_version=actual_version,
        version_ok=version_ok,
        ok=ok,
        error="; ".join(err_parts),
    )


def probe_single_target(target: ServiceProbeTarget, timeout: float = 3.0) -> ServiceProbeResult:
    if not target.url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise ValueError(f"Refusing non-loopback probe URL: {target.url}")
    req = urllib.request.Request(target.url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected -- loopback guard enforced above
            status = resp.status
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return ServiceProbeResult(
            name=target.name,
            url=target.url,
            reachable=True,
            http_status=exc.code,
            expected_service=target.expected_service,
            actual_service="",
            service_ok=False,
            expected_version=target.expected_version,
            actual_version="",
            version_ok=False,
            ok=False,
            error=f"HTTPError {exc.code}",
        )
    except Exception as exc:
        return ServiceProbeResult(
            name=target.name,
            url=target.url,
            reachable=False,
            http_status=0,
            expected_service=target.expected_service,
            actual_service="",
            service_ok=False,
            expected_version=target.expected_version,
            actual_version="",
            version_ok=False,
            ok=False,
            error=str(exc),
        )

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("JSON root is not an object")
    except Exception as exc:
        return ServiceProbeResult(
            name=target.name,
            url=target.url,
            reachable=True,
            http_status=status,
            expected_service=target.expected_service,
            actual_service="",
            service_ok=False,
            expected_version=target.expected_version,
            actual_version="",
            version_ok=False,
            ok=False,
            error=f"Invalid JSON health response: {exc}",
        )

    return verify_probe_payload(target, status, payload)


def build_default_targets(
    expected_app_version: str = "",
    include_apps: bool = True,
    include_supabase: bool = True,
    include_edge_proxy: bool = False,
    gotrue_version_prefix: str = "v2.",
) -> list[ServiceProbeTarget]:
    targets: list[ServiceProbeTarget] = []
    if include_supabase:
        targets.append(
            ServiceProbeTarget(
                name="supabase-auth",
                url="http://127.0.0.1:54321/auth/v1/health",
                service_field="name",
                expected_service="GoTrue",
                expected_version=gotrue_version_prefix,
                version_match="prefix",
            )
        )
    if include_apps:
        ver_mode = "exact" if expected_app_version else "nonempty"
        for service_name, port in ASTRO_APP_SPECS:
            targets.append(
                ServiceProbeTarget(
                    name=f"app:{service_name}",
                    url=f"http://127.0.0.1:{port}/api/health",
                    service_field="service",
                    expected_service=service_name,
                    expected_version=expected_app_version or "nonempty",
                    version_match=ver_mode,
                )
            )
    if include_edge_proxy:
        ver_mode = "exact" if expected_app_version else "nonempty"
        targets.append(
            ServiceProbeTarget(
                name="edge-local-proxy",
                url="http://127.0.0.1:8791/health",
                service_field="service",
                expected_service="w0m-edge-local-proxy",
                expected_version=expected_app_version or "local",
                version_match=ver_mode,
            )
        )
    return targets


def probe_all(
    targets: list[ServiceProbeTarget],
    wait_seconds: float = 0.0,
    poll_interval: float = 1.0,
) -> list[ServiceProbeResult]:
    deadline = time.monotonic() + max(0.0, wait_seconds)
    while True:
        results = [probe_single_target(t) for t in targets]
        if all(r.ok for r in results) or time.monotonic() >= deadline:
            return results
        time.sleep(poll_interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify host/service identity and expected version (T480)")
    parser.add_argument("--expect-version", default="", help="Expected DEPLOY_VERSION for Astro apps and edge proxy")
    parser.add_argument("--wait", type=float, default=0.0, help="Max seconds to wait for all targets to pass")
    parser.add_argument("--no-apps", action="store_true", help="Skip Astro app port probes (4321..4325)")
    parser.add_argument("--no-supabase", action="store_true", help="Skip Supabase GoTrue health probe (54321)")
    parser.add_argument("--include-edge-proxy", action="store_true", help="Also verify edge-local proxy on 8791")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args(argv)

    targets = build_default_targets(
        expected_app_version=args.expect_version,
        include_apps=not args.no_apps,
        include_supabase=not args.no_supabase,
        include_edge_proxy=args.include_edge_proxy,
    )
    results = probe_all(targets, wait_seconds=args.wait)
    all_ok = all(r.ok for r in results)

    if args.json:
        print(json.dumps({"ok": all_ok, "results": [asdict(r) for r in results]}, indent=2))
    else:
        for r in results:
            badge = "✅" if r.ok else "❌"
            detail = (
                f"service='{r.actual_service}' (expected '{r.expected_service}'), "
                f"version='{r.actual_version}' (expected '{r.expected_version}')"
            )
            if r.error:
                detail += f" — {r.error}"
            print(f"  {badge} {r.name:<18} {r.url:<38} {detail}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
