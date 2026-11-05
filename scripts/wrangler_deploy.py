#!/usr/bin/env python3
"""Execute `wrangler deploy` with bounded retry strictly on transient Cloudflare platform errors.

Why (2026-11-04, release 2026.11.04-1793813884, T639):
`deploy-cp` uploaded 70 static assets to Cloudflare Workers Assets, and Cloudflare's
`/accounts/.../workers/scripts/webomage-cp/versions` endpoint failed mid-flight so Wrangler's
internal retry replayed the single-use asset-upload completion JWT and exited 1 with:
  `Completion token has already been consumed [code: 100312]`
aborting `deploy-all` after `db-migrate`, `deploy-api`, `deploy-functions`, and `deploy-web`
had already shipped.

A fresh `wrangler deploy` invocation creates a new upload session (uploading 0 duplicate files
already cached at the edge) and obtains a fresh completion token.

Fail-closed contract (AgDR-0025):
- ONLY explicit transient Cloudflare upload/gateway/socket signatures trigger a retry.
- Authentication (`10000`), permission, invalid `wrangler.json`, missing binding, or bundle
  validation errors fail immediately on attempt 1 with the exact exit code.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import threading
import time
from typing import Any, Sequence

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_S = (4.0, 12.0)

TRANSIENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "cloudflare-100312-completion-token",
        re.compile(r"Completion token has already been consumed|\[code:\s*100312\]", re.IGNORECASE),
    ),
    (
        "cloudflare-5xx-gateway",
        re.compile(
            r"\b(?:502 Bad Gateway|503 Service Unavailable|504 Gateway Timeout|"
            r"Received a malformed response from the API.*status(?:\s+code)?\s*50[0234]|"
            r"A request to the Cloudflare API\b[\s\S]{0,240}\b(?:internal error|50[0234])\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "transient-network-socket",
        re.compile(
            r"\b(?:ECONNRESET|ETIMEDOUT|EAI_AGAIN|UND_ERR_CONNECT_TIMEOUT|UND_ERR_SOCKET|"
            r"socket hang up|TLS handshake timeout|fetch failed)\b",
            re.IGNORECASE,
        ),
    ),
)

NON_RETRYABLE_GUARD = re.compile(
    r"Authentication error|\[code:\s*10000\]|Invalid configuration|SyntaxError|ReferenceError",
    re.IGNORECASE,
)


def classify_transient_failure(output: str) -> str | None:
    """Return the matched transient reason slug if and only if output is safe to retry."""
    if NON_RETRYABLE_GUARD.search(output):
        return None
    for slug, pattern in TRANSIENT_PATTERNS:
        if pattern.search(output):
            return slug
    return None


def _stream_pipe(pipe: Any, sink: Any, chunks: list[str]) -> None:
    try:
        for line in iter(pipe.readline, ""):
            sink.write(line)
            sink.flush()
            chunks.append(line)
    finally:
        pipe.close()


def run_once(cmd: Sequence[str]) -> tuple[int, str]:
    """Run command once, streaming stdout/stderr live while capturing combined text."""
    proc = subprocess.Popen(
        list(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None and proc.stderr is not None
    captured: list[str] = []
    t_out = threading.Thread(target=_stream_pipe, args=(proc.stdout, sys.stdout, captured))
    t_err = threading.Thread(target=_stream_pipe, args=(proc.stderr, sys.stderr, captured))
    t_out.start()
    t_err.start()
    rc = proc.wait()
    t_out.join()
    t_err.join()
    return rc, "".join(captured)


def parse_backoff(raw: str) -> tuple[float, ...]:
    vals = [float(part.strip()) for part in raw.split(",") if part.strip()]
    return tuple(vals) if vals else DEFAULT_BACKOFF_S


def deploy_with_retry(
    cmd: Sequence[str],
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_s: Sequence[float] = DEFAULT_BACKOFF_S,
) -> int:
    if not cmd:
        print("wrangler_deploy.py: missing command after `--`", file=sys.stderr)
        return 2
    if max_attempts < 1:
        print("wrangler_deploy.py: --max-attempts must be >= 1", file=sys.stderr)
        return 2

    last_rc = 1
    for attempt in range(1, max_attempts + 1):
        rc, output = run_once(cmd)
        if rc == 0:
            if attempt > 1:
                print(f"  ✅ wrangler deploy succeeded on attempt {attempt}/{max_attempts}")
            return 0

        last_rc = rc
        reason = classify_transient_failure(output)
        if reason is None:
            return rc

        if attempt >= max_attempts:
            print(
                f"  ❌ wrangler deploy failed after {max_attempts} attempt(s) "
                f"(last transient signature: {reason}, exit {rc})",
                file=sys.stderr,
            )
            return rc

        delay = backoff_s[min(attempt - 1, len(backoff_s) - 1)] if backoff_s else 0.0
        print(
            f"  ↻ transient Cloudflare deploy failure ({reason}, exit {rc}) on attempt "
            f"{attempt}/{max_attempts}; retrying fresh session in {delay:g}s...",
            file=sys.stderr,
        )
        if delay > 0:
            time.sleep(delay)

    return last_rc


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if "--" in raw:
        idx = raw.index("--")
        wrapper_args, cmd = raw[:idx], raw[idx + 1 :]
    else:
        wrapper_args, cmd = [], raw

    parser = argparse.ArgumentParser(description="Bounded transient-error retry wrapper for wrangler deploy")
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument(
        "--backoff",
        default=",".join(str(x) for x in DEFAULT_BACKOFF_S),
        help="Comma-separated retry delays in seconds (default: 4.0,12.0)",
    )
    ns = parser.parse_args(wrapper_args)
    return deploy_with_retry(cmd, max_attempts=ns.max_attempts, backoff_s=parse_backoff(ns.backoff))


if __name__ == "__main__":
    raise SystemExit(main())
