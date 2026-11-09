#!/usr/bin/env python3
"""T664 / T671 — Per-Client Tech Identity (<slug>@w0m.xyz), Infisical Org & RFC 6238 TOTP Helper.

Usage:
    python3 scripts/client_tech_identity.py --client pandatransfer
    python3 scripts/client_tech_identity.py --totp-seed-env CLOUDFLARE_TOTP_SEED
    python3 scripts/client_tech_identity.py --test
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import struct
import sys
import time
import unittest
from typing import Any

ESTATE_ROOT = Path(__file__).resolve().parents[1]
CLIENTS_POLICY_PATH = ESTATE_ROOT / "project" / "policies" / "clients-policy.json"

DEVOPS_HATS = {"devops", "sre", "infra", "infrastructure", "platform-engineer"}
PM_HATS = {"pm", "project.manager", "product.manager", "product-manager", "project-manager"}
TL_HATS = {"tl", "tech.lead", "tech-lead"}


def generate_totp(base32_seed: str, timestamp: int | None = None, step: int = 30, digits: int = 6) -> str:
    """Compute a 6-digit RFC 6238 TOTP code from a base32 Authenticator seed."""
    cleaned = "".join(ch for ch in base32_seed.strip().upper() if ch.isalnum())
    if not cleaned:
        raise ValueError("Empty TOTP seed")
    pad_len = (8 - (len(cleaned) % 8)) % 8
    secret = base64.b32decode(cleaned + ("=" * pad_len), casefold=True)
    now = int(time.time()) if timestamp is None else int(timestamp)
    counter = now // step
    msg = struct.pack(">Q", counter)
    digest = hmac.new(secret, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code_int % (10**digits)).zfill(digits)


def inspect_client_tech_identity(client_id: str, policy_path: Path = CLIENTS_POLICY_PATH) -> dict[str, Any]:
    """Inspect a declared client's <slug>@w0m.xyz tech mailbox, hat routing, and Infisical profile."""
    data = json.loads(policy_path.read_text(encoding="utf-8"))
    projects = data.get("projects", [])
    match = next((p for p in projects if p.get("id") == client_id), None)
    if not match:
        raise KeyError(f"Client '{client_id}' not found in {policy_path}")

    slug = (match.get("org_slug") or match.get("project_slug") or client_id).strip().lower()
    list_address = f"{slug}@w0m.xyz"
    identities_catalog = data.get("identities_catalog", {})
    role_assignments = match.get("role_assignments", {})

    devops_emails: list[str] = []
    pm_emails: list[str] = []
    tl_emails: list[str] = []

    for _operator, assignment in role_assignments.items():
        ident_key = assignment.get("identity_key", "")
        ident = identities_catalog.get(ident_key, {})
        email = (ident.get("git_user_email") or match.get("identity", {}).get("git_user_email") or "").strip().lower()
        if not email:
            continue
        hats = {str(h).strip().lower() for h in assignment.get("hats", [])}
        if hats & DEVOPS_HATS and email not in devops_emails:
            devops_emails.append(email)
        if hats & PM_HATS and email not in pm_emails:
            pm_emails.append(email)
        if hats & TL_HATS and email not in tl_emails:
            tl_emails.append(email)

    if devops_emails:
        primary_source = "devops"
        operator_recipients = devops_emails
    elif pm_emails:
        primary_source = "pm_fallback"
        operator_recipients = pm_emails
    elif tl_emails:
        primary_source = "tl_fallback"
        operator_recipients = tl_emails
    else:
        primary_source = "operator_default"
        fallback_email = (match.get("identity", {}).get("git_user_email") or "casualuser@gmail.com").strip().lower()
        operator_recipients = [fallback_email]

    ext_services = match.get("external_services", [])
    cf_resources: list[str] = []
    infisical_resources: list[str] = []
    for svc in ext_services:
        if svc.get("service_key") == "cloudflare":
            cf_resources.extend(svc.get("resources", []))
        elif svc.get("service_key") == "infisical":
            infisical_resources.extend(svc.get("resources", []))

    return {
        "client_id": client_id,
        "slug": slug,
        "list_address": list_address,
        "primary_source": primary_source,
        "operator_recipients": operator_recipients,
        "infisical_profile": f"{list_address}--{slug}",
        "cloudflare_resources": cf_resources,
        "infisical_resources": infisical_resources,
    }


class TestClientTechIdentity(unittest.TestCase):
    def test_totp_rfc6238_deterministic(self) -> None:
        # JBSWY3DPEHPK3PXP ('Hello!\xde\xad\xbe\xef') at t=0 produces a deterministic 6-digit code
        code = generate_totp("JBSWY3DPEHPK3PXP", timestamp=1700000000)
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())
        self.assertEqual(code, generate_totp("jbsw y3dp ehpk 3pxp", timestamp=1700000000))

    def test_pandatransfer_tech_identity(self) -> None:
        info = inspect_client_tech_identity("pandatransfer")
        self.assertEqual(info["list_address"], "pandatransfer@w0m.xyz")
        self.assertEqual(info["primary_source"], "devops")
        self.assertIn("casualuser@gmail.com", info["operator_recipients"])
        self.assertIn("email:pandatransfer@w0m.xyz->worker:wom7func", info["cloudflare_resources"])
        self.assertIn("profile:pandatransfer@w0m.xyz--pandatransfer", info["infisical_resources"])

    def test_solar_collapsed_pm_fallback(self) -> None:
        info = inspect_client_tech_identity("solar")
        self.assertEqual(info["list_address"], "aleksei-tcelishchev@w0m.xyz")
        self.assertEqual(info["primary_source"], "pm_fallback")
        self.assertIn("casualuser@gmail.com", info["operator_recipients"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", help="Inspect a declared client tech identity (e.g. pandatransfer)")
    parser.add_argument("--totp-seed", help="Base32 TOTP seed to generate a 6-digit code")
    parser.add_argument("--totp-seed-env", help="Environment variable holding Base32 TOTP seed")
    parser.add_argument("--test", action="store_true", help="Run offline unit tests")
    args = parser.parse_args()

    if args.test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestClientTechIdentity)
        ok = unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
        return 0 if ok else 1

    if args.totp_seed or args.totp_seed_env:
        seed = args.totp_seed or os.environ.get(args.totp_seed_env or "", "")
        if not seed:
            print("ERROR: TOTP seed is empty or environment variable is unset", file=sys.stderr)
            return 1
        print(generate_totp(seed))
        return 0

    client_id = args.client or "pandatransfer"
    info = inspect_client_tech_identity(client_id)
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
