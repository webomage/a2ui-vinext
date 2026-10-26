#!/usr/bin/env python3
"""Red probes for the estate search tool (T406 AC3, T509 AC12).

    just py-test-file scripts/tests/test_estate_search.py

🔬 The probe that matters most is `test_unsearchable_repo_is_not_reported_as_zero_hits`. The whole
reason this tool exists is that a search which looks at nothing returns "no matches" in 0.06s and
reads exactly like a search that looked everywhere. If that distinction ever collapses, the tool
has become the bug it was written to prevent.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))
import estate_search as S  # noqa: E402


def _repo(path: Path, files: dict[str, str]) -> Path:
    """A real git repo — the tool shells out to git, so a fake directory would not exercise it."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    for name, body in files.items():
        f = path / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=path, check=True)
    return path


def test_finds_a_tracked_hit(tmp_path: Path) -> None:
    r = _repo(tmp_path / "r", {"a.ts": "const needle = 1;\n"})
    hits, _ = S.search_tree(r, "needle", fixed=False, paths=[])
    assert len(hits) == 1 and "a.ts" in hits[0]


def test_no_match_is_a_result_not_an_error(tmp_path: Path) -> None:
    """git grep exits 1 on 'no matches'. Treating that as a failure would make every clean
    search look broken; treating a REAL failure (rc > 1) as zero would do the opposite."""
    r = _repo(tmp_path / "r", {"a.ts": "nothing here\n"})
    hits, _ = S.search_tree(r, "needle", fixed=False, paths=[])
    assert hits == []


def test_git_failure_raises_rather_than_returning_zero(tmp_path: Path) -> None:
    """🔴 rc > 1 must NOT be folded into 'no hits'. An invalid regex is the cheap way to force it."""
    r = _repo(tmp_path / "r", {"a.ts": "x\n"})
    try:
        S.search_tree(r, "a{99999999,", fixed=False, paths=[])
    except RuntimeError:
        return
    raise AssertionError("a git grep failure was reported as a clean search")


def test_unsearchable_repo_is_not_reported_as_zero_hits(tmp_path: Path, capsys, monkeypatch) -> None:
    """🔴 THE PROBE THIS TOOL EXISTS FOR. A directory with no .git must land in UNMEASURABLE and
    make the run exit non-zero — never in the 'searched and matched nothing' bucket."""
    (tmp_path / "wom7web").mkdir()          # exists, but is not a repo
    monkeypatch.setattr(S, "ESTATE", tmp_path)
    monkeypatch.setattr(S, "OWNED", ("wom7web",))
    rc = S.main(["needle"])
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "COULD NOT BE SEARCHED" in out
    assert "real zero" not in out


def test_a_real_zero_says_so(tmp_path: Path, capsys, monkeypatch) -> None:
    """The other half of the same distinction — it must be possible to report a trustworthy zero."""
    _repo(tmp_path / "wom7web", {"a.ts": "nothing\n"})
    monkeypatch.setattr(S, "ESTATE", tmp_path)
    monkeypatch.setattr(S, "OWNED", ("wom7web",))
    rc = S.main(["needle"])
    out = capsys.readouterr().out
    assert rc == 0 and "real zero" in out


def test_output_cap_announces_what_it_hid(tmp_path: Path, capsys, monkeypatch) -> None:
    """Truncation that does not say it truncated is the console-spam fix turning into a data loss."""
    _repo(tmp_path / "wom7web", {"a.ts": "needle\n" * 50})
    monkeypatch.setattr(S, "ESTATE", tmp_path)
    monkeypatch.setattr(S, "OWNED", ("wom7web",))
    S.main(["needle", "--cap", "5"])
    out = capsys.readouterr().out
    assert "45 more line(s) NOT SHOWN" in out


def test_history_search_is_bounded(tmp_path: Path) -> None:
    """Unbounded history is the ~8-minute shape. `--history N` must look at N commits, not all."""
    r = _repo(tmp_path / "r", {"a.ts": "needle v1\n"})
    for i in range(2, 6):
        (r / "a.ts").write_text(f"needle v{i}\n", encoding="utf-8")
        subprocess.run(["git", "commit", "-aqm", f"v{i}"], cwd=r, check=True)
    shallow, _ = S.search_history(r, "needle", fixed=False, depth=2)
    deep, _ = S.search_history(r, "needle", fixed=False, depth=5)
    assert len(shallow) == 2 and len(deep) == 5


def test_noise_pathspec_applies_to_history_too(tmp_path: Path) -> None:
    """Generated files were excluded from the tree search and NOT from the history search in the
    first version, so results grew with the depth bound instead of with the code."""
    r = _repo(tmp_path / "r", {"STATUS-DASHBOARD.html": "needle\n", "a.ts": "needle\n"})
    hits, _ = S.search_history(r, "needle", fixed=False, depth=1)
    assert all("STATUS-DASHBOARD" not in h for h in hits), hits


def test_fixed_mode_does_not_treat_the_pattern_as_a_regex(tmp_path: Path) -> None:
    r = _repo(tmp_path / "r", {"a.ts": "a.c\nabc\n"})
    assert len(S.search_tree(r, "a.c", fixed=True, paths=[])[0]) == 1
    assert len(S.search_tree(r, "a.c", fixed=False, paths=[])[0]) == 2


def test_vendored_forks_are_off_by_default() -> None:
    """They are larger than the rest of the estate combined; including them silently would make
    every search slower and noisier for results nobody asked for."""
    assert set(S.OWNED).isdisjoint(S.VENDORED)
    assert "wom7pr" in S.VENDORED and "wom7web" in S.OWNED and "root" in S.OWNED


def test_root_repo_search_is_supported_and_scoped_to_root_paths(tmp_path: Path, capsys, monkeypatch) -> None:
    """T509 AC12 — `--repo root` (or `@wom` / `w0m`) searches the `@wom` root repo using ROOT_PATHS
    without traversing nested repos."""
    _repo(
        tmp_path,
        {
            "scripts/stale_path_check.py": "def stale_path_check():\n    return 0\n",
            "wom7web/leak.py": "stale_path_check_nested_leak\n",
        },
    )
    monkeypatch.setattr(S, "ESTATE", tmp_path)
    for alias in ("root", "@wom", "w0m"):
        rc = S.main(["stale_path_check", "--repo", alias])
        out = capsys.readouterr().out
        assert rc == 0, out
        assert "scripts/stale_path_check.py" in out
        assert "wom7web/leak.py" not in out
