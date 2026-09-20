#!/usr/bin/env python3
"""Refuse to commit a file belonging to one of the nested repos (T294 AC2).

The estate is a workspace of seven INDEPENDENT repos plus a fork container. `.gitignore` keeps them
out of this repo, and `git add -A` staging none of them was proven once at adoption — but that proof
expires the moment an ignore rule is loosened or a path is force-added. This hook is the standing
version of that check.

Why not trust .gitignore alone: `git add -f` bypasses it silently, and a broadened pattern is a
one-character edit. The consequence is not cosmetic — a repo swept in here would carry a second,
diverging copy of files whose real home has its own history, remote and hooks.
"""
import sys
from pathlib import Path

NESTED = {"wom7api", "wom7authz", "wom7ava", "wom7func", "wom7ext", "wom7mlx",
          "wom7sec", "wom7skills", "wom7web", "wom7pr", "wom7clips", "k7"}

bad = [f for f in sys.argv[1:] if Path(f).parts and Path(f).parts[0] in NESTED]
if bad:
    print("✗ these belong to a nested repo and must be committed there, not here:")
    for f in bad[:10]:
        print(f"    {f}")
    print("  The estate is a workspace of independent repos — this one holds only what sits BESIDE")
    print("  them. If an ignore rule was loosened, fix the rule rather than the symptom.")
    sys.exit(1)
