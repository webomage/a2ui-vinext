#!/usr/bin/env python3
"""Unit tests for Cross-Dialect Client Spec Bridge & Package Legitimacy Gate (T708 / T714)."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from client_spec_bridge import detect_spec_dialect, inspect_client_project_specs  # noqa: E402
from package_legitimacy_check import (  # noqa: E402
    audit_estate_repositories,
    evaluate_dependency,
    extract_spec_proposed_packages,
)


def test_estate_repositories_legitimacy_gate() -> None:
    report = audit_estate_repositories()
    assert report.ok is True
    assert report.slop_count == 0
    assert report.manifests_scanned >= 20
    assert report.total_dependencies >= 300
    assert "w0m-web" in report.repos_scanned
    assert "w0m-ext" in report.repos_scanned


def test_package_legitimacy_classifications() -> None:
    locked = {"zod", "vitest", "esbuild"}
    v = evaluate_dependency("w0m-web", "package.json", "npm", "zod", "^4.3.6", locked)
    assert v.status == "VERIFIED"

    fp = evaluate_dependency("w0m-web", "package.json", "npm", "@webomage/ui", "workspace:*", locked)
    assert fp.status == "VERIFIED"

    sus = evaluate_dependency("w0m-web", "package.json", "npm", "esbuild", "latest", locked)
    assert sus.status == "SUS"

    slop_denylist = evaluate_dependency(
        "w0m-web", "package.json", "npm", "openai-agents-sdk-official", "^1.0.0", locked
    )
    assert slop_denylist.status == "SLOP"

    slop_http = evaluate_dependency(
        "w0m-web", "package.json", "npm", "custom-pkg", "http://evil.example.com/pkg.tgz", locked
    )
    assert slop_http.status == "SLOP"


def test_spec_proposed_packages_extraction() -> None:
    md = """
    We will install dependencies:
    ```bash
    pnpm add zod@^4.3.6
    pip install openai-agents-sdk-official
    cargo add serde
    ```
    """
    findings = extract_spec_proposed_packages(md, manifest_label="plan.md", locked_names={"zod", "serde"})
    by_name = {f.name: f for f in findings}
    assert by_name["zod"].status == "VERIFIED"
    assert by_name["serde"].status == "VERIFIED"
    assert by_name["openai-agents-sdk-official"].status == "SLOP"


def test_github_speckit_dialect_bridge(tmp_path: Path) -> None:
    fdir = tmp_path / ".specify" / "specs" / "001-auth-flow"
    (fdir / "checklists").mkdir(parents=True)
    (fdir / "spec.md").write_text(
        "# Auth Flow Spec\n\nFR-001: Users authenticate.\n\n## Testing seams\n- `data-testid=\"auth-login\"`\n",
        encoding="utf-8",
    )
    (fdir / "tasks.md").write_text(
        "- [x] T001 Implement login route\n- [x] T002 Add Vitest test\n",
        encoding="utf-8",
    )
    (fdir / "checklists" / "requirements.md").write_text("- [x] Complete\n", encoding="utf-8")

    assert detect_spec_dialect(tmp_path) == "github-speckit"
    env = inspect_client_project_specs(tmp_path)
    assert env.dialect == "github-speckit"
    assert env.tasks_done == 3
    assert env.tasks_total == 3
    assert env.has_testing_seams is True
    assert env.verification_status == "verified"
    assert "FR-001" in env.requirements


def test_open_gsd_dialect_bridge(tmp_path: Path) -> None:
    pdir = tmp_path / ".planning" / "phases" / "01-foundation"
    pdir.mkdir(parents=True)
    (tmp_path / ".planning" / "PROJECT.md").write_text("# Client App\nREQ-AUTH-01\n", encoding="utf-8")
    (pdir / "01-01-PLAN.md").write_text(
        "# Phase 1 Plan\n<task type=\"auto\"><name>Task 1</name></task>\npnpm add openai-agents-sdk-official\n",
        encoding="utf-8",
    )
    (pdir / "01-01-SUMMARY.md").write_text("# Summary\nDone.\n", encoding="utf-8")
    (pdir / "01-VALIDATION.md").write_text("# Nyquist Validation\n", encoding="utf-8")
    (pdir / "01-VERIFICATION.md").write_text("# Verification\n", encoding="utf-8")

    assert detect_spec_dialect(tmp_path) == "open-gsd"
    env = inspect_client_project_specs(tmp_path)
    assert env.dialect == "open-gsd"
    assert env.tasks_done == 1
    assert env.tasks_total == 1
    assert env.has_testing_seams is True
    assert env.package_legitimacy["ok"] is False
    assert env.package_legitimacy["slop_count"] == 1


def test_openspec_and_w0m_dialects(tmp_path: Path) -> None:
    sdir = tmp_path / "openspec" / "specs" / "billing"
    sdir.mkdir(parents=True)
    (sdir / "spec.md").write_text(
        "# Billing Spec\n\n#### Scenario: Invoice paid\n- [x] AC1 Verify webhook\n",
        encoding="utf-8",
    )
    assert detect_spec_dialect(tmp_path) == "openspec"
    env = inspect_client_project_specs(tmp_path)
    assert env.dialect == "openspec"
    assert env.has_testing_seams is True
    assert env.verification_status == "verified"


def test_bmad_dialect_bridge(tmp_path: Path) -> None:
    epic_dir = tmp_path / "_bmad" / "epics" / "01-checkout"
    epic_dir.mkdir(parents=True)
    (tmp_path / "_bmad" / "project-context.md").write_text(
        "# Storefront Context\nREQ-BMAD-01\n",
        encoding="utf-8",
    )
    (epic_dir / "story-01.md").write_text(
        "# Checkout Story\nFR-101: Cart checkout.\n\n## Testing seams\n- `data-testid=\"bmad-pay\"`\n- [x] AC1 Build handler\n- [x] AC2 Verify E2E\n",
        encoding="utf-8",
    )
    assert detect_spec_dialect(tmp_path) == "bmad"
    env = inspect_client_project_specs(tmp_path)
    assert env.dialect == "bmad"
    assert env.tasks_done == 2
    assert env.tasks_total == 2
    assert env.has_testing_seams is True
    assert env.verification_status == "verified"
    assert "FR-101" in env.requirements
    assert "REQ-BMAD-01" in env.requirements


def test_conductor_and_cc_sdd_dialects(tmp_path: Path) -> None:
    # 1. Google Conductor (`conductor/tracks/<track>/`)
    c_root = tmp_path / "conductor_proj"
    track_dir = c_root / "conductor" / "tracks" / "webhook-delivery"
    track_dir.mkdir(parents=True)
    (c_root / "conductor" / "product.md").write_text("# Webhook Product\nREQ-COND-01\n", encoding="utf-8")
    (track_dir / "spec.md").write_text(
        "# Webhook Spec\n\n## Testing seams\n- Observable HTTP 202 receipt\n",
        encoding="utf-8",
    )
    (track_dir / "plan.md").write_text(
        "- [x] Task 1: Signature check\n- [ ] Task 2: Retry backoff\n",
        encoding="utf-8",
    )
    assert detect_spec_dialect(c_root) == "conductor"
    c_env = inspect_client_project_specs(c_root)
    assert c_env.dialect == "conductor"
    assert c_env.tasks_done == 1
    assert c_env.tasks_total == 2
    assert c_env.has_testing_seams is True
    assert c_env.verification_status == "in_progress"

    # 2. Kiro / cc-sdd (`.kiro/specs/<feature>/{requirements,design,tasks}.md`)
    k_root = tmp_path / "kiro_proj"
    k_spec = k_root / ".kiro" / "specs" / "audit-trail"
    k_spec.mkdir(parents=True)
    (k_spec / "requirements.md").write_text(
        "# Audit Trail Requirements\nREQ-KIRO-01\n#### Scenario: Append-only write\n",
        encoding="utf-8",
    )
    (k_spec / "tasks.md").write_text("- [x] 1.1 Create trigger\n- [x] 1.2 Add RLS test\n", encoding="utf-8")
    assert detect_spec_dialect(k_root) == "cc-sdd"
    k_env = inspect_client_project_specs(k_root)
    assert k_env.dialect == "cc-sdd"
    assert k_env.tasks_done == 2
    assert k_env.tasks_total == 2
    assert k_env.has_testing_seams is True
    assert k_env.verification_status == "verified"
