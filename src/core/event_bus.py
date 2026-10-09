"""
EventBus — publish/subscribe system for agent lifecycle and system events.
Event types: agent:spawn, agent:start, agent:complete, agent:error, agent:ralph,
             hook:pre, hook:post, memory:read, memory:write, sandbox:execute, sandbox:result
"""

import threading
from collections import defaultdict
from typing import Any, Callable, Dict, List


class EventBus:
    """Thread-safe publish/subscribe event bus."""

    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = defaultdict(list)
        self._lock = threading.Lock()
        self._history: List[Dict] = []

    def subscribe(self, event_type: str, callback: Callable) -> None:
        with self._lock:
            self._listeners[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        with self._lock:
            if callback in self._listeners[event_type]:
                self._listeners[event_type].remove(callback)

    def publish(self, event_type: str, data: Any = None) -> None:
        with self._lock:
            listeners = list(self._listeners[event_type])
            self._history.append({"type": event_type, "data": data})

        for listener in listeners:
            try:
                listener(event_type, data)
            except Exception as exc:
                print(f"[EventBus] Error in listener for '{event_type}': {exc}")

    def get_history(self, event_type: str = None) -> List[Dict]:
        if event_type:
            return [e for e in self._history if e["type"] == event_type]
        return list(self._history)

    def clear_history(self) -> None:
        self._history.clear()
