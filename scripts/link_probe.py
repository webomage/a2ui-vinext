#!/usr/bin/env python3
"""Which link form does THIS terminal make clickable? Run it, click, report the numbers.

Written because guessing cost two rounds. `just tasks` used OSC 8 with a `file://` target; the
owner reports nothing is clickable in the Claude Code terminal, and OSC 8 with `https://` was
clickable in a different one. Rather than iterate blind, print every plausible form of the SAME
target and let the terminal answer.

  · 3 and 6 clickable, 1/2/8 not  ⇒ OSC 8 works, `file:` targets are refused
  · 6 only                        ⇒ OSC 8 unsupported; only auto-detected bare https
  · nothing                       ⇒ no linkification at all; keep the label short and move on
"""
import os
import sys

TARGET = "/Users/proto/Projects/@self/@wom/w0m-web/project/tickets/T2.md"
ISSUE = "https://github.com/casualuser/webomage.com/issues/3"


def osc8(label: str, target: str) -> str:
    return f"\033]8;;{target}\033\\{label}\033]8;;\033\\"


print("▶ link-form probe — click each label; report which NUMBERS are clickable\n")
print(f"  TERM={os.environ.get('TERM','(unset)')!r} "
      f"TERM_PROGRAM={os.environ.get('TERM_PROGRAM','(unset)')!r} "
      f"CLAUDECODE={os.environ.get('CLAUDECODE','(unset)')!r} "
      f"tty={sys.stdout.isatty()}\n")

rows = [
    ("1", "OSC 8 → file://host/path   ", osc8("T2", f"file://{os.uname().nodename}{TARGET}")),
    ("2", "OSC 8 → file:///path       ", osc8("T2", f"file://{TARGET}")),
    ("3", "OSC 8 → https:// (control) ", osc8("#3", ISSUE)),
    ("4", "OSC 8 → vscode://file/path ", osc8("T2", f"vscode://file{TARGET}")),
    ("5", "bare text  file:///path    ", f"file://{TARGET}"),
    ("6", "bare text  https:// (ctrl) ", ISSUE),
    ("7", "bare absolute path         ", TARGET),
    ("8", "path:line                  ", f"{TARGET}:1"),
    ("9", "markdown [label](path)     ", f"[T2]({TARGET})"),
]
for n, what, rendered in rows:
    print(f"  {n}. {what}  {rendered}")
print("\n  (1, 2 and 4 all show the label `T2`; if none of those are clickable, OSC 8 is not\n"
      "   honoured here and 3 will be dead too — which is the answer, not a failure.)")
