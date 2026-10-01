#!/usr/bin/env python3
"""Do the Gauge specs actually test anything? — the reality check `gauge validate` cannot do.

`gauge validate specs` answers "does every step have an implementation?" and reports **No errors
found** across all 190 specs. That is a real check, and it is not the same question as "would any of
this fail if the product broke". A step implemented as `// Visual check` validates perfectly.

Three findings this reports, in descending severity:

1. **STUB identities** — a step that establishes WHO is acting but does nothing. The scenario then
   runs as somebody else and its assertion passes for the wrong reason. This is worse than an absent
   test: an absent test is visibly absent.
2. **Scenarios that cannot fail** — no step in the scenario verifies anything, transitively.
   Setup/teardown scenarios are excluded by name; they legitimately assert nothing.
3. **Claim-shaped steps that verify nothing** — the step NAME makes an assertion ("… should be
   visible") and the body does not. The name is the lie, not the body.

⚠️ On the assertion vocabulary. A first pass counted only `expect(`/`assert` and over-reported by
9 scenarios, because Playwright's `waitForURL`/`waitForSelector` ARE assertions — they throw on
timeout. Widening the vocabulary is what makes this honest; narrowing it manufactures findings.
The audit tool commits the defect it hunts unless the vocabulary is stated and reviewable, so it is
a module constant, not a literal buried in a function.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "wom7web"
SPECS, TESTS = WEB / "specs", WEB / "tests"

ASSERT = re.compile(
    r"\bexpect\(|\bassert|throw new|\.toBe|\.toContain|\.toHave|fail\(|"
    r"waitForURL|waitForSelector|waitForResponse|waitForFunction|\.isVisible\(|"
    r"\.textContent\(|\bcheckA11y|toMatchSnapshot"
)
CLAIM = re.compile(
    r"\b(should|must|is displayed|are displayed|is visible|are visible|returns?|contains?|"
    r"has |have |shows?|displays?|is not|are not|no longer|is present|exists?|match(es)?)\b", re.I)
# ⚠️ Matched against COMMENT TEXT ONLY, never raw source. A first version scanned the whole body and
# flagged 9 real steps because `placeholder*="Search"` appears in their CSS selectors — the exact
# "matched a name the inspected thing supplies" trap. `placeholder` is gone from the vocabulary too.
STUB = re.compile(r"\bstub\b|not (yet )?implemented|TODO|FIXME|for now", re.I)
COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
SETUP = re.compile(r"^(initialize|teardown|setup|cleanup)\b", re.I)

STEP = re.compile(r'@Step\(\s*"([^"]+)"\s*\)\s*\n\s*public\s+(?:async\s+)?(\w+)\s*\(', re.M)
METH = re.compile(r"(?:public|private|protected)?\s*(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{", re.M)


def _bodies(src: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in METH.finditer(src):
        i, depth = m.end() - 1, 0
        j = i
        for j in range(i, len(src)):
            if src[j] == "{":
                depth += 1
            elif src[j] == "}":
                depth -= 1
                if depth == 0:
                    break
        out[m.group(1)] = src[i:j + 1]
    return out


def main() -> int:
    srcs = {f: f.read_text(encoding="utf-8", errors="replace") for f in sorted(TESTS.rglob("*.ts"))}
    if not srcs:
        print("  ❌ no step implementations found — the matcher is broken, not the harness empty.")
        return 2
    allb: dict[str, str] = {}
    for s in srcs.values():
        allb.update(_bodies(s))

    def verifies(body: str, depth: int = 0, seen: set[str] | None = None) -> bool:
        if ASSERT.search(body):
            return True
        if depth >= 3:
            return False
        seen = seen or set()
        callees = set(re.findall(r"this\.(\w+)\s*\(", body)) | set(re.findall(r"await\s+(\w+)\s*\(", body))
        for c in callees:
            if c in seen or c not in allb:
                continue
            seen.add(c)
            if verifies(allb[c], depth + 1, seen):
                return True
        return False

    registry, stubs, liars = [], [], []
    for f, s in srcs.items():
        for m in STEP.finditer(s):
            name, fn = m.group(1), m.group(2)
            if fn not in allb:
                continue
            body = allb[fn]
            ok = verifies(body)
            rx = re.compile("^" + re.sub(r"<[^>]+>", r'("[^"]*"|<[^>]+>|[^ ]+)',
                            re.escape(name).replace("\\<", "<").replace("\\>", ">")) + "$", re.I)
            registry.append((rx, ok))
            inner = "\n".join(body.splitlines()[1:-1]).strip()
            comments = " ".join(COMMENT.findall(inner))
            code = COMMENT.sub("", inner).strip()
            # A stub is a step that DOES nothing: no code at all, or code that only logs, and whose
            # own comment admits it. Both arms require the absence of any verification.
            is_stub = not ok and (not code or (STUB.search(comments) and
                      not re.search(r"\b(click|fill|press|goto|navigate|type|select|check|request)\b", code, re.I)))
            # Order matters: a CLAIM that verifies nothing is a false assertion, not a stub action.
            # Both have empty bodies; only the claim's NAME promises verification.
            if CLAIM.search(name) and not ok:
                liars.append((f.name, name))
            elif is_stub:
                stubs.append((f.name, name, (inner.splitlines()[0][:70] if inner else "(empty body)")))

    if not registry:
        print("  ❌ no @Step implementations parsed — broken matcher.")
        return 2

    def lookup(step: str) -> bool | None:
        for rx, ok in registry:
            if rx.match(step):
                return ok
        return None

    specs = sorted(SPECS.rglob("*.spec"))
    if not specs:
        print("  ❌ no specs found — broken path, not a clean corpus.")
        return 2

    total = 0
    mute: list[tuple[str, str, int]] = []

    def scan(spec_path: Path) -> None:
        """Walk one spec's scenarios. Written as a flat loop over (heading, steps) pairs rather
        than a nested closure — the closure version type-checked as unreachable, because `cur`
        was inferred `None` at definition time and mypy could not see the reassignment."""
        nonlocal total
        scenarios: list[tuple[str, list[str]]] = []
        for ln in spec_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if ln.startswith("## "):
                scenarios.append((ln[3:].strip(), []))
            elif ln.strip().startswith("* ") and scenarios:
                scenarios[-1][1].append(ln.strip()[2:].strip())
        for name, steps in scenarios:
            if SETUP.match(name):
                continue
            real = [st for st in steps if lookup(st) is not None]
            if not real:
                continue
            total += 1
            if not any(lookup(st) for st in real):
                mute.append((str(spec_path.relative_to(ROOT)), name, len(real)))

    for sp in specs:
        scan(sp)

    print(f"  ▶ spec reality — {len(specs)} specs · {total} scenarios (setup/teardown excluded) · "
          f"{len(registry)} implemented steps")

    if stubs:
        print(f"\n  🔴 STUB actions/identities — the step does NOTHING, so the scenario acts as someone/something else ({len(stubs)}):")
        for fname, n, first in stubs:
            print(f"      · {n}\n          {fname} — {first}")
    if mute:
        print(f"\n  🔴 scenarios where NOT ONE step verifies anything ({len(mute)}):")
        for path_s, sc, n in mute:
            print(f"      · {path_s:<42} {sc[:44]:<44} {n} step(s)")
    if liars:
        print(f"\n  🔴 claim-shaped steps that verify NOTHING — the step NAME is the lie, not the body ({len(liars)}):")
        for fname, n in liars:
            print(f"      · {fname:<22} {n[:70]}")

    if not (stubs or mute or liars):
        print("  ✅ every scenario has at least one step that can fail.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
