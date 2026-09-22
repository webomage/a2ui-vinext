#!/usr/bin/env python3
r"""doc-format-check -- documents are Markdown, diagrams are Mermaid.

Owner instruction 2026-08-22: "use everywhere .md/.mmd format as default". This gate makes that
mechanical for the surfaces the estate authors, and declares its boundary rather than guessing at
one: a PDF is a deliverable, an image is an asset, a stylesheet is code. None of those is a
document written in the wrong format. What fails is PROSE or a DIAGRAM whose source was authored in
something other than Markdown or Mermaid.

Scoped to TRACKED files, because a gate that fires on uncommitted scratch is a gate people learn to
ignore -- the same lesson `ac-recipe-check` was narrowed by (T135 AC8).

Measured when written: the estate already authors every diagram in Mermaid (zero .puml, .drawio or
.dot anywhere), so the diagram half starts green and stays that way by ratchet rather than by
cleanup. The prose half found exactly one real violation.

Exit codes: 0 clean * 1 a violation * 2 could not measure.

Run it as `just doc-format-check`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "project" / "policies" / "doc-format-policy.json"
REPOS = ["wom7web", "wom7api", "wom7ext", "wom7skills", "wom7func", "wom7sec"]


def tracked(repo: Path) -> list[str]:
    """Every tracked path in a repo. Empty list when the repo cannot be read."""
    try:
        out = subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True,
                             text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return []
    return out.stdout.splitlines() if out.returncode == 0 else []


def scan(pol: dict) -> tuple[list[str], list[str], int]:
    """(violations, acknowledged, files_considered)."""
    docfmt = set(pol["document_formats"])
    diafmt = set(pol["diagram_formats"])
    roots = tuple(pol["doc_roots"])
    bad: list[str] = []
    ack: list[str] = []
    seen = 0
    for name in REPOS:
        repo = ROOT / name
        if not repo.exists():
            continue
        for rel in tracked(repo):
            if not rel.startswith(roots):
                continue
            seen += 1
            ext = Path(rel).suffix.lower()
            if ext in docfmt:
                why = pol["acknowledged"].get(rel)
                (ack if why else bad).append(
                    f"{name}/{rel} — {why}" if why
                    else f"{name}/{rel}: a document authored in {ext}; Markdown is the default")
            elif ext in diafmt:
                bad.append(f"{name}/{rel}: a diagram in {ext}; Mermaid (.mmd) is the default")
    return bad, ack, seen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if not POLICY.exists():
        print("doc-format-check: project/policies/doc-format-policy.json is missing — not passing.")
        return 2
    pol = json.loads(POLICY.read_text(encoding="utf-8"))
    bad, ack, seen = scan(pol)

    if not seen:
        # Zero files considered means the walk or `git ls-files` failed, not a clean estate (T240).
        print("doc-format-check: 0 tracked files under the declared doc roots. The reader is "
              "broken, not the estate clean.")
        return 2

    if a.json:
        print(json.dumps({"considered": seen, "violations": bad, "acknowledged": ack}, indent=2))
        return 1 if bad else 0

    print(f"doc-format-check — {seen} tracked file(s) under {', '.join(pol['doc_roots'])}/")
    if ack:
        print(f"\n  {len(ack)} acknowledged (reason recorded, printed every run):")
        for x in ack:
            print(f"      {x}")
    if bad:
        print(f"\n  {len(bad)} violation(s):")
        for x in bad:
            print(f"      {x}")
        print("\n  Convert the source to Markdown (.md) or Mermaid (.mmd), or add it to")
        print("  `acknowledged` in doc-format-policy.json WITH the reason it is not a document.")
        return 1
    print("\n  [OK] every tracked document is Markdown and every diagram is Mermaid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
