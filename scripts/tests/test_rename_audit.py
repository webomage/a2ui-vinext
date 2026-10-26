#!/usr/bin/env python3
"""Offline test suite for T409: rename_audit tool (AC2, AC4)."""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT / "w0m-web"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import rename_audit

checks = 0
fails = []


def check(label: str, cond: bool) -> None:
    global checks
    checks += 1
    if not cond:
        fails.append(label)
    print(f"  {'✓' if cond else '✗'} {label}")


def main() -> int:
    print("rename-audit Test Suite (T409)")
    print("─" * 60)

    # 1. Module existence
    check("rename_audit.py exists", (SCRIPTS / "rename_audit.py").is_file())
    check("SURFACES defined in rename_audit", hasattr(rename_audit, "SURFACES"))
    check("classify_file function exists", hasattr(rename_audit, "classify_file"))

    # 2. Surface classification
    check("classify .astro as code_and_templates", rename_audit.classify_file(Path("apps/web/src/pages/index.astro")) == "code_and_templates")
    check("classify .svelte as code_and_templates", rename_audit.classify_file(Path("packages/ui/Button.svelte")) == "code_and_templates")
    check("classify .ts as code_and_templates", rename_audit.classify_file(Path("packages/lib/index.ts")) == "code_and_templates")
    check("classify .py as code_and_templates", rename_audit.classify_file(Path("scripts/run.py")) == "code_and_templates")
    check("classify SKILL.md as governance_and_skills", rename_audit.classify_file(Path(".agents/skills/test/SKILL.md")) == "governance_and_skills")
    check("classify CLAUDE.md as governance_and_skills", rename_audit.classify_file(Path("CLAUDE.md")) == "governance_and_skills")
    check("classify .gitignore as configs_and_tooling", rename_audit.classify_file(Path(".gitignore")) == "configs_and_tooling")
    check("classify package.json as configs_and_tooling", rename_audit.classify_file(Path("package.json")) == "configs_and_tooling")
    check("classify justfile as configs_and_tooling", rename_audit.classify_file(Path("justfile")) == "configs_and_tooling")
    check("classify out/bin artifact as build_and_artifacts", rename_audit.classify_file(Path("out/bin/orca")) == "build_and_artifacts")
    check("classify Makefile as build_and_artifacts", rename_audit.classify_file(Path("native/build/Makefile")) == "build_and_artifacts")

    # 3. Detection in synthetic directory tree
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "apps/web").mkdir(parents=True)
        (root / ".agents/skills/my-skill").mkdir(parents=True)
        (root / "native/build").mkdir(parents=True)

        # Write clean and dirty files
        (root / "apps/web/page.astro").write_text("<script>const target = 'old_target_name';</script>")
        (root / ".agents/skills/my-skill/SKILL.md").write_text("Use old_target_name preset")
        (root / "native/build/Makefile").write_text("PATH = /path/to/old_target_name/bin")
        (root / ".gitignore").write_text("old_target_name/dist")
        (root / "clean.ts").write_text("const target = 'new_target_name';")

        report = rename_audit.run_audit("old_target_name", "new_target_name", root=root)

        check("audit discovers code_and_templates hit", len(report["surfaces"]["code_and_templates"]) == 1)
        check("audit discovers governance_and_skills hit", len(report["surfaces"]["governance_and_skills"]) == 1)
        check("audit discovers configs_and_tooling hit", len(report["surfaces"]["configs_and_tooling"]) == 1)
        check("audit discovers build_and_artifacts hit", len(report["surfaces"]["build_and_artifacts"]) == 1)
        check("total hits equal 4", report["total_hits"] == 4)

    # 4. Exception / Waiver handling
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "DECOMMISSIONED.md").write_text("## old_name (retired)\npath: old_name\n")
        report_waived = rename_audit.run_audit(
            "old_name", "new_name",
            root=root,
            exempt_paths=["DECOMMISSIONED.md"]
        )
        check("exempted path not counted as violation", report_waived["total_violations"] == 0)
        check("exempted path tracked in report", len(report_waived["exempted"]) >= 1)

    # 5. Binary file detection
    check("is_binary_file function exists", hasattr(rename_audit, "is_binary_file"))
    check("identify .png as binary", rename_audit.is_binary_file(Path("dummy.png")))
    check("identify .exe as binary", rename_audit.is_binary_file(Path("dummy.exe")))
    check("identify .ts as non-binary", not rename_audit.is_binary_file(Path("dummy.ts")))
    check("identify .py as non-binary", not rename_audit.is_binary_file(Path("dummy.py")))

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        bin_file = root / "binary_data.bin"
        bin_file.write_bytes(b"\x00\x01\x02old_target_name\x03\x04")
        check("identify file with null bytes as binary", rename_audit.is_binary_file(bin_file))

        report_bin = rename_audit.run_audit("old_target_name", "new_target_name", root=root)
        check("binary file content does not cause text line hits", report_bin["total_violations"] == 0)

    print("─" * 60)
    print(f"Results: {checks - len(fails)}/{checks} checks passed.")
    if fails:
        print("FAILURES:")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("All rename-audit unit tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
