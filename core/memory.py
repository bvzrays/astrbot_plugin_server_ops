"""Long-term memory system (Nanobot-inspired).

Two-layer memory:
  - MEMORY.md: Permanent long-term facts, updated by LLM consolidation
  - HISTORY.md: Chronological, grep-searchable event log
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING, List, Dict, Any

if TYPE_CHECKING:
    pass


# LLM tool used for memory consolidation
_CONSOLIDATE_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Save the memory consolidation result to persistent storage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "history_entry": {
                        "type": "string",
                        "description": (
                            "A concise paragraph (2-5 sentences) summarizing key events, "
                            "commands run, outcomes, and decisions. Start with [YYYY-MM-DD HH:MM]."
                        ),
                    },
                    "memory_update": {
                        "type": "string",
                        "description": (
                            "Full updated long-term memory as Markdown. Include all existing facts "
                            "PLUS newly discovered ones (server configs, deploy paths, API endpoints, etc.). "
                            "Return UNCHANGED content if nothing new was learned."
                        ),
                    },
                },
                "required": ["history_entry", "memory_update"],
            },
        },
    }
]


class MemoryStore:
    """Persistent two-layer memory store for the ops agent."""

    def __init__(self, workspace: Path):
        mem_dir = workspace / "memory"
        mem_dir.mkdir(parents=True, exist_ok=True)
        self.memory_file = mem_dir / "MEMORY.md"
        self.history_file = mem_dir / "HISTORY.md"

    # ------------------------------------------------------------------ #
    #  Low-level I/O                                                       #
    # ------------------------------------------------------------------ #

    def read_memory(self) -> str:
        """Read current long-term memory."""
        return self.memory_file.read_text(encoding="utf-8") if self.memory_file.exists() else ""

    def write_memory(self, content: str) -> None:
        """Overwrite long-term memory."""
        self.memory_file.write_text(content, encoding="utf-8")

    def append_history(self, entry: str) -> None:
        """Append a timestamped entry to HISTORY.md."""
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    def search_history(self, pattern: str, max_results: int = 20) -> str:
        """Search HISTORY.md for a pattern and return matching lines."""
        if not self.history_file.exists():
            return "No history yet."
        results = []
        for line in self.history_file.read_text(encoding="utf-8").splitlines():
            if pattern.lower() in line.lower():
                results.append(line)
        if not results:
            return f"No matches for '{pattern}' in history."
        return "\n".join(results[-max_results:])

    # ------------------------------------------------------------------ #
    #  Context injection                                                   #
    # ------------------------------------------------------------------ #

    def get_memory_context(self) -> str:
        """Return the long-term memory block for system prompt injection."""
        text = self.read_memory()
        return f"## Long-term Memory\n\n{text}" if text else ""

    # ------------------------------------------------------------------ #
    #  LLM-based consolidation                                            #
    # ------------------------------------------------------------------ #

    async def consolidate(
        self,
        history: List[Dict[str, Any]],
        llm_provider,
        model: str,
        memory_window: int = 50,
    ) -> bool:
        """Summarize old history into MEMORY.md + HISTORY.md via LLM.

        Returns True on success.
        """
        if not history:
            return True

        # Build text for LLM to summarize
        lines = []
        for m in history:
            role = m.get("role", "?").upper()
            content = m.get("content", "")
            if content:
                ts = m.get("timestamp", "")[:16]
                lines.append(f"[{ts}] {role}: {content[:500]}")

        current_memory = self.read_memory()
        prompt = (
            "You are a memory consolidation agent. Based on the conversation below, "
            "call the save_memory tool with a summary.\n\n"
            f"## Current Long-term Memory\n{current_memory or '(empty)'}\n\n"
            f"## Conversation\n{chr(10).join(lines)}"
        )

        try:
            # Use AstrBot's LLM provider
            response = await llm_provider.text_chat(
                prompt=prompt,
                tools=_CONSOLIDATE_TOOL,
            )

            # Try to extract tool call arguments if model returned them
            # Fallback: just append the raw response as a history entry
            if hasattr(response, 'tool_calls') and response.tool_calls:
                tc = response.tool_calls[0]
                args = tc.arguments if hasattr(tc, 'arguments') else {}
                if entry := args.get("history_entry"):
                    self.append_history(entry)
                if update := args.get("memory_update"):
                    if update != current_memory:
                        self.write_memory(update)
            else:
                # Simplified fallback: append raw text as history
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                entry = f"[{now}] CONSOLIDATED: {str(response)[:300]}"
                self.append_history(entry)

            return True
        except Exception as e:
            from astrbot.api import logger
            logger.warning(f"MemoryStore.consolidate failed: {e}")
            return False
