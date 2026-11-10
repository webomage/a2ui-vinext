#!/usr/bin/env python3
"""Cross-Dialect Client Spec Bridge & Constitutional/Testing-Seams Validator (T714).

Normalizes specifications, implementation plans, tasks, testing-seams observability,
and proposed package legitimacy across all 4 supported SDD dialects:
  1. `github-speckit` (`.specify/`)
  2. `open-gsd`       (`.planning/`)
  3. `openspec`       (`openspec/`)
  4. `w0m-openspec`   (`.w0m/sdlc.json` + `.tasks/` + `openspec/specs/`)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from package_legitimacy_check import (  # noqa: E402
    _collect_lockfile_packages,
    extract_spec_proposed_packages,
)

CHECKBOX_DONE_RE = re.compile(r"^\s*-\s*\[[xX]\]\s+(.+)$", re.M)
CHECKBOX_OPEN_RE = re.compile(r"^\s*-\s*\[\s\]\s+(.+)$", re.M)
TESTING_SEAMS_RE = re.compile(
    r"(?:##+\s*Testing\s+[Ss]eams|`data-testid`|\bNyquist\b|VALIDATION\.md|checklists/requirements\.md|####\s+Scenario:)",
    re.I,
)
REQ_ID_RE = re.compile(r"\b(?:REQ-[A-Z0-9_-]+|FR-\d{3}|AC\d+)\b")
GSD_TASK_RE = re.compile(r"<task\b[^>]*>", re.I)


@dataclass
class NormalizedFeatureSpec:
    id: str
    title: str
    dialect: str
    path: str
    tasks_done: int
    tasks_total: int
    requirements: list[str]
    has_testing_seams: bool
    verification_status: str  # "verified" | "in_progress" | "unverified"


@dataclass
class NormalizedProjectSpecEnvelope:
    project_root: str
    dialect: str
    features: list[NormalizedFeatureSpec]
    requirements: list[str]
    tasks_done: int
    tasks_total: int
    has_testing_seams: bool
    verification_status: str
    gaps: list[str] = field(default_factory=list)
    package_legitimacy: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": self.project_root,
            "dialect": self.dialect,
            "features": [asdict(f) for f in self.features],
            "requirements": self.requirements,
            "tasks_done": self.tasks_done,
            "tasks_total": self.tasks_total,
            "has_testing_seams": self.has_testing_seams,
            "verification_status": self.verification_status,
            "gaps": self.gaps,
            "package_legitimacy": self.package_legitimacy,
        }


def detect_spec_dialect(project_root: Path) -> str:
    """Detect SDD dialect from filesystem layout."""
    if (project_root / ".w0m" / "sdlc.json").is_file() or (project_root / ".tasks").is_dir():
        return "w0m-openspec"
    if (project_root / ".specify").is_dir():
        return "github-speckit"
    if (project_root / ".planning").is_dir():
        return "open-gsd"
    if (project_root / "openspec").is_dir() or (project_root / "w0m-web" / "openspec").is_dir():
        return "openspec"
    return "unknown"


def _extract_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return fallback


def _count_checkboxes(text: str) -> tuple[int, int]:
    done = len(CHECKBOX_DONE_RE.findall(text))
    open_c = len(CHECKBOX_OPEN_RE.findall(text))
    return done, done + open_c


def _parse_github_speckit(project_root: Path) -> tuple[list[NormalizedFeatureSpec], list[str], list[Path]]:
    spec_root = project_root / ".specify"
    specs_dir = spec_root / "specs"
    features: list[NormalizedFeatureSpec] = []
    all_reqs: set[str] = set()
    scanned_files: list[Path] = []

    constitution = spec_root / "memory" / "constitution.md"
    if constitution.is_file():
        scanned_files.append(constitution)

    if specs_dir.is_dir():
        for fdir in sorted(p for p in specs_dir.iterdir() if p.is_dir()):
            combined = ""
            for name in ("spec.md", "plan.md", "tasks.md", "research.md", "data-model.md"):
                fp = fdir / name
                if fp.is_file():
                    scanned_files.append(fp)
                    combined += "\n" + fp.read_text(encoding="utf-8", errors="ignore")
            req_checklist = fdir / "checklists" / "requirements.md"
            has_checklist = req_checklist.is_file()
            if has_checklist:
                scanned_files.append(req_checklist)
                combined += "\n" + req_checklist.read_text(encoding="utf-8", errors="ignore")

            done, total = _count_checkboxes(combined)
            reqs = sorted(set(REQ_ID_RE.findall(combined)))
            all_reqs.update(reqs)
            has_seams = bool(TESTING_SEAMS_RE.search(combined)) or has_checklist
            v_status = (
                "verified"
                if total > 0 and done == total and has_seams
                else ("in_progress" if done > 0 else "unverified")
            )
            features.append(
                NormalizedFeatureSpec(
                    id=fdir.name,
                    title=_extract_title(combined, fdir.name),
                    dialect="github-speckit",
                    path=str(fdir.relative_to(project_root)),
                    tasks_done=done,
                    tasks_total=total,
                    requirements=reqs,
                    has_testing_seams=has_seams,
                    verification_status=v_status,
                )
            )
    return features, sorted(all_reqs), scanned_files


def _parse_open_gsd(project_root: Path) -> tuple[list[NormalizedFeatureSpec], list[str], list[Path]]:
    plan_root = project_root / ".planning"
    features: list[NormalizedFeatureSpec] = []
    all_reqs: set[str] = set()
    scanned_files: list[Path] = []

    root_combined = ""
    for root_doc in ("PROJECT.md", "REQUIREMENTS.md", "ROADMAP.md", "STATE.md"):
        fp = plan_root / root_doc
        if fp.is_file():
            scanned_files.append(fp)
            txt = fp.read_text(encoding="utf-8", errors="ignore")
            root_combined += "\n" + txt
            all_reqs.update(REQ_ID_RE.findall(txt))

    phases_dir = plan_root / "phases"
    if phases_dir.is_dir():
        for pdir in sorted(p for p in phases_dir.iterdir() if p.is_dir()):
            combined = ""
            has_verification = False
            has_validation = False
            summaries_count = 0
            plans_count = 0
            for md in sorted(pdir.glob("*.md")):
                scanned_files.append(md)
                txt = md.read_text(encoding="utf-8", errors="ignore")
                combined += "\n" + txt
                if md.name.endswith("VERIFICATION.md"):
                    has_verification = True
                if md.name.endswith("VALIDATION.md"):
                    has_validation = True
                if md.name.endswith("SUMMARY.md"):
                    summaries_count += 1
                if md.name.endswith("PLAN.md"):
                    plans_count += 1

            cb_done, cb_total = _count_checkboxes(combined)
            xml_tasks = len(GSD_TASK_RE.findall(combined))
            if cb_total == 0 and xml_tasks > 0:
                total = xml_tasks
                done = xml_tasks if (summaries_count >= plans_count and plans_count > 0) else 0
            else:
                done, total = cb_done, cb_total

            reqs = sorted(set(REQ_ID_RE.findall(combined)))
            all_reqs.update(reqs)
            has_seams = has_validation or has_verification or bool(TESTING_SEAMS_RE.search(combined))
            v_status = (
                "verified"
                if has_verification and (total == 0 or done == total)
                else ("in_progress" if done > 0 or summaries_count > 0 else "unverified")
            )
            features.append(
                NormalizedFeatureSpec(
                    id=pdir.name,
                    title=_extract_title(combined, pdir.name),
                    dialect="open-gsd",
                    path=str(pdir.relative_to(project_root)),
                    tasks_done=done,
                    tasks_total=total,
                    requirements=reqs,
                    has_testing_seams=has_seams,
                    verification_status=v_status,
                )
            )
    elif root_combined:
        done, total = _count_checkboxes(root_combined)
        has_seams = bool(TESTING_SEAMS_RE.search(root_combined))
        features.append(
            NormalizedFeatureSpec(
                id="planning-root",
                title=_extract_title(root_combined, "OpenGSD Project"),
                dialect="open-gsd",
                path=".planning",
                tasks_done=done,
                tasks_total=total,
                requirements=sorted(all_reqs),
                has_testing_seams=has_seams,
                verification_status="verified" if (total > 0 and done == total and has_seams) else "in_progress",
            )
        )

    return features, sorted(all_reqs), scanned_files


def _parse_openspec(project_root: Path, dialect: str = "openspec") -> tuple[list[NormalizedFeatureSpec], list[str], list[Path]]:
    openspec_dir = project_root / "openspec"
    if not openspec_dir.is_dir() and (project_root / "w0m-web" / "openspec").is_dir():
        openspec_dir = project_root / "w0m-web" / "openspec"

    features: list[NormalizedFeatureSpec] = []
    all_reqs: set[str] = set()
    scanned_files: list[Path] = []

    specs_dir = openspec_dir / "specs"
    if specs_dir.is_dir():
        for sdir in sorted(p for p in specs_dir.iterdir() if p.is_dir()):
            spec_md = sdir / "spec.md"
            if not spec_md.is_file():
                continue
            scanned_files.append(spec_md)
            txt = spec_md.read_text(encoding="utf-8", errors="ignore")
            done, total = _count_checkboxes(txt)
            reqs = sorted(set(REQ_ID_RE.findall(txt)))
            all_reqs.update(reqs)
            has_seams = bool(TESTING_SEAMS_RE.search(txt))
            features.append(
                NormalizedFeatureSpec(
                    id=sdir.name,
                    title=_extract_title(txt, sdir.name),
                    dialect=dialect,
                    path=str(spec_md.relative_to(project_root)),
                    tasks_done=done,
                    tasks_total=total,
                    requirements=reqs,
                    has_testing_seams=has_seams,
                    verification_status="verified" if has_seams else "unverified",
                )
            )

    changes_dir = openspec_dir / "changes"
    if changes_dir.is_dir():
        for cdir in sorted(p for p in changes_dir.iterdir() if p.is_dir() and p.name != "archive"):
            combined = ""
            for md in sorted(cdir.rglob("*.md")):
                scanned_files.append(md)
                combined += "\n" + md.read_text(encoding="utf-8", errors="ignore")
            done, total = _count_checkboxes(combined)
            reqs = sorted(set(REQ_ID_RE.findall(combined)))
            all_reqs.update(reqs)
            has_seams = bool(TESTING_SEAMS_RE.search(combined))
            features.append(
                NormalizedFeatureSpec(
                    id=cdir.name,
                    title=_extract_title(combined, cdir.name),
                    dialect=dialect,
                    path=str(cdir.relative_to(project_root)),
                    tasks_done=done,
                    tasks_total=total,
                    requirements=reqs,
                    has_testing_seams=has_seams,
                    verification_status="verified" if (total > 0 and done == total and has_seams) else "in_progress",
                )
            )

    if dialect == "w0m-openspec" and (project_root / ".tasks").is_dir():
        tasks_dir = project_root / ".tasks"
        t_files = sorted(tasks_dir.glob("T*.md"))
        t_done = 0
        t_total = 0
        for tf in t_files:
            txt = tf.read_text(encoding="utf-8", errors="ignore")
            d, tot = _count_checkboxes(txt)
            t_done += d
            t_total += tot
            all_reqs.update(REQ_ID_RE.findall(txt))
        features.append(
            NormalizedFeatureSpec(
                id="w0m-tasks-ledger",
                title=f"w0m Ticket Ledger ({len(t_files)} tickets)",
                dialect="w0m-openspec",
                path=".tasks",
                tasks_done=t_done,
                tasks_total=t_total,
                requirements=[],
                has_testing_seams=True,
                verification_status="verified",
            )
        )

    return features, sorted(all_reqs), scanned_files


def inspect_client_project_specs(
    project_root: Path,
    dialect: str | None = None,
    live_registry: bool = False,
) -> NormalizedProjectSpecEnvelope:
    resolved_root = project_root.resolve()
    resolved_dialect = dialect or detect_spec_dialect(resolved_root)

    if resolved_dialect == "github-speckit":
        features, reqs, scanned_files = _parse_github_speckit(resolved_root)
    elif resolved_dialect == "open-gsd":
        features, reqs, scanned_files = _parse_open_gsd(resolved_root)
    elif resolved_dialect in ("openspec", "w0m-openspec"):
        features, reqs, scanned_files = _parse_openspec(resolved_root, dialect=resolved_dialect)
    else:
        features, reqs, scanned_files = [], [], []

    tasks_done = sum(f.tasks_done for f in features)
    tasks_total = sum(f.tasks_total for f in features)
    has_testing_seams = bool(features) and all(f.has_testing_seams for f in features)

    gaps: list[str] = []
    if resolved_dialect == "unknown":
        gaps.append("No recognized SDD directory (.specify/, .planning/, openspec/, or .w0m/sdlc.json) found")
    elif not features:
        gaps.append(f"Dialect '{resolved_dialect}' detected, but 0 feature/phase specifications found")

    for f in features:
        if not f.has_testing_seams:
            gaps.append(
                f"Feature '{f.id}' ({f.path}) is missing testable observables "
                "('## Testing seams', 'Scenario:', 'VALIDATION.md', or 'checklists/requirements.md')"
            )

    locked = _collect_lockfile_packages(resolved_root)
    pkg_findings = []
    for sf in scanned_files:
        rel = str(sf.relative_to(resolved_root)) if sf.is_relative_to(resolved_root) else str(sf)
        pkg_findings.extend(
            extract_spec_proposed_packages(
                sf.read_text(encoding="utf-8", errors="ignore"),
                manifest_label=rel,
                locked_names=locked,
                live=live_registry,
            )
        )

    slop_pkgs = [p for p in pkg_findings if p.status == "SLOP"]
    sus_pkgs = [p for p in pkg_findings if p.status == "SUS"]
    for sp in slop_pkgs:
        gaps.append(f"[SLOP] Proposed package '{sp.name}' in {sp.manifest}: {sp.reason}")

    if not features or gaps:
        v_status = "in_progress" if features and not slop_pkgs else "unverified"
    else:
        v_status = "verified"

    return NormalizedProjectSpecEnvelope(
        project_root=str(resolved_root),
        dialect=resolved_dialect,
        features=features,
        requirements=reqs,
        tasks_done=tasks_done,
        tasks_total=tasks_total,
        has_testing_seams=has_testing_seams,
        verification_status=v_status,
        gaps=gaps,
        package_legitimacy={
            "ok": len(slop_pkgs) == 0,
            "proposed_count": len(pkg_findings),
            "slop_count": len(slop_pkgs),
            "sus_count": len(sus_pkgs),
            "findings": [asdict(p) for p in pkg_findings],
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cross-dialect SDD spec bridge & testing-seams / package legitimacy validator (T714)."
    )
    parser.add_argument("target", nargs="?", default=".", help="Path to client or estate project root")
    parser.add_argument(
        "--dialect",
        choices=["github-speckit", "open-gsd", "openspec", "w0m-openspec"],
        default=None,
        help="Explicit SDD dialect override",
    )
    parser.add_argument("--live", action="store_true", help="Query live registries for proposed packages")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if testing seams or SLOP gaps exist")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    envelope = inspect_client_project_specs(
        Path(args.target),
        dialect=args.dialect,
        live_registry=args.live,
    )

    if args.json:
        print(json.dumps(envelope.to_dict(), indent=2))
    else:
        print(
            f"[{envelope.verification_status.upper()}] Client Spec Bridge ({envelope.dialect}): "
            f"{len(envelope.features)} feature/phase spec(s) · "
            f"tasks {envelope.tasks_done}/{envelope.tasks_total} · "
            f"testing_seams={envelope.has_testing_seams} · "
            f"pkg_slop={envelope.package_legitimacy.get('slop_count', 0)}"
        )
        for g in envelope.gaps:
            print(f"  - {g}")

    if not envelope.package_legitimacy.get("ok", True):
        return 1
    if args.strict and envelope.gaps:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
