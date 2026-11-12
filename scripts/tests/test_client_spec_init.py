from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import client_inventory  # noqa: E402
import client_spec_bridge  # noqa: E402
import client_spec_init  # noqa: E402


def test_clients_policy_schema_and_inventory_expose_spec_dialect() -> None:
    rep, errors = client_inventory.inventory(ROOT / "project" / "policies" / "clients-policy.json")
    assert errors == [], f"Unexpected client_inventory errors: {errors}"
    by_id = {p["id"]: p for p in rep["projects"]}
    assert "w0m" in by_id
    assert by_id["w0m"]["spec_dialect"] == "w0m-openspec"
    assert by_id["w0m"]["spec_dialect_source"] in ("declared", "detected")
    for pid, proj in by_id.items():
        assert proj["spec_dialect"] in (
            "w0m-openspec",
            "openspec",
            "github-speckit",
            "open-gsd",
            "bmad",
            "conductor",
            "cc-sdd",
            "unknown",
        ), f"{pid} returned invalid spec_dialect: {proj['spec_dialect']}"


@pytest.mark.parametrize("dialect", ["github-speckit", "open-gsd", "openspec"])
def test_bootstrap_creates_testing_seams_overlays_and_zero_w0m_leakage(
    tmp_path: Path, dialect: str
) -> None:
    target = tmp_path / f"client-{dialect}"
    target.mkdir(parents=True)

    res = client_spec_init.bootstrap_client_spec(
        target=target,
        dialect=dialect,
        role="self-managed",
        dry_run=False,
        force=False,
        install_skills=False,
    )
    assert res.ok is True
    assert res.resolved_dialect == dialect
    assert len(res.created_files) >= 3

    # Must NEVER leak internal .w0m, .tasks, TASKS.md, or TECH-DEBT.md surfaces
    for forbidden in (".w0m", ".tasks", "TASKS.md", "TECH-DEBT.md"):
        assert not (target / forbidden).exists(), f"Leaked forbidden w0m surface: {forbidden}"

    # Verify round-trip compatibility with client_spec_bridge
    assert client_spec_bridge.detect_spec_dialect(target) == dialect
    envelope = client_spec_bridge.inspect_client_project_specs(target)
    assert envelope.dialect == dialect
    assert envelope.has_testing_seams is True
    assert len(envelope.features) >= 1


def test_bootstrap_is_non_destructive_and_preserves_existing_files(tmp_path: Path) -> None:
    target = tmp_path / "existing-speckit"
    constitution = target / ".specify" / "memory" / "constitution.md"
    constitution.parent.mkdir(parents=True)
    constitution.write_text("# Custom Client Constitution\nKeep me intact.\n", encoding="utf-8")

    # Auto-detects github-speckit from existing .specify/ directory
    res = client_spec_init.bootstrap_client_spec(
        target=target,
        dialect="auto",
        role="managed",
        dry_run=False,
        force=False,
        install_skills=False,
    )
    assert res.ok is True
    assert res.resolved_dialect == "github-speckit"
    assert constitution.read_text(encoding="utf-8") == "# Custom Client Constitution\nKeep me intact.\n"
    assert ".specify/memory/constitution.md" in res.preserved_files
    assert (target / ".specify" / "templates" / "overrides" / "spec-template.md").is_file()


def test_bootstrap_refuses_target_with_w0m_sdlc_contract_without_force(tmp_path: Path) -> None:
    target = tmp_path / "w0m-governed"
    (target / ".w0m").mkdir(parents=True)
    (target / ".w0m" / "sdlc.json").write_text('{"profile": "w0m"}\n', encoding="utf-8")

    res = client_spec_init.bootstrap_client_spec(
        target=target,
        dialect="openspec",
        role="managed",
        dry_run=False,
        force=False,
        install_skills=False,
    )
    assert res.ok is False
    assert ".w0m/sdlc.json" in (res.error or "")


def test_generic_sdlc_set_doc_documents_all_three_client_dialects() -> None:
    doc = (ROOT / "w0m-skills" / "GENERIC-SDLC-SET.md").read_text(encoding="utf-8")
    for token in (
        "client-spec-init",
        "/speckit.specify",
        "/speckit.plan",
        "/gsd-plan-phase",
        "/gsd-verify-work",
        "egm-",
        "openspec-new-change",
    ):
        assert token in doc, f"GENERIC-SDLC-SET.md missing {token!r}"
