"""Context builder: assembles the system prompt from all sources.

Mirrors Nanobot's ContextBuilder:
  - Identity block (agent name, time, workspace, server info)
  - Bootstrap files (AGENTS.md, SOUL.md from workspace)
  - Long-term memory (MEMORY.md)
  - Always-loaded skills (full text)
  - Available skills (XML summary for lazy loading)
"""

from __future__ import annotations

import platform
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .memory import MemoryStore
from .skills import SkillsLoader


BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md"]


class ContextBuilder:
    """Assemble system prompt and message list for the agent."""

    def __init__(self, workspace: Path, agent_name: str = "OpsBot"):
        self.workspace = workspace
        self.agent_name = agent_name
        self.memory = MemoryStore(workspace)
        self.skills = SkillsLoader(workspace)

    # ------------------------------------------------------------------ #
    #  System Prompt                                                       #
    # ------------------------------------------------------------------ #

    def build_system_prompt(
        self,
        ssh_host: str = "",
        ssh_user: str = "",
        extra_context: str = "",
    ) -> str:
        """Build the full system prompt."""
        parts: List[str] = []

        # 1. Identity
        parts.append(self._identity(ssh_host, ssh_user))

        # 2. Bootstrap markdown files
        bootstrap = self._load_bootstrap()
        if bootstrap:
            parts.append(bootstrap)

        # 3. Long-term memory
        mem = self.memory.get_memory_context()
        if mem:
            parts.append(mem)

        # 4. Always-loaded skills (full text)
        always = self.skills.build_always_context()
        if always:
            parts.append(f"## Active Skills\n\n{always}")

        # 5. Skills summary for lazy loading
        summary = self.skills.build_skills_summary()
        if summary:
            parts.append(
                "## Available Skills\n\n"
                "To use a skill, read its SKILL.md with `read_file`. "
                "Skills not listed below simply do not exist yet.\n\n"
                + summary
            )

        # 6. Extra injected context (e.g. ops_skills KV)
        if extra_context:
            parts.append(extra_context)

        return "\n\n---\n\n".join(parts)

    def _identity(self, ssh_host: str, ssh_user: str) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        ws = str(self.workspace.resolve())
        ssh_info = f"  - SSH: {ssh_user}@{ssh_host}" if ssh_host else ""

        return f"""# {self.agent_name} — Server Ops Agent

You are **{self.agent_name}**, an AI-powered server operations specialist embedded in AstrBot (QQ).

## Current Time
{now}

## Workspace
{ws}
  - Long-term memory: {ws}/memory/MEMORY.md
  - Search history:   {ws}/memory/HISTORY.md
  - Skills:           {ws}/skills/<name>/SKILL.md
{ssh_info}

## Core Principles
1. **Action first** — call tools immediately, no lengthy preambles.
2. **Visualise** — use `render_output` for trees/logs rather than dumping text.
3. **Learn wisely** — only use `update_memory` to record facts with lasting value (endpoints, configs, deploy paths). Never record transient exploration commands.
4. **Verify** — re-read a file after writing it if accuracy matters.
5. **Media** — identify image URLs from the user's message and use `download_to_server` to place them on the server.
"""

    def _load_bootstrap(self) -> str:
        parts = []
        for fname in BOOTSTRAP_FILES:
            p = self.workspace / fname
            if p.exists():
                parts.append(f"## {fname}\n\n{p.read_text(encoding='utf-8')}")
        return "\n\n".join(parts)

    # ------------------------------------------------------------------ #
    #  Message list builder                                               #
    # ------------------------------------------------------------------ #

    def build_messages(
        self,
        history: List[Dict[str, Any]],
        current_message: str,
        system_prompt: str,
        image_urls: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Build complete message list for the LLM call."""
        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        messages.extend(history)

        # User message — optionally include inline images for vision LLMs
        if image_urls:
            content: Any = [{"type": "text", "text": current_message}]
            for url in image_urls:
                content.append({"type": "image_url", "image_url": {"url": url}})
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": current_message})

        return messages
