#!/usr/bin/env python3
"""Show git-hook run history — `just hook-log [n]`.

Exists because the hooks logged nothing. A pre-push failure printed to a terminal and vanished
with the scrollback, so finding WHICH of ~285 lines of gates blocked a push meant re-running the
whole chain for information the first run already had. That happened four times in one session.

🔻 A tiny script rather than a `just` one-liner, and that is the point: the first version WAS an
inline `python3 -c` inside the recipe, and its escaped quotes collapsed into
`SyntaxError: unexpected character after line continuation character`. The estate's own rule —
tool ladder MCP > CLI > Python > TS > bash-oneliner, "move UP when a one-liner wants control flow
or a heredoc" — was written for exactly this, and the one-liner broke on its first run.

Reads `$W0M_HOOK_LOG_DIR/runs.jsonl` (default `~/.cache/w0m/hooks`), one JSON object per run.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def log_dir() -> Path:
    return Path(os.environ.get("W0M_HOOK_LOG_DIR") or (Path.home() / ".cache/w0m/hooks"))


def main() -> int:
    d = log_dir()
    runs = d / "runs.jsonl"
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 0

    if not n:
        latest = d / "pre-push-latest.log"
        if not latest.exists():
            print("no hook run recorded yet — push once to create one")
            return 0
        print(f"▶ {latest.resolve()}\n")
        print(latest.read_text(errors="replace"))
        return 0

    if not runs.exists():
        print(f"no runs recorded yet ({runs})")
        return 0
    lines = [ln for ln in runs.read_text(errors="replace").splitlines() if ln.strip()][-n:]
    if not lines:
        print("runs.jsonl is empty")
        return 0
    for ln in lines:
        try:
            r: dict[str, object] = json.loads(ln)
        except json.JSONDecodeError:
            print(f"  (unparseable line) {ln[:90]}")
            continue
        # Exit code first after the timestamp: it is the only field anyone scans for.
        mark = "✅" if r.get("exit") == 0 else "❌"
        print(f"  {mark} {r.get('ts','?'):<21} {r.get('hook','?'):<9} "
              f"exit={str(r.get('exit','?')):<3} {str(r.get('seconds','?')):>4}s  {r.get('log','')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
