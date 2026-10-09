"""
BaseAgent — abstract base for all agent types.

Lifecycle: CREATED → INITIALIZED → IDLE → RUNNING → [SUCCESS | FAILED] → TERMINATED

Every agent runs RALPH reasoning before executing its core logic.
"""

import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from ..core.agent_registry import AgentStatus


class BaseAgent(ABC):
    """
    Abstract base class shared by all agents.

    Constructor args (positional, in order):
        agent_type   — string label for this agent type
        llm_client   — OllamaClient instance
        event_bus    — EventBus instance
        hook_registry — HookRegistry instance
        memory_system — MemorySystem instance
        ralph_engine  — RalphEngine instance
    """

    def __init__(
        self,
        agent_type: str,
        llm_client,
        event_bus,
        hook_registry,
        memory_system,
        ralph_engine,
    ):
        self.agent_id: str = f"{agent_type}_{str(uuid.uuid4())[:6]}"
        self.agent_type: str = agent_type
        self.status: AgentStatus = AgentStatus.CREATED

        self._llm = llm_client
        self._event_bus = event_bus
        self._hooks = hook_registry
        self._memory = memory_system
        self._ralph = ralph_engine

        self._transition(AgentStatus.INITIALIZED)
        self._transition(AgentStatus.IDLE)

    # ----------------------------------------------------------- lifecycle --
    def _transition(self, new_status: AgentStatus) -> None:
        self.status = new_status
        self._event_bus.publish(
            "agent:status",
            {"agent_id": self.agent_id, "status": new_status.value},
        )

    # ------------------------------------------------------------ RALPH ----
    def _run_ralph(self, task: str, context: Optional[Dict] = None) -> Dict:
        trace = self._ralph.run(self.agent_type, task, context)
        self._event_bus.publish(
            "agent:ralph", {"agent_id": self.agent_id, "trace": trace}
        )
        return trace

    # ----------------------------------------------------------- override --
    @abstractmethod
    def execute(self, task: str, context: Optional[Dict] = None) -> Any:
        """Override in each concrete agent to implement the core logic."""

    # ----------------------------------------------------------- public ----
    def run(self, task: str, context: Optional[Dict] = None) -> Any:
        """
        Public entry point.
        1. Transitions to RUNNING.
        2. Runs RALPH reasoning trace.
        3. Calls execute().
        4. Transitions to SUCCESS or FAILED.
        """
        self._transition(AgentStatus.RUNNING)
        self._event_bus.publish(
            "agent:start", {"agent_id": self.agent_id, "task": task[:200]}
        )

        # RALPH reasoning before any action
        self._run_ralph(task, context)

        try:
            result = self.execute(task, context)
            self._transition(AgentStatus.SUCCESS)
            self._event_bus.publish(
                "agent:complete",
                {"agent_id": self.agent_id, "result": str(result)[:300]},
            )
            return result
        except Exception as exc:
            self._transition(AgentStatus.FAILED)
            self._event_bus.publish(
                "agent:error", {"agent_id": self.agent_id, "error": str(exc)}
            )
            raise
        finally:
            # Return to IDLE so agent can be reused
            if self.status in (AgentStatus.SUCCESS, AgentStatus.FAILED):
                self._transition(AgentStatus.IDLE)
