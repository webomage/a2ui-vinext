#!/usr/bin/env python3
"""Unit & PTY probes for _read_masked_password in scripts/confirm_step.py (T584 AC1)."""

from __future__ import annotations

import os
import pty
import select
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import confirm_step as gate  # noqa: E402


def _drive_masked_pty(keystrokes: bytes, prompt: str = "   [confirm] sudo password for aleksei: ") -> tuple[str | None, str]:
    master, slave = pty.openpty()
    result: list[str | None] = []
    errors: list[BaseException] = []

    def _reader() -> None:
        try:
            pw = gate._read_masked_password(prompt, tty_fd=slave, timeout=5.0)
            result.append(pw)
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    th = threading.Thread(target=_reader, daemon=True)
    th.start()
    try:
        echoed = bytearray()
        # Wait until the prompt is printed (after ECHO has been disabled via tcsetattr)
        while b": " not in echoed:
            if select.select([master], [], [], 2.0)[0]:
                chunk = os.read(master, 1024)
                if not chunk:
                    break
                echoed.extend(chunk)
            else:
                break
        os.write(master, keystrokes)
        th.join(timeout=5.0)
        while select.select([master], [], [], 0.05)[0]:
            try:
                chunk = os.read(master, 1024)
                if not chunk:
                    break
                echoed.extend(chunk)
            except OSError:
                break
    finally:
        os.close(slave)
        os.close(master)

    if errors:
        raise errors[0]
    return (result[0] if result else None), echoed.decode("utf-8", "replace")


def test_masked_password_echoes_asterisks_not_cleartext() -> None:
    pw, echoed = _drive_masked_pty(b"s3cret\r")
    assert pw == "s3cret", f"expected 's3cret', got {pw!r}"
    assert "******" in echoed, f"expected 6 asterisks in echoed output, got {echoed!r}"
    assert "s3cret" not in echoed, f"cleartext password leaked in echoed output: {echoed!r}"


def test_masked_password_handles_backspace() -> None:
    pw, echoed = _drive_masked_pty(b"oiux\x7f\r")
    assert pw == "oiu", f"expected 'oiu', got {pw!r}"
    assert "****\b \b" in echoed, f"expected backspace erase sequence in echoed output, got {echoed!r}"
    assert "oiu" not in echoed


def test_masked_password_handles_ctrl_u_clear_line() -> None:
    pw, echoed = _drive_masked_pty(b"wrong\x15right\n")
    assert pw == "right", f"expected 'right', got {pw!r}"
    assert "\b \b" * 5 in echoed, f"expected 5 backspace erases on Ctrl+U, got {echoed!r}"
    assert "wrong" not in echoed and "right" not in echoed


def test_masked_password_handles_ctrl_c_cancel() -> None:
    pw, echoed = _drive_masked_pty(b"abc\x03")
    assert pw is None, f"expected None on Ctrl+C, got {pw!r}"
    assert "***" in echoed
    assert "abc" not in echoed


def test_masked_password_handles_utf8_characters() -> None:
    pw, echoed = _drive_masked_pty("päss\r".encode("utf-8"))
    assert pw == "päss", f"expected 'päss', got {pw!r}"
    assert "****" in echoed, f"expected 4 asterisks for 4 code points, got {echoed!r}"
    assert "päss" not in echoed


def main() -> int:
    tests = [
        test_masked_password_echoes_asterisks_not_cleartext,
        test_masked_password_handles_backspace,
        test_masked_password_handles_ctrl_u_clear_line,
        test_masked_password_handles_ctrl_c_cancel,
        test_masked_password_handles_utf8_characters,
    ]
    for fn in tests:
        fn()
        print(f"  ✅ {fn.__name__}")
    print(f"\n✅ confirm-step-masked-password: {len(tests)}/{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
