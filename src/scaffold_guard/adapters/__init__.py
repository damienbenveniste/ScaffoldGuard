"""Agent adapter template selection."""

from scaffold_guard.adapters.base import AgentAdapter, adapters_for, adapters_for_selection
from scaffold_guard.adapters.claude import ClaudeAdapter
from scaffold_guard.adapters.codex import CodexAdapter
from scaffold_guard.adapters.cursor import CursorAdapter

__all__ = [
    "AgentAdapter",
    "ClaudeAdapter",
    "CodexAdapter",
    "CursorAdapter",
    "adapters_for",
    "adapters_for_selection",
]
