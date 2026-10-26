#!/usr/bin/env python3
"""T234 — verify the ai-memory checkout and binary are still the VALIDATED ones.

Owner decision 2026-08-19: *"let's embed ai-memory and stick to validated version, do not
auto-update it without revalidating changes"*.

A pin recorded in a file is a wish. This turns it into a check, and it deliberately verifies THREE
independent things, because each can drift without the others:

  · the checkout's commit      — someone ran `git pull` in _ext/ai-memory
  · the built binary's sha256  — the tree was rebuilt from different sources, or replaced outright
  · the reported version       — a prebuilt binary was dropped in from elsewhere

Checking only the commit would pass a checkout whose `target/release/ai-memory` came from anywhere
at all — which is the precise supply-chain risk (AgDR-0009) that made building from source the
condition of adoption in the first place.

⚠️ Upstream moves ~15 commits/day, so a RED here is expected and normal after any `git pull`. It is
not a defect report — it means the tree no longer matches what was validated, and the response is to
revalidate and move the pin, never to silence the check.

Exit 0 clean · 1 drift · 2 the pin or checkout is missing (never silently "clean").
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ESTATE = HERE.parent  # …/@wom
PIN = ESTATE / "w0m-web" / "project" / "ai-memory-pin.json"


def git(repo: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    except OSError:
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify the ai-memory checkout and binary match ai-memory-pin.json")
    ap.add_argument("--pin", type=Path, default=None, help="Path to ai-memory-pin.json")
    ap.add_argument("--estate", type=Path, default=None, help="Path to estate root")
    args = ap.parse_args(argv)

    pin_path = args.pin if args.pin is not None else PIN
    estate_root = args.estate if args.estate is not None else ESTATE

    if not pin_path.exists():
        print(f"  ❌ no pin file at {pin_path} — cannot verify anything. Not clean, unknown.")
        return 2
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    repo = estate_root / pin["checkout"]
    if not (repo / ".git").exists():
        print(f"  ❌ checkout missing at {repo} — the pin describes a tree that is not here.")
        return 2

    findings: list[str] = []

    head = git(repo, "rev-parse", "HEAD")
    if head != pin["commit"]:
        desc = git(repo, "describe", "--tags", "HEAD") or "?"
        findings.append(
            f"commit drift\n        validated {pin['commit'][:12]} ({pin['describe']})\n"
            f"        current   {(head or '?')[:12]} ({desc})"
        )

    binary = repo / "target" / "release" / "ai-memory"
    if not binary.exists():
        if (sys.platform != "darwin" or shutil.which("cargo") is None) and not findings:
            print(f"  ✅ ai-memory commit {(head or '')[:12]} matches pin (binary not built on {sys.platform})")
            return 0
        findings.append(f"the validated binary is absent ({binary.relative_to(estate_root)}) — rebuild before use")
    else:
        got = hashlib.sha256(binary.read_bytes()).hexdigest()
        if got != pin["binary_sha256"]:
            findings.append(
                f"binary drift\n        validated sha256 {pin['binary_sha256'][:16]}…\n"
                f"        on disk           {got[:16]}…"
            )
        out = subprocess.run([str(binary), "--version"], capture_output=True, text=True, check=False)
        rep = (out.stdout or out.stderr).strip()
        if pin["reported_version"] not in rep:
            findings.append(f"version drift — validated {pin['reported_version']}, binary reports {rep!r}")

    if not findings:
        print(f"  ✅ ai-memory matches the validated build — {pin['describe']} "
              f"({pin['commit'][:12]}), binary sha256 {pin['binary_sha256'][:12]}…, "
              f"validated {pin['validated_on']}")
        return 0

    print(f"  ❌ ai-memory has drifted from the validated build ({len(findings)} finding(s)):")
    for f in findings:
        print(f"      · {f}")
    print("\n  This is not a bug report — upstream moves ~15 commits/day. Either restore the pinned")
    print(f"  tree (`git -C {pin['checkout']} checkout {pin['freeze_tag']}` + rebuild), or REVALIDATE:")
    print("  rebuild, re-run what justified adoption, and update project/ai-memory-pin.json in the")
    print("  same commit. Do not edit the pin to match a tree nobody re-checked.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
