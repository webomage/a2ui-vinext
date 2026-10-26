#!/usr/bin/env python3
"""Index every recorded DECISION in the estate — T232 AC8, the ADR value without an ADR store.

🔴 THIS DELIBERATELY DOES NOT CREATE A NINTH REGISTER. Measured 2026-08-19, decisions are already
recorded — **44 ticket files**, `.w0m/sdlc.json` (6), `TECH-DEBT.md` (4), `ROADMAP.md` (2),
`project/data/cv/resolutions.json` (3). What is missing is not the record, it is the **INDEX**: no
way to answer *"was this decided, or did it just happen?"* without grepping. Adding an `docs/adr/`
series would move decisions to a new place and leave these behind — the estate's recurring failure,
where a register nobody reads accumulates beside the ones people actually write in.

⇒ Decisions stay where they were made. This GENERATES an index that points at them.

⚠️ THE INDEX IS GENERATED, NEVER HAND-EDITED. A hand-maintained index is accurate on the day it is
written and decays silently — the exact shape of `AGENTS.md`'s dangling `LESSONS.md` pointer, which
sent agents to a file that did not exist for weeks. `just decisions` rebuilds it; drift is
impossible because nothing is retyped.

🔴 IT REFUSES AN EMPTY SWEEP. Zero decisions found exits 1: the corpus is known to hold ~59, so an
empty result means the matcher broke, not that nobody decided anything.

Usage:  python3 scripts/decisions_index.py [--check]
`--check` exits 1 if the committed index is stale — for the pre-push gate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[1]
ESTATE = ROOT  # the estate root holds the elevated registers, docs/ and .tasks/ (T411/T414/T509)
OUT = ROOT / "docs" / "DECISIONS.md"

# Surfaces that hold decisions today. Explicit, like the CV corpus's document list and for the same
# reason: a clever glob would silently start or stop covering a file and nobody would notice.
AGDR_DIR = "docs/decisions/AgDR-*.md"

# (kind, base, pattern). `base` is where the surface's CANONICAL copy lives.
SOURCES = [
    ("ticket", ESTATE, ".tasks/T*.md"),
    ("config", ESTATE, ".w0m/sdlc.json"),
    ("debt", ESTATE, "TECH-DEBT.md"),
    ("roadmap", ESTATE, "ROADMAP.md"),
    ("cv", ROOT, "w0m-web/project/data/cv/resolutions.json"),
    ("policy", ESTATE, "project/policies/confirm-policy.json"),
]

# A decision is an explicit CLAIM that someone chose something — not the word "decide" in passing.
MARKER = re.compile(
    r"(OWNER (?:DECISION|RULING)|owner (?:decision|ruling|call)|"
    r"[Oo]wner,? \d{4}-\d{2}-\d{2}|DECIDED(?: \d{4}-\d{2}-\d{2})?|decidedOn)", re.M)
DATE = re.compile(r"(20\d{2}-\d{2}-\d{2})")


def die(msg: str, code: int = 1) -> NoReturn:
    print(f"\n❌ {msg}", file=sys.stderr)
    raise SystemExit(code)


def agdr_records() -> list[dict]:
    """Structured AgDR records — read as FIRST-CLASS, not as another prose surface.

    🔴 `superseded_by` is why this format was adopted. 126 tickets and 199 commits carry corrections
    written IN PLACE, so a reader of the original gets no signal it was overturned. A structured
    link lets the index strike the old decision through and name what replaced it.
    """
    out = []
    for p in sorted(ROOT.glob(AGDR_DIR)):
        txt = p.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---", txt, re.S)
        if not m:
            continue
        fm = {}
        for line in m.group(1).splitlines():
            km = re.match(r"^([a-z_]+):\s*(.*)$", line)
            if km:
                fm[km.group(1)] = re.sub(r"\s+#.*$", "", km.group(2)).strip().strip('"')
        y = re.search(r"^## Y-statement\s*\n+> (.+?)(?=\n\n)", txt, re.S | re.M)
        out.append({
            "kind": "agdr", "file": str(p.relative_to(ROOT)), "line": 1,
            "date": (fm.get("timestamp") or "")[:10],
            "id": fm.get("id", ""), "title": fm.get("title", ""),
            "agent": fm.get("agent", ""), "model": fm.get("model", ""),
            "status": fm.get("status", ""), "superseded_by": fm.get("superseded_by", ""),
            "ticket": fm.get("ticket", ""),
            "text": re.sub(r"\s+", " ", re.sub(r"[*>_`]", "", y.group(1))).strip() if y else fm.get("title", ""),
        })
    return out


def harvest_repo_decisions() -> list[dict]:
    """T392 AC2 — widen harvest beyond w0m-web across all repos declared in .w0m/sdlc.json."""
    out: list[dict] = []
    sdlc_file = ROOT / ".w0m" / "sdlc.json"
    if not sdlc_file.is_file():
        return out
    try:
        sdlc = json.loads(sdlc_file.read_text(encoding="utf-8"))
        repos = sorted(set(sdlc.get("repos", {}).values()))
    except Exception:
        return out

    for repo in repos:
        rdir = ROOT / repo
        if not rdir.is_dir():
            continue
        for name in ["AGENTS.md", "CLAUDE.md"]:
            p = rdir / name
            if not p.is_file():
                continue
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                m = MARKER.search(line)
                if not m:
                    continue
                text = re.sub(r"[*_`>#|]+", " ", line).strip()
                text = re.sub(r"\s+", " ", text)
                start = max(0, m.start() - 40)
                d = DATE.search(line)
                out.append({
                    "kind": "repo",
                    "file": os.path.relpath(p, ROOT),
                    "line": n,
                    "date": d.group(1) if d else "",
                    "text": text[start:start + 260].strip(),
                })
    return out


def harvest() -> list[dict]:
    out: list[dict] = []
    for kind, base, pattern in SOURCES:
        paths = sorted(base.glob(pattern)) if "*" in pattern else [base / pattern]
        # Fail closed: a declared surface that resolves to nothing is a moved path, not "no decisions".
        if not paths or not all(p.exists() for p in paths):
            die(f"decision source `{kind}` ({base / pattern}) does not exist — a declared surface moved; "
                "update SOURCES rather than letting the index shrink silently.")
        for p in paths:
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                m = MARKER.search(line)
                if not m:
                    continue
                # The claim, trimmed of markdown noise but never reworded.
                text = re.sub(r"[*_`>#|]+", " ", line).strip()
                text = re.sub(r"\s+", " ", text)
                start = max(0, m.start() - 40)
                d = DATE.search(line)
                out.append({
                    "kind": kind,
                    "file": os.path.relpath(p, ROOT),
                    "line": n,
                    "date": d.group(1) if d else "",
                    "text": text[start:start + 260].strip(),
                })
    out.extend(harvest_repo_decisions())
    return out


def render(rows: list[dict]) -> str:
    dated = sorted([r for r in rows if r["date"]], key=lambda r: r["date"], reverse=True)
    undated = [r for r in rows if not r["date"]]
    agdr = [r for r in rows if r["kind"] == "agdr"]
    rows = [r for r in rows if r["kind"] != "agdr"]
    L = [
        "# Decisions — index",
        "",
        "> ⚠️ **GENERATED by `just decisions` — do not hand-edit.** An index maintained by hand is",
        "> accurate the day it is written and decays in silence. Run the recipe instead.",
        "",
        "🔴 **This is an INDEX, not a store.** Every decision below still lives in the file that",
        "records it, with the reasoning around it. This page exists to answer *\"was this decided,",
        "or did it just happen?\"* without grepping — nothing here is the source of truth.",
        "",
        f"**{len(rows) + len(agdr)} recorded decision(s)** — {len(agdr)} structured (AgDR), "
        f"{len(rows)} in place across {len({r['file'] for r in rows})} file(s).",
        "",
    ]
    if agdr:
        L += ["## Structured records (AgDR)", "",
              "Decisions recorded in the [AgDR](../project/templates/decision.md) format since "
              "2026-08-19. ⚠️ **A superseded record is struck through and names its replacement** — "
              "the field this format was adopted for.", "",
              "| id | Status | Agent / model | Decision |", "|---|---|---|---|"]
        for r in sorted(agdr, key=lambda r: r["id"]):
            sup = r["superseded_by"].strip()
            title = f"~~{r['title']}~~ → **{sup}**" if sup else r["title"]
            st = "🔴 superseded" if sup or r["status"] == "superseded" else r["status"]
            L.append(f"| [`{r['id']}`]({_rel(r['file'])}) | {st} | {r['agent']} / {r['model']} | "
                     f"{title}<br/><sub>{r['text'][:200]}</sub> |")
        L += [""]
    L += [
        "## Recorded in place (unstructured)",
        "",
        "⚠️ These predate AgDR and are **indexed, not migrated** — the reasoning stays in the file "
        "that made it.",
        "",
        "| Date | Where | Decision |",
        "|---|---|---|",
    ]
    for r in dated:
        L.append(f"| {r['date']} | [`{r['file']}:{r['line']}`]({_rel(r['file'])}) | {r['text']} |")
    if undated:
        L += ["", "## Undated", "",
              "⚠️ These carry no date in the line that declares them, so they cannot be ordered.",
              "", "| Where | Decision |", "|---|---|"]
        for r in undated:
            L.append(f"| [`{r['file']}:{r['line']}`]({_rel(r['file'])}) | {r['text']} |")
    return "\n".join(L) + "\n"


def _rel(f: str) -> str:
    return "../" + f


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="fail if the committed index is stale")
    ap.add_argument("--write", action="store_true", help="write the index (default when --check is not set)")
    a = ap.parse_args()

    rows = harvest() + agdr_records()
    if not rows:
        die("found ZERO decisions. The corpus is known to hold dozens, so this means the matcher "
            "broke — not that nobody decided anything. Refusing to publish an empty index.")
    body = render(rows)

    if a.check:
        if not OUT.exists():
            die(f"{OUT.relative_to(ROOT)} does not exist — run `just decisions`.")
        if OUT.read_text(encoding="utf-8") != body:
            die(f"{OUT.relative_to(ROOT)} is STALE — run `just decisions` and commit the result.")
        print(f"✅ decisions index current — {len(rows)} decision(s)")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8")
    by: dict[str, int] = {}
    for r in rows:
        by[r["kind"]] = by.get(r["kind"], 0) + 1
    print(f"decisions index → {OUT.relative_to(ROOT)}")
    for k, v in sorted(by.items(), key=lambda t: -t[1]):
        print(f"  {k:9} {v:3}")
    print(f"\n✅ {len(rows)} decision(s) indexed. The index POINTS; the files still hold the record.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
