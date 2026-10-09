"""
EvaluatorAgent — scores code quality, correctness, efficiency, and security.
"""

from typing import Any, Dict, Optional

from .base_agent import BaseAgent


_SYSTEM_PROMPT = """\
You are a senior Python code reviewer. Given any Python code and the task it
was written for, evaluate it objectively across five dimensions.

Adapt your evaluation to the nature of the code — do NOT assume a specific
domain, data structure, or algorithm. Judge each dimension on its own merits:

  CORRECTNESS  — Does the code fully and accurately fulfil the task?
  EFFICIENCY   — Are the algorithms and data structures appropriate for the
                 problem size and complexity?
  READABILITY  — Are names, structure, and style clear and maintainable?
  SECURITY     — Are inputs validated and common vulnerabilities avoided
                 (injection, unchecked eval, path traversal, etc.)?
  OVERALL      — A holistic score weighing all four dimensions.

You MUST output scores using EXACTLY this format (replace X with 1-10):

SCORE_CORRECTNESS: X/10
SCORE_EFFICIENCY: X/10
SCORE_READABILITY: X/10
SCORE_SECURITY: X/10
OVERALL: X/10
SUGGESTIONS:
- <specific, actionable suggestion>
- <specific, actionable suggestion>

Output all 5 score lines first, then SUGGESTIONS. Do NOT skip any score line.
"""


class EvaluatorAgent(BaseAgent):
    """Evaluates code quality and returns structured scores + suggestions."""

    def __init__(self, *args, **kwargs):
        super().__init__("EvaluatorAgent", *args, **kwargs)

    def execute(self, task: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Evaluate code.
        context keys:
            code             — source code to evaluate (required)
            execution_result — dict from ExecutorAgent (optional)
        """
        ctx = context or {}
        code = ctx.get("code", task)
        exec_result = ctx.get("execution_result", {})

        exec_summary = ""
        if exec_result:
            status = "SUCCESS" if exec_result.get("success") else "FAILED"
            exec_summary = (
                f"\nExecution status: {status}"
                f"\nstdout: {exec_result.get('stdout', '')[:300]}"
                f"\nstderr: {exec_result.get('stderr', '')[:300]}"
            )

        prompt = (
            f"Evaluate this Python code for the task: {task}\n\n"
            f"```python\n{code}\n```"
            f"{exec_summary}"
        )

        response = self._llm.chat(prompt, system=_SYSTEM_PROMPT)
        scores = self._parse_scores(response)

        return {"raw": response, "scores": scores}

    # ---------------------------------------------------------------- parse --
    @staticmethod
    def _parse_scores(text: str) -> Dict[str, Any]:
        import re

        scores: Dict[str, Any] = {}
        # Primary patterns (strict format)
        patterns = {
            "correctness": [
                r"SCORE_CORRECTNESS:\s*(\d+)/10",
                r"[Cc]orrectness[:\s]+?(\d+)\s*/\s*10",
                r"[Cc]orrectness[:\s]+?(\d+)",
            ],
            "efficiency": [
                r"SCORE_EFFICIENCY:\s*(\d+)/10",
                r"[Ee]fficiency[:\s]+?(\d+)\s*/\s*10",
                r"[Ee]fficiency[:\s]+?(\d+)",
            ],
            "readability": [
                r"SCORE_READABILITY:\s*(\d+)/10",
                r"[Rr]eadability[:\s]+?(\d+)\s*/\s*10",
                r"[Rr]eadability[:\s]+?(\d+)",
            ],
            "security": [
                r"SCORE_SECURITY:\s*(\d+)/10",
                r"[Ss]ecurity[:\s]+?(\d+)\s*/\s*10",
                r"[Ss]ecurity[:\s]+?(\d+)",
            ],
            "overall": [
                r"OVERALL:\s*(\d+)/10",
                r"[Oo]verall[:\s]+?(\d+)\s*/\s*10",
                r"[Oo]verall[:\s]+?(\d+)",
            ],
        }
        for key, pats in patterns.items():
            val = None
            for pat in pats:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    candidate = int(m.group(1))
                    # Sanity-check: must be 1–10
                    if 1 <= candidate <= 10:
                        val = candidate
                        break
            scores[key] = val

        # Extract suggestions block
        m = re.search(r"SUGGESTIONS:\s*(.*)", text, re.DOTALL | re.IGNORECASE)
        scores["suggestions"] = m.group(1).strip() if m else ""

        return scores
