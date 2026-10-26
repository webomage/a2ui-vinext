#!/usr/bin/env python3
"""Measure what ZeroClaw's context compression actually costs and saves.

WHY THIS EXISTS
---------------
Headroom was adopted on a compression figure that turned out to be Anthropic's prompt-cache discount
re-badged; measured properly it saved **0 tokens**. The lesson was not "distrust that vendor" — it
was that a compression claim is only worth what an independent, before/after token count on a real
routed task says it is. ZeroClaw ships its own compression, so the same question applies to it, and
the same discipline answers it.

WHERE THE NUMBERS COME FROM — AND WHY NOT FROM ZEROCLAW
-------------------------------------------------------
`~/.omlx/stats.json`, the **model server's** own counters. That is ground truth for what reached the
model, and it is measured OUTSIDE the thing under test: a compressor cannot flatter itself in a
counter it does not own. ZeroClaw's `--session-state-file` was the obvious alternative and does not
carry usage; its single-shot `-m` mode keeps no history at all, so compression could never fire there.

🔴 `cached_tokens` IS REPORTED SEPARATELY, AND THAT IS THE WHOLE POINT.
oMLX caches prompt prefixes. A run that re-sends an identical prefix is cheap for reasons that have
NOTHING to do with compression, and adding those tokens to a "saved" column is precisely the mistake
that made Headroom's headline number meaningless. So this reports:

    prompt_tokens      everything the server was asked to process
    cached_tokens      the part served from prefix cache
    uncached_prompt    prompt - cached  ← the only column where compression can honestly show up

UNMEASURABLE IS NOT ZERO
------------------------
If the server is down, or its counters do not move, this exits non-zero and says so. It never prints
a 0 that could be read as "no change".

Usage:
    python3 zc_compression_measure.py --reps 2 --turns 7
    python3 zc_compression_measure.py --reps 1 --turns 5 --agent measure --profile measure
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

STATS = Path.home() / ".omlx" / "stats.json"      # lazily flushed — NOT used for counting
SERVER_LOG = Path.home() / ".omlx" / "logs" / "server.log"
GREEN, RED, YELLOW, DIM, BOLD, RESET = (
    ("\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m")
    if sys.stdout.isatty() else ("", "", "", "", "", "")
)
COUNTERS = ("prompt_tokens", "completion_tokens", "cached_tokens", "requests")


def run(*cmd: str, stdin: str | None = None, timeout: int = 2400) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True,
                          check=False, timeout=timeout)


def log_offset() -> int:
    """Byte offset of the server log, so a run reads only the lines IT produced."""
    try:
        return SERVER_LOG.stat().st_size
    except OSError:
        return 0


def completions_since(offset: int, model: str) -> list[dict[str, int]]:
    """Per-request {prompt, completion} parsed from the model server's own log.

    🔴 THIS REPLACED ~/.omlx/stats.json, WHICH LAGS AND SILENTLY LOST RUNS.
    Measured: a single curl moved that file's request counter from 67 to 85 — it had been holding 17
    requests from an earlier run unflushed. Before/after snapshots of a lazily-written counter
    attribute work to whichever run happens to trigger the flush, which is how two runs here reported
    "no requests" while their own logs showed the model answering. This log is written per request and
    was verified fresh to the second.

    Prompt LENGTH is also the better metric for this question than a cache-adjusted token count:
    it is what the model was asked to process, and unlike a cache-hit tally it cannot be inflated by
    prefix reuse — the exact confusion that made Headroom's headline number meaningless.
    """
    try:
        with SERVER_LOG.open("r", errors="replace") as fh:
            fh.seek(offset)
            text = fh.read()
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        if "Chat completion:" not in line or f"model={model}," not in line:
            continue
        m_c = re.search(r",\s*(\d+)\s+tokens in", line)
        m_p = re.search(r"prompt:\s*(\d+)", line)
        if m_c and m_p:
            out.append({"completion": int(m_c.group(1)), "prompt": int(m_p.group(1))})
    return out


def server_up() -> bool:
    r = run("curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
            "--max-time", "10", "http://127.0.0.1:8888/v1/models", timeout=20)
    return r.stdout.strip() == "200"


def cfg_get(path: str) -> str:
    return run("zeroclaw", "config", "get", path, timeout=60).stdout.strip()


def cfg_set(path: str, value: str) -> bool:
    return run("zeroclaw", "config", "set", path, value, timeout=60).returncode == 0


def set_compression(profile: str, on: bool) -> None:
    cfg_set(f"runtime_profiles.{profile}.compact_context", "true" if on else "false")
    cfg_set(f"runtime_profiles.{profile}.context_compression.enabled", "true" if on else "false")


def conversation(turns: int, filler_reps: int) -> str:
    """A fixed script. Identical between arms, so the only variable is compression."""
    filler = "The quick brown fox jumps over the lazy dog. " * filler_reps
    lines = [
        f"Answer in one short sentence only, do not use any tools. "
        f"Context block {i}: {filler} What number block was that?"
        for i in range(1, turns + 1)
    ]
    # 🔴 No trailing "exit". The agent reads it as a SHELL COMMAND and the approval gate rejects it,
    # which burns an extra model round and skews the arms against each other. Closing stdin ends the
    # session on its own.
    return "\n".join(lines) + "\n"


def one_run(agent: str, model: str, turns: int, filler_reps: int, workdir: Path) -> dict:
    offset = log_offset()
    with tempfile.TemporaryDirectory() as td:
        session = Path(td) / "session.json"
        t0 = time.time()
        proc = run("zeroclaw", "agent", "--agent", agent, "-v",
                   "--session-state-file", str(session),
                   stdin=conversation(turns, filler_reps))
        wall = time.time() - t0
        out = proc.stdout + proc.stderr
    calls = completions_since(offset, model)
    delta = {
        "prompt_tokens": sum(c["prompt"] for c in calls),
        "completion_tokens": sum(c["completion"] for c in calls),
        "cached_tokens": 0,
        "requests": len(calls),
    }
    # 🔴 A run that moved no counters did not measure zero — it measured nothing.
    #
    # And "nothing was measured" on its own is a dead end: the first version of this reported exactly
    # that and threw away the agent's output, so the run could not be diagnosed without repeating it.
    # An unmeasurable result has to carry its own evidence.
    if delta["requests"] <= 0:
        tail = "\n      ".join(
            l for l in (out.splitlines()[-6:] if out else []) if l.strip()
        ) or "(the agent produced no output at all)"
        return {"error": f"the model server logged no requests for {model} — nothing was measured.\n"
                         f"    agent exit={proc.returncode}, last output:\n      {tail}"}
    ctx = [int(m.replace(",", "")) for m in _ctx_values(out)]
    result: dict = dict(delta)
    result["max_prompt"] = max((c["prompt"] for c in calls), default=0)
    result["mean_prompt"] = round(delta["prompt_tokens"] / len(calls)) if calls else 0
    result["wall_s"] = round(wall, 1)
    result["ctx_peak"] = max(ctx) if ctx else None
    result["ctx_final"] = ctx[-1] if ctx else None
    # A drop in the reported context is the observable signature of history being reduced.
    result["ctx_dropped"] = bool(ctx and max(ctx) > ctx[-1])
    return result


def _ctx_values(text: str) -> list[str]:
    import re
    return re.findall(r"ctx:\s*([0-9,]+)\s*/", text)


def fmt(n: int | float | str | None) -> str:
    return f"{n:,}" if isinstance(n, int) else str(n)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", default="measure")
    ap.add_argument("--profile", default="measure")
    ap.add_argument("--model", default="gemma-4-e4b-it-4bit",
                    help="the per_model key in ~/.omlx/stats.json to read")
    ap.add_argument("--turns", type=int, default=7)
    ap.add_argument("--filler-reps", type=int, default=120)
    ap.add_argument("--reps", type=int, default=1, help="repetitions per arm; >1 shows variance")
    ap.add_argument("--settle", type=int, default=45,
                    help="seconds to let the model server settle between arms")
    args = ap.parse_args(argv)

    if not shutil.which("zeroclaw"):
        print(f"{RED}FAIL: zeroclaw is not on PATH{RESET}")
        return 2
    if not SERVER_LOG.is_file():
        print(f"{RED}FAIL: {SERVER_LOG} not found - is oMLX installed?{RESET}")
        return 2
    if not server_up():
        print(f"{RED}FAIL: the model server is not answering on 127.0.0.1:8888 - "
              f"`omlx start` first. Unmeasurable, not zero.{RESET}")
        return 2

    original = cfg_get(f"runtime_profiles.{args.profile}.compact_context")
    print(f"{DIM}agent={args.agent} profile={args.profile} model={args.model} "
          f"turns={args.turns} reps={args.reps}{RESET}")
    print(f"{DIM}restoring compact_context={original!r} when done{RESET}\n")

    results: dict[str, list[dict]] = {"off": [], "on": []}
    try:
        for rep in range(args.reps):
            for mode in ("off", "on"):
                set_compression(args.profile, mode == "on")
                # Let the model server settle between arms. Measured: a heavy run leaves it busy
                # enough that the next agent's provider call can time out and log no request at all,
                # which reads as a harness failure when it is really back-pressure.
                if results["off"] or results["on"]:
                    time.sleep(args.settle)
                print(f"{DIM}> rep {rep + 1}/{args.reps}  compression {mode.upper()}...{RESET}",
                      flush=True)
                r = one_run(args.agent, args.model, args.turns, args.filler_reps, Path.cwd())
                if "error" in r:
                    print(f"{RED}FAIL: {r['error']}{RESET}")
                    return 1
                results[mode].append(r)
                print(f"  prompt_total={fmt(r['prompt_tokens'])} mean/call={fmt(r['mean_prompt'])} "
                      f"max/call={fmt(r['max_prompt'])} out={fmt(r['completion_tokens'])} "
                      f"reqs={r['requests']} {r['wall_s']}s "
                      f"ctx_peak={fmt(r['ctx_peak'])} dropped={r['ctx_dropped']}")
    finally:
        set_compression(args.profile, original.strip().lower() == "true")

    print(f"\n{BOLD}RESULT{RESET}  (means over {args.reps} rep(s))")
    hdr = f"  {'':<18}{'OFF':>14}{'ON':>14}{'Δ':>14}"
    print(hdr); print("  " + "-" * (len(hdr) - 2))
    verdict_uncached = None
    for key in ("prompt_tokens", "mean_prompt", "max_prompt", "completion_tokens",
                "requests", "wall_s"):
        off = sum(r[key] for r in results["off"]) / len(results["off"])
        on = sum(r[key] for r in results["on"]) / len(results["on"])
        d = on - off
        mark = ""
        if key == "mean_prompt":
            verdict_uncached = d
            mark = f"  {DIM}← context actually sent per call{RESET}"
        print(f"  {key:<18}{off:>14,.0f}{on:>14,.0f}{d:>+14,.0f}{mark}")

    # 🔴 Per-rep, not any(). An earlier version printed "firing: yes" off a single rep while the
    # other never compressed at all — the two arms were then not comparable, and the mean hid it.
    n_fired = sum(1 for r in results["on"] if r["ctx_dropped"])
    n_on = len(results["on"])
    fired = n_fired > 0
    colour = GREEN if n_fired == n_on else YELLOW
    print(f"\n  compression observed firing: {colour}{n_fired}/{n_on} ON rep(s){RESET}")
    if 0 < n_fired < n_on:
        print(f"  {YELLOW}WARNING: MIXED ARMS - compression fired in only some ON reps, so the means above "
              f"average compressed and uncompressed runs together. Treat the deltas as "
              f"indicative only and raise --turns until it fires every time.{RESET}")
    if not fired:
        print(f"  {YELLOW}WARNING: with no observed firing, any difference above is run-to-run noise, "
              f"not compression. Raise --turns until it fires.{RESET}")
        return 0
    if verdict_uncached is not None and verdict_uncached >= 0:
        print(f"  {YELLOW}WARNING: compression fired and uncached prompt tokens did NOT fall. "
              f"It is costing tokens, not saving them.{RESET}")
    if args.reps < 2:
        print(f"  {DIM}note: one rep per arm - a model is nondeterministic; use --reps 3 "
              f"before believing a small delta.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
