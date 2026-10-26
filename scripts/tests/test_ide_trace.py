#!/usr/bin/env python3
"""Prove `ide-trace`'s checks go RED — T192 AC2/AC3.

AC3 asks for one thing in particular, in the ticket's own words: *"a red probe must prove the
check fails on today's `.agent/rules.md` (0 of 6) — a parity gate that passes on the known-bad
case is worthless."* So the first case below runs the real parity function against the real,
unmodified `w0m-web/.agent/rules.md` and asserts it comes back at ZERO. If someone fixes that
file, this case fails and must be replaced by a frozen copy — the probe is deliberately bound to
the artefact that motivated the gate, not to a synthetic string that always fails.

The rest are the estate's standing shapes:
  • a check must fail on an EMPTY corpus rather than pass (T147 AC6 / T149 — `0 skills match ✓`);
  • a surface is identified by its MARKER, never by its directory NAME — both directions, since
    this ticket's own filing got it wrong twice and the first draft of the gate got it wrong a
    third time by using too narrow a marker.

Run: `just ide-trace-test`
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import ide_trace  # noqa: E402

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []
POLICY = json.loads((ROOT / "project" / "policies" / "ide-policy.json").read_text())
RULES = POLICY["non_negotiables"]
MARKER = POLICY["marker"]
DELEG = POLICY["delegation"]


def case(name: str, fn) -> None:
    try:
        fn()
        results.append((True, name))
    except AssertionError as exc:
        results.append((False, f"{name} — {exc}"))
    except Exception as exc:  # a probe that errors is a probe that did not run
        results.append((False, f"{name} — raised {type(exc).__name__}: {exc}"))


# ── AC3: the red probe the ticket names ─────────────────────────────────────────────────────────

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BAD = "agent-rules-2026-08-10-before.md"


def red_probe_the_frozen_known_bad_file() -> None:
    """The artefact that motivated the whole ticket, frozen at 1,646 B.

    This probe ran against the LIVE `w0m-web/.agent/rules.md` until that file was rewritten to
    6/6 — at which point it failed and said exactly what to do: *"if it was FIXED, freeze a copy
    of the original as the fixture"*. That is the fixture. Binding a red probe to a file you
    intend to repair guarantees the probe stops proving anything the moment you succeed; binding
    it to the frozen bytes keeps the evidence. Recovered with `git show`, byte-for-byte.
    """
    text = (FIXTURES / BAD).read_text()
    assert len(text.encode()) == 1646, "the fixture must be the original bytes, not a paraphrase"
    r = ide_trace.parity(FIXTURES, BAD, RULES, DELEG)
    assert r["present"], "the frozen fixture is missing — restore it, do not delete this probe"
    assert r["carried"] == [], (
        f"the known-bad file carries {r['carried']} — it is FROZEN, so this can only mean the "
        "rule regexes changed; a parity gate whose red case went green proves nothing")
    assert r["delegated"] is None, (
        "the original pointed at no canonical file either — if delegation now rescues it, the "
        "delegation pattern is too loose and would rescue any file mentioning a .md")
    assert len(r["missing"]) == len([k for k in RULES if not k.startswith("_")]), \
        "every non-negotiable must be reported missing, not just some"


def the_live_file_is_now_fixed() -> None:
    # The other half of the same evidence: the real surface this ticket set out to repair.
    # MOVED 2026-08-30: Antigravity relocated its own autoload from the single file
    # `.agent/rules.md` to the directory `.agents/rules/*.md` (ide-policy.json's `tools.antigravity`
    # records the move). Not a regression — check the surface Antigravity actually reads today.
    r = ide_trace.parity(ide_trace.CANONICAL, ".agents/rules/*.md", RULES, DELEG)
    assert r["present"], "w0m-web/.agents/rules/*.md is gone — it is a declared Antigravity surface"
    assert not r["missing"], f"the live Antigravity surface regressed; missing {r['missing']}"


def red_probe_canonical_is_green() -> None:
    # The other half: the gate must be able to say YES. A check that reds on everything is as
    # useless as one that greens on everything, and only running both directions shows which.
    r = ide_trace.parity(ide_trace.CANONICAL, "CLAUDE.md", RULES)
    assert r["missing"] == [], f"the canonical contract must satisfy its own rules; missing {r['missing']}"


def parity_on_absent_file_is_total_failure() -> None:
    # artemio's real shape: `.agent/workflows/` exists, `.agent/rules.md` does not. A connected
    # IDE whose autoload file is missing has an EMPTY contract — the check must say 0/6, not skip.
    with tempfile.TemporaryDirectory() as d:
        r = ide_trace.parity(Path(d), ".agent/rules.md", RULES)
    assert r["present"] is False, "a missing autoload file must be reported as absent"
    assert r["carried"] == [], "an absent file cannot carry a rule"


def empty_ruleset_is_not_a_pass() -> None:
    # The estate's recurring defect, in this gate's terms: with no rules declared, every surface
    # would score 0/0 and print ✅. The schema forbids it (`minProperties: 2`); this proves the
    # schema is the thing standing in the way, by validating a doctored policy against it.
    try:
        import jsonschema
    except ImportError:
        return
    schema = json.loads((ROOT / "project" / "policies" / "ide-policy.schema.json").read_text())
    doctored = {**POLICY, "non_negotiables": {}}
    try:
        jsonschema.validate(doctored, schema)
    except jsonschema.ValidationError:
        return
    raise AssertionError("a policy with ZERO non-negotiables validated — the parity gate would "
                         "then be vacuously green on every IDE surface in the estate")


# ── AC2: marker, not name — in both directions ──────────────────────────────────────────────────

def name_alone_is_not_a_surface() -> None:
    # servicios777/.kilocode: a node package dir. The name matches an openspec tool exactly.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".kilocode").mkdir()
        (root / ".kilocode" / "package.json").write_text("{}")
        (root / ".kilocode" / "package-lock.json").write_text("{}")
        c = ide_trace.classify(root, ".kilocode", MARKER, None)
    assert c["state"] == "other", f"a package dir must not classify as a surface (got {c['state']})"


def a_file_named_openspec_is_not_openspec_output() -> None:
    """The correction that cost the most: I widened the marker on a FILENAME.

    Seeing `w0m-mlx/.cursor/rules/openspec.md` reported as an unruled lookalike, I added an
    `openspec*` glob and wrote "the earlier openspec layout" into the policy, the ticket, STATE.md
    and a commit message. It is hand-written — landed by a feature commit, pointing at a
    `specs/meta/` layout, in a repo with no `openspec/` directory, and the installed CLI contains
    no code emitting a `rules/openspec.md`. That is this ticket's own trap, committed by the gate
    built to catch it, at the fourth time of asking. The marker is `opsx*` and nothing else.
    """
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".cursor" / "rules").mkdir(parents=True)
        (root / ".cursor" / "rules" / "openspec.md").write_text("hand-written rules")
        c = ide_trace.classify(root, ".cursor", MARKER, None)
    assert c["state"] == "foreign", (
        f"a file NAMED openspec.md is not openspec OUTPUT (got {c['state']}) — it is a real "
        "surface with another author, which is what `foreign` means")
    assert "openspec*" not in MARKER["globs"], (
        "the marker must not match on the name `openspec`; only the CLI's own `opsx` family "
        "proves generation")


def delegation_satisfies_parity_only_when_the_chain_ENDS_somewhere_real() -> None:
    """Three cases the estate actually contains, and they must not collapse into one."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        full = "\n".join(f"rule {n}" for n in RULES if not n.startswith("_"))
        # a target carrying every rule — the w0m-api → w0m-web/CLAUDE.md shape
        (root / "CLAUDE.md").write_text("\n".join(
            [RULES[n].split("|")[0] for n in RULES if not n.startswith("_")]))
        (root / "good.md").write_text("Canonical conventions live in `CLAUDE.md`\n")
        (root / "dangling.md").write_text("Canonical conventions live in `../nope/CLAUDE.md`\n")
        (root / "AGENTS.md").write_text("nothing here at all\n")
        (root / "nowhere.md").write_text("Canonical conventions live in `AGENTS.md`\n")
        assert full  # the rule set is non-empty, else every case below is vacuous

        ok = ide_trace.parity(root, "good.md", RULES, DELEG)
        assert ok["delegated"] and ok["delegated"]["satisfied"], \
            f"a pointer to a file carrying every rule must satisfy parity: {ok['delegated']}"

        bad = ide_trace.parity(root, "dangling.md", RULES, DELEG)
        assert bad["delegated"] and not bad["delegated"]["resolves"], \
            "a pointer to a file that does not exist must NOT satisfy parity — it reads as compliance"

        dead = ide_trace.parity(root, "nowhere.md", RULES, DELEG)
        assert dead["delegated"] and dead["delegated"]["resolves"], "the target exists"
        assert not dead["delegated"]["satisfied"], (
            "delegating to a file that carries the rules no better than you do is delegation to "
            "nowhere — w0m-mlx's CLAUDE.md → AGENTS.md was exactly this, and it looked compliant")


def a_rules_directory_is_read_as_the_autoload() -> None:
    # Cursor and Windsurf load `.cursor/rules/*`, not a root file. Modelling every tool as one
    # path made three of w0m-mlx's declared surfaces report `[file absent]` against a path they
    # never open — measuring the wrong artefact and calling the result a finding.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".cursor" / "rules").mkdir(parents=True)
        (root / ".cursor" / "rules" / "a.md").write_text("--no-verify is forbidden")
        (root / ".cursor" / "rules" / "b.md").write_text("just ask before grep")
        text, where = ide_trace.read_autoload(root, [".cursor/rules/*.md"])
    assert text is not None and "no-verify" in text and "just ask" in text, \
        "every file in the rules directory must be read, not just the first"
    assert "+1" in where, f"the report must say how many files were concatenated (got {where!r})"


def current_openspec_layout_marks_on_a_directory() -> None:
    # …and the current layout puts the marker on a DIRECTORY component
    # (`.claude/commands/opsx/new.md`), which basename matching misses.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".claude" / "commands" / "opsx").mkdir(parents=True)
        (root / ".claude" / "commands" / "opsx" / "new.md").write_text("x")
        c = ide_trace.classify(root, ".claude", MARKER, None)
    assert c["state"] == "openspec", f"marker on a path component must count (got {c['state']})"


def a_foreign_generator_still_makes_a_real_surface() -> None:
    # w0m-ext/.windsurf/workflows/speckit.* — GitHub Spec Kit. Not openspec's, and it autoloads
    # exactly as hard. Reporting only openspec-generated surfaces would have missed it entirely.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".windsurf" / "workflows").mkdir(parents=True)
        (root / ".windsurf" / "workflows" / "speckit.plan.md").write_text("x")
        c = ide_trace.classify(root, ".windsurf", MARKER, None)
    assert c["state"] == "foreign", f"a non-openspec instruction surface is still a surface (got {c['state']})"


def an_empty_directory_autoloads_nothing() -> None:
    # `.github` is openspec's skillsDir for Copilot and exists in nearly every repo on earth.
    # w0m-ext/.github and w0m-sec/.github are empty; reporting them would train people to ignore
    # this gate's output, which is how a real finding gets lost.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".github").mkdir()
        c = ide_trace.classify(root, ".github", MARKER, None)
    assert c["state"] == "absent", f"an empty dir must not be a finding (got {c['state']})"


# ── the registry must be READ, never guessed ────────────────────────────────────────────────────

def openspec_registry_is_read_live() -> None:
    tools, err = ide_trace.openspec_tools()
    assert err is None, f"the registry must be readable: {err}"
    assert len(tools) >= 31, f"expected openspec's full tool set, got {len(tools)}"
    # MOVED 2026-08-30: openspec's own registry now reports antigravity's skillsDir as `.agents`
    # (was `.agent`) — matches the vendor relocation ide-policy.json's `tools.antigravity` records.
    assert tools.get("antigravity") == ".agents", "registry read produced the wrong skillsDir"
    assert tools.get("github-copilot") == ".github", (
        "the `.github` collision must come from the REGISTRY, not from a hardcoded list — if it "
        "stops being read live, the gate silently narrows to whatever someone once typed")


def red_probe_declared_agent_entrypoint_missing_or_unresolvable_fails() -> None:
    """T232 AC12 — ide-trace fails when a declared agent's entrypoint is missing or unresolvable."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # Mutation 1: Declared agent entrypoint missing entirely
        r_missing = ide_trace.parity(root, "AGENTS.md", RULES, DELEG)
        assert not r_missing["present"], "missing entrypoint must report present=False"
        assert len(r_missing["missing"]) == len([k for k in RULES if not k.startswith("_")]), (
            "missing entrypoint must report all non-negotiables missing"
        )

        # Mutation 2: Declared agent entrypoint points to dangling path
        (root / "AGENTS.md").write_text("Canonical conventions live in `../unresolvable_path/AGENTS.md`\n")
        r_dangling = ide_trace.parity(root, "AGENTS.md", RULES, DELEG)
        assert r_dangling["present"], "entrypoint file exists"
        assert r_dangling["delegated"] is not None, "delegation must be parsed"
        assert not r_dangling["delegated"]["resolves"], "dangling delegation must fail to resolve"
        assert not r_dangling["delegated"]["satisfied"], "unresolvable pointer cannot satisfy parity"

        # Mutation 3: Entrypoint resolves to a file that does NOT carry all rules
        (root / "sub").mkdir()
        (root / "sub" / "AGENTS.md").write_text("just ask before grep\n")  # carries only 1 of 6
        (root / "CLAUDE.md").write_text("Canonical conventions live in `sub/AGENTS.md`\n")
        r_insufficient = ide_trace.parity(root, "CLAUDE.md", RULES, DELEG)
        assert r_insufficient["present"], "CLAUDE.md must be present"
        assert r_insufficient["delegated"] is not None, "delegation to sub/AGENTS.md must be parsed"
        assert r_insufficient["delegated"]["resolves"], "target sub/AGENTS.md exists"
        assert not r_insufficient["delegated"]["satisfied"], (
            "delegation to target missing non-negotiables must NOT satisfy parity"
        )


for label, probe in [
    ("AC3 RED — the FROZEN known-bad .agent/rules.md carries 0 of 6", red_probe_the_frozen_known_bad_file),
    ("AC3 — and the live file it replaced is now at parity", the_live_file_is_now_fixed),
    ("AC3 GREEN — the canonical CLAUDE.md satisfies its own rules", red_probe_canonical_is_green),
    ("AC3 — a missing autoload file is 0/6, not a skip", parity_on_absent_file_is_total_failure),
    ("AC3 — a policy with ZERO rules is rejected, not vacuously green", empty_ruleset_is_not_a_pass),
    ("AC2 — a matching NAME with no marker is not a surface", name_alone_is_not_a_surface),
    ("AC2 — a file NAMED openspec.md is not openspec OUTPUT", a_file_named_openspec_is_not_openspec_output),
    ("AC3 — delegation counts only when the chain ends somewhere real", delegation_satisfies_parity_only_when_the_chain_ENDS_somewhere_real),
    ("AC3 — a rules DIRECTORY is read as the autoload", a_rules_directory_is_read_as_the_autoload),
    ("AC2 — a marker on a path COMPONENT counts", current_openspec_layout_marks_on_a_directory),
    ("AC2 — a foreign generator's instructions are still a surface", a_foreign_generator_still_makes_a_real_surface),
    ("AC2 — an empty tool directory is not a finding", an_empty_directory_autoloads_nothing),
    ("AC2 — openspec's 31-tool registry is read live", openspec_registry_is_read_live),
    ("AC12 RED — declared agent entrypoint missing or unresolvable fails parity", red_probe_declared_agent_entrypoint_missing_or_unresolvable_fails),
]:
    case(label, probe)

print("\n  ide-trace red probes — every check proven to FAIL on its known-bad case\n")
for ok, name in results:
    print(f"    {PASS if ok else FAIL} {name}")
bad = [n for ok, n in results if not ok]
print(f"\n  {len(results) - len(bad)}/{len(results)} passed\n")
sys.exit(1 if bad else 0)
