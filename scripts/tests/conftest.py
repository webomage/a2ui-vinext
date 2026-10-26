"""w0m pytest configuration and custom collector for estate root test scripts (T376, T509)."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterator

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS_DIR.parent
WEB_SCRIPTS_DIR = ROOT / "wom7web" / "project" / "scripts"
REGISTRY_PATH = ROOT / "wom7web" / "project" / "test-suites.json"

for _p in (SCRIPTS_DIR, WEB_SCRIPTS_DIR):
    _s = str(_p)
    if _p.is_dir() and _s not in sys.path:
        sys.path.insert(0, _s)

NON_BLOCKING_SUITES: dict[str, str] = {}
if REGISTRY_PATH.is_file():
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        for s in data.get("suites", []):
            if s.get("blocking") is False:
                reason = s.get("reason", "non-blocking suite in test-suites.json")
                if s.get("name"):
                    NON_BLOCKING_SUITES[s["name"]] = reason
                if s.get("recipe"):
                    NON_BLOCKING_SUITES[s["recipe"]] = reason
    except Exception:
        pass


def is_non_blocking(filename: str) -> str | None:
    stem = filename.removesuffix(".py").removeprefix("test_")
    stem_dash = stem.replace("_", "-")
    for key in (
        stem,
        stem_dash,
        f"{stem}-test",
        f"{stem_dash}-test",
        f"{stem}-check",
        f"{stem_dash}-check",
        f"test_{stem}",
        f"test_{stem_dash}",
    ):
        if key in NON_BLOCKING_SUITES:
            return NON_BLOCKING_SUITES[key]
    return None


def is_script_test(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=path.name)
    except Exception:
        return True

    has_test_construct = False
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if "Test" in node.name or any("TestCase" in ast.unparse(b) for b in node.bases):
                has_test_construct = True
        elif isinstance(node, ast.FunctionDef):
            if node.name.startswith("test_"):
                has_test_construct = True

    has_top_sys_exit = False
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = ast.unparse(node.value)
            if "sys.exit" in call:
                has_top_sys_exit = True
        elif isinstance(node, ast.If):
            test_str = ast.unparse(node.test)
            if "__name__" not in test_str:
                body_str = ast.unparse(node)
                if "sys.exit" in body_str:
                    has_top_sys_exit = True

    return has_top_sys_exit or not has_test_construct


class ScriptTestFailure(Exception):
    pass


class ScriptItem(pytest.Item):
    def __init__(self, name: str, parent: ScriptFile, path: Path) -> None:
        super().__init__(name, parent)
        self.path = path
        reason = is_non_blocking(path.name)
        if reason:
            self.add_marker(pytest.mark.xfail(reason=reason, strict=False))

    def runtest(self) -> None:
        res = subprocess.run(
            [sys.executable, str(self.path)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            out = res.stdout.strip()
            err = res.stderr.strip()
            msg = f"Script {self.name} failed with exit code {res.returncode}\n"
            if out:
                msg += f"--- STDOUT ---\n{out}\n"
            if err:
                msg += f"--- STDERR ---\n{err}\n"
            raise ScriptTestFailure(msg)

    def repr_failure(self, excinfo: pytest.ExceptionInfo) -> str:  # type: ignore[override]
        if excinfo.errisinstance(ScriptTestFailure):
            return str(excinfo.value)
        return str(super().repr_failure(excinfo))

    def reportinfo(self) -> tuple[Path, int, str]:
        return self.path, 0, f"script: {self.name}"


class ScriptFile(pytest.File):
    def collect(self) -> Iterator[ScriptItem]:
        yield ScriptItem.from_parent(self, name=self.path.name, path=self.path)


@pytest.hookimpl(tryfirst=True)
def pytest_pycollect_makemodule(module_path: Path, parent: pytest.Collector) -> pytest.Collector | None:
    if module_path.name.startswith("test_") and module_path.suffix == ".py":
        if is_script_test(module_path):
            return ScriptFile.from_parent(parent, path=module_path)
    return None


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        p = getattr(item, "path", None)
        if p is not None:
            reason = is_non_blocking(p.name)
            if reason and not item.get_closest_marker("xfail"):
                item.add_marker(pytest.mark.xfail(reason=reason, strict=False))
