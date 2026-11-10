#!/usr/bin/env python3
"""w0m 3-Tier Project Development Mode Controller (T704 AC4/AC5).

Manages the estate development mode (`ultra`, `balance`, `wise`) and integrates
Google's Elephant-Goldfish Model (`google/elephant-goldfish-model`) review depth
and `session-complete` / `agent-tree-land` gate selection:

- `ultra`:   Maximum speed (~25-45s wrap-up). Runs fast changed-surface gates
             only, deduplicates pre-push/estate certification, and offloads
             shared estate-wide graph/vector rebuilds to `just deploy`.
- `balance`: Default medium-careful mode (~60-90s wrap-up). Runs core drift,
             security, reality, and DoD gates + single-pass pre-land
             certification while offloading the 15-minute full-estate
             `kb_vector` + `graph_global` rebuild to `just deploy`.
- `wise`:    Full deep thinking + Google Elephant-Goldfish Model (`egm-*`)
             stateless fresh-subagent adversarial review loop + all 19
             verification gates + synchronous `refresh_canonical_graph_union()`.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SDLC_PATH = ROOT / ".w0m" / "sdlc.json"
LOCAL_STATE_PATH = ROOT / ".w0m" / "dev-mode.json"

VALID_MODES = ("ultra", "balance", "wise")
DEFAULT_MODE = "balance"

MODE_SPECS: dict[str, dict[str, Any]] = {
    "ultra": {
        "mode": "ultra",
        "label": "Ultra (Maximum Speed · Fast Worktree Land)",
        "target_wrapup_seconds": "25-45s",
        "thinking_depth": "fast_single_pass",
        "egm_workflow": [
            "egm-draft (fast inline context)",
        ],
        "session_complete_gates": [
            "lessons_check",
            "supabase_surface_drift_check",
            "ds-conformance",
            "ui-ticket-leak-check",
            "reports-ticket-check",
            "state-check",
        ],
        "run_graph_union_on_land": False,
        "deduplicate_prepush_certification": True,
        "deferred_to_deploy": [
            "refresh_canonical_graph_union (w0m_kb_vector + graph_global --auto-rebuild-stale)",
            "full-estate py-typecheck (1m27s)",
            "full-estate mmd-validate across all historical reports (24s)",
            "duplicate certify_estate_tree passes",
        ],
    },
    "balance": {
        "mode": "balance",
        "label": "Balance (Medium Careful · Default Balanced Speed & Checks)",
        "target_wrapup_seconds": "60-90s",
        "thinking_depth": "elephant_context_plus_targeted_goldfish_check",
        "egm_workflow": [
            "egm-draft",
            "egm-review (targeted changed-surface check)",
            "egm-resolve",
        ],
        "session_complete_gates": [
            "reality-verify",
            "spec-drift",
            "dod-check",
            "lessons_check",
            "supabase_surface_drift_check",
            "db-drift-check",
            "debt-check",
            "reports-ticket-check",
            "ds-conformance",
            "ui-ticket-leak-check",
            "commit-msg-check",
            "state-check",
        ],
        "run_graph_union_on_land": False,
        "deduplicate_prepush_certification": True,
        "deferred_to_deploy": [
            "refresh_canonical_graph_union (w0m_kb_vector + graph_global --auto-rebuild-stale)",
            "full-estate py-typecheck (1m27s)",
            "duplicate certify_estate_tree passes",
        ],
    },
    "wise": {
        "mode": "wise",
        "label": "Wise (Full Deep Thinking · EGM Elephant-Goldfish Loop + All 19 Gates)",
        "target_wrapup_seconds": "8-15m",
        "thinking_depth": "deep_egm_elephant_goldfish_adversarial_loop",
        "egm_workflow": [
            "egm-brainstorm",
            "egm-draft",
            "egm-review-loop (stateless Goldfish fresh-context reviewer)",
            "egm-resolve",
            "egm-drift-report",
        ],
        "session_complete_gates": ["all_19_gates"],
        "run_graph_union_on_land": True,
        "deduplicate_prepush_certification": True,
        "deferred_to_deploy": [],
    },
}


def resolve_active_mode(explicit_mode: str | None = None) -> tuple[str, str]:
    """Return `(mode, source)` where `mode` is in `VALID_MODES`."""
    if explicit_mode:
        norm = explicit_mode.strip().lower()
        if norm in VALID_MODES:
            return norm, "cli"
        raise ValueError(f"Invalid mode {explicit_mode!r}; expected one of {VALID_MODES}")

    env_mode = os.environ.get("W0M_DEV_MODE", "").strip().lower()
    if env_mode in VALID_MODES:
        return env_mode, "env:W0M_DEV_MODE"

    if LOCAL_STATE_PATH.exists():
        try:
            data = json.loads(LOCAL_STATE_PATH.read_text(encoding="utf-8"))
            file_mode = str(data.get("mode", "")).strip().lower()
            if file_mode in VALID_MODES:
                return file_mode, ".w0m/dev-mode.json"
        except Exception:
            pass

    if SDLC_PATH.exists():
        try:
            sdlc = json.loads(SDLC_PATH.read_text(encoding="utf-8"))
            cfg_mode = (
                str(sdlc.get("development_modes", {}).get("default_mode", ""))
                .strip()
                .lower()
            )
            if cfg_mode in VALID_MODES:
                return cfg_mode, ".w0m/sdlc.json"
        except Exception:
            pass

    return DEFAULT_MODE, "default"


def set_active_mode(mode: str) -> dict[str, Any]:
    norm = mode.strip().lower()
    if norm not in VALID_MODES:
        raise ValueError(f"Invalid mode {mode!r}; expected one of {VALID_MODES}")
    LOCAL_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mode": norm,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "spec": MODE_SPECS[norm],
    }
    LOCAL_STATE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def get_mode_status(explicit_mode: str | None = None) -> dict[str, Any]:
    mode, source = resolve_active_mode(explicit_mode)
    spec = MODE_SPECS[mode]
    return {
        "active_mode": mode,
        "source": source,
        "spec": spec,
        "available_modes": list(VALID_MODES),
    }


def run_self_test() -> int:
    for m in VALID_MODES:
        resolved, src = resolve_active_mode(m)
        assert resolved == m and src == "cli", f"Failed explicit resolve for {m}"
        assert MODE_SPECS[m]["mode"] == m
    assert MODE_SPECS["ultra"]["run_graph_union_on_land"] is False
    assert MODE_SPECS["balance"]["run_graph_union_on_land"] is False
    assert MODE_SPECS["wise"]["run_graph_union_on_land"] is True
    print("dev_mode.py self-test: PASS (ultra / balance / wise contracts verified)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage w0m project development mode (ultra | balance | wise)."
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        help="status | get | set | ultra | balance | wise",
    )
    parser.add_argument(
        "mode_arg",
        nargs="?",
        default=None,
        help="Target mode when action is 'set' (ultra | balance | wise)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    parser.add_argument("--self-test", action="store_true", help="Run self-test")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    action = args.action.strip().lower()
    if action in VALID_MODES:
        target = action
        action = "set"
    elif action == "set":
        if not args.mode_arg:
            print("ERROR: `set` requires a mode: ultra | balance | wise", file=sys.stderr)
            return 2
        target = args.mode_arg.strip().lower()
    else:
        target = None

    if action == "set" and target:
        set_active_mode(target)
        status = get_mode_status()
    elif action == "get":
        mode, _ = resolve_active_mode()
        if args.json:
            print(json.dumps({"mode": mode}))
        else:
            print(mode)
        return 0
    elif action == "status":
        status = get_mode_status()
    else:
        print(
            f"ERROR: unknown action {args.action!r} (use status | get | ultra | balance | wise)",
            file=sys.stderr,
        )
        return 2

    if args.json:
        print(json.dumps(status, indent=2))
        return 0

    spec = status["spec"]
    print(f"w0m Development Mode: {status['active_mode'].upper()} (source: {status['source']})")
    print(f"  Profile:            {spec['label']}")
    print(f"  Target Wrap-Up:     {spec['target_wrapup_seconds']}")
    print(f"  Thinking / Review:  {spec['thinking_depth']}")
    print(f"  EGM Workflow:       {', '.join(spec['egm_workflow'])}")
    print(f"  Wrap-Up Gates:      {', '.join(spec['session_complete_gates'])}")
    if spec["deferred_to_deploy"]:
        print(f"  Deferred to Deploy: {', '.join(spec['deferred_to_deploy'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
