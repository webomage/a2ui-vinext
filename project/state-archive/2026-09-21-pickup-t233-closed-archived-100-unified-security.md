<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### ⭐ (was) PICK UP HERE — 2026-09-21 — **T233 closed & archived (100%), unified security posture engine composing HOST, -->

### ⭐ (was) PICK UP HERE — 2026-09-21 — **T233 closed & archived (100%), unified security posture engine composing HOST, AUTHZ & PLATFORM checks into `just audit`, host startup baseline ratcheted, TCC fail-closed guard wired, and 19 red probes passing; all 180 test suites green; next: T407 (deploy/archive verification) / T406 (estate search) / T290 (Stage-4 Money).**

**What this session completed:**

1. **T233 (One security posture — compose platform and host checks) — Completed, Verified & Archived (100%)**:
   - **Unified Host Posture Engine**: Implemented `project/scripts/host_posture.py` asserting macOS Application Firewall, stealth mode, FileVault, SIP, Gatekeeper, and Postgres loopback binding (safe: 0 external exposure) (AC1, AC2).
   - **Startup Surface Ratchet**: Formulated `project/host-startup-baseline.json` cataloging all 26 root daemons, 5 login items, and 15 agents with reasons, reliably detecting new daemons and distinguishing dead-but-present plists (AC3).
   - **TCC Permission Grants & Fail-Closed Guard**: Enumerates TCC grants, properly reporting `NOT MEASURED` (never a false clean) when the agent runner lacks Full Disk Access (AC4).
   - **VPN Rulings & Policies**: Authored `docs/backend/TUNNEL-POLICIES.md` establishing explicit operational rulings for WARP (Approved), RUSVPN (Restricted), Windscribe (Unmanaged), and Tunnelblick (Unmanaged) (AC5).
   - **Unmeasured Dimensions Accounting**: Formally records outbound network telemetry and browser extensions as `NOT MEASURED` per T96 AC3 (AC6).
   - **Offline Red Probes**: 19 offline mutation tests in `project/scripts/tests/test_host_posture.py` proving all failure modes pass offline (AC7).
   - **Scheduled Execution**: Added daily audit schedule to `project/launchd/schedules.jsonc` (AC8).
   - **OpenSpec & Sync**: Spec change `2026-09-20-security-posture-audit` archived cleanly; GitHub issue #233 closed.

2. **Grounding & Test Suite Fixes Across Estate**:
   - Fixed `ac-recipe-check` by forwarding `worktree-agent*` from `wom7web/justfile` to root justfile (T411).
   - Fixed `emoji-check` by syncing line exemption in `project/policies/emoji-policy.json` (`tasks_render.py:129`).
   - Fixed `deploy-in-flight` by making `estate_root()` resolve against `.w0m/sdlc.json`'s config location.
   - Re-locked skills manifest via `just skill relock` (169/169 tests pass).
   - Full `just test` (180 suites, 3,121 checks) exits 0 cleanly.

3. **Next Pickup Candidates**:
   - **T407** (P2, 100% ACs, awaiting deploy/archive gate closure).
   - **T406** (P1, searching estate root grep seeing 19 of 92,467 files).
   - **T290** (P1, Stage-4 Money).
