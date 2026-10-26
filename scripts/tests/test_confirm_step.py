#!/usr/bin/env python3
"""Red probes for the mutating-recipe confirmation gate (T161 AC3).

A gate that only ever passes proves nothing — and this one guards deploys and schema writes, so
its failure mode is silent. Every case here asserts the gate WITHHOLDS, because withholding is
the whole product. The two "pass" cases exist to prove it is not simply refusing everything,
which would be a gate nobody could use and would get removed.

Run: `just confirm-test` (or `python3 scripts/tests/test_confirm_step.py`).
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import os
import pty
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ESTATE = Path(__file__).resolve().parents[2]
WEB_ROOT = ESTATE / "w0m-web"
SCRIPT = ESTATE / "scripts" / "confirm_step.py"
POLICY = ESTATE / "project" / "policies" / "confirm-policy.json"
# 🔴 The probes MUST NOT touch the shared consent file. They grant and clear consent, and this
# suite runs inside `just test`, which runs inside `just deploy` — pointing at the real path meant
# the suite erased a live deploy's consent and made every later step re-prompt the owner.
_ISOLATED = Path(tempfile.mkdtemp(prefix="w0m-confirm-test-")) / "consent.json"
os.environ["W0M_CONFIRM_CONSENT"] = str(_ISOLATED)   # inherited by every subprocess below
CONSENT = _ISOLATED

# T435: the gate's layers 1 (agent refusal) and 3 (Touch ID) depend on who runs this suite. The
# behavioural probes go through FIXTURE, which pins both, so they test the terminal and consent logic
# whoever the caller is. Layers 1 and 3 get their own probes below, including one against the real
# script. See the fixture's docstring for why this is not an override the recipes honour.
FIXTURE = ESTATE / "scripts" / "tests" / "confirm_step_fixture.py"
PRESENCE_SOURCE = WEB_ROOT / "project" / "scripts" / "human_presence.swift"
sys.path.insert(0, str(SCRIPT.parent))
import confirm_step as gate  # noqa: E402  — after W0M_CONFIRM_CONSENT, which it reads at import

failures: list[str] = []
passes = 0


def run(step: str, stdin: str | None = None, caller: str = "human",
        presence: str = "yes") -> subprocess.CompletedProcess[str]:
    """Run the gate with NO controlling terminal — guaranteed, not assumed.

    🔴 `start_new_session=True` is what makes these probes honest. Without it the child INHERITS
    the caller's terminal, so `/dev/tty` exists, and the gate does the right thing — it prompts,
    and waits forever for a human who is not watching. These checks are named "no tty"; they have
    to CREATE that condition rather than depend on the caller happening to lack one.

    Measured 2026-08-16: run from a non-interactive shell this passed instantly (no `/dev/tty`), so
    it looked correct for as long as nobody ran it from a terminal. Run from a real one — which
    T224's `just test` in `just deploy` finally did — it hung a production deploy for 20 minutes on
    an invisible prompt. The probe was never terminal-independent; the environment was just always
    the same.
    """
    argv = ([sys.executable, str(SCRIPT), step] if caller == "real"
            else [sys.executable, str(FIXTURE), caller, presence, step])
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        # BOTH channels must be closed, because the gate tries BOTH: `/dev/tty` first, then stdin
        # when `stdin.isatty()`. `start_new_session` only kills the first — an inherited terminal
        # on fd 0 still satisfies the second, which is precisely what kept this hanging after the
        # first attempt at a fix. When the caller supplies no input, hand the child DEVNULL.
        input=stdin,
        stdin=None if stdin is not None else subprocess.DEVNULL,
        cwd=WEB_ROOT,
        start_new_session=True,
        timeout=30,
    )


def check(label: str, cond: bool, detail: str = "") -> None:
    global passes
    if cond:
        passes += 1
        print(f"  ✅ {label}")
    else:
        failures.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  ❌ {label}{' — ' + detail if detail else ''}")


def head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=WEB_ROOT, capture_output=True, text=True
    ).stdout.strip()


def grant(root: str) -> None:
    pol = json.loads(POLICY.read_text())
    CONSENT.write_text(
        json.dumps(
            {
                "root": root,
                "covered": pol["roots"][root],
                "head": head(),
                "granted_at": time.time(),
                "expires": time.time() + int(pol["ttl_seconds"]),
            }
        )
    )


def pty_answer(step: str, answer: str, caller: str = "human", presence: str = "yes") -> int:
    return pty_run(step, answer, caller, presence)[0]


def pty_run(step: str, answer: str, caller: str = "human", presence: str = "yes") -> tuple[int, str]:
    """Drive the gate through a REAL pty — what a human in a terminal actually is.

    Exists because the human path was the one case never proven: the gate shipped reading only
    /dev/tty, which the app's embedded terminal does not expose, so it refused the owner while
    reporting "there is no terminal to ask on". A probe suite that only proves a gate BLOCKS can
    ship a gate that blocks everyone.
    """
    parent, child = pty.openpty()  # noqa: F841  (kept for the fd-close contract below)
    # 🔴 `start_new_session=True` is LOAD-BEARING, and its absence deadlocked a production deploy.
    #
    # The gate reads `/dev/tty`, which is the CONTROLLING TERMINAL — not stdin. Handing the pty in
    # as stdin therefore did nothing when this ran from a real terminal: `/dev/tty` still resolved
    # to the CALLER's terminal, so the probe prompted the human running the command and waited.
    # It only ever "passed" because it was run from non-interactive shells, where `/dev/tty` does
    # not exist and the gate refuses instantly — the fast path, which proves nothing about humans.
    #
    # 2026-08-16: T224 wired `just test` into `just deploy`; the first real deploy from a terminal
    # hung for 15 minutes on an invisible prompt buried inside a test suite's captured output.
    # A probe that can seize the caller's terminal is worse than the bug it tests for.
    #
    # `start_new_session` detaches the child from the caller's terminal, and giving it the pty on
    # all three fds makes THAT the controlling terminal — so `/dev/tty` inside the child is the pty
    # this function owns, and can never be the developer's.
    os.close(parent)
    os.close(child)

    # `pty.fork()` — not `Popen(stdin=pty)`. Handing a pty in as a FILE DESCRIPTOR does nothing for
    # `/dev/tty`, which resolves to the CONTROLLING TERMINAL of the session. `pty.fork()` does the
    # `setsid()` + `TIOCSCTTY` dance so the new pty genuinely becomes the child's controlling
    # terminal — which means `/dev/tty` inside the child is OURS, and can never be the caller's.
    pid, master = pty.fork()
    if pid == 0:                                   # child: becomes the gate, on its own terminal
        try:
            os.chdir(WEB_ROOT)
            os.execv(sys.executable, [sys.executable, str(FIXTURE), caller, presence, step])
        finally:
            os._exit(127)

    deadline = time.time() + 10
    out = b""
    try:
        os.write(master, f"{answer}\n".encode())
        while True:
            r, _, _ = select.select([master], [], [], 0.5)
            if r:
                try:
                    chunk = os.read(master, 1024)
                    if not chunk:
                        break
                    out += chunk
                except OSError:
                    break                              # slave closed — the child is done
            if time.time() > deadline:
                os.kill(pid, signal.SIGKILL)
                break
    finally:
        os.close(master)
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status), out.decode("utf-8", "replace")


def clear() -> None:
    CONSENT.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# T407 — THE PROSE MUST NOT CONTRADICT THE POLICY DATA.
#
# On 2026-08-16 the owner moved `db-migrate` out of `always_confirm` and into the steps
# `deploy-all` covers. The change landed in confirm-policy.json and in the assertion below — and
# in NOTHING ELSE. Ten claims across four surfaces went on describing the old behaviour for 34
# days: this file's sibling docstring, `_always_confirm_why` (100 lines above the `_notes` entry
# that contradicted it, in the SAME FILE), docs/DEPLOY-CONFIRM.md, and the justfile comment above
# `_confirm`. Found on 2026-09-19 when a live `deploy-all` passed db-migrate on the root consent
# and the docstring said it could not.
#
# 🔑 Why a test and not a careful re-read: the behavioural contract was already pinned and stayed
# green throughout. Green tests plus confidently wrong documentation is the worse failure — it is
# the gate-that-reads-as-protection shape this whole module exists to avoid, turned on the module's
# own description of itself. So the prose is now DERIVED-CHECKED against the data.
#
# This reads English, so it is deliberately narrow: it matches CLAIM SHAPES, not meaning. It will
# not catch every way prose can lie. It catches the exact shapes that did lie, in both directions,
# and the MUTATION section below proves it still catches them.
PROSE_SURFACES = (
    "scripts/confirm_step.py",
    "project/policies/confirm-policy.json",
    "w0m-web/docs/DEPLOY-CONFIRM.md",
    "justfile",
)

# "this step asks again even inside an agreed root"
REPROMPT = re.compile(r"re-prompt|re-ask|asks? again|prompts? again|again for|still block", re.I)
# "this step rides the root consent" — the inverse claim
RIDES = re.compile(r"covered by|inside the one yes|included in the one yes", re.I)
# A bare integer + "min"; the lookbehind keeps "~4.5 min" from reading as "5 min".
MINUTES = re.compile(r"(?<![\d.])(\d+)\s*min", re.I)
TTL_TALK = re.compile(r"consent|expires|lasts|chains for", re.I)
COUNTS = re.compile(r"(?<![\d.])(\d+)\s*(?:probes|cases)", re.I)


def prose_regions(rel: str, text: str) -> list[str]:
    """The parts of a surface that DESCRIBE the gate — not the whole file.

    🔴 The first version scanned whole files and produced four false positives, which is the
    failure mode this suite exists to refuse: a check that cries wolf is turned off, and a check
    that is off is indistinguishable from one that passes. `roots` is a JSON ARRAY of step names —
    reading it as prose makes every step look like a claim about itself; the justfile carries other
    recipes' comments advertising other suites' probe counts."""
    if rel.endswith("confirm_step.py"):
        m = re.search(r'"""(.*?)"""', text, re.S)
        return [m.group(1)] if m else []
    if rel.endswith("confirm-policy.json"):
        doc = json.loads(text)
        notes = [v for k, v in doc.items() if k.startswith("_") and isinstance(v, str)]
        notes += [v for v in doc.get("_notes", {}).values() if isinstance(v, str)]
        return notes
    if rel.endswith(("justfile", "estate.just")):
        # Only the comment blocks introducing THIS gate's two recipes.
        return re.findall(r"((?:^#.*\n)+)^(?:_confirm step|confirm-test):", text, re.M)
    return [text]


def claim_units(text: str) -> list[str]:
    """Split prose into units small enough that a step name and a verb in the same unit really are
    one claim. Markdown table rows are their own unit — the stale `| ... then again for db-migrate |`
    row had no sentence-ending punctuation at all and would otherwise have merged with its
    neighbours."""
    units: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        for line in para.splitlines():
            if line.lstrip().startswith("|"):
                units.append(line)
        rest = "\n".join(l for l in para.splitlines() if not l.lstrip().startswith("|"))
        units.extend(u for u in re.split(r"(?<=[.!?])\s+", rest) if u.strip())
    return units


def prose_contradictions(text: str, policy: dict) -> list[str]:
    """Every way this text disagrees with the policy data. Empty list == agrees."""
    always = set(policy["always_confirm"])
    covered = set(policy["roots"]["deploy-all"])
    ttl_min = policy["ttl_seconds"] // 60
    out: list[str] = []
    for unit in claim_units(text):
        for step in covered | always:
            if step not in unit:
                continue
            # Both sides, or short names swallow ordinary words: `deploy` matched "deploys" and
            # "a w0m deploy running", `test` matched "latest". A longer step name containing this
            # one (db-migrate inside db-migrate-test) is likewise not a hit.
            if not re.search(r"(?<![\w-])" + re.escape(step) + r"(?![\w-])", unit):
                continue
            if REPROMPT.search(unit) and step in covered and step not in always:
                out.append(f"claims `{step}` re-prompts, but it rides the deploy-all consent: {unit.strip()[:90]}")
            if RIDES.search(unit) and step in always:
                out.append(f"claims `{step}` rides the root consent, but it is in always_confirm: {unit.strip()[:90]}")
        if TTL_TALK.search(unit):
            for found in MINUTES.findall(unit):
                if int(found) != ttl_min:
                    out.append(f"says consent lasts {found} min; ttl_seconds is {ttl_min} min: {unit.strip()[:90]}")
    return out


def surface_problems(rel: str, raw: str, policy: dict, read_error: str = "") -> list[str]:
    """Every way one surface disagrees with the data — or could not be checked at all.

    🔴 THREE STATES, NOT TWO. A surface that cannot be read, or whose extractor matches no prose
    region, must come back with a PROBLEM rather than an empty list. "Not checked" rendering as
    "agrees" is the vacuous pass this estate keeps finding in its own audit tools (T242), and
    `justfile` is the live instance: it is a symlink into the w0m-api repo, so in a detached
    worktree it resolves to nothing and a two-state version of this goes green having read zero
    bytes."""
    if read_error:
        return [f"UNMEASURABLE — {read_error}"]
    regions = prose_regions(rel, raw) if raw.strip() else []
    if not regions or not any(r.strip() for r in regions):
        return [f"UNMEASURABLE — no prose region matched in {rel}; the extractor found nothing to check"]
    return prose_contradictions("\n\n".join(regions), policy)


def declared_probe_counts(text: str) -> list[int]:
    """Every "N probes"/"N cases" figure a surface advertises."""
    return [int(n) for n in COUNTS.findall(text)]


# ---------------------------------------------------------------------------
# T435 — LAYER 1: agent ancestry. Synthetic process tables, shaped on chains measured 2026-09-24
# (pid → (ppid, comm, args)); `start` is the gate's own pid.
ORCA = (1, "/Applications/Orca.app/Contents/Frameworks/Orca Helper.app/Contents/MacOS/Orca Helper", "Orca Helper")
CHAINS: dict[str, tuple[dict[int, tuple[int, str, str]], str | None]] = {
    "Claude Code (the 2026-09-24 session's own chain)": ({
        500: (400, "python3", "python3 project/scripts/confirm_step.py deploy-web"),
        400: (300, "/bin/zsh", "/bin/zsh -c just deploy-web"),
        300: (200, "claude", "claude"),
        200: (100, "-/bin/zsh", "-zsh"), 100: (10, "/usr/bin/login", "login -fp proto"), 10: ORCA,
    }, "claude"),
    "agy (the 2026-09-17 db-migrate)": ({
        500: (400, "python3", "python3 project/scripts/confirm_step.py db-migrate"),
        400: (300, "just", "just db-migrate"), 300: (200, "agy", "agy"),
        200: (100, "-/bin/zsh", "-zsh"), 100: (10, "/usr/bin/login", "login"), 10: ORCA,
    }, "agy"),
    "`script -q /dev/null` wrapped under claude (the pty forge)": ({
        500: (450, "python3", "python3 confirm_step.py deploy-web"),
        450: (400, "script", "script -q /dev/null python3 confirm_step.py deploy-web"),
        400: (300, "/bin/zsh", "zsh"), 300: (1, "claude", "claude"),
    }, "claude"),
    "Antigravity IDE language server": ({
        500: (400, "python3", "python3 confirm_step.py deploy"),
        400: (300, "/bin/bash", "bash"),
        300: (1, "/Applications/Antigravity.app/Contents/Resources/bin/language_server_macos_arm", "language_server_macos_arm"),
    }, "language_server_macos_arm"),
    "an agent shipped as a node script (codex)": ({
        500: (400, "python3", "python3 confirm_step.py deploy"),
        400: (1, "node", "node /opt/homebrew/bin/codex exec"),
    }, "codex"),
    "a HUMAN in an Orca terminal": ({
        500: (400, "python3", "python3 confirm_step.py deploy-all"),
        400: (300, "just", "just deploy-all"),
        300: (100, "-/bin/zsh", "-zsh"), 100: (10, "/usr/bin/login", "login"), 10: ORCA,
    }, None),
    "a HUMAN in the Claude desktop APP's terminal pane (`Claude`, not `claude`)": ({
        500: (400, "python3", "python3 confirm_step.py deploy"),
        400: (300, "/bin/zsh", "zsh"),
        300: (1, "/Applications/Claude.app/Contents/MacOS/Claude", "Claude"),
    }, None),
}

# T435 AC4 — a recipe whose body runs one of these mutates production and must depend on `_confirm`.
DEPLOY_SHAPED = re.compile(
    r"wrangler\s+deploy|functions\s+deploy|secrets\s+set|db\s+push|terraform\b[^\n]*\bapply"
    r"|npm\s+run\s+deploy|wrangler\s+secret\s+put|sync_supabase_secrets", re.I)
# Every justfile the estate runs recipes from. w0m-web/w0m-cf/wom7authz link to w0m-api's.
JUSTFILES = ("justfile", "w0m-api/justfile", "w0m-ext/justfile", "w0m-sec/justfile",
             "w0m-mlx/w0m-mlx/justfile")


def recipe_body(rec: dict) -> str:
    return "\n".join("".join(f if isinstance(f, str) else "{…}" for f in line)
                     for line in rec.get("body") or [])


def confirm_args(rec: dict) -> list[str]:
    out: list[str] = []
    for dep in rec.get("dependencies") or []:
        if dep.get("recipe") == "_confirm":
            out += [a for a in dep.get("arguments") or [] if isinstance(a, str)]
    return out


def wiring_problems(dump: dict, described: set[str]) -> list[str]:
    """Every deploy-shaped recipe with no `_confirm`, and every `_confirm` naming an undescribed step."""
    out: list[str] = []
    for name, rec in sorted((dump.get("recipes") or {}).items()):
        args = confirm_args(rec)
        m = DEPLOY_SHAPED.search(recipe_body(rec))
        if m and not args:
            out.append(f"`{name}` runs `{m.group(0)}` with no `_confirm`")
        out += [f"`{name}` confirms `{a}`, which confirm-policy.json does not describe"
                for a in args if a not in described]
    return out


def dump_justfile(rel: str) -> tuple[dict | None, str]:
    path = ESTATE / rel
    if not path.exists():
        return None, f"{rel} does not exist"
    try:
        r = subprocess.run(["just", "--justfile", str(path), "--dump", "--dump-format", "json"],
                           cwd=path.parent, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"cannot run just: {exc}"
    if r.returncode != 0:
        return None, f"just --dump failed for {rel}: {r.stderr.strip()[:160]}"
    return json.loads(r.stdout), ""


def main() -> int:
    print("▶ confirm-step red probes\n")
    clear()
    os.environ["W0M_CONFIRM_TOTP_FILE"] = "/tmp/test-isolated-totp.secret"
    os.environ.pop("W0M_CONFIRM_TOTP_SECRET", None)

    print("RED — the gate must withhold from an automated caller:")
    check("no consent, no tty → blocked", run("deploy-web").returncode == 1)
    check("piped 'yes' does NOT satisfy it", run("deploy-web", stdin="yes\n").returncode == 1,
          "stdin must never be read — the prompt is on /dev/tty")
    check("piped 'yes' does NOT satisfy db-migrate", run("db-migrate", stdin="yes\n").returncode == 1)
    check("UNRECOGNISED step fails CLOSED", run("some-recipe-added-tomorrow").returncode == 1,
          "a recipe nobody classified must confirm, not pass")
    check("no consent file is written by a refused run", not CONSENT.exists(),
          "a blocked attempt must not leave consent behind")

    print("\nGREEN — a HUMAN AT A TERMINAL must be able to answer. This is the case that was")
    print("        shipped untested on 2026-08-10 and blocked the owner in a real terminal:")
    check("a pty stdin CAN confirm", pty_answer("deploy-web", "yes") == 0,
          "if this fails the gate is broken for humans, not strict")
    check("a pty stdin saying 'no' is refused", pty_answer("deploy-web", "no") == 1)

    # 2026-10-04: a real deploy aborted at `deploy-web` with "NOT confirmed" and NO reason: the owner saw `yes` on the prompt line, the Touch ID line never printed, and
    # nothing said why (the typed line had not been exactly `yes`, but a stray character, a leftover newline or a keyboard layout slip all looked identical).
    # A refusal of the typed answer must now say what kind of line it was, never echo it (a mistyped code is a secret), and name the layout case.
    for line, want in (("yes", "yes"), ("YES", "yes"), ("123456", "123456"), ("push", "push"), ("Orca", "orca"), ("mobile", "mobile"), ("", None), ("ye s", None), ("12345", None), ("1234567", None), ("\u043d\u0443\u044b", None)):
        with contextlib.redirect_stderr(io.StringIO()):
            got = gate._answer_from(line)
        check(f"_answer_from({line!r}) -> {want!r} (shared by both input channels)", got == want, repr(got))
    # The /dev/tty channel is the one a real terminal uses, and a pty cannot be relied on to reach it from every environment (an agent's shell reaches the stdin channel
    # instead), so drive it with a fake device: it must answer through the SAME function as the stdin channel.
    class _FakeTTY:
        def __init__(self, line: str) -> None:
            self.line = line

        def write(self, text: str) -> None:
            pass

        def flush(self) -> None:
            pass

        def readline(self) -> str:
            return self.line + "\n"

        def close(self) -> None:
            pass

    for line, want in (("yes", "yes"), ("123456", "123456"), ("", None), ("\u043d\u0443\u044b", None)):
        gate.open = lambda *a, _l=line, **k: _FakeTTY(_l)  # type: ignore[attr-defined]
        try:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                got = gate.prompt("deploy-web", "d", "r")
        finally:
            del gate.open  # type: ignore[attr-defined]
        check(f"the /dev/tty channel answers {line!r} -> {want!r}", got == want, repr(got))
        check(f"and refuses {line!r} with a reason" if want is None else f"and accepts {line!r} without a rejection note", (("✗" in err.getvalue()) == (want is None)), err.getvalue()[-160:])
    code_blank, out_blank = pty_run("deploy-web", "")
    check("an empty answer is refused and says it was empty", code_blank == 1 and "empty" in out_blank.lower(), out_blank[-200:])
    code_nonascii, out_nonascii = pty_run("deploy-web", "\u043d\u0443\u044b")
    check("a non-ASCII answer is refused and names the keyboard layout", code_nonascii == 1 and "layout" in out_nonascii.lower() and "non-ascii" in out_nonascii.lower(), out_nonascii[-240:])
    code_other, out_other = pty_run("deploy-web", "ye s")
    check("any other answer is refused and says it was not yes", code_other == 1 and "not 'yes'" in out_other, out_other[-240:])
    check("the refusal never echoes the typed text", "ye s" not in out_other.split("anything else to abort:")[-1].replace("ye s\r\n", "", 1) and "\u043d\u0443\u044b" not in out_nonascii.split("anything else to abort:")[-1].replace("\u043d\u0443\u044b\r\n", "", 1), out_other[-240:])
    code_bad6, out_bad6 = pty_run("deploy-web", "123456")
    check("a 6-digit answer still goes down the TOTP path, not the new message", code_bad6 == 1 and "not 'yes'" not in out_bad6, out_bad6[-240:])
    check("a correct yes is still accepted and prints no rejection note", pty_run("deploy-web", "yes")[0] == 0 and "not 'yes'" not in pty_run("deploy-web", "yes")[1])
    check("a pty stdin CAN confirm db-migrate", pty_answer("db-migrate", "yes") == 0)
    clear()

    print("\nGREEN — a granted consent must actually work, or the gate is unusable:")
    grant("deploy-all")
    check("chained step passes under an agreed root", run("deploy-web").returncode == 0)
    check("a second chained step also passes", run("deploy-cp").returncode == 0)

    print("\nGREEN — OWNER DECISION 2026-08-16: one yes covers deploy-all, db-migrate included:")
    # This assertion used to be the opposite — "one yes at the top must never carry a schema write".
    # The owner was shown the trade-off (a single consent now authorises an irreversible live schema
    # write, including migrations committed by someone else since they last looked) and chose the
    # single confirmation. Inverted rather than deleted, so the NEW contract is still guarded: if
    # somebody quietly puts db-migrate back into always_confirm, this fails and says why.
    check("db-migrate is COVERED by an agreed deploy-all",
          run("db-migrate").returncode == 0,
          "owner 2026-08-16 chose one confirmation for deploy-all; re-adding it to always_confirm "
          "reverses a decision rather than fixing a bug")
    check("db-migrate is SINGLE-USE: second run under same root consent is WITHHELD (T541)",
          run("db-migrate").returncode == 1,
          "once consumed by the chain, standalone db-migrate must prompt")

    print("\nRED — the carve-out still holds for everything else in always_confirm:")
    check("db-backup still blocked under agreed deploy-all", run("db-backup").returncode == 1)
    check("db-reset still blocked under agreed deploy-all", run("db-reset").returncode == 1)

    print("\nRED — and db-migrate ALONE still needs its own yes (no root consent in play):")
    clear()
    check("standalone db-migrate is refused without consent", run("db-migrate").returncode == 1,
          "removing it from always_confirm must not make a bare `just db-migrate` silent")

    print("\nRED / GREEN — T541: CONSENT LIFECYCLE CLEANUP (--clear)")
    grant("deploy-all")
    r_clear = run("--clear")
    check("--clear exits 0 and removes consent file", r_clear.returncode == 0 and not CONSENT.exists())
    grant("deploy-all")

    print("\nRED — consent is bound to the tree and to time:")
    c = json.loads(CONSENT.read_text())
    c["head"] = "deadbee"
    CONSENT.write_text(json.dumps(c))
    check("consent dies when HEAD moves", run("deploy-web").returncode == 1,
          "what was agreed to is not what would ship now")
    c["head"] = head()
    c["expires"] = time.time() - 1
    CONSENT.write_text(json.dumps(c))
    check("consent dies when it expires", run("deploy-web").returncode == 1)
    clear()

    print("\nRED — the policy itself must be present and sane:")
    check("every root's steps are described",
          all(s in json.loads(POLICY.read_text())["steps"]
              for r in json.loads(POLICY.read_text())["roots"].values() for s in r
              if not s.startswith(("check-", "_"))),
          "an undescribed step prompts with no explanation of what it does")
    check("always_confirm is non-empty",
          bool(json.loads(POLICY.read_text())["always_confirm"]),
          "an empty carve-out silently turns one yes into total consent")

    print("\nRED — T435 LAYER 1: an agent session is refused, whatever it can type. On 2026-09-17 agy")
    print("       ran `just db-migrate` on its own pty, sent `yes`, and migrations reached live:")
    check("agent + a pty answering 'yes' is REFUSED (the 2026-09-17 shape)",
          pty_answer("db-migrate", "yes", caller="agent") == 1,
          "a terminal proves a terminal, not a person")
    grant("deploy-all")
    check("agent CANNOT ride a live root consent a human granted",
          run("deploy-web", caller="agent").returncode == 1,
          "consent is a file; an agent refused at the prompt must not pass on the human's yes")
    check("agent is refused for an always_confirm step too", run("db-backup", caller="agent").returncode == 1)
    check("unmeasurable ancestry REFUSES rather than passing",
          run("deploy-web", caller="unmeasurable").returncode == 1,
          "could-not-tell must never render as not-an-agent (T242)")
    clear()
    for label, (table, expected) in CHAINS.items():
        got = gate.detect_agent(table, start=500, env={})
        check(f"detects {expected or 'NO agent'} — {label}", got.measurable and got.agent == expected,
              f"got {got}")
    broken = {500: (400, "python3", "python3 confirm_step.py deploy"), 400: (399, "zsh", "zsh")}
    got = gate.detect_agent(broken, start=500, env={})
    check("a chain that breaks before launchd is UNMEASURABLE", not got.measurable and got.agent is None,
          f"got {got}")
    human_table = CHAINS["a HUMAN in an Orca terminal"][0]
    for marker in gate.AGENT_ENV_MARKERS:
        got = gate.detect_agent(human_table, start=500, env={marker: "1"})
        check(f"env marker {marker} is an agent even under a human-looking chain", got.agent == marker,
              f"got {got}")
    real_verdict = gate.detect_agent()
    r = run("deploy-web", caller="real")
    want = "invoked from inside an agent session" if real_verdict.agent else "no terminal to ask on"
    check(f"REAL gate agrees with the real ancestry ({real_verdict.agent or 'not an agent'})",
          r.returncode == 1 and want in r.stderr,
          f"expected {want!r}; stderr: {r.stderr.strip()[-160:]}")

    print("\nRED — T435 LAYER 3: a typed 'yes' is not enough; the device owner must confirm in the")
    print("       macOS dialog (owner 2026-09-24: 'macOS Touch ID prompt is great here'):")
    check("pty 'yes' but the Touch ID dialog cancelled → refused",
          pty_answer("deploy-web", "yes", presence="no") == 1)
    check("pty 'yes' but LocalAuthentication unavailable → refused (fail closed)",
          pty_answer("deploy-web", "yes", presence="unavailable") == 1)
    check("a refused dialog on a ROOT writes no consent",
          pty_answer("deploy-all", "yes", presence="no") == 1 and not CONSENT.exists(),
          "a root that was not confirmed must not cover its chain")
    clear()
    if sys.platform == "darwin" and shutil.which("xcrun"):
        tc = subprocess.run(["xcrun", "swiftc", "-typecheck", str(PRESENCE_SOURCE)],
                            capture_output=True, text=True, timeout=180)
        check("human_presence.swift type-checks (built without ever showing the dialog)",
              tc.returncode == 0, tc.stderr.strip()[:200])
    else:
        check("human_presence.swift type-checks (built without ever showing the dialog)", True)

    print("\nRED / GREEN — T471: CROSS-DEVICE HUMAN PRESENCE (TOTP & ORCA MOBILE RELAY)")
    totp_secret = "JBSWY3DPEHPK3PXP"
    os.environ["W0M_CONFIRM_TOTP_SECRET"] = totp_secret
    valid_code = gate.generate_totp(totp_secret)
    check("pty answering valid 6-digit TOTP confirms with exit 0",
          pty_answer("deploy-web", valid_code) == 0)
    check("pty answering invalid 6-digit TOTP code refuses with exit 1",
          pty_answer("deploy-web", "000000") == 1)

    os.environ.pop("W0M_CONFIRM_TOTP_SECRET", None)
    os.environ["W0M_CONFIRM_TOTP_FILE"] = "/tmp/nonexistent-totp.secret"
    check("pty answering TOTP without secret configured refuses with exit 1",
          pty_answer("deploy-web", valid_code) == 1)

    os.environ["W0M_CONFIRM_TOTP_SECRET"] = totp_secret
    check("agent session attempting TOTP is refused at Layer 1 with exit 1",
          pty_answer("deploy-web", valid_code, caller="agent") == 1)

    tmp_orca = Path(tempfile.mkdtemp(prefix="orca-test-"))
    os.environ["W0M_CONFIRM_ORCA_DIR"] = str(tmp_orca)
    gate.CONFIRM_DIR = tmp_orca
    gate.REQUESTS_DIR = tmp_orca / "requests"
    gate.RESPONSES_DIR = tmp_orca / "responses"

    def _auto_approve() -> None:
        for _ in range(50):
            reqs = list(gate.REQUESTS_DIR.glob("*.json"))
            if reqs:
                gate.approve_request(reqs[0].stem, "orca_mobile_test")
                return
            time.sleep(0.1)

    th = threading.Thread(target=_auto_approve, daemon=True)
    th.start()
    check("Orca mobile push request dispatched and approved confirms with exit 0",
          pty_answer("deploy-web", "push") == 0)

    def _bad_nonce_respond() -> None:
        for _ in range(50):
            reqs = list(gate.REQUESTS_DIR.glob("*.json"))
            if reqs:
                req_id = reqs[0].stem
                gate.RESPONSES_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
                res_path = gate.RESPONSES_DIR / f"{req_id}.json"
                res_path.write_text(json.dumps({
                    "id": req_id,
                    "nonce": "mismatched-nonce-value",
                    "head": "mismatched-head",
                    "status": "approved",
                    "device": "unauthorized_device",
                }))
                return
            time.sleep(0.1)

    th2 = threading.Thread(target=_bad_nonce_respond, daemon=True)
    th2.start()
    check("Orca mobile push response with mismatched nonce fails closed with exit 1",
          pty_answer("deploy-web", "push") == 1)

    check("push option falls back to mobile TOTP when no relay responds",
          pty_answer("deploy-web", f"push\n{valid_code}") == 0)
    os.environ.pop("W0M_CONFIRM_TOTP_SECRET", None)
    os.environ.pop("W0M_CONFIRM_TOTP_FILE", None)
    os.environ.pop("W0M_CONFIRM_ORCA_DIR", None)

    print("\nRED — T435 AC4: every recipe that mutates production is wired to the gate. Before this,")
    print("       14 were not — Claude ran the ungated `just deploy-workers` against prod on 2026-08-21:")
    described = set(json.loads(POLICY.read_text())["steps"])
    for rel in JUSTFILES:
        dump, err = dump_justfile(rel)
        problems = [f"UNMEASURABLE — {err}"] if dump is None else wiring_problems(dump, described)
        check(f"{rel}: every deploy-shaped recipe depends on `_confirm`", not problems,
              " · ".join(problems[:4]) + (f" (+{len(problems) - 4} more)" if len(problems) > 4 else ""))
    bad = {"recipes": {"ship": {"body": [["@cd x && pnpm exec wrangler deploy --var V:", ["v"]]],
                                "dependencies": []}}}
    check("MUTATION: an ungated `wrangler deploy` recipe is flagged", bool(wiring_problems(bad, described)),
          "a detector that finds nothing looks exactly like a clean estate")
    bad["recipes"]["ship"]["dependencies"] = [{"recipe": "_confirm", "arguments": ["deploy-web"]}]
    check("MUTATION: the same recipe wired to `_confirm` is clean", not wiring_problems(bad, described))
    bad["recipes"]["ship"]["dependencies"] = [{"recipe": "_confirm", "arguments": ["not-a-step"]}]
    check("MUTATION: `_confirm` naming an undescribed step is flagged", bool(wiring_problems(bad, described)))

    policy = json.loads(POLICY.read_text())

    print("\nRED — T407: the PROSE describing this gate must match the POLICY DATA.")
    print("       Ten claims across these four surfaces described the pre-2026-08-16 behaviour")
    print("       for 34 days while every behavioural probe above stayed green:")
    surface_text: dict[str, str] = {}
    for rel in PROSE_SURFACES:
        path = ESTATE / rel
        try:
            raw, err = path.read_text(), ""
        except OSError as exc:
            raw, err = "", f"cannot read {path}: {exc.strerror}"
        surface_text[rel] = "\n\n".join(prose_regions(rel, raw) if raw.strip() else [])
        problems = surface_problems(rel, raw, policy, err)
        check(f"{rel} agrees with confirm-policy.json", not problems,
              " · ".join(problems[:3]) if problems else "")

    print("\n       MUTATION — a silent detector and a correct one look identical, so prove it")
    print("       still catches the exact text T407 removed:")
    check("flags the pre-T407 db-migrate carve-out claim",
          bool(prose_contradictions(
              "`deploy-all` additionally re-prompts for `db-migrate`, because a schema write is a "
              "different kind of irreversible from shipping a Worker.", policy)),
          "this is the sentence that was wrong; if it passes, the check is decorative")
    check("flags the pre-T407 table row",
          bool(prose_contradictions(
              "| `just deploy-all` | once at the root, **then again for `db-migrate`** |", policy)),
          "table rows have no sentence punctuation — claim_units must still isolate them")
    check("flags the pre-T407 TTL claim",
          bool(prose_contradictions("Consent lasts **15 minutes** and is bound to the git HEAD.", policy)))
    check("flags the INVERSE drift too (an always_confirm step described as covered)",
          bool(prose_contradictions("`db-reset` is covered by an agreed `deploy-all`.", policy)),
          "drift has two directions; a one-way check passes the day the policy flips")
    check("an EMPTY surface FAILS rather than passing",
          bool(surface_problems("docs/DEPLOY-CONFIRM.md", "", policy)),
          "no prose read == not checked == fail; a two-state version goes green on zero bytes")
    check("an UNREADABLE surface FAILS rather than passing",
          bool(surface_problems("justfile", "", policy, "cannot read it: No such file or directory")),
          "the justfile symlink crosses into w0m-api and does break — this is not hypothetical")
    check("stays SILENT on the corrected text",
          not prose_contradictions(
              "A standalone `just db-migrate` still asks on its own. Consent lasts 45 min.", policy),
          "a detector that flags the fix as well as the defect is unusable")

    print("\n       And the advertised probe count must be the REAL one — it had drifted too")
    print("       (docs said 16, the justfile said 13, the suite ran 18):")
    total = passes + len(failures) + 1  # +1: this check itself, which has not run yet
    wrong = {rel: c for rel, text in surface_text.items()
             for c in declared_probe_counts(text) if c != total}
    check("every surface advertising a probe count states the real one", not wrong,
          f"declared {wrong}, actual {total}")

    print(f"\n{'❌' if failures else '✅'} confirm-step: {passes} passed, {len(failures)} failed")
    for f in failures:
        print(f"   · {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    # try/finally is load-bearing, not tidiness: main() GRANTS real consent for `deploy-all`
    # at the real $TMPDIR path. If it threw between grant and clear, it would leave a live
    # deploy consent on disk — a test that arms the thing it is testing.
    try:
        raise SystemExit(main())
    finally:
        clear()
