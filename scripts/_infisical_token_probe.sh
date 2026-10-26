#!/bin/sh
# T134 task 3.1 — prove the Infisical read credential is what it claims to be.
#
# Runs as a CHILD of `infisical run`, so the token arrives injected and this script is the only
# thing that ever holds it. It prints verdicts and never a value, on any path.
#
# 🔑 Two properties, and the second is the load-bearing one:
#   1. the token is usable from the ENVIRONMENT (`INFISICAL_TOKEN`), so it never needs to appear in
#      argv where `ps` and shell history would expose it
#   2. the token CANNOT WRITE
#
# ⚠️ Property 2 is checked by ATTEMPTING A WRITE, because "I set the role to read-only" is a claim
# about a UI, not about the credential. The spec's own words for the route probe apply here: the
# absence of a capability must be checkable, not asserted. The probe key is obviously named and is
# deleted immediately if the write unexpectedly succeeds.
set -u

K=_W0M_T134_READONLY_PROBE
ENV_NAME="${1:-dev}"

if [ -z "${INFISICAL_SERVICE_TOKEN:-}" ]; then
    echo "SKIP: INFISICAL_SERVICE_TOKEN is not injected — nothing to prove yet (task 3.1)"
    exit 0
fi

export INFISICAL_TOKEN="$INFISICAL_SERVICE_TOKEN"
# Point HOME away from the operator's session so a PASS cannot be the session's doing. Without
# this the probe would certify the token while actually exercising the logged-in user.
export HOME=/nonexistent-w0m-no-session

if infisical secrets --env="$ENV_NAME" --silent >/dev/null 2>&1; then
    echo "PASS: the token READS $ENV_NAME from the environment (no argv exposure needed)"
else
    echo "FAIL: the token cannot read $ENV_NAME — wrong scope, expired, or not a valid token"
    exit 1
fi

if infisical secrets set "$K=probe" --env="$ENV_NAME" >/dev/null 2>&1; then
    echo "FAIL: 🔴 the token CAN WRITE — it is not read-only, and every 'no write path' claim in"
    echo "      this phase is currently false. Re-scope it in Infisical."
    if infisical secrets delete "$K" --env="$ENV_NAME" >/dev/null 2>&1; then
        echo "      cleanup: probe key deleted"
    else
        echo "      cleanup: FAILED — delete $K by hand"
    fi
    exit 1
fi

echo "PASS: the token CANNOT write — read-only scoping is real, not merely configured"
