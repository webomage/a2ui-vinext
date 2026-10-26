#!/usr/bin/env python3
"""Regression test suite for Client Beta Epic (ROADMAP.md §34): T279, T280, T351, T364."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
ESTATE_ROOT = HERE.parents[2]
WEB_ROOT = ESTATE_ROOT / "w0m-web"
API_ROOT = ESTATE_ROOT / "w0m-api"


class TestClientBetaEpic(unittest.TestCase):
    def test_t364_latam_kyc_and_entitlements(self) -> None:
        kyc_src = WEB_ROOT / "packages/kyc/src"
        for rel in (
            "central-america/costa-rica.ts",
            "central-america/panama.ts",
            "south-america/brazil.ts",
            "south-america/colombia.ts",
            "south-america/argentina.ts",
            "south-america/chile.ts",
            "south-america/peru.ts",
            "latam-registry.ts",
        ):
            self.assertTrue((kyc_src / rel).is_file(), f"Missing KYC module: {rel}")

        entitlements_ts = WEB_ROOT / "packages/lib/src/entitlements/index.ts"
        self.assertTrue(entitlements_ts.is_file())
        ent_text = entitlements_ts.read_text(encoding="utf-8")
        self.assertIn("evaluateServiceEntitlement", ent_text)
        self.assertIn("SUBSCRIPTION_INACTIVE", ent_text)
        self.assertIn("TRIAL_EXPIRED", ent_text)
        self.assertIn("QUOTA_EXCEEDED", ent_text)

        sec_audit_api = (
            WEB_ROOT / "apps/cp/src/pages/api/client/security-audit.ts"
        ).read_text(encoding="utf-8")
        corp_verify_api = (
            WEB_ROOT / "apps/cp/src/pages/api/admin/corporate-verify.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("evaluateServiceEntitlement", sec_audit_api)
        self.assertIn("evaluateServiceEntitlement", corp_verify_api)

        corp_svelte = (
            WEB_ROOT / "apps/cp/src/components/admin/CorporateVerification.svelte"
        ).read_text(encoding="utf-8")
        for code in ("MX", "CR", "PA", "BR", "CO", "AR", "CL", "PE"):
            self.assertIn(f'country: "{code}"', corp_svelte)

        sub_svelte = (
            WEB_ROOT / "apps/cp/src/components/client/SubscriptionManager.svelte"
        ).read_text(encoding="utf-8")
        self.assertIn('data-testid="service-usage-gauges"', sub_svelte)

        mig_t364 = (
            API_ROOT
            / "supabase/migrations/20261021200000_t364_client_subscription_trial_and_quotas.sql"
        )
        self.assertTrue(mig_t364.is_file())
        mig_text = mig_t364.read_text(encoding="utf-8")
        self.assertIn("trial_ends_at", mig_text)
        self.assertIn("service_quotas", mig_text)
        self.assertIn("service_usage", mig_text)

    def test_t351_mexican_payment_rails(self) -> None:
        rails_ts = WEB_ROOT / "packages/lib/src/payments/mexican-rails.ts"
        self.assertTrue(rails_ts.is_file())
        rails_text = rails_ts.read_text(encoding="utf-8")
        for fn in (
            "validateClabe",
            "generateSpeiReference",
            "buildSpeiWireInstructions",
            "buildMercadoPagoPreference",
            "verifyMercadoPagoSignature",
        ):
            self.assertIn(f"export function {fn}" if "verify" not in fn else f"export async function {fn}", rails_text)

        for edge_fn in (
            "supabase/functions/_shared/mexican-payments.ts",
            "supabase/functions/mercadopago-checkout/index.ts",
            "supabase/functions/mercadopago-webhook/index.ts",
        ):
            self.assertTrue((API_ROOT / edge_fn).is_file(), f"Missing edge function: {edge_fn}")

        for cp_api in (
            "apps/cp/src/pages/api/payments/mercadopago-checkout.ts",
            "apps/cp/src/pages/api/payments/mercadopago-webhook.ts",
            "apps/cp/src/pages/api/admin/invoices/reconcile-spei.ts",
        ):
            self.assertTrue((WEB_ROOT / cp_api).is_file(), f"Missing CP API route: {cp_api}")

        inv_list = (
            WEB_ROOT / "apps/cp/src/components/client/InvoiceList.svelte"
        ).read_text(encoding="utf-8")
        self.assertIn('data-testid="mexican-payment-rail-selector"', inv_list)
        self.assertIn('data-testid="spei-wire-instructions"', inv_list)

        inv_mgr = (
            WEB_ROOT / "apps/cp/src/components/admin/InvoiceManager.svelte"
        ).read_text(encoding="utf-8")
        self.assertIn("reconcileSpeiInvoice", inv_mgr)
        self.assertIn("Reconcile SPEI", inv_mgr)

        mig_t351 = (
            API_ROOT
            / "supabase/migrations/20261021201000_t351_mexican_payment_rails_invoices.sql"
        )
        self.assertTrue(mig_t351.is_file())
        mig_text = mig_t351.read_text(encoding="utf-8")
        for col in (
            "currency",
            "amount_local",
            "exchange_rate",
            "spei_reference",
            "spei_clabe",
            "mercadopago_preference_id",
            "mercadopago_payment_id",
            "reconciled_by",
            "reconciled_at",
        ):
            self.assertIn(col, mig_text)

    def test_t279_t280_maksim_kulikov_and_client_check_conformance(self) -> None:
        policy_data: dict[str, Any] = json.loads(
            (ESTATE_ROOT / "project/policies/clients-policy.json").read_text(encoding="utf-8")
        )
        projects: dict[str, dict[str, Any]] = {
            str(p["id"]): p for p in policy_data.get("projects", [])
        }
        for pid in ("servicios777", "personaje0"):
            self.assertIn(pid, projects)
            p = projects[pid]
            self.assertEqual(p.get("org_slug"), "maksim-kulikov")
            self.assertEqual(p.get("project_slug"), pid)
            self.assertTrue(len(p.get("external_services", [])) >= 2)

            proc = subprocess.run(
                [sys.executable, "scripts/client_check.py", pid, "--json"],
                cwd=str(ESTATE_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, f"client_check.py {pid} failed: {proc.stdout}\n{proc.stderr}")
            report: dict[str, Any] = json.loads(proc.stdout)
            self.assertTrue(report.get("conforms"), f"{pid} did not conform: {report}")
            self.assertEqual(report.get("missing_required"), [])

        mig_t279 = (
            API_ROOT
            / "supabase/migrations/20261021202000_t279_t280_maksim_kulikov_servicios777_personaje0.sql"
        )
        self.assertTrue(mig_t279.is_file())
        mig_text = mig_t279.read_text(encoding="utf-8")
        self.assertIn("servicios777@webomage.com", mig_text)
        self.assertIn("maksim-kulikov", mig_text)
        self.assertIn("eg-servicios777", mig_text)
        self.assertIn("eg-personaje0", mig_text)
        self.assertIn("c2790031-2790-4000-8000-000000000001", mig_text)
        self.assertIn("c2790032-2790-4000-8000-000000000002", mig_text)


if __name__ == "__main__":
    unittest.main()
