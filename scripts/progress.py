#!/usr/bin/env python3
"""T507 — Clean, high-visibility progress bar utility for just recipes and deployment wrappers.

Usage from CLI:
    python3 scripts/progress.py --step 3 --total 8 --label "Building apps/cp"
    python3 scripts/progress.py --step 6 --total 6 --label "Complete" --elapsed 45.2

Usage from Python:
    from scripts.progress import ProgressBar
    pb = ProgressBar(total=8, title="Deploying Applications")
    pb.step("Building cp")
"""
from __future__ import annotations

import argparse
import os
import sys
import time


def supports_color() -> bool:
    """Return True if the current stdout stream supports ANSI colors."""
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def format_bar(
    step: int,
    total: int,
    label: str = "",
    width: int = 24,
    elapsed: float | None = None,
    color: bool = False,
) -> str:
    """Render a deterministic progress bar line."""
    step = max(0, min(step, total if total > 0 else 0))
    pct = int((step / total) * 100) if total > 0 else 100
    filled_len = int(width * step // total) if total > 0 else width
    empty_len = max(0, width - filled_len)

    filled = "█" * filled_len
    empty = "░" * empty_len

    time_str = f" ({elapsed:.1f}s)" if elapsed is not None and elapsed > 0 else ""

    if color:
        # Bold cyan step count, green filled bar, dim empty bar, bold white label
        step_part = f"\033[1;36m[{step:>2}/{total:<2}]\033[0m"
        bar_part = f"\033[32m{filled}\033[90m{empty}\033[0m"
        pct_part = f"\033[1;32m{pct:>3}%\033[0m"
        label_part = f"\033[1;37m{label}\033[0m{time_str}"
        return f"{step_part} [{bar_part}] {pct_part} | {label_part}"
    else:
        return f"[{step:>2}/{total:<2}] [{filled}{empty}] {pct:>3}% | {label}{time_str}"


class ProgressBar:
    """Interactive / programmatic step progress tracker."""

    def __init__(self, total: int, title: str = "", width: int = 24, stream=None):
        self.total = max(1, total)
        self.title = title
        self.width = width
        self.stream = stream or sys.stdout
        self.start_time = time.monotonic()
        self.last_step_time = self.start_time
        self.current = 0
        self.use_color = supports_color()

    def step(self, label: str = "") -> None:
        self.current += 1
        now = time.monotonic()
        step_elapsed = now - self.last_step_time
        self.last_step_time = now
        line = format_bar(
            self.current,
            self.total,
            label=label,
            width=self.width,
            elapsed=step_elapsed,
            color=self.use_color,
        )
        self.stream.write(f"\n▶ {line}\n")
        self.stream.flush()

    def finish(self, label: str = "Finished") -> None:
        total_elapsed = time.monotonic() - self.start_time
        line = format_bar(
            self.total,
            self.total,
            label=label,
            width=self.width,
            elapsed=total_elapsed,
            color=self.use_color,
        )
        self.stream.write(f"\n✅ {line}\n")
        self.stream.flush()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--step", type=int, required=True, help="current step number (1-indexed)")
    ap.add_argument("--total", type=int, required=True, help="total number of steps")
    ap.add_argument("--label", type=str, default="", help="action description / step label")
    ap.add_argument("--elapsed", type=float, default=None, help="optional elapsed seconds")
    ap.add_argument("--no-color", action="store_true", help="force disable ANSI color formatting")
    args = ap.parse_args()

    color = False if args.no_color else supports_color()
    rendered = format_bar(
        step=args.step,
        total=args.total,
        label=args.label,
        elapsed=args.elapsed,
        color=color,
    )
    print(rendered, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
