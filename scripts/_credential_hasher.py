#!/usr/bin/env python3
"""Hash injected secrets and print DIGESTS ONLY. Runs as a child of `infisical run`.

🔴 THIS FILE EXISTS SO THE PARENT NEVER HOLDS A SECRET VALUE. Infisical has no digest endpoint —
its API returns `secretValue` in plaintext or omits it entirely — so proving two stores agree means
somebody hashes a value somewhere. Confining that to a short-lived child, whose entire stdout is
`NAME<TAB>digest`, is what keeps plaintext out of the snapshot process, its variables, its
exception messages and anything it writes.

⚠️ It prints a value NOWHERE. Not on success, not in an error, not in a traceback — every failure
path here names a KEY and never its content, because a traceback is the classic way a secret
reaches a log.

Invoked as:  infisical run --env=<env> --silent -- python3 scripts/_credential_hasher.py
with `_W0M_BASELINE` holding the parent's own environment keys, comma-separated.
"""
from __future__ import annotations

import hashlib
import os
import sys


def main() -> int:
    baseline = set(filter(None, os.environ.get("_W0M_BASELINE", "").split(",")))
    if not baseline:
        # 🔴 Without a baseline every ambient variable (PATH, HOME, SHELL) would be reported as an
        # injected secret. An empty baseline is a caller error, not an empty result.
        print("_ERROR\tno _W0M_BASELINE supplied — refusing to guess which vars are secrets",
              file=sys.stderr)
        return 2

    emitted = 0
    for key, value in sorted(os.environ.items()):
        if key in baseline or key == "_W0M_BASELINE":
            continue
        # ⚠️ Hash the exact bytes. No strip(), no normalisation: a trailing newline that differs
        # between two stores IS a drift, and quietly trimming it would hide the very thing this
        # phase looks for.
        print(f"{key}\t{hashlib.sha256(value.encode()).hexdigest()}")
        emitted += 1

    if emitted == 0:
        print("_ERROR\tinjection produced no new variables — treat as unreadable, not as empty",
              file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
