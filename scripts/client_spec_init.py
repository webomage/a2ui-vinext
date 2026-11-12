#!/usr/bin/env python3
"""client_spec_init.py — Multi-Dialect Client Project Spec Bootstrapper (T713).

Initializes SDD specification scaffolds with Webomage `Testing seams` and security/RLS
verification overlays across external/client repositories (`role: "managed"` or
`role: "self-managed"`) without leaking internal `.w0m/` tracking surfaces:

  * `github-speckit` (`.specify/` + `.specify/templates/overrides/`)
  * `open-gsd`       (`.planning/` + `.planning/templates/VALIDATION-TESTING-SEAMS.md`)
  * `openspec`       (`openspec/` + `openspec/SPEC-TESTING-SEAMS.md`)

Non-destructive by default: existing files are preserved unless `--force` is passed.
Optionally invokes `w0m-skills/scripts/install_generic.ts` (`--install-skills`) to
vendor the portable skill set into `<target>/.agents/skills/` and `<target>/.claude/skills/`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

from client_spec_bridge import detect_spec_dialect  # noqa: E402

SUPPORTED_BOOTSTRAP_DIALECTS = ("github-speckit", "open-gsd", "openspec")
SUPPORTED_ROLES = ("managed", "self-managed")


@dataclass
class BootstrapResult:
    ok: bool
    target: str
    role: str
    requested_dialect: str
    resolved_dialect: str
    dry_run: bool
    created_files: list[str] = field(default_factory=list)
    overwritten_files: list[str] = field(default_factory=list)
    preserved_files: list[str] = field(default_factory=list)
    skills_installed: bool = False
    skills_output: str = ""
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _speckit_overlays() -> dict[str, str]:
    return {
        ".specify/memory/constitution.md": (
            "# Project Engineering Constitution\n\n"
            "## Core Principles\n"
            "1. **Specification Before Implementation:** Every non-trivial feature declares clear requirements (`REQ-*` / `FR-*`) and acceptance scenarios.\n"
            "2. **Security & Tenant Isolation:** Fail closed by default; verify authentication, row-level authorization, and secret boundaries.\n"
            "3. **Deterministic Observability (`Testing seams`):** Every UI control, API route, and background job exposes deterministic selectors (`data-testid`), structured health responses, and reproducible verification commands.\n"
        ),
        ".specify/templates/overrides/spec-template.md": (
            "# Feature Specification Template\n\n"
            "## Summary\n"
            "Describe the user problem, target outcome, and scope boundaries.\n\n"
            "## Requirements\n"
            "- [ ] REQ-001 — Primary functional behavior.\n"
            "- [ ] REQ-002 — Security, validation, and authorization boundary.\n\n"
            "#### Scenario: Primary happy path and fail-closed boundary\n"
            "- **GIVEN** an authenticated caller within an authorized project scope\n"
            "- **WHEN** the feature action is invoked\n"
            "- **THEN** the state transition succeeds deterministically and unauthorized callers receive `401`/`403`\n\n"
            "## Testing seams\n"
            "- **UI Selectors:** Declare stable `data-testid` attributes for interactive controls and status banners.\n"
            "- **API / CLI Probes:** Document deterministic status codes, payload schemas, and dry-run commands.\n"
            "- **Security Assertions:** Verify cross-tenant isolation and input validation failures.\n"
        ),
        ".specify/templates/overrides/plan-template.md": (
            "# Implementation Plan Template\n\n"
            "## Architecture & Data Boundaries\n"
            "- Components, data contracts, and migration order.\n"
            "- Authentication, authorization, and audit-logging touchpoints.\n\n"
            "## Testing seams\n"
            "- Unit, integration, and browser E2E verification commands (`data-testid` & API probes).\n"
        ),
    }


def _speckit_seed_feature() -> dict[str, str]:
    return {
        ".specify/specs/001-foundation/spec.md": (
            "# 001 — Foundation & Testing Seams Baseline\n\n"
            "## Requirements\n"
            "- [ ] REQ-FOUNDATION-001 — Establish constitutional specification workflow and deterministic verification hooks.\n\n"
            "#### Scenario: Baseline specification verification\n"
            "- **GIVEN** the repository `.specify/` workspace\n"
            "- **WHEN** specification normalization runs\n"
            "- **THEN** requirements and `Testing seams` are discovered cleanly\n\n"
            "## Testing seams\n"
            "- Interactive views expose stable `data-testid` hooks; API endpoints emit structured JSON errors.\n"
        ),
        ".specify/specs/001-foundation/checklists/requirements.md": (
            "# Requirements Quality & Testing Seams Checklist\n\n"
            "- [ ] Every requirement (`REQ-*`) maps to at least one testable scenario.\n"
            "- [ ] `## Testing seams` declares `data-testid` hooks and authz boundary checks.\n"
        ),
    }


def _open_gsd_overlays() -> dict[str, str]:
    return {
        ".planning/PROJECT.md": (
            "# Project Vision & Architecture Context\n\n"
            "## Overview\n"
            "Milestone-driven engineering plan managed via OpenGSD (`.planning/`).\n\n"
            "## Guardrails\n"
            "- Fail-closed security boundaries, explicit migrations, and deterministic `Testing seams`.\n"
        ),
        ".planning/ROADMAP.md": (
            "# Milestone Roadmap\n\n"
            "- **Phase 01 (`01-foundation`):** Baseline architecture, security boundaries, and Nyquist `Testing seams` validation.\n"
        ),
        ".planning/STATE.md": (
            "# Current Execution State\n\n"
            "- **Active Phase:** `01-foundation`\n"
            "- **Status:** Initialized via client specification bootstrap.\n"
        ),
        ".planning/templates/VALIDATION-TESTING-SEAMS.md": (
            "# Nyquist & Testing Seams Validation Overlay\n\n"
            "## Testing seams\n"
            "- **Nyquist Sampling Rule:** Every phase plan pairs each requirement (`REQ-*`) with an automated unit, API, or `data-testid` E2E assertion.\n"
            "- **Security Verification:** Confirm unauthorized/cross-tenant requests fail closed.\n"
        ),
    }


def _open_gsd_seed_phase() -> dict[str, str]:
    return {
        ".planning/phases/01-foundation/01-PLAN.md": (
            "# Phase 01 — Foundation Plan\n\n"
            "## Tasks\n"
            "- [ ] REQ-FOUNDATION-001 — Stand up baseline specification and verification harness.\n\n"
            "## Testing seams\n"
            "- Verify `data-testid` selectors and API health contracts.\n"
        ),
        ".planning/phases/01-foundation/01-VALIDATION.md": (
            "# Phase 01 — Nyquist Validation Matrix\n\n"
            "## Testing seams\n"
            "- Map `REQ-FOUNDATION-001` to deterministic automated test commands.\n"
        ),
    }


def _openspec_overlays() -> dict[str, str]:
    return {
        "openspec/README.md": (
            "# OpenSpec Specification Workspace\n\n"
            "- `openspec/specs/<capability>/spec.md` — Canonical capability specifications.\n"
            "- `openspec/changes/<change>/` — Proposed capability deltas (`proposal.md`, `design.md`, `tasks.md`).\n"
            "- `openspec/SPEC-TESTING-SEAMS.md` — Mandatory `Scenario:` and `Testing seams` contract.\n"
        ),
        "openspec/SPEC-TESTING-SEAMS.md": (
            "# OpenSpec Authoring & Testing Seams Overlay\n\n"
            "Every capability spec under `openspec/specs/<capability>/spec.md` and delta under "
            "`openspec/changes/<change>/` MUST include:\n"
            "1. Normative requirements (`REQ-*`) paired with `#### Scenario:` Given/When/Then blocks.\n"
            "2. A `## Testing seams` section naming stable `data-testid` selectors, CLI/API probes, and fail-closed security checks.\n"
        ),
    }


def _openspec_seed_spec() -> dict[str, str]:
    return {
        "openspec/specs/foundation/spec.md": (
            "# Foundation Capability Specification\n\n"
            "## Requirements\n"
            "- [ ] REQ-FOUNDATION-001 — Capability changes follow delta-spec review with deterministic verification.\n\n"
            "#### Scenario: Capability spec validation\n"
            "- **GIVEN** `openspec/specs/foundation/spec.md`\n"
            "- **WHEN** cross-dialect spec verification runs\n"
            "- **THEN** scenarios and `Testing seams` validate cleanly\n\n"
            "## Testing seams\n"
            "- Expose `data-testid` attributes on UI surfaces and deterministic JSON status codes on API endpoints.\n"
        ),
    }


def resolve_bootstrap_dialect(target: Path, requested: str, role: str) -> str:
    if requested != "auto":
        if requested not in SUPPORTED_BOOTSTRAP_DIALECTS:
            raise ValueError(
                f"Unsupported bootstrap dialect {requested!r}; choose auto or one of {SUPPORTED_BOOTSTRAP_DIALECTS}"
            )
        return requested

    detected = detect_spec_dialect(target)
    if detected in SUPPORTED_BOOTSTRAP_DIALECTS:
        return detected
    return "github-speckit" if role == "self-managed" else "openspec"


def bootstrap_client_spec(
    target: Path,
    dialect: str = "auto",
    role: str = "managed",
    dry_run: bool = False,
    force: bool = False,
    install_skills: bool = False,
) -> BootstrapResult:
    target = target.resolve()
    if role not in SUPPORTED_ROLES:
        return BootstrapResult(
            ok=False,
            target=str(target),
            role=role,
            requested_dialect=dialect,
            resolved_dialect="unknown",
            dry_run=dry_run,
            error=f"Unsupported role {role!r}; expected one of {SUPPORTED_ROLES}",
        )

    if not target.exists() or not target.is_dir():
        return BootstrapResult(
            ok=False,
            target=str(target),
            role=role,
            requested_dialect=dialect,
            resolved_dialect="unknown",
            dry_run=dry_run,
            error=f"Target directory does not exist: {target}",
        )

    if (target / ".w0m" / "sdlc.json").is_file() and not force:
        return BootstrapResult(
            ok=False,
            target=str(target),
            role=role,
            requested_dialect=dialect,
            resolved_dialect="w0m-openspec",
            dry_run=dry_run,
            error=(
                f"Refusing to bootstrap client spec overlays into {target}: `.w0m/sdlc.json` already exists "
                "(governed by w0m-sdlc-* gates). Pass --force only when intentionally adding a secondary overlay."
            ),
        )

    try:
        resolved = resolve_bootstrap_dialect(target, dialect, role)
    except ValueError as exc:
        return BootstrapResult(
            ok=False,
            target=str(target),
            role=role,
            requested_dialect=dialect,
            resolved_dialect="unknown",
            dry_run=dry_run,
            error=str(exc),
        )

    file_map: dict[str, str] = {}
    empty_dirs: list[str] = []

    if resolved == "github-speckit":
        file_map.update(_speckit_overlays())
        specs_dir = target / ".specify" / "specs"
        has_existing_specs = specs_dir.is_dir() and any(p.is_dir() for p in specs_dir.iterdir())
        if not has_existing_specs:
            file_map.update(_speckit_seed_feature())
    elif resolved == "open-gsd":
        file_map.update(_open_gsd_overlays())
        phases_dir = target / ".planning" / "phases"
        has_existing_phases = phases_dir.is_dir() and any(p.is_dir() for p in phases_dir.iterdir())
        if not has_existing_phases:
            file_map.update(_open_gsd_seed_phase())
    elif resolved == "openspec":
        file_map.update(_openspec_overlays())
        empty_dirs.append("openspec/changes")
        specs_dir = target / "openspec" / "specs"
        has_existing_specs = specs_dir.is_dir() and any(specs_dir.rglob("*.md"))
        if not has_existing_specs:
            file_map.update(_openspec_seed_spec())

    created: list[str] = []
    overwritten: list[str] = []
    preserved: list[str] = []

    if not dry_run:
        for rel_dir in empty_dirs:
            (target / rel_dir).mkdir(parents=True, exist_ok=True)

    for rel_path, content in sorted(file_map.items()):
        # Hard invariant: never write internal w0m surfaces
        assert not rel_path.startswith((".w0m/", ".tasks/")) and rel_path not in (
            "TASKS.md",
            "TECH-DEBT.md",
        )
        dest = target / rel_path
        if dest.exists():
            if force:
                overwritten.append(rel_path)
                if not dry_run:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(content, encoding="utf-8")
            else:
                preserved.append(rel_path)
        else:
            created.append(rel_path)
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")

    skills_installed = False
    skills_output = ""
    if install_skills:
        skills_repo = ROOT / "w0m-skills"
        cmd = ["pnpm", "--dir", str(skills_repo), "exec", "tsx", "scripts/install_generic.ts", str(target)]
        if dry_run:
            cmd.append("--dry-run")
        if force:
            cmd.append("--force")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        skills_output = (proc.stdout + "\n" + proc.stderr).strip()
        if proc.returncode != 0:
            return BootstrapResult(
                ok=False,
                target=str(target),
                role=role,
                requested_dialect=dialect,
                resolved_dialect=resolved,
                dry_run=dry_run,
                created_files=created,
                overwritten_files=overwritten,
                preserved_files=preserved,
                skills_installed=False,
                skills_output=skills_output,
                error=f"install_generic.ts failed (exit {proc.returncode}): {skills_output}",
            )
        skills_installed = True

    return BootstrapResult(
        ok=True,
        target=str(target),
        role=role,
        requested_dialect=dialect,
        resolved_dialect=resolved,
        dry_run=dry_run,
        created_files=created,
        overwritten_files=overwritten,
        preserved_files=preserved,
        skills_installed=skills_installed,
        skills_output=skills_output,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap multi-dialect client specifications (.specify/, .planning/, or openspec/) with Testing seams overlays."
    )
    parser.add_argument("target", help="Path to target client repository or workspace root.")
    parser.add_argument(
        "--dialect",
        choices=("auto", *SUPPORTED_BOOTSTRAP_DIALECTS),
        default="auto",
        help="SDD dialect to initialize (default: auto-detect existing markers, else openspec/github-speckit by role).",
    )
    parser.add_argument(
        "--role",
        choices=SUPPORTED_ROLES,
        default="managed",
        help="Client management tier (managed or self-managed; never writes .w0m/).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview files without writing to disk.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing template overlay files.")
    parser.add_argument(
        "--install-skills",
        action="store_true",
        help="Also run w0m-skills/scripts/install_generic.ts to install portable skills.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output.")
    args = parser.parse_args(argv)

    res = bootstrap_client_spec(
        target=Path(args.target),
        dialect=args.dialect,
        role=args.role,
        dry_run=args.dry_run,
        force=args.force,
        install_skills=args.install_skills,
    )
    if args.json:
        print(json.dumps(res.to_dict(), indent=2))
    else:
        if not res.ok:
            print(f"[ERROR] client-spec-init failed: {res.error}", file=sys.stderr)
            return 1
        mode = "DRY-RUN" if res.dry_run else "APPLIED"
        print(
            f"[{mode}] client-spec-init ({res.resolved_dialect}, role={res.role}) -> {res.target}\n"
            f"  created={len(res.created_files)} overwritten={len(res.overwritten_files)} preserved={len(res.preserved_files)}"
        )
        for rel in res.created_files:
            print(f"    + {rel}")
        for rel in res.preserved_files:
            print(f"    = {rel} (preserved)")
    return 0 if res.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
