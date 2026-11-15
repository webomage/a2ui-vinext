from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import w0m_job_hunter as jh


def test_resolve_include_all_and_exclude() -> None:
    all_sources = jh.resolve_active_sources(["all"], [])
    assert len(all_sources) == 13
    assert "upwork" in all_sources

    no_upwork = jh.resolve_active_sources(["all"], ["upwork"])
    assert len(no_upwork) == 12
    assert "upwork" not in no_upwork

    subset = jh.resolve_active_sources(["hn", "ats", "wwr"], ["ats"])
    assert subset == ["hn", "weworkremotely"]


def test_search_jobs_excludes_upwork_and_grounds_cv() -> None:
    res = jh.search_jobs(
        include_sources=["all"],
        exclude_sources=["upwork"],
        query="devops kubernetes terraform",
        remote_only=True,
        usd_only=True,
        limit=20,
    )
    assert len(res["active_sources"]) == 12
    assert res["total_matched"] > 0
    assert res["grounding"]["cv_token_count"] > 0
    for item in res["results"]:
        assert item["source"] != "upwork"
        assert item["currency"] == "USD"
        assert item["remote"] is True
        assert item["rrf_score"] > 0


def test_search_jobs_includes_all_when_no_exclusions() -> None:
    res = jh.search_jobs(
        include_sources=["all"],
        exclude_sources=[],
        query="sre ai-agents aws",
        remote_only=True,
        usd_only=True,
        limit=20,
    )
    assert len(res["active_sources"]) == 13
    assert any(item["source"] == "upwork" for item in res["results"])


def test_cli_json_output(capsys) -> None:
    rc = jh.main(["--include", "all", "--exclude", "upwork", "--usd-only", "--remote-only", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["active_sources"]) == 12
    assert all(r["source"] != "upwork" for r in out["results"])
