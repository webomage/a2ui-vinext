"""Tests for T212: Portable w0m Core CLI Toolchain & just Recipe Distribution via w0m-skills Plugin."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

import pytest

# scripts/tests/test_t212_portable_toolchain.py -> estate root is 2 parents up
ESTATE_ROOT = Path(__file__).resolve().parents[2]
W0M_SKILLS_ROOT = ESTATE_ROOT / "w0m-skills"
PORTABLE_CLI = W0M_SKILLS_ROOT / "tools" / "w0m_portable_cli.py"
TEMPLATE_JUST = W0M_SKILLS_ROOT / "templates" / "w0m.just"
TS_CLI = W0M_SKILLS_ROOT / "src" / "cli.ts"
W0M_SKILL_CLI = W0M_SKILLS_ROOT / "w0m_skill.ts"
BRIDGEROAD_ROOT = Path("/home/aleksei/Projects/!proj/bridgeroad")


def _env_with_brew() -> dict[str, str]:
    env = dict(os.environ)
    brew_bin = "/home/linuxbrew/.linuxbrew/bin"
    if brew_bin not in env.get("PATH", ""):
        env["PATH"] = f"{brew_bin}:{env.get('PATH', '')}"
    return env


def _compute_skill_integrity(skill_dir: Path) -> str:
    real_root = skill_dir.resolve()
    lines: list[str] = []
    for root, dirs, files in os.walk(real_root):
        dirs[:] = sorted(d for d in dirs if d not in {".git", "node_modules"})
        for fname in sorted(files):
            full = Path(root) / fname
            rel = full.relative_to(real_root).as_posix()
            digest = hashlib.sha256(full.read_bytes()).hexdigest()
            lines.append(f"{rel}:{digest}")
    lines.sort()
    payload = "\n".join(lines).encode("utf-8")
    return f"sha256-{hashlib.sha256(payload).hexdigest()}"


def test_t212_ac1_template_just_exists_and_has_no_monorepo_hardcoding() -> None:
    """AC1: templates/w0m.just defines portable recipes with zero hardcoded monorepo paths."""
    assert TEMPLATE_JUST.is_file(), f"Missing {TEMPLATE_JUST}"
    content = TEMPLATE_JUST.read_text(encoding="utf-8")

    for recipe in ("tasks", "sync-tickets", "skill-check", "state-bounds", "w0m-status"):
        assert f"{recipe}" in content, f"Missing recipe {recipe} in templates/w0m.just"

    # Must not hardcode the 7-repo w0m estate member names or retired wom7* names
    forbidden = ("w0m-web", "w0m-api", "w0m-cf", "w0m-ext", "w0m-sec", "w0m-mlx", "wom7web", "wom7api", "wom7func", "wom7ext", "wom7sec", "wom7mlx", "casualuser/wom7")  # retired wom7* names
    for token in forbidden:
        assert token not in content, f"templates/w0m.just must not hardcode '{token}'"


def test_t212_ac2_portable_cli_has_no_monorepo_hardcoding() -> None:
    """AC2: tools/w0m_portable_cli.py dynamically resolves repo paths with zero monorepo assumptions."""
    assert PORTABLE_CLI.is_file(), f"Missing {PORTABLE_CLI}"
    content = PORTABLE_CLI.read_text(encoding="utf-8")

    forbidden = ("w0m-web", "w0m-api", "w0m-cf", "w0m-ext", "w0m-sec", "w0m-mlx", "wom7web", "wom7api", "wom7func", "wom7ext", "wom7sec", "wom7mlx", "casualuser/wom7")  # retired wom7* names
    for token in forbidden:
        assert token not in content, f"w0m_portable_cli.py must not hardcode '{token}'"


def test_t212_ac3_claude_plugin_manifests_expose_commands() -> None:
    """AC3: w0m-skills plugin manifests register commands/status.md, sync-tickets.md, tasks.md."""
    expected_commands = [
        "./commands/status.md",
        "./commands/sync-tickets.md",
        "./commands/tasks.md",
    ]
    for rel_cmd in expected_commands:
        cmd_file = W0M_SKILLS_ROOT / rel_cmd[2:]
        assert cmd_file.is_file(), f"Missing command markdown file: {cmd_file}"
        text = cmd_file.read_text(encoding="utf-8")
        assert text.startswith("---\n"), f"Command file {cmd_file} must have YAML frontmatter"

    for manifest_rel in (".claude-plugin/plugin.json", "plugin.json"):
        manifest_path = W0M_SKILLS_ROOT / manifest_rel
        assert manifest_path.is_file(), f"Missing {manifest_path}"
        manifest: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest.get("commands") == expected_commands, (
            f"{manifest_rel} commands mismatch: {manifest.get('commands')} != {expected_commands}"
        )


def test_t212_ac4_and_ac5_client_project_install_and_just_execution(tmp_path: Path) -> None:
    """AC4 & AC5: Install portable toolchain into a clean client repo and execute just recipes."""
    client_repo = tmp_path / "bridgeroad-fixture"
    client_repo.mkdir(parents=True)

    env = _env_with_brew()
    subprocess.run(["git", "init", "-q"], cwd=client_repo, env=env, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:webomage/bridgeroad.git"],
        cwd=client_repo,
        env=env,
        check=True,
    )

    # Create a pre-existing client justfile to prove non-destructive `import? '.w0m/w0m.just'`
    (client_repo / "justfile").write_text(
        "# Client project justfile\n\nbuild:\n    @echo 'client build ok'\n",
        encoding="utf-8",
    )

    # Create .w0m/sdlc.json
    w0m_dir = client_repo / ".w0m"
    w0m_dir.mkdir(parents=True)
    (w0m_dir / "sdlc.json").write_text(
        json.dumps(
            {
                "project": "bridgeroad",
                "paths": {
                    "tasks_dir": ".tasks",
                    "tasks_index": "TASKS.md",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # Create a sample governed skill in .agents/skills/demo-skill
    skill_dir = client_repo / ".agents" / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Demo client skill\n---\n# Demo Skill\n",
        encoding="utf-8",
    )
    integrity = _compute_skill_integrity(skill_dir)
    (w0m_dir / "skills.json").write_text(
        json.dumps(
            {
                "project": "bridgeroad",
                "skills": {
                    "demo-skill": {
                        "provider": "w0m-native",
                        "version": "canonical",
                    }
                },
                "auto_recommend": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (w0m_dir / "skills.lock.json").write_text(
        json.dumps(
            {
                "lockfileVersion": 1,
                "generatedAt": "2026-10-21T00:00:00Z",
                "skills": {
                    "demo-skill": {
                        "provider": "w0m-native",
                        "resolved": "canonical",
                        "scope": "project",
                        "path": ".agents/skills/demo-skill",
                        "integrity": integrity,
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # Create .tasks/T1.md and .tasks/T2.md
    tasks_dir = client_repo / ".tasks"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / "T1.md").write_text(
        "---\n"
        "id: T1\n"
        'title: "Bootstrap client portal authentication"\n'
        "status: in-progress\n"
        "priority: P0\n"
        "type: feat\n"
        "area: auth\n"
        "phase: build\n"
        "---\n\n"
        "## Acceptance criteria\n"
        "- [x] AC1: Configure OAuth provider\n"
        "- [ ] AC2: Verify session cookie\n",
        encoding="utf-8",
    )
    (tasks_dir / "T2.md").write_text(
        "---\n"
        "id: T2\n"
        'title: "Add invoice PDF export"\n'
        "status: open\n"
        "priority: P1\n"
        "type: feat\n"
        "area: billing\n"
        "---\n\n"
        "## Acceptance criteria\n"
        "- [ ] AC1: Render PDF from template\n",
        encoding="utf-8",
    )

    # Create STATE.md within 100-line budget
    (client_repo / "STATE.md").write_text(
        "# STATE — bridgeroad\n\n## PICK UP HERE\n- Active ticket: T1\n",
        encoding="utf-8",
    )

    # Run `tsx src/cli.ts init-tools --project <client_repo>` (AC4)
    init_res = subprocess.run(
        ["pnpm", "exec", "tsx", str(TS_CLI), "init-tools", "--project", str(client_repo)],
        cwd=W0M_SKILLS_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert init_res.returncode == 0, f"init-tools failed: {init_res.stderr}\n{init_res.stdout}"
    assert (client_repo / ".w0m" / "w0m.just").is_file()
    assert (client_repo / ".w0m" / "bin" / "w0m_portable_cli.py").is_file()
    just_text = (client_repo / "justfile").read_text(encoding="utf-8")
    assert "import? '.w0m/w0m.just'" in just_text

    # Re-running init-tools via w0m_skill.ts is idempotent and does not duplicate the import line
    init_res2 = subprocess.run(
        ["pnpm", "exec", "tsx", str(W0M_SKILL_CLI), "init-tools", "--project", str(client_repo)],
        cwd=W0M_SKILLS_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert init_res2.returncode == 0
    assert (client_repo / "justfile").read_text(encoding="utf-8").count("import? '.w0m/w0m.just'") == 1

    # Verify `just tasks`, `just tasks hot`, `just tasks sdlc` work inside the client project (AC5)
    just_bin = shutil.which("just", path=env["PATH"])
    assert just_bin is not None, "just binary must be available"

    tasks_res = subprocess.run(
        [just_bin, "tasks"],
        cwd=client_repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tasks_res.returncode == 0, f"just tasks failed: {tasks_res.stderr}\n{tasks_res.stdout}"
    assert "T1" in tasks_res.stdout
    assert "T2" in tasks_res.stdout
    assert "webomage/bridgeroad" in tasks_res.stdout

    hot_res = subprocess.run(
        [just_bin, "tasks", "hot"],
        cwd=client_repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert hot_res.returncode == 0
    assert "T2" in hot_res.stdout

    # Verify `just skill-check` passes on clean lockfile and fails on tamper
    skill_res = subprocess.run(
        [just_bin, "skill-check"],
        cwd=client_repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert skill_res.returncode == 0, f"just skill-check failed: {skill_res.stderr}\n{skill_res.stdout}"
    assert "1 declared · 1 locked · 1 verified" in skill_res.stdout

    # Tamper with skill and confirm non-zero exit
    (skill_dir / "SKILL.md").write_text("tampered content\n", encoding="utf-8")
    tamper_res = subprocess.run(
        [just_bin, "skill-check"],
        cwd=client_repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tamper_res.returncode != 0, "just skill-check must fail when skill content drifts from lockfile"
    # Restore clean skill content
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Demo client skill\n---\n# Demo Skill\n",
        encoding="utf-8",
    )

    # Verify `just state-bounds` passes on short STATE.md and fails when > 100 lines
    bounds_res = subprocess.run(
        [just_bin, "state-bounds"],
        cwd=client_repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert bounds_res.returncode == 0, f"just state-bounds failed: {bounds_res.stderr}\n{bounds_res.stdout}"

    (client_repo / "STATE.md").write_text("\n".join(f"line {i}" for i in range(120)) + "\n", encoding="utf-8")
    bounds_fail = subprocess.run(
        [just_bin, "state-bounds"],
        cwd=client_repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert bounds_fail.returncode != 0, "just state-bounds must fail when STATE.md exceeds 100 lines"
    (client_repo / "STATE.md").write_text("# STATE — bridgeroad\n", encoding="utf-8")

    # Verify `just sync-tickets --dry-run` resolves dynamic origin (webomage/bridgeroad)
    sync_dry = subprocess.run(
        [just_bin, "sync-tickets", "--dry-run"],
        cwd=client_repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert sync_dry.returncode == 0, f"just sync-tickets --dry-run failed: {sync_dry.stderr}\n{sync_dry.stdout}"
    assert "repo=webomage/bridgeroad" in sync_dry.stdout
    assert "T1" in sync_dry.stdout
    assert "T2" in sync_dry.stdout


@pytest.mark.skipif(not BRIDGEROAD_ROOT.is_dir(), reason="Client project bridgeroad not present on host")
def test_t212_ac5_readonly_discovery_against_real_bridgeroad_client_repo() -> None:
    """AC5: Read-only verification against /home/aleksei/Projects/!proj/bridgeroad."""
    env = _env_with_brew()
    res = subprocess.run(
        ["python3", str(PORTABLE_CLI), "--project", str(BRIDGEROAD_ROOT), "status", "--json"],
        cwd=BRIDGEROAD_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"status --json failed on bridgeroad: {res.stderr}\n{res.stdout}"
    payload: Any = json.loads(res.stdout)
    assert Path(payload["project_root"]).resolve() == BRIDGEROAD_ROOT.resolve()
    assert payload["state_bounds"]["ok"] is True


def test_t567_ac6_unified_w0m_cli_subcommands_replace_k7_tuis(tmp_path: Path) -> None:
    """T567 AC6: Verify `w0m` CLI subcommands (`vm`, `k8s`, `cloud`, `llm`, `spec`, `notify`) work cleanly."""
    env = _env_with_brew()
    for subcmd in ("vm", "k8s", "cloud", "llm", "spec", "notify"):
        res = subprocess.run(
            ["python3", str(PORTABLE_CLI), "--project", str(tmp_path), subcmd, "--json"],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 0, f"w0m {subcmd} failed: {res.stderr}\n{res.stdout}"
        payload: Any = json.loads(res.stdout)
        assert payload["ok"] is True
        assert payload["subcommand"] == subcmd

