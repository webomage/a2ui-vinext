#!/usr/bin/env python3
"""Fail-closed Infisical dead-environment-variable backup, prune, and restore helper (T730, T731).

Security & Operational Invariants:
- NEVER prints, logs, or writes plaintext secret values to disk, stdout, or stderr.
- Cross-validates every candidate key against `scripts/env_usage_audit.py`: a key is eligible
  for deletion ONLY if `status == "DEAD_UNUSED"` (`0` executable runtime, CLI/sync, or test readers).
- Runs in `dry-run` mode by default; mutates Infisical ONLY when `--apply` is passed.
- Before deleting any key on `--apply`, captures (or verifies an existing `--backup-archive`)
  an `AES-256-GCM` encrypted backup under `~/.w0m/backups/infisical/` (`0o700` dir, `0o600` files)
  via `infisical run --silent`, proving lossless in-memory round-trip decryption before `0 -> 1` delete calls.
"""

from __future__ import annotations

import argparse
import base64
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from env_usage_audit import (  # noqa: E402
    DEFAULT_ESTATE_REPOS,
    DEFAULT_INFISICAL_PROJECT_ID,
    HISTORICAL_DIGEST_LEAK_KEYS,
    audit_env_keys,
    discover_infisical_key_names,
    discover_static_candidate_keys,
)

DEFAULT_BACKUP_DIR = Path.home() / ".w0m" / "backups" / "infisical"
BACKUP_SCHEMA_VERSION = 1
BACKUP_CIPHER = "AES-256-GCM"
MASTER_KEY_FILENAME = "master.key"


def classify_dead_key_group(key: str) -> str:
    if key in HISTORICAL_DIGEST_LEAK_KEYS:
        return "historical_leak_dead"
    if key.startswith(
        (
            "SIGNOZ_",
            "PUBLIC_SIGNOZ_",
            "POSTHOG_PROJECT_",
            "PUBLIC_POSTHOG_",
            "HONEYCOMB_MANAGEMENT_",
        )
    ):
        return "retired_observability"
    if key.startswith("OCI_"):
        return "retired_oci_provisioning"
    if key in {
        "COHERE_API_KEY",
        "GROQ_API_KEY",
        "HATCHET_CLIENT_TOKEN",
        "HUGGINGFACE_API_TOKEN",
        "MISTRAL_TEST_MODEL",
        "GEMINI_TEST_MODEL",
        "CF_RUNTIME_API_TOKEN",
        "OPIK_API_KEY",
    }:
        return "retired_ai_or_queue"
    return "retired_qa_demo_or_metadata"


def _ensure_secure_backup_dir(backup_dir: Path) -> Path:
    resolved = backup_dir.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(resolved, 0o700)
    return resolved


def _write_private_bytes(target: Path, payload: bytes) -> None:
    tmp_path = target.with_name(f".{target.name}.tmp.{os.getpid()}")
    fd = os.open(str(tmp_path), os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, target)
    os.chmod(target, 0o600)


def _load_or_create_master_key(backup_dir: Path) -> bytes:
    secure_dir = _ensure_secure_backup_dir(backup_dir)
    key_path = secure_dir / MASTER_KEY_FILENAME
    if key_path.is_file():
        os.chmod(key_path, 0o600)
        raw = base64.b64decode(key_path.read_text(encoding="ascii").strip())
        if len(raw) != 32:
            raise ValueError(f"Invalid master key length in {key_path}: expected 32 bytes")
        return raw

    fresh = os.urandom(32)
    encoded = (base64.b64encode(fresh).decode("ascii") + "\n").encode("ascii")
    try:
        fd = os.open(str(key_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        os.chmod(key_path, 0o600)
        return base64.b64decode(key_path.read_text(encoding="ascii").strip())
    try:
        os.write(fd, encoded)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(key_path, 0o600)
    return fresh


def _build_aad_bytes(
    *,
    schema_version: int,
    cipher: str,
    project_id: str,
    infisical_env: str,
    created_at: str,
    key_names: Sequence[str],
) -> bytes:
    aad_obj = {
        "schema_version": schema_version,
        "cipher": cipher,
        "project_id": project_id,
        "infisical_env": infisical_env,
        "created_at": created_at,
        "key_names": list(key_names),
    }
    return json.dumps(aad_obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decrypt_archive_to_mapping(
    archive_path: Path,
    *,
    backup_dir: Path | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    resolved_archive = archive_path.expanduser().resolve()
    if not resolved_archive.is_file():
        raise ValueError(f"Encrypted backup archive does not exist: {resolved_archive}")

    eff_backup_dir = (backup_dir or resolved_archive.parent).expanduser().resolve()
    key_path = eff_backup_dir / MASTER_KEY_FILENAME
    if not key_path.is_file():
        raise ValueError(f"Master encryption key not found at {key_path}")

    master_key = base64.b64decode(key_path.read_text(encoding="ascii").strip())
    if len(master_key) != 32:
        raise ValueError(f"Invalid master key length in {key_path}")

    try:
        envelope = json.loads(resolved_archive.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Corrupt encrypted backup envelope {resolved_archive}: {exc}") from exc

    if envelope.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise ValueError(f"Unsupported backup schema_version: {envelope.get('schema_version')}")
    if envelope.get("cipher") != BACKUP_CIPHER:
        raise ValueError(f"Unsupported backup cipher: {envelope.get('cipher')}")

    key_names = envelope.get("key_names")
    if not isinstance(key_names, list) or not all(isinstance(k, str) for k in key_names):
        raise ValueError("Invalid key_names list in encrypted backup envelope")

    nonce = base64.b64decode(str(envelope.get("nonce_b64", "")))
    ciphertext = base64.b64decode(str(envelope.get("ciphertext_b64", "")))
    actual_sha256 = hashlib.sha256(ciphertext).hexdigest()
    if actual_sha256 != envelope.get("ciphertext_sha256"):
        raise ValueError("Ciphertext SHA-256 mismatch in encrypted backup envelope")

    aad_bytes = _build_aad_bytes(
        schema_version=int(envelope["schema_version"]),
        cipher=str(envelope["cipher"]),
        project_id=str(envelope["project_id"]),
        infisical_env=str(envelope["infisical_env"]),
        created_at=str(envelope["created_at"]),
        key_names=key_names,
    )
    try:
        plaintext_bytes = AESGCM(master_key).decrypt(nonce, ciphertext, aad_bytes)
    except InvalidTag as exc:
        raise ValueError(
            f"AES-256-GCM authentication failed (tampered envelope or wrong key) for {resolved_archive}"
        ) from exc

    decoded = json.loads(plaintext_bytes.decode("utf-8"))
    if not isinstance(decoded, dict) or sorted(decoded.keys()) != sorted(key_names):
        raise ValueError("Decrypted backup key set does not match authenticated envelope metadata")

    clean_map = {str(k): str(v) for k, v in decoded.items()}
    return envelope, clean_map


def write_encrypted_backup_from_mapping(
    *,
    secret_map: Mapping[str, str],
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    project_id: str = DEFAULT_INFISICAL_PROJECT_ID,
    infisical_env: str = "beta",
) -> dict[str, Any]:
    """Encrypt `{key: value}` in memory with AES-256-GCM, round-trip verify, and write 0o600 files."""
    if not secret_map:
        raise ValueError("Refusing to write an empty encrypted secret backup")

    secure_dir = _ensure_secure_backup_dir(backup_dir)
    master_key = _load_or_create_master_key(secure_dir)

    now = datetime.now(tz=UTC)
    created_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    sorted_keys = sorted(secret_map.keys())
    normalized_map = {k: str(secret_map[k]) for k in sorted_keys}

    aad_bytes = _build_aad_bytes(
        schema_version=BACKUP_SCHEMA_VERSION,
        cipher=BACKUP_CIPHER,
        project_id=project_id,
        infisical_env=infisical_env,
        created_at=created_at,
        key_names=sorted_keys,
    )
    nonce = os.urandom(12)
    plaintext_bytes = json.dumps(normalized_map, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(master_key).encrypt(nonce, plaintext_bytes, aad_bytes)
    ciphertext_sha256 = hashlib.sha256(ciphertext).hexdigest()

    # Immediate in-memory round-trip check before writing or returning success.
    roundtrip_plain = AESGCM(master_key).decrypt(nonce, ciphertext, aad_bytes)
    roundtrip_map = json.loads(roundtrip_plain.decode("utf-8"))
    if roundtrip_map != normalized_map:
        raise RuntimeError("In-memory AES-256-GCM round-trip verification failed")

    stem = f"pruned-{infisical_env}-{stamp}"
    archive_path = secure_dir / f"{stem}.aesgcm"
    manifest_path = secure_dir / f"{stem}.manifest.json"

    envelope = {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "cipher": BACKUP_CIPHER,
        "project_id": project_id,
        "infisical_env": infisical_env,
        "created_at": created_at,
        "key_names": sorted_keys,
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        "ciphertext_sha256": ciphertext_sha256,
    }
    _write_private_bytes(archive_path, (json.dumps(envelope, indent=2, sort_keys=True) + "\n").encode("utf-8"))

    groups: dict[str, list[str]] = {}
    for k in sorted_keys:
        groups.setdefault(classify_dead_key_group(k), []).append(k)

    manifest = {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "cipher": BACKUP_CIPHER,
        "project_id": project_id,
        "infisical_env": infisical_env,
        "created_at": created_at,
        "archive_path": str(archive_path),
        "master_key_path": str(secure_dir / MASTER_KEY_FILENAME),
        "backed_up_count": len(sorted_keys),
        "backed_up_keys": sorted_keys,
        "groups": groups,
        "ciphertext_sha256": ciphertext_sha256,
        "roundtrip_verified": True,
    }
    _write_private_bytes(manifest_path, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))

    # Verify the written file on disk decrypts cleanly via the public verifier.
    disk_verified = verify_encrypted_backup(archive_path, backup_dir=secure_dir)
    if not disk_verified["verified"] or disk_verified["key_count"] != len(sorted_keys):
        raise RuntimeError("On-disk AES-256-GCM backup verification failed")

    return {
        "verified": True,
        "roundtrip_verified": True,
        "cipher": BACKUP_CIPHER,
        "created_at": created_at,
        "archive_path": str(archive_path),
        "manifest_path": str(manifest_path),
        "backed_up_count": len(sorted_keys),
        "backed_up_keys": sorted_keys,
        "ciphertext_sha256": ciphertext_sha256,
    }


def verify_encrypted_backup(
    archive_path: Path,
    *,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    """Authenticate and decrypt `archive_path` in RAM, returning non-secret metadata only."""
    envelope, clean_map = _decrypt_archive_to_mapping(archive_path, backup_dir=backup_dir)
    key_names = sorted(clean_map.keys())
    clean_map.clear()
    return {
        "verified": True,
        "cipher": str(envelope["cipher"]),
        "project_id": str(envelope["project_id"]),
        "infisical_env": str(envelope["infisical_env"]),
        "created_at": str(envelope["created_at"]),
        "archive_path": str(archive_path.expanduser().resolve()),
        "key_count": len(key_names),
        "key_names": key_names,
        "ciphertext_sha256": str(envelope["ciphertext_sha256"]),
    }


def capture_infisical_encrypted_backup(
    *,
    root: Path,
    dead_keys: Sequence[str],
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    infisical_env: str = "beta",
    project_id: str = DEFAULT_INFISICAL_PROJECT_ID,
) -> dict[str, Any]:
    """Spawn an `infisical run --silent` child to encrypt `dead_keys` in RAM without exposing values."""
    requested = sorted({k.strip() for k in dead_keys if k and k.strip()})
    if not requested:
        raise ValueError("No DEAD_UNUSED keys supplied for encrypted backup")

    stdin_payload = json.dumps(
        {
            "keys": requested,
            "backup_dir": str(backup_dir.expanduser().resolve()),
            "project_id": project_id,
            "infisical_env": infisical_env,
        }
    )
    proc = subprocess.run(
        [
            "infisical",
            "run",
            f"--projectId={project_id}",
            f"--env={infisical_env}",
            "--silent",
            "--",
            sys.executable,
            str(Path(__file__).resolve()),
            "--internal-capture-stdin",
        ],
        cwd=str(root),
        input=stdin_payload,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        err_msg = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"Encrypted Infisical pre-prune backup failed (exit {proc.returncode}): {err_msg}")

    summary: dict[str, Any] = json.loads(proc.stdout.strip())
    if not summary.get("verified") or summary.get("backed_up_keys") != requested:
        raise RuntimeError("Encrypted Infisical backup returned incomplete key set; aborting")
    return summary


def restore_encrypted_backup(
    *,
    archive_path: Path,
    backup_dir: Path | None = None,
    keys: Sequence[str] | None = None,
    infisical_env: str | None = None,
    project_id: str | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Restore all or selected keys from an encrypted `.aesgcm` archive back to Infisical."""
    envelope, secret_map = _decrypt_archive_to_mapping(archive_path, backup_dir=backup_dir)
    target_env = infisical_env or str(envelope["infisical_env"])
    target_project = project_id or str(envelope["project_id"])

    if keys:
        selected = sorted({k.strip() for k in keys if k and k.strip()})
        missing = [k for k in selected if k not in secret_map]
        if missing:
            secret_map.clear()
            raise ValueError(f"Key(s) not present in encrypted backup archive: {', '.join(missing)}")
    else:
        selected = sorted(secret_map.keys())

    restored: list[str] = []
    try:
        if apply:
            for k in selected:
                val = secret_map[k]
                proc = subprocess.run(
                    [
                        "infisical",
                        "secrets",
                        "set",
                        f"{k}={val}",
                        f"--env={target_env}",
                        f"--projectId={target_project}",
                        "--silent",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                if proc.returncode != 0:
                    scrubbed = (proc.stderr or "").replace(val, "[REDACTED]").strip()
                    raise RuntimeError(f"Failed restoring {k} to Infisical ({target_env}): {scrubbed}")
                restored.append(k)
    finally:
        secret_map.clear()

    return {
        "mode": "restored" if apply else "dry-run",
        "archive_path": str(archive_path.expanduser().resolve()),
        "infisical_env": target_env,
        "project_id": target_project,
        "selected_count": len(selected),
        "selected_keys": selected,
        "restored_count": len(restored),
        "restored_keys": restored,
    }


def prune_dead_infisical_keys(
    root: Path,
    candidate_keys: Sequence[str],
    explicit_targets: Sequence[str] | None = None,
    repos: Sequence[str] = DEFAULT_ESTATE_REPOS,
    infisical_env: str = "beta",
    project_id: str = DEFAULT_INFISICAL_PROJECT_ID,
    backup: bool = False,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    backup_archive: Path | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    report = audit_env_keys(root, candidate_keys, repos=repos)
    by_key = {row["key"]: row for row in report["keys"]}

    if explicit_targets:
        requested = sorted({k.strip() for k in explicit_targets if k and k.strip()})
        unsafe = [k for k in requested if by_key.get(k, {}).get("status") != "DEAD_UNUSED"]
        if unsafe:
            details = ", ".join(
                f"{k} ({by_key.get(k, {}).get('status', 'UNAUDITED')})" for k in unsafe
            )
            raise ValueError(
                f"Refusing to prune active/non-dead environment variable(s): {details}"
            )
        dead_keys = requested
    else:
        dead_keys = sorted(
            row["key"] for row in report["keys"] if row["status"] == "DEAD_UNUSED"
        )

    protected_active = sorted(
        row["key"] for row in report["keys"] if row["status"] != "DEAD_UNUSED"
    )

    groups: dict[str, list[str]] = {}
    for key in dead_keys:
        grp = classify_dead_key_group(key)
        groups.setdefault(grp, []).append(key)

    backup_summary: dict[str, Any] | None = None
    if dead_keys and (backup or apply):
        if backup_archive is not None:
            verified = verify_encrypted_backup(backup_archive, backup_dir=backup_dir)
            missing = sorted(set(dead_keys) - set(verified["key_names"]))
            if missing:
                raise ValueError(
                    f"Provided --backup-archive is missing {len(missing)} target key(s): {', '.join(missing)}"
                )
            backup_summary = verified
        else:
            backup_summary = capture_infisical_encrypted_backup(
                root=root,
                dead_keys=dead_keys,
                backup_dir=backup_dir,
                infisical_env=infisical_env,
                project_id=project_id,
            )

    deleted_keys: list[str] = []
    if apply and dead_keys:
        if not backup_summary or not backup_summary.get("verified"):
            raise RuntimeError("Refusing to delete Infisical keys without a verified encrypted backup")
        for key in dead_keys:
            subprocess.run(
                [
                    "infisical",
                    "secrets",
                    "delete",
                    key,
                    f"--env={infisical_env}",
                    f"--projectId={project_id}",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            deleted_keys.append(key)

    mode = "applied" if apply else ("backed-up" if backup else "dry-run")
    return {
        "mode": mode,
        "infisical_env": infisical_env,
        "project_id": project_id,
        "total_audited": report["total_keys"],
        "dead_count": len(dead_keys),
        "dead_keys": dead_keys,
        "deleted_keys": deleted_keys,
        "protected_active_count": len(protected_active),
        "protected_active_keys": protected_active,
        "groups": groups,
        "backup": backup_summary,
    }


def _run_internal_capture_from_stdin() -> int:
    spec = json.loads(sys.stdin.read())
    keys = [str(k) for k in spec["keys"]]
    missing = [k for k in keys if k not in os.environ]
    if missing:
        print(
            f"Missing expected Infisical key(s) in injected environment: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1

    secret_map = {k: os.environ[k] for k in keys}
    try:
        meta = write_encrypted_backup_from_mapping(
            secret_map=secret_map,
            backup_dir=Path(str(spec["backup_dir"])),
            project_id=str(spec["project_id"]),
            infisical_env=str(spec["infisical_env"]),
        )
    finally:
        secret_map.clear()

    print(json.dumps(meta, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Estate root path",
    )
    ap.add_argument(
        "--infisical",
        action="store_true",
        help="Discover candidate key names live from Infisical (key names only)",
    )
    ap.add_argument(
        "--infisical-env",
        default="beta",
        help="Infisical environment slug (default: beta)",
    )
    ap.add_argument(
        "--project-id",
        default=DEFAULT_INFISICAL_PROJECT_ID,
        help="Infisical project ID",
    )
    ap.add_argument(
        "--key",
        action="append",
        default=[],
        help="Restrict prune or restore to specific key name(s)",
    )
    ap.add_argument(
        "--backup",
        action="store_true",
        help="Write & verify an AES-256-GCM encrypted backup of DEAD_UNUSED keys without deleting",
    )
    ap.add_argument(
        "--backup-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
        help=f"Encrypted backup directory (default: {DEFAULT_BACKUP_DIR})",
    )
    ap.add_argument(
        "--backup-archive",
        type=Path,
        default=None,
        help="Existing verified .aesgcm backup archive to validate before --apply",
    )
    ap.add_argument(
        "--verify-backup",
        type=Path,
        default=None,
        help="Verify AES-256-GCM tag, AAD, and key list of an encrypted .aesgcm archive",
    )
    ap.add_argument(
        "--restore-backup",
        type=Path,
        default=None,
        help="Restore all (or --key selected) secrets from an encrypted .aesgcm archive",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Execute Infisical mutation (auto-backups before delete; applies restore when paired with --restore-backup)",
    )
    ap.add_argument("--json", action="store_true", help="Emit JSON summary")
    ap.add_argument(
        "--internal-capture-stdin",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.internal_capture_stdin:
        return _run_internal_capture_from_stdin()

    try:
        if args.verify_backup is not None:
            verified = verify_encrypted_backup(args.verify_backup, backup_dir=args.backup_dir)
            if args.json:
                print(json.dumps(verified, indent=2, sort_keys=True))
            else:
                print(
                    f"[VERIFIED] {verified['archive_path']} ({verified['cipher']}, "
                    f"env={verified['infisical_env']}, keys={verified['key_count']}, "
                    f"sha256={verified['ciphertext_sha256'][:16]}...)"
                )
            return 0

        if args.restore_backup is not None:
            restored = restore_encrypted_backup(
                archive_path=args.restore_backup,
                backup_dir=args.backup_dir,
                keys=args.key or None,
                infisical_env=args.infisical_env if "--infisical-env" in (argv or sys.argv[1:]) else None,
                project_id=args.project_id if "--project-id" in (argv or sys.argv[1:]) else None,
                apply=args.apply,
            )
            if args.json:
                print(json.dumps(restored, indent=2, sort_keys=True))
            else:
                banner = "RESTORED" if args.apply else "RESTORE-DRY-RUN"
                print(
                    f"[{banner}] {restored['archive_path']} -> env={restored['infisical_env']}: "
                    f"selected={restored['selected_count']}, restored={restored['restored_count']}"
                )
            return 0

        root = args.root.resolve()
        if args.infisical:
            candidates = discover_infisical_key_names(
                root,
                project_id=args.project_id,
                infisical_env=args.infisical_env,
            )
        else:
            candidates = discover_static_candidate_keys(root)

        if args.key:
            candidates = sorted(set(candidates) | {k.strip() for k in args.key if k.strip()})

        summary = prune_dead_infisical_keys(
            root=root,
            candidate_keys=candidates,
            explicit_targets=args.key or None,
            infisical_env=args.infisical_env,
            project_id=args.project_id,
            backup=args.backup,
            backup_dir=args.backup_dir,
            backup_archive=args.backup_archive,
            apply=args.apply,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"[FAIL] env-prune-dead: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    mode_banner = summary["mode"].upper()
    print(
        f"[{mode_banner}] env-prune-dead ({summary['infisical_env']}): "
        f"{summary['dead_count']} DEAD_UNUSED key(s) eligible "
        f"({summary['protected_active_count']} active key(s) protected)"
    )
    if summary.get("backup"):
        bmeta = summary["backup"]
        count = bmeta.get("backed_up_count", bmeta.get("key_count", 0))
        print(
            f"  - encrypted_backup ({bmeta['cipher']}): {bmeta['archive_path']} "
            f"({count} key(s), sha256={bmeta['ciphertext_sha256'][:16]}...)"
        )
    for grp, items in sorted(summary["groups"].items()):
        print(f"  - {grp} ({len(items)}): {', '.join(items)}")
    if summary["mode"] == "applied":
        print(f"  -> Pruned {len(summary['deleted_keys'])} DEAD_UNUSED key(s) from Infisical ({summary['infisical_env']}).")
    elif summary["dead_keys"]:
        print("  -> Pass `--infisical --apply` to auto-backup (`AES-256-GCM`) and delete these dead keys.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
