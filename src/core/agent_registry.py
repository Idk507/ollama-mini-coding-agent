"""
AgentRegistry — central map of agentId → AgentInstance.
Supports spawn, terminate, pause, resume and emits lifecycle events.

Agent lifecycle:
  CREATED → INITIALIZED → IDLE → RUNNING → [SUCCESS | FAILED | PAUSED] → TERMINATED
"""

import threading
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentStatus(Enum):
    CREATED = "CREATED"
    INITIALIZED = "INITIALIZED"
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PAUSED = "PAUSED"
    TERMINATED = "TERMINATED"


class AgentRegistry:
    """Thread-safe central registry for all agents."""

    def __init__(self, event_bus):
        self._agents: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._event_bus = event_bus

    def register(self, agent) -> None:
        """Register a new agent and emit spawn event."""
        with self._lock:
            self._agents[agent.agent_id] = agent
        self._event_bus.publish(
            "agent:spawn",
            {"agent_id": agent.agent_id, "type": agent.agent_type},
        )

    def get(self, agent_id: str) -> Optional[Any]:
        return self._agents.get(agent_id)

    def list_agents(self) -> List[Any]:
        return list(self._agents.values())

    def terminate(self, agent_id: str) -> bool:
        agent = self._agents.get(agent_id)
        if agent:
            agent.status = AgentStatus.TERMINATED
            self._event_bus.publish(
                "agent:terminate", {"agent_id": agent_id}
            )
            return True
        return False

    def pause(self, agent_id: str) -> bool:
        agent = self._agents.get(agent_id)
        if agent and agent.status == AgentStatus.RUNNING:
            agent.status = AgentStatus.PAUSED
            return True
        return False

    def resume(self, agent_id: str) -> bool:
        agent = self._agents.get(agent_id)
        if agent and agent.status == AgentStatus.PAUSED:
            agent.status = AgentStatus.IDLE
            return True
        return False

    def get_summary(self) -> List[Dict]:
        return [
            {
                "agent_id": a.agent_id,
                "type": a.agent_type,
                "status": a.status.value,
            }
            for a in self._agents.values()
        ]
