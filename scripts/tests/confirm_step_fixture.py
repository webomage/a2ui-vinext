#!/usr/bin/env python3
"""Run confirm_step.main() with its two machine-dependent layers replaced (T435).

    confirm_step_fixture.py <caller> <presence> <step>

  caller    human | agent | unmeasurable   — what layer 1 (agent refusal) reports
  presence  yes | no | unavailable         — what layer 3 (the macOS Touch ID dialog) answers

WHY A FIXTURE AND NOT AN ENV VAR: the gate deliberately has no override variable — an escape
hatch the recipe path honours is the hole. This file is not on that path: `_confirm` runs
confirm_step.py, never this. Running it yourself proves nothing to any recipe.

It exists because the probe suite is run BY agents (so the real layer 1 would refuse every probe
for the wrong reason, and the TTY and consent logic would go untested) and BY the owner inside
`just deploy` (so the real layer 3 would pop a Touch ID dialog in the middle of a test run — the
T224 class: a test seizing the human's attention). Layer 2, the terminal, stays real.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import confirm_step  # noqa: E402

CALLERS = {
    "human": confirm_step.AgentVerdict(None, "fixture: human caller", True),
    "agent": confirm_step.AgentVerdict("agy", "fixture: ancestor `agy` pid 4242", True),
    "unmeasurable": confirm_step.AgentVerdict(None, "fixture: ancestry unreadable", False),
}
PRESENCE = {
    "yes": (True, "fixture: device owner verified"),
    "no": (False, "fixture: dialog cancelled"),
    "unavailable": (False, "fixture: LocalAuthentication unavailable"),
}


def main() -> int:
    if len(sys.argv) != 4 or sys.argv[1] not in CALLERS or sys.argv[2] not in PRESENCE:
        print(__doc__, file=sys.stderr)
        return 2
    caller, presence, step = sys.argv[1:]
    confirm_step.detect_agent = lambda *a, **k: CALLERS[caller]
    confirm_step.confirm_presence = lambda *a, **k: PRESENCE[presence]
    sys.argv = [str(confirm_step.__file__), step]
    return confirm_step.main()


if __name__ == "__main__":
    raise SystemExit(main())
