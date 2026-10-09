"""
ExecutorAgent — runs code in the SandboxRunner and reports results.
"""

from typing import Any, Dict, Optional

from .base_agent import BaseAgent
from ..core.sandbox_runner import SandboxRunner


class ExecutorAgent(BaseAgent):
    """Executes Python code in an isolated sandbox subprocess."""

    def __init__(self, sandbox: SandboxRunner, *args, **kwargs):
        self._sandbox = sandbox
        super().__init__("ExecutorAgent", *args, **kwargs)

    def execute(self, task: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Run code from context['code'] and return execution result dict.
        context keys:
            code     — source code string (required)
            language — runtime language, default 'python'
        """
        ctx = context or {}
        code = ctx.get("code", task)
        language = ctx.get("language", "python")

        # Stage any requested file operations in the sandbox before execution
        for op in ctx.get("file_ops", []):
            op_type = op.get("op", "")
            path = op.get("path", "")
            if op_type == "write" and path:
                self._sandbox.write_file(path, op.get("content", ""))
            elif op_type == "delete" and path:
                self._sandbox.delete_file(path)

        self._event_bus.publish(
            "sandbox:execute",
            {"agent_id": self.agent_id, "language": language, "code_preview": code[:200]},
        )

        stdout, stderr, returncode = self._sandbox.execute(code, language)

        result = {
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
            "success": returncode == 0,
        }

        self._event_bus.publish("sandbox:result", result)
        return result
