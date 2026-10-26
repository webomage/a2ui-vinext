#!/usr/bin/env python3
"""Refuse to commit while a deploy is in flight.

## Why this exists

`confirm_step.py` binds a granted consent to the git HEAD it was granted at:

    if c.get("head") != head_sha():   # the tree moved; what was agreed is not what would ship
        return None

That is correct and worth keeping. Its consequence is easy to miss: **any commit during a deploy
invalidates the consent**, so every remaining step in the chain re-prompts. The owner hits it, not
the committer, and the symptom ("it keeps asking me for every app") looks nothing like the cause.

On 2026-08-16 this happened repeatedly in one session. An agent committed at 04:40 during a deploy
that started at 04:38, and again at 05:01 and 06:10. Each time the owner was asked to re-confirm
every remaining step, and each time the diagnosis went looking at the confirm POLICY — which was
correct throughout. Three fixes were made to coverage and TTL before the actual cause was found.

A promise to be careful does not survive the next session. This does.

## What it does NOT do

It does not detect deploys on another machine, and it does not stop `git commit --no-verify`
(prohibited here anyway). It is a guard against the ordinary mistake, not a security boundary.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "w0m-web"
SDLC = ROOT / ".w0m" / "sdlc.json"

# The recipes whose consent a commit would invalidate — `just deploy-web` counts too, being a
# chained step under the same consent.
#
# 🔴 Matched against the process's ARGUMENTS, and only when its EXECUTABLE is `just`.
# The first version searched the whole command line for the phrase and immediately produced a false
# positive: it matched the very shell running this check, because that shell's script text contained
# the words `just deploy` inside an unrelated `pgrep -f 'just deploy'`. A guard that blocks every
# commit is worse than the bug it prevents, and "the string appears somewhere" is not "a deploy is
# running" — the same substring-vs-identity trap this estate keeps rediscovering.
DEPLOY_RE = re.compile(r"^(deploy|deploy-all|deploy-(?!in-flight|ratchets|confirm-test|logged-test)[a-z-]+)$")


def estate_root() -> Path | None:
    """The declared estate root — `.w0m/sdlc.json -> root`, resolved against this repo.

    🔑 READ, never assumed. CLAUDE.md's standing rule is *measure from the root the CONFIG
    declares*, and this estate has been bitten twice by surveys that started somewhere plausible
    and described a different system accurately (T255). Returns None when the declaration cannot
    be read, which the caller treats as UNMEASURABLE — not as "no estate".
    """
    try:
        cfg_file = SDLC.resolve()
        root = json.loads(cfg_file.read_text(encoding="utf-8")).get("root")
    except (OSError, ValueError):
        return None
    if not isinstance(root, str) or not root:
        return None
    cfg_root = cfg_file.parent.parent if cfg_file.parent.name == ".w0m" else WEB
    return (cfg_root / root).resolve()


def process_cwd(pid: str) -> tuple[str | None, str]:
    """(cwd, state) for a pid. state is 'ok' | 'gone' | 'unmeasurable'.

    🔴 THREE STATES, NOT TWO, and the distinction is the whole point (T242's lesson, met again).
      ok            we read the cwd
      gone          the process no longer exists — a MEASUREMENT, and it means the deploy ended
      unmeasurable  lsof is missing, denied, or unparseable — we know nothing, so FAIL CLOSED

    ⚠️ `gone` is common, not an edge. Both live trials of this technique on 2026-08-23/24 hit it:
    pid 35132 and pid 56562 had each exited between the `ps` scan and the cwd lookup. A deploy that
    finished between two syscalls must not block a commit, so it resolves to `gone` -> allow.
    """
    try:
        r = subprocess.run(["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None, "unmeasurable"
    for line in r.stdout.splitlines():
        # ⚠️ Parse by FIELD TAG, never by line number. `-F` emits tagged lines and the second one
        # is `fcwd`, the descriptor — not a path. Taking `sed -n 2p` here yields the literal string
        # "fcwd", which matches no estate root and would make every deploy look foreign. That parse
        # bug fails OPEN, which is the direction that costs something.
        if line.startswith("n"):
            return line[1:], "ok"
    # No `n` field and lsof did not error: the pid is gone. `ps` agrees or it does not exist.
    alive = subprocess.run(["ps", "-p", pid], capture_output=True, text=True).returncode == 0
    return (None, "unmeasurable") if alive else (None, "gone")


def running_deploys() -> tuple[list[str], list[str]]:
    """(blocking, unmeasurable) — deploys INSIDE the declared estate, and ones we could not scope.

    🔴 Scoped to the estate, not the host (T267 AC1). The previous version matched any `just
    deploy*` anywhere on the machine, so on 2026-08-23 another project's apex deploy blocked a
    commit here — in a repo that has no `confirm_step.py` at all. The fact being protected is
    repo-scoped: `confirm_step.py:148` pins `head_sha()` to `cwd=WEB_ROOT`.

    🔑 And the OBVIOUS narrowing is wrong. "Block only if the deploy's git toplevel is this repo"
    would UNBLOCK the case the hook exists for, because a w0m deploy runs from `w0m-api/` — a
    different repo under the same estate. The boundary is the ESTATE, which `.w0m/sdlc.json`
    already declares.
    """
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid=,command="], capture_output=True, text=True, timeout=10
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return [], ["ps failed — the process list could not be read"]

    root = estate_root()
    if root is None:
        return [], [f"cannot read the declared estate root from {SDLC}"]

    blocking: list[str] = []
    unmeasurable: list[str] = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        pid = parts[0]
        exe = parts[1].rsplit("/", 1)[-1]      # the binary, not the whole command line
        if exe != "just":
            continue
        # `just <recipe> [args]` — the recipe is the first non-flag argument.
        for arg in parts[2:]:
            if arg.startswith("-"):
                continue
            if DEPLOY_RE.match(arg):
                cwd, state = process_cwd(pid)
                desc = line.strip()[:120]
                if state == "gone":
                    pass                       # finished mid-check; nothing to protect
                elif state == "unmeasurable":
                    unmeasurable.append(f"{desc}  (cwd unreadable)")
                elif cwd is not None and Path(cwd).resolve().is_relative_to(root):
                    blocking.append(f"{desc}  (in {root})")
                # else: resolved, and outside the estate — not our business
            break
    return blocking, unmeasurable


def main() -> int:
    blocking, unmeasurable = running_deploys()

    # 🔴 UNMEASURABLE gets its own message and its own paragraph. "I could not scope this" and
    # "a deploy is running here" are different facts, and printing the same words for both is the
    # defect T242 removed from authz_probe_suite — where `got=-1` made an unreachable database
    # indistinguishable from three policy violations and blocked two pushes as a security finding.
    # It still FAILS CLOSED: you may not commit past a deploy you could not scope.
    if unmeasurable:
        # TEXT dialect, not a glyph: `emoji-check`'s script_output ratchet is at 0 and a new
        # line must not be the thing that raises it. T257 migrates the estate this way anyway.
        print("\n\033[33m\033[1m[WARN] A deploy is running and its SCOPE could not be determined."
              "\033[0m")
        for u in unmeasurable:
            print(f"     {u}")
        print(
            "\n   This is NOT the same as 'a deploy is running in this estate' — it is 'this check\n"
            "   could not tell'. Failing closed because certifying a commit against a deploy you\n"
            "   cannot locate is a guess. If `lsof` is unavailable here, that is the thing to fix.\n"
        )
        return 1

    if not blocking:
        return 0

    print("\n\033[31m\033[1m❌ A deploy is running in THIS estate — committing now would break "
          "it.\033[0m")
    for h in blocking:
        print(f"     {h}")
    print(
        "\n   Consent for a deploy is bound to the git HEAD it was granted at "
        "(confirm_step.py:148).\n"
        "   Committing moves HEAD, so the running deploy loses its consent and re-prompts for\n"
        "   EVERY remaining step. The person at the terminal pays for it, not you, and the\n"
        "   symptom looks like a broken confirm policy rather than a commit.\n\n"
        "   Scoped to the estate declared at `.w0m/sdlc.json -> root` (T267). A deploy in another\n"
        "   project on this machine no longer blocks you — that was a real false positive on\n"
        "   2026-08-23, when 1945's apex deploy stopped a commit here.\n\n"
        "   Wait for the deploy to finish, then commit. Nothing here is lost by waiting.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
