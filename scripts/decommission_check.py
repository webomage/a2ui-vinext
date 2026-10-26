#!/usr/bin/env python3
"""Decommission drift — does a tombstone still describe something that is actually gone?

    python3 scripts/decommission_check.py            # report, exit 0
    python3 scripts/decommission_check.py --enforce  # exit 1 if a retirement came back

WHY THIS EXISTS
---------------
`DECOMMISSIONED.md` and the audit's drift check had **zero overlap** before this. Measured
2026-08-31:

  · the log declared 5 tombstones — openclaw, UpworkPollerWorkflow, wom7swarm, wom7md, the
    OpenClaw native surface — and **nothing in the estate read the file**. All five code
    references to it were prose comments pointing at a document no program opened.
  · `w0m_audit.py` checked exactly 2 hardcoded terms, `openrouter` and `SWARM_URL`. Only
    `SWARM_URL` corresponded to a tombstone. `openrouter` appeared **nowhere** in the log —
    checked but never recorded as retired, which is how a real owner decision stayed invisible.

So: a declaration with no reader on one side, a reader with no declaration on the other. This
script is the join. Each tombstone now carries an ```absent``` block naming what must stay gone,
and that block is the ONLY source — adding a tombstone without one is reported, not ignored.

Giving the log a reader is also what settles [[D15]]. Its recorded blocker was *"deciding this
means choosing a repo"*; a gate must read a versioned file, and the gate lives in `w0m-web`, so
the file moved here and became versioned as a consequence rather than as a preference.

WHAT AN ASSERTION MAY SAY
-------------------------
    code:  ["SWARM_URL"]        symbols that must not reappear in tracked source
    repos: ["w0m-api"]          which repos `code` is searched in (default: w0m-web)
    path:  ["wom7md"]           paths that must not exist; estate-relative, or ~ for host files
    except: [{path, why}]       a file that may legitimately name it, AND WHY

⚠️ **`except` requires a `why` and is refused without one.** A retirement leaves legitimate
traces — a provenance comment recording what code was ported FROM, a vendor-generated type union,
a comment explaining the decommission itself. Those are the record working, not drift. But an
allowlist without stated reasons is how a gate quietly stops meaning anything, and a gate that
fires on legitimate traces is one somebody switches off (T135 AC8). Both failure modes are real,
so the exception is allowed and made to justify itself. An entry whose file no longer matches is
reported as STALE — an acknowledgement that has outlived its cause is itself drift.

`path` accepts host paths on purpose. T196: OpenClaw's LaunchAgent kept four plaintext secrets and
a KeepAlive daemon alive for 21 days AFTER its tombstone was written, and every gate was
STRUCTURALLY blind because `~/Library/LaunchAgents` is not a repo. Decommissioning means auditing
the surfaces a component INSTALLED, not only the ones it occupied in git.

WHAT IT CANNOT SEE
------------------
Secret stores. `OPENROUTER_KEY` is still provisioned in Supabase and Cloudflare while every
`code:` assertion for it is green. A green run here means "the code is gone", never "the thing is
fully retired" — the credential half belongs to `credential-snapshot` and to a human.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

ESTATE = Path(__file__).resolve().parents[1]
WEB_ROOT = ESTATE / "w0m-web"
LOG = WEB_ROOT / "DECOMMISSIONED.md"

# w0m-web-relative code roots, matching w0m_audit.py's CODE_PATHS.
CODE_PATHS = ("apps", "packages")

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"

HEADING = re.compile(r"^## (.+)$", re.M)
BLOCK = re.compile(r"^```absent\n(.*?)^```", re.M | re.S)


def load_assertions(path: Path = LOG) -> tuple[list[dict], list[str]]:
    """Every tombstone's `absent` block, plus the names of tombstones that have none."""
    if not path.exists():
        raise FileNotFoundError(f"{path} — the tombstone log is missing")
    text = path.read_text(encoding="utf-8")

    heads = [(m.start(), m.group(1).strip()) for m in HEADING.finditer(text)]
    out: list[dict] = []
    missing: list[str] = []
    for i, (start, name) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        section = text[start:end]
        m = BLOCK.search(section)
        if not m:
            missing.append(name)
            continue
        spec = yaml.safe_load(m.group(1)) or {}
        out.append({
            "tombstone": name,
            "code": list(spec.get("code") or []),
            "repos": list(spec.get("repos") or ["w0m-web"]),
            "path": list(spec.get("path") or []),
            "except": list(spec.get("except") or []),
        })
    return out, missing


def _grep_repo(term: str, repo: str) -> list[str]:
    """Tracked files in `repo` matching `term`. Only code roots for w0m-web, whole repo elsewhere."""
    root = ESTATE / repo
    if not (root / ".git").exists() and not (root / ".git").is_file():
        return []
    paths = [p for p in CODE_PATHS if (root / p).exists()] if repo == "w0m-web" else []
    cmd = ["git", "grep", "-liE", term]
    if paths:
        cmd += ["--", *paths]
    r = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False)
    return [f"{repo}/{l}" for l in r.stdout.splitlines() if l.strip()]


def check(a: dict) -> list[tuple[bool, str, str]]:
    """(ok, label, detail) per assertion in one tombstone."""
    results: list[tuple[bool, str, str]] = []

    allowed: dict[str, str] = {}
    for ex in a["except"]:
        if not isinstance(ex, dict) or not ex.get("path") or not ex.get("why"):
            results.append((False, "except", f"malformed entry {ex!r} — needs both `path` and `why`"))
            continue
        allowed[ex["path"]] = ex["why"]

    matched: set[str] = set()
    for term in a["code"]:
        hits: list[str] = []
        for repo in a["repos"]:
            hits += _grep_repo(term, repo)
        real = [h for h in hits if h not in allowed]
        matched |= {h for h in hits if h in allowed}
        note = f" ({len(hits) - len(real)} allowed)" if len(hits) != len(real) else ""
        results.append((
            not real,
            f"code {term!r}",
            f"absent (clean){note}" if not real
            else f"still in {len(real)} file(s): " + ", ".join(real[:3]),
        ))

    # An acknowledgement that has outlived its cause is drift of its own.
    for path in allowed:
        if path not in matched:
            results.append((False, f"except {path}", "STALE — allowed, but nothing matches it any more"))
    for raw in a["path"]:
        target = Path(raw).expanduser() if raw.startswith("~") else ESTATE / raw
        results.append((
            not target.exists(),
            f"path {raw}",
            "absent (clean)" if not target.exists() else "STILL EXISTS",
        ))
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--enforce", action="store_true")
    ap.add_argument("--log", default=str(LOG))
    args = ap.parse_args()

    assertions, missing = load_assertions(Path(args.log))

    # An empty corpus must FAIL rather than report a confident green over nothing.
    if not assertions:
        print(f"{RED}[FAIL] no `absent` blocks found in {args.log} — cannot measure{RESET}")
        return 1

    total = failed = 0
    print(f"{DIM}▶ decommission drift — {len(assertions)} tombstone(s) with assertions{RESET}")
    for a in assertions:
        rows = check(a)
        head = a["tombstone"].split("—")[0].strip()
        for ok, label, detail in rows:
            total += 1
            if not ok:
                failed += 1
            mark = f"{GREEN}ok{RESET}" if ok else f"{RED}BACK{RESET}"
            print(f"  [{mark}] {head}: {label} — {detail}")

    for name in missing:
        print(f"  {YELLOW}[warn]{RESET} {name.split('—')[0].strip()}: no `absent` block — "
              "retired, but nothing proves it stayed gone")

    print(f"\n  {total} assertion(s), {failed} regression(s), {len(missing)} tombstone(s) unasserted")
    if failed:
        print(f"{RED}[FAIL] a retired component is back in live source{RESET}")
        return 1 if args.enforce else 0
    print(f"{GREEN}✅ every asserted retirement is still gone{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
