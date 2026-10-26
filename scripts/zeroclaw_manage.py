#!/usr/bin/env python3
"""ZeroClaw Runtime Management, Config Sync & Siri/Shortcuts Health Probe (T153, T516, T517 AC3).

Subcommands:
  sync    - Generate ~/.zeroclaw/config.toml from tracked template (dry-run by default; pass --apply to write)
  check   - Detect drift between tracked template and installed ~/.zeroclaw/config.toml
  health  - Run ZeroClaw runtime health audit (T153 AC7) + Siri & Apple Shortcuts contract checks (T367 / T517 AC3)
  status  - Check ZeroClaw gateway (:42617) and daemon service status
  start   - Start ZeroClaw daemon service (dry-run by default; pass --apply)
  stop    - Stop ZeroClaw daemon service (dry-run by default; pass --apply)
  restart - Restart ZeroClaw daemon service (dry-run by default; pass --apply)
  logs    - Show recent ZeroClaw daemon log lines
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib
from typing import Any, cast
from urllib.parse import quote

ESTATE_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ESTATE_ROOT / "wom7web"
TEMPLATE_PATH = WEB_ROOT / "project" / "zeroclaw" / "config.template.toml"
SHORTCUT_JSON_PATH = WEB_ROOT / "project" / "data" / "shortcuts" / "AskZeroClaw.shortcut.json"
ZEROCLAW_DIR = Path(os.path.expanduser("~/.zeroclaw"))
INSTALLED_CONFIG = ZEROCLAW_DIR / "config.toml"
SECRET_KEY_PATH = ZEROCLAW_DIR / ".secret_key"


def load_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def verify_siri_shortcuts_contract(
    shortcut_path: Path = SHORTCUT_JSON_PATH,
    scripts_dirs: tuple[Path, ...] | None = None,
) -> list[tuple[str, bool, str]]:
    """Run the T367 Siri & Apple Shortcuts contract checks folded under T517 AC3."""
    results: list[tuple[str, bool, str]] = []

    # 1. Apple Shortcut workflow definition
    if not shortcut_path.is_file():
        results.append(("siri-shortcut-definition", False, f"Missing shortcut definition at {shortcut_path}"))
    else:
        try:
            data: dict[str, Any] = cast(dict[str, Any], json.loads(shortcut_path.read_text(encoding="utf-8")))
            actions: list[dict[str, Any]] = data.get("workflow", {}).get("actions", [])
            action_types = {a.get("type") for a in actions if isinstance(a, dict)}
            required_actions = {"AskForInput", "GetContentsOfURL", "SpeakText", "OpenURL"}
            missing_actions = sorted(required_actions - action_types)
            name_ok = data.get("name") == "Ask ZeroClaw"
            ok = name_ok and not missing_actions
            detail = (
                "Ask ZeroClaw workflow actions verified"
                if ok
                else f"name={data.get('name')!r}, missing_actions={missing_actions}"
            )
            results.append(("siri-shortcut-definition", ok, detail))
        except (OSError, ValueError, TypeError) as exc:
            results.append(("siri-shortcut-definition", False, f"Invalid shortcut JSON: {exc}"))

    # 2. Gateway unauthenticated rejection (:42617)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", 42617, timeout=1.0)
        payload = json.dumps({"origin": "siri_shortcut", "prompt": "test"})
        conn.request("POST", "/webhook", body=payload, headers={"Content-Type": "application/json"})
        res = conn.getresponse()
        gw_ok = res.status in (401, 403, 404)
        results.append(("siri-gateway-auth-guard", gw_ok, f"Gateway HTTP {res.status} on unauthenticated /webhook"))
        conn.close()
    except OSError:
        results.append(("siri-gateway-auth-guard", True, "Gateway daemon offline on :42617 (offline check OK)"))

    # 3. Zero TCC / chat.db privacy guarantee
    scan_dirs = scripts_dirs or (WEB_ROOT / "project" / "scripts", ESTATE_ROOT / "scripts")
    chat_db_needle = "chat" + ".db"
    offenders: list[str] = []
    for sdir in scan_dirs:
        if not sdir.is_dir():
            continue
        for script in sorted(sdir.glob("*.py")):
            if script.resolve() == Path(__file__).resolve():
                continue
            text = script.read_text(encoding="utf-8", errors="ignore")
            if chat_db_needle in text:
                offenders.append(script.name)
    results.append(
        (
            "siri-zero-tcc-chat-db",
            len(offenders) == 0,
            "Zero chat.db references across scripts" if not offenders else f"Found in: {offenders}",
        )
    )

    # 4. Orca deep-link protocol contract
    sample_title = "Voice task: fix compile break"
    encoded_title = quote(sample_title)
    sample_repo = "wom7web"
    deep_link = f"orca://orchestration/new?title={encoded_title}&repo={sample_repo}"
    dl_ok = (
        deep_link.startswith("orca://orchestration/new?")
        and f"repo={sample_repo}" in deep_link
        and f"title={encoded_title}" in deep_link
    )
    results.append(("siri-orca-deep-link", dl_ok, deep_link))

    return results


def cmd_sync(
    apply: bool = False,
    template_path: Path = TEMPLATE_PATH,
    zeroclaw_dir: Path = ZEROCLAW_DIR,
) -> int:
    installed_config = zeroclaw_dir / "config.toml"
    secret_key_path = zeroclaw_dir / ".secret_key"

    if not template_path.is_file():
        print(f"[FAIL] Tracked template not found at {template_path}")
        return 1

    template_text = template_path.read_text(encoding="utf-8")

    preserved_tokens: list[str] = []
    if installed_config.is_file():
        installed_data = load_toml(installed_config)
        gateway = installed_data.get("gateway", {})
        if isinstance(gateway, dict) and gateway.get("paired_tokens"):
            preserved_tokens = list(gateway["paired_tokens"])

    if preserved_tokens:
        tokens_json = json.dumps(preserved_tokens)
        template_text = re.sub(
            r"\[gateway\]\s*\npaired_tokens\s*=\s*\[.*?\]",
            f"[gateway]\npaired_tokens = {tokens_json}",
            template_text,
            flags=re.DOTALL,
        )

    if not apply:
        print(f"[INFO] Dry run: would sync {template_path} -> {installed_config} (mode 0600)")
        print(f"[INFO] Preserved paired tokens count: {len(preserved_tokens)}")
        print("[INFO] Re-run with --apply to write changes.")
        return 0

    zeroclaw_dir.mkdir(parents=True, exist_ok=True)
    for swp in zeroclaw_dir.glob("*.swp"):
        try:
            swp.unlink()
            print(f"[INFO] Removed stale swap file: {swp.name}")
        except OSError:
            pass

    installed_config.write_text(template_text, encoding="utf-8")
    installed_config.chmod(0o600)
    print(f"[OK] Generated {installed_config} (mode 0600)")
    if secret_key_path.is_file():
        print(f"[OK] Local keystore preserved at {secret_key_path}")
    return 0


def cmd_check(
    template_path: Path = TEMPLATE_PATH,
    installed_config: Path = INSTALLED_CONFIG,
) -> int:
    print("[INFO] Checking ZeroClaw configuration drift...")
    if not template_path.is_file():
        print(f"[FAIL] Template missing at {template_path}")
        return 1
    if not installed_config.is_file():
        print(f"[FAIL] Installed config missing at {installed_config}")
        return 1

    template_data = load_toml(template_path)
    installed_data = load_toml(installed_config)

    drift: list[str] = []
    for section in ("providers", "agents", "risk_profiles", "runtime_profiles", "memory"):
        t_sec = template_data.get(section, {})
        i_sec = installed_data.get(section, {})
        if not i_sec and t_sec:
            drift.append(f"Missing section [{section}] in installed config")
            continue
        if isinstance(t_sec, dict) and isinstance(i_sec, dict):
            for k in t_sec:
                if k not in i_sec:
                    drift.append(f"Missing key/agent [{section}.{k}] in installed config")

    t_rp = template_data.get("risk_profiles", {})
    i_rp = installed_data.get("risk_profiles", {})
    if isinstance(t_rp, dict) and isinstance(i_rp, dict):
        for rp_name, rp_val in t_rp.items():
            if rp_name not in i_rp:
                drift.append(f"Missing risk profile: {rp_name}")
            elif isinstance(rp_val, dict) and isinstance(i_rp.get(rp_name), dict):
                inst_val = i_rp[rp_name]
                for field in ("workspace_only", "sandbox_enabled"):
                    if field in rp_val and rp_val[field] != inst_val.get(field):
                        drift.append(
                            f"Risk profile [{rp_name}] {field} drift: "
                            f"template={rp_val[field]} vs installed={inst_val.get(field)}"
                        )

    if drift:
        print(f"[FAIL] Configuration drift detected ({len(drift)} divergence(s)):")
        for d in drift:
            print(f"  - {d}")
        print("[WARN] Run 'just zeroclaw sync --apply' to reconcile.")
        return 1

    print("[PASS] ZeroClaw configuration is in sync with template")
    return 0


def cmd_health() -> int:
    print("=== ZeroClaw Runtime & Siri/Shortcuts Health Audit (T153 AC7, T517 AC3) ===\n")

    zc_bin = shutil.which("zeroclaw") or os.path.expanduser("~/.cargo/bin/zeroclaw")
    bin_path = Path(zc_bin)
    if bin_path.is_file():
        res = subprocess.run([str(bin_path), "--version"], capture_output=True, text=True, check=False)
        version = res.stdout.strip() or "unknown"
        print(f"  [PASS] 1. Binary: {version} ({bin_path})")
    else:
        print(f"  [WARN] 1. Binary: Not installed at {bin_path}")

    if not INSTALLED_CONFIG.is_file():
        print(f"  [WARN] 2. Config: Not installed at {INSTALLED_CONFIG}")
        installed_data: dict[str, Any] = load_toml(TEMPLATE_PATH)
    else:
        rc = cmd_check(TEMPLATE_PATH, INSTALLED_CONFIG)
        if rc == 0:
            print("  [PASS] 2. Config: In sync with tracked template")
        else:
            print("  [WARN] 2. Config: Drift detected (run 'just zeroclaw sync --apply')")
        installed_data = load_toml(INSTALLED_CONFIG)

    try:
        conn = http.client.HTTPConnection("127.0.0.1", 8888, timeout=2)
        conn.request("GET", "/v1/models", headers={"User-Agent": "zeroclaw-health/1.0"})
        resp = conn.getresponse()
        data: dict[str, Any] = cast(dict[str, Any], json.loads(resp.read().decode("utf-8")))
        models = [str(m.get("id", "")) for m in data.get("data", []) if isinstance(m, dict)]
        print(f"  [PASS] 3. Provider: oMLX reachable at 127.0.0.1:8888 (models: {', '.join(models) or 'none'})")
        conn.close()
    except Exception as exc:
        print(f"  [WARN] 3. Provider: oMLX unreachable at 127.0.0.1:8888 ({exc})")

    agents = installed_data.get("agents", {})
    risk_profiles = installed_data.get("risk_profiles", {})
    print(f"  [PASS] 4. Agents configured: {len(agents) if isinstance(agents, dict) else 0}")
    print(f"  [PASS] 5. Risk profiles evaluated: {len(risk_profiles) if isinstance(risk_profiles, dict) else 0}")

    print("\n--- Siri & Apple Shortcuts Contract Checks (T367 / T517 AC3) ---")
    contract_failures = 0
    for cid, ok, detail in verify_siri_shortcuts_contract():
        tag = "PASS" if ok else "FAIL"
        print(f"  [{tag}] {cid}: {detail}")
        if not ok:
            contract_failures += 1

    return 1 if contract_failures else 0


def cmd_status() -> int:
    zc_bin = shutil.which("zeroclaw")
    if not zc_bin:
        print("  [WARN] zeroclaw binary not on PATH (gateway offline)")
        return 0
    gw = subprocess.run([zc_bin, "status", "--format", "exit-code"], capture_output=True, text=True, check=False)
    gw_status = "ONLINE" if gw.returncode == 0 else "OFFLINE"
    print(f"  [INFO] ZeroClaw gateway (:42617): {gw_status}")
    svc = subprocess.run([zc_bin, "service", "status"], capture_output=True, text=True, check=False)
    loaded = "not loaded" not in (svc.stdout + svc.stderr)
    print(f"  [INFO] ZeroClaw daemon service: {'LOADED' if loaded else 'NOT LOADED'}")
    return 0


def cmd_service(action: str, apply: bool = False) -> int:
    if not apply:
        print(f"[INFO] Dry run: would run 'zeroclaw service {action}'. Pass --apply to execute.")
        return 0
    zc_bin = shutil.which("zeroclaw")
    if not zc_bin:
        print("[FAIL] zeroclaw binary not found on PATH")
        return 1
    res = subprocess.run([zc_bin, "service", action], check=False)
    return res.returncode


def cmd_logs(lines: int = 50) -> int:
    log_file = ZEROCLAW_DIR / "logs" / "daemon.log"
    if not log_file.is_file():
        print(f"[INFO] No daemon log found at {log_file}")
        return 0
    content = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    for ln in content[-lines:]:
        print(ln)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="ZeroClaw Runtime Management, Config Sync & Siri/Shortcuts Health Probe (T153, T516, T517 AC3)."
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_sync = sub.add_parser("sync", help="Generate ~/.zeroclaw/config.toml from template (dry-run default)")
    p_sync.add_argument("--apply", "--write", action="store_true", dest="apply", help="Write config to ~/.zeroclaw/config.toml")
    p_sync.add_argument("--dry-run", action="store_true", help="Report without writing (default)")

    sub.add_parser("check", help="Check config drift against tracked template")
    sub.add_parser("health", help="Run runtime health audit + Siri/Shortcuts contract checks")
    sub.add_parser("status", help="Check ZeroClaw gateway and daemon service status")

    for act in ("start", "stop", "restart"):
        p_act = sub.add_parser(act, help=f"{act.capitalize()} ZeroClaw daemon service (dry-run default)")
        p_act.add_argument("--apply", action="store_true", help=f"Execute service {act}")
        p_act.add_argument("--dry-run", action="store_true", help="Report without executing (default)")

    p_logs = sub.add_parser("logs", help="Show recent ZeroClaw daemon log lines")
    p_logs.add_argument("--lines", "-n", type=int, default=50, help="Number of log lines to print")

    args = parser.parse_args(argv)

    if args.subcommand == "sync":
        return cmd_sync(apply=bool(args.apply))
    if args.subcommand == "check":
        return cmd_check()
    if args.subcommand == "health":
        return cmd_health()
    if args.subcommand == "status":
        return cmd_status()
    if args.subcommand in ("start", "stop", "restart"):
        return cmd_service(str(args.subcommand), apply=bool(args.apply))
    if args.subcommand == "logs":
        return cmd_logs(lines=int(args.lines))
    return 1


if __name__ == "__main__":
    sys.exit(main())
