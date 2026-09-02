# `_msg` — manual client correspondence

For engagements where communication is **hand-driven** rather than through a system: messages,
documents and attachments going to or coming from a client.

    _msg/inbound/    what arrived  — from the client, verbatim
    _msg/outbound/   what was sent — our side, as sent

## Why keep it here

Because otherwise it lives in someone's chat client and nobody else can see it. BridgeRoad already
works this way — `_proj/bridgeroad/2026.08.31/` holds `Haidi MSG.md` beside `in/` and `out/`
directories — a convention that grew because it was needed. This names it once at the estate level
instead of each project reinventing it.

## Conventions

- One file per exchange, dated: `2026-09-02-<client>-<subject>.md`.
- **Record what was actually sent or received**, not a summary. A paraphrase in an archive is a
  claim about a conversation, and claims drift.
- Attachments beside the message, same date prefix.

🔴 **Client material is not public-tier content.** The KB content policy keeps client work out of
shared tiers; `_msg` is excluded from the estate repo for that reason — the directory is tracked so
the convention exists, its contents are not.
