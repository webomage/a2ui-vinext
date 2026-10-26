#!/usr/bin/env python3
"""Validate every config in the estate against the schema its own `$schema` key names (T301).

WHY THIS IS SHARED AND NOT COPIED
---------------------------------
T301 measured that five of six policy schemas in this repo were decorative: written, declared, and
loaded by nothing. Fixing that per file means the same twenty lines in every gate, and the copy that
drifts is the one that stops catching things. One implementation, imported by per-tool gates and
run across the whole estate via `just schema-check`.

🔑 A MISSING VALIDATOR AND A CLEAN VALIDATION MUST NOT PRINT THE SAME WORD.
An absent `jsonschema`, an unreadable schema, or a `$schema` naming a file that does not exist are
reported as ERRORS, not skipped. That is the estate's standing rule after a gate reported an
unmeasurable state and a real violation with the same word (T242).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
WEB = ROOT / "w0m-web"

SKIP_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    ".astro",
    "target",
    ".venv",
    "venv",
    "__pycache__",
    ".next",
    "_ext",
    "_in",
    "ext",
    "graphify-out",
    "codegraph-out",
    ".codegraph",
    "vendor",
    "k7",
    "mob",
    "wom7authz",
    "wom7open",
    "w0m-pr",
    "w0m-skills",
}

SCHEMA_REF_RE = re.compile(r'"\$schema"\s*:\s*"([^"]+)"')


def load_json_or_jsonc(path: Path) -> dict[str, Any]:
    """Parse a .json or .jsonc object file, stripping // line comments outside string literals."""
    txt = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonc":
        txt = re.sub(
            r'"(?:\\.|[^"\\])*"|(//[^\n]*)',
            lambda m: "" if m.group(1) else m.group(0),
            txt,
        )
        txt = re.sub(r",\s*([\]}])", r"\1", txt)
    data = json.loads(txt)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} root must be a JSON object")
    return data


def validate_declared_schema(path: Path, doc: dict[str, Any]) -> list[str]:
    """Errors from validating `doc` against the local schema its `$schema` names.

    A remote `$schema` (http/https) returns no errors: nothing here fetches over the network, and
    pretending otherwise would be the vacuous half of this check.
    """
    ref = doc.get("$schema")
    if not ref or not isinstance(ref, str):
        return [f"{path.name} declares no $schema — nothing states its shape"]
    if ref.startswith("http"):
        return []
    schema_path = (path.parent / ref).resolve()
    if not schema_path.is_file() and path.is_symlink():
        schema_path = (path.resolve().parent / ref).resolve()
    if not schema_path.is_file():
        return [f"{path.name} names a schema that does not exist: {ref}"]
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return [f"schema unreadable: {schema_path} — {e}"]
    try:
        import jsonschema
    except ImportError:
        return [f"jsonschema is not installed, so {path.name} could not be validated (skipped, not passed) — "
                "unmeasurable, not passing"]
    validator = jsonschema.Draft7Validator(schema)
    out = []
    # NOT `e`: the `except ... as e` above deletes that name at the end of its block, so reusing it
    # here is a read of a deleted variable. mypy caught it; the runtime would have too, less clearly.
    for err in sorted(validator.iter_errors(doc), key=lambda x: list(x.absolute_path)):
        where = "/".join(str(x) for x in err.absolute_path) or "(root)"
        out.append(f"{path.name} does not validate at {where} (schema {schema_path.name}): {err.message}")
    return out


def discover_declared_schemas(root: Path | None = None) -> list[Path]:
    """Discover every config in `root` declaring a local `$schema` (derived from files, not a static list)."""
    base = (root or ROOT).resolve()
    seen: set[Path] = set()
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for fn in sorted(filenames):
            if not (fn.endswith(".json") or fn.endswith(".jsonc")) or fn.endswith(".schema.json"):
                continue
            if fn in ("package.json", "tsconfig.json"):
                continue
            p = Path(dirpath) / fn
            try:
                real = p.resolve()
            except OSError:
                continue
            if real in seen or not real.is_file():
                continue
            try:
                txt = real.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            m = SCHEMA_REF_RE.search(txt)
            if not m:
                continue
            ref = m.group(1)
            if ref.startswith("http") or "node_modules" in ref:
                continue
            seen.add(real)
            found.append(p)
    return found


def check_all_schemas(root: Path | None = None) -> tuple[list[Path], list[str]]:
    """Validate every discovered config declaring a local `$schema` under `root`."""
    base = (root or ROOT).resolve()
    configs = discover_declared_schemas(base)
    if not configs:
        return [], [f"no local $schema configs discovered under {base} — refusing vacuous pass"]
    valid_configs: list[Path] = []
    errors: list[str] = []
    for cfg in configs:
        try:
            doc = load_json_or_jsonc(cfg)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{cfg.name} unreadable or invalid JSON/JSONC: {exc}")
            continue
        cfg_errors = validate_declared_schema(cfg, doc)
        if cfg_errors:
            errors.extend(cfg_errors)
        else:
            valid_configs.append(cfg)
    return valid_configs, errors


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if "--file" in args:
        idx = args.index("--file")
        if idx + 1 >= len(args):
            print("  [FAIL] --file requires a path")
            return 2
        target_file = Path(args[idx + 1]).resolve()
        try:
            doc = load_json_or_jsonc(target_file)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"  [FAIL] {target_file.name} unreadable or invalid JSON/JSONC: {exc}")
            return 1
        errs = validate_declared_schema(target_file, doc)
        if errs:
            for err in errs:
                print(f"  [FAIL] {err}")
            return 1
        print(f"  [OK] {target_file.name}")
        return 0

    target_root = ROOT
    if "--root" in args:
        idx = args.index("--root")
        if idx + 1 >= len(args):
            print("  [FAIL] --root requires a directory path")
            return 2
        target_root = Path(args[idx + 1]).resolve()
    valid_configs, errors = check_all_schemas(target_root)
    print(f"schema-check: validated {len(valid_configs)} config(s) declaring a local $schema")
    for cfg in valid_configs:
        try:
            rel: Path | str = cfg.resolve().relative_to(target_root.resolve())
        except ValueError:
            rel = cfg
        print(f"  [OK] {rel}")
    if errors:
        for err in errors:
            print(f"  [FAIL] {err}")
        print(f"schema-check FAILED ({len(errors)} error(s))")
        return 1
    print(f"schema-check OK ({len(valid_configs)}/{len(valid_configs)} validated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

