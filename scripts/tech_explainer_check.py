#!/usr/bin/env python3
"""Governance, Self-Containment, A11y & Consistency Gate for the Interactive Visual Explainer (T736)."""

from __future__ import annotations

import argparse
import html.parser
import json
from pathlib import Path
import re
import subprocess
import sys

ESTATE_ROOT = Path(__file__).resolve().parents[1]
PRIMARY_REL = Path("docs/visuals/w0m-tech-landscape-explainer.html")
DEPRECATED_REL = Path("w0m-web/docs/walkthroughs/w0m-tech-landscape-explainer.html")

EXTERNAL_NET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("external tag src/href", re.compile(r"<(?:script|link|img|iframe)\b[^>]+(?:src|href)\s*=\s*['\"]?(?:https?:)?//", re.I)),
    ("external SVG <image> href", re.compile(r"<image\b[^>]+(?:href|xlink:href)\s*=\s*['\"]?(?:https?:)?//", re.I)),
    ("external CSS @import", re.compile(r"@import\s+(?:url\(\s*)?['\"]?(?:https?:)?//", re.I)),
    ("external CSS url()", re.compile(r"url\(\s*['\"]?(?:https?:)?//", re.I)),
    ("external srcset", re.compile(r"\bsrcset\s*=\s*['\"][^'\"]*(?:https?:)?//", re.I)),
    ("runtime fetch/dynamic import", re.compile(r"\b(?:fetch|import)\(\s*['\"](?:https?:)?//", re.I)),
)

TICKET_OR_AGDR_LEAK_RE = re.compile(r"\b(?:T\d{2,4}|AgDR-\d{4}|ADR-\d{4}|AC\d+)\b")
HOST_PATH_LEAK_RE = re.compile(r"(?:/home/|/Users/)[A-Za-z0-9_.\-]+")
GET_BY_ID_RE = re.compile(r"""getElementById\(\s*['"]([A-Za-z0-9_\-:]+)['"]\s*\)""")
HTML_ID_RE = re.compile(r"""\bid\s*=\s*['"]([A-Za-z0-9_\-:]+)['"]""")
DATA_NODE_RE = re.compile(r"""<g\b[^>]*class\s*=\s*['"][^'"]*\bnode\b[^'"]*['"][^>]*>""")
DATA_EDGE_RE = re.compile(r"""<(?:line|path)\b[^>]*class\s*=\s*['"][^'"]*\bedge\b[^'"]*['"][^>]*>""")
ATTR_DATA_NODE_RE = re.compile(r"""\bdata-node\s*=\s*['"]([^'"]+)['"]""")
ATTR_DATA_FROM_RE = re.compile(r"""\bdata-from\s*=\s*['"]([^'"]+)['"]""")
ATTR_DATA_TO_RE = re.compile(r"""\bdata-to\s*=\s*['"]([^'"]+)['"]""")


class _TextExtractor(html.parser.HTMLParser):
    """Extract visible text outside `<style>` tags for user-facing leak scanning."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "style":
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "style" and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.chunks.append(data)


def validate_explainer_html(root: Path = ESTATE_ROOT) -> list[str]:
    """Validate single-SSOT placement, zero external dependencies, a11y, and graph parity."""
    errors: list[str] = []
    primary = root / PRIMARY_REL
    deprecated = root / DEPRECATED_REL

    if not primary.is_file():
        return [f"Missing canonical explainer HTML: {primary}"]
    if deprecated.exists():
        errors.append(
            f"Deprecated duplicate explainer exists at {deprecated}; single SSOT is {primary} (ANTI-PATTERNS §2.2)."
        )

    html_text = primary.read_text(encoding="utf-8")

    # 1. Zero external CDN/network references (fixing `justfile` raw-string regex bug)
    for label, pat in EXTERNAL_NET_PATTERNS:
        if pat.search(html_text):
            errors.append(f"Forbidden external network reference ({label}) in {primary.name}")

    # 2. Core interactive controls & reduced-motion support
    for audience in ("novice", "junior", "product", "executive"):
        if f'data-audience="{audience}"' not in html_text:
            errors.append(f"Missing required audience button data-audience={audience!r}")
    if 'id="theme-toggle"' not in html_text:
        errors.append("Missing required #theme-toggle button")
    if "prefers-reduced-motion: reduce" not in html_text:
        errors.append("Missing prefers-reduced-motion: reduce media query")

    # 3. SVG container & interactive node accessibility
    svg_match = re.search(r"<svg\b[^>]*class\s*=\s*['\"][^'\"]*\btopo\b[^'\"]*['\"][^>]*>", html_text, re.I)
    if not svg_match:
        errors.append("Missing <svg class=\"topo\"> topology diagram")
    else:
        svg_tag = svg_match.group(0)
        if re.search(r"\brole\s*=\s*['\"]img['\"]", svg_tag, re.I):
            errors.append('<svg class="topo"> must NOT have role="img" (hides interactive focusable child buttons)')

    node_tags = DATA_NODE_RE.findall(html_text)
    if not node_tags:
        errors.append("No SVG <g class=\"node\"> elements found")
    svg_nodes: set[str] = set()
    for tag in node_tags:
        m_id = ATTR_DATA_NODE_RE.search(tag)
        if not m_id:
            errors.append(f"SVG node missing data-node attribute: {tag}")
            continue
        nid = m_id.group(1)
        svg_nodes.add(nid)
        if 'role="button"' not in tag or 'tabindex="0"' not in tag or "aria-label=" not in tag:
            errors.append(f"Interactive SVG node {nid!r} must declare role=\"button\", tabindex=\"0\", and aria-label")

    svg_edges: set[tuple[str, str]] = set()
    for etag in DATA_EDGE_RE.findall(html_text):
        m_from = ATTR_DATA_FROM_RE.search(etag)
        m_to = ATTR_DATA_TO_RE.search(etag)
        if m_from and m_to:
            pair = (m_from.group(1), m_to.group(1))
            svg_edges.add(pair)
            if pair[0] not in svg_nodes or pair[1] not in svg_nodes:
                errors.append(f"SVG edge {pair!r} references missing SVG node")

    # 4. DOM ID integrity across getElementById(...) calls
    html_ids = set(HTML_ID_RE.findall(html_text))
    for ref_id in sorted(set(GET_BY_ID_RE.findall(html_text))):
        if ref_id not in html_ids:
            errors.append(f"JS getElementById({ref_id!r}) references missing DOM id")

    # 5. Structured JSON dataset validation (NODES, FLOWS, CATALOG, LADDERS parity)
    data_match = re.search(
        r"""<script\b[^>]*id\s*=\s*['"]explainer-data['"][^>]*>(.*?)</script>""",
        html_text,
        re.DOTALL | re.I,
    )
    if not data_match:
        errors.append('Missing <script type="application/json" id="explainer-data"> structured dataset block')
    else:
        try:
            payload = json.loads(data_match.group(1))
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid JSON inside #explainer-data: {exc}")
            payload = {}

        nodes_dict = payload.get("NODES", {})
        if set(nodes_dict.keys()) != svg_nodes:
            missing_in_js = sorted(svg_nodes - set(nodes_dict.keys()))
            missing_in_svg = sorted(set(nodes_dict.keys()) - svg_nodes)
            if missing_in_js:
                errors.append(f"SVG nodes missing from NODES JSON: {missing_in_js}")
            if missing_in_svg:
                errors.append(f"NODES JSON entries missing from SVG: {missing_in_svg}")

        for flow in payload.get("FLOWS", []):
            fid = flow.get("id", "<unknown>")
            for idx, step in enumerate(flow.get("steps", []), 1):
                for nid in step.get("nodes", []):
                    if nid not in svg_nodes:
                        errors.append(f"Flow {fid!r} step {idx} references unknown SVG node {nid!r}")
                for eid in step.get("edges", []):
                    edge_pair = (
                        (str(eid[0]), str(eid[1]))
                        if isinstance(eid, list) and len(eid) == 2
                        else None
                    )
                    if edge_pair is None or edge_pair not in svg_edges:
                        errors.append(f"Flow {fid!r} step {idx} references unknown SVG edge {eid!r}")

    # 6. Zero internal ticket / AgDR / AC identifiers and personal host paths in rendered text/data
    parser = _TextExtractor()
    parser.feed(html_text)
    visible_and_data = "\n".join(parser.chunks)
    if m_ticket := TICKET_OR_AGDR_LEAK_RE.search(visible_and_data):
        errors.append(f"Internal SDLC/AgDR identifier leak in user-facing explainer: {m_ticket.group(0)!r} (T667)")
    if m_host := HOST_PATH_LEAK_RE.search(visible_and_data):
        errors.append(f"Personal workstation path leak in explainer: {m_host.group(0)!r}")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ESTATE_ROOT)
    parser.add_argument("--mode", choices=("check", "path", "open"), default="check")
    args = parser.parse_args(argv)

    primary = args.root / PRIMARY_REL
    if args.mode == "path":
        if not primary.is_file():
            print(f"Missing canonical explainer HTML: {primary}", file=sys.stderr)
            return 1
        print(primary)
        return 0

    errors = validate_explainer_html(args.root)
    if errors:
        for err in errors:
            print(f"[FAIL] {err}", file=sys.stderr)
        return 1

    if args.mode == "check":
        print(f"[OK] {PRIMARY_REL} validated (single-SSOT, zero-CDN, a11y, DOM/SVG parity, T667 clean)")
        return 0

    opener = "xdg-open" if sys.platform.startswith("linux") else "open"
    subprocess.run([opener, str(primary)], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
