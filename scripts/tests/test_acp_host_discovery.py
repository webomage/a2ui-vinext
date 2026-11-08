"""Unit tests for `scripts/acp_host_discovery.py` (`T681`)."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acp_host_discovery import (  # noqa: E402
    ACP_PROTOCOL_VERSION,
    build_acp_jsonrpc_message,
    discover_acp_agent_endpoints,
    discover_host_agent_sessions,
    evaluate_seo_geo_security_from_artifacts,
    validate_public_scan_url,
)


def test_ssrf_guard_blocks_loopback_and_private_ips() -> None:
    ok_local, _, _ = validate_public_scan_url("http://localhost:8080/admin")
    assert not ok_local

    ok_loopback, _, _ = validate_public_scan_url("http://127.0.0.1:8770")
    assert not ok_loopback

    ok_meta, _, _ = validate_public_scan_url("http://169.254.169.254/latest/meta-data/")
    assert not ok_meta

    ok_pub, norm, host = validate_public_scan_url("webomage.com")
    assert ok_pub
    assert norm == "https://webomage.com/"
    assert host == "webomage.com"


def test_evaluates_seo_geo_and_security_scores_deterministically() -> None:
    html = """<!doctype html>
    <html>
      <head>
        <title>Webomage — Agentic Engineering, Security & Cloud Platform</title>
        <meta name="description" content="Webomage builds edge-first AI platforms, security scanners, and autonomous engineering workflows on Cloudflare and Rust." />
        <link rel="canonical" href="https://webomage.com/" />
        <meta property="og:title" content="Webomage Platform" />
        <script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Webomage"}</script>
      </head>
      <body>
        <main>
          <article>
            <h1>Webomage Engineering & AI Platform</h1>
            <time datetime="2026-11-08">November 8, 2026</time>
          </article>
        </main>
      </body>
    </html>"""
    headers = {
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
        "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
    }
    report = evaluate_seo_geo_security_from_artifacts(
        target_url="https://webomage.com/",
        hostname="webomage.com",
        html_body=html,
        response_headers=headers,
        robots_txt="User-agent: *\nAllow: /\nSitemap: https://webomage.com/sitemap.xml\n",
        sitemap_xml="<urlset></urlset>",
        llms_txt="# Webomage\n> Edge AI, Rust @k7 TUIs, and ACP multi-agent orchestration.\n",
        security_txt="Contact: mailto:security@webomage.com\nExpires: 2027-12-31T00:00:00Z\n",
    )
    assert report.seo_score == 100
    assert report.geo_score == 100
    assert report.security_score == 100
    assert report.overall_score == 100
    assert report.letter_grade == "A"


def test_builds_acp_jsonrpc_messages_with_tenant_scope() -> None:
    init_msg = build_acp_jsonrpc_message("initialize")
    assert init_msg["jsonrpc"] == "2.0"
    assert init_msg["method"] == "initialize"
    assert init_msg["params"]["protocolVersion"] == ACP_PROTOCOL_VERSION
    assert init_msg["params"]["capabilities"]["tablinuxWasm"] is True

    sess_msg = build_acp_jsonrpc_message("session/new", project_id="artemio")
    scope = sess_msg["params"]["projectScope"]
    assert scope["projectId"] == "artemio"
    assert scope["accountEmail"] == "artemio@webomage.com"
    assert scope["infisicalSecretKey"] == "MISTRAL_API_KEY_ARTEMIO"
    assert scope["crossProjectAccess"] is False


def test_discovers_same_host_sessions_and_acp_endpoints(tmp_path: Path) -> None:
    work_dir = tmp_path / ".w0m" / "work" / "t681-demo" / "w0m"
    work_dir.mkdir(parents=True)
    sessions = discover_host_agent_sessions(home_dir=tmp_path)
    ids = {s.session_id for s in sessions}
    assert "w0m-worktree:t681-demo" in ids
    assert "orca-host:primary" in ids
    assert "mistral-vibe:w0m" in ids

    endpoints = discover_acp_agent_endpoints()
    agent_ids = {e.agent_id for e in endpoints}
    assert {
        "orca-acp",
        "mistral-vibe-acp",
        "claude-code-acp",
        "codex-acp",
        "k7hub-acp",
        "k7kb-acp",
    }.issubset(agent_ids)
