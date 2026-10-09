"""
MemoryAgent — manages read/write operations on the STM and LTM stores.
"""

from typing import Any, Dict, List, Optional

from .base_agent import BaseAgent


class MemoryAgent(BaseAgent):
    """Provides a unified interface for memory operations."""

    def __init__(self, *args, **kwargs):
        super().__init__("MemoryAgent", *args, **kwargs)

    def execute(self, task: str, context: Optional[Dict] = None) -> Any:
        """
        Perform a memory operation.
        context keys:
            operation — 'read' | 'write' | 'search' | 'stm_history'
            key       — LTM key (for 'read')
            topic     — LTM topic (for 'write')
            value     — value to store (for 'write')
            importance — float 0-1 (for 'write', default 0.5)
            query     — search string (for 'search')
            n         — number of recent STM turns (for 'stm_history')
        """
        ctx = context or {}
        operation = ctx.get("operation", "search")

        self._event_bus.publish(
            "memory:read" if operation in ("read", "search", "stm_history") else "memory:write",
            {"agent_id": self.agent_id, "operation": operation},
        )

        if operation == "read":
            key = ctx.get("key", "")
            return self._memory.ltm.read(key)

        if operation == "write":
            return self._memory.ltm.write(
                topic=ctx.get("topic", "general"),
                value=ctx.get("value", ""),
                importance=float(ctx.get("importance", 0.5)),
            )

        if operation == "stm_history":
            return self._memory.stm.get_recent(ctx.get("n", 10))

        # Default: search
        query = ctx.get("query", task)
        return self._memory.ltm.search(query)
