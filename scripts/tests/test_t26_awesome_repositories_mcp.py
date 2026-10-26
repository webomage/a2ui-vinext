#!/usr/bin/env python3
"""Tests for T26 — Package discovery via awesome-repositories MCP."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ESTATE_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = ESTATE_ROOT / "wom7web"
sys.path.insert(0, str(ESTATE_ROOT / "scripts"))

import mcp_declared  # noqa: E402


def test_ac1_awesome_repositories_mcp_declared_and_configured() -> None:
    """AC1: awesome-repositories is declared in .w0m/sdlc.json and .mcp.json with HTTP transport, OAuth 2.1, read-only, and 5 tools."""
    sdlc = json.loads((ESTATE_ROOT / ".w0m" / "sdlc.json").read_text(encoding="utf-8"))
    srv = sdlc["mcp"]["servers"].get("awesome-repositories")
    assert srv is not None, "awesome-repositories missing from .w0m/sdlc.json -> mcp.servers"
    assert srv["enabled"] is True
    assert srv["transport"] == "remote"
    assert srv["url"] == "https://awesome-repositories.com/api/mcp"
    assert srv["auth"] == "oauth-2.1-auto-discovery"
    assert srv["oauth_discovery"] == "/.well-known/oauth-protected-resource"
    assert srv["read_only"] is True
    expected_tools = {
        "search_repositories",
        "search_metadata_tags",
        "get_repository",
        "list_curated_searches",
        "list_repository_docs",
    }
    assert set(srv["tools"]) == expected_tools

    # Validate mcp_declared schema check accepts the live .w0m/sdlc.json
    declared_map = mcp_declared.load_declared(ESTATE_ROOT / ".w0m" / "sdlc.json")
    assert "awesome-repositories" in declared_map

    # Validate .mcp.json HTTP configuration
    mcp_json = json.loads((ESTATE_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    host_srv = mcp_json["mcpServers"].get("awesome-repositories")
    assert host_srv is not None, "awesome-repositories missing from @wom/.mcp.json"
    assert host_srv["type"] == "http"
    assert host_srv["url"] == "https://awesome-repositories.com/api/mcp"


def test_ac2_when_to_use_documented_in_sdlc_and_docs() -> None:
    """AC2: When-to-use is documented in docs/PACKAGE-DISCOVERY-MCP.md and wired in w0m-sdlc-research."""
    doc_path = WEB_ROOT / "docs" / "PACKAGE-DISCOVERY-MCP.md"
    assert doc_path.is_file(), f"Missing {doc_path}"
    doc_text = doc_path.read_text(encoding="utf-8")
    for required in (
        "https://awesome-repositories.com/api/mcp",
        "/.well-known/oauth-protected-resource",
        "search_repositories",
        "search_metadata_tags",
        "get_repository",
        "list_curated_searches",
        "list_repository_docs",
        "w0m-sdlc-research",
        "w0m-sdlc-spec",
        "mcp.boundary",
    ):
        assert required in doc_text, f"Missing {required!r} in PACKAGE-DISCOVERY-MCP.md"

    for skill_path in (
        ESTATE_ROOT / "wom7skills" / "skills" / "w0m-sdlc-research" / "SKILL.md",
        WEB_ROOT / ".agents" / "skills" / "w0m-sdlc-research" / "SKILL.md",
        ESTATE_ROOT / ".agents" / "skills" / "w0m-sdlc-research" / "SKILL.md",
    ):
        text = skill_path.read_text(encoding="utf-8")
        assert "awesome-repositories" in text, f"Missing awesome-repositories in {skill_path}"
        assert "PACKAGE-DISCOVERY-MCP.md" in text, f"Missing PACKAGE-DISCOVERY-MCP.md in {skill_path}"
