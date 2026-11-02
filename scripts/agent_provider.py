#!/usr/bin/env python3
"""Canonical Multi-Agent CLI & Orca Provider Abstraction (`T609` AC5).

Eliminates hardcoded `claude` / `agy` CLI assumptions and macOS-only `/Applications/Orca.app`
paths across Orca automations (`w0m_prs.py`, `t171_sandbox_cohort_runner.py`) and session
reattachment (`orca_sessions.py`).

Fails closed (`AgDR-0025`) when an explicitly requested provider CLI is not installed on the
host, preventing scheduled Orca automations from spawning `claude: command not found`.
"""

from __future__ import annotations

import os
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping


@dataclass(frozen=True)
class AgentProviderSpec:
    orca_id: str
    binaries: tuple[str, ...]
    aliases: tuple[str, ...]
    env_markers: tuple[str, ...]
    resume_template: str


AGENT_PROVIDER_SPECS: tuple[AgentProviderSpec, ...] = (
    AgentProviderSpec(
        orca_id="antigravity",
        binaries=("agy", "antigravity"),
        aliases=("antigravity", "agy"),
        env_markers=("ANTIGRAVITY_CLI", "AGY_CONVERSATION_ID"),
        resume_template="agy --conversation={session_id} --dangerously-skip-permissions",
    ),
    AgentProviderSpec(
        orca_id="claude",
        binaries=("claude",),
        aliases=("claude", "claude-code"),
        env_markers=("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"),
        resume_template="claude --resume {session_id} --dangerously-skip-permissions",
    ),
    AgentProviderSpec(
        orca_id="codex",
        binaries=("codex",),
        aliases=("codex",),
        env_markers=("CODEX_CLI", "CODEX_SANDBOX"),
        resume_template="codex resume {session_id}",
    ),
    AgentProviderSpec(
        orca_id="opencode",
        binaries=("opencode",),
        aliases=("opencode",),
        env_markers=("OPENCODE",),
        resume_template="opencode --session {session_id}",
    ),
    AgentProviderSpec(
        orca_id="gemini",
        binaries=("gemini",),
        aliases=("gemini", "gemini-cli"),
        env_markers=("GEMINI_CLI",),
        resume_template="gemini --resume {session_id}",
    ),
    AgentProviderSpec(
        orca_id="goose",
        binaries=("goose",),
        aliases=("goose",),
        env_markers=("GOOSE_PROVIDER",),
        resume_template="goose session --resume --name {session_id}",
    ),
)

SPECS_BY_ID: dict[str, AgentProviderSpec] = {s.orca_id: s for s in AGENT_PROVIDER_SPECS}
ALIAS_MAP: dict[str, str] = {
    alias: spec.orca_id for spec in AGENT_PROVIDER_SPECS for alias in spec.aliases
}


def normalize_provider_id(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.strip().lower()
    if not cleaned or cleaned == "auto":
        return None
    return ALIAS_MAP.get(cleaned)


def _default_search_dirs(home_dir: Path | None = None) -> tuple[Path, ...]:
    home = home_dir or Path.home()
    return (
        home / ".local" / "bin",
        Path("/home/linuxbrew/.linuxbrew/bin"),
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
    )


def find_agent_binary(
    provider_id: str,
    *,
    which_fn: Callable[[str], str | None] | None = None,
    extra_dirs: tuple[Path, ...] | None = None,
) -> str | None:
    canonical = ALIAS_MAP.get(provider_id.strip().lower())
    if not canonical:
        return None
    spec = SPECS_BY_ID[canonical]
    lookup = which_fn or shutil.which

    for binary in spec.binaries:
        found = lookup(binary)
        if found:
            return found

    if which_fn is None:
        for directory in extra_dirs if extra_dirs is not None else _default_search_dirs():
            for binary in spec.binaries:
                candidate = directory / binary
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    return str(candidate)
    return None


def list_installed_agent_providers(
    *,
    which_fn: Callable[[str], str | None] | None = None,
    extra_dirs: tuple[Path, ...] | None = None,
) -> list[str]:
    return [
        spec.orca_id
        for spec in AGENT_PROVIDER_SPECS
        if find_agent_binary(spec.orca_id, which_fn=which_fn, extra_dirs=extra_dirs) is not None
    ]


def resolve_agent_provider(
    requested: str | None = "auto",
    *,
    env: Mapping[str, str] | None = None,
    which_fn: Callable[[str], str | None] | None = None,
    extra_dirs: tuple[Path, ...] | None = None,
) -> str:
    """Resolve the Orca `--provider` / `agentId` to an installed agent CLI on this host.

    Order:
    1. Explicit `requested` argument (when not `"auto"` / empty) or `W0M_AGENT_PROVIDER` env var.
       Fails closed (`RuntimeError`) if unknown or its CLI binary is missing on this host.
    2. Active agent environment markers (`ANTIGRAVITY_CLI`, `CLAUDECODE`, `CODEX_CLI`, `OPENCODE`, …)
       when that agent's CLI binary is installed.
    3. First installed agent CLI in canonical priority order:
       `antigravity` (`agy`), `claude`, `codex`, `opencode`, `gemini`, `goose`.
    """
    environ = env if env is not None else os.environ
    raw_choice = (requested or "").strip()
    if not raw_choice or raw_choice.lower() == "auto":
        raw_choice = environ.get("W0M_AGENT_PROVIDER", "").strip()

    if raw_choice and raw_choice.lower() != "auto":
        canonical = normalize_provider_id(raw_choice)
        if not canonical:
            supported = ", ".join(s.orca_id for s in AGENT_PROVIDER_SPECS)
            raise RuntimeError(
                f"Unknown agent provider {raw_choice!r}; supported providers: {supported}"
            )
        if find_agent_binary(canonical, which_fn=which_fn, extra_dirs=extra_dirs) is None:
            installed = list_installed_agent_providers(which_fn=which_fn, extra_dirs=extra_dirs)
            raise RuntimeError(
                f"Requested agent provider {canonical!r} has no installed CLI binary on this host "
                f"(installed: {installed or 'none'})."
            )
        return canonical

    for spec in AGENT_PROVIDER_SPECS:
        if any(environ.get(marker) for marker in spec.env_markers):
            if find_agent_binary(spec.orca_id, which_fn=which_fn, extra_dirs=extra_dirs):
                return spec.orca_id

    installed = list_installed_agent_providers(which_fn=which_fn, extra_dirs=extra_dirs)
    if installed:
        return installed[0]

    checked = ", ".join(f"{s.orca_id} ({'/'.join(s.binaries)})" for s in AGENT_PROVIDER_SPECS)
    raise RuntimeError(f"No supported coding agent CLI found on this host (checked: {checked}).")


def resolve_orca_bin(
    *,
    which_fn: Callable[[str], str | None] | None = None,
    home_dir: Path | None = None,
) -> str:
    """Resolve the cross-platform `orca` CLI binary across Linux and macOS."""
    lookup = which_fn or shutil.which
    found = lookup("orca")
    if found:
        return found
    home = home_dir or Path.home()
    candidates = (
        home / ".local" / "bin" / "orca",
        home / ".config" / "orca" / "linux-orca-cli-shim" / "orca",
        Path("/Applications/Orca.app/Contents/Resources/bin/orca"),
    )
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return "orca"


def build_agent_resume_command(session_id: str, agent_type: str | None = None) -> str:
    """Build the shell command to resume/attach `session_id` for `agent_type`."""
    canonical = normalize_provider_id(agent_type) or "antigravity"
    spec = SPECS_BY_ID[canonical]
    safe_id = shlex.quote(session_id) if any(c.isspace() for c in session_id) else session_id
    return spec.resume_template.format(session_id=safe_id)
