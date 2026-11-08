#!/usr/bin/env python3
"""Unified multi-step progress bar formatter and tracker (`T677`).

Provides deterministic ASCII/Unicode progress bars for multi-step CLI workflows
(`scripts/session_complete.py`, `scripts/run_suites.py`, `scripts/w0m_kb_vector.py`)
with elapsed time, percentage, and step labels that stream cleanly across both
interactive terminals and non-TTY background task logs.
"""

from __future__ import annotations

import sys
import time
from typing import TextIO


def format_duration(seconds: float) -> str:
    """Format seconds as `MM:SSs` (or `HH:MM:SSs` when >= 1 hour)."""
    sec = max(0, int(round(seconds)))
    mins, rem = divmod(sec, 60)
    hrs, mins = divmod(mins, 60)
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{rem:02d}s"
    return f"{mins:02d}:{rem:02d}s"


def format_progress_bar(
    current: int,
    total: int,
    label: str = "",
    *,
    width: int = 16,
    elapsed_sec: float | None = None,
    prefix: str = "",
) -> str:
    """Render a single-line progress bar: `[prefix] [ 3/13] [███░░░░░░░░░░░░░]  23% | 00:04s | label`."""
    safe_total = max(1, int(total))
    safe_current = max(0, min(int(current), safe_total))
    safe_width = max(4, int(width))

    ratio = safe_current / safe_total
    pct = int(round(ratio * 100))
    filled = int(round(ratio * safe_width))
    filled = max(0, min(filled, safe_width))
    bar = ("█" * filled) + ("░" * (safe_width - filled))

    digits = len(str(safe_total))
    counter = f"[{safe_current:>{digits}}/{safe_total}]"

    parts: list[str] = []
    if prefix:
        parts.append(prefix)
    parts.append(f"{counter} [{bar}] {pct:>3}%")
    if elapsed_sec is not None:
        parts.append(f"| {format_duration(elapsed_sec)}")
    if label:
        parts.append(f"| {label}")
    return " ".join(parts)


class StepProgress:
    """Stateful multi-step progress reporter writing to `stderr` by default."""

    def __init__(
        self,
        total: int,
        *,
        prefix: str = "",
        width: int = 16,
        stream: TextIO | None = None,
        enabled: bool = True,
    ) -> None:
        self.total = max(1, int(total))
        self.prefix = prefix
        self.width = width
        self.stream: TextIO = stream if stream is not None else sys.stderr
        self.enabled = enabled
        self.start_time = time.monotonic()
        self.current = 0

    def emit(self, current: int, label: str = "") -> str:
        """Update current step and print formatted progress bar line."""
        self.current = max(0, min(int(current), self.total))
        elapsed = time.monotonic() - self.start_time
        line = format_progress_bar(
            self.current,
            self.total,
            label,
            width=self.width,
            elapsed_sec=elapsed,
            prefix=self.prefix,
        )
        if self.enabled:
            print(line, file=self.stream, flush=True)
        return line

    def advance(self, label: str = "") -> str:
        """Increment current step by 1 and emit progress line."""
        return self.emit(self.current + 1, label)
