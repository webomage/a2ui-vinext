# Headroom Proxy Issues Audit & `webomage/headroom` Fork Setup

**Ticket**: [[T377]], [[T378]]  
**Date**: 2026-09-25  
**Scope**: `wom7pr/headroom`, Claude Code, Antigravity, local proxy (`127.0.0.1:8787`), upstream Headroom repository.

---

## Executive Summary

1. **Fork Created & Configured**:
   - Upstream [`headroomlabs-ai/headroom`](https://github.com/headroomlabs-ai/headroom) has been forked into organization [`webomage/headroom`](https://github.com/webomage/headroom).
   - In [`wom7pr/headroom`](file:///Users/proto/Projects/@self/@wom/wom7pr/headroom), git remotes were realigned:
     - `origin` → `git@github.com:webomage/headroom.git`
     - `casualuser` → `git@github.com:casualuser/headroom.git` (preserved personal remote)
     - `upstream` → `git@github.com:headroomlabs-ai/headroom.git`
   - Active feature branches pushed to `webomage/headroom`:
     - `feat/omlx-proxy-routing` (multi-upstream routing for Anthropic Cloud + local oMLX)
     - `feat/audit-host-services` (host services security audit)
   - Updated [`wom7pr/README.md`](file:///Users/proto/Projects/@self/@wom/wom7pr/README.md) table mapping.

2. **Root Cause Analysis of Proxy Data Malformation**:
   A deep search across Claude Code sessions, local proxy logs (`~/.headroom/logs/proxy-8787.log`), and upstream issue reports revealed 6 major vectors where Headroom malforms or drops data:
   - **Claude Code Auto-mode & SSE Malformation**: Rewrote/dropped query parameters (`?beta=true`), `anthropic-version`/`anthropic-beta` headers, and safeguard payloads (`safeguard_results`). Opaque/unknown SSE frames were dropped or caused parser crashes (`TypeError: unhashable type`). Fixed upstream in PR #3784 (merged today into `main`).
   - **CCR Buffered Streaming Conversion (`stream:false` flip)**: Forces streaming turns into buffered mode when `headroom_retrieve` is in scope, causing 30–40s TTFT latency and empty streaming envelopes ("0 stream events received").
   - **Injected Tool Cache-Busting**: Injected `headroom_retrieve` tool mutates provider prefix, busting Anthropic prompt caching (81k+ cached tokens lost per turn).
   - **Kompress Single-Line JSON Corruption**: Kompress treated single-line structured JSON records as prose and compressed/truncated records (Upstream Issue #3673, PR #3786).
   - **System Role Wire Violation (HTTP 400)**: Non-text system messages left at `messages[0]` triggered Anthropic 400 errors (Upstream Issue #3667).
   - **Daemon Crash & Socket Resets**: Intermittent `ECONNRESET` (106 events) and `ConnectionRefused` when the local Python daemon enters unhealthy state.

---

## 1. Remote Alignment in `wom7pr/headroom`

```
webomage/headroom (GitHub)
       ▲
       │ origin (push/fetch)
┌──────┴──────────────────────────────────────────────────────┐
│                    wom7pr/headroom                          │
│                                                             │
│  Branches:                                                  │
│   • feat/omlx-proxy-routing  (tracking origin)              │
│   • feat/audit-host-services (tracking origin)              │
│   • main                     (tracking origin/main, v0.39.0)│
└──────┬───────────────────────┬──────────────────────────────┘
       │ casualuser            │ upstream
       ▼                       ▼
casualuser/headroom     headroomlabs-ai/headroom
```

### Remote Configuration

```bash
$ git -C wom7pr/headroom remote -v
casualuser  git@github.com:casualuser/headroom.git (fetch)
casualuser  git@github.com:casualuser/headroom.git (push)
origin      git@github.com:webomage/headroom.git (fetch)
origin      git@github.com:webomage/headroom.git (push)
upstream    git@github.com:headroomlabs-ai/headroom.git (fetch)
upstream    git@github.com:headroomlabs-ai/headroom.git (push)
```

Verified with `just forks`:
- `headroom: feat/omlx-proxy-routing` — `Origin Sync: +0/-0`, `Worktree: clean`.

---

## 2. Issues Detected Across Agents & Sessions

An audit of 572 Claude Code session logs (`~/.claude/projects/*/*.jsonl`), local Headroom logs (`~/.headroom/logs/proxy-8787.log`), and upstream issue trackers surfaced the following concrete failure modes:

### Issue Vector 1: Claude Code Auto-Mode & SSE Frame Dropping (PR #3784)
- **Symptom**: Claude Code reports auto-mode classifier fallback; safeguard results dropped; tool calls corrupted.
- **Mechanism**:
  - Headroom's native Anthropic handler stripped or mutated `anthropic-beta` parameters and query string flags (`?beta=true`).
  - Unknown SSE frames (e.g. `event: safeguard_results`) were omitted on re-rendering.
  - Reconstructing SSE streams failed when encountering non-scalar discriminators or malformed UTF-8 deltas, terminating streams abruptly.
- **Upstream Status**: Fixed in PR #3784 (`fix(proxy): preserve Claude Code auto-mode protocol`), merged into upstream `main` ~4 hours ago (`12c15796`). Local installation is currently `0.37.0` (does not have this fix).

### Issue Vector 2: CCR Buffered Stream Conversion & Empty Events (Issues #3587, #3266)
- **Symptom**: Claude Code reports `0 stream events received` or hangs for 30+ seconds before output renders.
- **Evidence in Local Logs**:
  ```text
  CCR: stream:true request has headroom_retrieve available; using buffered stream:false upstream request for server-side retrieval handling
  CCR: workspace unresolved; skipping track_compression (fail-closed)
  ```
- **Mechanism**:
  - The proxy intercepts `stream:true` requests and sends them upstream as `stream:false`.
  - When upstream responses take long or when streaming envelopes fail to reconstruct, only `ping` and `message_stop` events are emitted to the client, losing all content deltas.
  - Local proxy logs also showed `POST /v1/retrieve status=404` at `15:09:28`, indicating failed retrieval attempts.

### Issue Vector 3: Provider Prefix Cache Invalidation (Cache-Busting)
- **Symptom**: Large latency spikes and high token consumption despite warm sessions.
- **Mechanism**:
  - Dynamic injection of `headroom_retrieve` into `tools` alters the prefix byte sequence sent to Anthropic.
  - Upstream measured loss: `CACHE-BUST: expected_cached=81,024 actual_read=0 tokens_lost=81,024` (Issue #3266).
  - Even in our local diagnostic (`headroom_bootstrap.py`):
    - Headroom compression saved: `3,141,708` tokens over 1,290 reqs.
    - Anthropic prefix cache read: `316,959,838` tokens.
    - When cache busts occur, the loss outweighs proxy compression savings by 20–80x.

### Issue Vector 4: Record Deletion in Kompress (Issue #3673 & PR #3786)
- **Symptom**: Loss of JSON records and malformed structured command output.
- **Mechanism**:
  - Single-line JSON payloads or tabular command outputs were misclassified as prose by ContentRouter.
  - Kompress replaced sections with CCR hash markers (`[444 words compressed to ...]`), corrupting JSON syntax and dropping array items.

### Issue Vector 5: Wire Violation HTTP 400 on Non-Text System Messages (Issue #3667)
- **Symptom**: API returns HTTP 400: `messages.0: use the top-level 'system' parameter for the initial system prompt`.
- **Mechanism**:
  - Wire guard attempted to relocate system-role messages to top-level `system`, but skipped non-text content, leaving an illegal `role="system"` message at `messages[0]`.

### Issue Vector 6: Connection Drops & Unhealthy Daemon
- **Symptom**: 106 `ECONNRESET` and 22 `ConnectionRefused` events recorded across Claude Code project histories.
- **Local State**: `headroom_bootstrap.py` reports:
  ```text
  ❌ daemon deployment 'default' INSTALLED BUT NOT HEALTHY
  ```

---

## 3. Recommended Remediation & Next Steps

1. **Rebase `feat/omlx-proxy-routing` onto `upstream/main` (v0.39.0)**:
   - Incorporates PR #3784 (Claude Code auto-mode fix) and PR #3786 (tabular/JSON protection).
2. **Mitigate CCR Stream Buffering and Cache-Busting**:
   - Run proxy with `HEADROOM_NO_CCR=1` or `HEADROOM_LOSSLESS=1` in agent environments to prevent tool injection, avoid cache busts, and enforce 100% true streaming.
3. **Upgrade Local Daemon**:
   - Build wheel from `webomage/headroom` (or install updated version once tested) to resolve daemon unhealthiness.
