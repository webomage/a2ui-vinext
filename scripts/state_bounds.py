#!/usr/bin/env python3
"""state_bounds.py — the CLIENT-CAPABLE half of `state_surface` (T182 Phase 5 / AC5).

`state_doctor.py` enforces `state_surface` for w0m and only w0m: 1019 lines that render a managed
block out of w0m's repo set, ticket queue and gate codes, reading `.w0m/sdlc.json` from a module
constant. None of that is meaningful for a client, and none of it can be pointed at one — which is
why six of the profile's eight required keys were found unenforceable at a client.

This is the part a client actually needs, and the part T177 is about: **are the agent-maintained
memory files within the bounds the project declares?** It is registry-driven, so it answers that
for every declared project including the clients.

  declared     the project's `.w0m/sdlc.json -> state_surface.retention` (`max_bytes`, `max_lines`)
  measured     every file named by `state_surface.file` plus the registry's
               `state_surface_candidates`, on disk, now
  verdict      within bounds / over / **UNDECLARED** — and undeclared is the finding, not a skip

🔴 Undeclared is reported as a defect rather than passed over. That is the whole of AC5: T177
recurred because nothing obliged a client to declare `state_surface`, so T174's retention fix had
nothing to attach to. A tool that skipped undeclared projects would reproduce the same hole.

⚠️ This measures, it does not rotate. Rotation is lossy — T174 required a disposition record
covering every section, and that discipline does not transfer to a client repo unattended.

Usage:
    python3 scripts/state_bounds.py            # report, exit 0
    python3 scripts/state_bounds.py --enforce  # over-budget or undeclared blocks
    python3 scripts/state_bounds.py --json
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]                      # …/@wom
CANONICAL = ROOT / "w0m-web"                # …/w0m-web
REGISTRY = ROOT / "project" / "policies" / "clients-policy.json"


def read_text(path: Path) -> str | None:
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError):
        return None


def load_json(path: Path) -> dict | None:
    text = read_text(path)
    if text is None:
        return None
    try:
        v = json.loads(text)
    except json.JSONDecodeError:
        return None
    return v if isinstance(v, dict) else None


def measure_file(path: Path) -> dict | None:
    text = read_text(path)
    if text is None:
        return None
    return {"bytes": len(text.encode()), "lines": len(text.splitlines())}


def resolve_project_root(rel_root: str) -> Path:
    direct = (ROOT / rel_root).resolve()
    if direct.is_dir() or rel_root in ("", ".") or Path(rel_root).is_absolute():
        return direct
    if (ROOT / ".git").is_file():
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            common_dir = Path(proc.stdout.strip())
            if not common_dir.is_absolute():
                common_dir = (ROOT / common_dir).resolve()
            alt = (common_dir.resolve().parent / rel_root).resolve()
            if alt.is_dir():
                return alt
    return direct


def audit() -> tuple[list[dict], list[str]]:
    """Returns (rows, errors)."""
    reg = load_json(REGISTRY)
    if reg is None:
        return [], [f"project registry unreadable: {REGISTRY}"]
    candidates = reg.get("state_surface_candidates") or []
    if not candidates:
        return [], ["registry declares no state_surface_candidates — this audit would inspect "
                    "nothing and report it as health"]

    rows: list[dict] = []
    for p in reg.get("projects", []):
        if not p.get("enabled"):
            continue
        root = resolve_project_root(p["root"])
        if not root.is_dir():
            return [], [f"{p['id']}: declared root does not exist — {root}"]
        # `root` may be a multi-repo WORKSPACE (w0m's is "." — T294, seven repos, not one) while
        # `.w0m/sdlc.json` and the state surface live in one specific repo inside it. `canonical_repo`
        # names that repo; default "." keeps every project with no such split reading from `root`
        # exactly as before.
        canon = root if p.get("role") == "w0m" else (root / p.get("canonical_repo", ".")).resolve()
        decl = load_json(canon / ".w0m" / "sdlc.json") or {}
        surface = decl.get("state_surface") or {}
        retention = surface.get("retention") or {}
        max_bytes = retention.get("max_bytes")
        max_lines = retention.get("max_lines")

        # The declared handoff file first, then every candidate that exists. Named files are
        # measured even when the project declares no bounds — that is precisely the case worth
        # seeing, and a tool that only measured declared-and-bounded projects would show T177 as
        # solved everywhere it had never been attempted.
        names = []
        if surface.get("file"):
            names.append(surface["file"])
        names += [c for c in candidates if c not in names]

        files = {}
        for n in names:
            m = measure_file(canon / n)
            if m:
                files[n] = m
        total = sum(f["bytes"] for f in files.values())
        biggest = max(files.items(), key=lambda kv: kv[1]["bytes"], default=None)

        declared = bool(max_bytes or max_lines)
        over = []
        if declared and biggest:
            for n, m in files.items():
                if max_bytes and m["bytes"] > max_bytes:
                    over.append(f"{n} {m['bytes']:,} B > {max_bytes:,}")
                elif max_lines and m["lines"] > max_lines:
                    over.append(f"{n} {m['lines']:,} lines > {max_lines:,}")

        rows.append({
            "project": p["id"], "role": p.get("role"), "declared": declared,
            "max_bytes": max_bytes, "max_lines": max_lines,
            "files": files, "total_bytes": total,
            "largest": biggest[0] if biggest else None,
            "largest_bytes": biggest[1]["bytes"] if biggest else 0,
            "over": over,
            # 🔴 "within" must mean MEASURED-and-inside, never "nothing was measured". A project
            # that declares bounds and has no memory file yet has verified nothing — reporting it
            # as within is a green tick over an empty set, the same shape the AC7 cold run caught
            # in the composite runner. servicios777 is exactly that case: bounds declared 2026-08-09
            # before any STATE.md exists, deliberately, so the first one written is already bounded.
            "verdict": ("undeclared" if not declared
                        else "no-files" if not files
                        else "over" if over else "within"),
        })

    if not rows:
        return [], ["no enabled project — an audit over nothing is not a pass"]
    if not any(r["files"] for r in rows):
        return [], ["no agent-memory file found in any project — refusing to report health over "
                    "an empty corpus"]
    return rows, []


def main() -> int:
    argv = set(sys.argv[1:])
    rows, errors = audit()
    if errors:
        if "--json" in argv:
            print(json.dumps({"ok": False, "errors": errors}, indent=2))
        else:
            print("\n  ✗ state-bounds not run\n")
            for e in errors:
                print(f"     ✗ {e}")
            print()
        return 2

    # `no-files` is not a failure: bounds declared ahead of the file is the correct order, and it
    # is what stops the next project repeating 1945's 411 KB. It is simply not a verified pass.
    bad = [r for r in rows if r["verdict"] not in ("within", "no-files")]
    if "--json" in argv:
        print(json.dumps({"ok": not bad, "projects": rows}, indent=2))
        return 1 if ("--enforce" in argv and bad) else 0

    print("\n  agent-memory bounds — declared vs measured\n")
    hdr = (f"  {'project':10} {'declared':>9} {'largest file':>22} {'bytes':>10} "
           f"{'limit':>9}  verdict")
    print(hdr)
    print("  " + "─" * (len(hdr) + 4))
    for r in rows:
        lim = f"{r['max_bytes']:,}" if r["max_bytes"] else "—"
        mark = {"within": "✓ within", "over": "✗ OVER", "undeclared": "🔴 UNDECLARED",
                "no-files": "· bounds set, no file yet"}[r["verdict"]]
        print(f"  {r['project']:10} {('yes' if r['declared'] else 'NO'):>9} "
              f"{(r['largest'] or '—'):>22} {r['largest_bytes']:10,} {lim:>9}  {mark}")

    for r in rows:
        if r["verdict"] in ("within", "no-files"):
            continue
        print(f"\n  ── {r['project']}")
        for n, m in sorted(r["files"].items(), key=lambda kv: -kv[1]["bytes"]):
            print(f"     {n:16} {m['bytes']:>9,} B  {m['lines']:>6,} lines")
        print(f"     total {r['total_bytes']:,} B")
        if r["verdict"] == "undeclared":
            print("     🔴 no `state_surface.retention` — nothing bounds these files, so nothing "
                  "can report them growing. This is T177's actual cause: the retention fix had "
                  "no declaration to attach to.")
        else:
            for o in r["over"]:
                print(f"     ✗ {o}")

    measured = sum(1 for r in rows if r["verdict"] == "within")
    pending = sum(1 for r in rows if r["verdict"] == "no-files")
    print(f"\n  {measured}/{len(rows)} MEASURED within declared bounds"
          + (f" · {pending} bounded ahead of any file" if pending else ""))
    blocking = "--enforce" in argv and bad
    print(f"  {'BLOCKING (--enforce)' if blocking else 'advisory — run with --enforce to block'}")
    print("  measures only; rotation is lossy and stays a deliberate act (T174 disposition record)\n")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
