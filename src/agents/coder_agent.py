"""
CoderAgent — generates Python code from natural language task descriptions.
"""

import re
from typing import Any, Dict, Optional

from .base_agent import BaseAgent


_SYSTEM_PROMPT = """\
You are an expert Python programmer. Given a task description of any kind,
generate clean, correct, and idiomatic Python code that fully satisfies it.

Rules:
1. Read the task carefully — do NOT assume a specific data structure, algorithm,
   or domain. Implement exactly what is asked.
2. Write a complete, runnable script: include all necessary imports and an
   `if __name__ == '__main__':` guard when the task calls for one.
3. Prefer the standard library; only use third-party packages when the task
   explicitly requires them or they are clearly the best fit.
4. Handle obvious edge cases (empty input, zero values, None, boundary
   conditions) unless the task scope clearly excludes them.
5. Keep the code readable: use descriptive names, keep functions focused, and
   avoid unnecessary complexity.
6. Respond with ONLY the code wrapped in a single ```python ... ``` fence.
   Do NOT include any explanation, commentary, or prose outside the fence.
"""


class CoderAgent(BaseAgent):
    """Generates Python code from a natural-language task description."""

    def __init__(self, *args, **kwargs):
        super().__init__("CoderAgent", *args, **kwargs)

    def execute(self, task: str, context: Optional[Dict] = None) -> str:
        """Return raw Python source code as a string."""
        prompt = f"Generate Python code for the following task:\n\n{task}"

        if context:
            if context.get("requirements"):
                prompt += f"\n\nAdditional requirements:\n{context['requirements']}"
            if context.get("previous_error"):
                prompt += f"\n\nNote: A previous attempt produced this error:\n{context['previous_error']}"

        if context.get("feedback"):
            prompt += f"\n\nFeedback from previous subtasks:\n{context['feedback']}"
        if context.get("parent_task"):
            prompt += (
                f"\n\nThis is subtask {context.get('subtask_id', '?')} of a "
                f"larger task: {context['parent_task'][:200]}"
            )

        response = self._llm.chat(prompt, system=_SYSTEM_PROMPT)
        code = self._extract_code(response)

        self._memory.stm.add("assistant", f"Generated code for: {task[:80]}")
        return code

    # ---------------------------------------------------------------- util --
    @staticmethod
    def _extract_code(text: str) -> str:
        """Extract code from ```python ... ``` or ``` ... ``` fences."""
        # Try python-fenced block first
        m = re.search(r"```python\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # Generic fenced block
        m = re.search(r"```\s*(.*?)```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        # No fences — return raw (model may have skipped fences)
        return text.strip()
