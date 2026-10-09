"""
HookRegistry — intercept and transform agent tool calls, LLM calls, and memory ops.

Hooks:
  pre_tool_call   — transform args or abort before a tool runs
  post_tool_call  — transform result, log, or alert after a tool runs
  pre_llm_call    — inject context or rate-limit before LLM call
  post_llm_call   — parse, validate, or store after LLM response
  on_error        — retry logic or fallback routing on agent error
  on_memory_read  — access control / logging on memory read
  on_memory_write — validation / dedup on memory write
"""

from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class HookType(Enum):
    PRE_TOOL_CALL = "pre_tool_call"
    POST_TOOL_CALL = "post_tool_call"
    PRE_LLM_CALL = "pre_llm_call"
    POST_LLM_CALL = "post_llm_call"
    ON_ERROR = "on_error"
    ON_MEMORY_READ = "on_memory_read"
    ON_MEMORY_WRITE = "on_memory_write"


class HookRegistry:
    """Stores and executes lifecycle hooks across all agents."""

    def __init__(self):
        self._hooks: Dict[str, List[Callable]] = {
            h.value: [] for h in HookType
        }

    def register(self, hook_type: HookType, callback: Callable) -> None:
        """Register a hook callback for the given hook type."""
        self._hooks[hook_type.value].append(callback)

    def execute(self, hook_type: HookType, *args, **kwargs) -> Optional[Any]:
        """
        Execute all hooks of the given type sequentially.
        Returns the last non-None result, or None if all hooks return None.
        """
        last_result = None
        for hook in self._hooks[hook_type.value]:
            try:
                result = hook(*args, **kwargs)
                if result is not None:
                    last_result = result
            except Exception as exc:
                print(f"[HookRegistry] Error in hook '{hook_type.value}': {exc}")
        return last_result

    def has_hooks(self, hook_type: HookType) -> bool:
        return bool(self._hooks[hook_type.value])
