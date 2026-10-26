#!/usr/bin/env python3
"""w0m identity gate — refuse to push w0m work under the wrong GitHub identity.

WHY THIS EXISTS
    This machine hosts two GitHub identities: `casualuser` (the w0m institutional
    persona) and `Shinagawa-monkey` (Elena, on the evercred project). They are
    separated by directory-scoped git config (`includeIf` in ~/.gitconfig →
    ~/.gitconfig-wom / ~/.gitconfig-evercred), which handles user.email and the
    SSH key correctly and automatically.

    What that does NOT cover is the `gh` CLI: its active account is a single
    GLOBAL setting, so it flips as a matter of course when work moves between the
    w0m repos and Elena's evercred project. This is expected, not a malfunction —
    the point of the gate is that the flip is caught at the moment it would matter,
    since a flipped account makes the ticket-sync and board scripts operate as — or
    403 against — the wrong user, silently. Recover with `just gh-w0m`.

    So: git/ssh identity is enforced by config, and this gate is the check that
    the config actually took effect, plus the only real guard on `gh`.

DESIGN NOTES
    - Offline. Reads ~/.config/gh/hosts.yml directly rather than shelling out to
      `gh auth status`, which makes a network round-trip to validate the token.
    - Blocks on what it can prove (wrong email, wrong gh account); advisory on
      what it cannot (gh not installed, no gh config in this clone).
    - Repo-agnostic: run from any w0m repo.

Usage:  python3 scripts/check_git_identity.py   (exit 1 = blocked)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

EXPECTED_EMAIL = "casualuser@gmail.com"
EXPECTED_GH_USER = "casualuser"
EXPECTED_SSH_KEY = "id_rsa"  # registered on casualuser as 'proto@localhost'

# Honor GH_CONFIG_DIR so the gate validates the SAME config `gh` will actually use. w0m scopes
# gh to a dedicated dir (see the justfile / pre-push hook), which is how account selection is
# made deterministic rather than inherited from the global active account.
_GH_DIR = os.environ.get("GH_CONFIG_DIR") or str(Path.home() / ".config" / "gh")
GH_HOSTS = Path(_GH_DIR) / "hosts.yml"


def git(*args: str) -> str:
    """Read a git config value; '' when unset."""
    res = subprocess.run(["git", *args], capture_output=True, text=True)
    return res.stdout.strip() if res.returncode == 0 else ""


def gh_active_user() -> str | None:
    """Active gh account for github.com, read locally. None when undeterminable.

    hosts.yml nests a `users:` map and a top-level `user:` key under the host;
    we want the latter. Matching on indentation distinguishes them without a
    YAML dependency (this runs in a hook — no third-party imports).
    """
    if not GH_HOSTS.is_file():
        return None
    for line in GH_HOSTS.read_text().splitlines():
        m = re.match(r"^\s{4}user:\s*(\S+)\s*$", line)
        if m:
            return m.group(1)
    return None


def main() -> int:
    problems: list[str] = []
    notes: list[str] = []

    email = git("config", "user.email")
    if email != EXPECTED_EMAIL:
        problems.append(
            f"git user.email is {email or '(unset)'} — expected {EXPECTED_EMAIL}.\n"
            f"     The ~/.gitconfig includeIf for @wom is missing or not matching this path."
        )

    ssh_cmd = git("config", "core.sshCommand")
    if EXPECTED_SSH_KEY not in ssh_cmd:
        notes.append(
            f"core.sshCommand does not pin {EXPECTED_SSH_KEY} (got: {ssh_cmd or 'unset'}). "
            f"SSH will fall back to default key order."
        )

    # GITHUB_TOKEN OVERRIDES the keyring: when it is set, gh authenticates as whoever owns the
    # token and ignores the active account entirely. A gate that only read hosts.yml would happily
    # report "casualuser" while every gh call acted as somebody else. Check it explicitly.
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        who = subprocess.run(["gh", "api", "user", "--jq", ".login"],
                             capture_output=True, text=True)
        actual = who.stdout.strip() if who.returncode == 0 else None
        if actual and actual != EXPECTED_GH_USER:
            problems.append(
                f"GITHUB_TOKEN is set and belongs to '{actual}', not '{EXPECTED_GH_USER}'.\n"
                f"     It OVERRIDES the gh account, so switching accounts will not help.\n"
                f"     Fix: unset GITHUB_TOKEN (or correct it in the secret store)."
            )
        elif actual:
            notes.append(f"GITHUB_TOKEN is set and overrides the keyring; it belongs to "
                         f"'{actual}' (correct), so gh calls act as w0m regardless of the "
                         f"active account.")

    gh_user = gh_active_user()
    if gh_user is None:
        notes.append("gh config not found — skipping the gh account check.")
    elif gh_user != EXPECTED_GH_USER:
        problems.append(
            f"gh active account is '{gh_user}' — expected '{EXPECTED_GH_USER}'.\n"
            f"     Fix:  just gh-w0m   (or: gh auth switch --hostname github.com "
            f"--user {EXPECTED_GH_USER})"
        )

    for n in notes:
        print(f"  ⚠  identity: {n}")

    if problems:
        print("❌ w0m identity gate — this push would use the wrong identity:")
        for p in problems:
            print(f"  ✗  {p}")
        print("\n   w0m work must be pushed as casualuser. Elena's evercred project")
        print("   is scoped separately and is unaffected by fixing this.")
        return 1

    print(f"  ✓ identity: {EXPECTED_EMAIL} / gh:{gh_user or 'n-a'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
