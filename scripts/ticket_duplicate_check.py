#!/usr/bin/env python3
"""ticket_duplicate_check.py — automated continuous ticket duplicate detection (T403).

Computes weighted lexical, token, and n-gram similarity across ticket titles,
summaries, and acceptance criteria to detect duplicate tasks and scope overlap
before or after entering the queue.

Usage:
    python3 scripts/ticket_duplicate_check.py                   # audit active corpus
    python3 scripts/ticket_duplicate_check.py --enforce         # exit 1 if duplicates found
    python3 scripts/ticket_duplicate_check.py --check-ticket T397  # check specific ticket
    python3 scripts/ticket_duplicate_check.py --check-draft draft.md # pre-flight check
    python3 scripts/ticket_duplicate_check.py --json            # JSON output
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TICKETS_DIR = ROOT / ".tasks"

# Common English + w0m boilerplate stopwords
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's",
    "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves",
    # Ticket & SDLC boilerplate words
    "ac1", "ac2", "ac3", "ac4", "ac5", "ac6", "ac7", "ac8",
    "acceptance", "criteria", "verify", "verification", "implement", "update",
    "author", "ensure", "check", "cleanly", "organically", "passes", "pass",
    "per", "spec", "standard", "filed", "directive", "owner", "summary",
    "ticket", "tickets", "wom7web", "wom7api", "w0m", "task", "work", "delivers",
}

# Technical distinct phrases that strongly signal identity when co-occurring
TECHNICAL_KEY_PHRASES = [
    "aes-256-gcm", "withservicerole", "client-profile-check", "client-inventory-test",
    "status-dashboard", "push_report", "sync_manifest_versions", "ticket_id_align_check",
    "dead-code", "admin-guard", "upwork-poller", "cloud-proxy", "headroom",
    "openrouter", "wom7func", "wom7cfworkers", "code-review-graph", "crg-serve",
    "social_integrations", "ports-policy", "ticket_duplicate_check",
]


# Boilerplate symbols present in nearly all tickets (ignored for similarity)
BOILERPLATE_SYMBOLS = {
    "openspec", "spec-authoring-standard.md", "just test", "just debt-check",
    "just db-migrate", "just tasks", "status.md", "tasks.md", "agents.md",
    "claude.md", "readme.md", "gate-integrity", "t1", "t2", "t3",
}


def stem(word: str) -> str:
    """Lightweight rule-based stemmer for English suffixes."""
    w = word.lower()
    for sfx in ("ations", "ation", "tions", "tion", "ments", "ment", "nesses", "ness", "ities", "ity", "ies"):
        if len(w) > len(sfx) + 2 and w.endswith(sfx):
            w = w[:-len(sfx)]
            break
    for sfx in ("ing", "ed", "able", "ible", "ate", "ize", "ise", "es", "s"):
        if len(w) > len(sfx) + 2 and w.endswith(sfx):
            w = w[:-len(sfx)]
            break
    if w.endswith("e") and len(w) > 3:
        w = w[:-1]
    return w


def tokenize(text: str) -> set[str]:
    """Tokenize text into stemmed words and bigrams, filtering stopwords."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    filtered = [stem(w) for w in words if len(w) > 2 and w not in STOPWORDS and stem(w) not in STOPWORDS]
    tokens = set(filtered)
    # Add bigrams for context-sensitive phrase matching
    for i in range(len(filtered) - 1):
        tokens.add(f"{filtered[i]}_{filtered[i+1]}")
    return tokens


def sim_field(set_a: set[str], set_b: set[str], cont_weight: float = 0.65) -> tuple[float, float, float]:
    """Calculate combined similarity using Dice coefficient and Containment index."""
    if not set_a or not set_b:
        return 0.0, 0.0, 0.0
    inter = set_a & set_b
    dice = 2 * len(inter) / (len(set_a) + len(set_b))
    cont = len(inter) / min(len(set_a), len(set_b))
    # Combined score takes the maximum of Dice and weighted containment
    combined = max(dice, cont_weight * cont)
    return combined, dice, cont


def extract_ticket_data(text: str, stem_id: str = "") -> dict[str, Any]:
    """Extract frontmatter, tags, epic, and key sections from raw markdown."""
    frontmatter: dict[str, Any] = {}
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            for line in fm_text.splitlines():
                if ":" in line and not line.strip().startswith("#"):
                    k, _, v = line.partition(":")
                    k = k.strip()
                    v = v.split("#", 1)[0].strip().strip('"\'')
                    if v.startswith("[") and v.endswith("]"):
                        items = [x.strip().strip('"\'') for x in v[1:-1].split(",") if x.strip()]
                        frontmatter[k] = items
                    else:
                        frontmatter[k] = v

    title = frontmatter.get("title", "")
    if isinstance(title, list):
        title = " ".join(title)
    if not title:
        m_t = re.search(r"^#\s+T\d+\s+[—\-]\s+(.*)$", text, re.M)
        if m_t:
            title = m_t.group(1).strip()

    # Extract Summary
    summary = ""
    m_sum = re.search(r"## Summary\s*\n\s*(.*?)(?=\n## |\Z)", text, re.DOTALL)
    if m_sum:
        summary = m_sum.group(1).strip()

    # Extract Acceptance Criteria lines
    acs = re.findall(r"^- \[.\] (.*)$", text, re.M)
    ac_text = " ".join(acs)

    # Extract tags & epic
    tags = frontmatter.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    epic = str(frontmatter.get("epic", "")).lower()

    # Extract backticked code symbols and kebab/snake identifiers
    raw_symbols = set(re.findall(r"`([a-zA-Z0-9_\-\.\:\/]+)`", text))
    clean_symbols = {
        s.lower() for s in raw_symbols
        if len(s) > 3
        and not any(bp in s.lower() for bp in BOILERPLATE_SYMBOLS)
        and not re.match(r"^t\d+$", s, re.I)
    }

    tag_tokens = {stem(t) for t in tags if t}
    if epic and epic not in BOILERPLATE_SYMBOLS:
        tag_tokens.add(stem(epic))

    # Check for duplicate exemption
    is_duplicate = (
        frontmatter.get("closed_as") == "duplicate"
        or "CLOSED AS A DUPLICATE" in text
        or "superseded_by:" in text
    )
    dup_target = ""
    m_dup = re.search(r"CLOSED AS A DUPLICATE of \[\[(T\d+)\]\]|duplicate_of:\s*(T\d+)|^superseded_by:\s*\[?\[?(T\d+)", text, re.I | re.M)
    if m_dup:
        dup_target = m_dup.group(1) or m_dup.group(2) or m_dup.group(3)

    return {
        "id": stem_id or str(frontmatter.get("id", "UNKNOWN")),
        "title": title,
        "status": str(frontmatter.get("status", "queued")),
        "closed_as": str(frontmatter.get("closed_as", "")),
        "is_duplicate": is_duplicate,
        "duplicate_of": dup_target,
        "epic": epic,
        "tags": set(tags),
        "tag_tokens": tag_tokens,
        "code_symbols": clean_symbols,
        "title_tokens": tokenize(title),
        "summary_tokens": tokenize(summary),
        "ac_tokens": tokenize(ac_text),
        "raw_text": text.lower(),
    }


def compare_tickets(t1: dict[str, Any], t2: dict[str, Any]) -> tuple[float, list[str]]:
    """Compute calibrated similarity score between two tickets (0.0 to 1.0)."""
    # Use balanced dice + containment for title
    _, t_dice, t_cont = sim_field(t1["title_tokens"], t2["title_tokens"])
    title_sim = (0.4 * t_dice) + (0.6 * t_cont) if (t_cont >= 0.40 and len(t1["title_tokens"] & t2["title_tokens"]) >= 2) else t_dice

    _, s_dice, s_cont = sim_field(t1["summary_tokens"], t2["summary_tokens"])
    summary_sim = (0.5 * s_dice) + (0.5 * s_cont) if s_cont >= 0.35 else s_dice

    _, a_dice, a_cont = sim_field(t1["ac_tokens"], t2["ac_tokens"])
    ac_sim = (0.5 * a_dice) + (0.5 * a_cont) if a_cont >= 0.35 else a_dice

    # Tags and epic overlap
    tag_inter = t1["tag_tokens"] & t2["tag_tokens"]
    tag_sim = len(tag_inter) / max(1, min(len(t1["tag_tokens"]), len(t2["tag_tokens"]))) if (t1["tag_tokens"] and t2["tag_tokens"]) else 0.0

    # Code symbols overlap
    code_inter = t1["code_symbols"] & t2["code_symbols"]
    code_sim = len(code_inter) / max(1, min(len(t1["code_symbols"]), len(t2["code_symbols"]))) if (t1["code_symbols"] and t2["code_symbols"]) else 0.0

    # Base weighted score: Title 40%, Summary 25%, AC 15%, Tags/Epic 10%, Code 10%
    base_score = (
        (0.40 * title_sim)
        + (0.25 * summary_sim)
        + (0.15 * ac_sim)
        + (0.10 * tag_sim)
        + (0.10 * code_sim)
    )

    # Shared technical phrases bonus
    shared_phrases = []
    for kp in TECHNICAL_KEY_PHRASES:
        if kp in t1["raw_text"] and kp in t2["raw_text"]:
            shared_phrases.append(kp)

    if shared_phrases:
        # Technical term alignment strongly boosts confidence
        base_score = min(1.0, base_score + (0.10 * len(shared_phrases)))

    reasons = []
    if title_sim > 0.30:
        reasons.append(f"title overlap ({title_sim:.0%}, cont={t_cont:.0%})")
    if summary_sim > 0.20:
        reasons.append(f"summary overlap ({summary_sim:.0%})")
    if ac_sim > 0.15:
        reasons.append(f"AC overlap ({ac_sim:.0%})")
    if tag_inter:
        reasons.append(f"shared tags/epic: {', '.join(sorted(tag_inter)[:3])}")
    if code_inter:
        reasons.append(f"shared symbols: {', '.join(sorted(code_inter)[:3])}")
    if shared_phrases:
        reasons.append(f"shared keywords: {', '.join(shared_phrases[:3])}")

    return round(base_score, 3), reasons


def load_all_tickets(tickets_dir: Path = TICKETS_DIR) -> list[dict[str, Any]]:
    """Load all T*.md tickets from directory."""
    tickets = []
    for f in sorted(tickets_dir.glob("T*.md"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0)):
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
            t_data = extract_ticket_data(txt, f.stem)
            tickets.append(t_data)
        except OSError:
            continue
    return tickets


def find_duplicates(
    tickets: list[dict[str, Any]],
    threshold: float = 0.30,
    include_closed: bool = False,
) -> list[dict[str, Any]]:
    """Scan all ticket pairs for duplicate or overlapping scopes."""
    results = []
    seen_pairs = set()

    for i, t1 in enumerate(tickets):
        if t1["is_duplicate"]:
            continue
        if not include_closed and t1["status"] in ("done", "paused"):
            continue

        for j in range(i + 1, len(tickets)):
            t2 = tickets[j]
            if t2["is_duplicate"]:
                continue
            if not include_closed and t1["status"] == "done" and t2["status"] == "done":
                continue

            pair_key = (t1["id"], t2["id"])
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            score, reasons = compare_tickets(t1, t2)
            if score >= threshold:
                results.append({
                    "ticket_a": t1["id"],
                    "status_a": t1["status"],
                    "title_a": t1["title"],
                    "ticket_b": t2["id"],
                    "status_b": t2["status"],
                    "title_b": t2["title"],
                    "similarity": score,
                    "reasons": reasons,
                })

    return sorted(results, key=lambda x: x["similarity"], reverse=True)


def check_candidate(
    candidate: dict[str, Any],
    tickets: list[dict[str, Any]],
    top_n: int = 5,
    threshold: float = 0.30,
) -> list[dict[str, Any]]:
    """Check a single candidate ticket against all existing tickets."""
    matches = []
    for t in tickets:
        if t["id"] == candidate["id"]:
            continue
        score, reasons = compare_tickets(candidate, t)
        matches.append({
            "id": t["id"],
            "title": t["title"],
            "status": t["status"],
            "is_duplicate": t["is_duplicate"],
            "duplicate_of": t["duplicate_of"],
            "similarity": score,
            "reasons": reasons,
        })
    matches.sort(key=lambda x: x["similarity"], reverse=True)
    return matches[:top_n]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--threshold", type=float, default=0.30, help="similarity threshold (default 0.30 for overlap, 0.45 for dup)")
    parser.add_argument("--enforce", action="store_true", help="exit 1 if high-confidence duplicate (>= 0.45) found in active queue")
    parser.add_argument("--all", action="store_true", help="include closed and historical tickets in pair check")
    parser.add_argument("--check-ticket", help="check a specific ticket ID (e.g. T397)")
    parser.add_argument("--check-draft", help="pre-flight check a candidate draft markdown file")
    parser.add_argument("--json", action="store_true", help="output JSON format")
    args = parser.parse_args()

    tickets = load_all_tickets()
    if not tickets:
        print("[FAIL] no tickets found in directory", file=sys.stderr)
        return 2

    # Mode 1: Candidate draft pre-flight check
    if args.check_draft:
        p = Path(args.check_draft)
        if not p.exists():
            print(f"[FAIL] draft file {args.check_draft} not found", file=sys.stderr)
            return 2
        draft_data = extract_ticket_data(p.read_text(encoding="utf-8", errors="replace"), stem_id="DRAFT")
        top_matches = check_candidate(draft_data, tickets, top_n=5, threshold=args.threshold)
        high_dups = [m for m in top_matches if m["similarity"] >= 0.40]

        if args.json:
            print(json.dumps({"draft": args.check_draft, "matches": top_matches, "is_duplicate": bool(high_dups)}, indent=2))
            return 1 if high_dups else 0
        else:
            print(f"▶ Pre-flight duplicate check for draft: {draft_data['title'] or args.check_draft}")
            if high_dups:
                print("  ❌ SUSPECTED DUPLICATE DETECTED:")
                for m in high_dups:
                    print(f"     · {m['id']} [{m['status']}] ({m['similarity']:.0%}) — {m['title']}")
                    if m["reasons"]:
                        print(f"       Details: {', '.join(m['reasons'])}")
                print("\n  Action required: Fold work into the existing ticket or mark closed_as: duplicate.")
                return 1
            else:
                top_sim = top_matches[0]['similarity'] if top_matches else 0.0
                top_id = top_matches[0]['id'] if top_matches else 'none'
                print(f"  ✅ Clean — no duplicate found (highest match: {top_id} at {top_sim:.0%})")
            return 0

    # Mode 2: Specific ticket check
    if args.check_ticket:
        target_id = args.check_ticket.upper()
        found = [t for t in tickets if t["id"] == target_id]
        if not found:
            print(f"[FAIL] ticket {target_id} not found", file=sys.stderr)
            return 2
        matches = check_candidate(found[0], tickets, top_n=5, threshold=args.threshold)
        if args.json:
            print(json.dumps({"ticket": target_id, "matches": matches}, indent=2))
        else:
            print(f"▶ Duplication analysis for {target_id}: {found[0]['title']}")
            for m in matches:
                flag = "🔴" if m["similarity"] >= 0.40 else "⚪"
                dup_note = f" (closed as duplicate of {m['duplicate_of']})" if m["is_duplicate"] else ""
                print(f"  {flag} {m['id']} [{m['status']}{dup_note}] similarity: {m['similarity']:.0%} — {m['title']}")
                if m["reasons"]:
                    print(f"     ({', '.join(m['reasons'])})")
        return 0

    # Mode 3: Corpus-wide scan
    duplicates = find_duplicates(tickets, threshold=args.threshold, include_closed=args.all)

    if args.json:
        print(json.dumps({"total_tickets": len(tickets), "duplicates_found": len(duplicates), "results": duplicates}, indent=2))
        high_unexempt = [d for d in duplicates if d["similarity"] >= 0.45]
        return 1 if (args.enforce and high_unexempt) else 0

    print(f"▶ ticket-duplicate-check — scanned {len(tickets)} tickets (reporting threshold: {args.threshold:.0%})")
    high_unexempt = [d for d in duplicates if d["similarity"] >= 0.45]
    if not duplicates:
        print("✅ No unhandled duplicate tickets detected in active queue.")
        return 0

    print(f"⚠️  {len(duplicates)} duplicate/overlapping pair(s) detected:")
    for d in duplicates:
        is_high = d["similarity"] >= 0.45
        icon = "🔴 DUPLICATE" if is_high else "🟡 OVERLAP"
        print(f"  [{icon}] {d['ticket_a']} ({d['status_a']}) ↔ {d['ticket_b']} ({d['status_b']}) — {d['similarity']:.0%}")
        print(f"      {d['ticket_a']}: {d['title_a'][:65]}")
        print(f"      {d['ticket_b']}: {d['title_b'][:65]}")
        if d["reasons"]:
            print(f"      Details: {', '.join(d['reasons'])}")

    if args.enforce and high_unexempt:
        print(f"\n[FAIL] {len(high_unexempt)} high-confidence duplicate ticket(s) found in active queue.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
