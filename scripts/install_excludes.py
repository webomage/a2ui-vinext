#!/usr/bin/env python3
"""Install this repo's nested-repo exclusions into .git/info/exclude (T294 AC2).

WHY NOT .gitignore
------------------
🔴 Because a directory pattern in a parent `.gitignore` is read by tools running BELOW it. Git stops
applying `.gitignore` at a repo root; osv-scanner does not. With `/wom7web/` in the estate
`.gitignore`, osv walked up from inside wom7web, applied the pattern, decided the entire repo was
ignored, and returned **exit 128 — "No package sources found" — in all seven repos at once.** One
line in a parent file silently disabled a security gate across the whole estate.

`.git/info/exclude` lives inside `.git/`, so nothing walking the worktree can see it. It is not
versioned, which is exactly why this script exists: the installer is the versioned surface, and
re-running it is what makes a fresh clone reproducible. `install_hooks.py` records the same reasoning
for `.git/hooks/`.

Run:  python3 scripts/install_excludes.py [--check]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARK = "# w0m: nested repos — installed by scripts/install_excludes.py"
NESTED = ["wom7api", "wom7authz", "wom7cfworkers", "wom7ext", "wom7mlx",
          "wom7sec", "wom7skills", "wom7web", "wom7open"]
BLOCK = "\n".join([MARK] + [f"/{n}/" for n in NESTED]) + "\n"


def main() -> int:
    exclude = ROOT / ".git" / "info" / "exclude"
    if not exclude.parent.exists():
        print(f"✗ {exclude.parent} missing — is this a git repo?")
        return 2
    current = exclude.read_text() if exclude.exists() else ""
    if MARK in current:
        missing = [n for n in NESTED if f"/{n}/" not in current]
        if "--check" in sys.argv:
            if missing:
                print(f"✗ exclude block is present but incomplete: {missing}")
                return 1
            print(f"✅ {len(NESTED)} nested repo(s) excluded via .git/info/exclude")
            return 0
        if missing:
            # Rebuild block
            idx = current.index(MARK)
            exclude.write_text(current[:idx].rstrip("\n") + "\n\n" + BLOCK)
            print(f"✅ updated .git/info/exclude with {len(NESTED)} nested repo(s)")
            return 0
        print("already installed — nothing to do")
        return 0
    if "--check" in sys.argv:
        print("✗ .git/info/exclude carries no w0m block — run without --check to install")
        return 1
    exclude.write_text(current.rstrip("\n") + "\n\n" + BLOCK if current.strip() else BLOCK)
    print(f"✅ excluded {len(NESTED)} nested repo(s) via .git/info/exclude")
    return 0


if __name__ == "__main__":
    sys.exit(main())
