"""
DemoRunnerAgent — runs the validated code with LLM-generated demo inputs,
capturing real stdout output to prove the code works end-to-end.
"""

import re
from typing import Any, Dict, Optional

from .base_agent import BaseAgent
from ..core.sandbox_runner import SandboxRunner


_SYSTEM_PROMPT = """\
You are a Python code demonstrator. Given any working Python script or module,
write a concise, self-contained demo script that:

1. INCLUDES the original code INLINE — do NOT use import statements for it.
2. Reads and understands what the code does, then exercises its main public
   API (functions, classes, or top-level logic) with realistic sample inputs
   that cover typical use-cases.
3. Prints the result of every significant operation with a short, descriptive
   label so it is clear what is being shown, e.g.:
       print("<operation description> :", <result>)
   Adapt the labels and operations to whatever the code actually provides —
   do not assume a specific data structure or domain.
4. Covers at least: a normal/happy-path call, an edge case (empty input,
   zero, None, boundary value, etc.), and — where relevant — a sequence of
   operations that shows state changes over time.
5. Does NOT invoke unittest.main(), import or instantiate TestCase classes,
   or reproduce any existing `if __name__ == '__main__':` test block.
6. Wraps ONLY the final combined script (original code + demo section)
   in a single ```python ... ``` fence — nothing else outside the fence.

Keep the demo section to 15-25 lines of executable code after the original.
"""


class DemoRunnerAgent(BaseAgent):
    """Generates and executes a demo script to validate the final code live."""

    def __init__(self, sandbox: SandboxRunner, *args, **kwargs):
        self._sandbox = sandbox
        super().__init__("DemoRunnerAgent", *args, **kwargs)

    # ----------------------------------------------------------------- run --

    def execute(self, task: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Generate a demo script then execute it in the sandbox.

        context keys:
            code — the final validated Python code (required)
        """
        ctx = context or {}
        code = ctx.get("code", "")

        if not code:
            return {
                "demo_output": "",
                "demo_code": "",
                "success": False,
                "error": "No code provided to DemoRunnerAgent",
            }

        prompt = (
            f"Task: {task}\n\n"
            f"Working code:\n```python\n{code}\n```\n\n"
            "Write a complete, self-contained demo script (original code embedded "
            "inline) that runs the code with sample inputs and prints each result "
            "with a clear descriptive label. Do NOT call unittest.main()."
        )

        response = self._llm.chat(prompt, system=_SYSTEM_PROMPT)
        demo_code = self._extract_code(response)

        stdout, stderr, returncode = self._sandbox.execute(demo_code, "python")

        self._memory.stm.add(
            "assistant", f"Demo run complete (success={returncode == 0})"
        )

        return {
            "demo_code": demo_code,
            "demo_output": stdout.strip(),
            "demo_error": stderr.strip(),
            "success": returncode == 0,
        }

    # ---------------------------------------------------------------- util --

    @staticmethod
    def _extract_code(text: str) -> str:
        m = re.search(r"```python\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
        m = re.search(r"```\s*(.*?)```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        return text.strip()
