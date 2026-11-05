#!/usr/bin/env python3
"""test_npx_audit.py — Unit test suite for zero-npx invariant (T398).

Verifies that no active, runnable scripts, package manifests, or justfiles
invoke `npx` instead of native `pnpm exec` or `pnpm dlx`.
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # /Users/proto/Projects/@self/@wom
WEB = ROOT / "w0m-web"
API = ROOT / "w0m-api"
SKILLS = ROOT / "w0m-skills"
EXT = ROOT / "w0m-ext"


class TestPackageManifestsNoNpx(unittest.TestCase):
    """AC1: Verify package manifests use pnpm instead of npx."""

    def test_cp_package_json(self):
        cp_pkg = WEB / "apps" / "cp" / "package.json"
        self.assertTrue(cp_pkg.exists(), f"Missing {cp_pkg}")
        data = json.loads(cp_pkg.read_text(encoding="utf-8"))
        scripts = data.get("scripts", {})
        for name, cmd in scripts.items():
            self.assertNotIn("npx", cmd.split(), f"apps/cp script '{name}' invokes npx: {cmd}")
        self.assertIn("pnpm dlx pagefind@1.5.2", scripts.get("build:search", ""))

    def test_web_package_json(self):
        web_pkg = WEB / "apps" / "web" / "package.json"
        self.assertTrue(web_pkg.exists(), f"Missing {web_pkg}")
        data = json.loads(web_pkg.read_text(encoding="utf-8"))
        scripts = data.get("scripts", {})
        for name, cmd in scripts.items():
            self.assertNotIn("npx", cmd.split(), f"apps/web script '{name}' invokes npx: {cmd}")
        self.assertIn("pnpm dlx pagefind@1.5.2", scripts.get("build:search", ""))


class TestSkillsToolchainNoNpx(unittest.TestCase):
    """AC2: Verify w0m_skill.ts delegates via pnpm dlx/exec rather than npx."""

    def test_w0m_skill_ts_no_npx_spawns(self):
        skill_ts = SKILLS / "w0m_skill.ts"
        self.assertTrue(skill_ts.exists(), f"Missing {skill_ts}")
        content = skill_ts.read_text(encoding="utf-8")
        # Ensure spawnSync("npx" is absent
        self.assertNotIn('spawnSync("npx"', content)
        self.assertNotIn("spawnSync('npx'", content)
        # Ensure native delegation is present
        self.assertIn('spawnSync("pnpm", ["dlx", "skills"', content)
        self.assertIn('spawnSync("pnpm", ["exec", "tsx"', content)


class TestMcpScriptsNoNpx(unittest.TestCase):
    """AC3: Verify MCP helper scripts do not invoke npx."""

    def test_upwork_mcp_sync(self):
        script = WEB / "project" / "scripts" / "upwork_mcp_sync.py"
        self.assertTrue(script.exists(), f"Missing {script}")
        content = script.read_text(encoding="utf-8")
        self.assertNotIn('["npx"', content)
        self.assertIn('["pnpm", "dlx", "mcp-remote"', content)

    def test_probe_upwork_mcp(self):
        script = WEB / "project" / "scripts" / "probe_upwork_mcp.py"
        self.assertTrue(script.exists(), f"Missing {script}")
        content = script.read_text(encoding="utf-8")
        self.assertNotIn('["npx"', content)
        self.assertIn('["pnpm", "dlx", "mcp-remote"', content)

    def test_test_upwork_mcp(self):
        script = WEB / "project" / "scripts" / "test_upwork_mcp.mjs"
        self.assertTrue(script.exists(), f"Missing {script}")
        content = script.read_text(encoding="utf-8")
        self.assertNotIn('"npx"', content)
        self.assertIn('"pnpm", ["dlx", "mcp-remote"', content)

    def test_upwork_harvest_proposals(self):
        script = WEB / "project" / "scripts" / "upwork_harvest_proposals.py"
        self.assertTrue(script.exists(), f"Missing {script}")
        content = script.read_text(encoding="utf-8")
        self.assertNotIn('["npx"', content)
        self.assertIn('["pnpm", "dlx", "mcp-remote"', content)


class TestJustfilesNoRunnableNpx(unittest.TestCase):
    """AC4: Verify justfile recipes do not execute npx."""

    def _assert_no_runnable_npx(self, justfile_path: Path):
        self.assertTrue(justfile_path.exists(), f"Missing {justfile_path}")
        content = justfile_path.read_text(encoding="utf-8")
        for line_no, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            # Ignore comments or echo explanations
            if stripped.startswith("#") or stripped.startswith('echo "') or stripped.startswith("@echo \""):
                continue
            # Check for runnable npx commands
            match = re.search(r"(?:^|[;&|\s])npx\s+", stripped)
            self.assertIsNone(
                match,
                f"{justfile_path.name}:{line_no} contains runnable npx invocation: {stripped}",
            )

    def test_w0m_api_justfile(self):
        self._assert_no_runnable_npx(API / "justfile")

    def test_w0m_ext_justfile(self):
        self._assert_no_runnable_npx(EXT / "justfile")

    def test_root_justfile_and_estate_just(self):
        self._assert_no_runnable_npx(ROOT / "justfile")
        self._assert_no_runnable_npx(ROOT / "just" / "estate.just")


class TestPreCommitConfigsNoNpx(unittest.TestCase):
    """T620 AC1: Verify .pre-commit-config.yaml across all estate repos never invoke npx."""

    def test_pre_commit_hooks_use_pnpm_exec_not_npx(self):
        checked = 0
        for rel in (".", "w0m-web", "w0m-api", "w0m-cf", "w0m-ext", "w0m-sec", "w0m-skills"):
            pc = (ROOT if rel == "." else ROOT / rel) / ".pre-commit-config.yaml"
            if not pc.exists():
                continue
            checked += 1
            for line_no, line in enumerate(pc.read_text(encoding="utf-8").splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                self.assertIsNone(
                    re.search(r"\bnpx\s+", stripped),
                    f"{rel}/.pre-commit-config.yaml:{line_no} invokes npx instead of pnpm exec: {stripped}",
                )
        self.assertGreaterEqual(checked, 6, "Expected at least 6 .pre-commit-config.yaml files across estate")


def run_all() -> int:
    print("\n=== NPX AUDIT TEST SUITE (T398) ===")
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_all())
