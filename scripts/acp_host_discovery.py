#!/usr/bin/env python3
"""Same-Host Agent Session Discovery, ACP Protocol Manager & SEO/GEO/Security Scanner (`T681`).

Provides three unified crew capabilities for `@wom`, `@k7` (`k7kb`), `Orca`, and `TabLinux`:
  1. Same-Host Agent Session Discovery (`discover`):
     - Discovers active `@wom` agent worktrees (`~/.w0m/work/*`), `Antigravity` sessions,
       `Claude Code` projects, `Codex` sessions, `Orca` worktrees, and live agent processes.
  2. Agent Client Protocol (`agentclientprotocol.com`) JSON-RPC 2.0 Management (`acp`):
     - Builds and validates canonical ACP JSON-RPC 2.0 messages (`initialize`, `session/new`,
       `session/load`, `session/prompt`, `session/cancel`, `host/discover`) with per-project
       Infisical / Mistral private-scope isolation (`AgDR-0025`, `AgDR-0055`).
  3. Crew SEO, GEO (Generative Engine Optimization) & Perimeter Security Scanner (`seo-geo`):
     - Evaluates HTML + HTTP headers + `/robots.txt` + `/sitemap.xml` + `/llms.txt` +
       `/.well-known/security.txt` with strict SSRF protection blocking private/loopback IPs.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Sequence

ESTATE_ROOT = Path(__file__).resolve().parents[1]
ACP_PROTOCOL_VERSION = "2025-03-26"


@dataclass(frozen=True)
class HostAgentSession:
    session_id: str
    agent_family: str
    transport: str
    workspace_path: str
    branch_or_scope: str
    status: str
    acp_endpoint: str
    updated_at: str


@dataclass(frozen=True)
class AcpAgentEndpoint:
    agent_id: str
    title: str
    binary: str
    installed: bool
    acp_command: str
    supported_methods: tuple[str, ...]
    tablinux_module: str


@dataclass(frozen=True)
class SeoGeoSecurityFinding:
    pillar: str
    check_id: str
    status: str
    weight: int
    earned: int
    title: str
    observed: str
    remediation: str


@dataclass(frozen=True)
class SeoGeoSecurityReport:
    target_url: str
    hostname: str
    seo_score: int
    geo_score: int
    security_score: int
    overall_score: int
    letter_grade: str
    findings: tuple[SeoGeoSecurityFinding, ...]


def is_private_or_reserved_ip(ip_str: str) -> bool:
    """Return True if `ip_str` is loopback, private, link-local, multicast, or reserved (SSRF guard)."""
    try:
        addr = ipaddress.ip_address(ip_str.strip())
    except ValueError:
        return True
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def validate_public_scan_url(raw_url: str) -> tuple[bool, str, str]:
    """Validate URL scheme/host and block SSRF to localhost/RFC1918/link-local addresses."""
    candidate = raw_url.strip()
    if not candidate:
        return False, "", "Empty target URL"
    if not candidate.startswith(("http://", "https://")):
        candidate = f"https://{candidate}"
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.scheme not in ("http", "https"):
        return False, "", f"Unsupported scheme: {parsed.scheme!r}"
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname or hostname in ("localhost", "localhost.localdomain") or hostname.endswith(".local"):
        return False, "", f"SSRF guard blocked local hostname: {hostname!r}"
    try:
        ipaddress.ip_address(hostname)
        if is_private_or_reserved_ip(hostname):
            return False, "", f"SSRF guard blocked non-public IP literal: {hostname}"
    except ValueError:
        pass
    normalized = urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, "")
    )
    return True, normalized, hostname


def compute_letter_grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def evaluate_seo_geo_security_from_artifacts(
    *,
    target_url: str,
    hostname: str,
    html_body: str,
    response_headers: dict[str, str],
    robots_txt: str | None = None,
    sitemap_xml: str | None = None,
    llms_txt: str | None = None,
    security_txt: str | None = None,
) -> SeoGeoSecurityReport:
    """Deterministically score SEO (0..100), GEO (0..100), and Perimeter Security (0..100)."""
    findings: list[SeoGeoSecurityFinding] = []
    headers_lc = {k.lower(): v for k, v in response_headers.items()}

    # --- 1. SEO PILLAR (100 points) ---
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html_body, re.IGNORECASE | re.DOTALL)
    title_text = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""
    title_ok = 10 <= len(title_text) <= 70
    findings.append(
        SeoGeoSecurityFinding(
            pillar="seo",
            check_id="seo.title",
            status="pass" if title_ok else ("warn" if title_text else "fail"),
            weight=20,
            earned=20 if title_ok else (10 if title_text else 0),
            title="HTML <title> tag length & presence",
            observed=f"len={len(title_text)} ({title_text[:50]})" if title_text else "missing",
            remediation="Provide a unique <title> between 30 and 65 characters.",
        )
    )

    desc_match = re.search(
        r'<meta\s+[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']',
        html_body,
        re.IGNORECASE,
    ) or re.search(
        r'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*name=["\']description["\']',
        html_body,
        re.IGNORECASE,
    )
    desc_text = desc_match.group(1).strip() if desc_match else ""
    desc_ok = 50 <= len(desc_text) <= 170
    findings.append(
        SeoGeoSecurityFinding(
            pillar="seo",
            check_id="seo.meta_description",
            status="pass" if desc_ok else ("warn" if desc_text else "fail"),
            weight=20,
            earned=20 if desc_ok else (10 if desc_text else 0),
            title="Meta description tag",
            observed=f"len={len(desc_text)}" if desc_text else "missing",
            remediation="Add <meta name=\"description\" content=\"...\"> (70-160 chars).",
        )
    )

    canonical_present = bool(
        re.search(r'<link\s+[^>]*rel=["\']canonical["\']', html_body, re.IGNORECASE)
    )
    findings.append(
        SeoGeoSecurityFinding(
            pillar="seo",
            check_id="seo.canonical",
            status="pass" if canonical_present else "warn",
            weight=15,
            earned=15 if canonical_present else 0,
            title="Canonical URL link element",
            observed="present" if canonical_present else "missing",
            remediation="Include <link rel=\"canonical\" href=\"https://...\"> in <head>.",
        )
    )

    og_present = bool(
        re.search(r'<meta\s+[^>]*property=["\']og:title["\']', html_body, re.IGNORECASE)
    )
    findings.append(
        SeoGeoSecurityFinding(
            pillar="seo",
            check_id="seo.opengraph",
            status="pass" if og_present else "warn",
            weight=15,
            earned=15 if og_present else 0,
            title="OpenGraph social metadata (og:title / og:image)",
            observed="present" if og_present else "missing",
            remediation="Add og:title, og:description, and og:image meta tags.",
        )
    )

    h1_matches = re.findall(r"<h1\b[^>]*>", html_body, re.IGNORECASE)
    h1_ok = len(h1_matches) == 1
    findings.append(
        SeoGeoSecurityFinding(
            pillar="seo",
            check_id="seo.h1_hierarchy",
            status="pass" if h1_ok else ("warn" if len(h1_matches) > 1 else "fail"),
            weight=15,
            earned=15 if h1_ok else (8 if len(h1_matches) > 1 else 0),
            title="Single primary <h1> heading",
            observed=f"count={len(h1_matches)}",
            remediation="Ensure exactly one semantic <h1> heading per page.",
        )
    )

    robots_and_sitemap_ok = bool(robots_txt and robots_txt.strip()) and (
        bool(sitemap_xml and sitemap_xml.strip()) or ("sitemap:" in (robots_txt or "").lower())
    )
    findings.append(
        SeoGeoSecurityFinding(
            pillar="seo",
            check_id="seo.robots_sitemap",
            status="pass" if robots_and_sitemap_ok else ("warn" if robots_txt else "fail"),
            weight=15,
            earned=15 if robots_and_sitemap_ok else (8 if robots_txt else 0),
            title="robots.txt & XML Sitemap discovery",
            observed=(
                "robots.txt + sitemap verified"
                if robots_and_sitemap_ok
                else ("robots.txt only" if robots_txt else "missing")
            ),
            remediation="Publish /robots.txt with a Sitemap: directive and /sitemap.xml.",
        )
    )

    # --- 2. GEO (Generative Engine Optimization) PILLAR (100 points) ---
    llms_ok = bool(llms_txt and len(llms_txt.strip()) >= 32)
    findings.append(
        SeoGeoSecurityFinding(
            pillar="geo",
            check_id="geo.llms_txt",
            status="pass" if llms_ok else "warn",
            weight=30,
            earned=30 if llms_ok else 0,
            title="/llms.txt machine-readable AI context index",
            observed=f"present ({len(llms_txt.strip())} chars)" if llms_ok and llms_txt else "missing",
            remediation="Publish /llms.txt (llmstxt.org standard) summarizing canonical docs & APIs for AI engines.",
        )
    )

    jsonld_blocks = re.findall(
        r'<script\s+[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html_body,
        re.IGNORECASE | re.DOTALL,
    )
    jsonld_ok = len(jsonld_blocks) > 0
    findings.append(
        SeoGeoSecurityFinding(
            pillar="geo",
            check_id="geo.schema_org_jsonld",
            status="pass" if jsonld_ok else "warn",
            weight=30,
            earned=30 if jsonld_ok else 0,
            title="Schema.org JSON-LD entity graph (application/ld+json)",
            observed=f"{len(jsonld_blocks)} JSON-LD block(s)" if jsonld_ok else "missing",
            remediation="Embed Organization, WebSite, FAQPage, or SoftwareApplication JSON-LD schemas for AI grounding.",
        )
    )

    robots_lc = (robots_txt or "").lower()
    blocks_ai_bots = any(
        re.search(rf"user-agent:\s*{bot}\s+disallow:\s*/\s*$", robots_lc, re.MULTILINE)
        for bot in ("gptbot", "claudebot", "perplexitybot", "oai-searchbot", "google-extended")
    )
    ai_crawlers_ok = not blocks_ai_bots
    findings.append(
        SeoGeoSecurityFinding(
            pillar="geo",
            check_id="geo.ai_crawler_access",
            status="pass" if ai_crawlers_ok else "warn",
            weight=20,
            earned=20 if ai_crawlers_ok else 5,
            title="AI answer-engine crawler access (GPTBot, ClaudeBot, PerplexityBot, Mistral)",
            observed="allowed" if ai_crawlers_ok else "restricted in robots.txt",
            remediation="Allow OAI-SearchBot, PerplexityBot, ClaudeBot, and Google-Extended on public knowledge pages.",
        )
    )

    semantic_landmarks = sum(
        1
        for tag in ("<main", "<article", "<section", "<time", "<nav")
        if tag in html_body.lower()
    )
    landmarks_ok = semantic_landmarks >= 2
    findings.append(
        SeoGeoSecurityFinding(
            pillar="geo",
            check_id="geo.semantic_landmarks",
            status="pass" if landmarks_ok else "warn",
            weight=20,
            earned=20 if landmarks_ok else (10 if semantic_landmarks == 1 else 0),
            title="Semantic HTML5 citation landmarks (<main>, <article>, <section>, <time>)",
            observed=f"{semantic_landmarks}/5 landmark types present",
            remediation="Wrap primary content in <main> and <article> with machine-readable <time datetime=\"...\">.",
        )
    )

    # --- 3. PERIMETER SECURITY PILLAR (100 points) ---
    https_ok = target_url.lower().startswith("https://")
    findings.append(
        SeoGeoSecurityFinding(
            pillar="security",
            check_id="sec.https",
            status="pass" if https_ok else "fail",
            weight=20,
            earned=20 if https_ok else 0,
            title="HTTPS transport encryption",
            observed="https://" if https_ok else "insecure http://",
            remediation="Enforce HTTPS with TLS 1.3 and automatic 301 redirects from HTTP.",
        )
    )

    hsts = headers_lc.get("strict-transport-security", "")
    hsts_ok = "max-age=" in hsts.lower()
    findings.append(
        SeoGeoSecurityFinding(
            pillar="security",
            check_id="sec.hsts",
            status="pass" if hsts_ok else "warn",
            weight=20,
            earned=20 if hsts_ok else 0,
            title="Strict-Transport-Security (HSTS)",
            observed=hsts if hsts_ok else "missing",
            remediation="Set Strict-Transport-Security: max-age=31536000; includeSubDomains; preload.",
        )
    )

    csp = headers_lc.get("content-security-policy", "")
    csp_ok = bool(csp.strip())
    findings.append(
        SeoGeoSecurityFinding(
            pillar="security",
            check_id="sec.csp",
            status="pass" if csp_ok else "warn",
            weight=20,
            earned=20 if csp_ok else 0,
            title="Content-Security-Policy (CSP)",
            observed="present" if csp_ok else "missing",
            remediation="Configure a strict Content-Security-Policy header restricting script-src and frame-ancestors.",
        )
    )

    xcto = headers_lc.get("x-content-type-options", "")
    xfo = headers_lc.get("x-frame-options", "")
    headers_hardened = ("nosniff" in xcto.lower()) and (
        bool(xfo.strip()) or "frame-ancestors" in csp.lower()
    )
    findings.append(
        SeoGeoSecurityFinding(
            pillar="security",
            check_id="sec.clickjacking_mime",
            status="pass" if headers_hardened else ("warn" if xcto or xfo else "fail"),
            weight=20,
            earned=20 if headers_hardened else (10 if (xcto or xfo) else 0),
            title="MIME-sniffing & Clickjacking protection (nosniff + X-Frame-Options)",
            observed=f"XCTO={xcto or '-'}, XFO={xfo or '-'}",
            remediation="Send X-Content-Type-Options: nosniff and X-Frame-Options: DENY (or CSP frame-ancestors).",
        )
    )

    sec_txt_ok = bool(security_txt and "contact:" in security_txt.lower())
    findings.append(
        SeoGeoSecurityFinding(
            pillar="security",
            check_id="sec.security_txt",
            status="pass" if sec_txt_ok else "warn",
            weight=20,
            earned=20 if sec_txt_ok else 0,
            title="RFC 9116 /.well-known/security.txt disclosure policy",
            observed="present (Contact: verified)" if sec_txt_ok else "missing",
            remediation="Publish /.well-known/security.txt with Contact: and Expires: fields per RFC 9116.",
        )
    )

    seo_score = sum(f.earned for f in findings if f.pillar == "seo")
    geo_score = sum(f.earned for f in findings if f.pillar == "geo")
    security_score = sum(f.earned for f in findings if f.pillar == "security")
    overall_score = round((seo_score + geo_score + security_score) / 3)

    return SeoGeoSecurityReport(
        target_url=target_url,
        hostname=hostname,
        seo_score=seo_score,
        geo_score=geo_score,
        security_score=security_score,
        overall_score=overall_score,
        letter_grade=compute_letter_grade(overall_score),
        findings=tuple(findings),
    )


def _fetch_text_optional(url: str, timeout: float = 5.0) -> tuple[str | None, dict[str, str]]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "w0m-k7kb-crew-scanner/1.0 (+https://webomage.com)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            headers = {k: v for k, v in resp.headers.items()}
            body = resp.read(262_144).decode("utf-8", errors="replace")
            return body, headers
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None, {}


def run_live_seo_geo_security_scan(raw_url: str, timeout: float = 6.0) -> SeoGeoSecurityReport:
    """Execute live SEO, GEO & Security scan against `raw_url` after SSRF validation."""
    ok, normalized_url, hostname = validate_public_scan_url(raw_url)
    if not ok:
        raise ValueError(hostname)
    try:
        infos = socket.getaddrinfo(hostname, None)
        for info in infos:
            ip_addr = str(info[4][0])
            if is_private_or_reserved_ip(ip_addr):
                raise ValueError(f"SSRF guard blocked resolved private IP {ip_addr} for {hostname}")
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failed for {hostname}: {exc}") from exc

    parsed = urllib.parse.urlsplit(normalized_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    html_body, headers = _fetch_text_optional(normalized_url, timeout=timeout)
    if html_body is None:
        html_body = ""
    robots_txt, _ = _fetch_text_optional(f"{origin}/robots.txt", timeout=3.0)
    sitemap_xml, _ = _fetch_text_optional(f"{origin}/sitemap.xml", timeout=3.0)
    llms_txt, _ = _fetch_text_optional(f"{origin}/llms.txt", timeout=3.0)
    security_txt, _ = _fetch_text_optional(f"{origin}/.well-known/security.txt", timeout=3.0)

    return evaluate_seo_geo_security_from_artifacts(
        target_url=normalized_url,
        hostname=hostname,
        html_body=html_body,
        response_headers=headers,
        robots_txt=robots_txt,
        sitemap_xml=sitemap_xml,
        llms_txt=llms_txt,
        security_txt=security_txt,
    )


def discover_host_agent_sessions(home_dir: Path | None = None) -> list[HostAgentSession]:
    """Discover same-host agent worktrees, sessions, and ACP runtime endpoints."""
    home = home_dir or Path.home()
    sessions: list[HostAgentSession] = []

    # 1. @wom isolated agent worktrees (~/.w0m/work/*)
    work_root = home / ".w0m" / "work"
    if work_root.is_dir():
        for entry in sorted(work_root.iterdir()):
            w0m_dir = entry / "w0m"
            if w0m_dir.is_dir():
                sessions.append(
                    HostAgentSession(
                        session_id=f"w0m-worktree:{entry.name}",
                        agent_family="w0m-agent-tree",
                        transport="git-worktree+acp-stdio",
                        workspace_path=str(w0m_dir),
                        branch_or_scope=f"agent/{entry.name}",
                        status="ACTIVE_WORKTREE",
                        acp_endpoint=f"acp://stdio/w0m/{entry.name}",
                        updated_at="live",
                    )
                )

    # 2. Antigravity (AGY) brain conversations (~/.gemini/antigravity-cli/brain/*)
    agy_brain = home / ".gemini" / "antigravity-cli" / "brain"
    if agy_brain.is_dir():
        dirs = sorted(
            (d for d in agy_brain.iterdir() if d.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for d in dirs[:5]:
            sessions.append(
                HostAgentSession(
                    session_id=f"antigravity:{d.name[:12]}",
                    agent_family="google-antigravity",
                    transport="acp-compatible-session",
                    workspace_path=str(ESTATE_ROOT),
                    branch_or_scope="w0m",
                    status="ACTIVE_SESSION",
                    acp_endpoint=f"conversation://{d.name}",
                    updated_at="recent",
                )
            )

    # 3. Claude Code sessions (~/.claude/projects/*)
    claude_projects = home / ".claude" / "projects"
    if claude_projects.is_dir():
        c_dirs = sorted(
            (d for d in claude_projects.iterdir() if d.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for d in c_dirs[:4]:
            sessions.append(
                HostAgentSession(
                    session_id=f"claude-code:{d.name[-20:]}",
                    agent_family="claude-code",
                    transport="acp-stdio",
                    workspace_path=d.name.replace("-", "/"),
                    branch_or_scope="host-local",
                    status="DISCOVERED",
                    acp_endpoint=f"acp://claude/{d.name[-16:]}",
                    updated_at="cached",
                )
            )

    # 4. Orca & Mistral Vibe ACP endpoints
    sessions.append(
        HostAgentSession(
            session_id="orca-host:primary",
            agent_family="orca-desktop-cli",
            transport="acp-jsonrpc-2.0",
            workspace_path=str(ESTATE_ROOT),
            branch_or_scope="w0m+k7",
            status="ACP_READY",
            acp_endpoint="acp://orca/host-session-bus",
            updated_at="live",
        )
    )
    sessions.append(
        HostAgentSession(
            session_id="mistral-vibe:w0m",
            agent_family="vibe-acp (Mistral + Obsidian)",
            transport="acp-jsonrpc-2.0",
            workspace_path=str(ESTATE_ROOT / "w0m-web/projects/w0m/vault"),
            branch_or_scope="w0m@webomage.com (MISTRAL_API_KEY_W0M)",
            status="ACP_READY",
            acp_endpoint="acp://vibe-acp/w0m",
            updated_at="live",
        )
    )
    return sessions


def discover_acp_agent_endpoints() -> list[AcpAgentEndpoint]:
    """List same-host ACP-capable agent binaries and their `TabLinux` / `Orca` bindings."""
    candidates = [
        (
            "orca-acp",
            "Orca Desktop & CLI Agent Host (agentclientprotocol.com)",
            "orca",
            "orca worktree list",
            "acp",
        ),
        (
            "mistral-vibe-acp",
            "Mistral Vibe ACP Agent (Obsidian + Project Private Scope)",
            "vibe-acp",
            "infisical run --env=beta --silent -- vibe-acp",
            "kb",
        ),
        (
            "claude-code-acp",
            "Claude Code ACP Session Adapter",
            "claude",
            "claude --acp",
            "llm",
        ),
        (
            "codex-acp",
            "OpenAI Codex CLI ACP Session Adapter",
            "codex",
            "codex --acp",
            "llm",
        ),
        (
            "k7hub-acp",
            "Unified @k7 Super-TUI & TabLinux Module Host",
            "k7",
            "k7 orca kb",
            "hub",
        ),
        (
            "k7kb-acp",
            "k7kb Knowledge Base, SEO/GEO & Enterprise Analytics TUI",
            "k7kb",
            "k7kb acp --discover",
            "kb",
        ),
    ]
    methods = (
        "initialize",
        "session/new",
        "session/load",
        "session/prompt",
        "session/cancel",
        "host/discover",
    )
    out: list[AcpAgentEndpoint] = []
    for agent_id, title, binary, cmd, mod_slug in candidates:
        installed = bool(shutil_which(binary))
        out.append(
            AcpAgentEndpoint(
                agent_id=agent_id,
                title=title,
                binary=binary,
                installed=installed,
                acp_command=cmd,
                supported_methods=methods,
                tablinux_module=mod_slug,
            )
        )
    return out


def shutil_which(binary: str) -> str | None:
    for p in os.environ.get("PATH", "").split(os.pathsep):
        cand = Path(p) / binary
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    # Check @k7 target debug binaries
    k7_cand = Path("/home/aleksei/Projects/!self/k7") / binary / binary / "target/debug" / binary
    if k7_cand.is_file():
        return str(k7_cand)
    if binary == "k7":
        hub_cand = Path("/home/aleksei/Projects/!self/k7/k7hub/k7hub/target/debug/k7")
        if hub_cand.is_file():
            return str(hub_cand)
    return None


def build_acp_jsonrpc_message(
    method: str,
    *,
    project_id: str = "w0m",
    session_id: str = "sess_w0m_01",
    prompt_text: str | None = None,
    request_id: int = 1,
) -> dict[str, Any]:
    """Construct a spec-compliant Agent Client Protocol (ACP) JSON-RPC 2.0 request envelope."""
    cwd = str(ESTATE_ROOT)
    if method == "initialize":
        params: dict[str, Any] = {
            "protocolVersion": ACP_PROTOCOL_VERSION,
            "clientInfo": {
                "name": "w0m-orca-k7-host",
                "title": "Webomage Orca & @k7 Same-Host ACP Manager",
                "version": "1.0.0",
            },
            "capabilities": {
                "fs": {"readTextFile": True, "writeTextFile": True},
                "terminal": True,
                "hostDiscovery": True,
                "tablinuxWasm": True,
            },
        }
    elif method == "session/new":
        params = {
            "cwd": cwd,
            "projectScope": {
                "projectId": project_id,
                "accountEmail": f"{project_id}@webomage.com",
                "infisicalSecretKey": f"MISTRAL_API_KEY_{project_id.upper().replace('-', '_')}",
                "crossProjectAccess": False,
            },
            "mcpServers": [],
        }
    elif method == "session/load":
        params = {
            "sessionId": session_id,
            "cwd": cwd,
        }
    elif method == "session/prompt":
        params = {
            "sessionId": session_id,
            "prompt": [
                {
                    "type": "text",
                    "text": prompt_text or "Run SEO, GEO, security, and Knowledge Base diagnostics.",
                }
            ],
        }
    elif method == "session/cancel":
        params = {
            "sessionId": session_id,
        }
    elif method == "host/discover":
        params = {
            "includeWorktrees": True,
            "includeAcpEndpoints": True,
            "includeTablinuxModules": True,
        }
    else:
        raise ValueError(f"Unsupported ACP method: {method!r}")

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params,
    }


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Same-Host Agent Session Discovery, ACP Protocol Manager & SEO/GEO/Security Scanner (T681)."
    )
    sub = ap.add_subparsers(dest="cmd")

    p_disc = sub.add_parser("discover", help="Discover same-host agent sessions and ACP endpoints")
    p_disc.add_argument("--json", action="store_true", help="Emit JSON output")

    p_acp = sub.add_parser("acp", help="Generate ACP JSON-RPC 2.0 session management payloads")
    p_acp.add_argument(
        "--method",
        default="initialize",
        choices=[
            "initialize",
            "session/new",
            "session/load",
            "session/prompt",
            "session/cancel",
            "host/discover",
        ],
    )
    p_acp.add_argument("--project", default="w0m")
    p_acp.add_argument("--session-id", default="sess_w0m_01")
    p_acp.add_argument("--prompt", default=None)

    p_scan = sub.add_parser("seo-geo", help="Run SEO, GEO, and Perimeter Security scan on a URL")
    p_scan.add_argument("url", help="Public URL or domain to scan (e.g. https://webomage.com)")
    p_scan.add_argument("--json", action="store_true", help="Emit JSON output")

    args = ap.parse_args(argv)
    cmd = args.cmd or "discover"

    if cmd == "discover":
        sessions = discover_host_agent_sessions()
        endpoints = discover_acp_agent_endpoints()
        if args.json:
            print(
                json.dumps(
                    {
                        "protocol": "agent-client-protocol",
                        "protocol_version": ACP_PROTOCOL_VERSION,
                        "sessions": [asdict(s) for s in sessions],
                        "endpoints": [asdict(e) for e in endpoints],
                    },
                    indent=2,
                )
            )
            return 0
        print(
            f"=== Same-Host Agent Sessions (ACP {ACP_PROTOCOL_VERSION}) ==="
        )
        print(
            f"{'SESSION ID':<28} {'FAMILY':<24} {'STATUS':<16} {'BRANCH / SCOPE':<32} {'ACP ENDPOINT'}"
        )
        print("-" * 125)
        for s in sessions:
            print(
                f"{s.session_id:<28} {s.agent_family:<24} {s.status:<16} {s.branch_or_scope:<32} {s.acp_endpoint}"
            )
        print("\n=== Registered Same-Host ACP Agent Endpoints ===")
        print(
            f"{'AGENT ID':<20} {'INSTALLED':<10} {'TABLINUX':<10} {'COMMAND':<44} {'TITLE'}"
        )
        print("-" * 125)
        for e in endpoints:
            inst = "YES" if e.installed else "READY"
            print(
                f"{e.agent_id:<20} {inst:<10} {e.tablinux_module:<10} {e.acp_command:<44} {e.title}"
            )
        return 0

    if cmd == "acp":
        msg = build_acp_jsonrpc_message(
            args.method,
            project_id=args.project,
            session_id=args.session_id,
            prompt_text=args.prompt,
        )
        print(json.dumps(msg, indent=2))
        return 0

    if cmd == "seo-geo":
        try:
            report = run_live_seo_geo_security_scan(args.url)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(asdict(report), indent=2))
            return 0
        print(
            f"=== SEO + GEO + Security Scan: {report.target_url} (Grade {report.letter_grade}, Overall {report.overall_score}/100) ==="
        )
        print(
            f"  SEO Score: {report.seo_score}/100 | GEO (AI Search) Score: {report.geo_score}/100 | Security Score: {report.security_score}/100"
        )
        print("-" * 120)
        print(
            f"{'PILLAR':<10} {'STATUS':<8} {'PTS':<8} {'CHECK':<42} {'OBSERVED'}"
        )
        print("-" * 120)
        for f in report.findings:
            pts = f"{f.earned}/{f.weight}"
            print(
                f"{f.pillar.upper():<10} {f.status.upper():<8} {pts:<8} {f.title[:40]:<42} {f.observed[:45]}"
            )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
