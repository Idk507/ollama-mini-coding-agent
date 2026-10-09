"""
SessionManager — unique sessionId per user task.
Tracks: messages, tool calls, code artifacts, RALPH traces, events.
Persists sessions to JSON files.
"""

import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional


class Session:
    """A single user task session with full audit trail."""

    def __init__(self, session_id: str = None):
        self.session_id: str = session_id or str(uuid.uuid4())[:8]
        self.created_at: float = time.time()
        self.messages: List[Dict] = []
        self.tool_calls: List[Dict] = []
        self.code_artifacts: List[Dict] = []
        self.ralph_traces: List[Dict] = []
        self.events: List[Dict] = []

    # --------------------------------------------------------- add helpers --
    def add_message(self, role: str, content: str) -> None:
        self.messages.append(
            {"role": role, "content": content, "timestamp": time.time()}
        )

    def add_tool_call(self, agent_id: str, tool: str, args: Any, result: Any) -> None:
        self.tool_calls.append(
            {
                "agent_id": agent_id,
                "tool": tool,
                "args": args,
                "result": str(result)[:500],
                "timestamp": time.time(),
            }
        )

    def add_code_artifact(
        self, code: str, language: str = "python", description: str = ""
    ) -> None:
        self.code_artifacts.append(
            {
                "code": code,
                "language": language,
                "description": description,
                "timestamp": time.time(),
            }
        )

    def add_ralph_trace(self, agent_id: str, trace: Dict) -> None:
        self.ralph_traces.append(
            {"agent_id": agent_id, "trace": trace, "timestamp": time.time()}
        )

    def add_event(self, event_type: str, data: Any = None) -> None:
        self.events.append(
            {"type": event_type, "data": data, "timestamp": time.time()}
        )

    # --------------------------------------------------------------- I/O --
    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "messages": self.messages,
            "tool_calls": self.tool_calls,
            "code_artifacts": self.code_artifacts,
            "ralph_traces": self.ralph_traces,
            "events": self.events,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Session":
        session = cls(data["session_id"])
        session.created_at = data.get("created_at", time.time())
        session.messages = data.get("messages", [])
        session.tool_calls = data.get("tool_calls", [])
        session.code_artifacts = data.get("code_artifacts", [])
        session.ralph_traces = data.get("ralph_traces", [])
        session.events = data.get("events", [])
        return session


class SessionManager:
    """Creates, saves, loads, and lists sessions."""

    def __init__(self, storage_dir: str = "sessions"):
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)
        self._sessions: Dict[str, Session] = {}

    def create_session(self) -> Session:
        session = Session()
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def save_session(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        path = os.path.join(self.storage_dir, f"{session_id}.json")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(session.to_dict(), fh, indent=2, default=str)
            return True
        except OSError as exc:
            print(f"[SessionManager] Save failed: {exc}")
            return False

    def load_session(self, session_id: str) -> Optional[Session]:
        path = os.path.join(self.storage_dir, f"{session_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            session = Session.from_dict(data)
            self._sessions[session_id] = session
            return session
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[SessionManager] Load failed: {exc}")
            return None

    def list_sessions(self) -> List[str]:
        return [
            f.replace(".json", "")
            for f in os.listdir(self.storage_dir)
            if f.endswith(".json")
        ]
