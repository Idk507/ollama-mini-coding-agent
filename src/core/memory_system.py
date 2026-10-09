"""
MemorySystem — STM (short-term), LTM (long-term), and Working Memory.

STM  — sliding window conversation buffer (last N turns), in-memory.
LTM  — persistent KV store backed by JSON file; keyword-searchable.
Working Memory — active task context cleared on session end.
"""

import hashlib
import json
import os
import time
from collections import deque
from typing import Any, Dict, List, Optional


class STM:
    """Short-Term Memory: sliding window conversation buffer."""

    def __init__(self, max_turns: int = 20):
        self._buffer: deque = deque(maxlen=max_turns)

    def add(self, role: str, content: str) -> None:
        self._buffer.append(
            {"role": role, "content": content, "timestamp": time.time()}
        )

    def get_recent(self, n: int = None) -> List[Dict]:
        buf = list(self._buffer)
        return buf[-n:] if n else buf

    def to_messages(self) -> List[Dict[str, str]]:
        """Return buffer as role/content dicts suitable for LLM history."""
        return [{"role": e["role"], "content": e["content"]} for e in self._buffer]

    def clear(self) -> None:
        self._buffer.clear()

    def __len__(self) -> int:
        return len(self._buffer)


class LTM:
    """Long-Term Memory: persistent JSON-backed KV store with keyword search."""

    def __init__(self, storage_path: str = "ltm.json"):
        self._path = storage_path
        self._store: Dict[str, Any] = {}
        self._load()

    # ------------------------------------------------------------------ I/O --
    def _load(self) -> None:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    self._store = json.load(fh)
            except (json.JSONDecodeError, OSError):
                self._store = {}

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(self._store, fh, indent=2, default=str)
        except OSError as exc:
            print(f"[LTM] Failed to save: {exc}")

    # --------------------------------------------------------------- public --
    def write(self, topic: str, value: Any, importance: float = 0.5) -> str:
        key = f"ltm:{topic}:{hashlib.md5(str(value).encode()).hexdigest()[:8]}"
        self._store[key] = {
            "value": value,
            "topic": topic,
            "importance": max(0.0, min(1.0, importance)),
            "timestamp": time.time(),
            "access_count": 0,
        }
        self._save()
        return key

    def read(self, key: str) -> Optional[Any]:
        if key in self._store:
            self._store[key]["access_count"] += 1
            self._save()
            return self._store[key]["value"]
        return None

    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        query_lower = query.lower()
        results = []
        for key, item in self._store.items():
            if query_lower in str(item["value"]).lower() or query_lower in item["topic"].lower():
                results.append({"key": key, **item})
        return sorted(results, key=lambda x: x["importance"], reverse=True)[:top_k]

    def all_keys(self) -> List[str]:
        return list(self._store.keys())

    def __len__(self) -> int:
        return len(self._store)


class WorkingMemory:
    """Active task context; cleared on session end."""

    def __init__(self):
        self._ctx: Dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._ctx[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._ctx.get(key, default)

    def delete(self, key: str) -> None:
        self._ctx.pop(key, None)

    def clear(self) -> None:
        self._ctx.clear()

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._ctx)


class MemorySystem:
    """Facade combining STM, LTM, and Working Memory for a session."""

    def __init__(self, session_id: str, storage_dir: str = "memory"):
        os.makedirs(storage_dir, exist_ok=True)
        ltm_path = os.path.join(storage_dir, "ltm.json")
        self.session_id = session_id
        self.stm = STM(max_turns=20)
        self.ltm = LTM(storage_path=ltm_path)
        self.working = WorkingMemory()
