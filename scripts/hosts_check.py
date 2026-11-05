#!/usr/bin/env python3
"""Check local domain resolution and /etc/hosts for *.w0m.local development domains."""

import sys
from pathlib import Path

REQUIRED_DOMAINS = [
    "w0m.local",
    "web.w0m.local",
    "cp.w0m.local",
    "admin.w0m.local",
    "me.w0m.local",
    "demo.w0m.local",
    "func.w0m.local",
]

HOSTS_PATH = Path("/etc/hosts")


def main() -> int:
    if not HOSTS_PATH.exists():
        print("❌ /etc/hosts not found!", file=sys.stderr)
        return 1

    content = HOSTS_PATH.read_text(encoding="utf-8", errors="ignore")
    words = set(content.split())

    missing = [d for d in REQUIRED_DOMAINS if d not in words]

    if not missing:
        print("✅ All local development domains are configured in /etc/hosts:")
        for d in REQUIRED_DOMAINS:
            print(f"  • {d} -> 127.0.0.1")
        return 0

    print("⚠️  The following local development domains are missing from /etc/hosts:")
    for d in missing:
        print(f"  ✗ {d}")

    entry_line = "127.0.0.1 " + " ".join(missing)
    print("\nTo configure them, run:")
    print(f'  sudo sh -c \'echo "{entry_line}" >> /etc/hosts\'')
    print("\nNote: *.localhost subdomains (e.g. web.localhost, cp.localhost) resolve natively without /etc/hosts.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
