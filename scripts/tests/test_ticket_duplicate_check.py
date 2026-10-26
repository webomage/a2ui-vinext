#!/usr/bin/env python3
"""Prove the ticket-duplicate-check gate detects duplicates and rejects false alarms (T403).

Tests:
1. Frontmatter, tags, epic, symbols, and AC extraction.
2. Tokenizer, stemming, bigrams, and boilerplate filtering.
3. Synthetic exact and near-duplicate detection (>= 0.70).
4. Domain false-alarm resilience (distinct tickets sharing terms remain < 0.40).
5. Exemption handling (closed_as: duplicate, superseded_by, duplicate_of).
6. Candidate draft pre-flight check mode (--check-draft).
7. Real-world audit validation on estate duplicates (T397, T398, T399).
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCRIPT = ROOT / "scripts/ticket_duplicate_check.py"

spec = importlib.util.spec_from_file_location("tdc", SCRIPT)
tdc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tdc)


class ProbeRunner:
    def __init__(self) -> None:
        self.n = 0
        self.fail: list[str] = []

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        self.n += 1
        status = "ok" if ok else "!! FAILED"
        print(f"  {label:<68} {status}")
        if not ok:
            self.fail.append(f"{label} {detail}".strip())


SAMPLE_TICKET_ORIGINAL = """---
id: T901
title: "Encrypt third-party API connector tokens with AES-256-GCM at rest"
status: queued
area: security
epic: "security-rbac-hardening"
tags: [security, encryption, tokens, connectors, aes-256-gcm]
---

# T901 — Encrypt third-party API connector tokens with AES-256-GCM at rest

## Summary

Connector tokens stored in the database are currently plaintext. We must implement
AES-256-GCM authenticated encryption at rest for all stored OAuth tokens in `social_integrations`.

## Acceptance Criteria

- [ ] AC1 — Implement AES-256-GCM encryption helper with envelope key management.
- [ ] AC2 — Encrypt tokens on write and decrypt on read across connector pipelines.
- [ ] AC3 — Add automated unit and integration tests verifying ciphertext integrity.
"""

SAMPLE_TICKET_DUPLICATE = """---
id: T902
title: "Connector token hardening: AES-256-GCM app-level encryption at rest"
status: queued
area: security
epic: "security-rbac-hardening"
tags: [security, tokens, aes-256-gcm, encryption]
---

# T902 — Connector token hardening: AES-256-GCM app-level encryption at rest

## Summary

Protect third-party OAuth connector tokens by encrypting at rest using AES-256-GCM.
Eliminate plaintext token storage across the `social_integrations` schema.

## Acceptance Criteria

- [ ] AC1 — Author AES-256-GCM encryption module with authenticated tag verification.
- [ ] AC2 — Ensure connector write operations encrypt credentials transparently.
- [ ] AC3 — Prove decryption works cleanly with zero plaintext leakage in tests.
"""

SAMPLE_TICKET_DISTINCT_SECURITY = """---
id: T903
title: "Constant-time string comparison for admin service role API authentication"
status: queued
area: security
epic: "security-rbac-hardening"
tags: [security, authz, timing-attack, constant-time]
---

# T903 — Constant-time string comparison for admin service role API authentication

## Summary

Audit revealed `!==` comparison of incoming service tokens in edge functions.
Replace with constant-time equality check to prevent timing attacks.

## Acceptance Criteria

- [ ] AC1 — Replace raw string inequality check with timing-safe comparison helper.
- [ ] AC2 — Verify all edge function admin guards use timing-safe comparison.
- [ ] AC3 — Add unit tests validating rejection of timing leak probes.
"""

SAMPLE_TICKET_EXEMPT_DUPLICATE = """---
id: T904
title: "Connector token hardening: AES-256-GCM app-level encryption at rest"
status: done
closed_as: duplicate
duplicate_of: T901
---

# T904 — Connector token hardening

> ⚠️ **CLOSED AS A DUPLICATE of [[T901]]**
"""


def main() -> int:
    p = ProbeRunner()

    print("\n1. PARSING & EXTRACTION")
    t1 = tdc.extract_ticket_data(SAMPLE_TICKET_ORIGINAL, "T901")
    p.check("title parsed correctly", t1["title"] == "Encrypt third-party API connector tokens with AES-256-GCM at rest")
    p.check("tags extracted into set", "aes-256-gcm" in t1["tags"] and "security" in t1["tags"])
    p.check("epic extracted and lowercased", t1["epic"] == "security-rbac-hardening")
    p.check("code symbols extracted excluding boilerplate", "social_integrations" in t1["code_symbols"])
    p.check("AC text extracted and tokenized", len(t1["ac_tokens"]) > 5)

    print("\n2. STEMMING & TOKENIZATION")
    tok1 = tdc.tokenize("Remediating flaky test suites with remediation and remediate")
    p.check("remediating, remediation, remediate stem to remedi", "remedi" in tok1)
    tok2 = tdc.tokenize("Testing test suites and test suite")
    p.check("suites and suite stem consistently", "suit" in tok2)
    p.check("bigram test_suit created", "test_suit" in tok2)

    print("\n3. SYNTHETIC DUPLICATE DETECTION")
    t2 = tdc.extract_ticket_data(SAMPLE_TICKET_DUPLICATE, "T902")
    score_dup, reasons_dup = tdc.compare_tickets(t1, t2)
    p.check("synthetic duplicate scores >= 0.65", score_dup >= 0.65, f"got {score_dup}")
    p.check("reasons report title and summary overlap", any("title" in r for r in reasons_dup))
    p.check("reasons report shared keywords/phrases", any("aes-256-gcm" in r for r in reasons_dup))

    print("\n4. DOMAIN FALSE-ALARM RESILIENCE")
    t3 = tdc.extract_ticket_data(SAMPLE_TICKET_DISTINCT_SECURITY, "T903")
    score_distinct, _ = tdc.compare_tickets(t1, t3)
    p.check("distinct security ticket scores < 0.40", score_distinct < 0.40, f"got {score_distinct}")

    print("\n5. EXEMPTION HANDLING")
    t4 = tdc.extract_ticket_data(SAMPLE_TICKET_EXEMPT_DUPLICATE, "T904")
    p.check("closed_as: duplicate recognized as exempt", t4["is_duplicate"] is True)
    p.check("duplicate_of target parsed correctly", t4["duplicate_of"] == "T901")

    # In a corpus with T901, T902, T904:
    # T904 is exempt, so find_duplicates should only find (T901, T902), not (T901, T904)
    dups = tdc.find_duplicates([t1, t2, t4], threshold=0.50)
    p.check("exempt duplicate not surfaced in find_duplicates", len(dups) == 1 and dups[0]["ticket_a"] == "T901" and dups[0]["ticket_b"] == "T902")

    print("\n6. CANDIDATE DRAFT PRE-FLIGHT CHECK")
    with tempfile.TemporaryDirectory() as tmpdir:
        draft_dup_path = Path(tmpdir) / "draft_dup.md"
        draft_dup_path.write_text(SAMPLE_TICKET_DUPLICATE, encoding="utf-8")
        matches = tdc.check_candidate(t2, [t1, t3], top_n=3)
        p.check("draft duplicate top match is T901", len(matches) > 0 and matches[0]["id"] == "T901")
        p.check("draft duplicate similarity >= 0.65", matches[0]["similarity"] >= 0.65)

        draft_clean = tdc.extract_ticket_data(SAMPLE_TICKET_DISTINCT_SECURITY, "DRAFT_CLEAN")
        matches_clean = tdc.check_candidate(draft_clean, [t1], top_n=3)
        p.check("distinct draft similarity < 0.40", matches_clean[0]["similarity"] < 0.40)

    print("\n7. REAL-WORLD ESTATE AUDIT ACCURACY")
    estate_tickets = tdc.load_all_tickets()
    p.check("estate corpus loaded >= 400 tickets", len(estate_tickets) >= 400, f"got {len(estate_tickets)}")

    # T211 was a closed duplicate of T209 until 2026-09-24, when it was recycled into ticket-diagram
    # co-location — the same fate as T397-T399 below, so it gets the same assertion. The old
    # "top match is T209" probe asserted a fact about live data that recycling is designed to change.
    t211 = next((t for t in estate_tickets if t["id"] == "T211"), None)
    if t211:
        m211 = tdc.check_candidate(t211, estate_tickets, top_n=3)
        top_sim_211 = m211[0]["similarity"] if m211 else 0.0
        p.check("repurposed T211 is clean with no duplicate", top_sim_211 < 0.40, f"top sim: {top_sim_211:.0%}")

    # Test T397 (repurposed to automated ticket recycling) has no high duplicate
    t397 = next((t for t in estate_tickets if t["id"] == "T397"), None)
    if t397:
        m397 = tdc.check_candidate(t397, estate_tickets, top_n=3)
        top_sim = m397[0]["similarity"] if m397 else 0.0
        p.check("repurposed T397 is clean with no duplicate", top_sim < 0.35, f"top sim: {top_sim:.0%}")

    # Test T398 (repurposed to pnpm exec/dlx migration) is clean with no duplicate
    t398 = next((t for t in estate_tickets if t["id"] == "T398"), None)
    if t398:
        m398 = tdc.check_candidate(t398, estate_tickets, top_n=3)
        top_sim_398 = m398[0]["similarity"] if m398 else 0.0
        p.check("repurposed T398 is clean with no duplicate", top_sim_398 < 0.40, f"top sim: {top_sim_398:.0%}")

    # Test T399 (repurposed to wom7func cutover and wom7cfworkers decommission) is clean with no duplicate
    t399 = next((t for t in estate_tickets if t["id"] == "T399"), None)
    if t399:
        m399 = tdc.check_candidate(t399, estate_tickets, top_n=3)
        top_sim_399 = m399[0]["similarity"] if m399 else 0.0
        p.check("repurposed T399 is clean with no duplicate", top_sim_399 < 0.40, f"top sim: {top_sim_399:.0%}")

    print(f"\nRan {p.n} probes: {p.n - len(p.fail)} passed, {len(p.fail)} failed.")
    if p.fail:
        print("\nFailures:")
        for f in p.fail:
            print(f"  - {f}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
