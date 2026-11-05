"""Unit and live-estate tests for `scripts/cf_bindings_inventory.py` (T271 AC8)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import cf_bindings_inventory as cbi  # noqa: E402


def test_strip_jsonc_preserves_urls_and_strips_comments_and_trailing_commas() -> None:
    sample = """
    /**
     * Multi-line comment with https://developers.cloudflare.com/workers/
     */
    {
        // Single-line comment with "quoted" text
        "name": "test-worker",
        "url": "https://example.com//not-a-comment/*still-string*/",
        "observability": {
            "enabled": true,
        },
        "triggers": {
            "crons": ["*/15 * * * *", "0 8 * * *",],
        },
    }
    """
    parsed = json.loads(cbi.strip_jsonc(sample))
    assert parsed["name"] == "test-worker"
    assert parsed["url"] == "https://example.com//not-a-comment/*still-string*/"
    assert parsed["observability"]["enabled"] is True
    assert parsed["triggers"]["crons"] == ["*/15 * * * *", "0 8 * * *"]


def test_parse_wrangler_config_extracts_bindings(tmp_path: Path) -> None:
    cfg_file = tmp_path / "wrangler.jsonc"
    cfg_file.write_text(
        """
        {
            "name": "sample-worker",
            "compatibility_date": "2026-05-06",
            "observability": { "enabled": true },
            "ai": { "binding": "AI" },
            "kv_namespaces": [{ "binding": "CACHE", "id": "abc123" }],
            "r2_buckets": [{ "binding": "ASSETS_R2", "bucket_name": "my-bucket" }],
            "durable_objects": {
                "bindings": [{ "name": "MEM", "class_name": "MemDO" }]
            },
            "queues": {
                "producers": [{ "binding": "JOBS_Q", "queue": "jobs-queue" }],
                "consumers": [{ "queue": "jobs-queue" }]
            },
            "triggers": { "crons": ["0 * * * *"] }
        }
        """,
        encoding="utf-8",
    )
    summary = cbi.parse_wrangler_config(cfg_file, root=tmp_path)
    assert summary["worker_name"] == "sample-worker"
    assert summary["observability"] is True
    assert summary["crons"] == ["0 * * * *"]
    assert summary["bindings"]["ai"] == ["AI"]
    assert summary["bindings"]["kv_namespaces"] == ["CACHE->abc123"]
    assert summary["bindings"]["r2_buckets"] == ["ASSETS_R2->my-bucket"]
    assert summary["bindings"]["durable_objects"] == ["MEM->MemDO"]
    assert summary["bindings"]["queues"] == ["producer:JOBS_Q", "consumer:jobs-queue"]


def test_live_estate_inventory_matches_measured_wrangler_configs() -> None:
    inventory = cbi.build_estate_inventory(ROOT)
    assert inventory["config_count"] == 6
    assert inventory["total_cron_triggers"] == 5

    by_name = {w["worker_name"]: w for w in inventory["workers"]}
    assert set(by_name.keys()) == {
        "wom7api",  # pinned worker script name
        "wom7func",  # pinned worker script name
        "webomage",
        "webomage-cp",
        "webomage-demo",
        "webomage-me",
    }

    # pinned worker wom7api has 19 workflows, AI binding, and CHAT_MEMORY Durable Object, 0 crons
    assert len(by_name["wom7api"]["bindings"]["workflows"]) == 19  # pinned worker
    assert by_name["wom7api"]["bindings"]["ai"] == ["AI"]  # pinned worker
    assert by_name["wom7api"]["bindings"]["durable_objects"] == ["CHAT_MEMORY->ChatMemoryDO"]  # pinned worker
    assert by_name["wom7api"]["crons"] == []  # pinned worker

    # pinned worker wom7func has AI, BROWSER, and all 5 account cron triggers
    assert by_name["wom7func"]["bindings"]["ai"] == ["AI"]  # pinned worker
    assert by_name["wom7func"]["bindings"]["browser"] == ["BROWSER"]  # pinned worker
    assert len(by_name["wom7func"]["crons"]) == 5  # pinned worker

    # webomage (apps/web) has SESSION + SETTINGS KV namespaces, CF_WORKERS + WOM7API services, and PUBLIC_ASSETS + VAULT_R2 R2 buckets
    assert len(by_name["webomage"]["bindings"]["kv_namespaces"]) == 2
    assert by_name["webomage"]["bindings"]["r2_buckets"] == [
        "PUBLIC_ASSETS->wom-public-assets",
        "VAULT_R2->wom-engagement-vaults",
    ]
    assert by_name["webomage-cp"]["bindings"]["r2_buckets"] == ["VAULT_R2->wom-engagement-vaults"]
    assert by_name["webomage-cp"]["bindings"]["ai"] == ["AI"]
    assert by_name["webomage-me"]["bindings"]["r2_buckets"] == ["VAULT_R2->wom-engagement-vaults"]
    assert by_name["webomage-me"]["bindings"]["ai"] == ["AI"]

    # Candidates verified absent from all wrangler configs
    unconfigured = set(inventory["unconfigured_binding_types"])
    for expected_absent in (
        "d1_databases",
        "hyperdrive",
        "queues",
        "vectorize",
        "turnstile",
        "containers",
        "analytics_engine_datasets",
        "send_email",
    ):
        assert expected_absent in unconfigured

    md = cbi.format_markdown_table(inventory)
    assert "| `w0m-api/wrangler.jsonc` | `wom7api` |" in md  # pinned worker
    assert "| `w0m-cf/wrangler.jsonc` | `wom7func` |" in md  # pinned worker
