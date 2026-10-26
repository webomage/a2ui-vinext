#!/usr/bin/env python3
"""Backfill the OPTIONAL `type` frontmatter field via System One typed decisions (`T434`).

Primary classifier (`T434` AC3/AC5/AC6/AC7/AC9):
- `infer_type()` calls `system_one.decide()` (`@cf/cloudflare/clef-flash`, `laya`, `kev`, `jev`,
  `omlx`, or `deterministic-fixture`) as the primary classifier.
- Zero silent fallback (`AgDR-0025`, `T242`, `T434` AC7/AC9): when `--require-provider` (or
  default System One mode) is invoked without a reachable provider, `type_backfill.py` reports
  `UNMEASURABLE` and NEVER silently guesses with regexes.
- Legacy `TYPE_RULES` regex heuristic is retained ONLY behind explicit `--offline-heuristic`
  for offline comparison and benchmark baselining (`system_one_bench.py`).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
WEB = ROOT / "w0m-web"
WEB_SCRIPTS = WEB / "project" / "scripts"
if str(WEB_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(WEB_SCRIPTS))
ESTATE_SCRIPTS = SCRIPT_DIR
if str(ESTATE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(ESTATE_SCRIPTS))

from system_one import (  # noqa: E402
    DecisionResult,
    DecisionUnavailableError,
    decide,
)
from tasks_query import resolve_tickets_dir  # noqa: E402 — canonical .tasks/ resolver (T411)

TICKETS = resolve_tickets_dir()
MIN_ACCURACY = 0.80  # below this, --apply refuses.
DEFAULT_MIN_CONFIDENCE = 0.30

TICKET_TYPE_OPTIONS: dict[str, str] = {
    "bug": (
        "Fixes an existing defect, broken runtime/gate/test behavior, security exposure "
        "(over-permissive RLS/grants, auth bypass, secret leak), drift, false positive, or regression."
    ),
    "feature": (
        "Introduces or builds a new capability, new CLI/recipe/script, new database table/migration, "
        "new UI component/endpoint, or new subsystem."
    ),
    "task": (
        "Performs an audit, investigation, measurement, documentation/AgDR record, "
        "retirement/decommission, or consolidation without adding a new product feature."
    ),
}

# ── Legacy regex rules (retained ONLY for explicit `--offline-heuristic` & benchmark baseline) ──
BUG = [
    r"\bis (?:DOWN|broken|dead|a silent no-?op|inert|wrong|stale)\b",
    r"\bsilently\b",
    r"\bno-?op\b",
    r"\bfails? (?:open|closed|silently)\b",
    r"\breports? success\b",
    r"\bnever (?:fires?|ran|runs|caught)\b",
    r"\bleaks?\b",
    r"\bworld-readable\b",
    r"\bcannot (?:read|reach|sign in|see)\b",
    r"\bhas no\b",
    r"\bdrift(?:ed|s)?\b",
    r"\bmismatch\b",
    r"\bregress",
    r"\bblocks? a commit\b",
    r"\bfalse positive\b",
    r"\bundeclared\b",
]
FEATURE = [
    r"^PARENT\b",
    r"\bunified\b",
    r"\benhancement\b",
    r"\badd (?:a|an|the)?\b",
    r"\bintroduce\b",
    r"\bsupport both\b",
    r"\bsupport\b",
    r"\bnothing (?:can|carries|covers)\b",
    r"\bno path\b",
    r"\bmodel\b",
    r"\bdefine and pilot\b",
    r"\bturn .* into\b",
]
TASK = [
    r"^(?:Gate|Retire|Research|Import|Audit|Migrate|Standardi[sz]e|Document|Split|Define|"
    r"Measure|Record|Register|Reconcile|Backfill|Rotate|Clean|Remove|Review|Finish|Pay down)\b",
    r"\bdeclares \d+ of \d+\b",
    r"\bconform",
    r"\bgovernance\b",
    r"\bpackaging format\b",
    r"\bwrite (?:it )?down\b",
    r"\bevaluate\b",
    r"\binventory\b",
]
RULES: dict[str, list[str]] = {"bug": BUG, "feature": FEATURE, "task": TASK}
TYPE_RULES = RULES


def frontmatter(text: str) -> tuple[str, str]:
    parts = text.split("---", 2)
    return (parts[1], parts[2]) if len(parts) >= 3 else ("", text)


def field(fm: str, key: str) -> str:
    m = re.search(rf"^{key}: *(.*)$", fm, re.M)
    return m.group(1).strip().strip('"').split("#")[0].strip() if m else ""


def classify_regex(title: str, body: str) -> tuple[str, int]:
    """Legacy regex heuristic `(type, score)`. Used only with `--offline-heuristic` or bench."""
    head = body[:900]
    scores = {t: 0 for t in TYPE_RULES}
    for t, pats in TYPE_RULES.items():
        for p in pats:
            if re.search(p, title, re.I):
                scores[t] += 3
            elif re.search(p, head, re.I):
                scores[t] += 1
    best = max(scores, key=lambda k: scores[k])
    top = scores[best]
    runner = max(v for k, v in scores.items() if k != best)
    return (best, top) if top >= 3 and top - runner >= 4 else ("", top)


# Preserve backwards-compatible symbol `classify` for callers/tests
classify = classify_regex


def infer_type(
    title: str,
    body: str = "",
    *,
    ticket_id: str = "",
    area: str = "",
    tags: str = "",
    provider: str | None = None,
    require_provider: bool = False,
    offline_heuristic: bool = False,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    timeout: float = 0.45,
    transport: Any = None,
) -> tuple[str, float, str]:
    """Infer ticket `type` using `system_one.decide()` as the primary classifier.

    When `offline_heuristic=True` (and `require_provider=False`), runs the legacy regex
    classifier explicitly. Otherwise invokes `system_one.decide()` and raises
    `DecisionUnavailableError("UNMEASURABLE: ...")` if the provider is unavailable.
    """
    if offline_heuristic and require_provider:
        raise ValueError("Cannot combine --require-provider with --offline-heuristic (AgDR-0025).")

    if offline_heuristic:
        got, score_val = classify_regex(title, body)
        return got, float(score_val), "offline-heuristic"

    res: DecisionResult = decide(
        "Classify this w0m software engineering ticket into its canonical `type` (`bug`, `feature`, or `task`) based on its title and summary.",
        TICKET_TYPE_OPTIONS,
        {
            "id": ticket_id,
            "title": title,
            "area": area,
            "tags": tags,
            "summary": body[:900],
        },
        mode="choice",
        provider=provider,
        timeout=timeout,
        transport=transport,
        fixture_key=ticket_id or title,
    )
    source = f"system_one:{res.provider}:{res.model}"
    if res.confidence < min_confidence:
        return "", float(res.confidence), source
    return str(res.value), float(res.confidence), source


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate and backfill ticket `type` field (T434)")
    ap.add_argument("--apply", action="store_true", help="Write high-confidence proposals to .tasks/")
    ap.add_argument(
        "--provider",
        default=None,
        help="System One provider id (clef-flash, clef, jev, kev, laya, omlx, von, deterministic-fixture)",
    )
    ap.add_argument(
        "--require-provider",
        action="store_true",
        help="Hook/strict posture: report UNMEASURABLE when provider is unreachable; never fall back to regexes",
    )
    ap.add_argument(
        "--offline-heuristic",
        action="store_true",
        help="Explicitly run the legacy TYPE_RULES regex heuristic for offline comparison",
    )
    ap.add_argument(
        "--tickets-dir",
        type=Path,
        default=None,
        help="Override .tasks/ directory path (for tests)",
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=0.45,
        help="Per-decision timeout in seconds (default 0.45s <= 500ms hook budget)",
    )
    args = ap.parse_args(argv)

    if args.require_provider and args.offline_heuristic:
        print(
            "ERROR: --require-provider and --offline-heuristic are mutually exclusive (AgDR-0025).",
            file=sys.stderr,
        )
        return 2

    tickets_dir = args.tickets_dir or TICKETS
    Rec = tuple[Path, str, str, str, str, str]
    labelled: list[Rec] = []
    blank: list[Rec] = []
    for f in sorted(tickets_dir.glob("T*.md")):
        text = f.read_text(encoding="utf-8")
        fm, body = frontmatter(text)
        rec = (
            f,
            field(fm, "title"),
            body,
            field(fm, "type"),
            field(fm, "area"),
            field(fm, "tags"),
        )
        (labelled if rec[3] else blank).append(rec)

    # ── 1. Validate against human-typed tickets ───────────────────────────────────────────
    hit = miss = abstain = 0
    wrong: list[str] = []
    model_banner = "offline-heuristic (TYPE_RULES)"
    try:
        for f, title, body, truth, area, tags in labelled:
            if truth not in TICKET_TYPE_OPTIONS and args.offline_heuristic:
                continue
            got, _conf, source = infer_type(
                title,
                body,
                ticket_id=f.stem,
                area=area,
                tags=tags,
                provider=args.provider,
                require_provider=args.require_provider,
                offline_heuristic=args.offline_heuristic,
                timeout=args.timeout,
            )
            model_banner = source
            if not got:
                abstain += 1
            elif got == truth:
                hit += 1
            else:
                miss += 1
                wrong.append(f"{f.stem}: human={truth} classifier={got}")
    except DecisionUnavailableError as exc:
        print(f"type-backfill: {exc}")
        return 0 if args.require_provider else 2

    decided = hit + miss
    acc = hit / decided if decided else 0.0

    print(f"\ntype backfill ({model_banner}) -- validating against human-typed tickets\n")
    print(f"  {len(labelled)} human-typed  ->  {hit} agree · {miss} disagree · {abstain} abstained")
    print(f"  accuracy on decided cases: {acc:.0%}  (floor for --apply: {MIN_ACCURACY:.0%})")
    for w in wrong[:6]:
        print(f"     x {w}")

    # ── 2. Propose for blank tickets ──────────────────────────────────────────────────────
    props: list[tuple[Path, str, float, str]] = []
    try:
        for f, title, body, _, area, tags in blank:
            got, score_val, _src = infer_type(
                title,
                body,
                ticket_id=f.stem,
                area=area,
                tags=tags,
                provider=args.provider,
                require_provider=args.require_provider,
                offline_heuristic=args.offline_heuristic,
                timeout=args.timeout,
            )
            if got:
                props.append((f, got, score_val, title))
    except DecisionUnavailableError as exc:
        print(f"type-backfill: {exc}")
        return 0 if args.require_provider else 2

    print(f"\n  {len(blank)} blank  ->  {len(props)} confident · {len(blank) - len(props)} left blank")
    by = {t: sum(1 for p in props if p[1] == t) for t in TICKET_TYPE_OPTIONS}
    print(f"  proposed: {by}")
    for f, got, score_val, title in props[:8]:
        fmt_score = f"{score_val:.2f}" if not args.offline_heuristic else f"{int(score_val)}"
        print(f"     {f.stem:6} -> {got:8} ({fmt_score}) {title[:56]}")
    if len(props) > 8:
        print(f"     ... and {len(props) - 8} more")

    if not args.apply:
        print("\n  report only -- pass --apply to write. Nothing changed.")
        return 0

    if acc < MIN_ACCURACY:
        print(
            f"\n  [REFUSED] {acc:.0%} < {MIN_ACCURACY:.0%}. A classifier that cannot reproduce the "
            f"labels a human chose\n            does not get to invent {len(blank)} of them. Nothing written."
        )
        return 1

    for f, got, _score, _t in props:
        text = f.read_text(encoding="utf-8")
        if re.search(r"^type: *$", text, re.M):
            text = re.sub(r"^type: *$", f"type: {got}", text, count=1, flags=re.M)
        else:
            text = re.sub(r"^(tags:)", f"type: {got}\n\\1", text, count=1, flags=re.M)
        f.write_text(text, encoding="utf-8")
    print(f"\n  applied to {len(props)} ticket(s). {len(blank) - len(props)} deliberately left blank.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
