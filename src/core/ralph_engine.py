"""
RalphEngine — Reflect → Analyze → Learn → Plan → Hypothesize reasoning loop.

Each agent runs RALPH before executing any tool call.
The trace is stored in the session event log.
"""

from typing import Any, Dict, Optional


_RALPH_PROMPT_TEMPLATE = """\
You are performing RALPH (Reflect→Analyze→Learn→Plan→Hypothesize) reasoning.

Agent: {agent_name}
Task: {task}
Context: {context}

Respond ONLY in this exact format (one line per phase, no extra sections):

REFLECT: <what you know about this task from past experience>
ANALYZE: <breakdown of the problem, sub-tasks, risks>
LEARN: <relevant knowledge and patterns that apply>
PLAN: <step-by-step execution plan>
HYPOTHESIZE: <predicted outcome and success/failure criteria>
"""


class RalphEngine:
    """Generates and parses RALPH reasoning traces via the LLM."""

    def __init__(self, llm_client):
        self._llm = llm_client

    def run(
        self,
        agent_name: str,
        task: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        context_str = str(context) if context else "none"
        prompt = _RALPH_PROMPT_TEMPLATE.format(
            agent_name=agent_name,
            task=task,
            context=context_str,
        )
        response = self._llm.chat(prompt)
        return self._parse_ralph(response)

    # ---------------------------------------------------------------- parse --
    def _parse_ralph(self, text: str) -> Dict[str, str]:
        phases = ["REFLECT", "ANALYZE", "LEARN", "PLAN", "HYPOTHESIZE"]
        result: Dict[str, str] = {}

        for i, phase in enumerate(phases):
            marker = f"{phase}:"
            start = text.find(marker)
            if start == -1:
                continue
            content_start = start + len(marker)

            # Find the start of the next phase marker
            end = len(text)
            for next_phase in phases[i + 1 :]:
                next_marker = f"{next_phase}:"
                pos = text.find(next_marker, content_start)
                if pos != -1:
                    end = min(end, pos)

            result[phase] = text[content_start:end].strip()

        return result

    def format_trace(self, trace: Dict[str, str]) -> str:
        lines = ["[RALPH Trace]"]
        for phase in ["REFLECT", "ANALYZE", "LEARN", "PLAN", "HYPOTHESIZE"]:
            if phase in trace:
                snippet = trace[phase][:120].replace("\n", " ")
                lines.append(f"  {phase}: {snippet}")
        return "\n".join(lines)
