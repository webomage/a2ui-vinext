#!/usr/bin/env python3
"""Synchronize per-engagement Obsidian vaults to Cloudflare R2 (`wom-engagement-vaults`) — T580 AC2.

Reads declared `knowledge_hub` boundaries from `project/policies/clients-policy.json`, filters
each engagement's vault files through client-safe rules (never `inbox/`, `.obsidian/plugins/`,
or `internal/`), includes the mobile-safe `.obsidian/{app,graph}.json` starter config, ensures
bucket `wom-engagement-vaults` and mobile CORS (`app://obsidian.md`, `capacitor://localhost`)
exist, and pushes objects to `r2://<r2_bucket>/<r2_prefix>/<path>` with SHA-256 verification.

Usage:
    python3 scripts/vault_push_r2.py [--engagement <id>] [--dry-run] [--verify]
    just vault-push-r2 [--engagement <id>] [--dry-run] [--verify]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, NoReturn

ESTATE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POLICY = ESTATE_ROOT / "project" / "policies" / "clients-policy.json"
DEFAULT_BUCKET = "wom-engagement-vaults"

DEFAULT_DENIED_PREFIXES: tuple[str, ...] = (
    "inbox/",
    ".obsidian/plugins/",
    ".obsidian/workspace",
    "internal/",
    ".w0m/",
    "openspec/",
    ".tasks/",
    "TECH-DEBT",
    "STATE.md",
    "TASKS.md",
    "LESSONS.md",
)

SAFE_OBSIDIAN_CONFIG_FILES: frozenset[str] = frozenset(
    {
        ".obsidian/app.json",
        ".obsidian/graph.json",
    }
)

INTERNAL_CONTENT_RE = re.compile(
    r"(?:https?://cp\.w0m\.xyz\b|\bjust\s+project-vault-init\b)",
    re.IGNORECASE,
)

MOBILE_CORS_RULES: list[dict[str, Any]] = [
    {
        "AllowedOrigins": [
            "app://obsidian.md",
            "capacitor://localhost",
            "http://localhost",
            "https://cp.webomage.com",
            "https://cp.w0m.xyz",
        ],
        "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
        "AllowedHeaders": ["*"],
        "ExposeHeaders": ["ETag", "Content-Length", "Last-Modified"],
        "MaxAgeSeconds": 3600,
    }
]


def die(msg: str, code: int = 1) -> NoReturn:
    print(f"\n❌ {msg}", file=sys.stderr)
    raise SystemExit(code)


def get_s3_client() -> Any:
    try:
        import boto3  # type: ignore[import-untyped]
        from botocore.config import Config  # type: ignore[import-untyped]
    except ImportError:
        die("boto3 is not installed — `pip install boto3`", 2)

    ak = os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    acct = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if not (ak and sk and acct):
        die(
            "R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / CLOUDFLARE_ACCOUNT_ID not set — "
            "run via `just vault-push-r2` so infisical injects them.",
            2,
        )
    return boto3.client(
        "s3",
        endpoint_url=f"https://{acct}.r2.cloudflarestorage.com",
        aws_access_key_id=ak,
        aws_secret_access_key=sk,
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        region_name="auto",
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_client_safe_vault_file(
    rel_path: str,
    raw_bytes: bytes,
    allowed_prefixes: list[str],
    denied_prefixes: list[str],
) -> bool:
    """Return True if a relative file path inside a project vault is safe to sync to R2."""
    norm = rel_path.replace("\\", "/").lstrip("/")
    if not norm or norm.endswith("/.gitkeep") or norm == ".gitkeep":
        return False

    # Allow strictly the mobile-safe .obsidian/{app,graph}.json starter files
    if norm in SAFE_OBSIDIAN_CONFIG_FILES:
        return True

    denied = set(DEFAULT_DENIED_PREFIXES) | {
        p for p in denied_prefixes if p != ".obsidian/"
    } | {".obsidian/"}
    for prefix in denied:
        if norm == prefix or norm.startswith(prefix) or f"/{prefix}" in norm:
            return False

    if allowed_prefixes:
        if not any(norm == p or norm.startswith(p) for p in allowed_prefixes):
            return False

    if norm.endswith(".md"):
        text = raw_bytes.decode("utf-8", errors="replace")
        if INTERNAL_CONTENT_RE.search(text):
            return False

    return True


def discover_engagement_vaults(
    policy_path: Path = DEFAULT_POLICY,
    root_dir: Path = ESTATE_ROOT,
    filter_engagement: str | None = None,
) -> list[dict[str, Any]]:
    """Return declared engagement vaults from clients-policy.json."""
    if not policy_path.is_file():
        die(f"Policy file not found: {policy_path}", 2)
    data = json.loads(policy_path.read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []
    target = filter_engagement.strip().lower() if filter_engagement else None

    for proj in data.get("projects", []):
        kh = proj.get("knowledge_hub")
        if not isinstance(kh, dict):
            continue
        vault_slug = str(kh.get("vault_slug") or proj.get("id") or "")
        engagement_public_id = str(
            kh.get("engagement_public_id") or f"eg-{vault_slug}"
        )
        r2_bucket = str(kh.get("r2_bucket") or DEFAULT_BUCKET)
        r2_prefix = str(
            kh.get("r2_prefix") or f"engagements/{engagement_public_id}"
        ).strip("/")
        corpus_root = str(kh.get("corpus_root") or "")

        if target and target not in {
            proj.get("id", "").lower(),
            vault_slug.lower(),
            engagement_public_id.lower(),
            str(proj.get("org_slug") or "").lower(),
        }:
            continue

        vault_dir = (root_dir / corpus_root).resolve()
        out.append(
            {
                "project_id": proj.get("id"),
                "org_slug": proj.get("org_slug"),
                "vault_slug": vault_slug,
                "engagement_public_id": engagement_public_id,
                "r2_bucket": r2_bucket,
                "r2_prefix": r2_prefix,
                "corpus_root": corpus_root,
                "vault_dir": vault_dir,
                "allowed_prefixes": list(kh.get("allowed_prefixes") or []),
                "denied_prefixes": list(kh.get("denied_prefixes") or []),
            }
        )
    return out


def collect_vault_files(vault_meta: dict[str, Any]) -> list[tuple[str, Path, bytes]]:
    """Walk an engagement vault directory and return client-safe (rel_path, full_path, bytes)."""
    vault_dir: Path = vault_meta["vault_dir"]
    if not vault_dir.is_dir():
        return []
    collected: list[tuple[str, Path, bytes]] = []
    for p in sorted(vault_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(vault_dir).as_posix()
        raw = p.read_bytes()
        if is_client_safe_vault_file(
            rel,
            raw,
            vault_meta["allowed_prefixes"],
            vault_meta["denied_prefixes"],
        ):
            collected.append((rel, p, raw))
    return collected


def ensure_bucket_and_cors(s3: Any, bucket: str, dry_run: bool) -> None:
    if dry_run:
        print(f"  [dry-run] would ensure bucket r2://{bucket} + mobile CORS rules")
        return
    try:
        s3.head_bucket(Bucket=bucket)
    except Exception:
        print(f"  creating R2 bucket r2://{bucket}...")
        s3.create_bucket(Bucket=bucket)
        s3.head_bucket(Bucket=bucket)

    try:
        s3.put_bucket_cors(
            Bucket=bucket,
            CORSConfiguration={"CORSRules": MOBILE_CORS_RULES},
        )
    except Exception as e:
        print(f"  ⚠️  CORS update warning on {bucket}: {e}", file=sys.stderr)


def push_vault(s3: Any, vault_meta: dict[str, Any], dry_run: bool) -> tuple[int, int]:
    bucket = vault_meta["r2_bucket"]
    prefix = vault_meta["r2_prefix"]
    eg_id = vault_meta["engagement_public_id"]
    vault_slug = vault_meta["vault_slug"]
    files = collect_vault_files(vault_meta)
    if not files:
        die(
            f"engagement vault '{eg_id}' ({vault_meta['corpus_root']}) has 0 client-safe files to push."
        )

    pushed_count = 0
    pushed_bytes = 0
    for rel_path, full_path, raw in files:
        key = f"{prefix}/{rel_path}"
        digest = sha256_bytes(raw)
        size = len(raw)
        content_type = (
            "text/markdown; charset=utf-8"
            if rel_path.endswith(".md")
            else "application/json; charset=utf-8"
            if rel_path.endswith(".json")
            else "application/octet-stream"
        )
        if dry_run:
            print(f"  would push  r2://{bucket}/{key:52} {size:>6,} B")
            pushed_count += 1
            pushed_bytes += size
            continue

        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=raw,
            ContentType=content_type,
            Metadata={
                "sha256": digest,
                "engagement": eg_id,
                "vault_slug": vault_slug,
            },
        )
        head = s3.head_object(Bucket=bucket, Key=key)
        if head["ContentLength"] != size:
            die(
                f"{key}: uploaded {size:,} B but R2 reports {head['ContentLength']:,} B"
            )
        pushed_count += 1
        pushed_bytes += size

    print(
        f"  ✅ {eg_id:26} ({vault_slug:12}) → r2://{bucket}/{prefix}/ ({pushed_count} file(s), {pushed_bytes:,} B)"
    )
    return pushed_count, pushed_bytes


def verify_vaults(s3: Any, vaults: list[dict[str, Any]]) -> int:
    checked = 0
    for v in vaults:
        bucket = v["r2_bucket"]
        prefix = v["r2_prefix"]
        eg_id = v["engagement_public_id"]
        objs = s3.list_objects_v2(Bucket=bucket, Prefix=f"{prefix}/").get(
            "Contents", []
        )
        if not objs:
            die(f"no objects under r2://{bucket}/{prefix}/ — cannot verify {eg_id}.")
        index_key = f"{prefix}/index.md"
        head = s3.head_object(Bucket=bucket, Key=index_key)
        want = head.get("Metadata", {}).get("sha256")
        if not want:
            die(f"{index_key}: missing sha256 metadata in R2.")
        with tempfile.NamedTemporaryFile() as tf:
            s3.download_file(bucket, index_key, tf.name)
            data = Path(tf.name).read_bytes()
            got = sha256_bytes(data)
        if got != want or len(data) != head["ContentLength"]:
            die(
                f"{index_key}: round-trip mismatch ({len(data)} B / {got[:12]} vs {head['ContentLength']} B / {want[:12]})"
            )
        print(
            f"  ✅ verified {eg_id:26} r2://{bucket}/{prefix}/ ({len(objs)} object(s), index.md sha256={got[:12]}…)"
        )
        checked += 1
    if not checked:
        die("verified ZERO engagement vaults.")
    print(f"\n✅ {checked} engagement vault(s) round-tripped and verified in Cloudflare R2.")
    return 0


IOS_EXT_FILES: dict[str, str] = {
    "w0m-ext-ios-orion.xpi": "application/x-xpinstall",
    "w0m-ext-ios-chrome.zip": "application/zip",
    "w0m-ext-safari.zip": "application/zip",
    "ios-packages.json": "application/json; charset=utf-8",
}


def push_ios_ext_packages(s3: Any | None, dry_run: bool) -> int:
    ios_dir = ESTATE_ROOT / "w0m-ext" / "extension" / "dist" / "ios"
    bucket = DEFAULT_BUCKET
    prefix = "releases/w0m-ext"
    if not ios_dir.is_dir():
        die(f"{ios_dir} does not exist — run 'pnpm -C w0m-ext/extension build:ios' first.")
    print(f"\n📦 Pushing iOS extension packages → r2://{bucket}/{prefix}/")
    pushed = 0
    for fname, content_type in IOS_EXT_FILES.items():
        fpath = ios_dir / fname
        if not fpath.is_file():
            die(f"missing {fpath} — run 'pnpm -C w0m-ext/extension build:ios' first.")
        data = fpath.read_bytes()
        digest = sha256_bytes(data)
        key = f"{prefix}/{fname}"
        if dry_run:
            print(f"    🔍 DRY RUN: would upload {key:42} ({len(data):>8,} B, sha256={digest[:12]}…)")
            pushed += 1
            continue
        assert s3 is not None
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            Metadata={"sha256": digest, "channel": "w0m-ext-ios"},
        )
        head = s3.head_object(Bucket=bucket, Key=key)
        if head["ContentLength"] != len(data):
            die(f"{key}: R2 size mismatch ({head['ContentLength']} vs {len(data)})")
        print(f"    ✅ {key:42} ({len(data):>8,} B, sha256={digest[:12]}…)")
        pushed += 1
    print(f"\n✅ Pushed {pushed} iOS extension package file(s) to r2://{bucket}/{prefix}/")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--engagement",
        help="Filter to a single engagement public_id or project slug (e.g. eg-artemio-quiero-comer, servicios777)",
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--verify",
        action="store_true",
        help="Download and verify SHA-256 of index.md for each engagement vault in R2",
    )
    ap.add_argument(
        "--push-ios-ext",
        action="store_true",
        help="Upload built w0m-ext iOS packages (.xpi / .zip) to r2://wom-engagement-vaults/releases/w0m-ext/",
    )
    ap.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    args = ap.parse_args(argv)

    s3 = None if args.dry_run else get_s3_client()
    if args.push_ios_ext:
        return push_ios_ext_packages(s3, args.dry_run)

    vaults = discover_engagement_vaults(
        policy_path=args.policy,
        root_dir=ESTATE_ROOT,
        filter_engagement=args.engagement,
    )
    if not vaults:
        die(
            f"no declared engagement vaults matched {args.engagement or 'clients-policy.json'}."
        )

    if args.verify:
        assert s3 is not None
        return verify_vaults(s3, vaults)

    buckets = sorted({v["r2_bucket"] for v in vaults})
    for b in buckets:
        ensure_bucket_and_cors(s3, b, args.dry_run)

    total_files = 0
    total_bytes = 0
    for v in vaults:
        f_cnt, b_cnt = push_vault(s3, v, args.dry_run)
        total_files += f_cnt
        total_bytes += b_cnt

    if args.dry_run:
        print(
            f"\n🔍 DRY RUN — would push {total_files} file(s) ({total_bytes:,} B) across {len(vaults)} engagement vault(s)."
        )
    else:
        print(
            f"\n✅ Pushed and size-confirmed {total_files} file(s) ({total_bytes:,} B) across {len(vaults)} engagement vault(s) in Cloudflare R2."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
