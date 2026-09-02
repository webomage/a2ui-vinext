#!/usr/bin/env python3
"""Conventional Commits, matching the other w0m repos so one habit works everywhere."""
import re
import sys
from pathlib import Path

msg = Path(sys.argv[1]).read_text().strip().splitlines()
subject = msg[0] if msg else ""
if subject.startswith(("Merge ", "Revert ", "fixup!", "squash!")):
    sys.exit(0)
if not re.match(r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^)]+\))?!?: .+",
                subject):
    print(f"✗ not a Conventional Commit subject:\n    {subject[:100]}")
    print("  expected: type(scope): description   e.g. `docs(estate): record the workspace adoption`")
    sys.exit(1)
