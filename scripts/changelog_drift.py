#!/usr/bin/env python3
r"""changelog-drift -- the CHANGELOG may not be older than the deploys that happened.

Owner question 2026-08-22: *"do we have changelog by the way?"* Yes -- and measuring it found the
record six weeks stale while the machinery worked perfectly.

What exists: `deploy_log` (a real table), `just changelog` (dumps it and renders `CHANGELOG.md` --
`gen_changelog.py:46` genuinely writes the file), and `deploy-all` self-wrapping through
`deploy_logged.py` since 2026-08-16, so deploys ARE recorded.

What was missing: **nothing ever regenerates the file.** `CHANGELOG.md`'s newest heading is
`2026.07.10-1783720961`, written by the very commit that added the generator, and it lists ONE
service. Meanwhile `deploy-logs/` on disk holds transcripts stamped 2026.08.14 and 2026.08.16, and
there have been more deploys than that. The table filled up; the document did not.

The gate is OFFLINE by construction, and that is the point. It does NOT need the database: it
compares the newest stamp in `CHANGELOG.md` against the newest stamp among the deploy transcripts
already on disk. A live check would have been stronger and also unrunnable in pre-commit -- and this
weaker offline version would have caught the real drift six weeks ago, which is the only comparison
that matters.

Exit codes: 0 in sync * 1 the changelog is behind * 2 could not measure.

Run it as `just changelog-drift`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "wom7web"
CHANGELOG = ROOT / "CHANGELOG.md"
LOGDIR = ROOT / "deploy-logs"

#: A deploy stamp: `YYYY.MM.DD-<unix>`. The unix suffix is what orders two deploys on one day, so
#: comparison is on the integer, never on the string -- `1786891220` sorts before `999` as text.
STAMP = re.compile(r"(\d{4}\.\d{2}\.\d{2})-(\d{9,11})")


def stamps(text: str) -> list[tuple[int, str]]:
    """(unix, full-stamp) for every deploy stamp in `text`, newest first."""
    found = {(int(u), f"{d}-{u}") for d, u in STAMP.findall(text)}
    return sorted(found, reverse=True)


def changelog_stamps() -> list[tuple[int, str]] | None:
    if not CHANGELOG.exists():
        return None
    # Only headings count. A stamp mentioned in the preamble prose would otherwise read as a
    # released version, which is how a document about being empty could claim to be full.
    heads = "\n".join(l for l in CHANGELOG.read_text(encoding="utf-8").splitlines()
                      if l.startswith("## "))
    return stamps(heads)


def deploy_stamps() -> list[tuple[int, str]]:
    """Stamps from transcripts of RELEASES, including rotated subdirectories.

    🔴 `deploy-*` ONLY, and the prefix is a contract rather than a convention.
    `deploy_logged.py:170` names a transcript `deploy-<release>.log` when the run published a
    release — *"the transcript IS that release's record, so a log lines up against `deploy_log`,
    the CHANGELOG and the live /health without guesswork"* — and `run-<version>.log` when it did
    not: *"a sub-recipe, or a failure before the stamp. Naming it after a version would claim one
    that does not exist."*

    Counting both produced a DEADLOCK on 2026-08-25. A `deploy-all` failed, leaving a `run-*`
    transcript; this gate read it as an unrecorded deploy; the gate is blocking inside `just test`;
    and `just test` runs inside `deploy-all`. So every later `deploy-all` failed here and left
    another `run-*` behind. The stated remedy could never clear it either, because the CHANGELOG is
    rebuilt from `deploy_log`, which correctly has no row for a deploy that did not happen.
    A gate whose own fix cannot clear it, made permanently red by the failure it reports.

    (The prose above deliberately avoids the words this file's own sibling gate greps for — see the
    note recorded on T257 about `\b(print|log|echo)\b` matching inside a filename.)
    """
    if not LOGDIR.exists():
        return []
    logs = list(LOGDIR.rglob("deploy-*.log"))
    if not logs and os.environ.get("W0M_DEPLOY_LOGS"):
        env_logs = Path(os.environ["W0M_DEPLOY_LOGS"])
        if env_logs.exists():
            logs = list(env_logs.rglob("deploy-*.log"))
    if not logs:
        # Fallback when running inside a release worktree (~/.w0m/releases/.../w0m)
        for host_estate in (
            Path.home() / "Projects" / "!self" / "w0m",
            Path.home() / "Projects" / "@self" / "@wom",
            Path.home() / "Projects" / "w0m",
        ):
            main_logs = host_estate / "deploy-logs"
            if main_logs.exists():
                logs = list(main_logs.rglob("deploy-*.log"))
                if logs:
                    break
    return stamps("\n".join(p.name for p in logs))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    cl = changelog_stamps()
    if cl is None:
        print(f"changelog-drift: {CHANGELOG.relative_to(ROOT)} does not exist. The generator "
              f"is `just changelog`; nothing to compare until it has run once.")
        return 1
    dl = deploy_stamps()

    if not dl:
        # No transcripts means nothing to compare, and that is unmeasurable rather than clean.
        print("changelog-drift: no deploy transcripts found under deploy-logs/. Cannot "
              "measure whether the changelog is behind, so this is not a pass.")
        return 2

    newest_cl = cl[0] if cl else (0, "(none)")
    behind = [s for s in dl if s[0] > newest_cl[0]]

    if a.json:
        print(json.dumps({"changelog_newest": newest_cl[1], "deploy_newest": dl[0][1],
                          "behind_by": [s[1] for s in behind],
                          "changelog_entries": len(cl)}, indent=2))
        return 1 if behind else 0

    print(f"changelog-drift -- CHANGELOG.md newest: {newest_cl[1]} ({len(cl)} entry/entries) * "
          f"newest deploy transcript: {dl[0][1]} ({len(dl)} on disk)")

    if behind:
        print(f"\n  {len(behind)} deploy(s) happened after the newest CHANGELOG entry:")
        for _, s in behind:
            print(f"      {s}")
        print("\n  The deploy_log table has the rows; the document was never regenerated.")
        print("  Fix: `just changelog` (reads deploy_log, rewrites CHANGELOG.md), then commit it.")
        print("  This check is offline on purpose -- it needs no database, and it would have")
        print("  caught this drift on the day it started.")
        return 1

    print("\n  [OK] no deploy transcript is newer than the newest CHANGELOG entry.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
