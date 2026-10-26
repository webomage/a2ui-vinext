#!/usr/bin/env python3
"""T276 — regression suite for `Testing seams` in `SPEC-AUTHORING-STANDARD.md` and `w0m-sdlc-spec`.

Covers all 7 Acceptance Criteria of T276:
- AC1: Enriched requirement block template carries `- **Testing seams:**` ordered BEFORE
       `#### Scenario:` blocks, naming `the observable`, `where it is read`, and `its failure shape`.
- AC2: The failure-shape question ("What does a catastrophic failure look like in this measurement,
       and does it look like a pass?") is mandatory, and states that if the answer is "a pass", the
       seam must be replaced before scenarios are written.
- AC3: `prefer existing seams` and `minimise new seams` are stated as rules with their rationale
       (referencing [[T135]] AC8).
- AC4: Retrofitting existing/archived OpenSpec changes is explicitly out of scope (new and modified
       requirements only), and `spec_standard_check.py` remains green on the live corpus.
- AC5: `w0m-sdlc-spec` (canonical + synced active copies) requires identifying `Testing seams`
       before writing `#### Scenario:` blocks.
- AC6: Complete worked example of [[T261]] (16px H1 passing a line-count metric vs computed
       `font-size` observable in the layout matrix).
- AC7: `mattpocock/skills@to-spec` is NOT installed in any manifest, registry, or `.agents/skills/`
       directory, and its non-adoption is explicitly recorded in `SPEC-AUTHORING-STANDARD.md`.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ESTATE_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = ESTATE_ROOT / "wom7web"
SPEC_STANDARD = WEB_ROOT / "openspec" / "SPEC-AUTHORING-STANDARD.md"
SPEC_CHECK_SCRIPT = ESTATE_ROOT / "scripts" / "spec_standard_check.py"

CANONICAL_SKILL = ESTATE_ROOT / "wom7skills" / "skills" / "w0m-sdlc-spec" / "SKILL.md"
WEB_ACTIVE_SKILL = WEB_ROOT / ".agents" / "skills" / "w0m-sdlc-spec" / "SKILL.md"
ROOT_ACTIVE_SKILL = ESTATE_ROOT / ".agents" / "skills" / "w0m-sdlc-spec" / "SKILL.md"

ROOT_SKILLS_JSON = ESTATE_ROOT / ".w0m" / "skills.json"
WEB_SKILLS_JSON = WEB_ROOT / ".w0m" / "skills.json"
SKILLS_REGISTRY_JSON = ESTATE_ROOT / "wom7skills" / "skills-registry.json"


def _extract_enriched_template(standard_text: str) -> str:
    """Return the fenced markdown template block under `## The enriched requirement block`."""
    section_match = re.search(
        r"^##\s+The enriched requirement block\s*$([\s\S]*?)(?=^##\s+|\Z)",
        standard_text,
        re.M,
    )
    assert section_match, "Missing `## The enriched requirement block` section in SPEC-AUTHORING-STANDARD.md"
    section_body = section_match.group(1)
    fence_match = re.search(r"```md\n([\s\S]*?)```", section_body)
    assert fence_match, "Missing ```md template fence under `## The enriched requirement block`"
    return fence_match.group(1)


def _validate_template_seam_order(template_block: str) -> tuple[bool, str]:
    """Validate that `- **Testing seams:**` appears before `#### Scenario:` and carries all 3 parts."""
    seam_idx = template_block.find("- **Testing seams:**")
    scenario_idx = template_block.find("#### Scenario:")
    if seam_idx < 0:
        return False, "missing `- **Testing seams:**` in template"
    if scenario_idx < 0:
        return False, "missing `#### Scenario:` in template"
    if seam_idx >= scenario_idx:
        return False, "`- **Testing seams:**` must appear BEFORE `#### Scenario:`"

    seam_slice = template_block[seam_idx:scenario_idx]
    for required_part in ("the observable", "where it is read", "its failure shape"):
        if required_part not in seam_slice:
            return False, f"missing `{required_part}` inside `- **Testing seams:**` block"
    return True, "ok"


def test_ac1_enriched_block_has_testing_seams_before_scenarios() -> None:
    text = SPEC_STANDARD.read_text(encoding="utf-8")
    template = _extract_enriched_template(text)
    ok, detail = _validate_template_seam_order(template)
    assert ok, detail

    # Negative / RED proof: verify our validator rejects a template where Testing seams is after Scenario
    reversed_template = (
        "### Requirement: X\n"
        "#### Scenario: happy path\n"
        "- **Testing seams:**\n"
        "  - **the observable:** x\n"
        "  - **where it is read:** y\n"
        "  - **its failure shape:** z\n"
    )
    bad_ok, bad_reason = _validate_template_seam_order(reversed_template)
    assert not bad_ok and "BEFORE" in bad_reason


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def test_ac2_failure_shape_question_is_mandatory() -> None:
    text = SPEC_STANDARD.read_text(encoding="utf-8")
    normalized = _norm(text)
    question = "What does a catastrophic failure look like in this measurement, and does it look like a pass?"
    assert question in normalized, "Mandatory failure-shape question missing from SPEC-AUTHORING-STANDARD.md"
    assert "mandatory, not advisory" in normalized
    assert "must be replaced before the scenarios are written" in normalized


def test_ac3_prefer_existing_seams_and_minimise_new_seams_rules() -> None:
    text = SPEC_STANDARD.read_text(encoding="utf-8")
    normalized = _norm(text)
    assert "`prefer existing seams`" in text
    assert "`minimise new seams`" in text
    assert "[[T135]]" in text and "AC8" in text
    assert "bespoke harness per requirement" in normalized


def test_ac4_non_retrofit_scope_written_and_gate_stays_green() -> None:
    text = SPEC_STANDARD.read_text(encoding="utf-8")
    normalized = _norm(text)
    assert "Retrofitting existing/archived OpenSpec changes is explicitly OUT of scope" in normalized
    assert "new and modified requirements only" in normalized

    res = subprocess.run(
        [sys.executable, str(SPEC_CHECK_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, (
        f"spec_standard_check.py failed (rc={res.returncode}):\n{res.stdout}\n{res.stderr}"
    )


def test_ac5_w0m_sdlc_spec_requires_testing_seams_and_stays_in_sync() -> None:
    canon = CANONICAL_SKILL.read_text(encoding="utf-8")
    web_active = WEB_ACTIVE_SKILL.read_text(encoding="utf-8")
    root_active = ROOT_ACTIVE_SKILL.read_text(encoding="utf-8")

    assert canon == web_active, "wom7web active w0m-sdlc-spec/SKILL.md drifted from canonical wom7skills"
    assert canon == root_active, "root active w0m-sdlc-spec/SKILL.md drifted from canonical wom7skills"

    normalized = _norm(canon)
    assert "Testing seams" in canon
    assert "BEFORE writing `#### Scenario:` blocks" in normalized
    assert "the observable" in canon
    assert "where it is read" in canon
    assert "its failure shape" in canon
    assert "What does a catastrophic failure look like in this measurement, and does it look like a pass?" in normalized
    assert "prefer existing seams" in normalized
    assert "minimise new seams" in normalized


def test_ac6_worked_example_t261_in_standard() -> None:
    text = SPEC_STANDARD.read_text(encoding="utf-8")
    normalized = _norm(text)
    assert "[[T261]]" in text
    assert "16px" in text
    assert "33 rows" in normalized
    assert "observable: computed font-size of h1" in text
    assert "attachment: layout matrix per-viewport measurement" in text
    assert (
        "failure shape: a collapsed 16px heading still fits on one line, so a lines-based metric "
        "passes — whereas computed font-size drops below the minimum token threshold and fails"
    ) in normalized


def test_ac7_to_spec_is_not_installed() -> None:
    text = SPEC_STANDARD.read_text(encoding="utf-8")
    assert "Do NOT install `mattpocock/skills@to-spec`" in text

    for manifest_path in (ROOT_SKILLS_JSON, WEB_SKILLS_JSON, SKILLS_REGISTRY_JSON):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        skills = data.get("skills", {})
        assert "to-spec" not in skills, f"`to-spec` must not be declared in {manifest_path}"
        for name, entry in skills.items():
            if isinstance(entry, dict):
                src = str(entry.get("source") or entry.get("upstream") or "")
                assert "to-spec" not in src, f"{name} in {manifest_path} references `to-spec`"

    assert not (ESTATE_ROOT / ".agents" / "skills" / "to-spec").exists()
    assert not (WEB_ROOT / ".agents" / "skills" / "to-spec").exists()


if __name__ == "__main__":
    tests = [
        test_ac1_enriched_block_has_testing_seams_before_scenarios,
        test_ac2_failure_shape_question_is_mandatory,
        test_ac3_prefer_existing_seams_and_minimise_new_seams_rules,
        test_ac4_non_retrofit_scope_written_and_gate_stays_green,
        test_ac5_w0m_sdlc_spec_requires_testing_seams_and_stays_in_sync,
        test_ac6_worked_example_t261_in_standard,
        test_ac7_to_spec_is_not_installed,
    ]
    for fn in tests:
        fn()
        print(f"  [PASS] {fn.__name__}")
    print(f"✅ T276 testing seams suite: all {len(tests)} checks passed.")
