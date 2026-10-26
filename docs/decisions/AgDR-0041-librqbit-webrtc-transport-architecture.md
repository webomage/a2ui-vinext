---
id: AgDR-0041
title: "librqbit WebRTC / WebTorrent Transport Architecture and Tauri Desktop Path"
timestamp: 2026-10-22T18:00:00-05:00
agent: antigravity
model: claude-opus-4-6
trigger: user-prompt
status: accepted
date: 2026-10-22
deciders: ["owner", "agent:antigravity"]
scope: oss
repos: ["w0m-web"]
ticket: T438
tickets: ["T437", "T438"]
supersedes: []
superseded_by:
---

# AgDR-0041: librqbit WebRTC / WebTorrent Transport Architecture and Tauri Desktop Path

## Y-statement

> In the context of **native Apple Silicon (`darwin-arm64`) BitTorrent and WebTorrent desktop client modernization (`T437` / `T438`)**, facing **the `~180 MB` bundle size and `320–450 MB` idle RAM overhead of Electron + Node.js alongside `librqbit`'s lack of WebRTC DataChannel peer transport**, we decided for **keeping `T437` (Electron 33 + `node-datachannel`) as the immediate compatibility release while adopting a feature-gated pure-Rust WebRTC transport (`#[cfg(feature = "webrtc")]`) + Tauri v2 (`WKWebView`) architecture for `librqbit` (`T438`)**, and neglected **bundling C/C++ `libdatachannel` FFI into `rqbit` or maintaining Electron long-term**, to achieve **a `~14 MB` memory-safe Rust desktop client with opt-in WebTorrent swarming**, accepting **the maintenance cost of a dedicated `wss://` SDP tracker signaling and 16 KiB SCTP DataChannel framing layer**.

## Context

`T437` modernized `webtorrent-desktop` for native Apple Silicon (`darwin-arm64`) execution by upgrading Electron (`12 -> 33`) and replacing the broken `wrtc` C++ addon with `node-datachannel`. While that unblocks immediate native `arm64` builds, an Electron + Node.js BitTorrent client still ships a `~180 MB` bundle, consumes `320-450 MB` idle RAM, and performs piece hashing on the Node runtime.

`T438` (split from `T437`) evaluated replacing the Electron/Node torrent engine with **Rust (`librqbit`)**, which already provides async `tokio` BitTorrent (`BEP-03`/`05`/`09`/`10`/`15`/`29`) and a built-in HTTP range-request media streaming server (`/torrents/{id}/stream/{file_idx}`), but lacks **WebTorrent (`WebRTC` DataChannel peer transport + `wss://` tracker signaling)**.

## Decision

1. **Keep `T437` (Electron 33 + `node-datachannel` in `webomage/webtorrent-desktop`) as the immediate compatibility release** for existing WebTorrent Desktop users on `darwin-arm64`.
2. **Adopt a feature-gated pure-Rust WebTorrent extension architecture (`#[cfg(feature = "webrtc")]`) for `webomage/rqbit` (`librqbit`):**
   - Generalize `librqbit`'s peer stream abstraction so `peer_connection::PeerConnection` operates over any `AsyncRead + AsyncWrite + Unpin + Send` stream (`DataChannelByteStream` enforcing the 16 KiB cross-browser SCTP chunk ceiling) rather than assuming a TCP/uTP `SocketAddr`.
   - Implement `wss://` WebSocket tracker signaling (`announce` with SDP offers/answers) in a dedicated module (`tracker_comms/wss_tracker.rs`) using `tokio-tungstenite`.
   - Keep WebRTC dependencies strictly opt-in (`feature = "webrtc"`, disabled by default) so upstream `librqbit` CLI/server builds incur zero extra compile time or binary size unless WebTorrent peer swarming is enabled.
3. **Use Tauri v2 (`WKWebView`) + `librqbit` HTTP Range Streaming as the next-generation macOS `arm64` desktop architecture**, eliminating bundled Chromium (`~180 MB` -> `~14 MB`).

## Consequences

- **Positive:** Cleanly separates immediate `darwin-arm64` maintenance (`T437`) from the Rust/Tauri native engine path (`T438`).
- **Positive:** Preserves 100% memory-safe Rust across the BitTorrent + WebRTC transport stack without introducing C/C++ `libdatachannel` FFI build complexity into `rqbit`.
- **Negative / Trade-off:** Full browser WebTorrent interoperability requires maintaining both the `wss://` SDP signaling state machine and SCTP DataChannel backpressure handling (`16 KiB` framing).
- **Enforcement:** Tracked in [`wom7web/docs/research/oss/2026-10-22-t438-librqbit-webrtc-webtorrent-evaluation.md`](../../wom7web/docs/research/oss/2026-10-22-t438-librqbit-webrtc-webtorrent-evaluation.md) and `.tasks/T438.md`.
