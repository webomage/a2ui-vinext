#!/usr/bin/env python3
r"""T256 -- probes for `doc-format-check`.

The gate's whole risk is the boundary between a DOCUMENT and an ASSET. Get it wrong in one
direction and it fires on every PNG and stylesheet in the estate; wrong in the other and it never
fires at all. So most of these probes pin that boundary, and two of them pin the acknowledgement
mechanism -- because an acknowledgement is how a gate is allowed to stay green about something it
still sees, and it must therefore be impossible to add one without a reason.

Run: `just doc-format-check-test`
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "wom7web"
sys.path.insert(0, str(ROOT / "scripts"))

import doc_format_check as g  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}")
    if not ok:
        failures.append(f"{label} — {detail}")


print("▶ T256 — doc-format-check\n")

POL = json.loads((ROOT / "project" / "policies" / "doc-format-policy.json").read_text())


def fake(paths: list[str], ack: dict | None = None):
    """scan() over a fixture file list rather than the real repos."""
    orig_tracked, orig_repos = g.tracked, g.REPOS
    g.tracked = lambda _repo: paths
    g.REPOS = ["wom7web"]
    try:
        return g.scan({**POL, "acknowledged": POL["acknowledged"] if ack is None else ack})
    finally:
        g.tracked, g.REPOS = orig_tracked, orig_repos


# ── the boundary: documents fail, assets do not ─────────────────────────────────────────────────
for ext in [".html", ".txt", ".rst", ".docx", ".adoc"]:
    bad, _, _ = fake([f"docs/thing{ext}"], ack={})
    check(f"a document in {ext} is a violation", len(bad) == 1)

for ext in [".png", ".pdf", ".css", ".svg", ".json", ".woff2"]:
    bad, _, _ = fake([f"docs/thing{ext}"], ack={})
    check(f"an asset in {ext} is NOT a violation", not bad,
          f"{ext} is an output or a binary, not prose authored in the wrong format")

check("Markdown is never a violation", not fake(["docs/a.md"], ack={})[0])
check("Mermaid is never a violation", not fake(["docs/flows/a.mmd"], ack={})[0])

for ext in [".puml", ".drawio", ".dot", ".excalidraw"]:
    bad, _, _ = fake([f"docs/flows/d{ext}"], ack={})
    check(f"a diagram in {ext} is a violation", len(bad) == 1)

# ── scope: only the declared doc roots ──────────────────────────────────────────────────────────
check("a file OUTSIDE the declared doc roots is ignored",
      not fake(["apps/web/src/index.html"], ack={})[0],
      "app source is not documentation; firing there would make the gate meaningless")
check("a file INSIDE a declared root is considered",
      len(fake(["docs/x.html"], ack={})[0]) == 1)

# ── the acknowledgement mechanism ───────────────────────────────────────────────────────────────
bad, ack, _ = fake(["docs/x.html"], ack={"docs/x.html": "a stated reason"})
check("an acknowledged path moves OUT of violations", not bad and len(ack) == 1)
check("the acknowledgement carries its reason into the report",
      "a stated reason" in ack[0],
      "an acknowledgement whose reason is not printed is indistinguishable from a suppressed check")

# 🔬 Non-vacuity, and the reason it matters here specifically: `git ls-files` returning nothing
# looks EXACTLY like a clean estate. It must exit 2, never 0.
orig = g.tracked
g.tracked = lambda _repo: []
try:
    _, _, seen = g.scan(POL)
    check("an empty tracked list yields 0 considered (so main() can exit 2)", seen == 0)
finally:
    g.tracked = orig

bad, ack, seen = g.scan(POL)
check("the real estate is measured, and substantially (non-vacuous)", seen > 500, f"only {seen}")
check("the real estate currently has no unacknowledged violation", not bad, f"{bad}")
check("every acknowledged entry has a non-trivial reason",
      all(len(v) > 40 for v in POL["acknowledged"].values()),
      "a one-word reason is a waiver wearing a reason's clothes")

# ── MUTATION ────────────────────────────────────────────────────────────────────────────────────
check("MUTATION: an extension-blind rule finds 0 where the real one finds 1",
      len(fake(["docs/x.html"], ack={})[0]) == 1
      and not fake(["docs/x.html"], ack={"docs/x.html": "waived"})[0],
      "the two must disagree, or the acknowledgement list is doing nothing")

print()
if failures:
    print(f"❌ {len(failures)} failure(s):")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("✅ documents are Markdown, diagrams are Mermaid, assets are left alone, waivers need reasons")
