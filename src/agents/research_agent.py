"""
ResearchAgent — knowledge retrieval and context enrichment using the LLM.

Since we operate without live web access, the agent uses the LLM's training
knowledge to answer research queries and enrich task context.
"""

from typing import Any, Dict, Optional

from .base_agent import BaseAgent


_SYSTEM_PROMPT = """\
You are a knowledgeable research assistant for software engineering and
programming topics. When asked any research question, answer concisely and
factually based on your training knowledge.

Adapt your response to the nature of the question — do NOT assume a specific
language, framework, or domain unless the question specifies one.

Structure every answer as:
1. A short summary (2-3 sentences) stating the direct answer.
2. Key points as concise bullet points covering important details,
   trade-offs, or caveats relevant to the question.
3. Concrete examples, API names, library names, or commands where they
   meaningfully support the answer — omit this section if not applicable.

Be specific and actionable. Avoid filler phrases and generic advice.
"""


class ResearchAgent(BaseAgent):
    """Provides knowledge enrichment for the other agents."""

    def __init__(self, *args, **kwargs):
        super().__init__("ResearchAgent", *args, **kwargs)

    def execute(self, task: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Research a topic and return findings.
        task — the research question or topic.
        context keys:
            focus — optional focus area (e.g. 'performance', 'security')
        """
        focus = (context or {}).get("focus", "")
        prompt = task
        if focus:
            prompt += f"\n\nFocus on: {focus}"

        response = self._llm.chat(prompt, system=_SYSTEM_PROMPT)

        # Store finding in LTM for future reference
        self._memory.ltm.write(
            topic="research",
            value={"query": task, "answer": response},
            importance=0.4,
        )

        return {"query": task, "answer": response}
