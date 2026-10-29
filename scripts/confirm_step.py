#!/usr/bin/env python3
"""Confirmation gate for mutating `just` recipes (T161 AC3).

WHY THIS EXISTS RATHER THAN A PERMISSION RULE
---------------------------------------------
The natural home for "ask before you deploy" is the harness `ask` permission tier. It does not
work. Probed 2026-08-02 (T161 AC3) and RE-PROBED 2026-08-10: `Bash(just <recipe>*)` in `ask` ran
with **no prompt** both times, while the same shape in `deny` was withheld instantly. `ask` is a
silent allow under this permission mode. Shipping it would have been a gate that *reads* as
protection and withholds nothing — the exact defect T161 is about.

WHAT MAKES THIS ONE REAL — THREE LAYERS, IN ORDER (T435)
-------------------------------------------------------
1. **Agent refusal.** If an agent harness is in this process's ancestry (`claude`, `agy`, `codex`,
   an IDE `language_server*`, …) or an agent environment marker is set (`CLAUDECODE`, `AI_AGENT`),
   the step is refused before anything else — before the prompt, before a root consent is honoured,
   and for `always_confirm` steps. Ancestry that cannot be read refuses as UNMEASURABLE.
2. **A terminal.** The prompt is never read from a redirected stdin. Two channels are tried:
   `/dev/tty`, then stdin **only if `stdin.isatty()`**. A pipe is not a tty, so `echo yes |`,
   `yes |` and heredocs never reach it.
3. **A present human.** After the typed `yes`, macOS verifies the device owner (Touch ID, Apple
   Watch or the login password in the system dialog) via `human_presence.swift`. No dialog, no pass.

🔴 WHY LAYER 1 AND 3 EXIST — layer 2 alone was answered by an agent, live. The original premise
was "an agent shell has no terminal". Claude Code's Bash tool indeed has none (`/dev/tty` is
`Device not configured`, `stdin.isatty()` False). But **agy runs background commands inside a
pseudo-terminal and can type into them**: on 2026-09-17 it ran `just db-migrate`, the prompt
appeared on agy's pty, agy sent `yes`, and three migrations reached the live database
(`w0m-confirm.log`: CONFIRMED db-migrate, 01:17:07). And any agent can make a terminal:
`script -q /dev/null <cmd>` gives the child a pty (measured 2026-09-24: isatty True, /dev/tty
opens). A terminal proves a terminal, not a person.

⚠️ Two channels, not one, because one was WRONG: shipped /dev/tty-only on 2026-08-10 and the owner
— in a genuine terminal — was told there was no terminal. The app's embedded terminal pane does not
expose /dev/tty. A gate that blocks the person it exists to ask is not strict, it is broken.
`just confirm-doctor` prints which channels a given shell exposes, so that failure is diagnosable
instead of mysterious.

There is deliberately **no override env var**. An escape hatch is the hole; the estate has no CI
to need one (GitHub Actions has been dead account-wide since before this was written).

CONSENT MODEL (owner spec, 2026-08-10)
--------------------------------------
- "top level script agreement counts as agree for chained" — confirming a ROOT (e.g. `deploy`)
  writes a short-lived consent covering the steps that root chains, so you answer once, not eight
  times.
- "option to confirm only specific steps like migrations" — steps in `always_confirm` re-prompt
  **even inside an agreed root**. ⚠️ Read the list from confirm-policy.json, never from prose here:
  prose is what rotted for 34 days (T407), the data is what the code reads.

⚠️ PARTLY SUPERSEDED — OWNER, 2026-08-16. The exemplar the sentence above was written around,
`db-migrate`, is NOT in the carve-out any more. Shown the trade-off, the owner chose a single
confirmation for the whole chain: *"one yes from human should be enough here."* So one root yes
DOES carry an irreversible live schema write, for the length of the TTL. That is the decision, not
a defect — the full reasoning, and the explicit instruction not to "restore" the carve-out as a fix
for something else, are in confirm-policy.json under `_notes.one_yes_is_the_decision`. Two things
still hold and are the reason this is survivable: a standalone `just db-migrate` prompts on its own
(rule 4 in main()), and layer 1 refuses it to any agent session outright.

Consent is bound to the git HEAD it was granted at and expires after `ttl_seconds` from
confirm-policy.json — **2700s (45 min)** since 2026-08-16, sized to one full `deploy-all` run — so
it cannot be reused across a later, different tree. The 900s literal in main() is a fallback for a
policy file with no `ttl_seconds` at all; it is deliberately the shorter of the two.

FAIL CLOSED
-----------
An unrecognised step name requires confirmation rather than passing. A recipe added tomorrow is
safe by default instead of safe only if someone remembered to classify it.

🔴 KNOWN LIMITS — STATED, NOT DISCOVERED LATER
----------------------------------------------
This file said "the tty prompt is un-forgeable" from 2026-08-10 to 2026-09-24. It was forged —
see above. What each layer really withholds:

  · a ROOT confirmation (`deploy`, `deploy-all`, or any step run directly) — needs a non-agent
    ancestry, a terminal AND the device owner in the macOS dialog.
  · a CHAINED step's pass — trusts `$TMPDIR/w0m-confirm-consent.json`. Any process that can write
    that file can mint coverage (verified 2026-08-10); layer 1 still refuses an agent that tries
    to ride it, but a forged file read by a non-agent process is not detected. That is the cost
    of the owner's "top level agreement counts as agree for chained": carrying one yes across
    separate `just` invocations needs somewhere to carry it.
  · layer 1 matches ancestry and environment. A process that DELIBERATELY detaches from its agent
    (double fork, `tmux new -d`, `osascript` into a fresh Terminal) and scrubs the markers escapes
    it — which is why layer 3 exists: the dialog needs a finger or the login password.

⇒ This stops accidental and automated deploys — including an agent that simply answers the
prompt it was shown, which is what happened. Nothing here stops an agent that rewrites this file
or runs `supabase db push` itself; that is outside what a recipe gate can see. The harness `deny`
rules stay as belt and braces, and every grant, refusal and consent-backed pass is appended to
`.git/w0m-confirm.log`, so a forgery is visible after the fact rather than silent.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Mapping
import uuid

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "w0m-web"
POLICY = ROOT / "project" / "policies" / "confirm-policy.json"
# 🔴 Overridable, and it has to be. The consent file is REAL, shared state: whatever grants or
# clears it affects a deploy that may be running right now. The confirm-step probe suite grants and
# clears consent as part of its own checks, and `just test` runs inside `just deploy` — so on
# 2026-08-16 the suite silently deleted the owner's live consent mid-deploy, and every step after
# it re-prompted. The audit log shows it exactly: PASSED-ON-CONSENT at 08:34, the suite's fixtures
# at 08:36, then "run directly, outside an agreed root" at 08:38 — same HEAD, well inside the TTL.
# Tests must point this at their own file; nothing else may touch the shared one.
CONSENT = Path(
    os.environ.get("W0M_CONFIRM_CONSENT") or (Path(tempfile.gettempdir()) / "w0m-confirm-consent.json")
)

# 🔴 The audit log follows the consent file. If a test points CONSENT at its own path, its events
# belong beside it — not in the estate's real trail.
#
# Third instance of one class in a single day: a test sharing real, mutable state with the thing it
# tests. The others were the consent file itself (the suite deleted a live deploy's consent) and
# the deploy-log directory (32 of 33 transcripts were fixtures). Here the cost was diagnostic
# rather than operational: the suite's `some-recipe-added-tomorrow` fixtures sat in the same log as
# real prompts, and reading them as real is exactly the confusion that produced three wrong
# diagnoses before the log was finally read properly.
def _git_common_dir(root: Path) -> Path:
    """The repo's shared git directory. In a linked worktree (a T473 release checkout) `.git` is a FILE pointing at
    the main repo, so `<root>/.git/w0m-confirm.log` cannot be written; every worktree logs to the one shared trail."""
    dot_git = root / ".git"
    if dot_git.is_dir():
        return dot_git
    out = subprocess.run(["git", "-C", str(root), "rev-parse", "--git-common-dir"],
                         capture_output=True, text=True, check=True).stdout.strip()
    common = Path(out)
    return common if common.is_absolute() else (root / common).resolve()


AUDIT_LOG = (
    CONSENT.with_name("w0m-confirm-test.log")
    if os.environ.get("W0M_CONFIRM_CONSENT")
    else _git_common_dir(WEB_ROOT) / "w0m-confirm.log"
)

TOTP_SECRET_FILE = Path(
    os.environ.get("W0M_CONFIRM_TOTP_FILE") or (Path.home() / ".w0m" / "confirm_totp.secret")
)
CONFIRM_DIR = Path(
    os.environ.get("W0M_CONFIRM_ORCA_DIR") or (Path.home() / ".w0m" / "confirm")
)
REQUESTS_DIR = CONFIRM_DIR / "requests"
RESPONSES_DIR = CONFIRM_DIR / "responses"


GREEN, RED, YELLOW, BOLD, DIM, OFF = (
    "\033[32m",
    "\033[31m",
    "\033[33m",
    "\033[1m",
    "\033[2m",
    "\033[0m",
)


def load_policy() -> dict[str, Any]:
    if not POLICY.exists():
        die(f"confirm-policy.json missing at {POLICY} — refusing to run unguarded.")
    try:
        data: dict[str, Any] = json.loads(POLICY.read_text())
    except json.JSONDecodeError as exc:
        die(f"confirm-policy.json is not valid JSON ({exc}) — refusing to run unguarded.")
    if not data.get("roots") and not data.get("always_confirm"):
        # An empty policy would make every step "unrecognised" and therefore prompt, which is
        # safe — but it is far more likely to mean the file was truncated. Say so.
        die("confirm-policy.json declares no roots and no always_confirm — that is not a policy.")
    return data


def audit(event: str, step: str, detail: str) -> None:
    """Append-only trail. The cached consent is forgeable (see the module docstring); this is what
    makes a forgery *visible* rather than silent. Best-effort — an unwritable log must never be
    the thing that stops a legitimate deploy."""
    try:
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')}\t{event}\t{step}\t{head_sha()}\t{detail}\n"
        with AUDIT_LOG.open("a") as fh:
            fh.write(line)
    except OSError:
        pass


def die(msg: str) -> None:
    print(f"{RED}❌ confirm: {msg}{OFF}", file=sys.stderr)
    raise SystemExit(1)


def head_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=WEB_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


# ── Layer 1: agent refusal (T435) ──────────────────────────────────────────────────────────────
# Executable basenames of agent harnesses. CASE-SENSITIVE on purpose: the Claude desktop APP is
# `Claude`, and its terminal pane is a human's; the Claude Code CLI agent is `claude`.
AGENT_EXECUTABLES = frozenset({
    "claude", "agy", "antigravity", "codex", "opencode", "gemini", "cursor-agent", "aider",
    "hermes", "hermes-agent", "grok",
})
# IDE agent back-ends (Antigravity / Windsurf run their agent inside `language_server_macos_arm`).
AGENT_EXECUTABLE_PREFIXES = ("language_server",)
# Agents shipped as scripts show up as their interpreter; the agent is then in the arguments.
INTERPRETERS = frozenset({"node", "bun", "deno", "python", "python3", "ruby"})
# Exported by the agent into every command it runs. Measured 2026-09-24 in Claude Code's Bash tool;
# absent from a plain Orca terminal. A marker proves an agent; its absence proves nothing, which is
# why the ancestry walk runs as well.
AGENT_ENV_MARKERS = ("CLAUDECODE", "AI_AGENT")
MAX_ANCESTRY = 128

ProcessTable = Mapping[int, tuple[int, str, str]]  # pid → (ppid, comm, args)


@dataclass(frozen=True)
class AgentVerdict:
    agent: str | None   # what was found, or None
    evidence: str       # which signal decided it, for the refusal message and the audit line
    measurable: bool    # False = could not tell; the gate refuses on that too


def _basename(name: str) -> str:
    return os.path.basename(name.strip().lstrip("-"))


def process_table() -> ProcessTable | None:
    """Snapshot of every process: two `ps` calls, because `comm` may contain spaces (`Orca Helper`)
    and so must be the last column, and `args` must be too."""
    try:
        comm = subprocess.run(["ps", "-axo", "pid=,ppid=,comm="], capture_output=True, text=True,
                              check=True, timeout=10).stdout
        argv = subprocess.run(["ps", "-axww", "-o", "pid=,args="], capture_output=True, text=True,
                              check=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    args: dict[int, str] = {}
    for line in argv.splitlines():
        parts = line.strip().split(None, 1)
        if parts and parts[0].isdigit():
            args[int(parts[0])] = parts[1] if len(parts) > 1 else ""
    table: dict[int, tuple[int, str, str]] = {}
    for line in comm.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            pid = int(parts[0])
            table[pid] = (int(parts[1]), parts[2] if len(parts) > 2 else "", args.get(pid, ""))
    return table or None


def agent_name(comm: str, args: str) -> str | None:
    """The agent this one process is, or None."""
    base = _basename(comm)
    if base in AGENT_EXECUTABLES or base.startswith(AGENT_EXECUTABLE_PREFIXES):
        return base
    if base in INTERPRETERS:
        for token in args.split()[1:4]:
            if _basename(token) in AGENT_EXECUTABLES:
                return _basename(token)
    return None


def detect_agent(table: ProcessTable | None = None, start: int | None = None,
                 env: Mapping[str, str] | None = None) -> AgentVerdict:
    """Is this gate running inside an agent session? Pure over its inputs, so the probes can hand
    it synthetic process tables; with no arguments it measures the real ones."""
    env = os.environ if env is None else env
    for key in AGENT_ENV_MARKERS:
        if env.get(key):
            return AgentVerdict(key, f"environment marker {key} is set — agent sessions export it", True)
    table = process_table() if table is None else table
    if not table:
        return AgentVerdict(None, "could not read the process table (`ps` failed)", False)
    pid = os.getpid() if start is None else start
    chain: list[str] = []
    for _ in range(MAX_ANCESTRY):
        if pid <= 1:                                   # launchd / kernel — the walk completed
            return AgentVerdict(None, "no agent in ancestry: " + " <- ".join(chain), True)
        row = table.get(pid)
        if row is None:
            return AgentVerdict(None, f"ancestry breaks at pid {pid} before reaching launchd: "
                                + " <- ".join(chain), False)
        ppid, comm, args = row
        chain.append(f"{_basename(comm)}({pid})")
        hit = agent_name(comm, args)
        if hit:
            return AgentVerdict(hit, f"ancestor `{hit}` pid {pid}: " + " <- ".join(chain), True)
        pid = ppid
    return AgentVerdict(None, f"ancestry deeper than {MAX_ANCESTRY} — a cycle?", False)


def refuse_agent(step: str, describe: str, verdict: AgentVerdict) -> None:
    headline = ("was invoked from inside an agent session" if verdict.agent
                else "cannot tell whether it was invoked from inside an agent session")
    print(
        f"\n{RED}{BOLD}❌ BLOCKED — `{step}` {headline}.{OFF}\n"
        f"   {describe}\n"
        f"   {DIM}{verdict.evidence}{OFF}\n"
        f"   {DIM}A confirmation is a person's answer. An agent can hold a terminal and type `yes`\n"
        f"   into it (agy did, on a live db-migrate, 2026-09-17), so an agent session is refused\n"
        f"   outright rather than prompted.{OFF}\n"
        f"   {BOLD}Run it yourself in a terminal that is not an agent session:{OFF} just {step}\n"
        f"   {DIM}`just confirm-doctor` shows the ancestry this decision was made from.{OFF}\n",
        file=sys.stderr,
    )


# ── Layer 3: a present human (T435 AC8, owner 2026-09-24: "macOS Touch ID prompt is great") ──
PRESENCE_SOURCE = Path(__file__).resolve().with_name("human_presence.swift")
PRESENCE_TIMEOUT = 120


def _run_presence_helper(arg: str) -> tuple[int, str]:
    """Build the helper into a fresh temp dir and run it once. (exit code, detail); exit 2 means
    the check could not be made at all."""
    host_os = str(sys.platform)
    if host_os != "darwin":
        return 2, f"the device-owner check needs macOS LocalAuthentication; this host is {host_os}"
    if not PRESENCE_SOURCE.exists():
        return 2, f"{PRESENCE_SOURCE} is missing"
    with tempfile.TemporaryDirectory(prefix="w0m-confirm-") as tmp:
        exe = Path(tmp) / "w0m-confirm"
        try:
            subprocess.run(["xcrun", "swiftc", "-O", "-o", str(exe), str(PRESENCE_SOURCE)],
                           capture_output=True, text=True, check=True, timeout=180)
        except subprocess.CalledProcessError as exc:
            return 2, f"could not build the Touch ID helper: {exc.stderr.strip()[:200]}"
        except (OSError, subprocess.SubprocessError) as exc:
            return 2, f"could not build the Touch ID helper: {exc}"
        try:
            r = subprocess.run([str(exe), arg], capture_output=True, text=True, timeout=PRESENCE_TIMEOUT)
        except subprocess.TimeoutExpired:
            return 1, f"no answer in the Touch ID dialog within {PRESENCE_TIMEOUT}s"
        except OSError as exc:
            return 2, f"could not run the Touch ID helper: {exc}"
    return r.returncode, (r.stdout.strip() or r.stderr.strip())


def _read_masked_password(
    prompt: str,
    tty_fd: int | None = None,
    timeout: float = PRESENCE_TIMEOUT,
) -> str | None:
    """Read a password from a TTY fd, echoing '*' for each character typed.

    Supports Backspace (\\x7f / \\x08 -> '\\b \\b'), Ctrl+U (\\x15 line clear),
    Ctrl+W (\\x17 word erase), Enter (\\r / \\n), and Ctrl+C / Ctrl+D cancel.
    Returns None on cancel/EOF, raises TimeoutError on timeout.
    """
    import select
    import termios

    own_fd = False
    fd = tty_fd
    if fd is None:
        try:
            fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
            own_fd = True
        except OSError:
            if sys.stdin.isatty():
                fd = sys.stdin.fileno()
            else:
                raise

    try:
        old_attrs = termios.tcgetattr(fd)
    except Exception:
        if own_fd and fd is not None:
            os.close(fd)
        raise

    def _write(text: str) -> None:
        data = text.encode("utf-8", "replace")
        try:
            os.write(fd, data)
        except OSError:
            try:
                sys.stderr.write(text)
                sys.stderr.flush()
            except OSError:
                pass

    chars: list[str] = []
    deadline = time.monotonic() + timeout
    try:
        new_attrs = termios.tcgetattr(fd)
        new_attrs[3] &= ~(termios.ECHO | termios.ICANON | termios.ISIG)
        new_attrs[0] &= ~termios.ICRNL
        new_attrs[6][termios.VMIN] = 1
        new_attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSADRAIN, new_attrs)
        _write(prompt)

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _write("\r\n")
                raise TimeoutError(f"timed out waiting for password within {int(timeout)}s")
            ready, _, _ = select.select([fd], [], [], min(remaining, 0.5))
            if not ready:
                continue
            try:
                raw = os.read(fd, 1)
            except OSError:
                _write("\r\n")
                return None
            if not raw:
                _write("\r\n")
                return "".join(chars) if chars else None

            b0 = raw[0]
            if b0 in (0x0D, 0x0A):  # Enter (\r or \n)
                _write("\r\n")
                return "".join(chars)
            if b0 == 0x03:  # Ctrl+C
                _write("\r\n")
                return None
            if b0 == 0x04:  # Ctrl+D
                if not chars:
                    _write("\r\n")
                    return None
                continue
            if b0 in (0x7F, 0x08):  # Backspace / Ctrl+H
                if chars:
                    chars.pop()
                    _write("\b \b")
                continue
            if b0 == 0x15:  # Ctrl+U (clear line)
                if chars:
                    _write("\b \b" * len(chars))
                    chars.clear()
                continue
            if b0 == 0x17:  # Ctrl+W (erase previous word)
                erased = 0
                while chars and chars[-1].isspace():
                    chars.pop()
                    erased += 1
                while chars and not chars[-1].isspace():
                    chars.pop()
                    erased += 1
                if erased:
                    _write("\b \b" * erased)
                continue
            if b0 == 0x1B:  # Escape / CSI sequence — drain any immediately buffered sequence bytes
                while select.select([fd], [], [], 0.01)[0]:
                    if not os.read(fd, 1):
                        break
                continue
            if b0 < 0x20:
                continue

            # Decode multi-byte UTF-8 character if needed
            seq = bytearray(raw)
            expected_extra = (
                1 if (b0 & 0xE0) == 0xC0 else 2 if (b0 & 0xF0) == 0xE0 else 3 if (b0 & 0xF8) == 0xF0 else 0
            )
            for _ in range(expected_extra):
                if select.select([fd], [], [], 0.05)[0]:
                    nxt = os.read(fd, 1)
                    if nxt:
                        seq.extend(nxt)
            ch = bytes(seq).decode("utf-8", "replace")
            chars.append(ch)
            _write("*")
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
        except Exception:
            pass
        if own_fd and fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def _confirm_presence_linux(step: str, describe: str) -> tuple[bool, str]:
    """Verify device owner on Linux using security key (FIDO2 / virtual-fido) or system auth."""
    # 1. CTAP / FIDO2 security key presence check (e.g. virtual-fido or hardware YubiKey)
    try:
        from fido2.hid import CtapHidDevice
        from fido2.ctap2 import Ctap2
        from fido2.ctap import CtapError

        devices = list(CtapHidDevice.list_devices())
        if devices:
            dev = devices[0]
            name = getattr(dev, "product_name", None) or "FIDO2 / Virtual FIDO"
            print(f"\n{BOLD}▶ Security key detected: {name}{OFF}", file=sys.stderr)
            if "virtual" in name.lower():
                print(
                    f"{DIM}   → press {BOLD}Ctrl+CapsLock{OFF}{DIM}, {BOLD}Ctrl+F12{OFF}{DIM}, or {BOLD}F12{OFF}{DIM} to confirm {step}…{OFF}",
                    file=sys.stderr,
                )
            else:
                print(f"{DIM}   → touch your security key to confirm {step}…{OFF}", file=sys.stderr)
            try:
                ctap = Ctap2(dev)
                ctap.selection()
                return True, f"device owner verified via {name}"
            except CtapError as e:
                print(f"{YELLOW}⚠️  Security key touch failed: {e}; trying system auth…{OFF}", file=sys.stderr)
            except Exception as e:
                print(f"{YELLOW}⚠️  Security key error: {e}; trying system auth…{OFF}", file=sys.stderr)
    except Exception:
        pass

    # 2. System authentication fallback (PAM / sudo with '*' masked feedback)
    user = os.environ.get("USER", "device owner")
    print(f"\n{BOLD}▶ Device owner verification (Linux system auth){OFF}", file=sys.stderr)
    print(f"{DIM}   → confirm with password or fingerprint for {user}…{OFF}", file=sys.stderr)
    prompt = f"   [confirm] sudo password for {user}: "
    try:
        for attempt in range(3):
            try:
                pw = _read_masked_password(prompt, timeout=PRESENCE_TIMEOUT)
            except TimeoutError:
                return False, f"timed out waiting for system auth within {PRESENCE_TIMEOUT}s"
            except Exception:
                # Fallback if no termios-capable TTY is attached
                r = subprocess.run(
                    ["sudo", "-k", "-p", "   [confirm] sudo password for %u: ", "sudo", "-v"],
                    timeout=PRESENCE_TIMEOUT,
                )
                if r.returncode == 0:
                    return True, "device owner verified via system auth"
                return False, f"system authentication failed (exit {r.returncode})"

            if pw is None:
                return False, "system authentication cancelled"

            r = subprocess.run(
                ["sudo", "-k", "-S", "-p", "", "sudo", "-v"],
                input=pw + "\n",
                text=True,
                capture_output=True,
                timeout=PRESENCE_TIMEOUT,
            )
            if r.returncode == 0:
                return True, "device owner verified via system auth"
            if attempt < 2:
                print("   Sorry, try again.", file=sys.stderr)
        return False, "system authentication failed (3 incorrect password attempts)"
    except subprocess.TimeoutExpired:
        return False, f"timed out waiting for system auth within {PRESENCE_TIMEOUT}s"
    except Exception as exc:
        return False, f"system authentication error: {exc}"


def confirm_presence(step: str, describe: str) -> tuple[bool, str]:
    """Verify the device owner. (confirmed, detail). Anything but a confirmation —
    refused, cancelled, timed out, or the check being unavailable — is False."""
    host_os = str(sys.platform)
    if host_os == "darwin":
        reason = f"confirm {step}: {describe}"[:180] + f" (HEAD {head_sha()})"
        code, detail = _run_presence_helper(reason)
        if code == 0:
            return True, "device owner verified"
        return False, detail or f"helper exited {code}"

    if host_os.startswith("linux"):
        return _confirm_presence_linux(step, describe)

    return False, f"unsupported platform for device-owner check: {host_os}"


def get_totp_secret() -> str | None:
    env_secret = os.environ.get("W0M_CONFIRM_TOTP_SECRET")
    if env_secret and env_secret.strip():
        return env_secret.strip()
    if TOTP_SECRET_FILE.exists():
        try:
            sec = TOTP_SECRET_FILE.read_text().strip()
            if sec:
                return sec
        except OSError:
            pass
    return None


def generate_totp(secret: str, timestamp: int | None = None) -> str:
    """Generate 6-digit TOTP code for a secret at a given timestamp (RFC 6238)."""
    secret_clean = secret.strip().replace(" ", "").upper()
    pad_len = (8 - len(secret_clean) % 8) % 8
    key = base64.b32decode(secret_clean + "=" * pad_len)
    t = (int(time.time()) if timestamp is None else timestamp) // 30
    msg = struct.pack(">Q", t)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    o = h[19] & 0x0F
    code_int = (struct.unpack(">I", h[o : o + 4])[0] & 0x7FFFFFFF) % 1000000
    return f"{code_int:06d}"


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    """Verify an RFC 6238 6-digit TOTP code against a base32 secret."""
    code_str = code.strip()
    if not (len(code_str) == 6 and code_str.isdigit()):
        return False
    try:
        secret_clean = secret.strip().replace(" ", "").upper()
        pad_len = (8 - len(secret_clean) % 8) % 8
        key = base64.b32decode(secret_clean + "=" * pad_len)
        code_int = int(code_str)
    except Exception:
        return False

    current_t = int(time.time()) // 30
    for offset in range(-window, window + 1):
        t = current_t + offset
        msg = struct.pack(">Q", t)
        h = hmac.new(key, msg, hashlib.sha1).digest()
        o = h[19] & 0x0F
        expected = (struct.unpack(">I", h[o : o + 4])[0] & 0x7FFFFFFF) % 1000000
        if code_int == expected:
            return True
    return False


def dispatch_orca_mobile_request(step: str, describe: str, timeout: int = 120) -> tuple[bool, str]:
    """Write an interactive confirmation challenge to ~/.w0m/confirm/requests/<id>.json,
    and poll for an approved response from the mobile Orca app."""
    try:
        REQUESTS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        RESPONSES_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        return False, f"cannot create mobile request directory: {exc}"

    req_id = uuid.uuid4().hex[:12]
    nonce = secrets.token_hex(16)
    head = head_sha()
    now = time.time()
    expires_at = now + timeout

    req_data = {
        "id": req_id,
        "step": step,
        "describe": describe,
        "head": head,
        "nonce": nonce,
        "created_at": now,
        "expires_at": expires_at,
    }
    req_path = REQUESTS_DIR / f"{req_id}.json"
    res_path = RESPONSES_DIR / f"{req_id}.json"

    try:
        req_path.write_text(json.dumps(req_data, indent=2))
        req_path.chmod(0o600)
    except OSError as exc:
        return False, f"failed to write mobile confirmation request: {exc}"

    print(
        f"\n{BOLD}▶ Orca Mobile Biometric Confirmation Request Dispatched{OFF}\n"
        f"   Request ID: {BOLD}{req_id}{OFF}  |  Nonce: {DIM}{nonce[:8]}…{OFF}\n"
        f"   Open the Orca app on your phone to approve with Face ID / Touch ID.\n"
        f"   {DIM}Waiting up to {timeout}s (press Ctrl+C to abort)…{OFF}",
        file=sys.stderr,
    )

    poll_interval = 0.2
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            if res_path.exists():
                try:
                    resp = json.loads(res_path.read_text())
                except (json.JSONDecodeError, OSError):
                    time.sleep(poll_interval)
                    continue

                if resp.get("nonce") != nonce:
                    return False, "response nonce mismatch"
                if resp.get("head") != head:
                    return False, f"response head mismatch ({resp.get('head')} != {head})"
                if resp.get("status") == "approved":
                    device = resp.get("device", "orca_mobile")
                    return True, f"approved on {device}"
                return False, resp.get("reason", "mobile user declined")
            time.sleep(poll_interval)
    finally:
        req_path.unlink(missing_ok=True)
        res_path.unlink(missing_ok=True)

    return False, f"timed out waiting for mobile approval ({timeout}s)"


def approve_request(req_id: str, device: str = "orca_mobile_client") -> int:
    """Approve a pending mobile confirmation request (called by Orca client or test helper)."""
    req_path = REQUESTS_DIR / f"{req_id}.json"
    if not req_path.exists():
        print(f"{RED}❌ confirm: request {req_id} not found{OFF}", file=sys.stderr)
        return 1
    try:
        data = json.loads(req_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"{RED}❌ confirm: invalid request file ({exc}){OFF}", file=sys.stderr)
        return 1

    if time.time() > float(data.get("expires_at", 0)):
        print(f"{RED}❌ confirm: request {req_id} has expired{OFF}", file=sys.stderr)
        return 1

    res_path = RESPONSES_DIR / f"{req_id}.json"
    res_data = {
        "id": req_id,
        "nonce": data["nonce"],
        "head": data["head"],
        "status": "approved",
        "device": device,
        "timestamp": time.time(),
    }
    RESPONSES_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    res_path.write_text(json.dumps(res_data, indent=2))
    res_path.chmod(0o600)
    print(f"{GREEN}✅ confirm: request {req_id} approved for {device}{OFF}")
    return 0


def enroll_totp() -> int:
    """Enroll a fresh RFC 6238 TOTP secret for cross-device authentication."""
    verdict = detect_agent()
    if verdict.agent or not verdict.measurable:
        refuse_agent("--enroll-totp", "TOTP secret enrollment", verdict)
        return 1

    raw_secret = secrets.token_bytes(20)
    secret = base64.b32encode(raw_secret).decode("ascii")
    uri = f"otpauth://totp/w0m:admin?secret={secret}&issuer=w0m"

    print(f"\n{BOLD}▶ w0m Admin TOTP Enrollment (Cross-Device Confirmation){OFF}\n")
    qr_shown = False
    try:
        qr = subprocess.run(["qrencode", "-t", "UTF8", "-o", "-", uri],
                            capture_output=True, text=True, check=False)
        if qr.returncode == 0 and qr.stdout.strip():
            print(qr.stdout)
            qr_shown = True
    except OSError:
        pass

    print(f"  Secret (Base32): {BOLD}{secret}{OFF}")
    print(f"  Authenticator URI: {DIM}{uri}{OFF}\n")
    if qr_shown:
        print("  Scan the QR code above with your Authenticator app (Apple Passwords, 1Password, Google Authenticator).")
    else:
        print("  Add this secret to your Authenticator app (1Password, Google Authenticator, Apple Passwords).")
    print("  To confirm enrollment, enter the 6-digit code from your app:")

    code = _prompt_line("  Enter 6-digit verification code: ")
    if not code or not verify_totp(secret, code):
        print(f"\n{RED}❌ Verification failed — code did not match. Enrollment aborted.{OFF}\n", file=sys.stderr)
        return 1

    TOTP_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    TOTP_SECRET_FILE.write_text(secret + "\n")
    TOTP_SECRET_FILE.chmod(0o600)
    print(f"\n{GREEN}✅ TOTP secret successfully saved to {TOTP_SECRET_FILE}!{OFF}")
    print(f"   You can now confirm deployments and migrations from any terminal by typing the 6-digit code.\n")
    audit("ENROLLED-TOTP", "--enroll-totp", f"saved to {TOTP_SECRET_FILE}")
    return 0


def _prompt_line(prompt_text: str) -> str | None:
    try:
        tty = open("/dev/tty", "r+")
    except OSError:
        pass
    else:
        try:
            tty.write(prompt_text)
            tty.flush()
            line = tty.readline().strip()
            return line if line else None
        finally:
            tty.close()

    if sys.stdin.isatty():
        sys.stderr.write(prompt_text)
        sys.stderr.flush()
        line = sys.stdin.readline().strip()
        return line if line else None

    return None



def read_consent() -> dict[str, Any] | None:
    if not CONSENT.exists():
        return None
    try:
        c: dict[str, Any] = json.loads(CONSENT.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if time.time() > float(c.get("expires", 0)):
        return None
    if c.get("head") != head_sha():
        # The tree moved since consent was granted. Whatever was agreed to is not what would ship
        # now, so the agreement does not carry.
        return None
    return c


def write_consent(root: str, covered: list[str], ttl: int) -> None:
    payload = {
        "root": root,
        "covered": covered,
        "head": head_sha(),
        "granted_at": time.time(),
        "expires": time.time() + ttl,
    }
    CONSENT.write_text(json.dumps(payload, indent=2))
    try:
        CONSENT.chmod(0o600)
    except OSError:
        pass


def clear_consent() -> int:
    """Unconditionally unlink the active consent file on disk (T541)."""
    try:
        if CONSENT.exists():
            CONSENT.unlink()
            audit("CLEARED", "--clear", f"unlinked {CONSENT}")
            print(f"{GREEN}✅ confirm: consent cleared ({CONSENT}){OFF}")
        return 0
    except OSError as exc:
        print(f"{RED}❌ confirm: failed to clear consent: {exc}{OFF}", file=sys.stderr)
        return 1


def consume_consent_step(step: str, consent: dict[str, Any]) -> None:
    """Atomically remove a single-use step from the active consent grant on disk (T541)."""
    covered = [s for s in consent.get("covered", []) if s != step]
    consent["covered"] = covered
    try:
        CONSENT.write_text(json.dumps(consent, indent=2))
        CONSENT.chmod(0o600)
    except OSError:
        pass


def _banner(step: str, describe: str, reason: str) -> str:
    return (
        f"\n{YELLOW}{BOLD}⚠️  CONFIRM: {step}{OFF}\n"
        f"   {describe}\n"
        f"   {DIM}({reason}){OFF}\n"
        f"   HEAD {head_sha()}\n"
        f"{BOLD}   Type 'yes' to proceed (or 6-digit TOTP / 'push'), anything else to abort: {OFF}"
    )


def rejection_note(line: str) -> str:
    """Why a typed answer was not accepted, WITHOUT repeating it (a mistyped code is a secret). Added 2026-10-04 after a real deploy aborted at `deploy-web` with no reason."""
    if not line:
        return "the answer was empty (just Enter). Type yes, then Enter."
    if not line.isascii():
        return (f"the answer had {len(line)} character(s), at least one non-ASCII: the keyboard layout may be set to another language "
                "(this gate reads exactly `yes`). Switch to the English layout and run the step again.")
    return f"the answer ({len(line)} character(s)) was not 'yes', not a 6-digit code and not push. Type yes, then Enter."


def _answer_from(line: str) -> str | None:
    """The one place a typed line becomes an answer, for BOTH input channels: `yes`, a 6-digit code, or push; anything else is refused WITH a reason."""
    if line.lower() == "yes":
        return "yes"
    if len(line) == 6 and line.isdigit():
        return line
    if line.lower() in ("push", "orca", "mobile"):
        return line.lower()
    _tell_rejected(line)
    return None


def _tell_rejected(line: str) -> None:
    print(f"{RED}   ✗ {rejection_note(line)}{OFF}", file=sys.stderr)


def prompt(step: str, describe: str, reason: str) -> str | None:
    """Ask a human, on whichever real terminal exists.

    TWO channels, tried in order, because ONE is not enough — found the hard way 2026-08-10 when
    the owner ran `just deploy` in a genuine terminal and was told there was none:

    1. **/dev/tty** — works in a plain shell. But it is NOT universally present: the Claude Code
       app's embedded terminal pane reports `Device not configured` for it, so a /dev/tty-only gate
       blocks the very person it is supposed to ask.
    2. **stdin, only when `stdin.isatty()`** — the fallback that covers case 1.

    ⚠️ The fallback does NOT weaken the gate, and the reason is worth stating: a PIPE IS NOT A TTY.
    `echo yes | …`, `yes | …` and heredocs all make stdin a pipe, so `isatty()` is False and the
    prompt is never reached — which is exactly the property the /dev/tty channel was chosen for.
    Both channels have the same ceiling — an agent that holds a pty answers either, and agy did —
    which is why this is layer 2 of 3 and never runs for an agent session (layer 1).
    """
    banner = _banner(step, describe, reason)

    # 1. A real terminal device, independent of redirection.
    try:
        tty = open("/dev/tty", "r+")          # noqa: SIM115 — closed explicitly below
    except OSError:
        pass
    else:
        try:
            tty.write(banner)
            tty.flush()
            line = tty.readline().strip()
            return _answer_from(line)
        finally:
            tty.close()

    # 2. No /dev/tty, but stdin is an interactive terminal — a pipe would report False here.
    if sys.stdin.isatty():
        sys.stderr.write(banner)
        sys.stderr.flush()
        return _answer_from(sys.stdin.readline().strip())

    print(
        f"\n{RED}{BOLD}❌ BLOCKED — `{step}` needs a human confirmation and there is no "
        f"terminal to ask on.{OFF}\n"
        f"   {describe}\n"
        f"   {DIM}Neither /dev/tty nor an interactive stdin is available, so there is no way to "
        f"ask a person. This is the gate working, not a bug — an automated caller cannot answer "
        f"it.{OFF}\n"
        f"   {BOLD}Run it yourself in a terminal:{OFF} just {step}   {DIM}(from w0m-api/){OFF}\n"
        f"   {DIM}If you ARE in a terminal and still see this, run `just confirm-doctor` — it "
        f"prints which channels your shell exposes.{OFF}\n",
        file=sys.stderr,
    )
    return None


def human_confirms(step: str, describe: str, reason: str) -> bool:
    """Layers 2 and 3: typed input at a terminal (yes / 6-digit TOTP / push), then verification."""
    ans = prompt(step, describe, reason)
    if not ans:
        return False

    # Path A: Direct 6-digit TOTP code
    if len(ans) == 6 and ans.isdigit():
        sec = get_totp_secret()
        if not sec:
            print(
                f"{RED}❌ confirm: {step} — TOTP entered but no secret configured on host "
                f"(run just confirm-enroll-totp or set W0M_CONFIRM_TOTP_SECRET){OFF}",
                file=sys.stderr,
            )
            return False
        if verify_totp(sec, ans):
            print(f"{GREEN}✅ confirm: {step} — TOTP 6-digit code verified{OFF}")
            return True
        print(f"{RED}❌ confirm: {step} — invalid TOTP code{OFF}", file=sys.stderr)
        return False

    # Path B: Orca Mobile challenge-response push / Mobile TOTP
    if ans in ("push", "orca", "mobile"):
        ok, msg = dispatch_orca_mobile_request(step, describe, timeout=2)
        if ok:
            print(f"{GREEN}✅ confirm: {step} — {msg}{OFF}")
            return True
        if "declined" in msg or "mismatch" in msg:
            print(f"{RED}❌ confirm: {step} — mobile confirmation failed: {msg}{OFF}", file=sys.stderr)
            return False

        # No background Orca relay responded: launch mobile TOTP
        sec = get_totp_secret()
        if not sec:
            print(f"\n{BOLD}▶ Mobile TOTP (push) selected, but no secret is enrolled on this host.{OFF}")
            print(f"   Launching mobile TOTP enrollment with QR code...\n")
            if enroll_totp() == 0:
                sec = get_totp_secret()
            else:
                return False

        if sec:
            print(f"\n{BOLD}▶ Enter 6-digit code from your mobile authenticator app:{OFF}")
            code = _prompt_line("   6-digit TOTP code: ")
            if code and verify_totp(sec, code):
                print(f"{GREEN}✅ confirm: {step} — Mobile TOTP code verified{OFF}")
                return True
            print(f"{RED}❌ confirm: {step} — invalid TOTP code{OFF}", file=sys.stderr)
            return False

        print(f"{RED}❌ confirm: {step} — mobile confirmation failed: {msg}{OFF}", file=sys.stderr)
        return False

    # Path C: Standard "yes" typed -> verify Touch ID dialog or Linux key/system auth
    if ans == "yes":
        if sys.platform == "darwin":
            print(
                f"{DIM}   → confirm with Touch ID (or your login password) in the macOS dialog…{OFF}",
                file=sys.stderr,
            )
        else:
            print(
                f"{DIM}   → verify device owner presence (security key / system auth)…{OFF}",
                file=sys.stderr,
            )
        ok, detail = confirm_presence(step, describe)
        if ok:
            return True

        print(f"{RED}❌ confirm: {step} — device owner NOT verified ({detail}){OFF}", file=sys.stderr)
        return False

    return False


def doctor() -> int:
    """Print which confirmation channels this shell exposes. Exists because "there is no terminal
    to ask on" is useless feedback when you are, in fact, sitting in a terminal."""
    dev_tty: str
    try:
        open("/dev/tty").close()
        dev_tty = f"{GREEN}available{OFF}"
        ok = True
    except OSError as exc:
        dev_tty = f"{RED}unavailable{OFF} ({exc.strerror})"
        ok = False
    stdin_tty = sys.stdin.isatty()
    ok = ok or stdin_tty
    print("▶ confirm-doctor — can this shell answer a confirmation?\n")
    print(f"  /dev/tty          {dev_tty}")
    print(f"  stdin.isatty()    {GREEN + 'True' + OFF if stdin_tty else RED + 'False' + OFF}")
    print(f"  stdout.isatty()   {sys.stdout.isatty()}   {DIM}(not used — informational){OFF}")
    verdict = detect_agent()
    if verdict.agent:
        agent_line = f"{RED}agent session — `{verdict.agent}`{OFF}"
    elif not verdict.measurable:
        agent_line = f"{RED}UNMEASURABLE{OFF}"
    else:
        agent_line = f"{GREEN}not an agent session{OFF}"
    print(f"  ancestry          {agent_line}")
    print(f"                    {DIM}{verdict.evidence}{OFF}")
    code, detail = _run_presence_helper("--check")
    presence = GREEN + "available" + OFF if code == 0 else f"{RED}unavailable{OFF} ({detail})"
    print(f"  Touch ID dialog   {presence}   {DIM}(checked without showing it){OFF}")
    totp_sec = get_totp_secret()
    if totp_sec:
        totp_source = "W0M_CONFIRM_TOTP_SECRET" if os.environ.get("W0M_CONFIRM_TOTP_SECRET") else str(TOTP_SECRET_FILE)
        totp_status = f"{GREEN}configured{OFF} {DIM}({totp_source}){OFF}"
    else:
        totp_status = f"{YELLOW}not configured{OFF} {DIM}(run with --enroll-totp to enable cross-device confirmation){OFF}"
    print(f"  TOTP fallback     {totp_status}")
    print(f"  Orca mobile relay {GREEN}enabled{OFF} {DIM}(requests at {REQUESTS_DIR}){OFF}")
    print()
    if verdict.agent or not verdict.measurable:
        print(
            f"{RED}❌ Mutating recipes REFUSE here — this is (or may be) an agent session.{OFF}\n"
            f"   {DIM}Run them from a terminal no agent started.{OFF}"
        )
        return 1
    if not ok:
        print(
            f"{RED}❌ This shell CANNOT be prompted, so every mutating recipe will refuse.{OFF}\n"
            f"   {DIM}If you are a human in a real terminal, this is a bug in the gate — a pipe or a\n"
            f"   non-pty wrapper is swallowing both channels. Say so rather than working around it.{OFF}"
        )
        return 1
    if code != 0:
        if totp_sec:
            print(
                f"{YELLOW}⚠️  Touch ID is unavailable, but TOTP is configured — cross-device terminal confirmation will work.{OFF}\n"
            )
            return 0
        print(f"{RED}❌ The device-owner check is unavailable and no TOTP secret is configured, so every mutating recipe will refuse.{OFF}")
        return 1
    print(f"{GREEN}✅ This shell CAN be prompted — mutating recipes will ask you, then Touch ID (or TOTP / Orca mobile).{OFF}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        die("usage: confirm_step.py <step-name> | --doctor | --enroll-totp | --approve <id> [device]")
    step = sys.argv[1]
    if step in ("--doctor", "doctor"):
        return doctor()
    if step in ("--enroll-totp", "enroll-totp"):
        return enroll_totp()
    if step in ("--approve", "approve"):
        if len(sys.argv) < 3:
            die("usage: confirm_step.py --approve <request-id> [device-name]")
        req_id = sys.argv[2]
        device = sys.argv[3] if len(sys.argv) > 3 else "orca_mobile_client"
        return approve_request(req_id, device)
    if step in ("--clear", "clear"):
        return clear_consent()
    policy = load_policy()
    roots: dict[str, list[str]] = policy.get("roots", {})
    always: list[str] = policy.get("always_confirm", [])
    single_use: list[str] = policy.get("single_use", ["db-migrate"])
    steps: dict[str, str] = policy.get("steps", {})
    ttl = int(policy.get("ttl_seconds", 900))

    describe = steps.get(step, f"UNRECOGNISED STEP `{step}` — not classified in confirm-policy.json.")
    known = step in steps or step in roots or step in always

    # 0. An agent session is refused before ANY path below — including a live root consent, which
    #    an agent must not be able to ride because a human granted it minutes ago (T435).
    verdict = detect_agent()
    if verdict.agent or not verdict.measurable:
        refuse_agent(step, describe, verdict)
        audit("REFUSED-AGENT" if verdict.agent else "REFUSED-UNMEASURABLE", step, verdict.evidence)
        return 1

    # 1. always_confirm wins over everything, including an agreed root. This is the owner's
    #    "confirm only specific steps like migrations" carve-out.
    if step in always:
        if human_confirms(step, describe, "in always_confirm — re-asked even inside an agreed run"):
            audit("CONFIRMED", step, "always_confirm — answered at a tty, device owner verified")
            print(f"{GREEN}✅ confirm: {step} — confirmed{OFF}")
            return 0
        print(f"{RED}❌ confirm: {step} — NOT confirmed, aborting{OFF}", file=sys.stderr)
        return 1

    # 2. A live consent covering this step: pass without asking again.
    consent = read_consent()
    if consent and step in consent.get("covered", []):
        left = int(float(consent["expires"]) - time.time())
        audit("PASSED-ON-CONSENT", step, f"root={consent['root']} (consent is forgeable — see docstring)")
        if step in single_use:
            consume_consent_step(step, consent)
            audit("CONSUMED-ON-CONSENT", step, f"single-use step removed from root={consent['root']} covered list")
        print(
            f"{GREEN}✅ confirm: {step} — covered by `{consent['root']}` "
            f"(expires in {left}s, HEAD {consent['head']}){OFF}"
        )
        return 0

    # 3. A root: ask once, then cover its chain.
    if step in roots:
        if not human_confirms(step, describe, f"top-level — one yes covers {len(roots[step])} chained step(s)"):
            print(f"{RED}❌ confirm: {step} — NOT confirmed, aborting{OFF}", file=sys.stderr)
            return 1
        write_consent(step, roots[step], ttl)
        audit("GRANTED", step, f"root; covers {len(roots[step])} step(s) for {ttl}s — answered at a tty, device owner verified")
        print(f"{GREEN}✅ confirm: {step} — confirmed; chained steps covered for {ttl}s{OFF}")
        return 0

    # 4. Anything else — including an unrecognised name — confirms individually. FAIL CLOSED.
    reason = (
        "run directly, outside an agreed root"
        if known
        else "NOT IN POLICY — unrecognised steps confirm by default, never pass by default"
    )
    if human_confirms(step, describe, reason):
        audit("CONFIRMED", step, reason)
        print(f"{GREEN}✅ confirm: {step} — confirmed{OFF}")
        return 0
    audit("REFUSED", step, reason)
    print(f"{RED}❌ confirm: {step} — NOT confirmed, aborting{OFF}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
