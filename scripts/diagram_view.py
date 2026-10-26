#!/usr/bin/env python3
"""diagram_view.py — Zero-width-limit browser viewer for ticket Mermaid architecture diagrams (T211 AC4).

Solves the terminal/TUI horizontal column truncation problem by compiling ticket .mmd diagrams
into an interactive standalone HTML page with SVG pan/zoom and dark mode, opening in the default browser.

Usage:
    just diagram T211
    just diagram .tasks/T211-arch.mmd
    python3 scripts/diagram_view.py T211 --no-open
    python3 scripts/diagram_view.py .tasks/T211.mmd --output /tmp/custom.html
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def find_workspace_root(start_path: Path | None = None) -> Path:
    """Find the workspace root containing .tasks and .w0m/sdlc.json."""
    cur = (start_path or Path(__file__)).resolve()
    for parent in [cur] + list(cur.parents):
        if (parent / ".tasks").is_dir() and (parent / ".w0m").is_dir():
            return parent
        if (parent / ".git").exists() and (parent / "w0m-web").is_dir():
            return parent
    return Path(__file__).resolve().parents[1]


ROOT = find_workspace_root()
TICKETS_DIR = ROOT / ".tasks"
DEFAULT_OUT = Path("/tmp/w0m-diagram-preview.html")


def normalize_id(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.upper().startswith("T") and cleaned[1:].isdigit():
        return cleaned.upper()
    if cleaned.isdigit():
        return f"T{cleaned}"
    m = re.match(r"^[tT](\d+)", cleaned)
    if m:
        return f"T{m.group(1)}"
    return cleaned


def clean_diagram_content(raw: str) -> str:
    content = raw.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:mermaid)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        content = content.strip()
    return content


def discover_ticket_diagrams(ticket_id: str) -> list[tuple[str, str, Path]]:
    """Discover all sibling .mmd files for a ticket."""
    if not TICKETS_DIR.is_dir():
        return []
    pat = re.compile(rf"^{re.escape(ticket_id)}(?:[-_](.+))?\.mmd$")
    diagrams: list[tuple[str, str, Path]] = []

    def sort_key(p: Path) -> tuple[int, str]:
        if p.name == f"{ticket_id}.mmd":
            return (0, "")
        return (1, p.name)

    for f in sorted(TICKETS_DIR.glob(f"{ticket_id}*.mmd"), key=sort_key):
        m = pat.match(f.name)
        if not m:
            continue
        suffix = m.group(1)
        if suffix:
            title = suffix.replace("-", " ").replace("_", " ").strip().title()
        else:
            title = "Architecture Diagram"
        try:
            content = clean_diagram_content(f.read_text(encoding="utf-8"))
            if content:
                diagrams.append((title, content, f))
        except OSError:
            continue
    return diagrams


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{page_title}</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
  <style>
    :root {{
      --bg: #020617;        /* slate-950 */
      --surface: #0f172a;   /* slate-900 */
      --border: #1e293b;    /* slate-800 */
      --text: #f8fafc;      /* slate-50 */
      --muted: #94a3b8;     /* slate-400 */
      --brand: #38bdf8;     /* sky-400 */
      --brand-hover: #0284c7;
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    body {{
      background-color: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      overflow: hidden;
      height: 100vh;
      display: flex;
      flex-direction: column;
    }}
    header {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 12px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      z-index: 10;
      user-select: none;
    }}
    .title-group {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .badge {{
      background: #1e293b;
      color: var(--brand);
      padding: 4px 10px;
      border-radius: 6px;
      font-weight: 700;
      font-size: 13px;
      letter-spacing: 0.5px;
      border: 1px solid rgba(56, 189, 248, 0.2);
    }}
    h1 {{
      font-size: 16px;
      font-weight: 600;
      color: var(--text);
    }}
    .tabs {{
      display: flex;
      gap: 8px;
    }}
    .tab-btn {{
      background: transparent;
      border: 1px solid var(--border);
      color: var(--muted);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 13px;
      cursor: pointer;
      transition: all 0.15s ease;
    }}
    .tab-btn:hover {{
      color: var(--text);
      border-color: var(--muted);
    }}
    .tab-btn.active {{
      background: var(--border);
      color: var(--brand);
      border-color: var(--brand);
      font-weight: 600;
    }}
    .controls {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .btn {{
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 13px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      transition: background 0.15s;
    }}
    .btn:hover {{
      background: var(--border);
      border-color: var(--brand);
    }}
    .hint {{
      font-size: 12px;
      color: var(--muted);
      margin-right: 12px;
    }}
    #viewport {{
      flex: 1;
      position: relative;
      overflow: hidden;
      cursor: grab;
      background-image: radial-gradient(rgba(30, 41, 59, 0.4) 1px, transparent 1px);
      background-size: 24px 24px;
    }}
    #viewport:active {{
      cursor: grabbing;
    }}
    #canvas-container {{
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      transform-origin: 0 0;
      display: flex;
      align-items: center;
      justify-content: center;
      pointer-events: none;
    }}
    .diagram-panel {{
      display: none;
      pointer-events: auto;
      min-width: 100px;
      min-height: 100px;
    }}
    .diagram-panel.active {{
      display: block;
    }}
    .diagram-panel svg {{
      max-width: none !important;
      height: auto !important;
    }}
  </style>
</head>
<body>
  <header>
    <div class="title-group">
      <span class="badge">{header_badge}</span>
      <h1>{header_title}</h1>
      {tabs_html}
    </div>
    <div class="controls">
      <span class="hint">Drag to Pan • Wheel to Zoom • Key 0 to Reset</span>
      <button class="btn" onclick="zoomIn()" title="Zoom In (+)">+</button>
      <button class="btn" onclick="zoomOut()" title="Zoom Out (-)">-</button>
      <button class="btn" onclick="resetZoom()" title="Reset Zoom (0)">Reset</button>
    </div>
  </header>

  <main id="viewport">
    <div id="canvas-container">
      {diagram_panels_html}
    </div>
  </main>

  <script>
    mermaid.initialize({{
      startOnLoad: true,
      theme: 'dark',
      themeVariables: {{
        darkMode: true,
        background: '#020617',
        primaryColor: '#1e293b',
        primaryBorderColor: '#38bdf8',
        primaryTextColor: '#f8fafc',
        lineColor: '#38bdf8',
        secondaryColor: '#0f172a',
        tertiaryColor: '#1e293b'
      }}
    }});

    let scale = 1.0;
    let panX = 0;
    let panY = 0;
    let isDragging = false;
    let startX = 0;
    let startY = 0;

    const viewport = document.getElementById('viewport');
    const container = document.getElementById('canvas-container');

    function updateTransform() {{
      container.style.transform = `translate(${{panX}}px, ${{panY}}px) scale(${{scale}})`;
    }}

    function zoomIn() {{
      scale = Math.min(scale * 1.25, 8.0);
      updateTransform();
    }}

    function zoomOut() {{
      scale = Math.max(scale * 0.8, 0.15);
      updateTransform();
    }}

    function resetZoom() {{
      scale = 1.0;
      panX = 0;
      panY = 0;
      updateTransform();
    }}

    function switchTab(index) {{
      document.querySelectorAll('.tab-btn').forEach((btn, idx) => {{
        btn.classList.toggle('active', idx === index);
      }});
      document.querySelectorAll('.diagram-panel').forEach((panel, idx) => {{
        panel.classList.toggle('active', idx === index);
      }});
      resetZoom();
    }}

    viewport.addEventListener('mousedown', (e) => {{
      if (e.button !== 0) return;
      isDragging = true;
      startX = e.clientX - panX;
      startY = e.clientY - panY;
    }});

    window.addEventListener('mousemove', (e) => {{
      if (!isDragging) return;
      panX = e.clientX - startX;
      panY = e.clientY - startY;
      updateTransform();
    }});

    window.addEventListener('mouseup', () => {{
      isDragging = false;
    }});

    viewport.addEventListener('wheel', (e) => {{
      e.preventDefault();
      const rect = viewport.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
      const newScale = Math.max(0.15, Math.min(8.0, scale * zoomFactor));

      // Zoom towards mouse position
      panX = mouseX - (mouseX - panX) * (newScale / scale);
      panY = mouseY - (mouseY - panY) * (newScale / scale);
      scale = newScale;

      updateTransform();
    }}, {{ passive: false }});

    window.addEventListener('keydown', (e) => {{
      if (e.key === '+' || e.key === '=') zoomIn();
      else if (e.key === '-' || e.key === '_') zoomOut();
      else if (e.key === '0') resetZoom();
    }});
  </script>
</body>
</html>
"""


def sanitize_mermaid(content: str) -> str:
    """Sanitize diagram content to prevent script injection while preserving Mermaid syntax like -->."""
    return re.sub(r"<\s*/?\s*script\b", "&lt;script", content, flags=re.I)


def render_html_page(
    target_label: str,
    diagrams: list[tuple[str, str, Path]],
    output_path: Path,
) -> None:
    page_title = f"{target_label} — Architecture Diagram Preview"
    header_badge = target_label
    header_title = diagrams[0][0] if len(diagrams) == 1 else "Architecture Diagrams"

    tabs_html = ""
    if len(diagrams) > 1:
        tab_buttons = []
        for idx, (title, _, _) in enumerate(diagrams):
            active_cls = " active" if idx == 0 else ""
            tab_buttons.append(
                f'<button class="tab-btn{active_cls}" onclick="switchTab({idx})">{html.escape(title)}</button>'
            )
        tabs_html = f'<div class="tabs">{"".join(tab_buttons)}</div>'

    panels = []
    for idx, (title, content, _) in enumerate(diagrams):
        active_cls = " active" if idx == 0 else ""
        safe_content = sanitize_mermaid(content)
        panels.append(
            f'<div class="diagram-panel{active_cls}" id="panel-{idx}">'
            f'<pre class="mermaid">\n{safe_content}\n</pre>'
            f'</div>'
        )
    diagram_panels_html = "\n".join(panels)

    rendered = HTML_TEMPLATE.format(
        page_title=html.escape(page_title),
        header_badge=html.escape(header_badge),
        header_title=html.escape(header_title),
        tabs_html=tabs_html,
        diagram_panels_html=diagram_panels_html,
    )
    output_path.write_text(rendered, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Zero-width-limit browser viewer for ticket Mermaid diagrams."
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="Ticket ID (e.g. T211 or 211) or path to .mmd file",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Generate HTML without opening in default browser",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_OUT,
        help="Path to output HTML file (default: /tmp/w0m-diagram-preview.html)",
    )

    args = parser.parse_args()

    if not args.target:
        print(
            "❌ diagram-view: Missing target argument. Usage: just diagram <T## | path/to/diagram.mmd>",
            file=sys.stderr,
        )
        return 1

    target_str = args.target.strip()
    target_path = Path(target_str)

    # 1. Direct file path case
    if target_str.endswith(".mmd") or target_path.exists():
        if not target_path.exists():
            print(f"❌ diagram-view: File not found: {target_str}", file=sys.stderr)
            return 1
        raw_text = target_path.read_text(encoding="utf-8")
        cleaned = clean_diagram_content(raw_text)
        if not cleaned:
            print(f"❌ diagram-view: Diagram file is empty: {target_str}", file=sys.stderr)
            return 1
        title = target_path.stem.replace("-", " ").replace("_", " ").strip().title()
        diagrams = [(title, cleaned, target_path)]
        target_label = target_path.name
    else:
        # 2. Ticket ID case
        tid = normalize_id(target_str)
        ticket_file = TICKETS_DIR / f"{tid}.md"
        diagrams = discover_ticket_diagrams(tid)
        if not ticket_file.exists() and not diagrams:
            print(f"❌ diagram-view: Ticket {tid} does not exist in {TICKETS_DIR.relative_to(ROOT)}/", file=sys.stderr)
            return 1
        if not diagrams:
            print(
                f"❌ diagram-view: No .mmd diagrams found for ticket {tid} in {TICKETS_DIR.relative_to(ROOT)}/ "
                f"(expected {tid}.mmd or {tid}-*.mmd)",
                file=sys.stderr,
            )
            return 1
        target_label = tid

    out_path = args.output.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    render_html_page(target_label, diagrams, out_path)
    print(f"Generated diagram preview at {out_path}")

    if not args.no_open:
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", str(out_path)], check=False)
            elif sys.platform.startswith("linux"):
                subprocess.run(["xdg-open", str(out_path)], check=False)
            elif sys.platform == "win32":
                os.startfile(str(out_path))  # type: ignore[attr-defined]
        except Exception as e:
            print(f" [WARN] could not launch browser: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
