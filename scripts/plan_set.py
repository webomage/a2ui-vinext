#!/usr/bin/env python3
"""T335 — the only sanctioned way to change `.w0m/sdlc.json -> current_plan`.

    just plan-set --list                       # browse ROADMAP's numbered epics (the "available raids" view)
    just plan-set 19 --reason "why"            # select one; writes name + roadmap + a fresh stages projection
    just plan-set "client alfa" --reason "…"   # free text works if it matches exactly ONE epic
    just plan-set --adopt --reason "…"         # stamp the CURRENT plan as set-by-tool without rewriting its stages
    just plan-set --check                      # AC3 gate: current_plan still resolves and was not hand-edited

Why it exists: `current_plan` answers "what is the estate trying to ship right now", and until now it was a JSON
value anyone (or any agent) could edit by hand with nothing validating it. Now a write must (1) resolve to exactly
one numbered ROADMAP section, (2) carry a stated reason, and (3) it leaves a fingerprint that `check` compares, so a
later hand-edit of `name`/`roadmap` is a red gate instead of a silent change. Read paths are untouched: `just tasks
current` / `plan` and the status dashboard keep reading `current_plan` exactly as before.

Fail closed: zero matches, several matches, no reason, or an epic with no tickets writes NOTHING and exits non-zero.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

SECTION_RE = re.compile(r"^##\s+(\d+)\.\s+(.+?)\s*$")
PRIORITY_RE = re.compile(r"\((P[0-3])\b")
TRAILING_TAG_RE = re.compile(r"\s*`([a-z0-9_]+)`\s*$")
PAREN_TAIL_RE = re.compile(r"\s*\((?:P[0-3]|status|added|updated|R&D|FEATURE)[^)]*\)\s*$")
ROADMAP_REF_RE = re.compile(r"§\s*(\d+)")


def read_epics(roadmap_md: Path) -> list[dict]:
    """ROADMAP's numbered top-level sections: `## 19. Security, RBAC & Platform Hardening (P0, added …) `tag``."""
    epics = []
    for line in roadmap_md.read_text(encoding="utf-8").splitlines():
        m = SECTION_RE.match(line)
        if not m:
            continue
        raw_title = m.group(2)
        tag_m = TRAILING_TAG_RE.search(raw_title)
        tag = tag_m.group(1) if tag_m else ""
        title = TRAILING_TAG_RE.sub("", raw_title).strip()
        pr = PRIORITY_RE.search(title)
        epics.append({
            "n": int(m.group(1)),
            "title": title,
            "name": PAREN_TAIL_RE.sub("", title).strip(),
            "priority": pr.group(1) if pr else "",
            "tag": tag,
        })
    return epics


def resolve(query: str, epics: list[dict]) -> list[dict]:
    """`19`, `§19`, `ROADMAP §19` -> that section; otherwise every token must appear in the title."""
    q = query.strip()
    m = re.fullmatch(r"(?:ROADMAP(?:\.md)?\s*)?§?\s*(\d+)", q, re.I)
    if m:
        return [e for e in epics if e["n"] == int(m.group(1))]
    tokens = [t for t in re.split(r"\s+", q.lower()) if t]
    if not tokens:
        return []
    return [e for e in epics if all(t in e["title"].lower() for t in tokens)]


def fingerprint(plan: dict) -> str:
    return hashlib.sha256(f"{plan.get('name', '')}|{plan.get('roadmap', '')}".encode("utf-8")).hexdigest()[:16]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_conf(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_conf(path: Path, conf: dict) -> None:
    # indent=2 + ensure_ascii=False + trailing newline round-trips the file byte-for-byte (measured), so a write
    # changes only `current_plan` and the diff is reviewable.
    path.write_text(json.dumps(conf, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def verify_plan(conf: dict, epics: list[dict]) -> list[str]:
    """AC3. Returns the list of problems (empty = OK). No `current_plan` declared is a legitimate state."""
    plan = conf.get("current_plan")
    if not plan:
        return []
    problems: list[str] = []
    ref = str(plan.get("roadmap", ""))
    m = ROADMAP_REF_RE.search(ref)
    if not m:
        problems.append(f"current_plan.roadmap {ref!r} names no ROADMAP section (expected 'ROADMAP.md §N')")
    elif int(m.group(1)) not in {e["n"] for e in epics}:
        problems.append(f"current_plan.roadmap {ref!r}: ROADMAP has no numbered section {m.group(1)}")
    stamp = plan.get("_set")
    if not isinstance(stamp, dict) or not stamp.get("fingerprint"):
        problems.append("current_plan was not set through `just plan-set` (no `_set` stamp); "
                        "run `just plan-set --adopt --reason \"…\"` if the value is right")
    elif stamp["fingerprint"] != fingerprint(plan):
        problems.append(f"current_plan.name/roadmap were edited by hand (fingerprint {fingerprint(plan)} != "
                        f"stamped {stamp['fingerprint']}); use `just plan-set <epic> --reason \"…\"`")
    return problems


def build_plan(epic: dict, tickets: list[dict], reason: str) -> dict:
    from tasks_query import build_dynamic_plan, epic_key  # lazily: importing it reads the workspace

    roadmap = f"ROADMAP.md §{epic['n']}"
    targets = {f"ROADMAP §{epic['n']}"}
    if epic.get("tag"):
        targets.add(epic["tag"])
    matched = [
        t for t in tickets
        if epic_key(t.get("epic", "")) in targets or t.get("epic", "") in targets
    ]
    plan = build_dynamic_plan(matched, epic["name"], roadmap)
    if not plan:
        raise SystemExit(f"❌ no ticket carries epic 'ROADMAP §{epic['n']}' — a plan must track something. "
                         f"Nothing written.")
    plan["roadmap"] = roadmap
    plan["_comment"] = (f"Set by `just plan-set` — {reason}. Stages are a projection of the tickets whose epic rolls up to "
                        f"ROADMAP §{epic['n']}; add `exit`/`exit_checks` by hand per stage if it needs a probe.")
    plan["_set"] = {"at": now_iso(), "reason": reason, "fingerprint": fingerprint(plan)}
    return plan


def append_history(path: Path, entry: dict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def cmd_list(epics: list[dict], current: str) -> int:
    m = ROADMAP_REF_RE.search(current or "")
    cur = int(m.group(1)) if m else None
    print(f"ROADMAP epics ({len(epics)}) — pick one with `just plan-set <number|words> --reason \"…\"`\n")
    for e in epics:
        mark = "*" if e["n"] == cur else " "
        print(f" {mark} {e['n']:>3}  {e['priority'] or '--':<3}  {e['name']}")
    if cur is not None:
        print("\n  * = current_plan")
    return 0


def cmd_set(conf_path: Path, history_path: Path, epics: list[dict], tickets: list[dict],
            query: str, reason: str, dry_run: bool) -> int:
    if not reason.strip():
        print("❌ --reason is required: a plan change must say why. Nothing written.", file=sys.stderr)
        return 2
    hits = resolve(query, epics)
    if not hits:
        print(f"❌ {query!r} matches no ROADMAP epic. Nothing written. Browse with `just plan-set --list`.",
              file=sys.stderr)
        return 1
    if len(hits) > 1:
        print(f"❌ {query!r} is ambiguous — {len(hits)} epics match; name one by number. Nothing written:",
              file=sys.stderr)
        for e in hits:
            print(f"     {e['n']:>3}  {e['name']}", file=sys.stderr)
        return 1
    conf = load_conf(conf_path)
    plan = build_plan(hits[0], tickets, reason.strip())
    previous = conf.get("current_plan")
    print(f"{'would set' if dry_run else 'setting'} current_plan -> §{hits[0]['n']} {plan['name']} "
          f"({len(plan['stages'])} stage(s), active {plan['active_stage']!r})")
    if dry_run:
        return 0
    conf["current_plan"] = plan
    save_conf(conf_path, conf)
    append_history(history_path, {"at": plan["_set"]["at"], "action": "set", "reason": reason.strip(),
                                  "to": {"name": plan["name"], "roadmap": plan["roadmap"]}, "previous": previous})
    print(f"✅ written; previous plan snapshot kept in {history_path.name}")
    return 0


def cmd_adopt(conf_path: Path, history_path: Path, epics: list[dict], reason: str) -> int:
    if not reason.strip():
        print("❌ --reason is required. Nothing written.", file=sys.stderr)
        return 2
    conf = load_conf(conf_path)
    plan = conf.get("current_plan")
    if not plan:
        print("❌ no current_plan to adopt. Nothing written.", file=sys.stderr)
        return 1
    ref = ROADMAP_REF_RE.search(str(plan.get("roadmap", "")))
    if not ref or int(ref.group(1)) not in {e["n"] for e in epics}:
        print(f"❌ current_plan.roadmap {plan.get('roadmap')!r} does not resolve to a ROADMAP section — "
              f"choose an epic with `just plan-set <epic> --reason …` instead. Nothing written.", file=sys.stderr)
        return 1
    plan["_set"] = {"at": now_iso(), "reason": reason.strip(), "fingerprint": fingerprint(plan), "adopted": True}
    save_conf(conf_path, conf)
    append_history(history_path, {"at": plan["_set"]["at"], "action": "adopt", "reason": reason.strip(),
                                  "to": {"name": plan.get("name"), "roadmap": plan.get("roadmap")}})
    print(f"✅ adopted current_plan {plan.get('name')!r} ({plan.get('roadmap')}); stages untouched")
    return 0


def cmd_check(conf_path: Path, epics: list[dict]) -> int:
    problems = verify_plan(load_conf(conf_path), epics)
    if problems:
        for p in problems:
            print(f"❌ {p}", file=sys.stderr)
        return 1
    print("✅ current_plan resolves to a ROADMAP section and matches its plan-set stamp")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="?", help="epic number (19, §19) or words that match exactly one epic title")
    ap.add_argument("--reason", default="", help="why the plan changes (required to write)")
    ap.add_argument("--list", action="store_true", help="print the numbered epic list")
    ap.add_argument("--adopt", action="store_true", help="stamp the current plan as set-by-tool, stages untouched")
    ap.add_argument("--check", action="store_true", help="verify current_plan (exit 1 on drift)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--root", type=Path, help="workspace root (default: discovered)")
    args = ap.parse_args(argv)

    if args.root:
        root = args.root
    else:
        from tasks_query import WORKSPACE_ROOT
        root = WORKSPACE_ROOT
    conf_path = root / ".w0m" / "sdlc.json"
    roadmap = root / "ROADMAP.md"
    if not conf_path.is_file() or not roadmap.is_file():
        print(f"❌ need {conf_path} and {roadmap}", file=sys.stderr)
        return 2
    epics = read_epics(roadmap)
    if not epics:
        print(f"❌ {roadmap} has no numbered '## N.' sections — refusing to run against nothing", file=sys.stderr)
        return 2
    history = root / ".w0m" / "plan-history.jsonl"

    if args.check:
        return cmd_check(conf_path, epics)
    if args.adopt:
        return cmd_adopt(conf_path, history, epics, args.reason)
    if args.list or not args.query:
        cur = (load_conf(conf_path).get("current_plan") or {}).get("roadmap", "")
        return cmd_list(epics, cur)
    from tasks_query import load
    return cmd_set(conf_path, history, epics, load(), args.query, args.reason, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
