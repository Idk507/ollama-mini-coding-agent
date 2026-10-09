"""
TaskDecomposer — breaks large tasks into ordered, self-contained subtasks.

A task is considered "large" when either:
  - Its description exceeds LARGE_TASK_CHARS characters, OR
  - The RALPH ANALYZE phase lists more than LARGE_TASK_STEPS distinct steps.

The LLM returns a numbered list; this module parses it into structured dicts
ready for the OrchestratorAgent subtask loop.
"""

import re
from typing import Any, Dict, List

LARGE_TASK_CHARS = 300
LARGE_TASK_STEPS = 3   # number of distinct steps/lines in ANALYZE phase

_DECOMPOSE_PROMPT = """\
You are a task planner. Break the following task into ordered, self-contained subtasks.

Task: {task}

RALPH Analysis:
{analyze}

Rules:
- Respond ONLY as a numbered list (no prose, no headers).
- Each subtask must be independently executable or depend only on earlier ones.
- Maximum 8 subtasks.
- Keep each description concise (one sentence).

Example:
1. Write a function that reads a CSV file.
2. Parse the CSV rows into a list of dicts.
3. Filter rows where column 'status' equals 'active'.
4. Write the filtered results to a new CSV file.
"""


class TaskDecomposer:
    """Determines whether a task needs breakdown and produces subtask lists."""

    def __init__(self, llm_client) -> None:
        self._llm = llm_client

    # ───────────────────────────────────────────────── public interface ────

    def should_decompose(self, task: str, ralph_trace: Dict[str, str]) -> bool:
        """Return True when the task warrants subtask decomposition."""
        if len(task) > LARGE_TASK_CHARS:
            return True

        analyze = ralph_trace.get("ANALYZE", "")
        # Count non-empty lines that look like enumerated items or sentences
        step_lines = [
            ln for ln in analyze.splitlines()
            if ln.strip() and (
                re.match(r"^\s*\d+[\.\)]\s", ln)   # numbered
                or re.match(r"^\s*[-*•]\s", ln)      # bulleted
                or "step" in ln.lower()
                or "then" in ln.lower()
            )
        ]
        return len(step_lines) > LARGE_TASK_STEPS

    def decompose(
        self, task: str, ralph_trace: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Ask the LLM to break *task* into subtasks.

        Returns a list of dicts:
          {
            "id": int,                # 1-based
            "description": str,
            "depends_on": List[int],  # ids of prerequisite subtasks
            "context_keys": List[str] # output keys from prior subtasks to inject
          }
        """
        analyze = ralph_trace.get("ANALYZE", "no analysis available")
        prompt = _DECOMPOSE_PROMPT.format(task=task, analyze=analyze)
        response = self._llm.chat(prompt)
        return self._parse_subtasks(response)

    # ───────────────────────────────────────────────── parsing ────────────

    @staticmethod
    def _parse_subtasks(text: str) -> List[Dict[str, Any]]:
        """Parse a numbered list from LLM output into structured subtask dicts."""
        subtasks: List[Dict[str, Any]] = []

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            # Match lines like "1. do something" or "1) do something"
            m = re.match(r"^(\d+)[.\)]\s+(.+)$", line)
            if not m:
                continue
            idx = int(m.group(1))
            description = m.group(2).strip()
            subtasks.append(
                {
                    "id": idx,
                    "description": description,
                    "depends_on": list(range(1, idx)),   # sequential dependency
                    "context_keys": (
                        [f"subtask_{idx - 1}_output"] if idx > 1 else []
                    ),
                }
            )

        # If the LLM returned nothing parseable, treat whole task as one subtask
        if not subtasks:
            subtasks = [
                {
                    "id": 1,
                    "description": text.strip() or "Complete the task.",
                    "depends_on": [],
                    "context_keys": [],
                }
            ]

        return subtasks
