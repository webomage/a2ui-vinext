---
name: w0m-handoff
description: Generate a continuation prompt for handing off work to a new context window. Use when user says "/w0m:handoff", "hand off", "context handoff", or wants to prepare a prompt to resume work in a fresh conversation.
metadata:
  version: "2026.07.27-1785131185"
---

# /w0m:handoff (Context Preservation)

Your job is to generate a comprehensive continuation prompt that captures the current work state so the user can resume seamlessly in a new context window.

## Process
This is an **interactive** process. Do NOT skip ahead.

1. **Understand Goal**: Ask the user: "What's the overall goal you're working on?"
2. **Gather Progress**: Ask: "What has been accomplished so far?" (Investigate `git log` or `task.md` if they say "you tell me").
3. **Remaining Work**: Ask: "What's left to do?"
4. **Key Context**: Ask: "Are there any failed approaches, tricky gotchas, or architectural decisions the next session needs to know?"
5. **Constraints**: Ask: "Any rules or preferences for how the next session should operate?"

## Output Generation
Once all answers are collected, output a single, copy-pasteable Markdown prompt inside a fenced code block:

````markdown
## Goal
[Goal description]

## Context & Important Notes
[Decisions, gotchas, failed approaches]

## Progress
[What's done]

## Remaining Work
[What's left]

## Constraints
[Rules for proceeding]
````
