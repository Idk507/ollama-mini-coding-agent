"""
DebuggerAgent — analyzes execution errors and proposes fixed code.
"""

import re
from typing import Any, Dict, Optional

from .base_agent import BaseAgent


_SYSTEM_PROMPT = """\
You are an expert Python debugger. Given any broken Python code and its error
output, identify and fix all bugs.

Rules:
1. Analyse the full traceback and code to find the root cause — do NOT assume
   a specific bug type or domain. The issue may be a syntax error, a logic
   fault, a wrong algorithm, a missing edge-case guard, or anything else.
2. Explain the root cause in 1-2 sentences starting with "BUG:" placed
   OUTSIDE and BEFORE the code fence.
3. Provide the complete fixed code inside a single ```python ... ``` fence.
   Do NOT place any labels, prefixes, or commentary inside the fence.
4. Fix ONLY what is broken — preserve the original structure, algorithm, and
   intended behaviour everywhere else.
5. If multiple distinct bugs are present, fix all of them in the single
   corrected script and note each briefly in the "BUG:" explanation.
"""


class DebuggerAgent(BaseAgent):
    """Analyses errors and returns fixed Python code."""

    def __init__(self, *args, **kwargs):
        super().__init__("DebuggerAgent", *args, **kwargs)

    def execute(self, task: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Fix broken code.
        context keys:
            code  — original source code (required)
            error — stderr / error message from ExecutorAgent (required)
        """
        ctx = context or {}
        code = ctx.get("code", "")
        error = ctx.get("error", task)

        prompt = (
            f"Fix the following Python code.\n\n"
            f"Original code:\n```python\n{code}\n```\n\n"
            f"Error:\n{error}"
        )

        response = self._llm.chat(prompt, system=_SYSTEM_PROMPT)
        fixed_code = self._extract_code(response)

        return {
            "fixed_code": fixed_code,
            "explanation": response,
            "original_code": code,
        }

    # ---------------------------------------------------------------- util --
    @staticmethod
    def _extract_code(text: str) -> str:
        m = re.search(r"```python\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if m:
            code = m.group(1).strip()
        else:
            m = re.search(r"```\s*(.*?)```", text, re.DOTALL)
            if m:
                code = m.group(1).strip()
            else:
                code = text.strip()

        # Strip any leading label lines (e.g. "FIX:", "BUG:") that the LLM
        # may have placed inside the code block.
        lines = code.splitlines()
        while lines and re.match(r'^[A-Z_]+:\s*$', lines[0].strip()):
            lines.pop(0)
        return "\n".join(lines).strip()
