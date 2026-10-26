#!/usr/bin/env python3
"""T267 — probes for the deploy-in-flight hook's SCOPE.

🔴 Why this file exists. The hook scanned `ps` HOST-WIDE for any `just deploy*`, so on 2026-08-23
another project's apex production deploy blocked a commit in `w0m-web` — a repo whose
`confirm_step.py` that deploy has never heard of. The fact being protected is repo-scoped
(`confirm_step.py:148` pins `head_sha()` to `cwd=WEB_ROOT`); the detection was machine-scoped.

🔑 AND THE OBVIOUS FIX IS WRONG, which is why the CONTROL below is the most important probe here.
"Block only if the deploy's git toplevel is this repo" reads like a tightening and is a silent
removal: a w0m deploy runs from `w0m-api/`, a DIFFERENT repo under the same estate, so that rule
unblocks precisely the case the hook exists for. The boundary is the ESTATE, declared at
`.w0m/sdlc.json -> root`.

⚠️ Every probe stubs `subprocess.run`. Nothing here inspects the real process table, so the suite
is deterministic and cannot be green merely because no deploy happened to be running.

Run: `just deploy-in-flight-test`
"""
from __future__ import annotations

import subprocess as _sp
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "w0m-web"
sys.path.insert(0, str(ROOT / "scripts"))

import deploy_in_flight_check as dif  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global checks
    checks += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        failures.append(f"{label}{' — ' + detail if detail else ''}")


ESTATE = dif.estate_root()
API = str(WEB.parent / "w0m-api")
FOREIGN = "/Users/proto/Projects/_self/1945"


def fake(ps_lines: list[str], cwds: dict[str, str | None], *, lsof_broken: bool = False,
         alive: set[str] | None = None):
    """Stub subprocess.run for ps / lsof / ps -p.

    cwds maps pid -> path, or pid -> None meaning "lsof returned no `n` field".
    `alive` decides what `ps -p <pid>` says for those, which is what separates GONE from
    UNMEASURABLE.
    """
    alive = alive or set()

    def run(cmd, *a, **kw):
        if cmd[:2] == ["ps", "-eo"]:
            return _sp.CompletedProcess(cmd, 0, stdout="\n".join(ps_lines), stderr="")
        if cmd[0] == "lsof":
            if lsof_broken:
                raise OSError("lsof not found")
            pid = cmd[cmd.index("-p") + 1]
            path = cwds.get(pid)
            # ⚠️ Real `-F` output: a descriptor line THEN the tagged path. The `fcwd` line is here
            # on purpose — a parser taking line 2 would return the literal string "fcwd".
            out = "p" + pid + "\nfcwd\n" + ("n" + path if path else "")
            return _sp.CompletedProcess(cmd, 0, stdout=out, stderr="")
        if cmd[:2] == ["ps", "-p"]:
            return _sp.CompletedProcess(cmd, 0 if cmd[2] in alive else 1, stdout="", stderr="")
        return _sp.CompletedProcess(cmd, 0, stdout="", stderr="")
    return run


print("\nT267 — deploy-in-flight scope\n")

check("the estate root is READ from .w0m/sdlc.json, not hardcoded",
      ESTATE is not None and ESTATE.name in ("@wom", "w0m"),
      f"got {ESTATE} — AC3; a path literal here is the same defect one layer along")

_real = dif.subprocess.run

# ── AC1: a deploy OUTSIDE the estate does not block ──────────────────────────────────────────
dif.subprocess.run = fake(["111 /opt/homebrew/bin/just deploy-prod"], {"111": FOREIGN})
blocking, unmeasurable = dif.running_deploys()
check("AC1: a deploy OUTSIDE the declared estate does NOT block",
      blocking == [] and unmeasurable == [],
      "this is the 2026-08-23 false positive — 1945's apex deploy stopped a commit here")

# ── AC2: THE CONTROL. A w0m deploy from w0m-api/ STILL blocks. ───────────────────────────────
# 🔴 If this fails, the change is indistinguishable from deleting the hook.
dif.subprocess.run = fake(["222 /opt/homebrew/bin/just deploy-all"], {"222": API})
blocking, unmeasurable = dif.running_deploys()
check("AC2 CONTROL: a w0m deploy running from w0m-api/ STILL blocks",
      len(blocking) == 1 and not unmeasurable,
      "deploys run from w0m-api/, NOT w0m-web/ — the naive 'same repo' predicate would unblock "
      "the exact case this hook exists for, while reading as a tightening")

# ── AC4: the three states ────────────────────────────────────────────────────────────────────
# gone = a MEASUREMENT (the deploy ended between two syscalls) -> allow.
dif.subprocess.run = fake(["333 /opt/homebrew/bin/just deploy"], {"333": None}, alive=set())
blocking, unmeasurable = dif.running_deploys()
check("AC4: a process that EXITED mid-check resolves to gone, and does not block",
      blocking == [] and unmeasurable == [],
      "observed twice live — pids 35132 and 56562 both vanished between the ps scan and the "
      "cwd lookup, so this is the common path, not an edge")

# unmeasurable = we know nothing -> FAIL CLOSED.
dif.subprocess.run = fake(["444 /opt/homebrew/bin/just deploy"], {"444": None}, alive={"444"})
blocking, unmeasurable = dif.running_deploys()
check("AC4: a LIVE process whose cwd cannot be read is UNMEASURABLE, not allowed",
      blocking == [] and len(unmeasurable) == 1,
      "still alive but unreadable — certifying a commit against a deploy you cannot locate is a "
      "guess, so it fails closed")

dif.subprocess.run = fake(["555 /opt/homebrew/bin/just deploy"], {"555": API}, lsof_broken=True)
blocking, unmeasurable = dif.running_deploys()
check("AC4: lsof missing entirely is UNMEASURABLE, never a silent pass",
      blocking == [] and len(unmeasurable) == 1)

# 🔑 The two are reported SEPARATELY — the T242 rule. Same words for both is the defect.
check("AC4: unmeasurable is a distinct return channel from blocking",
      isinstance(dif.running_deploys(), tuple) and len(dif.running_deploys()) == 2,
      "'could not measure' and 'found one' must not print the same thing")

# ── AC5: parse by FIELD TAG, not line offset ─────────────────────────────────────────────────
# The stub emits `p<pid>` then `fcwd` then `n<path>`. A parser taking line 2 gets "fcwd".
dif.subprocess.run = fake(["666 /opt/homebrew/bin/just deploy"], {"666": API})
cwd, state = dif.process_cwd("666")
check("AC5: the cwd is taken from the `n` FIELD, not from a line offset",
      cwd == API and state == "ok",
      "line 2 of -F output is `fcwd`, the descriptor — taking it yields a non-path that matches "
      "no estate root, which fails OPEN")

# ── non-deploy processes are still ignored ───────────────────────────────────────────────────
dif.subprocess.run = fake(["777 /opt/homebrew/bin/just test", "888 /bin/zsh just deploy-all"],
                          {"777": API, "888": API})
blocking, unmeasurable = dif.running_deploys()
check("CONTROL: `just test` is not a deploy, and a SHELL whose args mention `just deploy` is not one either",
      blocking == [] and unmeasurable == [],
      "the executable must be `just` — the first version of this hook matched the very shell "
      "running it, because that shell's script text contained the words")

# ── MUTATION: prove these probes DISCRIMINATE, by re-running them under the OLD rule ─────────
# 🔑 A probe that passes tells you nothing until you have seen it fail. The old rule is short, so
# the cheapest honest check is to apply it to the same inputs and assert it gets them WRONG.
# Without this section the file would be green against a hook that never changed.
def old_running_deploys(ps_out: str) -> list[str]:
    """The rule as it stood until 2026-08-24: match `just deploy*` anywhere on the host, no scope."""
    hits = []
    for line in ps_out.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[1].rsplit("/", 1)[-1] != "just":
            continue
        for arg in parts[2:]:
            if arg.startswith("-"):
                continue
            if dif.DEPLOY_RE.match(arg):
                hits.append(line.strip())
            break
    return hits


_foreign_ps = "111 /opt/homebrew/bin/just deploy-prod"
_api_ps = "222 /opt/homebrew/bin/just deploy-all"

check("MUTATION: the OLD rule BLOCKS on the foreign deploy (the new one does not)",
      len(old_running_deploys(_foreign_ps)) == 1,
      "if the old rule also allowed it, AC1 above would be asserting nothing — this is the "
      "2026-08-23 false positive, reproduced")
check("MUTATION: old and new AGREE that a w0m-api deploy blocks",
      len(old_running_deploys(_api_ps)) == 1,
      "the change must be confined to the out-of-estate case; if it moved this verdict it is not "
      "a narrowing, it is a different gate")

dif.subprocess.run = _real

print()
if failures:
    print(f"  {len(failures)} of {checks} failed:")
    for f in failures:
        print(f"     - {f}")
    print("\ndeploy-in-flight scope: FAILED")
    sys.exit(1)
print(f"deploy-in-flight scope: OK — {checks}/{checks}; scoped to the declared estate, and a "
      "w0m-api deploy still blocks")
