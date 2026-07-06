"""Agent adapter template selection."""

from agent_safe.adapters.base import AgentAdapter, adapters_for
from agent_safe.adapters.claude import ClaudeAdapter
from agent_safe.adapters.codex import CodexAdapter
from agent_safe.adapters.cursor import CursorAdapter

__all__ = [
    "AgentAdapter",
    "ClaudeAdapter",
    "CodexAdapter",
    "CursorAdapter",
    "adapters_for",
]
