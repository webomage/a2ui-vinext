# Hostinger MCP Complete Purge & Decommissioning Audit

- **Date:** 2026-09-28
- **Ticket:** [[T483]] — [#483](https://github.com/webomage/wom7board/issues/483)
- **Commit:** [`f531f1e`](https://github.com/casualuser/w0m/commit/f531f1e)
- **Status:** Closed (`status: done`, 5/5 ACs confirmed, 4/4 cross-surface consensus)

---

## 1. Executive Summary

Per owner directive (*"we do not need hostinger anymore anywhere, purge it from mcp, etc"*), all Hostinger MCP integrations, processes, credentials, schemas, and configurations across the machine and estate have been completely purged under [[T483]].

A multi-tiered audit verified:
1. **Processes**: Terminated **42** background node/npm MCP worker processes that were silently running across active/dormant terminal sessions (`s001`, `s004`, `s014`).
2. **MCP Configurations**: Removed all `hostinger-*` entries from `~/.claude.json`, `~/.gemini/config/mcp_config.json`, and `~/.gemini/antigravity/mcp_config.json`.
3. **Tool Schemas**: Deleted **21** schema directories across `~/.gemini/antigravity-cli/mcp/`, `~/.gemini/antigravity-ide/mcp/`, and `~/.gemini/antigravity/mcp/`.
4. **Local Credentials & Cache**: Purged `~/.config/hostinger-mcp/` and uninstalled cached npx packages from `~/.npm/_npx/`.
5. **Estate Declarations**: Removed the 6 decommissioned entries from [`.w0m/sdlc.json`](.w0m/sdlc.json). Verified `just mcp-declared-test` and `mcp_health.py` probe suite pass cleanly.

---

## 2. Multi-Layer Decommission Matrix

| Layer | Target Surface | Before Purge | After Purge | Verification Status |
|---|---|---|---|---|
| **Runtime Processes** | `ps aux \| grep hostinger` | 42 running node/npm MCP instances | 0 processes | ✅ `pgrep -f hostinger` returns clean |
| **Claude MCP Config** | `~/.claude.json` | 7 servers declared | 0 servers | ✅ Verified JSON keys |
| **Antigravity CLI Config** | `~/.gemini/config/mcp_config.json` | 7 servers declared | 0 servers | ✅ Verified JSON keys |
| **Antigravity IDE Config** | `~/.gemini/antigravity/mcp_config.json` | 7 servers declared | 0 servers | ✅ Verified JSON keys |
| **Tool Schemas (CLI)** | `~/.gemini/antigravity-cli/mcp/hostinger-*` | 7 schema folders | 0 folders | ✅ Deleted |
| **Tool Schemas (IDE)** | `~/.gemini/antigravity-ide/mcp/hostinger-*` | 7 schema folders | 0 folders | ✅ Deleted |
| **Tool Schemas (Core)**| `~/.gemini/antigravity/mcp/hostinger-*` | 7 schema folders | 0 folders | ✅ Deleted |
| **Local Credentials** | `~/.config/hostinger-mcp/credentials.json` | Present | Deleted | ✅ Path non-existent |
| **NPX Package Cache** | `~/.npm/_npx/*/node_modules/.bin/hostinger*` | 12 wrapper binaries | Deleted | ✅ Path non-existent |
| **Estate Declarations**| `.w0m/sdlc.json` | 6 decommissioned entries | 0 entries | ✅ `just mcp-declared-test` PASS |

---

## 3. Verified Acceptance Criteria

- [x] **AC1 — Background Process Termination:** 
  All 42 active `node ... hostinger-*-mcp` and `npm exec hostinger-*-mcp` processes across sessions `s001`, `s004`, and `s014` terminated via process signal. Confirmed 0 matching PIDs remaining.
- [x] **AC2 — MCP Configuration Purge:** 
  Backed up original configs to `*.bak.20260928` and cleanly removed `hostinger-hosting`, `hostinger-wordpress`, `hostinger-agency-hosting`, `hostinger-domains`, `hostinger-dns`, `hostinger-billing`, and `hostinger-reach` from all three global configuration files.
- [x] **AC3 — Tool Schema Directory Removal:** 
  Deleted all 21 schema directories. `ls -d ~/.gemini/*/mcp/hostinger*` returns zero matches.
- [x] **AC4 — Local Credentials & Binary Cache Cleanup:** 
  Deleted `~/.config/hostinger-mcp` (holding `credentials.json`) and removed cached binary wrappers under `~/.npm/_npx/a7204b5813574340`.
- [x] **AC5 — SDLC Registry & Integration Gates:** 
  Cleaned `.w0m/sdlc.json`. `just mcp-declared-test` passed all 23 assertions. `scripts/mcp_health.py` now discovers and probes only the 5 valid stdio servers (`codegraph`, `graphify`, `headroom`, `obsidian-wom7web`, `serena`), with zero Hostinger servers in the probe set.

---

## 4. Cross-Surface Consensus

```
# Ticket Reality Audit — T483
Recorded: status=done, 5/5 ACs (100%) · Cross-surface: 4/4 agree
AC1: [x] confirmed (0 processes running)
AC2: [x] confirmed (0 servers across all 3 configs)
AC3: [x] confirmed (21 schema dirs removed)
AC4: [x] confirmed (credentials and npx cache deleted)
AC5: [x] confirmed (just mcp-declared-test PASS)

Bottom line: Recorded status done is trustworthy across surfaces with zero contradictions.
```
